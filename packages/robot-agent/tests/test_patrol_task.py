"""``patrol``(W00c2a):整趟 Mission 在引擎上跑;每个航点一条 ``patrol_waypoint`` 事件;
终态映射同 goto。夹具与驱动同 ``test_engine_goto.py``。"""

from __future__ import annotations

import asyncio

import pytest

from nexwar_adapter_sim.robot import SimRobot
from nexwar_agent.assembly import build_engine
from nexwar_agent.events import EventBook
from nexwar_agent.tasks.patrol import PatrolTask
from nexwar_contract.geometry import Pose
from nexwar_contract.messages import TaskState
from nexwar_contract.mission import Action, Mission, MissionWaypoint, Policy


class 钟:
    def __init__(self) -> None:
        self.ms = 1_700_000_000_000
        self.mono = 100.0

    def __call__(self) -> int:
        return self.ms

    def advance(self, dt_s: float) -> None:
        self.ms += int(round(dt_s * 1000))
        self.mono += dt_s


@pytest.fixture
async def 台子(tmp_path):
    c = 钟()
    r = SimRobot(now_ms=c, max_vx=1.0, max_wz=1.5, stop_latency_s=0.2)
    await r.connect()
    await r.acquire_control()
    parts = build_engine(r, runs_root=tmp_path / "runs", now_ms=c, monotonic=lambda: c.mono,
                         map_id="m", home=Pose.from_xy_yaw(0.0, 0.0))
    book = EventBook(tmp_path / "ev.jsonl", boot_id="b1", now_ms=c)
    yield c, r, parts, book
    await parts.engine.aclose()


async def _跑(c, r, parts, task, n, dt=0.1):
    for _ in range(n):
        await task.step(dt)
        await parts.nav.step(dt)
        await parts.device.step(dt)
        r.tick(dt)
        c.advance(dt)
        for _ in range(4):
            await asyncio.sleep(0)
        if task.done:
            return


def _任务(*pts, policy=None, actions=()):
    return Mission(mission="loop", map_id="m", policy=policy or Policy(),
                   waypoints=tuple(MissionWaypoint(name=f"p{i}", pose=Pose.from_xy_yaw(x, y),
                                                   actions=actions)
                                   for i, (x, y) in enumerate(pts)))


def _点事件(book):
    return [e.data for e in book.pending() if e.kind == "patrol_waypoint"]


async def test_三个点走完_每点一条事件_done(台子):
    c, r, parts, book = 台子
    t = PatrolTask(task_id="t1", mission=_任务((1.0, 0.0), (1.0, 1.0), (0.0, 1.0),
                                              actions=(Action(type="dwell", seconds=0.5),)),
                   parts=parts, events=book, now_ms=c)
    await t.start()
    await _跑(c, r, parts, t, 1500)
    assert t.state is TaskState.DONE, (t.state, t.detail)
    got = _点事件(book)
    assert [(g["index"], g["name"], g["ok"]) for g in got] == [
        (0, "p0", True), (1, "p1", True), (2, "p2", True)]
    assert {g["total"] for g in got} == {3}            # W69:手机到点提醒说「第几个 / 共几个」
    o = await r.odometry()
    assert abs(o.x) < 0.2 and abs(o.y - 1.0) < 0.2


async def test_中途abort_aborted_停下(台子):
    c, r, parts, book = 台子
    t = PatrolTask(task_id="t1", mission=_任务((6.0, 0.0), (6.0, 6.0)), parts=parts,
                   events=book, now_ms=c)
    await t.start()
    await _跑(c, r, parts, t, 30)
    await t.abort("operator")
    await _跑(c, r, parts, t, 60)
    assert t.state is TaskState.ABORTED and await r.stopped()


async def test_到不了的点被跳过_完成_带跳过几个点并列出点名(台子, monkeypatch, tmp_path):
    """引擎的航点超时按真实时间算,测试的假钟推不动它;改让 HAL 对去 p1 的速度命令一律
    拒收(导航 Failed),引擎按 retry_then_skip 跳过 p1、接着走 p2。"""
    from nexwar_contract.hal import VelocityResult
    c, r, parts, book = 台子
    real = r.set_velocity

    async def 拒去远点(cmd):
        tgt = parts.nav._target
        if tgt is not None and tgt.position.x > 10.0:
            return VelocityResult(0.0, 0.0, clamped=False, rejected=True, reason="blocked")
        return await real(cmd)

    monkeypatch.setattr(r, "set_velocity", 拒去远点)
    pol = Policy(waypoint_retry=0)
    t = PatrolTask(task_id="t1", mission=_任务((0.5, 0.0), (40.0, 0.0), (0.5, 0.5), policy=pol),
                   parts=parts, events=book, now_ms=c)
    await t.start()
    await _跑(c, r, parts, t, 2000)
    # W71(11-03 商场 Patrol1 15/16 站点报「未完成」):到了一部分的算完成、带上跳过几个点
    assert t.state is TaskState.DONE, (t.state, t.detail)
    assert t.detail["skipped"] == 1 and t.detail["skipped_names"] == ["p1"]
    assert "p1" in t.detail["reason"] and "跳过 1 个点" in t.detail["reason"]
    assert [g["ok"] for g in _点事件(book)] == [True, False, True]
    # 导航 V1 第 5 节:没到的点带原因码(HAL 拒速度 = 机器人不接受命令),到了的不带
    assert [g.get("code") for g in _点事件(book)] == [None, "robot_not_ready", None]
    assert t.detail["code"] == "robot_not_ready"
    import json
    [m] = list((tmp_path / "runs").rglob("manifest.json"))
    assert json.loads(m.read_text())["summary"]["result"] == "partial"


async def test_W71_一个点都没到_还是failed(台子, monkeypatch):
    from nexwar_contract.hal import VelocityResult
    c, r, parts, book = 台子

    async def 全拒(cmd):
        return VelocityResult(0.0, 0.0, clamped=False, rejected=True, reason="blocked")
    monkeypatch.setattr(r, "set_velocity", 全拒)
    t = PatrolTask(task_id="t1", mission=_任务((20.0, 0.0), (40.0, 0.0),
                                               policy=Policy(waypoint_retry=0)),
                   parts=parts, events=book, now_ms=c)
    await t.start()
    await _跑(c, r, parts, t, 2000)
    assert t.state is TaskState.FAILED, (t.state, t.detail)
    assert "2 个航点未到达" in t.detail["reason"]
    assert t.detail["code"] == "robot_not_ready"


async def test_sim相机_带拍照动作的任务走得完_照片进归档(tmp_path):
    """任务包里常有拍照动作;sim 没有相机的话每个拍照点都失败,整趟必 failed。"""
    from nexwar_agent.bridges.sim_media import PLACEHOLDER_JPEG, sim_media
    c = 钟()
    r = SimRobot(now_ms=c, max_vx=1.0, max_wz=1.5, stop_latency_s=0.2)
    await r.connect()
    await r.acquire_control()
    parts = build_engine(r, runs_root=tmp_path / "runs", now_ms=c, monotonic=lambda: c.mono,
                         map_id="m", home=Pose.from_xy_yaw(0.0, 0.0), media=sim_media(c))
    book = EventBook(tmp_path / "ev.jsonl", boot_id="b1", now_ms=c)
    t = PatrolTask(task_id="t1", mission=_任务((1.0, 0.0), actions=(
        Action(type="photo", camera="front"),)), parts=parts, events=book, now_ms=c)
    await t.start()
    await _跑(c, r, parts, t, 500)
    assert t.state is TaskState.DONE, (t.state, t.detail)
    shots = list((tmp_path / "runs").rglob("*.jpg"))
    assert shots and shots[0].read_bytes() == PLACEHOLDER_JPEG
    await parts.engine.aclose()


async def test_工单20_点没到_证据清单里写结果failed_站点才不当成跑完了(台子, tmp_path, monkeypatch):
    """2026-10-28 回待命点(一个点的巡检):两次 goal_blocked、点跳过,清单 ``summary`` 只写了引擎的
    ``state: done``(「这趟跑到头了」),站点读的 ``result`` 没写 —— 现场看着像回去了。"""
    import json

    from nexwar_patrol.backends.base import NavRequestError
    c, r, parts, book = 台子

    async def 拒(pose):
        raise NavRequestError("goto", "规划失败(goal_blocked):终点在障碍、禁行区里或贴得太近")
    monkeypatch.setattr(parts.nav, "goto", 拒)
    t = PatrolTask(task_id="standby-1", mission=_任务((2.0, 0.0)), parts=parts, events=book,
                   now_ms=c)
    await t.start()
    await _跑(c, r, parts, t, 300)
    assert t.state is TaskState.FAILED, (t.state, t.detail)
    [m] = list((tmp_path / "runs").rglob("manifest.json"))
    s = json.loads(m.read_text())["summary"]
    assert s["result"] == "failed" and s["succeeded"] == 0, s


async def test_点都到了_清单结果done(台子, tmp_path):
    import json
    c, r, parts, book = 台子
    t = PatrolTask(task_id="t1", mission=_任务((0.5, 0.0)), parts=parts, events=book, now_ms=c)
    await t.start()
    await _跑(c, r, parts, t, 600)
    assert t.state is TaskState.DONE
    [m] = list((tmp_path / "runs").rglob("manifest.json"))
    assert json.loads(m.read_text())["summary"]["result"] == "done"


async def test_W76_一直巡逻_电量到线回原点_算完成_写跑了几圈(台子):
    from nexwar_contract.mission import LOOPS_FOREVER
    c, r, parts, book = 台子
    t = PatrolTask(task_id="t1", mission=_任务((1.0, 0.0), (1.0, 1.0),
                                               policy=Policy(loops=LOOPS_FOREVER)),
                   parts=parts, events=book, now_ms=c)
    await t.start()
    for _ in range(200):
        await _跑(c, r, parts, t, 50)
        if parts.engine.laps >= 2:
            break
    assert parts.engine.laps >= 2 and not t.done
    r.inject_battery(20.0)                                   # 返航线 25
    await _跑(c, r, parts, t, 3000)
    assert t.state is TaskState.DONE, (t.state, t.detail)
    assert t.detail["laps"] >= 2 and t.detail["ended"] == "battery"
    assert "电量" in t.detail["reason"] and "圈" in t.detail["reason"]
    laps = [e["lap"] for e in _点事件(book)]
    assert laps[:4] == [1, 1, 2, 2], "点位事件带第几圈"


async def test_W76_有限圈半路电量到线_照旧失败_写跑了几圈(台子):
    c, r, parts, book = 台子
    t = PatrolTask(task_id="t1", mission=_任务((1.0, 0.0), (1.0, 1.0), policy=Policy(loops=50)),
                   parts=parts, events=book, now_ms=c)
    await t.start()
    for _ in range(200):
        await _跑(c, r, parts, t, 50)
        if parts.engine.laps >= 1:
            break
    r.inject_battery(20.0)
    await _跑(c, r, parts, t, 3000)
    assert t.state is TaskState.FAILED, (t.state, t.detail)
    assert "半路返航" in t.detail["reason"] and t.detail["laps"] >= 1
    assert t.detail["ended"] == "battery"


async def test_W76_设了两圈跑完_完成_写圈数跑完_跟一直巡逻分得开(台子):
    c, r, parts, book = 台子
    t = PatrolTask(task_id="t1", mission=_任务((1.0, 0.0), (1.0, 1.0), policy=Policy(loops=2)),
                   parts=parts, events=book, now_ms=c)
    await t.start()
    await _跑(c, r, parts, t, 6000)
    assert t.state is TaskState.DONE, (t.state, t.detail)
    assert t.detail["laps"] == 2 and t.detail["ended"] == "loops"


def test_W76_能力里报一直巡逻():
    from nexwar_agent.status import compose_capabilities
    r = SimRobot(now_ms=lambda: 0, max_vx=1.0)
    caps = compose_capabilities(robot_id="r", adapter_id="sim", hal_caps=r.hal_capabilities(),
                                loaded_map=("m", "1"), nav_path="builtin", autonomy="full")
    assert caps.tasks["patrol"]["loops_forever"] is True


async def test_W76_一直巡逻低电返航时_有效优先级抬到日程之上_有限圈不抬(台子):
    from nexwar_agent.tasks.engine_goto import HOMING_GUARD_PRIORITY
    from nexwar_contract.mission import LOOPS_FOREVER
    c, r, parts, book = 台子
    t = PatrolTask(task_id="t1", mission=_任务((1.0, 0.0), (1.0, 1.0),
                                               policy=Policy(loops=LOOPS_FOREVER)),
                   parts=parts, events=book, now_ms=c, priority=5)
    await t.start()
    await _跑(c, r, parts, t, 30)
    assert t.effective_priority == 5
    r.inject_battery(20.0)
    for _ in range(200):
        await _跑(c, r, parts, t, 1)
        if parts.engine.state.value == "RETURNING":
            break
    assert parts.engine.state.value == "RETURNING"
    assert t.effective_priority == HOMING_GUARD_PRIORITY > 49
    await _跑(c, r, parts, t, 1)
    # 外审 W76-2 #1:告诉站点「这一趟在回家了」(一趟一条),站点日程等它到家、不拿这一轮去撞忙
    back = [e.data for e in book.pending() if e.kind == "task_returning"]
    assert len(back) == 1 and back[0]["task_id"] == "t1" and back[0]["reason"]
    # 外审 W76-2 #2:返航途中暂停了、引擎落了终态还在等停车确认 —— 都还在回家,照样护着
    await parts.engine.pause()
    await _跑(c, r, parts, t, 1)
    assert parts.engine.state.value == "PAUSED"
    assert t.effective_priority == HOMING_GUARD_PRIORITY
    await parts.engine.resume()
    for _ in range(600):
        await _跑(c, r, parts, t, 1)
        if parts.engine.state.value == "DONE" or t.done:
            break
    assert t.done or t.effective_priority == HOMING_GUARD_PRIORITY


async def test_minor4_一直巡逻两个近点_快照只留最近一段_编号圈数连着(台子, monkeypatch,
                                                                    tmp_path):
    """W76 外审 minor:两个点只隔 5 cm,原地快速循环,每到一个点都把全部结果整份重写进
    state.json。一直巡逻只留最近一段(累计数另记),点位事件的编号、第几圈不受影响。"""
    import json

    from nexwar_agent.engine import machine
    from nexwar_contract.mission import LOOPS_FOREVER
    monkeypatch.setattr(machine, "FOREVER_KEEP_RESULTS", 6)
    c, r, parts, book = 台子
    t = PatrolTask(task_id="t1", mission=_任务((1.0, 0.0), (1.0, 0.05),
                                               policy=Policy(loops=LOOPS_FOREVER)),
                   parts=parts, events=book, now_ms=c)
    await t.start()
    for _ in range(400):
        await _跑(c, r, parts, t, 50)
        if parts.engine.laps >= 8:
            break
    assert parts.engine.laps >= 8
    snap = parts.engine.snapshot
    assert len(snap.results) <= 6, len(snap.results)
    assert snap.results_from + len(snap.results) >= 16
    [st] = list((tmp_path / "runs").rglob("state.json"))
    assert len(json.loads(st.read_text())["results"]) <= 6
    evs = _点事件(book)
    assert [e["index"] for e in evs] == list(range(len(evs))), "点位编号连着,不因为丢了旧结果重来"
    assert [e["lap"] for e in evs] == [i // 2 + 1 for i in range(len(evs))]
    r.inject_battery(20.0)
    await _跑(c, r, parts, t, 3000)
    assert t.state is TaskState.DONE, (t.state, t.detail)
    [m] = list((tmp_path / "runs").rglob("manifest.json"))
    s = json.loads(m.read_text())["summary"]
    assert s["total"] == s["succeeded"] + s["failed"] >= 16, s
    assert len(s["results"]) <= 6 and s["results_from"] == s["total"] - len(s["results"])
