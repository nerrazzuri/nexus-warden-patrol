"""W00c5a:告警与值守的站点 API。真 HTTP、真代理(SimRobot):狗报事实,站点判,手机经站点看、确认。"""

from __future__ import annotations

import json
from urllib.parse import quote

import pytest
from test_site_api import PW, _等, 站


@pytest.fixture
def 站点(tmp_path):
    s = 站(tmp_path, alerts=True)
    s.accounts.add("gina", PW, role="guard")
    s.accounts.add("olga", PW, role="owner")
    yield s
    s.close()


def _登(s, name):
    code, d = s.req("POST", "/api/login", {"name": name, "password": PW})
    assert code == 200, d
    return d["token"]


def _告警(s, tok, kind):
    code, d = s.req("GET", "/api/alerts", token=tok)
    assert code == 200, d
    return next((a for a in d["alerts"] if a["kind"] == kind), None)


def _键(a):
    return quote(a["key"], safe="")


def test_狗急停_站点出P1_确认记登录账号_管理员也能确认(站点):
    s = 站点
    alice, gina, olga = _登(s, "alice"), _登(s, "gina"), _登(s, "olga")
    _等(lambda: s.req("GET", "/api/robots/A", token=alice)[1].get("fresh"))
    s.loop.call(lambda: s.dog.emergency_stop(True))
    a = _等(lambda: _告警(s, olga, "estop_pressed"))
    assert a["level"] == "P1" and a["robot"] == "A" and a["acked_by"] == ""
    # W20:管理员留守时自己看到了,能点「我知道了」
    code, d = s.req("POST", f"/api/alerts/{_键(a)}/ack", {"who": "mallory"}, token=olga)
    assert code == 200 and d["alert"]["acked_by"] == "olga", "确认人取登录账号,不信请求体"
    code, d = s.req("POST", f"/api/alerts/{_键(a)}/resolve", {}, token=gina)
    assert code == 200 and d["alert"]["resolved_by"] == "gina"
    assert _告警(s, alice, "estop_pressed") is None, "默认只列未解决的"
    code, d = s.req("GET", "/api/alerts?all=1", token=alice)
    assert any(x["key"] == a["key"] and x["resolved_by"] == "gina" for x in d["alerts"])
    audit = s.req("GET", "/api/audit", token=alice)[1]["audit"]
    assert any(r["actor"] == "olga" and "/ack" in r["action"] and r["target"] == a["key"]
               for r in audit), audit[:3]


def test_确认不存在的键404_没登录401(站点):
    s = 站点
    gina = _登(s, "gina")
    code, _ = s.req("POST", f"/api/alerts/{quote('A/stuck#99', safe='')}/ack", {}, token=gina)
    assert code == 404
    assert s.req("GET", "/api/alerts")[0] == 401
    assert s.req("GET", "/api/watch/summary")[0] == 401


def test_狗报跌倒故障_站点认出fallen(站点):
    s = 站点
    alice = _登(s, "alice")
    _等(lambda: s.req("GET", "/api/robots/A", token=alice)[1].get("fresh"))
    s.dog.inject_fault("3", True, "机身跌倒")
    a = _等(lambda: _告警(s, alice, "fallen"))
    assert "[3] 机身跌倒" in a["detail"]


def test_值守汇总_每台狗一行_狗上存储那几项是不知道而不是0(站点):
    s = 站点
    olga = _登(s, "olga")
    _等(lambda: s.req("GET", "/api/robots/A", token=olga)[1].get("fresh"))
    _等(lambda: s.disp.telemetry_at.get("A"))
    code, d = s.req("GET", "/api/watch/summary", token=olga)
    assert code == 200, d
    [r] = d["robots"]
    assert r["robot_id"] == "A" and r["online"] is True and r["fresh"] is True
    assert isinstance(r["battery_pct"], (int, float)) and r["battery_as_of_ms"] > 0
    # W09d:狗慢的方向(在途让刚来的几条略负)要攒够 10 条才算,之前是「不知道」、说得出为什么
    assert (r["clock_skew_s"] is None and r["why"]["clock_skew_s"]) or abs(r["clock_skew_s"]) < 5
    assert r["alerts"] == {"P1": 0, "P2": 0, "P3": 0}
    for k in ("disk_used_ratio", "upload_backlog"):                # W00c5d:狗还没报过盘况
        assert r[k] is None and "未知" in r["why"][k], k
    assert r["bundle_lag"] is None and "任务包" in r["why"]["bundle_lag"]
    assert r["backup"] is None and "站点" in r["why"]["backup"]
    assert d["site"]["schedule_ok"] is None and "未启用排程" in d["site"]["why"]["schedule_ok"]


def test_SSE里看得到告警的变化(站点):
    import http.client
    s = 站点
    alice = _登(s, "alice")
    _等(lambda: s.req("GET", "/api/robots/A", token=alice)[1].get("fresh"))
    host, port = s.api.httpd.server_address[:2]
    conn = http.client.HTTPConnection(host, port, timeout=10)
    conn.request("GET", "/api/events", headers={"Authorization": f"Bearer {alice}"})
    resp = conn.getresponse()
    s.loop.call(lambda: s.dog.emergency_stop(True))
    for _ in range(400):
        line = resp.fp.readline().decode()
        if line.startswith("data:"):
            d = json.loads(line[5:])
            if d.get("kind") == "alert":
                assert d["alert"]["kind"] == "estop_pressed"
                break
    else:
        raise AssertionError("SSE 里未等到告警")
    conn.close()



def test_交接班那一张_截多少条写明白_limit不对400(站点):
    s = 站点
    alice = _登(s, "alice")
    for i in range(3):
        s.loop.call(lambda i=i: _raise(s, i))
    code, d = s.req("GET", "/api/alerts?all=1&limit=2", token=alice)
    assert code == 200 and len(d["alerts"]) == 2 and d["limit"] == 2 and d["truncated"] is True
    code, d = s.req("GET", "/api/alerts?all=1", token=alice)
    assert d["limit"] == 200 and d["truncated"] is False
    for bad in ("0", "x", "99999"):
        assert s.req("GET", f"/api/alerts?all=1&limit={bad}", token=alice)[0] == 400


async def _raise(s, i):
    s.desk.raise_alert(kind="run_done", robot=f"R{i}", title="已完成")


def test_在事件循环里报告警_直接报不等自己(tmp_path):
    """LoopAlerts 从循环线程里调(比如以后派遣器里报):跳回循环再等结果会等自己,等满 10 s 才炸。"""
    import time as _t

    from nexwar_site.alert_store import AlertDesk, LoopAlerts
    from nexwar_site.db import SiteDB
    from nexwar_site.loop import LoopThread
    lt = LoopThread()
    lt.start()
    try:
        la = LoopAlerts(AlertDesk(SiteDB(tmp_path / "s.db"), now_ms=lambda: 1), lt)

        async def 在循环里():
            return la.raise_alert(kind="backup_stale", robot="site", title="t")
        t0 = _t.monotonic()
        got = lt.call(在循环里, timeout_s=15)
        assert got is not None and _t.monotonic() - t0 < 2
        got = la.raise_alert(kind="disk_80", robot="A", title="t")
        assert got is not None, "别的线程照样跳进去"
    finally:
        lt.stop()


def test_没回待命点_进告警簿P2_值守屏看得见(站点):
    """W00c6b:``standby_failed`` 以前只推进 SSE 事件流,值守屏的告警簿不收、手机不显示 —— 报告里写的
    「推给值守的人看」其实没人看得见。告警源挂到派遣器上时顺带听推送流。"""
    s = 站点
    gina = _登(s, "gina")
    async def 推():
        s.disp.feed.publish({"kind": "standby_failed", "robot_id": "A", "after": "sched-1",
                             "reason": "来路不明"})
    s.loop.call(推)
    a = _等(lambda: _告警(s, gina, "standby_failed"))
    assert a["level"] == "P2" and "待命点" in a["title"] and "来路不明" in a["detail"]


def test_W17外审_值守令牌只有告警流_首帧不带狗_别的帧一律不转(站点):
    """真连 SSE。外审:原先值守令牌走通用的 /api/events,首帧是全部狗的视图、之后是状态、任务事件、
    回执、入侵账 —— 偷到一个 30 天的令牌就能一直看整个站点。"""
    import http.client
    s = 站点
    gina = _登(s, "gina")
    s.loop.call(lambda: _raise(s, 0))                   # 先有一条没解决的:首帧里要有它
    code, d = s.req("POST", "/api/watch/token", {}, token=gina)
    assert code == 200, d
    w = d["token"]
    for path in ("/api/events", "/api/alerts", "/api/watch/summary", "/api/robots"):
        assert s.req("GET", path, token=w)[0] == 403, path
    host, port = s.api.httpd.server_address[:2]
    conn = http.client.HTTPConnection(host, port, timeout=10)
    conn.request("GET", "/api/watch/events", headers={"Authorization": f"Bearer {w}"})
    resp = conn.getresponse()
    assert resp.status == 200

    def 下一帧():
        for _ in range(200):
            line = resp.fp.readline().decode()
            if line.startswith("data:"):
                return json.loads(line[5:])
        raise AssertionError("未等到下一帧")
    first = 下一帧()
    assert first["kind"] == "snapshot" and "robots" not in first
    assert [a["robot"] for a in first["alerts"]] == ["R0"]
    feed = s.disp.feed
    for kind in ("status", "event", "ack", "reconcile", "incident", "snapshot"):
        feed.publish({"kind": kind, "robots": ["A"], "robot_id": "A", "secret": kind})
    s.loop.call(lambda: _raise(s, 1))
    got = 下一帧()
    assert got["kind"] == "alert" and got["alert"]["robot"] == "R1", got
    conn.close()
    # 普通会话照旧是全量流
    conn = http.client.HTTPConnection(host, port, timeout=10)
    conn.request("GET", "/api/events", headers={"Authorization": f"Bearer {gina}"})
    resp = conn.getresponse()
    assert "robots" in 下一帧()
    conn.close()


def test_W74_看见人_没到场关不了409说清楚_点了已到场再关(站点):
    s = 站点
    alice, gina = _登(s, "alice"), _登(s, "gina")
    async def 报():
        s.desk.raise_alert(kind="dog_sees_person", robot="A", title="机器人看见人了:1 个人")
    s.loop.call(报)
    a = _等(lambda: _告警(s, gina, "dog_sees_person"))
    code, d = s.req("POST", f"/api/alerts/{_键(a)}/resolve", {"verdict": "handled"}, token=gina)
    assert code == 409 and "已到场" in d["error"], d
    code, d = s.req("POST", f"/api/alerts/{_键(a)}/arrive", {"who": "mallory"}, token=gina)
    assert code == 200 and d["alert"]["context"]["arrived_by"] == "gina", "到场人取登录账号"
    assert d["alert"]["acked_by"] == "gina"
    code, d = s.req("POST", f"/api/alerts/{_键(a)}/resolve", {"verdict": "handled"}, token=gina)
    assert code == 200 and d["alert"]["resolved_by"] == "gina"
    audit = s.req("GET", "/api/audit", token=alice)[1]["audit"]
    assert any(r["actor"] == "gina" and "/arrive" in r["action"] for r in audit)


def test_网页P0_04_处置带备注_十分钟内能撤销_过了不行(站点):
    """网页易用性第 1 轮 P0-04:「已处理」一点就关,不能写备注、不能撤销。"""
    s = 站点
    gina = _登(s, "gina")
    async def 报():
        s.desk.raise_alert(kind="stuck", robot="A", title="卡住了")
    s.loop.call(报)
    a = _等(lambda: _告警(s, gina, "stuck"))
    code, d = s.req("POST", f"/api/alerts/{_键(a)}/resolve",
                    {"verdict": "false_alarm", "note": "风吹倒的纸箱"}, token=gina)
    assert code == 200 and d["alert"]["verdict"] == "false_alarm"
    assert d["alert"]["context"]["note"] == "风吹倒的纸箱"
    code, d = s.req("POST", f"/api/alerts/{_键(a)}/reopen", {}, token=gina)
    assert code == 200 and d["alert"]["resolved_ms"] is None and d["alert"]["verdict"] == ""
    assert _告警(s, gina, "stuck") is not None, "撤销后回到待处理"
    code, d = s.req("POST", f"/api/alerts/{_键(a)}/resolve", {"note": 5}, token=gina)
    assert code == 400, "备注要是字符串"
    code, d = s.req("POST", f"/api/alerts/{_键(a)}/resolve", {"verdict": "handled"}, token=gina)
    s.desk._now = lambda: d["alert"]["resolved_ms"] + 11 * 60_000
    code, d = s.req("POST", f"/api/alerts/{_键(a)}/reopen", {}, token=gina)
    assert code == 400 and "10 分钟" in d["error"], d


def test_按日期在站点查报警_能翻页_按类型机器人筛(站点):
    """liang-d5 第 5 轮前:报警记录按日期只看得到最近 500 条;一个月前的那天要能查到。"""
    s = 站点
    alice = _登(s, "alice")
    for i in range(5):
        s.loop.call(lambda i=i: _raise(s, i))
    day = 86_400_000
    old = 1_700_000_000_000
    with s.desk.db.tx() as c:   # 把 R0–R2 挪到一个月前那天,R3、R4 留在今天
        for i in range(3):
            c.execute("UPDATE alerts SET first_ms = ?, last_ms = ? WHERE robot = ?",
                      (old + i * 1000, old + i * 1000 + 10, f"R{i}"))
    rng = f"since={old}&until={old + day}"
    code, d = s.req("GET", f"/api/alerts?{rng}&limit=2", token=alice)
    assert code == 200, d
    assert d["total"] == 3 and [a["robot"] for a in d["alerts"]] == ["R2", "R1"]
    code, d = s.req("GET", f"/api/alerts?{rng}&limit=2&offset=2", token=alice)
    assert [a["robot"] for a in d["alerts"]] == ["R0"]
    code, d = s.req("GET", f"/api/alerts?{rng}&robot=R1", token=alice)
    assert d["total"] == 1 and d["alerts"][0]["robot"] == "R1"
    code, d = s.req("GET", f"/api/alerts?{rng}&kind=fallen,lens_blocked", token=alice)
    assert d["total"] == 0
    bads = (f"since={old}&until={old}", "since=x", f"since={old}&level=P9", f"since={old}&limit=0")
    for bad in bads:
        assert s.req("GET", f"/api/alerts?{bad}", token=alice)[0] == 400, bad


def test_全站活动日志_按日期人类别查_翻页_导出CSV(站点):
    """liang-d5 第 5 轮前:「11 月 5 日晚上谁撤的防、谁派的机器人」—— 按日期、人、类别查,能导出。"""
    import urllib.request
    s = 站点
    alice = _登(s, "alice")
    old = 1_700_000_000_000
    rows = [(old + 1000, "gina", "POST /api/mode", "disarmed"),
            (old + 2000, "gina", "POST /api/robots/A/goto", "A"),
            (old + 3000, "olga", "POST /api/robots/A/halt", "A"),
            (old + 4000, "olga", "POST /api/mode", "armed")]
    with s.desk.db.tx() as c:
        for at, who, act, tgt in rows:
            c.execute("INSERT INTO audit(at, actor, action, target, status) VALUES (?,?,?,?,200)",
                      (at, who, act, tgt))
    rng = f"since={old}&until={old + 86_400_000}"
    code, d = s.req("GET", f"/api/audit?{rng}&limit=3", token=alice)
    assert code == 200 and d["total"] == 4
    assert [r["target"] for r in d["audit"]] == ["armed", "A", "A"]
    d = s.req("GET", f"/api/audit?{rng}&limit=3&offset=3", token=alice)[1]
    assert d["audit"][0]["target"] == "disarmed"
    d = s.req("GET", f"/api/audit?{rng}&group=arming", token=alice)[1]
    assert [r["actor"] for r in d["audit"]] == ["olga", "gina"]
    d = s.req("GET", f"/api/audit?{rng}&group=dispatch&actor=gina", token=alice)[1]
    assert d["total"] == 1 and d["audit"][0]["action"] == "POST /api/robots/A/goto"
    assert s.req("GET", f"/api/audit?{rng}&group=nope", token=alice)[0] == 400
    assert s.req("GET", "/api/audit", token=alice)[0] == 200         # 旧的用法照旧(用户页)
    r = urllib.request.Request(s.api.url + f"/api/audit?{rng}&format=csv")
    r.add_header("Authorization", f"Bearer {alice}")
    with urllib.request.urlopen(r, timeout=15) as resp:
        assert resp.headers["Content-Type"].startswith("text/csv")
        assert "attachment" in resp.headers["Content-Disposition"]
        text = resp.read().decode("utf-8-sig")
    lines = text.strip().splitlines()
    assert lines[0].startswith("time,actor") and len(lines) == 5 and "POST /api/mode" in lines[1]


def test_往天的巡逻接口_日期要写对(站点):
    s = 站点
    alice = _登(s, "alice")
    code, d = s.req("GET", "/api/patrols/day?date=2026-11-05", token=alice)
    assert code == 200 and d["date"] == "2026-11-05"
    for bad in ("", "?date=11-05", "?date=2026-02-30"):
        assert s.req("GET", f"/api/patrols/day{bad}", token=alice)[0] == 400, bad


def test_第10轮_W9_01_活动日志的对象是日程_路线时带显示名(站点):
    """第 10 轮复测:活动日志写「改了巡逻日程 route-1-2」「改了路线 route-1」——
    起了中文名的写中文名。"""
    s = 站点
    alice = _登(s, "alice")
    with s.db.tx() as c:
        c.execute("INSERT INTO routes(route_id, map_id, map_version, definition, revision, "
                  "updated_ms, title) VALUES ('route-1','m1','7','{}',1,0,'一楼夜巡')")
        c.execute("INSERT INTO route_schedules(entry_id, title, definition, revision, "
                  "active_from_ms, updated_ms, updated_by, source) "
                  "VALUES ('route-1-2', '夜巡测试', '{}', 1, 0, 0, 'a', 'editor')")
    for tgt in ("route-1-2", "route-1", "gone-9"):
        s.api.audit.record(actor="demo", action="schedule blocked", target=tgt, status=200)
    rows = {r["target"]: r for r in s.req("GET", "/api/audit", token=alice)[1]["audit"]}
    assert rows["route-1-2"]["target_name"] == "夜巡测试"
    assert rows["route-1"]["target_name"] == "一楼夜巡"
    assert "target_name" not in rows["gone-9"], "查不到名字的不加(网页照旧写编号)"


def test_第11轮_W11_01_活动日志记当时的名字_删了也不变回编号(站点):
    """名字在写记录那一刻存下:删掉以后、编号换了主人以后,旧记录照旧写当时的名字。"""
    s = 站点
    alice = _登(s, "alice")
    with s.db.tx() as c:
        c.execute("INSERT INTO route_schedules(entry_id, title, definition, revision, "
                  "active_from_ms, updated_ms, updated_by, source) "
                  "VALUES ('route-1-2', '夜巡测试', '{}', 1, 0, 0, 'a', 'editor')")
    st, _ = s.req("POST", "/api/route-schedules/route-1-2/delete", {"base_revision": 1},
                  token=alice)
    assert st == 200
    import time
    for _ in range(100):                                  # 审计在回完话之后才写
        if s.db.query("SELECT 1 FROM audit WHERE target='route-1-2'"):
            break
        time.sleep(0.02)
    with s.db.tx() as c:                                  # 后来这个编号叫了别的名字
        c.execute("INSERT INTO retired_ids(kind, id, title, deleted_ms) "
                  "VALUES ('schedule','route-1-2','补跑测试',0) "
                  "ON CONFLICT(kind, id) DO UPDATE SET title='补跑测试'")
    [row] = [r for r in s.req("GET", "/api/audit", token=alice)[1]["audit"]
             if r["target"] == "route-1-2"]
    assert row["target_name"] == "夜巡测试" and row["detail"]["delete"] is True
