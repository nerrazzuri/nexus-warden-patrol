"""机器人概览(W44 第二期,设计 §5.0「机器人」、§5.1「机器人」):管理员看的卡片要的数,一次给全。

每台:名字、在线(在线且新鲜)、电量、今天巡了几趟(站点时区 0 点起派出去、没被拒的巡逻)、
毛病(这台没解决的「机器人需要帮忙 / 掉线」告警 + 设备不在线)、近 30 天的毛病、代理版本和兼容结论、
证书到期。
技术类告警(给管理员那一类)不算毛病,在「现场概况」里说。电池健康机器人还不报,不给。
"""

from __future__ import annotations

from datetime import tzinfo
from typing import Any

from nexwar_contract.binding import wifi_view
from nexwar_site.alert_audience import audience
from nexwar_site.dispatcher import battery_pct
from nexwar_site.sitetime import local_day_start

PROBLEM_AUDIENCES = ("help", "offline")
RECENT_DAYS = 30
RECENT_MAX = 50
WEEK_MS = 7 * 86_400_000


def overview(dispatcher: Any, db: Any, *, now_ms: int, tz: tzinfo) -> list[dict[str, Any]]:
    from nexwar_site.compat import _robot
    reg = dispatcher.registry
    names = reg.names()
    day0 = local_day_start(now_ms, tz)
    since = now_ms - RECENT_DAYS * 86_400_000
    out = []
    for rec in reg.list():
        rid = rec.robot_id
        c = dispatcher.clients.get(rid)
        fresh = bool(dispatcher._fresh(c))
        [n] = db.query("SELECT COUNT(*) AS n FROM commands WHERE robot_id=? AND kind='patrol' "
                       "AND issued_at>=? AND (ack_result IS NULL OR ack_result NOT IN "
                       "('rejected', 'expired', 'timeout'))", (rid, day0))
        week = _week(db, rid, now_ms)
        rows = db.query("SELECT key, kind, level, title, first_ms, resolved_ms, resolved_by "
                        "FROM alerts WHERE robot=? AND "
                        "(resolved_ms IS NULL OR first_ms>=?) ORDER BY first_ms DESC LIMIT 1000",
                        (rid, since))
        mine = [r for r in rows if audience(r["kind"]) in PROBLEM_AUDIENCES]
        problems: list[dict[str, Any]] = [{"key": r["key"], "kind": r["kind"],
                                           "first_ms": r["first_ms"]}
                                          for r in mine if r["resolved_ms"] is None]
        dv = dispatcher.devices_view(rid)
        if dv and not dv.get("stale"):
            problems += [{"device": x.get("id"), "state": x.get("state")}
                         for x in dv.get("items", []) if x.get("state") != "online"]
        caps = getattr(c, "capabilities", None) if c is not None else None
        n2 = (getattr(caps, "tasks", None) or {}).get("nav2") if fresh else None
        if isinstance(n2, dict) and n2.get("ready") is False:
            # W71:Nav2 没起来(机器人退回自己的规划,照样能走,但现场要知道)
            problems.append({"nav2": str(n2.get("reason") or "")[:200]})
        recent = [{"key": r["key"], "kind": r["kind"], "level": r["level"],
                   "title": r["title"] or "", "first_ms": r["first_ms"],
                   "resolved_ms": r["resolved_ms"], "resolved_by": r["resolved_by"] or ""}
                  for r in mine if r["first_ms"] >= since][:RECENT_MAX]
        # 网页易用性 P1-23:连上过没有(刚登记、等激活的不是「离线故障」)。站点重启后还没新状态的,
        # 看它以前报过事件、回过执没有
        live_at = getattr(c, "status_live_at", None) if c is not None else None
        seen = fresh or live_at is not None \
            or bool(db.query("SELECT 1 FROM events WHERE robot_id=? LIMIT 1", (rid,))) \
            or bool(db.query("SELECT 1 FROM commands WHERE robot_id=? AND ack_result IS NOT NULL "
                             "AND ack_result NOT IN ('expired', 'timeout') LIMIT 1", (rid,)))
        out.append({"robot_id": rid, "name": names.get(rid, ""), "revoked": rec.revoked,
                    "ever_seen": seen,
                    "expires_at": rec.expires_at, "online": fresh,
                    "battery_pct": battery_pct(c, fresh=fresh),
                    "manual_only": reg.manual_only(rid) is not None,
                    "patrols_today": n["n"], "problems": problems, "recent_problems": recent,
                    "agent": getattr(caps, "agent", None),
                    "compat": _robot(rid, c)["verdict"] if c is not None else "unknown",
                    # W42:连的哪个 WiFi、走哪条线、有没有等确认的 WiFi 改动(老机器人是 None)
                    "wifi": wifi_view(getattr(getattr(c, "telemetry", None), "net", None)),
                    # W72(用户 11-03):详情面板要的 —— 近 7 天、上次联系、存储、地图、设备、登记
                    **week,
                    "last_seen_ms": getattr(c, "status_live_at", None) if c is not None else None,
                    "storage": _storage(c), "map": _map(dispatcher, c),
                    "devices": [{"id": x.get("id"), "state": x.get("state")}
                                for x in (dv or {}).get("items", [])] if dv and not dv.get("stale")
                    else [],
                    "enrolled_at": reg.enrolled_at(rid), "held": _held(dispatcher, rid),
                    # POC:能换哪几种姿势(狗报的;不新鲜不给)、正在跑的任务(有就不让换姿势)
                    "postures": list(((getattr(caps, "tasks", None) or {}).get("posture") or {})
                                     .get("modes", [])) if fresh else [],
                    "task": _task(c),
                    "manual_note": (reg.manual_only(rid) or {}).get("note", ""),
                    **_return_targets(db, rid, caps)})
    return out


def _return_targets(db: Any, rid: str, caps: Any) -> dict[str, Any]:
    """网页易用性第 2 轮 N2:回原点、回待命点能不能派(站点派的时候同样这么查,见 standby.py)。
    ``home_set``:狗当前地图那一版上有没有原点(没报地图 = ``None``,不知道);``standby_set``:有没有默认待命点。"""
    patrol = ((getattr(caps, "tasks", None) or {}).get("patrol") or {}) if caps is not None else {}
    mid, ver = patrol.get("map_id"), patrol.get("map_version")
    home = None if mid is None else bool(db.query(
        "SELECT 1 FROM homes WHERE robot_id=? AND map_id=? AND map_version=?", (rid, mid, ver)))
    standby = bool(db.query("SELECT 1 FROM standby_points WHERE robot_id=? AND is_default=1",
                            (rid,)))
    return {"home_set": home, "standby_set": standby}


def _week(db: Any, rid: str, now_ms: int) -> dict[str, Any]:
    """近 7 天巡了几趟(派出去、狗接了的)、中止几次、最近一趟什么时候派的。"""
    since = now_ms - WEEK_MS
    [p] = db.query("SELECT COUNT(*) AS n, MAX(issued_at) AS last FROM commands "
                   "WHERE robot_id=? AND kind='patrol' AND issued_at>=? AND (ack_result IS NULL "
                   "OR ack_result NOT IN ('rejected', 'expired', 'timeout'))", (rid, since))
    [a] = db.query("SELECT COUNT(*) AS n FROM alerts WHERE robot=? AND kind='run_abort' "
                   "AND first_ms>=?", (rid, since))
    return {"patrols_7d": p["n"], "aborts_7d": a["n"], "last_patrol_ms": p["last"]}


def _task(c: Any) -> str | None:
    """狗状态里正在跑的任务号(没有 / 没状态 = None)。"""
    task = getattr(getattr(c, "status", None), "task", None)
    return getattr(task, "task_id", None)


def _held(dispatcher: Any, rid: str) -> dict[str, Any] | None:
    """被叫停了、还没人点恢复:谁、什么时候(详情里给「恢复」按钮)。"""
    fn = getattr(dispatcher, "held", None)
    h = fn(rid) if fn is not None else None
    return {"by": h["by"], "at_ms": h["at_ms"]} if h else None


def _storage(c: Any) -> dict[str, Any] | None:
    st = getattr(getattr(c, "telemetry", None), "storage", None)
    if st is None:
        return None
    return {"used_ratio": st.disk_used_ratio, "backlog_files": st.backlog_files,
            "oldest_backlog_s": st.oldest_backlog_s}


def _map(dispatcher: Any, c: Any) -> dict[str, Any] | None:
    """狗正在用哪张图、跟站点登记的那一版对不对得上(``match`` None = 查不了)。"""
    view = getattr(dispatcher, "running_view", None)
    rv = view(c) if view is not None and c is not None else None
    if not rv or rv.get("legacy") or not rv.get("map_id"):
        return None
    return {"id": rv["map_id"], "version": rv.get("map_version"),
            "match": (rv.get("map") or {}).get("match")}
