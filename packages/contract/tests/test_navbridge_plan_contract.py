"""导航 V1 第 2 节:Route Validator 拿路线的 plan / plan_result(协议 5)。

跟 goal → path → cmd → goal_state 分开:``req_id`` 自己一套号;路线带 Smac 原始朝向(倒车段切线 ≠
机头朝向),不抽稀;太长回 ``too_long``,不截断。"""
from __future__ import annotations

import pytest

from nexwar_contract import navbridge as nb
from nexwar_contract.errors import ContractError


def test_协议号升到5():
    assert nb.PROTO == 6


def test_plan只许代理发_plan_result只许转接节点发():
    assert "plan" in nb.FROM_AGENT and "plan" not in nb.FROM_BRIDGE
    assert "plan_result" in nb.FROM_BRIDGE and "plan_result" not in nb.FROM_AGENT


def test_plan_起点可选_目标三个数():
    nb.check({"type": "plan", "req_id": 1, "goal": [1.0, 2.0, 0.5]})
    nb.check({"type": "plan", "req_id": 2, "goal": [1.0, 2.0, 0.5], "start": [0.0, 0.0, 0.0]})
    with pytest.raises(ContractError):
        nb.check({"type": "plan", "req_id": 1, "goal": [1.0, 2.0]})
    with pytest.raises(ContractError):
        nb.check({"type": "plan", "req_id": 0, "goal": [1.0, 2.0, 0.0]})


def test_plan_result_位姿带朝向_最多5000个_不抽稀():
    poses = [[i * 0.025, 0.0, 3.14159] for i in range(nb.MAX_PLAN_POSES)]
    line = nb.encode({"type": "plan_result", "req_id": 7, "ok": True, "poses": poses})
    got = nb.parse(line, allowed=nb.FROM_BRIDGE)
    assert len(got["poses"]) == nb.MAX_PLAN_POSES and got["poses"][1] == [0.025, 0.0, 3.14159]
    assert nb.MAX_PLAN_POSES >= 5000
    with pytest.raises(ContractError):
        nb.check({"type": "plan_result", "req_id": 7, "ok": True,
                  "poses": poses + [[0.0, 0.0, 0.0]]})
    with pytest.raises(ContractError):
        nb.check({"type": "plan_result", "req_id": 7, "ok": True, "poses": [[0.0, 0.0]]})


def test_plan_result_失败带原因_不带位姿():
    nb.check({"type": "plan_result", "req_id": 3, "ok": False, "poses": [], "reason": "too_long"})
    with pytest.raises(ContractError):
        nb.check({"type": "plan_result", "req_id": 3, "ok": "no", "poses": []})


def test_显示用的path还是抽稀的二维点():
    assert nb.MAX_PATH_PTS == 256
    with pytest.raises(ContractError):
        nb.check({"type": "path", "goal_id": 1, "pts": [[0.0, 0.0, 0.0]]})


def _map(**kw):
    return {"type": "map", "req": 1, "map_id": "m", "map_version": "", "dir": "/x", **kw}


def test_11_16_地图带clear_协议收():
    """代理(72f9afa3 起)的地图报文总带 clear(机器人站在地图残影上时临时擦掉机身底下的
    [x, y, yaw, 半长, 半宽]);协议没加,真转接节点按协议丢掉整条地图,Nav2 等不到地图。"""
    import json
    m = _map(nogo=[], speed=[], clear=[[1.0, 2.0, 0.5, 0.515, 0.29]])
    assert nb.parse(json.dumps(m).encode(), allowed=nb.FROM_AGENT)["clear"] == m["clear"]
    assert nb.parse(json.dumps(_map(clear=[])).encode(), allowed=nb.FROM_AGENT)["clear"] == []


@pytest.mark.parametrize("bad", [[[1.0, 2.0]], "x", [[1.0, 2.0, 0.5, 0.5, "w"]],
                                 [[1.0, 2.0, 0.5, 0.5, float("nan")]], [[1.0, 2.0, 0.5, 0.0, 0.3]],
                                 [[1.0, 2.0, 0.5, 9.0, 0.3]],
                                 [[1.0, 2.0, 0.5, 0.5, 0.3]] * 65])
def test_11_16_clear写错就拒(bad):
    import json
    with pytest.raises(ContractError):
        nb.parse(json.dumps(_map(clear=bad)).encode(), allowed=nb.FROM_AGENT)
