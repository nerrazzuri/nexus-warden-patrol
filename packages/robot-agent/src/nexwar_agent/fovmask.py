"""雷达视野表(真机 11-20):机身系里哪些格子是这台机器人的雷达**本来看得见**的。

遮挡限速(导航 V1 第 1 节)只把「本来看得见、这一帧却看不见」的格子当阴影。以前「本来看得见」用写死的
视野锥(机头外 ±0.6 m、往外每米加宽 0.9 m),仿真的假感知也用同一个锥,所以仿真里对得上;C40221 真机的
前雷达视野窄得多(机身中心往前 0.65 m 处 ±0.6、1.05 m 处 ±0.7、1.55 m 处 ±1.0),两个锥之间那一条永远
看不见,被当成阴影,空旷的地方也一直压到 0.2 m/s。

视野表从录包学(``tools/fov_learn.py``):空旷的地方走一段,每一格看得见的帧占多少,≥ 门槛的算视野里。
跟外参一样是每台机器人的标定产物,放 ``/etc/nexwar/fov.json``(``NEXWAR_FOV_FILE`` 改路径)。
没有、读不了、格式不对:照旧用写死的锥(不会更松)。
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

FOV_ENV = "NEXWAR_FOV_FILE"
FOV_DEFAULT = Path("/etc/nexwar/fov.json")
FOV_VERSION = 1
#: 一格在多少帧里看得见才算「本来看得见」。
FOV_THRESHOLD = 0.9
#: 学视野至少要这么多帧(10 Hz 雷达约 20 s)。
FOV_MIN_FRAMES = 150


def learn(knowns: Any, *, threshold: float = FOV_THRESHOLD) -> Any:
    """一串 n × n 的「看得见」(布尔数组)→ 视野表(布尔 n × n)。"""
    import numpy as np
    stack = np.asarray(knowns, dtype=bool)
    if stack.ndim != 3 or stack.shape[1] != stack.shape[2] or len(stack) == 0:
        raise ValueError(f"视野表:要一串 n × n 的格子,给的形状是 {stack.shape}")
    return stack.mean(axis=0) >= threshold


def to_wire(mask: Any, *, res: float, frames: int, threshold: float = FOV_THRESHOLD,
            source: str = "") -> dict[str, Any]:
    from nexwar_contract.obsbridge import pack_bits
    n = int(mask.shape[0])
    return {"version": FOV_VERSION, "size": n, "res": float(res), "threshold": float(threshold),
            "frames": int(frames), "source": str(source),
            "bits": pack_bits(bytes(mask.astype("uint8").ravel()), n)}


def from_wire(d: Any) -> tuple[Any, float]:
    """视野表 json → (布尔 n × n, 格子边长)。不对抛 ``ValueError``。"""
    import numpy as np

    from nexwar_contract.errors import ContractError
    from nexwar_contract.obsbridge import unpack_bits
    if not isinstance(d, dict) or d.get("version") != FOV_VERSION:
        raise ValueError("视野表:版本不认识")
    n, res = d.get("size"), d.get("res")
    if not isinstance(n, int) or n <= 0 or not isinstance(res, (int, float)) or res <= 0:
        raise ValueError("视野表:size / res 不对")
    if int(d.get("frames", 0)) < FOV_MIN_FRAMES:
        raise ValueError(f"视野表:只学了 {d.get('frames')} 帧,至少要 {FOV_MIN_FRAMES}")
    try:
        bits = unpack_bits(str(d.get("bits", "")), n)
    except ContractError as exc:
        raise ValueError(f"视野表:位图不对({exc})") from None
    mask = np.frombuffer(bits, dtype=np.uint8).astype(bool).reshape(n, n)
    if not mask.any():
        raise ValueError("视野表:一格都看不见")
    return mask, float(res)


def load(env: Any = None) -> tuple[Any, float] | None:
    """按 ``NEXWAR_FOV_FILE``(没设 = :data:`FOV_DEFAULT`)读视野表;没有、不对是 None(按写死的锥)。"""
    raw = ((os.environ if env is None else env).get(FOV_ENV) or "").strip()
    path = Path(raw) if raw else FOV_DEFAULT
    if not path.is_file():
        if raw:
            log.warning("视野表 %s 没有:遮挡限速按写死的视野锥", path)
        return None
    try:
        got = from_wire(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError) as exc:
        log.warning("视野表 %s 读不了(%s):遮挡限速按写死的视野锥", path, exc)
        return None
    log.warning("遮挡限速按视野表 %s(%d 格看得见)", path, int(got[0].sum()))
    return got
