"""日志设计 第 1 条(用户 11-10,liang-d5 L1):操作记录每一条写出对象、前后变化、来源、结果和原因。"""

from __future__ import annotations

import logging

from test_site_api import PW, _等, 站

from nexwar_site.audit import redact
from nexwar_site.modes import ArmingDesk
from nexwar_site.standby import StandbyManager


def _站(tmp_path):
    s = 站(tmp_path)
    s.api.arming = ArmingDesk(s.db, now_ms=s.api._now, publish=s.disp.feed.publish)
    return s


def _最后一条(s, action, n=1):
    """回复先发出去、操作记录后写:等到这一类有 ``n`` 条再看最新的。"""
    return _等(lambda: (rows := [r for r in s.api.audit.list() if r["action"] == action])
              and len(rows) >= n and rows[0])


def test_改模式_记从什么改成什么_来源是App(tmp_path):
    s = _站(tmp_path)
    try:
        tok = s.login()
        assert s.req("POST", "/api/mode", {"mode": "home"}, token=tok)[0] == 200
        r = _最后一条(s, "POST /api/mode")
        assert r["target"] == "home"
        assert r["detail"]["from"] == "armed" and r["detail"]["to"] == "home", r
        assert r["detail"]["source"] == "app", "带令牌来的(手机、命令行)"
    finally:
        s.close()


def test_待命点_加和删都记哪台_哪个点_坐标(tmp_path):
    s = _站(tmp_path)
    try:
        s.api.standby = StandbyManager(s.db, s.disp, now_ms=s.api._now)
        tok = s.login()
        body = {"name": "dock", "map_id": "estate-1", "map_version": "7", "x": 1.5, "y": -2.0,
                "yaw": 0.0}
        assert s.req("POST", "/api/robots/A/standby", body, token=tok)[0] == 200
        r = _最后一条(s, "POST /api/robots/A/standby")
        assert r["target"] == "A"
        assert r["detail"]["op"] == "add" and r["detail"]["name"] == "dock"
        assert (r["detail"]["x"], r["detail"]["y"]) == (1.5, -2.0)
        assert r["detail"]["map"] == "estate-1:7"
        assert s.req("POST", "/api/robots/A/standby", {"name": "dock", "remove": True},
                     token=tok)[0] == 200
        r = _最后一条(s, "POST /api/robots/A/standby", n=2)
        assert r["detail"]["op"] == "remove" and r["detail"]["was"][0]["x"] == 1.5, r
    finally:
        s.close()


def test_路径里认得出对象_处理函数没写也填上_请求内容去敏存一份(tmp_path):
    s = _站(tmp_path)
    try:
        tok = s.login()
        # 处理函数没写改了什么的:请求去敏存一份(去敏规则单测;接口这条路看下面的 resume)
        req = redact({"token": "fcm-secret-123", "platform": "android",
                      "camera": "rtsp://bob:s3cret@10.0.0.2/s", "zones": list(range(25))})
        assert req["token"] == "***", "令牌不落库"
        assert req["platform"] == "android" and req["camera"] == "rtsp://bob:***@10.0.0.2/s"
        assert req["zones"][-1] == "…共 25 项"
        # 处理函数写明了的(建账号):不另存请求,密码当然也不在
        s.req("POST", "/api/accounts", {"name": "bob", "password": PW, "role": "guard",
                                        "confirm_password": PW}, token=tok)
        r = _最后一条(s, "POST /api/accounts")
        assert "request" not in r["detail"] and PW not in str(r)
        s.req("POST", "/api/robots/B/resume", {"note": "现场看过了"}, token=tok)
        r = _最后一条(s, "POST /api/robots/B/resume")
        assert r["target"] == "B"
    finally:
        s.close()


def test_被拒的写请求_站点日志里写原因_谁_从哪来(tmp_path, caplog):
    s = _站(tmp_path)
    try:
        tok = s.login()
        with caplog.at_level(logging.WARNING, logger="nexwar_site.api"):
            code, d = s.req("POST", "/api/mode", {"mode": "nonsense"}, token=tok)
            line = _等(lambda: next((m for m in caplog.messages
                                    if m.startswith("拒绝 POST /api/mode")), None))
        assert code == 400
        assert "status=400" in line and "actor=alice" in line and "remote=" in line
        assert d["error"][:10] in line, (line, d)
        r = _最后一条(s, "POST /api/mode")
        assert r["status"] == 400 and r["detail"]["error"] == d["error"]
    finally:
        s.close()


def test_操作记录留一年_更早的删掉(tmp_path):
    s = _站(tmp_path)
    try:
        log = s.api.audit
        now = s.api._now()
        log._now = lambda: now - 400 * 86_400_000
        log.record(actor="alice", action="POST /api/mode", target="home")
        log._now = lambda: now - 300 * 86_400_000
        log.record(actor="alice", action="POST /api/mode", target="armed")
        log._now = lambda: now
        assert log.prune() == 1
        assert [r["target"] for r in log.list() if r["action"] == "POST /api/mode"] == ["armed"]
    finally:
        s.close()
