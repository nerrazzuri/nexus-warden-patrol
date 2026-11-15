"""派去看一眼(redesign 第 4 期)的「看完后动作」(用户 11-15):到了点之后站点自动派下一步 ——
``standby`` 回待命点、``home`` 回原点;``stay`` / 不给 = 停在那里等人再派(老行为)。

只记在内存里(站点重启就忘:那一趟的后续不再派,机器人停在那里 —— 跟老行为一样,不会乱走)。
到没到点看 ``events`` 表里那一趟的 ``task_done``(跟自动回充同一个判法);失败 / 中止 / 被抢占就不派。
"""
from __future__ import annotations

import json
import logging
from typing import Any

log = logging.getLogger(__name__)

THENS = ("stay", "standby", "home")
#: 派出去这么久还没到就不等了(毫秒)。
EXPIRE_MS = 2 * 3_600_000


class LookDesk:
    def __init__(self, db: Any, standby: Any, *, now_ms) -> None:
        self.db = db
        self.standby = standby
        self._now = now_ms
        #: task_id -> {"robot", "then", "by", "at_ms"}
        self.pending: dict[str, dict[str, Any]] = {}

    def register(self, robot_id: str, task_id: str, then: str, *, by: str) -> None:
        if then not in ("standby", "home") or not task_id:
            return
        self.pending[task_id] = {"robot": robot_id, "then": then, "by": by, "at_ms": self._now()}

    def _terminal(self, rid: str, task_id: str) -> str | None:
        rows = self.db.query(
            "SELECT kind, data FROM events WHERE robot_id=? AND kind IN "
            "('task_done','task_failed','task_aborted','task_preempted') "
            "AND json_extract(data, '$.task_id')=? ORDER BY rowid DESC LIMIT 1", (rid, task_id))
        return rows[0]["kind"] if rows else None

    async def tick(self) -> None:
        if self.standby is None:
            self.pending.clear()
            return
        now = self._now()
        for task_id, p in list(self.pending.items()):
            rid = p["robot"]
            if now - p["at_ms"] > EXPIRE_MS:
                self.pending.pop(task_id, None)
                continue
            kind = self._terminal(rid, task_id)
            if kind is None:
                continue
            self.pending.pop(task_id, None)
            if kind != "task_done":
                log.info("%s 看一眼那一趟 %s,不派后续", rid, kind)
                continue
            try:
                if p["then"] == "home":
                    r = await self.standby.return_home(rid, issued_by=p["by"])
                else:
                    r = await self.standby.return_to(rid, issued_by=p["by"])
                log.info("%s 看完了,派%s:%s", rid, "回原点" if p["then"] == "home" else "回待命点",
                         json.dumps(r, ensure_ascii=False)[:200])
            except Exception:
                log.exception("%s 看完了,派后续没成", rid)
