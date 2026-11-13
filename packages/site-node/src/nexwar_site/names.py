"""给人看的路线名、排程名(第 9 轮 W9-01):起了显示名(能写中文)就用它,没起用编号。

报警标题、派单提醒、被接替说明、出错原因里都走这里,不直接写 ``route-1``、``route-1-1``。编号只在
技术信息里给。查不到(库里没有这条、老库没有 ``title`` 列)也回编号,不抛。
"""

from __future__ import annotations

from typing import Any


def _title(db: Any, sql: str, key: str) -> str:
    try:
        rows = db.query(sql, (key,))
    except Exception:  # noqa: BLE001 - 老库没这一列:照旧写编号
        return ""
    return str(rows[0]["title"] or "").strip() if rows else ""


def route_name(db: Any, route_id: Any) -> str:
    rid = str(route_id or "")
    if not rid or db is None:
        return rid
    return _title(db, "SELECT title FROM routes WHERE route_id=?", rid) or rid


def schedule_name(db: Any, entry_id: Any) -> str:
    eid = str(entry_id or "")
    if not eid or db is None:
        return eid
    return _title(db, "SELECT title FROM route_schedules WHERE entry_id=?", eid) or eid
