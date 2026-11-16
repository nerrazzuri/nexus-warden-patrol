"""外审 11-14(协议 6):``goal`` 可带 ``path`` —— 路线检查靠局部搜索放行、已逐个位姿查过的那条路,
转接节点交给控制器照着走(``FollowPath``);``controller`` 指定哪个控制器跟(MPPI 跟不动换 RPP)。"""
from __future__ import annotations

import json

import pytest

from nexwar_contract import navbridge as nb
from nexwar_contract.errors import ContractError


def _goal(**kw):
    return {"type": "goal", "goal_id": 1, "x": 1.0, "y": 2.0, "yaw": 0.0, **kw}


def test_协议号升到6():
    assert nb.PROTO == 7


def test_目标带路_每个点三个数_有上限():
    nb.check(_goal(path=[[0.0, 0.0, 0.0], [0.05, 0.0, 0.0]]))
    nb.check(_goal(path=[[0.0, 0.0, 0.0], [0.05, 0.0, 0.0]], controller="RPP"))
    nb.check(_goal(path=[[0.0, 0.0, 0.0], [0.05, 0.0, 0.0]], controller="FollowTight"))
    for bad in ([[0.0, 0.0]], [[0.0, 0.0, 0.0]], "x",
                [[0.0, 0.0, 0.0]] * (nb.MAX_GOAL_PATH + 1)):
        with pytest.raises(ContractError):
            nb.check(_goal(path=bad))


def test_控制器只能是配着的两个():
    with pytest.raises(ContractError):
        nb.check(_goal(path=[[0.0, 0.0, 0.0], [0.05, 0.0, 0.0]], controller="DWB"))
    with pytest.raises(ContractError):
        nb.check(_goal(controller="RPP"))                  # 没有路不能指定控制器


def test_带路又带途经点_不行():
    with pytest.raises(ContractError):
        nb.check(_goal(path=[[0.0, 0.0, 0.0], [0.05, 0.0, 0.0]], via=[[0.5, 0.0]]))


def test_最长的路也在一行里():
    import json
    m = _goal(path=[[123.456, -98.765, -3.1416]] * nb.MAX_GOAL_PATH)
    assert len(json.dumps(m, separators=(",", ":"))) + 1 <= nb.MAX_LINE


def test_仿真11_16_地图带clear_协议收():
    """11-05 起代理的地图报文带 clear(机器人站在地图残影上时临时擦掉机身底下);协议没加,
    真转接节点一直丢掉地图、Nav2 从没就绪。"""
    m = {"type": "map", "req": 1, "map_id": "m", "map_version": "", "dir": "/x", "nogo": [],
         "speed": [], "clear": [[1.0, 2.0, 0.5, 0.515, 0.29]]}
    assert nb.parse(json.dumps(m).encode(), allowed=nb.FROM_AGENT)["clear"] == m["clear"]


@pytest.mark.parametrize("bad", [[[1.0, 2.0]], "x", [[1.0, 2.0, 0.5, 0.5, "w"]],
                                 [[1.0, 2.0, 0.5, 0.5, 0.3]] * 65])
def test_仿真11_16_clear写错就拒(bad):
    m = {"type": "map", "req": 1, "map_id": "m", "map_version": "", "dir": "/x", "clear": bad}
    with pytest.raises(ContractError):
        nb.parse(json.dumps(m).encode(), allowed=nb.FROM_AGENT)
