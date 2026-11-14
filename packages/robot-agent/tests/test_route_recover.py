"""用户 11-15(最高优先):巡逻尽最大可能把整趟走完。路线检查说「这儿过不去」不直接放弃这个点:

- 出发前就卡在一处窄的 → 本趟把那一处临时标成「绕开」,重新要路线、重新查一次;过了就走绕开的那条,
  不过撤掉标记、照旧拒(引擎跳过这个点、去下一个)。
- 半路重查也过不去(钻进窄处、原地转不过来)→ 沿刚走过的路倒退 :data:`RETREAT_ROUTE_M`,退出来再查;
  还不过再试绕开那一处;都不行才放弃这个点。
"""
from __future__ import annotations

import math

import pytest
from test_nav2_backend import _L台, _台, 会规划的转接

from nexwar_agent.bridges.nav2_nav import RETREAT_ROUTE_M, _corner_poses
from nexwar_patrol.protocol.nav_types import NavStatus, Pose


def _隔墙():
    """x = 6 一道墙(0.2 厚),两个口子:y 3.65–4.35(0.7 m,太窄)、y 6.0–7.5(1.5 m,宽)。"""
    return [(5.9, 0.1, 6.1, 3.65), (5.9, 4.35, 6.1, 6.0), (5.9, 7.5, 6.1, 7.9)]


def _直穿窄口(sx, sy, gx, gy, gyaw):
    n = max(1, int(math.dist((sx, sy), (gx, gy)) / 0.025))
    return [[sx + (gx - sx) * i / n, sy + (gy - sy) * i / n, gyaw] for i in range(n + 1)]


def _绕宽口(sx, sy, gx, gy, gyaw):
    return [list(p) for p in _corner_poses([(sx, sy), (3.0, 6.75), (9.0, 6.75), (gx, gy)],
                                           0.0, gyaw)]


class 会绕路的转接(会规划的转接):
    """规划:最近一次送图里窄口 (6, 4) 被标成绕开 → 走宽口;否则直穿窄口。"""

    def __init__(self, always_narrow=False):
        super().__init__()
        self.always_narrow = always_narrow

    def send(self, m):
        if m["type"] == "plan":
            maps = self.kinds("map")
            nogo = maps[-1]["nogo"] if maps else []
            avoided = any(math.dist((sum(p[0] for p in poly) / len(poly),
                                     sum(p[1] for p in poly) / len(poly)), (6.0, 4.0)) < 0.8
                          for poly in nogo)
            sx, sy, _ = m["start"]
            gx, gy, gyaw = m["goal"]
            poses = (_绕宽口 if avoided and not self.always_narrow else _直穿窄口)(sx, sy, gx, gy,
                                                                                gyaw)
            self.plan_results[m["req_id"]] = {"type": "plan_result", "req_id": m["req_id"],
                                              "ok": True, "poses": poses}
            self.sent.append(m)
            return True
        return super().send(m)


async def test_出发前卡在窄口_标成绕开重新查_走宽口那条(tmp_path):
    link = 会绕路的转接()
    t = _台(tmp_path, link, walls=_隔墙())
    await t.start(1.5, 4.0)
    link.here = (1.5, 4.0)
    await t.nav.goto(Pose.from_xy_yaw(9.0, 4.0))
    assert len(link.kinds("plan")) == 2, "先查直穿的、拒了再查绕开的"
    [g] = link.kinds("goal")
    assert (g["x"], g["y"]) == (9.0, 4.0)
    nogo = link.kinds("map")[-1]["nogo"]
    assert len(nogo) == 1, "交给 Nav2 时那一处还标着绕开(Nav2 自己规划也绕)"
    kinds = [k for k, _ in t.events]
    assert "route_rejected" in kinds and "route_detour" in kinds
    assert t.nav._status is not NavStatus.FAILED


async def test_绕开也过不去_撤掉标记_照旧拒(tmp_path):
    from nexwar_patrol.backends.base import NavRequestError
    link = 会绕路的转接(always_narrow=True)
    t = _台(tmp_path, link, walls=_隔墙())
    await t.start(1.5, 4.0)
    link.here = (1.5, 4.0)
    with pytest.raises(NavRequestError) as e:
        await t.nav.goto(Pose.from_xy_yaw(9.0, 4.0))
    assert e.value.code == "route_too_narrow" and e.value.final
    assert len(link.kinds("plan")) == 2 and not link.kinds("goal")
    assert link.kinds("map")[-1]["nogo"] == [] and not t.nav._avoid, "临时标记撤掉了"
    assert t.nav._status is NavStatus.STANDBY and not t.nav._planning


async def test_卡的地方离终点太近_不标绕开_直接拒(tmp_path):
    from nexwar_patrol.backends.base import NavRequestError
    link = 会绕路的转接()
    t = _台(tmp_path, link, walls=_隔墙())
    await t.start(1.5, 4.0)
    link.here = (1.5, 4.0)
    with pytest.raises(NavRequestError):
        await t.nav.goto(Pose.from_xy_yaw(6.6, 4.0))      # 终点就在窄口后面
    assert len(link.kinds("plan")) == 1, "不能把终点圈进绕开的范围:不再查"


async def _走一段(t, link, gid, metres, mps=0.5):
    for _ in range(int(metres / mps / 0.1)):
        link.now += 0.1
        link.cmd = (link.now, gid, mps, 0.0, 0.0)
        await t.一拍()
    link.cmd = None


async def test_半路重查也过不去_沿来路倒退出来_退完再查_过了接着走(tmp_path):
    t, link = await _L台(tmp_path)
    g = link.kinds("goal")[-1]
    await _走一段(t, link, g["goal_id"], 2.0)
    x_in = t.r.x
    assert x_in > 3.0
    link.answer = {"ok": True, "poses": _直穿窄口(x_in, 4.0, 5.4, 6.5, math.pi / 2)}  # 穿墙:拒
    for _ in range(2):                                     # MPPI、RPP 都放弃
        g = link.kinds("goal")[-1]
        link.goal_states.append({"type": "goal_state", "goal_id": g["goal_id"],
                                 "state": "aborted", "reason": "x"})
        await t.跑(0.3)
    assert t.nav._back is not None and t.nav._back.get("after") == "recheck", "拒了:先退出来"
    assert NavStatus.FAILED not in t.status
    plans = len(link.kinds("plan"))
    link.answer = None                                     # 退出来以后再查:给一条过得去的
    from test_nav2_backend import _L路线
    link.answer = {"ok": True, "poses": _L路线()}
    await t.跑(20.0)
    assert t.nav._back is None
    assert x_in - t.r.x >= 0.8, ("沿来路退了", x_in, t.r.x)
    assert len(link.kinds("plan")) == plans + 1, "退完从那儿重新查"
    g2 = link.kinds("goal")[-1]
    assert g2["goal_id"] != g["goal_id"] and g2.get("path")
    assert NavStatus.FAILED not in t.status


async def test_倒退最多退这么远(tmp_path):
    assert 2.0 <= RETREAT_ROUTE_M <= 3.0, "用户 11-15:2–3 m"
