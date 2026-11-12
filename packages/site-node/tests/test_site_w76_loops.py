"""W76 循环巡逻(站点):派巡逻带圈数(0 = 一直巡逻)、全站电量线写进任务、老机器人不派一直巡逻、
估时、日程到点打断一直巡逻。"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from test_site_adhoc import 任务定义, 台  # noqa: F401 —— 台 是夹具

from nexwar_contract.mission import LOOPS_FOREVER, parse_mission
from nexwar_site import adhoc as ah
from nexwar_site.adhoc import LoopsRefused, geom_estimate_s, with_loops
from nexwar_site.energy import DRAIN_PCT_PER_H

NEW = {"loops_forever": True}


def test_带圈数_写进任务_电量线取路线和全站的高的那个():
    w = with_loops(任务定义(), 3, return_pct=40.0, caps=NEW)
    m = parse_mission(w)
    assert m.policy.loops == 3 and m.policy.battery_return_pct == 40.0
    w = with_loops({**任务定义(), "policy": {"battery_return_pct": 50.0}}, 1, return_pct=40.0,
                   caps={})
    assert parse_mission(w).policy.battery_return_pct == 50.0


def test_没给圈数_路线里写的圈数不动_电量线照样写():
    w = with_loops({**任务定义(), "policy": {"loops": 2}}, None, return_pct=30.0, caps={})
    m = parse_mission(w)
    assert m.policy.loops == 2 and m.policy.battery_return_pct == 30.0


def test_一直巡逻_新机器人能派_老机器人不派_说清楚():
    w = with_loops(任务定义(), LOOPS_FOREVER, return_pct=25.0, caps=NEW)
    assert parse_mission(w).policy.forever
    with pytest.raises(LoopsRefused, match="升级"):
        with_loops(任务定义(), LOOPS_FOREVER, return_pct=25.0, caps={})


@pytest.mark.parametrize("bad", [-1, 100, True, "3", 2.0])
def test_圈数不对_拒(bad):
    with pytest.raises(ValueError, match="循环次数"):
        with_loops(任务定义(), bad, return_pct=25.0, caps=NEW)


def test_估时_几圈按路长乘圈数_不按单圈的历史(台):  # noqa: F811
    t = 台
    m = parse_mission(with_loops(任务定义(), 3, return_pct=25.0, caps=NEW))
    one = parse_mission(任务定义())
    assert geom_estimate_s(m) > 2.5 * geom_estimate_s(one)
    t.desk.history_s = lambda r, name: 900.0
    assert t.desk.estimate_s("A", one) == int(900 * ah.MARGIN)
    assert t.desk.estimate_s("A", m) == int(max(geom_estimate_s(m), 60.0) * ah.MARGIN), \
        "单圈的历史不拿来估三圈"


def test_估时_一直巡逻_按从现在电量用到电量线(台):  # noqa: F811
    t = 台
    t.disp.clients["A"] = SimpleNamespace(telemetry=SimpleNamespace(battery_pct=85.0, pose=None),
                                          capabilities=None)
    m = parse_mission(with_loops(任务定义(), LOOPS_FOREVER, return_pct=25.0, caps=NEW))
    want = (85.0 - 25.0) / DRAIN_PCT_PER_H * 3600
    assert t.desk.estimate_s("A", m) == pytest.approx(int(want * ah.MARGIN), abs=2)


def test_几圈和一直巡逻_都不在末尾加走回起点(台):  # noqa: F811
    from test_site_adhoc import _站在
    t = 台
    _站在(t, -2.0, -1.0, path="planned")
    assert [p["name"] for p in t.desk.with_return("A", 任务定义())["waypoints"]] == \
        ["a", "b", "start"], "一圈的照旧加"
    for loops in (LOOPS_FOREVER, 3):
        w = with_loops(任务定义(), loops, return_pct=25.0, caps=NEW)
        assert [p["name"] for p in t.desk.with_return("A", w)["waypoints"]] == ["a", "b"], loops


# ------------------------------------------------------------ 用户 11-12:日程到点打断一直巡逻


def test_一直巡逻_撞日程也马上派_优先级比日程低_任务号带前缀(台):  # noqa: F811
    from test_site_adhoc import 跑

    from nexwar_site.priorities import FOREVER_PATROL, FOREVER_PREFIX, SCHEDULE_BASE
    t = 台                                               # 20:00,日程 22:00
    w = with_loops(任务定义(), LOOPS_FOREVER, return_pct=25.0, caps=NEW)
    r = 跑(t.desk.submit("A", w, label="loop", by="gina"))
    assert r["queued"] is False, r
    s = t.disp.sent[-1]
    assert s["priority"] == FOREVER_PATROL < SCHEDULE_BASE
    assert s["task_id"].startswith(FOREVER_PREFIX)


async def test_日程到点_正在一直巡逻的机器人照派日程_机器人停下一直巡逻改跑日程(tmp_path):
    from test_site_dispatcher import 台子
    from test_site_schedule import 打包, 毫秒
    from test_site_schedule_alerts import _拍
    from test_site_schedule_alerts import 站 as _站夹具  # noqa: F401

    from nexwar_site.catalog import import_bundle
    from nexwar_site.priorities import FOREVER_PATROL, FOREVER_PREFIX
    from nexwar_site.scheduler import SiteScheduler
    t = 台子(tmp_path)
    t.clock.ms = 毫秒(21, 50)
    t.dog.inject_battery(100.0)
    await t.start()
    try:
        import_bundle(t.db, 打包(tmp_path, 1), imported_by="alice", now_ms=t.clock())
        t.heard = []
        t.sched = SiteScheduler(t.db, t.site, now_ms=t.clock,
                                on_outcome=lambda *a: t.heard.append(a))
        await t.run(2)
        w = with_loops(任务定义(), LOOPS_FOREVER, return_pct=25.0, caps=NEW)
        r = await t.send(t.site.patrol("A", w, issued_by="gina", priority=FOREVER_PATROL,
                                       task_id=f"{FOREVER_PREFIX}x1"))
        assert r["ack"]["result"] == "accepted", r
        await t.run(20)
        assert t.site.busy("A") == f"{FOREVER_PREFIX}x1"
        t.clock.ms = 毫秒(22, 0, 30)
        await t.run(2)
        await _拍(t)
        assert [x["outcome"] for x in t.sched.runs("nightly")] == ["started"], t.sched.runs()
        await t.run(20)
        kinds = [e["kind"] for e in t.db.query(
            "SELECT kind FROM events WHERE json_extract(data, '$.task_id')=?",
            (f"{FOREVER_PREFIX}x1",))]
        assert "task_preempted" in kinds, kinds
        assert (t.site.busy("A") or "").startswith("sched-")
    finally:
        await t.close()


def test_先看会怎样_一直巡逻马上走_说会被哪趟日程打断(台):  # noqa: F811
    t = 台                                               # 20:00,日程 22:00
    w = with_loops(任务定义(), LOOPS_FOREVER, return_pct=25.0, caps=NEW)
    p = t.desk.plan("A", w)
    assert p["queued"] is False and p["forever"] is True
    assert "22:00" in p["interrupted_by"], p


def test_任务包里的路线不许存一直巡逻_不然日程会派出去(tmp_path):
    import pytest as _pt
    from test_site_schedule import 打包

    from nexwar_site.catalog import CatalogError, import_bundle
    from nexwar_site.db import SiteDB
    db = SiteDB(tmp_path / "s.db")
    bad = {**任务定义(), "policy": {"loops": 0}}
    with _pt.raises(CatalogError, match="loops"):
        import_bundle(db, 打包(tmp_path, 1, mission=bad), imported_by="alice", now_ms=1)
    db.close()


def test_外审1_路线写了低电接着走_派一直巡逻时换成回原点():
    w = with_loops({**任务定义(), "policy": {"on_battery_low": "continue"}}, LOOPS_FOREVER,
                   return_pct=25.0, caps=NEW)
    assert parse_mission(w).policy.on_battery_low == "return_home"


def test_外审1_估时的历史只认一圈的_几圈和一直巡逻的不算(台):  # noqa: F811
    import json

    from test_site_adhoc import 毫秒
    t = 台
    for i, (loops, dur) in enumerate(((0, 7200), (3, 1800), (1, 600))):
        t0 = 毫秒(10 + i, 0)
        wire = {**任务定义(), "policy": {"loops": loops}}
        with t.db.tx() as c:
            c.execute("INSERT INTO commands(command_id, task_id, robot_id, kind, payload, "
                      "issued_by, issued_at) VALUES (?,?,?,?,?,?,?)",
                      (f"c{i}", f"t{i}", "A", "patrol", json.dumps({"mission": wire}), "g", t0))
            c.execute("INSERT INTO events(robot_id, boot_id, seq, event_id, kind, data, stamp, "
                      "received_at) VALUES (?,?,?,?,?,?,?,?)",
                      ("A", "b", i, f"e{i}", "task_done", json.dumps({"task_id": f"t{i}"}),
                       t0 + dur * 1000, t0 + dur * 1000))
    assert t.desk.history_s("A", "loop") == 600


def test_外审1_先看会怎样写实际跑几圈_手机凭它知道站点认圈数(台):  # noqa: F811
    t = 台
    assert t.desk.plan("A", with_loops(任务定义(), 3, return_pct=25.0, caps=NEW))["loops"] == 3
    assert t.desk.plan("A", 任务定义())["loops"] == 1


async def test_外审2_一直巡逻已经在回家_日程到点等它_不白白记成跑过_到家以后照派(tmp_path):
    """外审 W76-2 #1:返航途中机器人回忙(有效优先级 50),以前这一轮记 started → dispatch_failed,
    同一窗口里不再补。机器人报了 ``task_returning`` 就按忙等它。"""
    import json

    from test_site_dispatcher import 台子
    from test_site_schedule import 打包, 毫秒
    from test_site_schedule_alerts import _拍

    from nexwar_site.catalog import import_bundle
    from nexwar_site.priorities import FOREVER_PATROL, FOREVER_PREFIX
    from nexwar_site.scheduler import SiteScheduler
    t = 台子(tmp_path)
    t.clock.ms = 毫秒(21, 50)
    t.dog.inject_battery(100.0)
    await t.start()
    try:
        import_bundle(t.db, 打包(tmp_path, 1), imported_by="alice", now_ms=t.clock())
        t.sched = SiteScheduler(t.db, t.site, now_ms=t.clock, on_outcome=lambda *a: None)
        await t.run(2)
        tid = f"{FOREVER_PREFIX}x2"
        w = with_loops(任务定义(), LOOPS_FOREVER, return_pct=25.0, caps=NEW)
        r = await t.send(t.site.patrol("A", w, issued_by="gina", priority=FOREVER_PATROL,
                                       task_id=tid))
        assert r["ack"]["result"] == "accepted", r
        await t.run(20)
        with t.db.tx() as c:
            c.execute("INSERT INTO events(robot_id, boot_id, seq, event_id, kind, data, stamp, "
                      "received_at) VALUES (?,?,?,?,?,?,?,?)",
                      ("A", "ret", 1, "ret-1", "task_returning",
                       json.dumps({"task_id": tid, "reason": "电量低"}), t.clock(), t.clock()))
        t.clock.ms = 毫秒(22, 0, 30)
        await t.run(2)
        await _拍(t)
        assert [x["outcome"] for x in t.sched.runs("nightly")] == ["busy"], t.sched.runs()
        assert t.site.busy("A") == tid, "没去抢回家的那一趟"
        await t.send(t.site.abort("A", tid, issued_by="gina"))   # 到家了(这里用撤代替)
        await t.run(30)
        assert t.site.busy("A") is None
        t.clock.ms = 毫秒(22, 2)
        await _拍(t)
        assert "started" in [x["outcome"] for x in t.sched.runs("nightly")], t.sched.runs()
    finally:
        await t.close()
