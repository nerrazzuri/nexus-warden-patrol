"""等充完电、空闲时再换的升级(W44 第四期,设计 §5.3「软件升级」:「现在装」或
「等机器人都在充电时装」)。

换版本(``release_activate``)要机器人空闲(机器人自己查),充电那一趟也是任务,所以不能真在桩上换;
规矩是:**在线新鲜、没有任务、电量 ≥ :data:`MIN_BATTERY`**(充完电、停下来的时候)才发。
发出去机器人收下了就出队;
拒了(比如这时候被派走了)留着下一拍再试。每台一条,后排的盖前面的。

真机 11-20:拒了每一拍(1 秒)就重发一次,一直刷;要切的那一版已经在跑了也照样发。现在:已经在跑 →
出队;拒了 → 记下原因(网页「软件升级」看得见)、:data:`RETRY_MS` 后再试;网页能取消。

每次排队一个不复用的编号(``id``,外审 R7):回执回来只删**发出去的那一条**;等回执的时候管理员又排了
一个,新的那条留着,下一拍照样发。
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

log = logging.getLogger(__name__)

MIN_BATTERY = 80.0
#: 拒了 / 发不出去,多久以后再试(毫秒)。
RETRY_MS = 5 * 60_000


class ReleaseQueue:
    def __init__(self, db: Any, dispatcher: Any, *, now_ms: Callable[[], int],
                 payload: Callable[[str], dict[str, Any]]) -> None:
        self.db = db
        self.dispatcher = dispatcher
        self._now = now_ms
        self._payload = payload
        #: 每台上一次发不出去的原因:同一个原因只记一次(演示站点实测:原来每一拍刷一段堆栈)
        self._last_err: dict[str, str] = {}
        #: 每一条(按编号):上回为什么没换成(机器人拒的原因 / 发不出去)、几点再试。
        #: 按编号记:被拒以后管理员又排一条,新的那条不跟着等
        self._why: dict[int, str] = {}
        self._retry_at: dict[int, int] = {}

    def add(self, robot_id: str, name: str, *, by: str) -> int:
        """排一个;这台原来排着的被盖掉。→ 这一次的编号。"""
        with self.db.tx() as c:
            c.execute("DELETE FROM release_queue WHERE robot_id=?", (robot_id,))
            return c.execute("INSERT INTO release_queue(robot_id, name, by, at_ms) "
                             "VALUES (?,?,?,?)", (robot_id, name, by, self._now())).lastrowid

    def done(self, robot_id: str, intent: int) -> bool:
        """``intent`` 那一次发出去、机器人收下了:只删那一条(后来又排的不动)。"""
        with self.db.tx() as c:
            return c.execute("DELETE FROM release_queue WHERE robot_id=? AND id=?",
                             (robot_id, intent)).rowcount > 0

    def remove(self, robot_id: str) -> bool:
        with self.db.tx() as c:
            return c.execute("DELETE FROM release_queue WHERE robot_id=?",
                             (robot_id,)).rowcount > 0

    def list(self) -> list[dict[str, Any]]:
        """每条带 ``last_reason``(上回没换成的原因,没有是空)、
        ``retry_at_ms``(几点再试,没有是 None)。"""
        rows = [dict(r) for r in self.db.query("SELECT * FROM release_queue ORDER BY robot_id")]
        for r in rows:
            r["last_reason"] = self._why.get(r["id"], "")
            r["retry_at_ms"] = self._retry_at.get(r["id"])
        return rows

    def _current(self, robot_id: str) -> str | None:
        caps = getattr(self.dispatcher.clients.get(robot_id), "capabilities", None)
        got = (getattr(caps, "tasks", None) or {}).get("release_install") or {}
        return got.get("current") if isinstance(got, dict) else None

    def _later(self, intent: int, why: str) -> None:
        self._why[intent] = why[:200]
        self._retry_at[intent] = self._now() + RETRY_MS

    def _ready(self, robot_id: str) -> bool:
        c = self.dispatcher.clients.get(robot_id)
        if not self.dispatcher._fresh(c):
            return False
        if getattr(getattr(c, "status", None), "task", None) is not None:
            return False
        batt = getattr(getattr(c, "telemetry", None), "battery_pct", None)
        return isinstance(batt, (int, float)) and batt >= MIN_BATTERY

    async def tick(self) -> None:
        for row in self.list():
            rid = row["robot_id"]
            if self._current(rid) == row["name"]:
                self.done(rid, row["id"])
                log.info("%s 已经在跑 %s,排队的升级出队", rid, row["name"])
                continue
            if self._now() < self._retry_at.get(row["id"], 0) or not self._ready(rid):
                continue
            try:
                got = await self.dispatcher.map_command(
                    rid, "release_activate", self._payload(row["name"]),
                    issued_by=f"{row['by']}(排队)")
            except Exception as exc:  # noqa: BLE001 - 什么原因都留着下一拍再试,只记一次
                why = f"{type(exc).__name__}: {exc}"
                if self._last_err.get(rid) != why:
                    self._last_err[rid] = why
                    log.warning("%s 排队的升级 %s 没发出去(%s),过一会再试", rid, row["name"],
                                why)
                self._later(row["id"], why)
                continue
            self._last_err.pop(rid, None)
            ack = (got or {}).get("ack", {})
            if ack.get("result") in ("accepted", "duplicate"):
                self.done(rid, row["id"])
                log.info("%s 充完电空闲了,换成 %s", rid, row["name"])
            else:
                why = str(ack.get("reason") or ack.get("result") or "没有回执")
                log.warning("%s 排队的升级 %s 被拒(%s),%d 分钟后再试", rid, row["name"], why,
                            RETRY_MS // 60_000)
                self._later(row["id"], why)
