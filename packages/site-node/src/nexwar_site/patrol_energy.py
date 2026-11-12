"""W76 循环巡逻:巡逻因为电量到线结束、回来以后怎么补能。

- 平时:回充的起充线 = 全站巡逻电量线(值班设置 ``patrol_return_pct``;回充自己判机器人空着、电量
  在线下,见 ``charging.ChargeDesk``)。
- **最近一趟巡逻是因为电量结束的**(代理在终态详情里写 ``ended: "battery"``)、
  :data:`RECENT_MS` 以内、
  机器人在线空着、电量还没到 :data:`~nexwar_site.energy.SWAP_OK_PCT`(换电引导判「换好」那一条)→
  要补能:有桩按这条线起回充,没桩起换电引导(``battery_swap.SwapDesk``)。

外审 W76-1 之后:

- 不跟全站电量线比(#3):机器人按动态返航线(中止线 + 回原点耗电 × 1.5)回来,回来时电量可能比全站线
  高,照样要补。
- 只看巡逻那一趟(#4):之后回待命点、去充电那几趟的 ``task_done`` 不盖掉它。
- 换到一半站点重启(#5):两块合起来没到换好线,照样接上。
- 换好、充好(≥ 换好线)就销账(W76-2 #3,落库):之后再掉电按平时的线,不再为这一趟起。销账是
  每拍看电量(:meth:`PatrolEnergy.tick`,W76-3 #2),两块分开报的要两块都装着、都到线(W76-3 #1)。
- 只看电量不行:换电引导会叫停在动的机器人,低电时有人遥控不能被它打断,所以要「空着」。

跟布防值守自己的补能线并用,取高的(:func:`combine_lines`)。
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any

from nexwar_site.energy import SWAP_OK_PCT

log = logging.getLogger(__name__)

Line = Callable[[str], "float | None"]

_TERMINAL = ("task_done", "task_failed", "task_aborted", "task_preempted")
#: 巡逻因电量结束之后多久以内还管它补能(之后机器人多半已经被人处理过、或另有安排)。
RECENT_MS = 2 * 3_600_000
#: 站点设置里记「哪一趟因电量结束的巡逻已经补好了」:``{robot_id: task_id}``。
DONE_KEY = "patrol_energy_done"


class PatrolEnergy:
    def __init__(self, db: Any, dispatcher: Any, settings: Any, *,
                 now_ms: Callable[[], int]) -> None:
        self.db, self.dispatcher, self.settings = db, dispatcher, settings
        self._now = now_ms

    def charge_line(self, rid: str) -> float | None:
        """回充的起充线(%)。"""
        return SWAP_OK_PCT if self._wants(rid) else float(self.settings.patrol_return_pct())

    def swap_line(self, rid: str) -> float | None:
        """该起换电引导了 → 那条线;不然 ``None``。"""
        return SWAP_OK_PCT if self._wants(rid) else None

    def tick(self) -> None:
        """每拍看一遍:因电量结束的那一趟,电补好了就销账(外审 W76-3 #2:不靠回充、换电来问 ——
        回充周期里不问,充到线、出桩又略低于线,会一直进出桩)。"""
        for rid in list(self.dispatcher.clients):
            try:
                self._settle(rid)
            except Exception:
                log.exception("%s 巡逻补能销账没办成", rid)

    def _settle(self, rid: str) -> None:
        c = self.dispatcher.clients.get(rid)
        st = getattr(c, "status", None)
        if st is None or not st.online or not _full(c):
            return
        task_id = self._ended_for_battery(rid)
        done = self._done()
        if task_id is not None and done.get(rid) != task_id:
            self.settings.put(DONE_KEY, {**done, rid: task_id})   # 落库:站点重启也记得

    def _done(self) -> dict[str, Any]:
        done = self.settings.get(DONE_KEY, {})
        return done if isinstance(done, dict) else {}

    def _wants(self, rid: str) -> bool:
        c = self.dispatcher.clients.get(rid)
        st = getattr(c, "status", None)
        if st is None or not st.online or st.task is not None or _full(c):
            return False
        pct = getattr(getattr(c, "telemetry", None), "battery_pct", None)
        if not isinstance(pct, (int, float)) or isinstance(pct, bool):
            return False
        task_id = self._ended_for_battery(rid)
        return task_id is not None and self._done().get(rid) != task_id

    def _ended_for_battery(self, rid: str) -> str | None:
        """最近一趟巡逻是因为电量结束的、而且在 :data:`RECENT_MS` 以内 → 它的任务号;
        不然 ``None``。"""
        marks = ",".join("?" * len(_TERMINAL))
        rows = self.db.query(
            "SELECT e.data, e.received_at, c.task_id FROM events e JOIN commands c "
            "ON c.robot_id = e.robot_id AND c.task_id = json_extract(e.data, '$.task_id') "
            f"AND c.kind = 'patrol' WHERE e.robot_id=? AND e.kind IN ({marks}) "
            "ORDER BY e.received_at DESC, e.rowid DESC LIMIT 1", (rid, *_TERMINAL))
        if not rows or self._now() - int(rows[0]["received_at"] or 0) > RECENT_MS:
            return None
        try:
            d = json.loads(rows[0]["data"] or "{}")
        except ValueError:
            return None
        return rows[0]["task_id"] if isinstance(d, dict) and d.get("ended") == "battery" else None


def _full(c: Any) -> bool:
    """电补好了没有。两块分开报的:两块都装着、都到换好线(外审 W76-3 #1:拔着一块时总电量按在位的
    那块算,会看着像补好了);不分开报的:总电量到线。"""
    t = getattr(c, "telemetry", None)
    packs = getattr(t, "battery_packs", None)
    if packs:
        return all(isinstance(p, (int, float)) and p >= SWAP_OK_PCT for p in packs)
    pct = getattr(t, "battery_pct", None)
    return isinstance(pct, (int, float)) and not isinstance(pct, bool) and pct >= SWAP_OK_PCT


def combine_lines(*lines: Line) -> Line:
    """几条补能线并用:都没要 → ``None``;要了的取高的。一条出错不耽误别的。"""
    def got(rid: str) -> float | None:
        out: float | None = None
        for f in lines:
            try:
                v = f(rid)
            except Exception:
                log.exception("%s 补能线读不出", rid)
                continue
            if v is not None and (out is None or v > out):
                out = float(v)
        return out
    return got
