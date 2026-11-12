"""W76 循环巡逻(用户 11-12):``loops = 0`` 一直跑,电量到返航线回原点 —— 这一趟正常结束。"""

from __future__ import annotations

from nexwar_agent.engine.machine import RunState
from nexwar_agent.engine.mission import LOOPS_FOREVER, Mission, MissionWaypoint, Policy
from nexwar_patrol.backends.base import BatteryEvent, NavStatusEvent
from nexwar_patrol.protocol.nav_types import NavStatus, Pose

from .conftest import _HOME, until


def _两点(**pol) -> Mission:
    wps = tuple(MissionWaypoint(name=n, pose=Pose.from_xy_yaw(x, y))
                for n, x, y in (("A", 3.0, 0.0), ("B", 3.0, 3.0)))
    pol.setdefault("battery_abort_pct", 15.0)
    return Mission(mission="L", map_id="map_test", waypoints=wps,
                   policy=Policy(loops=LOOPS_FOREVER, **pol))


async def test_一直跑_一圈接一圈_电量到线回原点_算跑完_记下跑了几圈(make_engine, nav, device):
    engine = make_engine()
    await engine.start(_两点(), home=_HOME)
    await until(lambda: len(nav.goto_calls) >= 7)          # 三圈多,还在跑
    assert engine.snapshot.state is RunState.RUNNING
    assert engine.laps >= 3
    device.emit(BatteryEvent(percent=20.0))                 # 返航线 25
    assert await engine.wait_done(timeout_s=5.0) is RunState.DONE
    assert engine.returned and "电量" in engine.returned
    assert engine.laps >= 3
    await engine.aclose()


async def test_一直跑_一整圈一个点都没到_停下不空转(make_engine, nav, device):
    nav.on_goto = [NavStatusEvent(NavStatus.FAILED)]
    engine = make_engine()
    await engine.start(_两点(on_waypoint_failed="skip"), home=_HOME)
    assert await engine.wait_done(timeout_s=5.0) is RunState.ABORTED
    assert "一整圈" in engine.snapshot.reason, engine.snapshot.reason
    assert len(nav.goto_calls) == 2, "第一圈两个点都没到就停,不再跑第二圈"
    await engine.aclose()


async def test_有限圈数照旧_跑完就完(make_engine, nav, device):
    engine = make_engine()
    m = _两点()
    m = Mission(mission=m.mission, map_id=m.map_id, waypoints=m.waypoints,
                policy=Policy(loops=2, battery_abort_pct=15.0))
    await engine.start(m, home=_HOME)
    assert await engine.wait_done(timeout_s=5.0) is RunState.DONE
    assert len(nav.goto_calls) == 4 and engine.laps == 2
    await engine.aclose()
