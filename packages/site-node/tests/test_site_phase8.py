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
    assert set(d) == {"battery_pct", "dist_m", "cost_pct", "line_pct", "enough"}
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
