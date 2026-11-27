"""POC 第 4 项:回原点、中止并回原点。``POST /api/robots/<id>/home/return {abort?}``(dispatch 权限):
没原点 409 说去哪标;有任务在跑不带 abort 409;带 abort 先中止、等它停下再去原点(任务号 ``standby-``,
自动回程的去重认它)。真 HTTP、真代理。"""

from __future__ import annotations

import pytest
from test_site_api import PW, _等, 站


@pytest.fixture
def 站点(tmp_path):
    from nexwar_site.standby import StandbyManager
    s = 站(tmp_path)
    s.accounts.add("gina", PW, role="guard")
    s.accounts.add("olga", PW, role="owner")
    s.api.standby = StandbyManager(s.db, s.disp, now_ms=s.disp._now)
    yield s
    s.close()


def _登(s, name):
    return s.req("POST", "/api/login", {"name": name, "password": PW})[1]["token"]


def _备好(s):
    _等(lambda: s.disp.clients["A"].capabilities is not None
        and "mark_home" in s.disp.clients["A"].capabilities.tasks
        and s.disp.clients["A"].status is not None)


def _任务(s):
    t = s.disp.clients["A"].status.task
    return t.task_id if t is not None else None


def _去远处(s, tok):
    target = {"map_id": "estate-1", "map_version": "7", "frame_id": "map", "x": 30.0, "y": 0.0,
              "yaw": 0.0}
    code, d = s.req("POST", "/api/robots/A/goto", {"target": target}, token=tok)
    assert code == 200 and d["ack"]["result"] == "accepted", d
    _等(lambda: _任务(s) == d["task_id"])
    return d["task_id"]


def test_没原点_409_说去哪标(站点):
    s = 站点
    gina = _登(s, "gina")
    _备好(s)
    code, d = s.req("POST", "/api/robots/A/home/return", {}, token=gina)
    assert code == 409 and "还没有原点" in d["error"] and "设为原点" in d["error"], d


def test_回原点_有任务在跑要先中止_带abort就先停再去(站点):
    s = 站点
    alice, gina, olga = _登(s, "alice"), _登(s, "gina"), _登(s, "olga")
    _备好(s)
    assert s.req("POST", "/api/robots/A/home/here", {"name": "dock"}, token=alice)[0] == 200
    assert s.req("POST", "/api/robots/A/home/return", {}, token=olga)[0] == 403
    tid = _去远处(s, gina)
    code, d = s.req("POST", "/api/robots/A/home/return", {}, token=gina)
    assert code == 409 and "中止并回原点" in d["error"], d
    assert _任务(s) == tid, "没动它"
    code, d = s.req("POST", "/api/robots/A/home/return", {"abort": True}, token=gina)
    assert code == 200 and d["ack"]["result"] == "accepted", d
    assert d["task_id"].startswith("standby-") and d["aborted"] == tid, d
    _等(lambda: _任务(s) == d["task_id"])
    # 操作记录在回完请求之后才写:等它
    _等(lambda: any(r["detail"].get("abort") is True for r in s.api.audit.list()
                   if r["action"] == "POST /api/robots/A/home/return"))


def test_没任务_直接回原点(站点):
    s = 站点
    alice, gina = _登(s, "alice"), _登(s, "gina")
    _备好(s)
    assert s.req("POST", "/api/robots/A/home/here", {"name": "dock"}, token=alice)[0] == 200
    code, d = s.req("POST", "/api/robots/A/home/return", {}, token=gina)
    assert code == 200 and d["task_id"].startswith("standby-home-") and d.get("aborted") is None, d


def test_外审r1_中止后停车没确认_不派回原点(站点):
    s = 站点
    alice, gina = _登(s, "alice"), _登(s, "gina")
    _备好(s)
    assert s.req("POST", "/api/robots/A/home/here", {"name": "dock"}, token=alice)[0] == 200
    tid = _去远处(s, gina)
    ev = s.agent.processor.events
    orig = ev.emit

    def 停不稳(kind, data, *a, **k):                   # 同 engine_goto:停车确认等不到也进终态
        if kind in ("task_aborted", "task_failed") and data.get("task_id") == tid:
            data = {**data, "reason": f"{data.get('reason', '')}; stop_unconfirmed"}
        return orig(kind, data, *a, **k)
    ev.emit = 停不稳
    code, d = s.req("POST", "/api/robots/A/home/return", {"abort": True}, token=gina)
    assert code == 409 and "停车没确认" in d["error"], d
    assert not any(c["kind"] == "goto" and c["task_id"].startswith("standby-")
                   for c in s.disp.commands("A", 50)), "没派回原点"


def test_用户1127_回待命点_有任务在跑_带abort先停再去(站点):
    """易用性 37 用户 11-27 轮 P2-1:值守、临时巡逻跑着时点「回待命点」,机器人回 busy、接着跑。"""
    s = 站点
    alice, gina = _登(s, "alice"), _登(s, "gina")
    _备好(s)
    assert s.req("POST", "/api/robots/A/standby/here", {"name": "lobby"}, token=alice)[0] == 200
    assert s.req("POST", "/api/robots/A/standby/return", {"abort": 1}, token=gina)[0] == 400
    tid = _去远处(s, gina)
    # 新人 11-28 第二轮 P2:不带 abort(页面刚显示空闲、其实已经出发了)—— 站点先拦,说再点一次
    code, d = s.req("POST", "/api/robots/A/standby/return", {}, token=gina)
    assert code == 409 and d.get("reason_code") == "busy_return" and "Press the button again" in \
        d["reason_en"], d
    assert _任务(s) == tid, "没动它手上那一趟"
    code, d = s.req("POST", "/api/robots/A/standby/return", {"abort": True}, token=gina)
    assert code == 200 and d["ack"]["result"] == "accepted", d
    assert d["task_id"].startswith("standby-") and d["aborted"] == tid, d
    _等(lambda: _任务(s) == d["task_id"])
    # 操作记录在回完请求之后才写:等它
    _等(lambda: any(r["detail"].get("abort") is True for r in s.api.audit.list()
                   if r["action"] == "POST /api/robots/A/standby/return"))


def test_用户1127_中止并回原点_回到后怎么办_参数不对400_撤防要权限_撤防了站点就是撤防(站点):
    from nexwar_site.modes import ArmingDesk
    s = 站点
    alice, gina = _登(s, "alice"), _登(s, "gina")
    _备好(s)
    assert s.req("POST", "/api/robots/A/home/here", {"name": "dock"}, token=alice)[0] == 200
    for bad in ({"abort": True, "after": "later"}, {"abort": True, "after": "wait", "wait_min": 0},
                {"abort": True, "after": "wait", "wait_min": 241},
                {"abort": True, "after": "wait", "wait_min": "5"}):
        assert s.req("POST", "/api/robots/A/home/return", bad, token=gina)[0] == 400, bad
    code, d = s.req("POST", "/api/robots/A/home/return", {"abort": True, "after": "disarm"},
                    token=gina)
    assert code == 409 and "布防模式" in d["error"], d
    s.api.arming = ArmingDesk(s.db, now_ms=s.disp._now)
    tid = _去远处(s, gina)
    code, d = s.req("POST", "/api/robots/A/home/return", {"abort": True, "after": "disarm"},
                    token=gina)
    assert code == 200 and d["aborted"] == tid, d
    assert s.api.arming.disarmed(), "撤防了"
    _等(lambda: any(r["detail"].get("after") == "disarm" for r in s.api.audit.list()
                   if r["action"] == "POST /api/robots/A/home/return"))
    code, d = s.req("POST", "/api/robots/A/home/return",
                    {"abort": True, "after": "wait", "wait_min": 5}, token=gina)
    assert code == 200, d
