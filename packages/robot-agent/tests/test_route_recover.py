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


def test_倒退一拍_纯函数_真机和仿真共用():
    from nexwar_agent.bridges.nav2_nav import RETREAT_MPS, retreat_cmd
    path = [(1.6, 0.0), (1.2, 0.0), (0.8, 0.0)]           # 车头朝 +x,来路在身后
    vx, wz = retreat_cmd(2.0, 0.0, 0.0, path)
    assert vx == pytest.approx(-RETREAT_MPS) and abs(wz) < 1e-9
    assert path[0] == (1.2, 0.0), "前瞻以内的点弹掉了"
    vx, wz = retreat_cmd(2.0, 0.05, 0.0, [(1.2, 0.0), (0.8, 0.0)])
    assert vx < 0 and wz != 0.0, "偏了往回拉"
    assert retreat_cmd(0.85, 0.0, 0.0, [(0.8, 0.0)]) is None, "到了"
    vx, wz = retreat_cmd(0.0, 0.0, 0.0, [(1.0, 0.0)])
    assert vx == 0.0 and wz != 0.0, "那一点跑到前面去了:原地先转"


def test_交付配置里有跟紧路线的控制器_协议认它_代理照路走用它():
    """仿真 11-15 跟路试验 T2(MPPI 看路线朝向、加重贴路线、限速 0.4、收窄采样、缩短预测):
    偏离 95% 分位中位 0.079 m(原来 0.132),53 个里到 36(原来 33)。
    照查过的路走时用它,平常导航不变。"""
    from pathlib import Path

    import yaml

    from nexwar_agent.bridges.nav2_nav import PATH_CONTROLLER
    from nexwar_contract.navbridge import CONTROLLERS
    root = Path(__file__).resolve().parents[3]
    cs = yaml.safe_load((root / "deploy/nav2/params.yaml").read_text())["controller_server"][
        "ros__parameters"]
    assert PATH_CONTROLLER == "FollowTight" and PATH_CONTROLLER in CONTROLLERS
    assert PATH_CONTROLLER in cs["controller_plugins"]
    t, base = cs[PATH_CONTROLLER], cs["FollowPath"]
    assert t["plugin"] == base["plugin"] == "nav2_mppi_controller::MPPIController"
    assert t["vx_max"] <= 0.4 and t["vy_max"] == 0.0, "照路走:慢一点,不横移"
    assert t["PathAlignCritic"]["use_path_orientations"] is True
    assert "PreferForwardCritic" not in t["critics"], "路里有倒车那段"
    assert base["vx_max"] == 1.0, "平常导航不变"


# ---------------------------------------------------------------- 用户 11-16:倒着退出窄巷

def _死巷():
    """x < 3 是空房间;x 3–8 一条 1.2 m 宽的死巷(y 3.4–4.6),x = 8 堵死。"""
    return [(3.0, 0.1, 11.9, 3.4), (3.0, 4.6, 11.9, 7.9), (8.0, 3.4, 11.9, 4.6)]


async def _等空闲(t):
    for _ in range(100):
        await t.跑(0.1)
        if t.nav._status is NavStatus.STANDBY:
            return
    raise AssertionError(t.nav._status)


async def _进死巷(tmp_path, link, x=7.2):
    """从房间 (1.5, 4.0) 朝东走进死巷,到 (``x``, 4.0) 停下(Nav2 报到了)。"""
    t = _台(tmp_path, link, walls=_死巷())
    await t.start(1.5, 4.0)
    link.here = (1.5, 4.0)
    await t.nav.goto(Pose.from_xy_yaw(x, 4.0, 0.0))
    g = link.kinds("goal")[-1]
    await _走一段(t, link, g["goal_id"], x - 1.5)
    link.goal_states.append({"type": "goal_state", "goal_id": g["goal_id"],
                             "state": "succeeded", "reason": ""})
    await _等空闲(t)
    assert NavStatus.SUCCEED in t.status and t.r.x > x - 0.4
    link.here = (t.r.x, t.r.y)
    return t


async def test_死巷尽头_下一个点在身后_先倒着退出巷子_转得开了再查路线交给Nav2(tmp_path):
    from nexwar_agent.bridges.nav2_nav import BACKOUT_M
    link = 会规划的转接()
    t = await _进死巷(tmp_path, link)
    goals, plans = len(link.kinds("goal")), len(link.kinds("plan"))
    await t.nav.goto(Pose.from_xy_yaw(1.5, 4.0, math.pi))
    assert len(link.kinds("goal")) == goals, "巷子里转不开:先不交给 Nav2"
    assert t.nav._back is not None and t.nav._back.get("room"), "沿来路倒着退"
    await t.跑(45.0)
    assert t.nav._back is None
    assert t.r.x < 2.7, ("退到巷口外、原地转得开的地方", t.r.x)
    assert abs(math.remainder(t.r.yaw, 2 * math.pi)) < 0.5, "倒着退的:车头还朝里"
    assert len(link.kinds("plan")) >= plans + 2, "退完从那儿重新查路线"
    new = link.kinds("goal")[goals:]
    assert new and all((g["x"], g["y"]) == (1.5, 4.0) for g in new), "退出来才交给 Nav2"
    assert NavStatus.FAILED not in t.status and not t.crashed
    assert 6.0 <= BACKOUT_M <= 10.0


async def test_死巷里_下一个点还在前面_不倒退_照常交给Nav2(tmp_path):
    link = 会规划的转接()
    t = await _进死巷(tmp_path, link, x=5.0)
    goals = len(link.kinds("goal"))
    await t.nav.goto(Pose.from_xy_yaw(7.2, 4.0, 0.0))
    assert t.nav._back is None and len(link.kinds("goal")) == goals + 1


async def test_房间里_转得开_下一个点在身后_不倒退(tmp_path):
    link = 会规划的转接()
    t = _台(tmp_path, link, walls=_死巷())
    await t.start(1.0, 4.0)
    link.here = (1.0, 4.0)
    await t.nav.goto(Pose.from_xy_yaw(2.6, 4.0, 0.0))
    g = link.kinds("goal")[-1]
    await _走一段(t, link, g["goal_id"], 1.4)
    link.goal_states.append({"type": "goal_state", "goal_id": g["goal_id"],
                             "state": "succeeded", "reason": ""})
    await _等空闲(t)
    link.here = (t.r.x, t.r.y)
    goals = len(link.kinds("goal"))
    await t.nav.goto(Pose.from_xy_yaw(0.8, 4.0, math.pi))
    assert t.nav._back is None and len(link.kinds("goal")) == goals + 1
