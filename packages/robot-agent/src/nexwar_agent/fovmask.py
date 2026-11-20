"""雷达视野表(真机 11-20):机身系里哪些格子是这台机器人的雷达**本来看得见**的。

遮挡限速(导航 V1 第 1 节)只把「本来看得见、这一帧却看不见」的格子当阴影。以前「本来看得见」用写死的
视野锥(机头外 ±0.6 m、往外每米加宽 0.9 m),仿真的假感知也用同一个锥,所以仿真里对得上;C40221 真机的
前雷达视野窄得多(机身中心往前 0.65 m 处 ±0.6、1.05 m 处 ±0.7、1.55 m 处 ±1.0),两个锥之间那一条永远
看不见,被当成阴影,空旷的地方也一直压到 0.2 m/s。

视野表从录包学(``tools/fov_learn.py``):空旷的地方走一段,每一格看得见的帧占多少,≥ 门槛的算视野里。
跟外参一样是每台机器人的标定产物,放 ``/etc/nexwar/fov.json``(``NEXWAR_FOV_FILE`` 改路径)。
没有、读不了、格式不对:照旧用写死的锥(不会更松)。

**自己学**(用户 11-20:新机器没有视野表就先关遮挡限速,第一次建图那阵子把视野表做了):第一次建图时
感知还没起(要等建好的图里的外参),所以是图装上以后机器人一动起来,代理拿感知发来的每一帧自己学
(:class:`Learner`),学够了存到代理数据目录(:data:`LEARNED_NAME`)、当场换上、遮挡限速打开。
挡在墙、货架后面的格子那一帧不算数(看不见是被挡住,不是视野外),一直贴墙走也学不窄。
真机上没有视野表的时候遮挡限速关着(``Nav2Nav.occ_need_fov``)—— 学出来的表再窄也只会比关着严。
"""

from __future__ import annotations

import json
import logging
import math
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
#: 自己学的存在代理数据目录里叫这个(``/etc/nexwar/fov.json`` 有的话先用那份)。
LEARNED_NAME = "fov.json"
#: 自己学:机器人挪了这么远、转了这么多才收一帧(站着不动收一堆一样的帧没用)。
AUTO_STEP_M = 0.05
AUTO_STEP_RAD = 0.05
#: 自己学:收够这么多帧出表(走着、转着约 1–2 分钟)。
AUTO_FRAMES = 600
#: 自己学:一格至少有这么多帧没被挡住才定它看不看得见(不够的算看不见)。
AUTO_MIN_EVIDENCE = 60
#: 自己学:出来的表至少这么多格看得见,不然不认、接着学(C40221 实测 1272 格)。
AUTO_MIN_CELLS = 400
#: 挡没挡住按从机身中心往外的方向分这么多份。
_BINS = 180


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


def load(env: Any = None, learned: Path | None = None) -> tuple[Any, float] | None:
    """按 ``NEXWAR_FOV_FILE`` 读视野表;没设:先 :data:`FOV_DEFAULT`,没有再 ``learned``(自己学的)。
    没有、不对是 None(按写死的锥)。"""
    raw = ((os.environ if env is None else env).get(FOV_ENV) or "").strip()
    path = Path(raw) if raw else FOV_DEFAULT
    if not raw and not path.is_file() and learned is not None:
        path = learned
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


def save(path: Path, mask: Any, *, res: float, frames: int, source: str) -> None:
    """写视野表(先写临时文件再换,断电不留半个)。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(json.dumps(to_wire(mask, res=res, frames=frames, source=source),
                              ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


class Learner:
    """边走边学视野表。:meth:`feed` 每来一帧感知(机身系 n × n 的 occ / known,加里程位姿)调一次;
    学够了回 ``(视野表, 格子边长, 帧数)``,别的时候回 None。"""

    def __init__(self) -> None:
        self.n = 0
        self.res = 0.0
        self.frames = 0
        self._last: tuple[float, float, float] | None = None
        self._seen: Any = None
        self._elig: Any = None
        self._bin: Any = None
        self._span: list[Any] = []
        self._r: Any = None

    def _reset(self, n: int, res: float) -> None:
        import numpy as np
        self.n, self.res, self.frames, self._last = n, res, 0, None
        self._seen = np.zeros((n, n), dtype=np.int32)
        self._elig = np.zeros((n, n), dtype=np.int32)
        cc = (np.arange(n) - n / 2 + 0.5) * res
        XX, YY = np.meshgrid(cc, cc, indexing="ij")
        self._r = np.hypot(XX, YY)

        def bins(x: Any, y: Any) -> Any:
            return ((np.arctan2(y, x) + math.pi) / (2 * math.pi) * _BINS).astype(int) % _BINS
        self._bin = bins(XX, YY)
        # 挡住哪些方向按格子里 3 × 3 个点算(近处一格横跨好几份,只按中心算后面会漏一条缝)
        h = res / 2
        self._span = [bins(XX + dx, YY + dy) for dx in (-h, 0.0, h) for dy in (-h, 0.0, h)]

    def shadow(self, occ: Any) -> Any:
        """这一帧被挡住的格子:同一个方向上更近处有挡(挡外扩一格)。挡本身不算被挡住。"""
        import numpy as np
        o = occ.copy()
        o[1:] |= occ[:-1]
        o[:-1] |= occ[1:]
        o[:, 1:] |= o[:, :-1].copy()
        o[:, :-1] |= o[:, 1:].copy()
        near = np.full(_BINS, np.inf)
        for sb in self._span:
            np.minimum.at(near, sb[o], self._r[o])
        return (self._r > near[self._bin] + self.res) & ~occ

    def feed(self, *, occ: Any, known: Any, size: int, res: float,
             pose: tuple[float, float, float]) -> tuple[Any, float, int] | None:
        import numpy as np
        if size != self.n or abs(res - self.res) > 1e-9:
            self._reset(size, res)
        if self._last is not None \
                and math.hypot(pose[0] - self._last[0], pose[1] - self._last[1]) < AUTO_STEP_M \
                and abs(math.remainder(pose[2] - self._last[2], 2 * math.pi)) < AUTO_STEP_RAD:
            return None
        self._last = pose
        o = np.asarray(occ, dtype=bool).reshape(size, size)
        k = np.asarray(known, dtype=bool).reshape(size, size)
        elig = ~self.shadow(o)
        self._elig += elig
        self._seen += k & elig
        self.frames += 1
        if self.frames < AUTO_FRAMES:
            return None
        mask = self.mask()
        if int(mask.sum()) < AUTO_MIN_CELLS:
            log.warning("自己学的视野表只有 %d 格看得见(至少 %d):不认,从头再学", int(mask.sum()),
                        AUTO_MIN_CELLS)
            self._reset(size, res)
            return None
        return mask, self.res, self.frames

    def mask(self) -> Any:
        ok = self._elig >= AUTO_MIN_EVIDENCE
        return ok & (self._seen >= FOV_THRESHOLD * self._elig)
