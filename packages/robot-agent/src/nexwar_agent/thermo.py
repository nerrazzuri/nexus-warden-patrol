"""1.1-6 热像测温:找起火、过热(设计 ``docs/1.1-6-热像测温-设计.md``,决定 72)。

热像机(上装 V2 的 HIKMICRO)自己会算温度:在它的网页上设一条**全画面的测温规则**,
它就一直报这条规则里的最高温度。这里每 :data:`EVERY_S` 秒用海康的 ISAPI 问一次
(HTTP Digest,账号口令跟 RTSP 地址里的同一套),读回来的 JSON 或 XML 里所有叫
``maxTemperature`` 的数取最大的。**接口路径、字段名没拿实物核过**:路径可配
(``cameras.json`` 热像那一路的 ``thermometry.path``),字段按名字找,不认死结构。

判:

- 连着 :data:`CONFIRM_N` 次 ≥ 起火线(缺省 :data:`FIRE_C` °C)→ ``thermal_hot``
  ``level=fire``(站点出 P1);
- 连着 :data:`CONFIRM_N` 次 ≥ 高温线(缺省 :data:`HOT_C` °C)→ ``thermal_hot`` ``level=hot``(站点 P2);
  已经报过高温、又到了起火线 → 再报一次 ``fire``(升级);
- 报过以后连着 :data:`CLEAR_N` 次低于高温线 :data:`HYSTERESIS_C` °C 以上 → ``thermal_normal``;
- 连着 :data:`FAIL_N` 次问不到 → ``thermometry_failed``(一次);问到了 → ``thermometry_ok``。

人、车头、太阳晒的铁皮也会热:高温线缺省 70 °C(人体表面 30 多度、晒过的车顶 60 多度),起火线 150 °C。
现场要按实物标(配置里改)。
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import urllib.error
import urllib.request
from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import unquote, urlsplit

log = logging.getLogger(__name__)

EVERY_S = 5.0
HOT_C = 70.0
FIRE_C = 150.0
HYSTERESIS_C = 5.0
CONFIRM_N = 2
CLEAR_N = 3
FAIL_N = 6
TIMEOUT_S = 4.0
#: HIKMICRO / 海康热像:第 2 路(热像通道)第 1 条测温规则的温度。实物到了核对。
DEFAULT_PATH = "/ISAPI/Thermal/channels/2/thermometry/1/rulesTemperatureInfo?format=json"
_MAX_KEY = re.compile(r"max_?temp(erature)?", re.I)


class ThermoError(RuntimeError):
    pass


def max_temperature(body: bytes) -> float:
    """ISAPI 回的 JSON 或 XML → 里面所有 ``maxTemperature`` 的最大值。
    一个都没有抛 :class:`ThermoError`。"""
    found: list[float] = []
    text = body.decode("utf-8", "replace").strip()
    if text.startswith("{") or text.startswith("["):
        def walk(v: Any) -> None:
            if isinstance(v, dict):
                for k, x in v.items():
                    if _MAX_KEY.fullmatch(str(k)) and isinstance(x, (int, float)) \
                            and not isinstance(x, bool):
                        found.append(float(x))
                    else:
                        walk(x)
            elif isinstance(v, list):
                for x in v:
                    walk(x)
        try:
            walk(json.loads(text))
        except ValueError as exc:
            raise ThermoError("热像回的不是 JSON") from exc
    else:
        for m in re.finditer(r"<(?:\w+:)?(max_?temp(?:erature)?)>\s*(-?[0-9.]+)\s*</", text, re.I):
            try:
                found.append(float(m.group(2)))
            except ValueError:
                continue
    if not found:
        raise ThermoError("热像回的里面没有最高温度(测温规则没设?)")
    return max(found)


def isapi_reader(rtsp_url: str, *, path: str = DEFAULT_PATH, port: int = 80,
                 scheme: str = "http") -> Callable[[], Awaitable[float]]:
    """按热像的 RTSP 地址(里面有账号口令)造一个「问一次最高温度」的协程函数。口令只在内存里。"""
    u = urlsplit(rtsp_url)
    if not u.hostname:
        raise ThermoError("热像地址里没有主机")
    user, pw = unquote(u.username or ""), unquote(u.password or "")
    url = f"{scheme}://{u.hostname}:{port}{path}"
    mgr = urllib.request.HTTPPasswordMgrWithDefaultRealm()
    mgr.add_password(None, f"{scheme}://{u.hostname}:{port}/", user, pw)
    opener = urllib.request.build_opener(urllib.request.HTTPDigestAuthHandler(mgr),
                                         urllib.request.HTTPBasicAuthHandler(mgr))

    def once() -> float:
        try:
            with opener.open(url, timeout=TIMEOUT_S) as r:
                return max_temperature(r.read(256 * 1024))
        except urllib.error.HTTPError as exc:
            raise ThermoError(f"热像不给温度(HTTP {exc.code})") from exc
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            raise ThermoError(f"连不上热像:{getattr(exc, 'reason', exc)}") from exc

    async def read() -> float:
        return await asyncio.to_thread(once)
    return read


class ThermoWatch:
    def __init__(self, read: Callable[[], Awaitable[float]], *,
                 emit: Callable[[str, dict[str, Any]], Any] = lambda k, d: None,
                 mono: Callable[[], float] = time.monotonic, hot_c: float = HOT_C,
                 fire_c: float = FIRE_C, every_s: float = EVERY_S) -> None:
        if not 0 < hot_c < fire_c:
            raise ValueError("高温线要大于 0、小于起火线")
        self._read = read
        self.emit = emit
        self._mono = mono
        self.hot_c, self.fire_c, self.every_s = float(hot_c), float(fire_c), float(every_s)
        self._next = 0.0
        #: 报到站点的级别:``normal`` / ``hot`` / ``fire``。
        self.level = "normal"
        self._up: dict[str, int] = {"hot": 0, "fire": 0}
        self._down = 0
        self._fails = 0
        self.failed = False
        self.last_c: float | None = None
        self.peak_c: float | None = None
        self.error = ""

    def due(self) -> bool:
        return self._mono() >= self._next

    async def step(self) -> None:
        if not self.due():
            return
        self._next = self._mono() + self.every_s
        try:
            c = await self._read()
        except Exception as exc:                     # noqa: BLE001 - 问不到:数着,够了报一次
            # 外审 1.1 #15:中间断过就不算「连着」:升级、回落都从头数
            self._up = {"hot": 0, "fire": 0}
            self._down = 0
            self._fails += 1
            self.error = str(exc)[:200]
            if self._fails >= FAIL_N and not self.failed:
                self.failed = True
                self.emit("thermometry_failed", {"reason": self.error, "times": self._fails})
            return
        self._fails = 0
        self.error = ""
        if self.failed:
            self.failed = False
            self.emit("thermometry_ok", {"max_c": round(c, 1)})
        self.last_c = c
        self._judge(c)

    def _judge(self, c: float) -> None:
        rank = {"normal": 0, "hot": 1, "fire": 2}
        now = "fire" if c >= self.fire_c else "hot" if c >= self.hot_c else "normal"
        for lv in ("hot", "fire"):
            self._up[lv] = self._up[lv] + 1 if rank[now] >= rank[lv] else 0
        if now != "normal":
            self.peak_c = c if self.peak_c is None else max(self.peak_c, c)
        want = "fire" if self._up["fire"] >= CONFIRM_N else "hot" if self._up["hot"] >= CONFIRM_N \
            else None
        if want is not None and rank[want] > rank[self.level]:
            self.level = want
            self._down = 0
            self.emit("thermal_hot", {"level": want, "max_c": round(c, 1),
                                      "hot_c": self.hot_c, "fire_c": self.fire_c})
            return
        if self.level != "normal":
            self._down = self._down + 1 if c < self.hot_c - HYSTERESIS_C else 0
            if self._down >= CLEAR_N:
                self.emit("thermal_normal", {"max_c": round(c, 1),
                                             "peak_c": round(self.peak_c or c, 1),
                                             "was": self.level})
                self.level = "normal"
                self.peak_c = None
                self._down = 0
