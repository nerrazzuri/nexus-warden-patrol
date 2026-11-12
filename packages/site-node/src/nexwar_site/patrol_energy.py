"""W76 循环巡逻:巡逻电量到全站电量线(值班设置 ``patrol_return_pct``)回来以后怎么补能。

- 有桩:回充的起充线取这条线(回充自己判机器人空着、电量在线下,见 ``charging.ChargeDesk``)。
- 没桩:**上一趟是因为电量到线结束的**(代理在终态详情里写 ``ended: "battery"``)、机器人在线空着、
  电量还在线下,才起换电引导(``battery_swap.SwapDesk``)。只看电量不行:换电引导会叫停在动的机器人,
  低电时有人遥控、或刚加的机器人还没开始巡逻,不能被它打断、也不该叫保安来换。

跟布防值守自己的补能线并用,取高的(:func:`combine_lines`)。
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any

log = logging.getLogger(__name__)

Line = Callable[[str], "float | None"]

_TERMINAL = ("task_done", "task_failed", "task_aborted", "task_preempted")


class PatrolEnergy:
    def __init__(self, db: Any, dispatcher: Any, settings: Any) -> None:
        self.db, self.dispatcher, self.settings = db, dispatcher, settings

    def _line(self) -> float:
        return float(self.settings.patrol_return_pct())

    def charge_line(self, rid: str) -> float | None:
        """回充的起充线(%)。"""
        return self._line()

    def swap_line(self, rid: str) -> float | None:
        """该起换电引导了 → 那条线;不然 ``None``。"""
        c = self.dispatcher.clients.get(rid)
        st = getattr(c, "status", None)
        if st is None or not st.online or st.task is not None:
            return None
        pct = getattr(getattr(c, "telemetry", None), "battery_pct", None)
        line = self._line()
        if not isinstance(pct, (int, float)) or isinstance(pct, bool) or pct > line:
            return None
        return line if self._ended_for_battery(rid) else None

    def _ended_for_battery(self, rid: str) -> bool:
        rows = self.db.query(
            "SELECT data FROM events WHERE robot_id=? AND kind IN "
            f"({','.join('?' * len(_TERMINAL))}) "
            "ORDER BY received_at DESC, rowid DESC LIMIT 1", (rid, *_TERMINAL))
        if not rows:
            return False
        try:
            d = json.loads(rows[0]["data"] or "{}")
        except ValueError:
            return False
        return isinstance(d, dict) and d.get("ended") == "battery"


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
