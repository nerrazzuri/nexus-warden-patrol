"""今天的巡逻(W53):日程的每一轮 + 临时巡逻,按时间排,一行一趟、人话的状态。

App 的值守页、日程页,网页的值守页都用这一份(``GET /api/patrols/today``)。按站点时区算「今天」。

状态:
- ``done`` 走完、``failed`` 没走完(原因在 ``reason``)、``aborted`` 被叫停、``running`` 正在走;
- ``waiting`` 到点了还没起跑(机器人忙、离线……还在窗口里,一会儿可能就跑了);
- ``missed`` 这一轮没跑(窗口过了、跳过);
- ``next`` 下一趟、``later`` 再往后;``blocked`` 还没到点、但到了也不会跑(``reason``:``manual_only``
  排给的那台只许手动派);
- 临时巡逻另有 ``queued`` 排队中、``cancelled`` 取消了、``expired`` 排太久作废了。
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from nexwar_contract.schedule import occurrences_between
from nexwar_site.catalog import active_bundle
from nexwar_site.sitetime import site_tz

# 第 8 轮 W8-03:被更优先的任务接替(日程到点停下一直巡逻)不是故障 —— 单独一种结局,不算「未完成」
_RESULT = {"done": "done", "failed": "failed", "aborted": "aborted", "preempted": "handed_over"}
_TERMINAL = {"task_done": "done", "task_failed": "failed", "task_aborted": "aborted",
             "task_preempted": "handed_over"}
#: 排程账里「这一轮到点了还没起跑」的几种去向(还在窗口里就是 waiting)。
_PENDING = ("busy", "no_robot", "displaced", "supervised", "weather", "skew", "ambiguous")


def _terminal(db: Any, robot: str, task_id: str) -> tuple[str, int, str, int] | None:
    """这一趟的结束事件 → (状态, 时刻, 原因, 跳过了几个点)。W71:巡逻跳过几个点、到了一部分,机器人报
    ``task_done`` 带 ``skipped``,手机、网页显示「完成(跳过 N 点)」。"""
    if not task_id:
        return None
    rows = db.query(
        "SELECT kind, data, received_at FROM events WHERE robot_id=? AND kind IN "
        "('task_done','task_failed','task_aborted','task_preempted') "
        "AND json_extract(data, '$.task_id')=? ORDER BY rowid DESC LIMIT 1", (robot, task_id))
    if not rows:
        return None
    try:
        data = json.loads(rows[0]["data"])
    except ValueError:
        data = {}
    why, skipped = "", 0
    if isinstance(data, dict):
        why = str(data.get("reason") or data.get("error") or data.get("detail") or "")[:200]
        s = data.get("skipped")
        skipped = s if isinstance(s, int) and not isinstance(s, bool) and s > 0 else 0
    if rows[0]["kind"] == "task_preempted":
        why = ""                                      # 不露 preempted 这种代号;谁接替的见 _handover
    return _TERMINAL[rows[0]["kind"]], int(rows[0]["received_at"]), why, skipped


def _loops(db: Any, robot: str, task_id: str) -> tuple[int, int] | None:
    """几圈的巡逻 → ``(共几圈(0 = 一直巡逻), 已经跑完几圈)``;一圈的、不是巡逻 → None。"""
    from nexwar_site.robot_overview import lap_counts
    return lap_counts(db, robot, task_id)


def _handover(db: Any, robot: str, task_id: str, at_ms: int) -> dict[str, Any]:
    """被接替的那一趟:谁接的(日程 / 遥控 / 别的任务)、日程叫什么、之前跑完了几圈。"""
    lo = _loops(db, robot, task_id)
    out: dict[str, Any] = {"by": "task", "name": "", "laps": lo[1] if lo else 0}
    runs = db.query("SELECT entry_id FROM schedule_runs WHERE robot_id=? AND outcome='started' "
                    "AND task_id<>? AND decided_at BETWEEN ? AND ? "
                    "ORDER BY decided_at DESC LIMIT 1",
                    (robot, task_id, at_ms - 120_000, at_ms + 10_000))
    if runs:
        out.update(by="schedule", name=str(runs[0]["entry_id"]))
        return out
    cmds = db.query("SELECT task_id FROM commands WHERE robot_id=? AND task_id<>? "
                    "AND issued_at BETWEEN ? AND ? ORDER BY issued_at DESC LIMIT 1",
                    (robot, task_id, at_ms - 120_000, at_ms + 10_000))
    if cmds and str(cmds[0]["task_id"] or "").startswith("teleop-"):
        out["by"] = "teleop"
    return out


def _loop_fields(db: Any, item: dict[str, Any]) -> None:
    """W76 / 第 8 轮 A8-01:几圈的巡逻带 ``lap``(在跑的第几圈)、一直巡逻带 ``forever``
    且不给预计结束时间;被接替的带 ``handover``。"""
    robot, tid = str(item.get("robot") or ""), str(item.get("task_id") or "")
    lo = _loops(db, robot, tid) if robot and tid else None
    if lo is not None:
        item["forever"] = lo[0] == 0
        if item["state"] == "running":
            item["lap"] = {"n": min(lo[1] + 1, lo[0]) if lo[0] else lo[1] + 1, "of": lo[0]}
            if lo[0] == 0:
                item["end_ms"] = None
    if item["state"] == "handed_over" and robot:
        item["handover"] = _handover(db, robot, tid, int(item.get("end_ms") or 0))


def _stopped_by(db: Any, robot: str, start_ms: int, end_ms: int) -> str:
    """第 4 轮 admin N7:被叫停的那趟是谁叫停的 —— 这一趟里最后一条停车 / 撤销命令的发令人
    (派单的人不一定是叫停的人)。找不到就空串。"""
    rows = db.query(
        "SELECT issued_by FROM commands WHERE robot_id=? AND kind IN ('halt','abort') "
        "AND issued_at BETWEEN ? AND ? ORDER BY issued_at DESC LIMIT 1",
        (robot, start_ms, end_ms + 5_000))
    return str(rows[0]["issued_by"]) if rows else ""


def today_view(db: Any, *, now_ms: int, adhoc: Any = None,
               day: str | None = None,
               loaded: Callable[[str], tuple[Any, Any]] | None = None) -> dict[str, Any]:
    """今天(或 ``day`` = ``YYYY-MM-DD`` 那天,站点时区)的每一趟巡逻。往天的按现在这份日程排轮次,
    跑了的、没跑的照库里的记录写(liang-d5 第 5 轮前:往天的巡逻在网页上查不到)。"""
    act = active_bundle(db)
    tz = act.schedule.tz() if act is not None else site_tz(db)
    now = datetime.fromtimestamp(now_ms / 1000, tz=tz)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if day is not None:
        d = datetime.strptime(day, "%Y-%m-%d")
        start = datetime(d.year, d.month, d.day, tzinfo=tz)
    end = start + timedelta(days=1) - timedelta(milliseconds=1)
    a_ms, b_ms = int(start.timestamp() * 1000), int(end.timestamp() * 1000)
    items: list[dict[str, Any]] = []
    if act is not None:
        for e in act.schedule.entries:
            if act.since(e.id) > b_ms:
                continue
            for occ in occurrences_between(e, start, end):
                occ_ms = int(occ.timestamp() * 1000)
                if occ_ms < act.since(e.id):
                    continue                            # 这条日程加进来之前的轮次:那时还没有它
                m = act.missions.get(e.mission)
                want = (m.map_id, m.map_version) if m is not None and m.map_version else None
                items.append(_schedule_item(db, e, occ_ms, now_ms, want=want, loaded=loaded,
                                            tz=tz))
    if adhoc is not None:
        for r in adhoc.between(a_ms, b_ms):
            items.append(_adhoc_item(db, r, now_ms))
    # 第 8 轮 W8-11:路线、排程起了显示名(能写中文)的带上;没起是空串,照旧显示编号
    titles = {r["route_id"]: r["title"] for r in db.query("SELECT route_id, title FROM routes")}
    stitles = {r["entry_id"]: r["title"] for r in db.query(
        "SELECT entry_id, title FROM route_schedules")}
    for it in items:
        it["title"] = titles.get(str(it.get("label") or ""), "")
        if it.get("schedule_id"):
            it["schedule_title"] = stitles.get(str(it["schedule_id"]), "")
        _loop_fields(db, it)
        if it["state"] == "aborted" and it.get("robot") and it.get("end_ms"):
            it["stopped_by"] = _stopped_by(db, it["robot"], int(it["at_ms"]), int(it["end_ms"]))
    items.sort(key=lambda x: (x["at_ms"], x["label"]))
    first = next((it for it in items if it["state"] == "later"), None)
    if first is not None:
        first["state"] = "next"                         # 还没到点的第一趟
    off = now.utcoffset()
    return {"date": start.strftime("%Y-%m-%d"), "timezone": str(tz),
            # 手机、网页按站点的钟显示时刻(外审 W53-1 #12)
            "utc_offset_min": int(off.total_seconds() // 60) if off is not None else 0,
            "items": items}


def _map_gap(want: tuple[str, str] | None, got: tuple[Any, Any] | None) -> dict[str, str] | None:
    """路线画在哪一版、机器人加载的哪一版;对得上、或者有一头不知道,回 None(不猜)。"""
    if want is None or got is None or got[0] is None or got[1] is None:
        return None
    if (str(got[0]), str(got[1])) == (str(want[0]), str(want[1])):
        return None
    if str(got[0]) != str(want[0]):
        return {"route": f"{want[0]}:{want[1]}", "robot": f"{got[0]}:{got[1]}"}
    return {"route": str(want[1]), "robot": str(got[1])}


def _late_runnable(e: Any, occ_ms: int, now_ms: int, tz: Any) -> bool:
    """``run_late`` 的这一轮窗口过了,执行器此刻还会不会补跑它(是不晚于现在的最新一轮)。"""
    if getattr(e, "on_missed", "") != "run_late" or tz is None:
        return False
    from nexwar_contract.schedule import DecisionKind, decide
    try:
        d = decide(e, now=datetime.fromtimestamp(now_ms / 1000, tz=tz), last_started_ms=None)
    except Exception:  # noqa: BLE001 - 算不出:照窗口算
        return False
    return d.kind == DecisionKind.LATE and d.scheduled_ms == occ_ms


def _schedule_item(db: Any, e: Any, occ_ms: int, now_ms: int, *,
                   want: tuple[str, str] | None = None,
                   loaded: Callable[[str], tuple[Any, Any]] | None = None,
                   tz: Any = None) -> dict[str, Any]:
    rows = [dict(r) for r in db.query(
        "SELECT outcome, robot_id, task_id, result, note, decided_at FROM schedule_runs "
        "WHERE entry_id=? AND scheduled_ms=? ORDER BY id", (e.id, occ_ms))]
    started = next((r for r in rows if r["outcome"] == "started"), None)
    item: dict[str, Any] = {"at_ms": occ_ms, "kind": "schedule", "label": e.mission,
                            "robot": e.robot, "by": "", "state": "later", "reason": "",
                            "end_ms": None, "schedule_id": e.id, "adhoc_id": "", "task_id": "",
                            "skipped": 0}
    if started is not None:
        rid = started["robot_id"] or e.robot
        item.update(robot=rid, task_id=started["task_id"] or "")
        fin = _terminal(db, rid, item["task_id"])
        if fin is not None:
            item.update(state=fin[0], end_ms=fin[1], reason=fin[2], skipped=fin[3])
        elif started["result"] in _RESULT:
            item["state"] = _RESULT[started["result"]]
        else:
            item["state"] = "running"
        return item
    if occ_ms > now_ms:
        # 易用性第 6 轮 W6-02:排给的那台只许手动派 —— 到点也不会跑,先说清楚(不写「下一次」)
        if e.robot and db.query("SELECT 1 FROM robot_service WHERE robot_id=?", (e.robot,)):
            item.update(state="blocked", reason="manual_only")
        # 易用性第 7 轮:排给的那台加载的图跟路线画的那一版对不上,到点也不会跑 —— 写上两边的版本
        gap = _map_gap(want, loaded(e.robot)) if e.robot and loaded is not None else None
        if gap is not None:
            item["map"] = gap
            if item["state"] != "blocked":
                item.update(state="blocked", reason="map_mismatch")
        return item
    settled = next((r for r in rows if r["outcome"] in ("skip", "alarm", "dispatch_failed",
                                                           "lost")), None)
    last = rows[-1] if rows else None
    window_over = now_ms > occ_ms + int(e.window_min) * 60_000
    if window_over and settled is None and _late_runnable(e, occ_ms, now_ms, tz):
        window_over = False                              # minor #37:run_late 还会补跑这一轮
    if settled is not None or window_over:
        item["state"] = "missed"
        item["reason"] = ((settled or last or {}).get("note") or "到点没有能派的机器人")[:200]
    else:
        item["state"] = "waiting"
        item["reason"] = ((last or {}).get("note") or "")[:200] if last and \
            last["outcome"] in _PENDING else ""
    return item


def _adhoc_item(db: Any, r: dict[str, Any], now_ms: int) -> dict[str, Any]:
    at = r["started_ms"] or r["not_before_ms"]
    item: dict[str, Any] = {"at_ms": at, "kind": "adhoc", "label": r["label"], "robot": r["robot"],
                            "by": r["by"], "state": r["state"], "reason": r["note"] or "",
                            "end_ms": None, "schedule_id": "", "adhoc_id": r["id"],
                            "task_id": r["task_id"] or "", "skipped": 0}
    if r["state"] == "queued":
        item["end_ms"] = r["not_before_ms"] + int(r["estimate_s"]) * 1000
    elif r["state"] == "started":
        fin = _terminal(db, r["robot"], r["task_id"])
        if fin is not None:
            item.update(state=fin[0], end_ms=fin[1], reason=fin[2], skipped=fin[3])
        else:
            item.update(state="running",
                        end_ms=(r["started_ms"] or now_ms) + int(r["estimate_s"]) * 1000,
                        reason="")
    return item
