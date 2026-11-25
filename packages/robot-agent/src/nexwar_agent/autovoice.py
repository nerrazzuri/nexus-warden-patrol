"""特定的时候自动放特定的话术(POC 11-05,用户:接入告警,特定的音频在特定的时候播放)。

机器人自己判,不等站点(断网了照样放):

| 情况 | 话术 | 多久最多一次 |
|---|---|---|
| 被挡住走不过去(``nav_blocked`` 到 ``nav_unblocked`` 或停下) | ``blocked`` | 挡着每 20 秒 |
| 有人进 2 米(人员检测最近的距离) | ``distance`` | 30 秒 |
| 走着的时候看到 3 个人以上 | ``passing`` | 60 秒 |

禁区见人不在这里:站点驱离第 2 级会轮放 ``warn-<语言>``(把 ``restricted`` 拷一份成 ``warn-en``)。

- 只放这台机器人**有的**话术(``/var/lib/nexwar/clips/<名>.wav``;没拷就等于不开)。
- 优先级 :data:`AUTO_PRIORITY` 比手动的(60)、驱离(80)都低:正在放更要紧的就不插,手动的能打断它。
- 一拍最多放一段,按上表从上往下挑(被挡最要紧)。
- **跟人有关的两段(有人进 2 米、看到 3 个人以上)只在站点说「放」的时候放**(真机 11-25,用户选「只在
  布防时喊,App 加静音」):撤防了还一直喊「please keep safe distance」。站点按布防、静音算好,用
  ``auto_voice`` 命令发 ``{"person": true/false}``;起来时默认不放(站点没说就不喊)。被挡那段照旧。
- 每放一段都记日志(哪段、为什么),排查时分得清是谁在喊。
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any

log = logging.getLogger(__name__)

#: 比站点手动(``MANUAL`` 60)、驱离(``EVENT`` 80)都低。
AUTO_PRIORITY = 40
CLIP_MAX_S = 15.0
BLOCKED_EVERY_S = 20.0
NEAR_M = 2.0
NEAR_EVERY_S = 30.0
CROWD_N = 3
CROWD_EVERY_S = 60.0


class AutoVoice:
    def __init__(self, deter: Any, *, monotonic: Callable[[], float] = time.monotonic) -> None:
        self.deter = deter
        self._mono = monotonic
        self._blocked = False
        self._last: dict[str, float] = {}
        #: 跟人有关的话术放不放(站点按布防 / 静音发,真机 11-25);起来时不放。
        self.person = False

    def on_nav_event(self, kind: str, data: dict[str, Any]) -> None:
        if kind == "nav_blocked":
            self._blocked = True
        elif kind == "nav_unblocked":
            self._blocked = False

    def _due(self, clip: str, every_s: float) -> bool:
        last = self._last.get(clip)
        return last is None or self._mono() - last >= every_s

    async def _play(self, clip: str, every_s: float, why: str) -> bool:
        if not self._due(clip, every_s):
            return False
        if await self.deter.auto_sound(clip, priority=AUTO_PRIORITY, max_s=CLIP_MAX_S, why=why):
            self._last[clip] = self._mono()
            log.info("自动话术:放 %s(%s)", clip, why)
            return True
        return False

    async def tick(self, *, moving: bool, persons: int | None, nearest_m: float | None) -> None:
        """每拍调一次:``moving`` = 有任务在跑;``persons``、``nearest_m`` 来自人员检测
        (没有就 None)。"""
        if not moving:
            self._blocked = False
        if self._blocked and await self._play("blocked", BLOCKED_EVERY_S, "nav_blocked"):
            return
        if not self.person:
            return                     # 站点没说放(撤防、静音、老站点):跟人有关的不喊
        if nearest_m is not None and nearest_m <= NEAR_M \
                and await self._play("distance", NEAR_EVERY_S, "person_near"):
            return
        if moving and (persons or 0) >= CROWD_N:
            await self._play("passing", CROWD_EVERY_S, "crowd")
