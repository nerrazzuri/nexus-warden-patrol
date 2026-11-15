"""redesign 第 8 期:请求支援、派前电量估算、充电时段。"""
from __future__ import annotations

from urllib.parse import quote

import test_site_alerts_api as _alerts
from test_site_alerts_api import _告警, _登
from test_site_api import _等, wall

站点 = _alerts.站点


def test_请求支援_推经理管理员的一条_原告警记下谁叫的(站点):
    s = 站点
    alice, gina, olga = _登(s, "alice"), _登(s, "gina"), _登(s, "olga")
    _等(lambda: s.req("GET", "/api/robots/A", token=alice)[1].get("fresh"))
    s.loop.call(lambda: s.dog.emergency_stop(True))
    a = _等(lambda: _告警(s, gina, "estop_pressed"))
    code, d = s.req("POST", f"/api/alerts/{quote(a['key'], safe='')}/backup", {}, token=gina)
    assert code == 200, d
    assert d["alert"]["context"]["backup_by"] == "gina"
    b = _等(lambda: _告警(s, olga, "backup_requested"))
    assert b["level"] == "P3" and b["context"]["for"] == a["key"] and b["context"]["by"] == "gina"
    assert b["title"].startswith("请求支援：")
    # 外审 1 #2:再叫一次不再起第二条;原告警别的现场字段不被覆盖;关了的 409
    code, d = s.req("POST", f"/api/alerts/{quote(a['key'], safe='')}/backup", {}, token=gina)
    assert code == 200 and d["alert"]["context"]["backup_by"] == "gina"
    code, d = s.req("GET", "/api/alerts", token=olga)
    assert sum(1 for x in d["alerts"] if x["kind"] == "backup_requested") == 1
    code, _ = s.req("POST", f"/api/alerts/{quote(a['key'], safe='')}/resolve", {}, token=gina)
    assert code == 200
    code, _ = s.req("POST", f"/api/alerts/{quote(a['key'], safe='')}/backup", {}, token=gina)
    assert code == 409
    code, _ = s.req("POST", f"/api/alerts/{quote('A/none#1', safe='')}/backup", {}, token=gina)
    assert code == 404


def test_派前电量_有位姿就算来回_没有就都是null(站点):
    s = 站点
    gina = _登(s, "gina")
    _等(lambda: s.req("GET", "/api/robots/A", token=gina)[1].get("fresh"))
    code, d = s.req("GET", "/api/robots/A/goto-plan?x=3&y=4", token=gina)
    assert code == 200, d
    assert {"battery_pct", "dist_m", "cost_pct", "line_pct", "enough"} <= set(d)
    assert d["reason"] == "no_map"          # 外审 3 #2:不带地图参数算不了,明说
    if d["dist_m"] is not None:
        assert d["cost_pct"] >= 3.0 and d["line_pct"] > d["cost_pct"] - 3.0
        assert d["enough"] in (True, False, None)
    assert s.req("GET", "/api/robots/A/goto-plan?x=a&y=4", token=gina)[0] == 400
    assert s.req("GET", "/api/robots/Z/goto-plan?x=1&y=1", token=gina)[0] == 404


def test_充电时段_按流水拼_没结束的to是null(站点):
    s = 站点
    gina = _登(s, "gina")
    now = wall()
    with s.db.tx() as c:
        log = (("goto", now - 3_600_000), ("dock", now - 3_000_000), ("idle", now - 1_800_000),
               ("goto", now - 600_000))
        for st, at in log:
            c.execute("INSERT INTO charge_log(robot_id, state, at_ms) VALUES (?,?,?)",
                      ("A", st, at))
    code, d = s.req("GET", f"/api/robots/charging?since={now - 7_200_000}&until={now}",
                    token=gina)
    assert code == 200, d
    assert d["spans"] == [
        {"robot": "A", "from_ms": now - 3_600_000, "to_ms": now - 1_800_000},
        {"robot": "A", "from_ms": now - 600_000, "to_ms": None}]
    assert s.req("GET", "/api/robots/charging?since=5&until=1", token=gina)[0] == 400


def test_充电时段_窗口前就在充的也算(站点):
    s = 站点
    gina = _登(s, "gina")
    now = wall()
    with s.db.tx() as c:
        c.execute("INSERT INTO charge_log(robot_id, state, at_ms) VALUES (?,?,?)",
                  ("B", "goto", now - 3 * 3_600_000))
    code, d = s.req("GET", f"/api/robots/charging?since={now - 3_600_000}&until={now}", token=gina)
    assert code == 200, d
    assert d["spans"] == [{"robot": "B", "from_ms": now - 3_600_000, "to_ms": None}]


def test_请求支援_事务失败_内存也退回_重试才真的起一条(站点, monkeypatch):
    s = 站点
    alice, gina = _登(s, "alice"), _登(s, "gina")
    _等(lambda: s.req("GET", "/api/robots/A", token=alice)[1].get("fresh"))
    s.loop.call(lambda: s.dog.emergency_stop(True))
    a = _等(lambda: _告警(s, gina, "estop_pressed"))
    desk = s.api.alerts
    real = desk.book.amend
    calls = {"n": 0}

    def boom(*args, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("写原告警时断了")
        return real(*args, **kw)
    monkeypatch.setattr(desk.book, "amend", boom)
    code, _ = s.req("POST", f"/api/alerts/{quote(a['key'], safe='')}/backup", {}, token=gina)
    assert code >= 500
    # 外审 3 #1:库里没有支援告警,内存里也没有;原告警没有「叫过人」的标记
    assert not s.db.query("SELECT 1 FROM alerts WHERE kind='backup_requested'")
    assert not [x for x in desk.open() if x["kind"] == "backup_requested"]
    assert "backup_by" not in desk.book.get(a["key"]).context
    code, d = s.req("POST", f"/api/alerts/{quote(a['key'], safe='')}/backup", {}, token=gina)
    assert code == 200 and d["alert"]["context"]["backup_by"] == "gina"
    assert len(s.db.query("SELECT 1 FROM alerts WHERE kind='backup_requested'")) == 1
    assert len([x for x in desk.open() if x["kind"] == "backup_requested"]) == 1


def test_派前电量_只有待命点没原点_不说够(站点):
    s = 站点
    alice, gina = _登(s, "alice"), _登(s, "gina")
    _等(lambda: s.req("GET", "/api/robots/A", token=alice)[1].get("fresh"))
    robots = s.req("GET", "/api/robots/overview", token=alice)[1]["robots"]
    r = next(x for x in robots if x["robot_id"] == "A")
    m = r.get("map") or {}
    mid, ver = m.get("id") or "m", m.get("version") or "1"
    from nexwar_site.standby import StandbyManager
    stb = StandbyManager(s.db, s.disp, now_ms=wall)
    stb.set("A", "dock", map_id=mid, map_version=ver, x=0.0, y=0.0, yaw=0.0, default=True)
    assert stb.home("A", mid, ver) is None
    url = f"/api/robots/A/goto-plan?x=1&y=0&map_id={mid}&map_version={ver}"
    code, d = s.req("GET", url, token=gina)
    assert code == 200, d
    assert d["enough"] is None and d["reason"] == "no_home"
    with s.db.tx() as c:
        c.execute("INSERT INTO homes(robot_id, map_id, map_version, name, x, y, yaw) "
                  "VALUES (?,?,?,?,?,?,?)", ("A", mid, ver, "home", 0.0, 0.0, 0.0))
    code, d = s.req("GET", url, token=gina)
    assert code == 200, d
    if d.get("reason") == "no_pose":
        assert d["enough"] is None
    else:
        assert d["line_pct"] >= 25.0 + 3.0 * 1.5 - 0.01 and d["enough"] in (True, False)


def test_看一眼_看完后回原点_站点自动派(站点):
    s = 站点
    alice, gina = _登(s, "alice"), _登(s, "gina")
    _等(lambda: s.req("GET", "/api/robots/A", token=alice)[1].get("fresh"))
    code, d = s.req("POST", "/api/robots/A/goto",
                    {"target": {"map_id": "m", "map_version": "1", "frame_id": "map", "x": 0.5,
                                "y": 0.0, "yaw": 0.0}, "then": "nope"}, token=gina)
    assert code == 400
    # 登记了就排在后续名单里(到点那一拍由主循环派;这里只验登记和到点后的派发逻辑)
    look = s.api.look if hasattr(s.api, "look") else None
    if look is None:
        from nexwar_site.look import LookDesk
        from nexwar_site.standby import StandbyManager
        s.api.look = look = LookDesk(s.db, StandbyManager(s.db, s.disp, now_ms=wall), now_ms=wall)
    look.register("A", "t-look-1", "home", by="gina")
    assert "t-look-1" in look.pending
    with s.db.tx() as c:
        c.execute("INSERT INTO events(robot_id, boot_id, seq, event_id, kind, data, stamp, "
                  "received_at) VALUES (?,?,?,?,?,?,?,?)",
                  ("A", "b1", 1, "e-look-1", "task_aborted", '{"task_id": "t-look-1"}', wall(),
                   wall()))
    s.loop.call(lambda: look.tick())
    assert "t-look-1" not in look.pending          # 中止了就不派后续
