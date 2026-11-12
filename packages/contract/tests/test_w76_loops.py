"""W76 循环巡逻(用户 11-12):``policy.loops`` 0 = 一直跑,直到电量到线回去补能。"""

from __future__ import annotations

import pytest

from nexwar_contract.mission import LOOPS_FOREVER, MissionError, parse_mission

_WP = {"name": "P1", "pose": {"position": {"x": 1.0, "y": 2.0, "z": 0.0},
                              "orientation": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0}}}


_WP2 = {"name": "P2", "pose": {"position": {"x": 3.0, "y": 2.0, "z": 0.0},
                               "orientation": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0}}}


def _raw(loops, **pol) -> dict:
    return {"mission": "night", "map_id": "floor1", "waypoints": [dict(_WP), dict(_WP2)],
            "policy": {"loops": loops, **pol}}


def test_外审1_一直巡逻配低电接着走_拒收_不然跑到没电停在外面():
    with pytest.raises(MissionError, match="on_battery_low"):
        parse_mission(_raw(0, on_battery_low="continue"))
    assert parse_mission(_raw(2, on_battery_low="continue")).policy.loops == 2


def test_外审1_一直巡逻至少两个点_一个点会原地空转():
    one = {**_raw(0), "waypoints": [dict(_WP)]}
    with pytest.raises(MissionError, match="两个点"):
        parse_mission(one)


def test_圈数0是一直跑_能解析能写回():
    assert LOOPS_FOREVER == 0
    m = parse_mission(_raw(0))
    assert m.policy.loops == LOOPS_FOREVER and m.policy.forever
    assert parse_mission(m.to_wire()) == m


@pytest.mark.parametrize("n", [1, 3, 99])
def test_有限圈数照旧(n):
    m = parse_mission(_raw(n))
    assert m.policy.loops == n and not m.policy.forever


@pytest.mark.parametrize("bad", [-1, True, False, 1.5, "3", None])
def test_负数_布尔_小数_字符串照旧拒(bad):
    with pytest.raises(MissionError):
        parse_mission(_raw(bad))
