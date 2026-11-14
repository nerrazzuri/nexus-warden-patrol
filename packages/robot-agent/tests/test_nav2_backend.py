"""W47 Nav2 后端(``docs/W47-导航换Nav2-设计.md``):契约、代理这头的转接服务端、
后端在仿真台子上的行为。
Nav2 本身不在这里起(那是 ``tools/navbench.py --backend nav2``);转接节点换成假的。"""

from __future__ import annotations

import asyncio
import json
import math
from collections import deque
from types import SimpleNamespace as NS

import pytest
from test_obstacle_avoid import 台子

from nexwar_agent.bridges.nav2_nav import Nav2NavBackend, _compose_map_odom
from nexwar_agent.navbridge import NavBridgeServer
from nexwar_agent.planning.planner import Planner
from nexwar_contract.errors import ContractError
from nexwar_contract.navbridge import FROM_AGENT, FROM_BRIDGE, encode, parse
from nexwar_patrol.protocol.nav_types import NavStatus, Pose

# ------------------------------------------------------------ 契约


@pytest.mark.parametrize("msg", [
    {"type": "tick", "t_ms": 5, "odom": [0, 0, 0], "vel": [0, 0, 0], "map_odom": None},
    {"type": "goal", "goal_id": 1, "x": 1.0, "y": 2.0, "yaw": 0.5},
    {"type": "goal", "goal_id": 1, "x": 1.0, "y": 2.0, "yaw": 0.5, "via": [[0.5, 0.5], [1.0, 0.5]]},
    {"type": "map", "req": 1, "map_id": "m", "map_version": "", "dir": "/x",
     "nogo": [[[0, 0], [1, 0], [1, 1]]], "speed": [{"poly": [[0, 0], [1, 0], [1, 1]], "mps": 0.3}]},
    {"type": "cmd", "t_ms": 3, "vx": 0.2, "vy": 0.0, "wz": -0.1},
    {"type": "cmd", "t_ms": 3, "vx": -0.15, "vy": 0.0, "wz": 0.0, "goal_id": 4, "src": "beh"},
    {"type": "goal_state", "goal_id": 2, "state": "aborted", "reason": "x"},
])
def test_契约_报文来回不变样(msg):
    assert parse(encode(msg)) == msg


@pytest.mark.parametrize("msg", [
    {"type": "tick", "t_ms": 5, "odom": [0, 0], "vel": [0, 0, 0]},
    {"type": "tick", "t_ms": -1, "odom": [0, 0, 0], "vel": [0, 0, 0]},
    {"type": "goal", "goal_id": 0, "x": 1, "y": 2, "yaw": 0},
    {"type": "goal", "goal_id": 1, "x": float("nan"), "y": 2, "yaw": 0},
    {"type": "goal", "goal_id": 1, "x": 1, "y": 2, "yaw": 0, "via": "x"},
    {"type": "goal", "goal_id": 1, "x": 1, "y": 2, "yaw": 0, "via": [[1, 2, 3]]},
    {"type": "goal", "goal_id": 1, "x": 1, "y": 2, "yaw": 0, "via": [[0, 0]] * 501},
    {"type": "goal", "goal_id": 1, "x": 1, "y": 2, "yaw": 0, "via": [[float("inf"), 0]]},
    {"type": "goal_state", "goal_id": 1, "state": "weird"},
    {"type": "cmd", "t_ms": 1, "vx": 0, "vy": 0, "wz": 0, "extra": 1},
    {"type": "cmd", "t_ms": 1, "vx": 0, "vy": 0, "wz": 0, "src": "smoother"},
    {"type": "nope"},
    {"type": "map", "req": 1, "map_id": "m", "map_version": "", "dir": "/x",
     "speed": [{"poly": [[0, 0], [1, 0], [1, 1]], "mps": -1}]},
])
def test_契约_写错就拒(msg):
    with pytest.raises(ContractError):
        encode(msg)


def test_契约_哪头只许发哪些():
    with pytest.raises(ContractError, match="不该收到"):
        parse(encode({"type": "goal", "goal_id": 1, "x": 0, "y": 0, "yaw": 0}),
              allowed=FROM_BRIDGE)
    with pytest.raises(ContractError, match="不该收到"):
        parse(encode({"type": "cmd", "t_ms": 1, "vx": 0, "vy": 0, "wz": 0}), allowed=FROM_AGENT)


def test_map_odom_换算():
    est = NS(x=3.0, y=-1.0, yaw=1.2)
    odom = (0.7, 0.4, -0.5)
    mx, my, myaw = _compose_map_odom(est, odom)
    c, s = math.cos(myaw), math.sin(myaw)
    assert math.isclose(mx + c * odom[0] - s * odom[1], est.x, abs_tol=1e-9)
    assert math.isclose(my + s * odom[0] + c * odom[1], est.y, abs_tol=1e-9)
    assert math.isclose(math.remainder(myaw + odom[2] - est.yaw, 2 * math.pi), 0, abs_tol=1e-9)


# ------------------------------------------------------------ 转接服务端(真套接字)


@pytest.fixture
def 短目录():
    """Unix 套接字路径有长度上限(108 字节),pytest 的 tmp_path 带长测试名会超。"""
    import shutil
    import tempfile
    from pathlib import Path
    d = Path(tempfile.mkdtemp(prefix="nb"))
    yield d
    shutil.rmtree(d, ignore_errors=True)


async def _client(path):
    r, w = await asyncio.open_unix_connection(str(path))

    async def send(m):
        w.write(encode(m))
        await w.drain()

    async def recv():
        return json.loads(await asyncio.wait_for(r.readline(), 2))
    return r, w, send, recv


async def test_服务端_握手_补发地图_收就绪速度结果_断了就不就绪(短目录):
    srv = NavBridgeServer(短目录 / "nav2.sock")
    await srv.start()
    srv.send({"type": "map", "req": 1, "map_id": "m", "map_version": "", "dir": "/d"})
    r, w, send, recv = await _client(短目录 / "nav2.sock")
    from nexwar_contract.navbridge import PROTO
    await send({"type": "hello", "proto": PROTO, "name": "t"})
    assert (await recv())["type"] == "hello"
    assert (await recv())["type"] == "map", "握手完补发最近一份地图"
    assert srv.connected and not srv.ready
    await send({"type": "ready", "ok": True})
    await send({"type": "cmd", "t_ms": 9, "vx": 0.3, "vy": 0.0, "wz": 0.1})
    await send({"type": "goal_state", "goal_id": 1, "state": "succeeded"})
    for _ in range(50):
        if srv.goal_states:
            break
        await asyncio.sleep(0.01)
    await send({"type": "path", "goal_id": 1, "pts": [[0.0, 0.0], [1.0, 0.5]]})
    for _ in range(50):
        if srv.plan:
            break
        await asyncio.sleep(0.01)
    assert srv.plan == (1, ((0.0, 0.0), (1.0, 0.5)))
    assert srv.ready and srv.cmd[1:7] == (9, 0.3, 0.0, 0.1, None, "ctl")
    assert srv.goal_states[0]["state"] == "succeeded"
    w.close()
    for _ in range(50):
        if not srv.ready:
            break
        await asyncio.sleep(0.01)
    assert not srv.ready and srv.cmd is None and "已断开" in srv.reason
    await srv.close()


async def test_服务端_握手不对就断(短目录):
    srv = NavBridgeServer(短目录 / "nav2.sock")
    await srv.start()
    r, w, send, recv = await _client(短目录 / "nav2.sock")
    await send({"type": "hello", "proto": 99})
    assert (await recv())["type"] == "error"
    assert not srv.connected
    await srv.close()


# ------------------------------------------------------------ 后端(假转接节点)


class 假转接:
    def __init__(self, ready=True):
        self.connected, self.ready, self.reason = True, ready, ""
        self.cmd = None
        self.goal_states: deque = deque()
        self.sent: list[dict] = []
        self.now = 0.0

    def _now(self):
        return self.now

    def send(self, m):
        self.sent.append(m)
        if m["type"] == "goal" and getattr(self, "auto_plan", True):
            # 真 Nav2 收下目标就规划出路线(转接节点按目标号报);测 P1 的那条自己管
            self.plan = (m["goal_id"], ((m["x"], m["y"]),))
        return True

    def tick(self):
        pass

    def kinds(self, k):
        return [m for m in self.sent if m["type"] == k]


def _台(tmp_path, link, **kw):
    t = 台子(tmp_path, **kw)
    old = t.nav
    nav = Nav2NavBackend(t.r, now_ms=t.c, map_id="m", planner=Planner(in_process=True), link=link)
    nav.obstacles, nav.guard, nav.on_event, nav.emit = (old.obstacles, old.guard, old.on_event,
                                                         old.emit)
    t.nav = nav
    nav.load_grid(tmp_path)
    return t


async def test_Nav2没就绪_这一段退回自己的规划_照样到(tmp_path):
    link = 假转接(ready=False)
    link.reason = "还在启动"
    t = _台(tmp_path, link)
    await t.start(1.5, 4.0)
    await t.nav.goto(Pose.from_xy_yaw(6.0, 4.0))
    assert "还在启动" in t.nav.fallback_reason and not link.kinds("goal")
    assert ("nav_fallback", {"reason": "Nav2 未就绪(还在启动)"}) in t.events
    await t.跑(60.0)
    assert NavStatus.SUCCEED in t.status and not t.crashed


async def test_Nav2没就绪_一米走廊退回自己的规划_也到得了_跟站点查路线一个口径(tmp_path):
    """11-09:备用规划按外接圆 0.52 + 0.05 m 膨胀,1.14 m 以下的通道都判走不通;站点查路线按 0.40 m
    (intercept_reach.REACH_RADIUS_M)。站点说走得通、Nav2 一没就绪机器人就跳点。"""
    from nexwar_agent.bridges.nav2_nav import FALLBACK_RADIUS_M
    from nexwar_contract.planning import costmap as cmod
    assert FALLBACK_RADIUS_M + cmod.INFLATE_MARGIN_M == pytest.approx(0.40)
    link = 假转接(ready=False)
    link.reason = "还在启动"
    t = _台(tmp_path, link, walls=_窄走廊(1.0))
    assert t.nav.robot_radius_m == pytest.approx(FALLBACK_RADIUS_M)
    await t.start(1.5, 4.0)
    await t.nav.goto(Pose.from_xy_yaw(9.0, 4.0))
    await t.跑(90.0)
    assert NavStatus.SUCCEED in t.status and not t.crashed, t.status


async def test_Nav2就绪_交目标_按它的速度走_它说到了就到(tmp_path):
    link = 假转接()
    t = _台(tmp_path, link)
    await t.start(1.5, 4.0)
    assert link.kinds("map") and link.kinds("map")[-1]["dir"] == str(tmp_path)
    await t.nav.goto(Pose.from_xy_yaw(6.0, 4.0, 0.0))
    g = link.kinds("goal")[-1]
    assert (g["x"], g["y"]) == (6.0, 4.0) and t.nav.fallback_reason == ""
    for _ in range(30):
        link.now += 0.1
        link.cmd = (link.now, 1, 0.4, 0.0, 0.0)
        await t.一拍()
    assert t.r.x > 2.0, "按 Nav2 的速度往前走了"
    ticks = link.kinds("tick")
    assert ticks and ticks[-1]["map_odom"] is not None and ticks[-1]["t_ms"] > ticks[0]["t_ms"]
    assert link.kinds("grid"), "感知栅格送过去了"
    link.goal_states.append({"type": "goal_state", "goal_id": g["goal_id"], "state": "succeeded"})
    await t.跑(2.0)
    assert NavStatus.SUCCEED in t.status


async def test_Nav2放弃_FAILED写清楚_取消时告诉它(tmp_path):
    link = 假转接()
    t = _台(tmp_path, link)
    await t.start(1.5, 4.0)
    await t.nav.goto(Pose.from_xy_yaw(6.0, 4.0))
    gid = link.kinds("goal")[-1]["goal_id"]
    await t.跑(0.5)
    link.goal_states.append({"type": "goal_state", "goal_id": gid, "state": "aborted",
                             "reason": "规划不出"})
    await t.跑(1.0)
    assert NavStatus.FAILED in t.status and "规划不出" in t.nav.fail_reason
    assert t.nav.fail_code == "goal_unreachable"
    await t.跑(1.0)
    await t.nav.goto(Pose.from_xy_yaw(6.0, 4.0))
    await t.跑(0.5)
    await t.nav.stop()
    assert link.kinds("cancel")[-1]["goal_id"] == link.kinds("goal")[-1]["goal_id"]


async def test_速度太旧发零_低于死区的整形(tmp_path):
    link = 假转接()
    t = _台(tmp_path, link)
    await t.start(1.5, 4.0)
    await t.nav.goto(Pose.from_xy_yaw(6.0, 4.0))
    await t.跑(0.5)
    link.now = 10.0
    link.cmd = (9.0, 1, 0.4, 0.0, 0.0)                     # 1 s 前的
    await t.一拍()
    assert abs(t.r.speed[0]) < 1e-9, "太旧的速度不执行"
    from nexwar_agent.bridges.nav2_nav import MIN_TRAVEL_MPS
    db = max(t.r.deadband_vx, MIN_TRAVEL_MPS)
    assert t.nav._deband(0.02, 0.0) == (0.0, 0.0)
    assert t.nav._deband(-db * 0.6, 0.0) == (-db, 0.0)
    link.cmd = (10.0, 2, db * 0.7, 0.0, 0.0)
    await t.一拍()
    assert t.nav.fail_reason == "" and NavStatus.FAILED not in t.status, "抬到死区,HAL 不拒"


async def test_守卫只拦真看到的挡_拦久了报被挡(tmp_path):
    link = 假转接()
    t = _台(tmp_path, link)
    await t.start(1.5, 4.0)
    t.world.dyn["box"] = (2.6, 3.6, 3.0, 4.4)              # 机头前 0.6 m
    await t.跑(0.5)
    await t.nav.goto(Pose.from_xy_yaw(6.0, 4.0))
    for _ in range(70):
        link.now += 0.1
        link.cmd = (link.now, 1, 0.5, 0.0, 0.0)            # Nav2 硬要往前冲
        await t.一拍()
    assert not t.crashed, "守卫拦住了"
    assert [k for k, _ in t.events].count("nav_blocked") == 1


async def test_转接节点断了_走着的这一段FAILED(tmp_path):
    link = 假转接()
    t = _台(tmp_path, link)
    await t.start(1.5, 4.0)
    await t.nav.goto(Pose.from_xy_yaw(6.0, 4.0))
    await t.跑(0.5)
    link.connected = False
    await t.跑(1.0)
    assert NavStatus.FAILED in t.status and "未连接" in t.nav.fail_reason
    assert t.nav.fail_code == "nav_unavailable"


async def test_目标号跨后端不重复_旧目标的晚到回执不认(tmp_path):
    link = 假转接()
    t = _台(tmp_path, link)
    await t.start(1.5, 4.0)
    await t.nav.goto(Pose.from_xy_yaw(6.0, 4.0))
    old = link.kinds("goal")[-1]["goal_id"]
    await t.nav.stop()
    await t.跑(1.0)
    (tmp_path / "b").mkdir()
    t2 = _台(tmp_path / "b", link)
    await t2.start(1.5, 4.0)
    await t2.nav.goto(Pose.from_xy_yaw(6.0, 4.0))
    new = link.kinds("goal")[-1]["goal_id"]
    assert new != old
    link.goal_states.append({"type": "goal_state", "goal_id": old, "state": "canceled"})
    await t2.跑(0.5)
    assert NavStatus.FAILED not in t2.status, "上一个后端的目标晚到的回执不算本次任务的"


async def test_原地转会扫到地图上的墙就不转_空地照转(tmp_path):
    """2026-10-29 仿真:0.85 m 门里 Nav2 的脱困原地转(Spin)扫到门框。门框在地图里:代理按地图核一道,
    不靠雷达、不靠 Nav2 的配置。"""
    link = 假转接()
    t = _台(tmp_path, link, walls=[(6.0, 0.1, 6.2, 3.575), (6.0, 4.425, 6.2, 7.9)])
    await t.start(6.1, 4.0)                                # 正卡在门里
    await t.nav.goto(Pose.from_xy_yaw(10.0, 4.0))
    for _ in range(30):
        link.now += 0.1
        link.cmd = (link.now, 1, 0.0, 0.0, 1.0)            # Nav2 要原地转
        await t.一拍()
    assert abs(t.r.yaw) < 0.05 and not t.crashed, "门里不许原地转"
    await t.nav.stop()
    await t.跑(1.0)
    t.r.teleport(3.0, 4.0, 0.0)                            # 空地
    await t.跑(1.0)
    await t.nav.goto(Pose.from_xy_yaw(1.0, 4.0))
    for _ in range(10):
        link.now += 0.1
        link.cmd = (link.now, 1, 0.0, 0.0, 1.0)
        await t.一拍()
    assert abs(t.r.yaw) > 0.3, "空地照转"


async def test_死区按命令算_0点13米每秒_原地转0点15弧度每秒_工单11_02_10(tmp_path):
    """2026-10-29 C40221 实测:前进、后退约 0.13 m/s 以下只踏步不走。原地转:比例 0.10 才实际转
    0.069 rad/s,比例 0.10 = 命令 0.15 rad/s(1.5 rad/s/比例)—— 原来把实际转速 0.07 当命令门槛,
    等于不转(11-02 工单 10)。MPPI 在障碍边上、收尾发的小速度不清零(清零 = 一直不动、「没进展」):
    0.03 以上一律抬到能走起来的最低速度。走着的时候转向不动(走路时小转向照样转)。"""
    from nexwar_agent.bridges.nav2_nav import DEBAND_FLOOR, MIN_TRAVEL_MPS, MIN_TURN_RPS
    link = 假转接()
    t = _台(tmp_path, link)
    assert (MIN_TRAVEL_MPS, MIN_TURN_RPS, DEBAND_FLOOR) == (0.13, 0.15, 0.03)
    assert t.nav._deband(0.02, 0.0) == (0.0, 0.0)
    assert t.nav._deband(0.05, 0.0) == (0.13, 0.0)
    assert t.nav._deband(-0.09, 0.0) == (-0.13, 0.0)
    assert t.nav._deband(0.3, 0.02) == (0.3, 0.02)
    assert t.nav._deband(0.0, -0.05) == (0.0, -0.15)
    assert t.nav._deband(0.0, 0.02) == (0.0, 0.0)


async def test_限速压前进时转向同比例压_弯不变急_工单11_02_9(tmp_path):
    """11-02 回程卡住:Nav2 要 0.87 m/s + 0.7 rad/s(弯半径 1.24 m),代理只把前进压到 0.3、转向照
    旧 → 半径 0.43 m,急拐向方块角,守卫一直拦。压前进就按同一比例压转向,走的还是 Nav2 算的那条弯。"""
    link = 假转接()
    t = _台(tmp_path, link)
    await t.start(1.5, 4.0)
    await t.nav.set_speed(0.3)
    await t.nav.goto(Pose.from_xy_yaw(6.0, 4.0))
    seen = []
    for _ in range(80):                                     # 刚出发两侧没看过:先直走看清
        link.now += 0.1
        link.cmd = (link.now, 1, 0.87, 0.0, 0.7)
        await t.一拍()
        if abs(t.nav._last_wz) > 1e-6:
            seen.append((t.nav._last_vx, t.nav._last_wz))
    assert seen, "看清以后照 Nav2 的弯走"
    vx, wz = max(seen)
    assert abs(vx - 0.3) < 1e-6, vx
    assert abs(wz / vx - 0.7 / 0.87) < 0.01, ("弯半径要跟 Nav2 的一样", vx, wz)


async def test_送给Nav2的速度按位置变化算_不信厂家里程报的速度(tmp_path):
    """厂家里程低速时原地踏步也报在走(10-29 实测 vx +0.087 m/s 时位置不变)。"""
    link = 假转接()
    t = _台(tmp_path, link)
    await t.start(1.5, 4.0)
    t.nav._v_meas = 0.087                                   # 厂家说在走
    for _ in range(5):
        await t.一拍()
    assert abs(link.kinds("tick")[-1]["vel"][0]) < 0.01, "位置未变:送 0"
    await t.nav.goto(Pose.from_xy_yaw(6.0, 4.0))
    for _ in range(20):
        link.now += 0.1
        link.cmd = (link.now, 1, 0.4, 0.0, 0.0)
        await t.一拍()
    v = link.kinds("tick")[-1]["vel"][0]
    assert 0.25 < v < 0.5, v


async def test_看不见的地方快了就慢下来_看得见的挡才停(tmp_path):
    """2026-10-29 仿真:Nav2 1.0 m/s 时人从侧面(盲区)横穿,5 次撞 5 次 ——
    「看不见的放行」快了不安全。改成:扫过区里有看不见的格子、又快,就降到 UNKNOWN_SLOW_MPS;
    低速照旧放行(不回到 10-28 起不了步)。"""
    from nexwar_agent.bridges.nav2_nav import UNKNOWN_SLOW_MPS
    from nexwar_agent.obstacles import Verdict
    link = 假转接()
    t = _台(tmp_path, link)
    await t.start(1.5, 4.0)
    await t.nav.goto(Pose.from_xy_yaw(9.0, 4.0))
    calls = []

    def guard(vx, wz):
        calls.append(vx)
        if abs(vx) > UNKNOWN_SLOW_MPS + 1e-9:
            return Verdict(False, "看不见 3 处", hits=(), unknown=3, kind="unknown")
        return Verdict(True)
    t.nav._guard_check = guard
    for _ in range(15):
        link.now += 0.1
        link.cmd = (link.now, 1, 0.9, 0.0, 0.0)
        await t.一拍()
    assert calls and calls[-1] == pytest.approx(UNKNOWN_SLOW_MPS), calls[-3:]
    assert 0.2 < t.r.speed[0] <= UNKNOWN_SLOW_MPS + 1e-6, "慢下来、不停"
    t.nav._guard_check = lambda vx, wz: Verdict(False, "扫过区有挡 2 处", hits=((1.0, 0.0),))
    for _ in range(5):
        link.now += 0.1
        link.cmd = (link.now, 1, 0.9, 0.0, 0.0)
        await t.一拍()
    assert abs(t.r.speed[0]) < 0.05, "看得见的挡:停"



# ------------------------------------------------------------ 看得清就快(决策 76)


async def _看清(t, n=8):
    for _ in range(n):
        await t.一拍()
    return t.nav._vis_cap(await t.nav._here(), 1)


async def test_看得清就快_空地放到最快(tmp_path):
    from nexwar_agent.bridges.nav2_nav import V_FAST
    t = _台(tmp_path, 假转接())
    await t.start(1.5, 4.0)
    assert await _看清(t) == pytest.approx(V_FAST)


async def test_看得清就快_正前方有箱子按刹车距离降(tmp_path):
    from nexwar_agent.bridges.nav2_nav import V_FAST
    t = _台(tmp_path, 假转接())
    await t.start(1.5, 4.0)
    t.world.dyn["box"] = (3.3, 3.7, 3.7, 4.3)               # 机头前约 1.3 m
    v = await _看清(t)
    assert v < 0.7 * V_FAST, v


async def test_看得清就快_斜前方有人就降_地图上的墙不算(tmp_path):
    from nexwar_agent.bridges.nav2_nav import V_FAST
    walls = [(0.1, 3.2, 11.9, 3.3), (0.1, 4.7, 11.9, 4.8)]  # 1.4 m 走廊:墙在地图里
    t = _台(tmp_path, 假转接(), walls=walls)
    await t.start(1.5, 4.0)
    assert await _看清(t) == pytest.approx(V_FAST), "走廊两边的墙在地图里:不拖慢"
    t2_dir = tmp_path / "b"
    t2_dir.mkdir()
    t2 = _台(t2_dir, 假转接())
    await t2.start(1.5, 4.0)
    t2.world.dyn["person"] = (3.0, 2.9, 3.4, 3.3)           # 前 1.2 m、右 0.9 m:不在扫过区
    v = await _看清(t2)
    assert v < 0.8 * V_FAST, v


@pytest.mark.parametrize("box, want", [
    ((2.6, 3.8, 2.9, 4.2), 0.3),                            # 机头前约 0.6 m:1 m 以内
    ((3.2, 2.1, 3.5, 2.4), 0.6),                            # 离机身边约 1.8 m(前 1.2、右 1.3)
    ((4.2, 6.4, 4.5, 6.7), 1.0),                            # 前 2.2 m、左 2.4 m:2 m 之外
])
async def test_W70_看得清就快_人2米内降到0点6_1米内0点3_别的到1点0(tmp_path, box, want):
    """用户 11-03:「速度提高到 1.0,周围 2 m 有人降到 0.6,1 m 以下 0.3」。"""
    t = _台(tmp_path, 假转接())
    await t.start(1.5, 4.0)
    t.world.dyn["p"] = box
    assert await _看清(t) == pytest.approx(want), box


async def test_看得清就快_限速送给Nav2(tmp_path):
    link = 假转接()
    t = _台(tmp_path, link)
    await t.start(1.5, 4.0)
    t.world.dyn["box"] = (3.3, 3.7, 3.7, 4.3)
    await t.nav.goto(Pose.from_xy_yaw(9.0, 4.0))
    for _ in range(10):
        link.now += 0.1
        link.cmd = (link.now, 1, 0.0, 0.0, 0.0)
        await t.一拍()
    sp = link.kinds("tick")[-1].get("speed")
    assert sp is not None and 0 < sp < 0.8, sp


# ------------------------------------------------------------ 站点上看得见(路线、健康)


async def test_走Nav2时_站点地图上画Nav2规划的路线(tmp_path):
    link = 假转接()
    link.plan = None
    link.auto_plan = False
    t = _台(tmp_path, link)
    await t.start(1.5, 4.0)
    await t.nav.goto(Pose.from_xy_yaw(6.0, 4.0))
    gid = link.kinds("goal")[-1]["goal_id"]
    assert t.nav.current_path() is None, "Nav2 尚未规划出来"
    link.plan = (gid - 1, ((0.0, 0.0), (1.0, 1.0)))
    assert t.nav.current_path() is None, "别的目标的路线不算"
    link.plan = (gid, ((1.5, 4.0), (3.0, 4.2), (6.0, 4.0)))
    assert t.nav.current_path() == ((1.5, 4.0), (3.0, 4.2), (6.0, 4.0))
    await t.nav.stop()
    await t.跑(1.0)
    assert t.nav.current_path() is None


async def test_设备健康_Nav2就绪没有_为什么(tmp_path):
    link = 假转接()
    t = _台(tmp_path, link)
    assert t.nav.health() == {"id": "nav2", "state": "online", "detail": "Nav2 就绪"}
    link.ready, link.reason = False, "还在启动(生命周期未全部激活)"
    h = t.nav.health()
    assert h["state"] == "offline" and "还在启动" in h["detail"] and "退回" in h["detail"]
    link.connected = False
    assert "未连接" in t.nav.health()["detail"]


def test_路径抽稀_头尾都留_最多256点():
    from nexwar_localizer.nav2bridge import decimate
    pts = [(i * 0.05, 0.0) for i in range(2001)]           # 100 m、每 5 cm 一个点
    out = decimate(pts)
    assert out[0] == [0.0, 0.0] and out[-1] == [100.0, 0.0] and len(out) <= 256
    assert decimate([(0, 0), (0.01, 0), (0.02, 0)]) == [[0.0, 0.0], [0.02, 0.0]]
    assert decimate([]) == []


async def test_运行时_nav2后端的设备健康里有Nav2一条(tmp_path):
    from test_runtime import REG, 钟

    from nexwar_adapter_sim.robot import SimRobot
    from nexwar_agent.runtime import AgentRuntime
    from nexwar_contract.memory_broker import MemoryBroker, MemoryTransport
    c = 钟()
    rt = AgentRuntime(transport=MemoryTransport(MemoryBroker(), "dog"), registration=REG,
                      hal=SimRobot(now_ms=c), store_dir=tmp_path / "a", now_ms=c,
                      loaded_map=("m", "1"), home=Pose.from_xy_yaw(0, 0), nav="nav2",
                      obstacles="bridge", monotonic=lambda: c.mono)
    got = await rt.devices.refresh()
    n = [d for d in got if d["id"] == "nav2"]
    assert n and n[0]["state"] == "offline" and "未连接" in n[0]["detail"]


# ---------------------------------------------------------------- W47 外审(R4–R7)

async def test_外审R4_限速区的上限也管Nav2的速度_送给Nav2的也降(tmp_path):
    from test_planned_nav import _区
    link = 假转接()
    t = _台(tmp_path, link, max_vx=1.0)
    await t.start(5, 4)
    await t.nav.set_zones(_区({"id": "children", "kind": "slow", "max_speed_mps": 0.2,
                               "polygon": [[3, 2], [9, 2], [9, 6], [3, 6]]}))
    await t.nav.goto(Pose.from_xy_yaw(8, 4))
    for _ in range(15):
        link.now += 0.1
        link.cmd = (link.now, 1, 0.8, 0, 0)
        await t.一拍()
    assert t.nav._last_vx <= 0.2 + 1e-9 and t.r.speed[0] <= 0.2 + 1e-6
    assert link.kinds("tick")[-1]["speed"] <= 0.3 + 1e-9      # 送给 Nav2 的不高于最低档


async def test_外审R5_死区整形不越过任务限速_也不越过转速上限(tmp_path):
    link = 假转接()
    t = _台(tmp_path, link)
    await t.start(1.5, 4)
    await t.nav.set_speed(0.1)
    await t.nav.goto(Pose.from_xy_yaw(6, 4))
    for _ in range(15):
        link.now += 0.1
        link.cmd = (link.now, 1, 0.5, 0, 0)
        await t.一拍()
    assert abs(t.nav._last_vx) <= 0.1 + 1e-9, "限速低于死区:停下,不抬到死区"
    link2 = 假转接()
    t2 = _台(tmp_path, link2)
    await t2.start(5, 4)
    await t2.nav.set_speed(0.6, z=0.05)
    await t2.nav.goto(Pose.from_xy_yaw(2, 4))
    for _ in range(15):
        link2.now += 0.1
        link2.cmd = (link2.now, 1, 0, 0, 0.5)
        await t2.一拍()
    assert abs(t2.nav._last_wz) <= 0.05 + 1e-9


async def test_外审R6_Nav2往后退时_禁行区提前刹按后退方向查(tmp_path):
    from test_planned_nav import _区, _在
    link = 假转接()
    t = _台(tmp_path, link)
    await t.start(5, 4)
    await t.nav.set_zones(_区({"id": "pond", "kind": "nogo",
                               "polygon": [[2, 0], [4.365, 0], [4.365, 8], [2, 8]]}))
    await t.nav.goto(Pose.from_xy_yaw(8, 4))
    t.nav._v_meas = -0.3
    link.now = 0.0
    link.cmd = (0.0, 1, -0.3, 0, 0)
    await t.nav._drive(_在(5, 4), 0.1)
    assert t.nav._last_vx > -0.2, "身后 17 cm 是禁行区:不许照 0.3 往后退"


async def test_外审R7_旧目标晚到的速度_不驱动新目标(tmp_path):
    link = 假转接()
    t = _台(tmp_path, link)
    await t.start(5, 4)
    await t.nav.goto(Pose.from_xy_yaw(8, 4))
    a = link.kinds("goal")[-1]["goal_id"]
    await t.nav.stop()
    for _ in range(8):
        await t.一拍()
    link.cmd = (link.now, 1, 0.4, 0, 0)                     # A 的速度晚到(老转接节点:不带目标号)
    await t.nav.goto(Pose.from_xy_yaw(2, 4))               # B 在身后,还没收下、没出速度
    for _ in range(4):
        await t.一拍()
    assert t.nav._last_vx <= 1e-9, "新目标尚无自己的速度:不动"
    b = link.kinds("goal")[-1]["goal_id"]
    link.cmd = (link.now, 1, 0.4, 0, 0, a)                  # 新转接节点:标了是 A 的
    for _ in range(3):
        await t.一拍()
    assert t.nav._last_vx <= 1e-9
    link.cmd = (link.now, 1, -0.3, 0, 0, b)                 # B 自己的:照走
    await t.一拍()
    assert t.nav._last_vx < -0.1


# ---------------------------------------------------------------- W47 复查(N2、N3、N5)

async def test_外审复查N2_很窄的限速区也算上_送给Nav2的不高于区域上限(tmp_path):
    from test_planned_nav import _区
    link = 假转接()
    t = _台(tmp_path, link, max_vx=1.0)
    await t.start(5, 4)
    await t.nav.set_zones(_区({"id": "thin", "kind": "slow", "max_speed_mps": 0.2,
                               "polygon": [[5.02, 2], [5.08, 2], [5.08, 6], [5.02, 6]]}))
    await t.nav.goto(Pose.from_xy_yaw(8, 4))
    gid = link.kinds("goal")[-1]["goal_id"]
    sent = []
    for _ in range(6):
        link.now += 0.1
        link.cmd = (link.now, 1, 0.8, 0, 0, gid)
        await t.一拍()
        sent.append(t.nav._last_vx)
    assert 0 < max(sent) <= 0.2 + 1e-9, sent
    assert link.kinds("tick")[-1]["speed"] <= 0.2 + 1e-9


async def test_外审复查N3_没标目标号的速度不认(tmp_path):
    link = 假转接()
    t = _台(tmp_path, link)
    await t.start(5, 4)
    await t.nav.goto(Pose.from_xy_yaw(8, 4))
    gid = link.kinds("goal")[-1]["goal_id"]
    for _ in range(4):                                       # 先起步(头几拍切步态)
        link.now += 0.1
        link.cmd = (link.now, 1, 0.4, 0, 0, gid)
        await t.一拍()
    assert t.nav._last_vx > 0.3
    for _ in range(2):
        link.now += 0.1
        link.cmd = (link.now, 1, 0.4, 0, 0, None)            # 转接节点那会儿没有在走的目标
        await t.一拍()
    assert t.nav._last_vx <= 1e-9


async def test_外审复查N5_刚停下时上一条命令还在后退_往前也要先按后退方向查禁行区(tmp_path):
    from test_planned_nav import _区, _在
    link = 假转接()
    t = _台(tmp_path, link)
    await t.start(5, 4)
    await t.nav.set_zones(_区({"id": "pond", "kind": "nogo",
                               "polygon": [[2, 0], [4.365, 0], [4.365, 8], [2, 8]]}))
    await t.nav.goto(Pose.from_xy_yaw(8, 4))
    gid = link.kinds("goal")[-1]["goal_id"]
    t.nav._v_meas = 0.0
    t.nav._last_vx = -0.3                                     # 刚发过后退,实测还没跟上
    link.now = 0.0
    link.cmd = (0.0, 1, 0.3, 0, 0, gid)
    await t.nav._drive(_在(5, 4), 0.1)
    assert t.nav._last_vx <= 1e-9, "上一条后退可能还在执行:身后 17 cm 是禁行区,这一拍先停"


async def test_外审复查P1_新目标收到自己的规划路线之前_Nav2的速度一律不用(tmp_path):
    """0.2 秒屏障证明不了速度是新目标的;控制器总是拿到新路线之后才出新目标的速度。"""
    link = 假转接()
    link.auto_plan = False
    t = _台(tmp_path, link)
    await t.start(5, 4)
    await t.nav.goto(Pose.from_xy_yaw(8, 4))
    gid = link.kinds("goal")[-1]["goal_id"]
    for _ in range(5):
        link.now += 0.1
        link.cmd = (link.now, 1, 0.4, 0, 0, gid)                # 标的是新目标,可路线还没来
        await t.一拍()
    assert t.nav._last_vx <= 1e-9
    link.plan = (gid - 1, ((5.0, 4.0), (2.0, 4.0)))             # 别的目标的路线:不算
    link.now += 0.1
    link.cmd = (link.now, 1, 0.4, 0, 0, gid)
    await t.一拍()
    assert t.nav._last_vx <= 1e-9
    link.plan = (gid, ((5.0, 4.0), (8.0, 4.0)))                 # 自己的路线来了
    for _ in range(3):
        link.now += 0.1
        link.cmd = (link.now, 1, 0.4, 0, 0, gid)
        await t.一拍()
    assert t.nav._last_vx > 0.3


def test_外审复查P1_转接节点订控制器的原始输出_不经速度平滑器():
    """平滑器会把旧目标的速度慢慢衰减(OPEN_LOOP),目标换了还在出旧方向的速度。"""
    from pathlib import Path
    src = (Path(__file__).resolve().parents[3] / "packages" / "localizer" / "src"
           / "nexwar_localizer" / "nav2bridge.py").read_text(encoding="utf-8")
    assert 'create_subscription(Twist, "/cmd_vel_nav"' in src
    assert 'create_subscription(Twist, "/cmd_vel",' not in src


async def test_外审复查P3_MPPI倒车被限速压到死区以下_照最小能走的倒车执行(tmp_path):
    """MPPI 按同一比例缩倒车上限(vx_min / vx_max = 0.3):限速 0.2 时它最多倒 0.06,
    原来落进死区一律清零。"""
    from test_planned_nav import _区
    link = 假转接()
    t = _台(tmp_path, link)
    await t.start(5, 4)
    await t.nav.set_zones(_区({"id": "lawn", "kind": "slow", "max_speed_mps": 0.2,
                               "polygon": [[3, 2], [9, 2], [9, 6], [3, 6]]}))
    await t.nav.goto(Pose.from_xy_yaw(8, 4))
    gid = link.kinds("goal")[-1]["goal_id"]
    sent = []
    for _ in range(6):
        link.now += 0.1
        link.cmd = (link.now, 1, -0.06, 0, 0, gid)
        await t.一拍()
        sent.append(t.nav._last_vx)
    assert min(sent) == pytest.approx(-0.13) and max(abs(v) for v in sent) <= 0.2 + 1e-9


def test_外审复查P3_代理记的倒车比例跟Nav2参数一致():
    from pathlib import Path

    from nexwar_agent.bridges.nav2_nav import MPPI_REVERSE_RATIO
    text = (Path(__file__).resolve().parents[3] / "deploy" / "nav2" / "params.yaml").read_text()
    import re
    vmax = float(re.search(r"\n\s+vx_max:\s*([0-9.]+)", text).group(1))
    vmin = float(re.search(r"\n\s+vx_min:\s*(-?[0-9.]+)", text).group(1))
    assert MPPI_REVERSE_RATIO == pytest.approx(-vmin / vmax)


async def test_复查三P1_路线门槛打开前缓存的速度作废_要比路线晚到的才认(tmp_path):
    """Codex 第三轮:新目标的路线来了,门槛打开,之前缓存的(标的也是新目标的)旧速度不能拿来开车。"""
    link = 假转接()
    link.auto_plan = False
    t = _台(tmp_path, link)
    await t.start(5, 4)
    await t.nav.goto(Pose.from_xy_yaw(2, 4))                    # 身后的目标
    gid = link.kinds("goal")[-1]["goal_id"]
    link.now += 0.1
    link.cmd = (link.now, 1, 0.4, 0, 0, gid, "ctl", 1)          # 第 1 条到的:上一个目标残留的往前
    link.plan, link.plan_rx = (gid, ((5.0, 4.0), (2.0, 4.0))), {gid: 2}   # 第 2 条到的:路线
    for _ in range(6):                                         # 过了起步那几拍
        link.now += 0.05
        link.cmd = (link.now, *link.cmd[1:])                    # 还是那一条(没新速度来)
        await t.一拍()
    assert t.nav._status is NavStatus.ACTIVE
    assert t.nav._last_vx <= 1e-9, "比路线早到的速度不认"
    for rx in (3, 4, 5):
        link.now += 0.1
        link.cmd = (link.now, 1, -0.3, 0, 0, gid, "ctl", rx)
        await t.一拍()
    assert t.nav._last_vx < -0.1, "路线之后到的照用"


async def test_复查三P4_脱困动作的速度不用等路线_目标号照样要对(tmp_path):
    """BackUp 往往在规划不出来时才做(没有路线):标了 beh 的不过路线门槛;别的目标的照样不认。"""
    link = 假转接()
    link.auto_plan = False
    t = _台(tmp_path, link)
    await t.start(5, 4)
    await t.nav.goto(Pose.from_xy_yaw(8, 4))
    gid = link.kinds("goal")[-1]["goal_id"]
    for rx in (1, 2, 3):
        link.now += 0.1
        link.cmd = (link.now, 1, -0.15, 0, 0, gid - 1, "beh", rx)   # 别的目标的脱困
        await t.一拍()
    assert t.nav._last_vx >= -1e-9
    for rx in (4, 5, 6):
        link.now += 0.1
        link.cmd = (link.now, 1, -0.15, 0, 0, gid, "beh", rx)
        await t.一拍()
    assert t.nav._last_vx < -0.1


def test_复查三_转接服务端_报文按到达编号_记下每个目标第一条路线是第几条到的():
    from nexwar_agent.navbridge import NavBridgeServer
    s = NavBridgeServer("/nonexistent/nav2.sock")
    s._on({"type": "cmd", "t_ms": 1, "vx": 0.1, "vy": 0, "wz": 0, "goal_id": 7, "src": "ctl"})
    s._on({"type": "path", "goal_id": 7, "pts": [[0, 0], [1, 0]]})
    s._on({"type": "path", "goal_id": 7, "pts": [[0, 0], [2, 0]]})     # 重规划:不挪第一条
    s._on({"type": "cmd", "t_ms": 2, "vx": 0.2, "vy": 0, "wz": 0, "goal_id": 7, "src": "beh"})
    assert s.plan_rx[7] == 2 and s.cmd[6:] == ("beh", 4)
    s._on({"type": "cmd", "t_ms": 3, "vx": 0.2, "vy": 0, "wz": 0})       # 老转接节点:不带
    assert s.cmd[6:] == ("ctl", 5)


def test_W48_协议4_目标可以带途经点():
    from nexwar_contract.navbridge import MAX_VIA, PROTO
    assert PROTO >= 4 and MAX_VIA >= 500, "路网最多 500 个点,途经点要装得下"


async def test_W48_有路网_交给Nav2的目标带上路网上的途经点_没路网不带(tmp_path):
    from nexwar_contract.routenet import RouteNet
    link = 假转接()
    t = _台(tmp_path, link)
    await t.start(1.5, 4.0)
    await t.nav.goto(Pose.from_xy_yaw(6.0, 4.0, 0.0))
    assert "via" not in link.kinds("goal")[-1]
    link.goal_states.append({"type": "goal_state", "goal_id": link.kinds("goal")[-1]["goal_id"],
                             "state": "succeeded"})
    await t.跑(1.0)
    net = RouteNet.from_wire({"map_id": "m", "map_version": "", "revision": 1,
                              "nodes": [{"id": "A", "x": 1.5, "y": 5.0},
                                        {"id": "B", "x": 6.0, "y": 5.2}],
                              "edges": [["A", "B"]]})
    t.nav.set_route_net(net)
    await t.nav.goto(Pose.from_xy_yaw(6.0, 4.5, 0.0))
    g = link.kinds("goal")[-1]
    here = (t.r.x, t.r.y)
    from nexwar_contract.routenet import densify, route
    want = densify(route(net, here, (6.0, 4.5)), step=1.0)
    assert g["via"] == [[round(x, 3), round(y, 3)] for x, y in want] and len(g["via"]) > 2, \
        "沿路每隔不到 1 m 一个途经点:Nav2 跳过一个(1.5 m 内算经过)下一个还在路上,不切角"


async def test_W48复查M1_很长的路网_加密以后途经点也不超过协议上限(tmp_path):
    """外审 W48-M1:按总长算间距、每段各自向上取整,点数可能超 500,报文编不出来。"""
    from nexwar_contract.navbridge import MAX_VIA
    from nexwar_contract.routenet import RouteNet
    link = 假转接()
    t = _台(tmp_path, link)
    await t.start(1.5, 4.0)
    # 300 个点、间距 1.6 m(总长约 478 m):每段都要切成两段,原来会出约 600 个途经点
    nodes = [{"id": f"N{i}", "x": 1.5 + i * 1.6, "y": 4.3} for i in range(300)]
    net = RouteNet.from_wire({"map_id": "m", "map_version": "", "revision": 1, "nodes": nodes,
                              "edges": [[f"N{i}", f"N{i + 1}"] for i in range(299)]})
    t.nav.set_route_net(net)
    await t.nav.goto(Pose.from_xy_yaw(1.5 + 299 * 1.6, 4.0, 0.0))
    g = link.kinds("goal")[-1]
    assert 250 < len(g.get("via", [])) <= MAX_VIA


def test_MPPI采样数按机器人上的算力_工单11_02_12():
    """11-02 C40221 上 controller 几乎每秒「missed its desired rate」:采样 1000 条算不过来。"""
    import re
    from pathlib import Path
    text = (Path(__file__).resolve().parents[3] / "deploy" / "nav2" / "params.yaml").read_text()
    batch = int(re.search(r"\n\s+batch_size:\s*(\d+)", text).group(1))
    assert batch <= 500


async def test_只差朝向的目标_代理自己原地转_不交给Nav2_工单11_02_11(tmp_path):
    """11-02:同一位置换朝向 10°,Smac Lattice「no valid path」、60 s 不动。离目标在容差内只差朝向的,
    代理自己原地转(守卫、地图墙照样管)。"""
    link = 假转接()
    t = _台(tmp_path, link)
    await t.start(1.5, 4.0, 0.0)
    await t.nav.goto(Pose.from_xy_yaw(1.55, 4.0, math.radians(10)))
    assert not link.kinds("goal"), "不交给 Nav2"
    await t.跑(20.0)
    assert NavStatus.SUCCEED in t.status, (t.status, t.nav.fail_reason)
    assert abs(math.degrees(t.r.yaw) - 10) < 9, math.degrees(t.r.yaw)
    # 外审 11-14:刚出发两侧没看过,先直走出去看清、倒回来再转 —— 最后还站在目标上
    assert math.dist((t.r.x, t.r.y), (1.55, 4.0)) < 0.15, (t.r.x, t.r.y)


async def test_离目标远的照样交给Nav2(tmp_path):
    link = 假转接()
    t = _台(tmp_path, link)
    await t.start(1.5, 4.0, 0.0)
    await t.nav.goto(Pose.from_xy_yaw(2.0, 4.0, 0.0))
    assert link.kinds("goal")


async def test_Nav2走到目标附近只差朝向_代理接过来自己转_工单11_02_18(tmp_path):
    """11-02 复测:从 (0,0) 派到 C1 起点,位置到了、差 66°,Nav2 三次没进展、原地卡约 50 s。到了
    xy 容差、只差朝向时代理取消 Nav2 的目标,自己原地转。"""
    link = 假转接()
    t = _台(tmp_path, link)
    await t.start(0.6, 4.0, 0.0)                         # 外审 11-14:走过来两侧才看过
    await t.nav.goto(Pose.from_xy_yaw(2.5, 4.0, math.radians(66)))
    gid = link.kinds("goal")[-1]["goal_id"]
    for _ in range(90):                                  # Nav2 把它开到目标点,朝向不管
        link.now += 0.1
        dx = 2.5 - t.r.x
        link.cmd = (link.now, 1, 0.3 if dx > 0.05 else 0.0, 0.0, 0.0)
        await t.一拍()
    assert abs(t.r.x - 2.5) < 0.2
    await t.跑(15.0)
    assert link.kinds("cancel") and link.kinds("cancel")[-1]["goal_id"] == gid, "取消 Nav2 的目标"
    assert NavStatus.SUCCEED in t.status, (t.status, t.nav.fail_reason)
    assert abs(math.degrees(t.r.yaw) - 66) < 9, math.degrees(t.r.yaw)


async def test_W70_原地转到朝向_差不到3度才算到(tmp_path):
    """2026-11-03 C40221:原点朝向 0,转完停在 0.166 rad(9.5°):原来差 0.15 rad 以内就停。"""
    link = 假转接()
    t = _台(tmp_path, link)
    await t.start(1.5, 4.0, math.radians(14))
    await t.nav.goto(Pose.from_xy_yaw(1.55, 4.0, 0.0))
    await t.跑(20.0)
    assert NavStatus.SUCCEED in t.status, (t.status, t.nav.fail_reason)
    assert abs(math.degrees(t.r.yaw)) < 3.5, math.degrees(t.r.yaw)


async def test_W70_刚中止完_Nav2在取消上一个目标_回原点等它一下_不退回(tmp_path, monkeypatch):
    """2026-11-03 C40221:用户中止任务后马上回原点,Nav2 还在取消上一个目标(转接节点报未就绪),
    代理立刻退回自己的规划导航(倒退 1.3 m、停 20 s)。这种一会儿就好的未就绪,等它。"""
    import nexwar_agent.bridges.nav2_nav as N
    monkeypatch.setattr(N, "NAV2_SETTLE_POLL_S", 0.01)
    link = 假转接()
    t = _台(tmp_path, link)
    await t.start(1.5, 4.0, 0.0)
    link.ready, link.reason = False, "等 Nav2 取消上一次留下的导航目标"
    task = asyncio.get_running_loop().create_task(t.nav.goto(Pose.from_xy_yaw(6.0, 4.0, 0.0)))
    await asyncio.sleep(0.05)
    assert not task.done() and not link.kinds("goal")
    link.ready, link.reason = True, ""
    await asyncio.wait_for(task, 2.0)
    assert link.kinds("goal") and t.nav.fallback_reason == ""


async def test_W70_Nav2一直取消不完_等够了才退回自己的规划(tmp_path, monkeypatch):
    import nexwar_agent.bridges.nav2_nav as N
    monkeypatch.setattr(N, "NAV2_SETTLE_POLL_S", 0.01)
    monkeypatch.setattr(N, "NAV2_SETTLE_S", 0.1)
    link = 假转接()
    t = _台(tmp_path, link)
    await t.start(1.5, 4.0, 0.0)
    link.ready, link.reason = False, "等 Nav2 取消上一次留下的导航目标"
    await asyncio.wait_for(t.nav.goto(Pose.from_xy_yaw(6.0, 4.0, 0.0)), 2.0)
    assert "取消上一次" in t.nav.fallback_reason and not link.kinds("goal")


async def test_W70_中止那一拍卡住_未在送时钟_回原点自己送上时钟(tmp_path, monkeypatch):
    """2026-11-03 C40221 11:58:01:中止后马上回原点,「Nav2 未就绪(代理未在送时钟)」→ 退回自己的
    规划(倒退 1.3 m、停 20 s)。处理中止那一拍卡了 2 s 多,时钟没送;goto 自己先送上时钟再等。"""
    import nexwar_agent.bridges.nav2_nav as N
    monkeypatch.setattr(N, "NAV2_SETTLE_POLL_S", 0.01)
    link = 假转接()
    t = _台(tmp_path, link)
    await t.start(1.5, 4.0, 0.0)
    link.ready, link.reason = False, "代理未在送时钟"
    send = link.send

    def 收到时钟就绪(m):
        if m["type"] == "tick":
            link.ready, link.reason = True, ""
        return send(m)
    link.send = 收到时钟就绪
    await asyncio.wait_for(t.nav.goto(Pose.from_xy_yaw(6.0, 4.0, 0.0)), 2.0)
    assert link.kinds("goal") and t.nav.fallback_reason == ""


async def test_W70_只差朝向_转身会扫到墙_被挡10秒就停在这儿算到_不干等(tmp_path):
    """11-03 C40221:原点旁边有椅子、桌子,要转 170°,守卫一直拦,停了一分多钟不动。"""
    link = 假转接()
    # 机头左前方 0.45 m 处一根柱子:转大半圈一定扫到
    t = _台(tmp_path, link, walls=[(1.85, 4.35, 1.95, 4.45)])
    await t.start(1.5, 4.0, 0.0)
    await t.nav.goto(Pose.from_xy_yaw(1.55, 4.0, math.radians(170)))
    await t.跑(5.0)
    assert NavStatus.SUCCEED not in t.status, "被挡不到 10 s 先等"
    await t.跑(8.0)
    assert NavStatus.SUCCEED in t.status, (t.status, t.nav.fail_reason)
    assert abs(math.degrees(t.r.yaw)) < 120, "确实被挡住、没转过去"
    assert not t.crashed


async def test_W70_Nav2失败而狗没挪窝_说规划不出_照旧再试一次(tmp_path):
    """11-03 C40221:原点被椅子占了,Nav2 一直 no valid path,站点上看不到原因。15:00 又一例:第一次
    空等 2 分钟,再发一次 35 s 就到了 —— 没挪窝的说清楚原因,但照旧让引擎再试一次。"""
    link = 假转接()
    t = _台(tmp_path, link)
    await t.start(1.5, 4.0)
    await t.nav.goto(Pose.from_xy_yaw(6.0, 4.0))
    gid = link.kinds("goal")[-1]["goal_id"]
    await t.跑(0.5)
    link.goal_states.append({"type": "goal_state", "goal_id": gid, "state": "aborted",
                             "reason": "no valid path"})
    await t.跑(1.0)
    assert NavStatus.FAILED in t.status and "规划不出到目标的路线" in t.nav.fail_reason
    assert t.nav.fail_code == "goal_unreachable"
    assert not t.nav.fail_final


async def test_W70_Nav2失败但走了一大段_照旧让引擎重试(tmp_path):
    link = 假转接()
    t = _台(tmp_path, link)
    await t.start(1.5, 4.0)
    await t.nav.goto(Pose.from_xy_yaw(6.0, 4.0, 0.0))
    gid = link.kinds("goal")[-1]["goal_id"]
    for _ in range(30):
        link.now += 0.1
        link.cmd = (link.now, 1, 0.4, 0.0, 0.0)
        await t.一拍()
    assert t.r.x > 2.0
    link.goal_states.append({"type": "goal_state", "goal_id": gid, "state": "aborted",
                             "reason": "x"})
    await t.跑(1.0)
    assert NavStatus.FAILED in t.status and not t.nav.fail_final


async def test_W70_目标点上有箱子_Nav2失败_说目标点被占_不再重试(tmp_path):
    """11-03 C40221:椅子放得离原点太近,原点本身被占了;Nav2 只说 no valid path。"""
    link = 假转接()
    t = _台(tmp_path, link)
    await t.start(1.5, 4.0)
    t.world.dyn["box"] = (2.8, 3.8, 3.2, 4.2)               # 正好压在目标 (3.0, 4.0) 上
    await _看清(t)
    await t.nav.goto(Pose.from_xy_yaw(3.0, 4.0, 0.0))
    gid = link.kinds("goal")[-1]["goal_id"]
    await t.跑(0.5)
    link.goal_states.append({"type": "goal_state", "goal_id": gid, "state": "aborted",
                             "reason": "no valid path"})
    await t.跑(1.0)
    assert NavStatus.FAILED in t.status and "目标点被占" in t.nav.fail_reason
    assert t.nav.fail_code == "goal_occupied"
    assert t.nav.fail_final


async def test_W70_Nav2卡住不给速度也不回结果_过20秒重发同一个目标_最多两次(tmp_path):
    """11-03 15:00 C40221:Nav2 的 action server、清图服务都确认超时,原地空等到 120 s;
    重发一次就好了。"""
    from nexwar_agent.bridges.nav2_nav import NAV2_RESENDS, NAV2_STALL_S
    link = 假转接()
    t = _台(tmp_path, link)
    await t.start(1.5, 4.0)
    await t.nav.goto(Pose.from_xy_yaw(6.0, 4.0, 0.0))
    first = link.kinds("goal")[-1]
    await t.跑(NAV2_STALL_S - 3)
    assert len(link.kinds("goal")) == 1, "没到时候不重发"
    await t.跑(5.0)
    goals = link.kinds("goal")
    assert len(goals) == 2 and goals[-1]["goal_id"] != first["goal_id"]
    assert (goals[-1]["x"], goals[-1]["y"]) == (first["x"], first["y"])
    assert link.kinds("cancel")[-1]["goal_id"] == first["goal_id"]
    await t.跑((NAV2_STALL_S + 1) * (NAV2_RESENDS + 1))
    assert len(link.kinds("goal")) == 1 + NAV2_RESENDS, "最多重发两次"


async def test_W70_Nav2一直在给速度_不重发(tmp_path):
    link = 假转接()
    t = _台(tmp_path, link)
    await t.start(1.5, 4.0)
    await t.nav.goto(Pose.from_xy_yaw(9.0, 4.0, 0.0))
    gid = link.kinds("goal")[-1]["goal_id"]
    for _ in range(250):                                    # 25 s 一直有速度
        link.now += 0.1
        link.cmd = (link.now, gid, 0.2, 0.0, 0.0)
        await t.一拍()
    assert len(link.kinds("goal")) == 1


async def test_W70_离终点不到半米_15秒没再靠近_停在这儿算到(tmp_path):
    """11-03 17:16 商场 P8:终点离地图障碍 0.26 m(Nav2 的致命带里),机器人离终点 0.3 m
    前后来回 2 分钟。"""
    from nexwar_agent.bridges.nav2_nav import NEAR_STALL_S
    link = 假转接()
    t = _台(tmp_path, link)
    await t.start(1.5, 4.0)
    await t.nav.goto(Pose.from_xy_yaw(1.85, 4.0, 0.0))     # 离终点 0.35 m,朝向已对上
    gid = link.kinds("goal")[-1]["goal_id"]
    n = int((NEAR_STALL_S - 2) * 10)
    for i in range(n):                                      # Nav2 一直给前后来回的小速度
        link.now += 0.1
        link.cmd = (link.now, gid, 0.15 if i % 10 < 5 else -0.15, 0.0, 0.0)
        await t.一拍()
    assert NavStatus.SUCCEED not in t.status, "还不到时候"
    for i in range(60):
        link.now += 0.1
        link.cmd = (link.now, gid, 0.15 if i % 10 < 5 else -0.15, 0.0, 0.0)
        await t.一拍()
    assert NavStatus.SUCCEED in t.status
    assert link.kinds("cancel")[-1]["goal_id"] == gid


def _卡在台阶边(t, roll, at_x=-math.inf):
    """仿真狗:走到 ``at_x`` 以后,朝向跟台阶边差不到 25° 时腿在边上打滑,往前走不动;机身按 ``roll``
    歪着。"""
    from nexwar_contract.hal import ImuSample
    real = t.r.tick

    def tick(dt):
        x, y = t.r.x, t.r.y
        real(dt)
        if abs(math.remainder(t.r.yaw, 2 * math.pi)) < math.radians(25) and t.r.x > x \
                and x >= at_x:
            t.r.x, t.r.y = x, y

    async def imu():
        return ImuSample(stamp_ms=t.c(), roll=roll, pitch=0.06, shock_g=0.0, load=None,
                         valid=True)
    t.r.tick = tick
    t.r.imu = imu


async def test_W71_沿着台阶边打滑走不动_机身歪着_退一点转大角度再上_再交回Nav2(tmp_path):
    """11-03 商场 P2→P3 用户:「轮胎和阶梯角度不够大,轮胎一直卡在阶梯边缘出不来…
    要把角度调大才能出来」。"""
    from nexwar_agent.bridges.nav2_nav import EDGE_TURN_RAD
    link = 假转接()
    t = _台(tmp_path, link)
    # 外审 11-14:从 1.5 m 外走到台阶边才卡住(两侧盲带走过来时看过;一出现就卡着的话两侧从没看过,
    # 不许转身,得先挪看清)
    await t.start(0.2, 4.0)
    _卡在台阶边(t, roll=math.radians(-4.8), at_x=1.5)
    await t.nav.goto(Pose.from_xy_yaw(9.0, 4.0, 0.0))
    first = link.kinds("goal")[-1]
    yaws, track = [], []
    for _ in range(300):
        link.now += 0.1
        gid = link.kinds("goal")[-1]["goal_id"]
        link.cmd = (link.now, gid, 0.4, 0.0, 0.0)
        await t.一拍()
        if track or t.r.x >= 1.5:
            yaws.append(t.r.yaw)
            track.append((t.r.x, t.r.yaw))
    turned = next(i for i, (_, y) in enumerate(track) if y > EDGE_TURN_RAD * 0.8)
    backed = next(i for i, (x, _) in enumerate(track) if x < 1.4)
    assert turned < backed, "用户:「困着的时候应该先转角度 再后退」"
    assert link.kinds("cancel") and link.kinds("cancel")[0]["goal_id"] == first["goal_id"]
    assert max(yaws) > EDGE_TURN_RAD * 0.8, "左边低(roll < 0):往左转大角度"
    goals = link.kinds("goal")
    assert len(goals) >= 2 and (goals[-1]["x"], goals[-1]["y"]) == (9.0, 4.0), "脱完交回 Nav2"
    assert t.r.x > 2.0, "转过来就上去了"


async def test_W71_走不动但机身是平的_不做台阶脱困(tmp_path):
    link = 假转接()
    t = _台(tmp_path, link)
    await t.start(1.5, 4.0)
    _卡在台阶边(t, roll=0.0)
    await t.nav.goto(Pose.from_xy_yaw(9.0, 4.0, 0.0))
    for _ in range(100):
        link.now += 0.1
        link.cmd = (link.now, link.kinds("goal")[-1]["goal_id"], 0.4, 0.0, 0.0)
        await t.一拍()
    assert not link.kinds("cancel") and abs(t.r.yaw) < 0.05


async def test_W71_机器人自己四周都被判成挡_Nav2失败_说机器人被困_不说目标点被占(tmp_path):
    """11-03 17:28 商场 P2→P3:机身歪着,身边一圈都被判成凸起,Nav2「Starting point in lethal space」,
    代理却报「目标点被占」。"""
    link = 假转接()
    t = _台(tmp_path, link)
    await t.start(1.5, 4.0)
    for k, box in {"前": (2.25, 3.5, 2.45, 4.5), "后": (0.55, 3.5, 0.75, 4.5),
                   "左": (1.0, 4.5, 2.0, 4.7), "右": (1.0, 3.3, 2.0, 3.5)}.items():
        t.world.dyn[k] = box
    await _看清(t)
    await t.nav.goto(Pose.from_xy_yaw(8.0, 4.0, 0.0))
    gid = link.kinds("goal")[-1]["goal_id"]
    await t.跑(0.5)
    link.goal_states.append({"type": "goal_state", "goal_id": gid, "state": "aborted",
                             "reason": "no valid path"})
    await t.跑(1.0)
    assert NavStatus.FAILED in t.status and "被困" in t.nav.fail_reason, t.nav.fail_reason
    assert "目标点被占" not in t.nav.fail_reason and not t.nav.fail_final
    assert t.nav.fail_code == "robot_trapped"


async def test_W71_目标点贴着地图墙_交给Nav2之前挪到最近能站的点(tmp_path):
    """11-03 商场:站点查可达时把贴墙的点挪进来算(intercept_reach.snap),说「到得了」;机器人却把原点
    交给 Nav2,Nav2 判终点在致命带里规划失败。自己的规划早就会挪(工单 20),Nav2 这条路也挪。"""
    from nexwar_agent.bridges.planned_nav import GOAL_SNAP_M
    link = 假转接()
    t = _台(tmp_path, link, walls=[(0.1, 4.7, 11.9, 4.8)])
    await t.start(1.5, 4.0)
    await t.nav.goto(Pose.from_xy_yaw(6.0, 4.3, 0.3))               # 离墙面 0.4 m:站点照收
    g = link.kinds("goal")[-1]
    assert g["y"] < 4.3 and math.dist((g["x"], g["y"]), (6.0, 4.3)) <= GOAL_SNAP_M + 1e-6, g
    assert g["yaw"] == pytest.approx(0.3), "朝向不变"
    await t.nav.stop()
    await t.跑(1.0)
    await t.跑(1.0)
    await t.nav.goto(Pose.from_xy_yaw(6.0, 3.0, 0.0))            # 空地上的点原样
    g = link.kinds("goal")[-1]
    assert (g["x"], g["y"]) == (6.0, 3.0)


def _晃(i):
    """原地前后晃:0.2 m/s 往前 1 s、往后 1 s(离目标的远近变不到 0.3 m,算没进展)。"""
    return 0.2 if (i // 10) % 2 == 0 else -0.2


async def test_W72_离终点还远_原地打转30秒没进展_报被挡_走起来了报恢复(tmp_path):
    """用户 11-03:导航卡住几十秒要给站点告警(站点一分钟报 P2,恢复了自动解除);11-03 绕人贴着沙发,
    Nav2 自己原地转了 70 秒,守卫没拦,站点什么都不知道。"""
    from nexwar_agent.bridges.nav2_nav import NAV2_NO_PROGRESS_S
    link = 假转接()
    t = _台(tmp_path, link)
    await t.start(1.5, 4.0)
    await t.nav.goto(Pose.from_xy_yaw(9.0, 4.0, 0.0))
    gid = link.kinds("goal")[-1]["goal_id"]
    blocked = lambda: [d for k, d in t.events if k == "nav_blocked"]   # noqa: E731
    # Nav2 一直原地前后晃(外审 11-14 起原地转超过 10 s 两侧记忆过期、守卫拦,另走被挡那条路报)
    n = int((NAV2_NO_PROGRESS_S - 3) * 10)
    for i in range(n):
        link.now += 0.1
        link.cmd = (link.now, gid, _晃(i), 0.0, 0.0)
        await t.一拍()
    assert blocked() == [], "还不到时候"
    for i in range(n, n + 50):
        link.now += 0.1
        link.cmd = (link.now, gid, _晃(i), 0.0, 0.0)
        await t.一拍()
    [b] = blocked()
    assert "没向目标靠近" in b["reason"] and b["waited_s"] >= NAV2_NO_PROGRESS_S
    for _ in range(40):                                     # 转回来、往前走起来了
        link.now += 0.1
        wz = -0.3 if t.r.yaw > 0.05 else (0.3 if t.r.yaw < -0.05 else 0.0)
        link.cmd = (link.now, gid, 0.5, 0.0, wz)
        await t.一拍()
    assert ("nav_unblocked" in [k for k, _ in t.events]), "有进展了:报恢复,站点那条自动解除"
    assert len(blocked()) == 1


async def test_W72_一直在往前走_绕远路也不算卡住(tmp_path):
    from nexwar_agent.bridges.nav2_nav import NAV2_NO_PROGRESS_S
    link = 假转接()
    t = _台(tmp_path, link)
    await t.start(1.5, 4.0)
    await t.nav.goto(Pose.from_xy_yaw(1.5, 1.0, 0.0))     # 目标在身后
    gid = link.kinds("goal")[-1]["goal_id"]
    for _ in range(int((NAV2_NO_PROGRESS_S + 10) * 10)):   # 往前(背离目标)绕远路一直在走
        link.now += 0.1
        link.cmd = (link.now, gid, 0.3, 0.0, 0.0)
        await t.一拍()
        if t.r.x > 10.5:
            break
    assert [d for k, d in t.events if k == "nav_blocked"] == []


async def test_W72_换了新目标_进展从头算_不拿上一个目标的时刻误报(tmp_path):
    from nexwar_agent.bridges.nav2_nav import NAV2_NO_PROGRESS_S
    link = 假转接()
    t = _台(tmp_path, link)
    await t.start(1.5, 4.0)
    await t.nav.goto(Pose.from_xy_yaw(5.0, 4.0, 0.0))
    gid = link.kinds("goal")[-1]["goal_id"]
    for i in range(int((NAV2_NO_PROGRESS_S - 5) * 10)):     # 原地晃了 25 秒(还没报)
        link.now += 0.1
        link.cmd = (link.now, gid, _晃(i), 0.0, 0.0)
        await t.一拍()
    await t.nav.stop()
    await t.跑(1.0)
    await t.nav.goto(Pose.from_xy_yaw(1.5, 9.0, 0.0))       # 换成更远的目标
    gid = link.kinds("goal")[-1]["goal_id"]
    for i in range(80):                                     # 新目标上晃了 8 秒
        link.now += 0.1
        link.cmd = (link.now, gid, _晃(i), 0.0, 0.0)
        await t.一拍()
    assert [d for k, d in t.events if k == "nav_blocked"] == []


def _残影(tmp_path, x, y):
    """在 floor.pgm 上 (x, y) 点一格挡(扫图时的人、摊位留下的残影;现场其实是空的)。"""
    import numpy as np
    from obs_world import RES
    raw = (tmp_path / "floor.pgm").read_bytes()
    w, h = map(int, raw.split(b"\n")[1].split())
    body = raw[len(b"\n".join(raw.split(b"\n")[:3])) + 1:]
    img = np.frombuffer(body, dtype=np.uint8).reshape(h, w).copy()
    img[h - 1 - int(y / RES), int(x / RES)] = 0
    (tmp_path / "floor.pgm").write_bytes(b"P5\n%d %d\n255\n" % (w, h) + img.tobytes())


async def test_现场1105_站在地图残影上_Nav2说起点致命_机身底下临时当空_说清楚再试(tmp_path):
    """11-05 商场原点、广场窄口:机器人站的那格在静态图上是挡(残影),Nav2「Starting point in lethal
    space」55 次,倒车脱困也被挡;原来报「身边一圈都被判成障碍」。机器人站着的地方一定是空的。"""
    link = 假转接()
    t = _台(tmp_path, link)
    _残影(tmp_path, 1.5, 4.0)
    t.nav.load_grid(tmp_path)
    await t.start(1.5, 4.0)
    await _看清(t)
    await t.nav.goto(Pose.from_xy_yaw(8.0, 4.0, 0.0))
    gid = link.kinds("goal")[-1]["goal_id"]
    await t.跑(0.5)
    link.goal_states.append({"type": "goal_state", "goal_id": gid, "state": "aborted",
                             "reason": "GridBased: failed to create plan, invalid use: "
                                       "Starting point in lethal space!"})
    await t.跑(1.0)
    why = t.nav.fail_reason
    assert NavStatus.FAILED in t.status and "残影" in why and "清理" in why, why
    assert "一圈" not in why and not t.nav.fail_final, "临时擦了,引擎再试一次"
    m = link.kinds("map")[-1]
    [c] = m["clear"]
    assert math.dist(c[:2], (1.5, 4.0)) < 0.2 and len(c) == 5, c


async def test_现场1105_站在禁行区边上_Nav2说起点致命_说先挪出来_不擦禁行区(tmp_path):
    from nexwar_contract.zones import Zone, ZoneSet
    link = 假转接()
    t = _台(tmp_path, link)
    await t.start(1.5, 4.0)
    await t.nav.set_zones(ZoneSet(map_id="m", map_version="1", revision=1, zones=(
        Zone(id="z", kind="nogo", label="栏杆", polygon=((1.3, 3.8), (3.0, 3.8), (3.0, 3.0),
                                                        (1.3, 3.0))),)))
    await _看清(t)
    t.nav._target = Pose.from_xy_yaw(8.0, 4.0, 0.0)
    t.r.teleport(1.5, 3.7, 0.0)                       # 机身压着禁行区边
    await t.跑(0.2)
    await t.nav._nav2_failed({"state": "aborted",
                              "reason": "Starting point in lethal space!"}, await t.nav._here())
    why = t.nav.fail_reason
    assert "禁行区" in why and "挪" in why and "残影" not in why, why
    assert not link.kinds("map")[-1].get("clear"), "禁行区不擦"


# ------------------------------------------------------------ W74 跟随:走着换目标


async def test_W74_走着换目标_Nav2收到新目标号_旧的取消_不在走就不换(tmp_path):
    link = 假转接()
    t = _台(tmp_path, link)
    await t.start(1.5, 4.0)
    assert await t.nav.retarget(Pose.from_xy_yaw(5.0, 4.0)) is False, "没在走:不换(要 goto)"
    await t.nav.goto(Pose.from_xy_yaw(6.0, 4.0, 0.0))
    await t.跑(0.3)
    g1 = link.kinds("goal")[-1]
    assert await t.nav.retarget(Pose.from_xy_yaw(7.0, 5.0, 0.5)) is True
    g2 = link.kinds("goal")[-1]
    assert g2["goal_id"] > g1["goal_id"] and (g2["x"], g2["y"], g2["yaw"]) == (7.0, 5.0, 0.5)
    assert "via" not in g2, "跟人不走路网"
    assert link.kinds("cancel")[-1]["goal_id"] == g1["goal_id"]
    assert t.nav._target.position.x == 7.0
    assert NavStatus.FAILED not in t.status


async def test_W74_换的新目标在禁行区里_不换(tmp_path):
    from nexwar_contract.zones import ZoneSet
    link = 假转接()
    t = _台(tmp_path, link)
    await t.start(1.5, 4.0)
    await t.nav.set_zones(ZoneSet.from_wire({"map_id": "m", "map_version": "1", "revision": 1,
                                             "zones": [
        {"id": "z", "kind": "nogo", "polygon": [[8, 3], [9, 3], [9, 5], [8, 5]]}]}))
    await t.nav.goto(Pose.from_xy_yaw(6.0, 4.0, 0.0))
    await t.跑(0.3)
    n = len(link.kinds("goal"))
    assert await t.nav.retarget(Pose.from_xy_yaw(8.5, 4.0)) is False
    assert len(link.kinds("goal")) == n


async def test_W74_自己的规划_走着换目标_从这儿重新规划过去(tmp_path):
    t = 台子(tmp_path)
    await t.start(1.5, 4.0)
    assert await t.nav.retarget(Pose.from_xy_yaw(5.0, 4.0)) is False
    await t.nav.goto(Pose.from_xy_yaw(6.0, 4.0, 0.0))
    await t.跑(1.0)
    assert await t.nav.retarget(Pose.from_xy_yaw(4.0, 6.0, 1.5)) is True
    await t.跑(40.0)
    assert NavStatus.SUCCEED in t.status and not t.crashed
    assert math.dist((t.r.x, t.r.y), (4.0, 6.0)) < 0.4, "到的是新目标"


# ---------------------------------------- 导航 V1 第 1 节:D 守卫(SAFE / SLOW / STOP)


def _按余量答(full_hits, soft_ok_at):
    """假守卫:按全余量查 → 给 full_hits;
    按软余量(多留的比全余量少)查、速度不超过 soft_ok_at → 放行。"""
    from nexwar_agent.obstacles import Verdict
    calls = []

    def guard(vx, wz, g=None):
        soft = g is not None and g.extra < 0.3 - 1e-9
        calls.append((round(vx, 3), round(wz, 3), "soft" if soft else "full"))
        if soft and abs(vx) <= soft_ok_at + 1e-9:
            return Verdict(True)
        return Verdict(False, "扫过区有挡", hits=full_hits)
    return guard, calls


async def test_外审1114_挡的全是地图墙_也按全余量停_不再软放行(tmp_path):
    """外审 11-14、用户定:删掉贴墙软放行。原来全余量查到的挡全在地图墙 0.2 m 以内,就降速、少留余量
    放过去 —— 墙边站着的人、箱子也被当墙,定位偏了更说不准。看得见的挡一律按全余量停。"""
    link = 假转接()
    t = _台(tmp_path, link, walls=[(0.1, 4.6, 11.9, 4.7)])  # 机身左边 0.6 m 有一道地图墙
    await t.start(1.5, 4.0)
    await t.nav.goto(Pose.from_xy_yaw(9.0, 4.0))
    guard, calls = _按余量答(full_hits=((1.0, 0.62),), soft_ok_at=0.6)   # 挡在墙上,少留余量就过得去
    t.nav._guard_check = guard
    for _ in range(12):
        link.now += 0.1
        link.cmd = (link.now, 1, 0.6, 0.0, 0.3)
        await t.一拍()
    assert abs(t.r.speed[0]) < 0.05 and abs(t.r.speed[1]) < 0.05, t.r.speed
    assert "soft" not in {c[2] for c in calls}, "不再试少留余量"


async def test_V1_看不见的只降速时_转向同比例压(tmp_path):
    from nexwar_agent.bridges.nav2_nav import UNKNOWN_SLOW_MPS
    from nexwar_agent.obstacles import Verdict
    link = 假转接()
    t = _台(tmp_path, link)
    await t.start(1.5, 4.0)
    await t.nav.goto(Pose.from_xy_yaw(9.0, 4.0))

    def guard(vx, wz, g=None):
        if abs(vx) > UNKNOWN_SLOW_MPS + 1e-9:
            return Verdict(False, "看不见 3 处", hits=(), unknown=3, kind="unknown")
        return Verdict(True)
    t.nav._guard_check = guard
    for _ in range(15):
        link.now += 0.1
        link.cmd = (link.now, 1, 0.6, 0.0, 0.4)
        await t.一拍()
    assert t.r.speed[0] == pytest.approx(UNKNOWN_SLOW_MPS, abs=0.02)
    assert t.r.speed[1] == pytest.approx(0.4 * UNKNOWN_SLOW_MPS / 0.6, abs=0.02)


# ---------------------------------------- 导航 V1 第 1 节:遮挡限速(看不见的区域主动限速)


async def _遮挡(t, n=25):
    # 车后面从雷达看过去是看不见的;等 2.5 s,打开阴影之前那几帧(全看得见)过了记忆
    t.per.shadow = True
    for _ in range(n):
        await t.一拍()
    return t.nav._occ_cap(await t.nav._here(), 1)


async def test_V1_遮挡限速_前方路边停着车_车后面的阴影可能冒出人_限速(tmp_path):
    """仿真 ab_parking_delay300(D 组 s8):人从两车之间冲出,0.42 m/s 撞上。车后面那片看不见的、
    跟机身走廊之间没有挡:按「反应 + 刹车」限速。"""
    from nexwar_agent.bridges.nav2_nav import V_FAST
    t = _台(tmp_path, 假转接())
    await t.start(1.5, 4.0)
    t.world.dyn["car"] = (2.6, 4.45, 3.2, 5.4)              # 机头前 0.6 m 起、走廊左边 0.1 m 外
    v = await _遮挡(t)
    # 人最早从车的远端(机头前约 1.2 m)冒出来:反应 0.5 s + 0.5 m/s² 刹车,停在它前面 0.1 m → 约 0.84
    assert 0.75 < v < 0.9 < V_FAST, v
    t.world.dyn["car"] = (2.1, 4.45, 2.5, 5.4)              # 车挨着机头:冒出点 0.5 m 内
    assert await _遮挡(t) == pytest.approx(0.2 + 0.31, abs=0.12)


async def test_V1_遮挡限速_空地不限(tmp_path):
    from nexwar_agent.bridges.nav2_nav import V_FAST
    t = _台(tmp_path, 假转接())
    await t.start(1.5, 4.0)
    assert await _遮挡(t) == pytest.approx(V_FAST)


async def test_V1_遮挡限速_走廊两边是地图墙_墙外的阴影不算(tmp_path):
    from nexwar_agent.bridges.nav2_nav import V_FAST
    t = _台(tmp_path, 假转接(), walls=[(0.1, 3.2, 11.9, 3.3), (0.1, 4.7, 11.9, 4.8)])
    await t.start(1.5, 4.0)
    assert await _遮挡(t) == pytest.approx(V_FAST)


async def test_V1_遮挡限速_E1按距离分档_关掉不限(tmp_path, monkeypatch):
    from nexwar_agent.bridges import nav2_nav
    t = _台(tmp_path, 假转接())
    await t.start(1.5, 4.0)
    t.world.dyn["car"] = (2.6, 4.45, 3.2, 5.4)
    monkeypatch.setattr(nav2_nav, "OCC_ALGO", "E1")
    assert await _遮挡(t) == pytest.approx(0.4)             # 阴影离机身 1–2 m
    monkeypatch.setattr(nav2_nav, "OCC_ALGO", "")
    assert t.nav._occ_cap(await t.nav._here(), 1) == pytest.approx(nav2_nav.V_FAST)


async def test_V1_遮挡限速_算进看得清就快_也送给Nav2(tmp_path):
    link = 假转接()
    t = _台(tmp_path, link)
    await t.start(1.5, 4.0)
    t.world.dyn["car"] = (2.6, 4.45, 3.2, 5.4)
    await t.nav.goto(Pose.from_xy_yaw(9.0, 4.0))
    for _ in range(10):
        link.now += 0.1
        link.cmd = (link.now, 1, 0.9, 0.0, 0.0)
        await t.一拍()
    occ = t.nav._occ_cap(await t.nav._here(), 1)
    assert t.nav._vis <= occ + 1e-6, (t.nav._vis, occ)


async def test_V1_遮挡限速_锥形视野_机头两侧刚刚看见过的不算_不一直压蠕行(tmp_path):
    """C40221 实测视野是锥形(机头两侧 1 m 内此刻看不见):往前走时那片刚刚看见过,不当阴影。"""
    from nexwar_agent.bridges.nav2_nav import V_FAST
    link = 假转接()
    t = _台(tmp_path, link, cone=True)
    await t.start(1.5, 4.0)
    first = t.nav._occ_cap(await t.nav._here(), 1)
    await t.nav.goto(Pose.from_xy_yaw(9.0, 4.0))
    for _ in range(40):                                     # 往前走 2 m 左右
        link.now += 0.1
        link.cmd = (link.now, 1, 0.5, 0.0, 0.0)
        await t.一拍()
    later = t.nav._occ_cap(await t.nav._here(), 1)
    assert later > 0.8 * V_FAST, (first, later)


async def test_V1_遮挡限速_车停在侧面1米外_车后的阴影也要限速(tmp_path, monkeypatch):
    """仿真 DE2 ab_parking_delay300 s33:人从横向 1.46 m 外的车后冒出,E2 只看 1.0 m 以内,
    遮挡限速一次没起作用,撞上。看到 2.0 m 以后(DE3)200 趟 0 碰撞。
    车摆在机头前 1.1–1.5 m、走廊边外 1.0–1.3 m:车后的阴影在视野锥里、离走廊边 1.0 m 以外。"""
    from nexwar_agent.bridges import nav2_nav
    t = _台(tmp_path, 假转接())
    await t.start(1.5, 4.0)
    t.world.dyn["car"] = (3.1, 5.29, 3.5, 5.6)
    v = await _遮挡(t)
    assert v < nav2_nav.V_FAST - 0.01, v
    monkeypatch.setattr(nav2_nav, "OCC_E2_SIDE_M", 1.0)     # 老的 1.0 m:看不到,不限
    assert t.nav._occ_cap(await t.nav._here(), 1) == pytest.approx(nav2_nav.V_FAST)


# ---------------------------------------- 导航 V1 第 2 节:Route Validator V1.0(出发前查路线)


class 会规划的转接(假转接):
    """收到 ``plan`` 当场回 ``plan_result``:直线连到目标(朝向照目标),或者按 ``answer`` 回。"""

    def __init__(self, answer=None):
        super().__init__()
        self.plan_results: dict = {}
        self.answer = answer

    def send(self, m):
        if m["type"] == "plan":
            if self.answer == "silent":
                self.sent.append(m)
                return True
            gx, gy, gyaw = m["goal"]
            sx, sy, _ = m.get("start") or [self.here[0], self.here[1], 0.0]
            n = max(1, int(math.dist((sx, sy), (gx, gy)) / 0.025))
            poses = [[sx + (gx - sx) * i / n, sy + (gy - sy) * i / n, gyaw] for i in range(n + 1)]
            res = {"type": "plan_result", "req_id": m["req_id"], "ok": True, "poses": poses}
            if self.answer is not None:
                res = {"type": "plan_result", "req_id": m["req_id"], **self.answer}
            self.plan_results[m["req_id"]] = res
        return super().send(m)


def _窄走廊(width):
    """y = 4 为中心、x 0.5–11.5 的走廊,宽 ``width``(墙在地图里)。"""
    h = width / 2
    return [(0.1, 0.1, 11.9, 4.0 - h), (0.1, 4.0 + h, 11.9, 7.9)]


async def test_V1_路线检查_走廊太窄_出发前拒绝_报最窄处_不发目标(tmp_path):
    from nexwar_patrol.backends.base import NavRequestError
    link = 会规划的转接()
    t = _台(tmp_path, link, walls=_窄走廊(0.7))
    await t.start(1.5, 4.0)
    link.here = (1.5, 4.0)
    with pytest.raises(NavRequestError) as e:
        await t.nav.goto(Pose.from_xy_yaw(9.0, 4.0))
    assert e.value.code == "route_too_narrow" and e.value.final, e.value
    assert "离墙只剩" in str(e.value) and "0.78" in str(e.value)
    assert link.kinds("plan") and not link.kinds("goal"), "拒了就不交给 Nav2"
    assert t.nav._status is NavStatus.STANDBY and not t.nav._planning


async def test_两种走法_紧急任务不做路线检查_直接交给Nav2_回到普通又查(tmp_path):
    """用户 11-09:跟可疑人物、报警出动这类紧急任务不走路线检查,走最快的路;普通巡逻照查。"""
    from nexwar_patrol.backends.base import NavRequestError
    link = 会规划的转接()
    t = _台(tmp_path, link, walls=_窄走廊(0.7))
    await t.start(1.5, 4.0)
    link.here = (1.5, 4.0)
    await t.nav.set_urgent(True)
    await t.nav.goto(Pose.from_xy_yaw(9.0, 4.0))
    assert not link.kinds("plan") and link.kinds("goal"), "紧急:不查,直接交给 Nav2"
    link2 = 会规划的转接()
    (tmp_path / "2").mkdir()
    t2 = _台(tmp_path / "2", link2, walls=_窄走廊(0.7))
    await t2.start(1.5, 4.0)
    link2.here = (1.5, 4.0)
    await t2.nav.set_urgent(True)
    await t2.nav.set_urgent(False)
    with pytest.raises(NavRequestError) as e:
        await t2.nav.goto(Pose.from_xy_yaw(9.0, 4.0))
    assert e.value.code == "route_too_narrow", "回到普通:照查"


def _走廊路网():
    from nexwar_contract.routenet import RouteNet
    return RouteNet.from_wire({"map_id": "m", "map_version": "", "revision": 1,
                               "nodes": [{"id": "A", "x": 1.5, "y": 4.0},
                                         {"id": "B", "x": 5.0, "y": 4.0},
                                         {"id": "C", "x": 9.0, "y": 4.0}],
                               "edges": [["A", "B"], ["B", "C"]]})


async def test_外审POC_I5_有路网的普通任务_照样查路线_查的是沿路网走的那条(tmp_path):
    """codex POC r1 I5:有路网(途经点)时整段路线检查被跳过,0.10 m 底线没查。"""
    from nexwar_patrol.backends.base import NavRequestError
    link = 会规划的转接()
    t = _台(tmp_path, link, walls=_窄走廊(0.7))
    await t.start(1.5, 4.0)
    link.here = (1.5, 4.0)
    t.nav.set_route_net(_走廊路网())
    with pytest.raises(NavRequestError) as e:
        await t.nav.goto(Pose.from_xy_yaw(9.0, 4.0))
    assert e.value.code == "route_too_narrow" and e.value.final, e.value
    assert not link.kinds("goal"), "拒了就不交给 Nav2"
    assert t.nav._status is NavStatus.STANDBY and not t.nav._planning
    await t.nav.set_urgent(True)                           # 紧急:照旧不查
    await t.nav.goto(Pose.from_xy_yaw(9.0, 4.0))
    assert link.kinds("goal")[-1].get("via")


async def test_外审POC_I5_有路网_走廊够宽_查过照常带途经点交给Nav2(tmp_path):
    link = 会规划的转接()
    t = _台(tmp_path, link, walls=_窄走廊(1.4))
    await t.start(1.5, 4.0)
    link.here = (1.5, 4.0)
    t.nav.set_route_net(_走廊路网())
    await t.nav.goto(Pose.from_xy_yaw(9.0, 4.0))
    assert link.kinds("goal")[-1].get("via")


async def test_V1_路线检查_走廊够宽_查过再交给Nav2(tmp_path):
    link = 会规划的转接()
    t = _台(tmp_path, link, walls=_窄走廊(1.4))
    await t.start(1.5, 4.0)
    link.here = (1.5, 4.0)
    await t.nav.goto(Pose.from_xy_yaw(9.0, 4.0))
    [p] = link.kinds("plan")
    assert p["goal"][:2] == pytest.approx([9.0, 4.0]) and link.kinds("goal")
    assert p["start"][:2] == pytest.approx([1.5, 4.0], abs=0.05)


async def test_V1_路线检查_转接节点不回_等一会儿照常交给Nav2(tmp_path, monkeypatch):
    from nexwar_agent.bridges import nav2_nav
    monkeypatch.setattr(nav2_nav, "PLAN_WAIT_S", 0.3)
    link = 会规划的转接(answer="silent")
    t = _台(tmp_path, link, walls=_窄走廊(0.85))
    await t.start(1.5, 4.0)
    link.here = (1.5, 4.0)
    await t.nav.goto(Pose.from_xy_yaw(9.0, 4.0))
    assert link.kinds("goal"), "检查做不成不挡路(Nav2 自己还有守卫、恢复)"


async def test_V1_路线检查_规划器说没路_照常交给Nav2_由它报失败(tmp_path):
    link = 会规划的转接(answer={"ok": False, "poses": [], "reason": "no_path"})
    t = _台(tmp_path, link, walls=_窄走廊(1.4))
    await t.start(1.5, 4.0)
    link.here = (1.5, 4.0)
    await t.nav.goto(Pose.from_xy_yaw(9.0, 4.0))
    assert link.kinds("goal")



def _没查成(t):
    return [d for k, d in t.events if k == "route_unchecked"]


async def test_外审_路线没查成_守卫健康_上报没查成_照常交给Nav2(tmp_path, monkeypatch):
    """外审 11-14(用户定):超时、检查不可用 → 标「未完成检查」;只在运行时守卫健康时继续。"""
    from nexwar_agent.bridges import nav2_nav
    monkeypatch.setattr(nav2_nav, "PLAN_WAIT_S", 0.3)
    link = 会规划的转接(answer="silent")
    t = _台(tmp_path, link, walls=_窄走廊(1.4))
    await t.start(1.5, 4.0)
    link.here = (1.5, 4.0)
    await t.nav.goto(Pose.from_xy_yaw(9.0, 4.0))
    assert link.kinds("goal")
    [ev] = _没查成(t)
    assert ev["code"] == "route_check_timeout" and ev["guard_ok"] is True, ev


async def test_外审_路线没查成_守卫不健康_不出发_可以再派(tmp_path, monkeypatch):
    from nexwar_agent.bridges import nav2_nav
    from nexwar_patrol.backends.base import NavRequestError
    monkeypatch.setattr(nav2_nav, "PLAN_WAIT_S", 0.3)
    link = 会规划的转接(answer="silent")
    t = _台(tmp_path, link, walls=_窄走廊(1.4))
    await t.start(1.5, 4.0)
    link.here = (1.5, 4.0)
    monkeypatch.setattr(t.nav.obstacles, "state", lambda: "lost")
    with pytest.raises(NavRequestError) as e:
        await t.nav.goto(Pose.from_xy_yaw(9.0, 4.0))
    assert e.value.code == "robot_not_ready" and not e.value.final, e.value
    assert "没查成" in str(e.value) and "障碍数据" in str(e.value)
    assert not link.kinds("goal")
    assert _没查成(t)[0]["guard_ok"] is False
    assert t.nav._status is NavStatus.STANDBY and not t.nav._planning


async def test_外审_紧急任务不查路线_也算没查成_要守卫健康(tmp_path, monkeypatch):
    from nexwar_patrol.backends.base import NavRequestError
    link = 会规划的转接()
    t = _台(tmp_path, link, walls=_窄走廊(0.7))
    await t.start(1.5, 4.0)
    link.here = (1.5, 4.0)
    await t.nav.set_urgent(True)
    await t.nav.goto(Pose.from_xy_yaw(9.0, 4.0))
    assert _没查成(t)[0]["code"] == "urgent"
    link2 = 会规划的转接()
    (tmp_path / "2").mkdir()
    t2 = _台(tmp_path / "2", link2, walls=_窄走廊(0.7))
    await t2.start(1.5, 4.0)
    link2.here = (1.5, 4.0)
    await t2.nav.set_urgent(True)
    monkeypatch.setattr(t2.nav.obstacles, "state", lambda: "stale")
    with pytest.raises(NavRequestError) as e:
        await t2.nav.goto(Pose.from_xy_yaw(9.0, 4.0))
    assert e.value.code == "robot_not_ready" and not link2.kinds("goal")


async def test_外审_规划器说没路_算没查成_守卫健康时交给Nav2报失败(tmp_path):
    link = 会规划的转接(answer={"ok": False, "poses": [], "reason": "no_path"})
    t = _台(tmp_path, link, walls=_窄走廊(1.4))
    await t.start(1.5, 4.0)
    link.here = (1.5, 4.0)
    await t.nav.goto(Pose.from_xy_yaw(9.0, 4.0))
    assert link.kinds("goal")
    assert _没查成(t)[0]["code"] == "no_route"


# ---------------------------------------- 导航 V1 第 3、4 节:卡住了自己脱困(恢复链)


def _死胡同(width, end_x=6.0):
    """y = 4 为中心、宽 ``width`` 的走廊,x = ``end_x`` 处封死。"""
    h = width / 2
    return [(0.1, 0.1, end_x + 1.0, 4.0 - h), (0.1, 4.0 + h, end_x + 1.0, 7.9),
            (end_x, 4.0 - h, end_x + 1.0, 4.0 + h)]


async def _跑到(t, cond, seconds):
    for _ in range(int(seconds / 0.1)):
        await t.一拍()
        if cond():
            return True
    return False


def _步(t):
    return [d for k, d in t.events if k == "recovery_step"]


async def test_脱困_一米三死胡同_Nav2规划不出_自己挪着掉头_再交给Nav2_不撞(tmp_path):
    """用户 11-07(广场 1.3 m 死胡同):这条路必须能过 —— 机器人自己前后挪、分段转,掉过头来再走。"""
    link = 假转接()
    t = _台(tmp_path, link, walls=_死胡同(1.3))
    await t.start(5.0, 4.0, 0.0)
    await t.nav.goto(Pose.from_xy_yaw(1.5, 4.0, math.pi))
    [g] = link.kinds("goal")
    link.goal_states.append({"goal_id": g["goal_id"], "state": "aborted",
                             "reason": "GridBased: failed to create plan"})
    ok = await _跑到(t, lambda: len(link.kinds("goal")) >= 2, 90.0)
    assert ok, (t.events, t.status)
    assert not t.crashed, "挪的时候不许蹭墙"
    assert abs(math.remainder(t.r.yaw - math.pi, 2 * math.pi)) < math.radians(30), t.r.yaw
    assert NavStatus.FAILED not in t.status
    steps = _步(t)
    assert steps and steps[0]["action"] == "maneuver" and steps[-1]["ok"] is True, steps


async def test_脱困_原地没进展_先重新规划_再挪_都不行停下报自动恢复试过了(tmp_path):
    """恢复链(导航 V1 第 3 节):没进展 → 重新规划 → 自己挪 → 停下说原因,不一直耗着。"""
    from nexwar_agent.bridges import nav2_nav
    link = 假转接()
    t = _台(tmp_path, link, walls=_死胡同(0.9))           # 0.9 m:机身怎么挪都掉不了头
    await t.start(5.0, 4.0, 0.0)
    await t.nav.goto(Pose.from_xy_yaw(1.5, 4.0, math.pi))
    # Nav2 一直让原地左右扭(打转):速度在、结果不回
    sign = [1.0]

    def 扭():
        sign[0] = -sign[0]
        link.now = t.c.s()
        link.cmd = (link.now, 0, 0.0, 0.0, 0.3 * sign[0], link.kinds("goal")[-1]["goal_id"], "beh")
    total = 3 * nav2_nav.RECOVER_AFTER_S + nav2_nav.MANEUVER_MAX_S + 30
    for _ in range(int(total / 0.1)):
        扭()
        await t.一拍()
        if NavStatus.FAILED in t.status:
            break
    assert NavStatus.FAILED in t.status, (t.events, t.status)
    assert t.nav.fail_code == "controller_stalled"
    actions = [s["action"] for s in _步(t)]
    assert actions[0] == "replan" and "maneuver" in actions and actions[-1] == "give_up", actions
    assert not t.crashed


async def test_脱困_有进展就从头算_不往下一级走(tmp_path):
    from nexwar_agent.bridges import nav2_nav
    link = 假转接()
    t = _台(tmp_path, link, walls=_窄走廊(1.4))
    await t.start(1.5, 4.0, 0.0)
    await t.nav.goto(Pose.from_xy_yaw(11.0, 4.0))
    gid = link.kinds("goal")[-1]["goal_id"]
    for _ in range(int((nav2_nav.RECOVER_AFTER_S * 1.4) / 0.1)):
        link.now = t.c.s()
        link.cmd = (link.now, 0, 0.3, 0.0, 0.0, link.kinds("goal")[-1]["goal_id"], "beh")
        await t.一拍()
    assert t.r.x > 6.0, t.r.x
    assert not _步(t), "一直在往前走:不触发恢复"
    assert link.kinds("goal")[-1]["goal_id"] == gid


async def test_脱困_走着走着卡住_重新规划不管用_沿原路退回去再规划(tmp_path):
    """用户 11-10:脱困的一种办法是退回原来走过的点再重新规划 —— 原路是刚走过的,一定走得通。"""
    from nexwar_agent.bridges import nav2_nav
    link = 假转接()
    t = _台(tmp_path, link, walls=_窄走廊(1.4))
    await t.start(1.5, 4.0, 0.0)
    await t.nav.goto(Pose.from_xy_yaw(11.0, 4.0))
    for _ in range(100):                                  # 先正常往前走 10 秒
        link.now = t.c.s()
        link.cmd = (link.now, 0, 0.3, 0.0, 0.0, link.kinds("goal")[-1]["goal_id"], "beh")
        await t.一拍()
    x_stuck = t.r.x
    assert x_stuck > 3.5, x_stuck
    sign = [1.0]
    n_goals = len(link.kinds("goal"))

    def 扭():
        sign[0] = -sign[0]
        link.now = t.c.s()
        link.cmd = (link.now, 0, 0.0, 0.0, 0.3 * sign[0], link.kinds("goal")[-1]["goal_id"], "beh")

    def 退完():
        return any(s["action"] == "retreat" and s["ok"] is not None for s in _步(t))
    for _ in range(int((2 * nav2_nav.RECOVER_AFTER_S + nav2_nav.RETREAT_MAX_S + 10) / 0.1)):
        扭()
        await t.一拍()
        if 退完():
            break
    steps = _步(t)
    assert [s["action"] for s in steps][:2] == ["replan", "retreat"], steps
    assert steps[-1]["ok"] is True, steps
    # 外审 11-14:Nav2 原地扭的时候两侧记忆过期,代理会先直走看清(往前挪)—— 卡住的位置按判卡住那一刻
    x_stuck = steps[0]["x"]
    assert x_stuck - t.r.x >= nav2_nav.RETREAT_M - 0.3, (x_stuck, t.r.x)
    assert len(link.kinds("goal")) >= n_goals + 2, "重新规划一次、退完再交给 Nav2 一次"
    assert not t.crashed
    # 用户 11-10:重新规划不走刚才堵住的那条 —— 卡住那一处临时标成不能走(只给 Nav2,这一趟有效)
    last_map = link.kinds("map")[-1]
    assert link.sent.index(last_map) < link.sent.index(link.kinds("goal")[-1]), "先送图再发目标"
    near = [poly for poly in last_map["nogo"]
            if math.dist((sum(p[0] for p in poly) / len(poly), sum(p[1] for p in poly) / len(poly)),
                         (x_stuck, 4.0)) < 0.3]
    assert near, last_map["nogo"]
    # 只有这一条路(绕开就规划不出):撤掉临时标记,还走这条
    link.goal_states.append({"goal_id": link.kinds("goal")[-1]["goal_id"], "state": "aborted",
                             "reason": "GridBased: failed to create plan"})
    n = len(link.kinds("goal"))
    await t.一拍()
    assert link.kinds("map")[-1]["nogo"] == [], "撤掉临时标记"
    assert len(link.kinds("goal")) == n + 1 and NavStatus.FAILED not in t.status


# ---------------------------------------- 外审 POC r1 C2:脱困动作统一过最后一道安全检查


async def _脱困台(tmp_path, x, y, yaw, monkeypatch, verdict=None, **kw):
    """机器人放在 1.4 m 走廊里;守卫按 ``verdict`` 回(``None`` 就照真的雷达查)。
    回 ``(t, sent)``:``sent`` 收后端发出去的每条速度。"""
    from nexwar_agent.obstacles import Verdict
    t = _台(tmp_path, 假转接(), walls=_窄走廊(1.4), **kw)
    await t.start(x, y, yaw)
    for _ in range(5):                                     # 攒几帧雷达
        await t.一拍()
    sent = []

    async def 发(vx, wz, dt_s):
        sent.append((round(vx, 3), round(wz, 3)))
    monkeypatch.setattr(t.nav, "_send", 发)
    if verdict is not None:
        monkeypatch.setattr(t.nav, "_guard_check", lambda vx, wz, g=None, **kw: Verdict(*verdict))
    return t, sent


def _退(t, path):
    t.nav._back = {"path": list(path), "t0": t.nav._secs(), "level": 2, "why": "测试", "fail": None,
                   "blocked": None, "stuck": (t.r.x, t.r.y)}


async def test_外审POC_C2_沿原路倒退_车尾会扫进地图墙_挡点是墙也不许退(tmp_path, monkeypatch):
    """codex POC r1 C2:原来守卫挡住的全是地图墙就照退,不查车身扫过的范围,0.8 秒后车尾越过墙边。"""
    t, sent = await _脱困台(tmp_path, 1.5, 3.86, math.pi / 2, monkeypatch,
                            (False, "挡住", ((-0.4, 0.0),)))
    _退(t, [(1.5, 3.5), (1.5, 3.3)])                       # 原路在背后、压着南墙(车尾只剩 4 cm)
    here = await t.nav._here()
    await t.nav._back_step(here, 0.1)
    assert sent and sent[-1] == (0.0, 0.0), sent


async def test_外审POC_C2_沿原路倒退_后面雷达看不见_停下等_不瞎退(tmp_path, monkeypatch):
    t, sent = await _脱困台(tmp_path, 5.0, 4.0, 0.0, monkeypatch, rear=False)
    _退(t, [(4.6, 4.0), (3.5, 4.0)])
    here = await t.nav._here()
    await t.nav._back_step(here, 0.1)
    assert sent and sent[-1] == (0.0, 0.0), sent


async def test_外审POC_C2_沿原路倒退_走廊中间_后面看得见_照常退(tmp_path, monkeypatch):
    t, sent = await _脱困台(tmp_path, 5.0, 4.0, 0.0, monkeypatch)
    _退(t, [(4.6, 4.0), (3.5, 4.0)])
    here = await t.nav._here()
    await t.nav._back_step(here, 0.1)
    assert sent and sent[-1][0] < 0, sent


async def test_外审POC_C2_K形掉头_往后挪_后面雷达看不见_这一步不挪(tmp_path, monkeypatch):
    t, sent = await _脱困台(tmp_path, 5.0, 4.0, 0.0, monkeypatch, rear=False)
    now = t.nav._secs()
    t.nav._man = {"want": math.pi, "t0": now, "steps": 1, "level": 2, "why": "测试", "fail": None,
                  "last": None, "cur": {"v": -0.15, "w": 0.4, "t": now}}
    here = await t.nav._here()
    await t.nav._man_step(here, 0.1)
    assert sent and sent[-1] == (0.0, 0.0), sent


async def test_外审POC_C2_K形掉头_这一步会扫到地图墙_挡点是墙也不挪(tmp_path, monkeypatch):
    t, sent = await _脱困台(tmp_path, 1.5, 3.86, math.pi / 2, monkeypatch,
                            (False, "挡住", ((-0.4, 0.0),)))
    now = t.nav._secs()
    t.nav._man = {"want": 0.0, "t0": now, "steps": 1, "level": 2, "why": "测试", "fail": None,
                  "last": None, "cur": {"v": -0.15, "w": 0.0, "t": now}}
    here = await t.nav._here()
    await t.nav._man_step(here, 0.1)
    assert sent and sent[-1] == (0.0, 0.0), sent


async def test_外审POC_r2_C2_挡点全是墙_同时后面看不见_也不许退(tmp_path, monkeypatch):
    """codex POC r2 #2:挡点全是地图墙就直接放行,没管同一份结果里后面(雷达看不见)的未知区。"""
    from nexwar_agent.obstacles import Verdict
    t, sent = await _脱困台(tmp_path, 5.0, 4.0, 0.0, monkeypatch, rear=False)
    monkeypatch.setattr(t.nav, "_guard_check", lambda vx, wz, g=None, **kw: Verdict(
        False, "扫过区有挡 1 处、看不见 50 处", hits=((-0.9, 0.6),), unknown=50))
    _退(t, [(4.6, 4.0), (3.5, 4.0)])
    here = await t.nav._here()
    await t.nav._back_step(here, 0.1)
    assert sent and sent[-1] == (0.0, 0.0), sent


async def test_外审1114_脱困_挡点全是地图墙_车身扫过也不压墙_照样不动(tmp_path, monkeypatch):
    """外审 11-14:脱困一步原来「守卫挡点全是地图墙 + 车身按地图查过不压墙」就放行 —— 定位偏了,
    地图说不压、雷达看见的墙其实就在那。看得见的挡一律不动。"""
    t, sent = await _脱困台(tmp_path, 5.0, 4.0, 0.0, monkeypatch, (False, "挡住", ((-0.9, 0.0),)))
    _退(t, [(4.6, 4.0), (3.5, 4.0)])                       # 走廊中间,按地图车尾扫不到墙
    here = await t.nav._here()
    await t.nav._back_step(here, 0.1)
    assert sent and sent[-1] == (0.0, 0.0), sent


async def test_外审POC_r2_C2_沿原路倒退_车尾会扫进禁行区_中心在区外也不许退(tmp_path, monkeypatch):
    """codex POC r2 #3:禁行区只查车身中心,0.68 秒后车尾进了禁行区。"""
    from test_planned_nav import _区
    t, sent = await _脱困台(tmp_path, 5.0, 4.0, 0.0, monkeypatch)
    await t.nav.set_zones(_区({"id": "pool", "kind": "nogo",
                               "polygon": [[4.3, 4.16], [4.4, 4.16], [4.4, 4.6], [4.3, 4.6]]}))
    _退(t, [(4.6, 4.0), (3.5, 4.0)])
    here = await t.nav._here()
    await t.nav._back_step(here, 0.1)
    assert sent and sent[-1] == (0.0, 0.0), sent


async def test_外审POC_r2_C2_K形掉头挑步子_车身会压上禁行区的那一步不挑(tmp_path, monkeypatch):
    from test_planned_nav import _区
    t, sent = await _脱困台(tmp_path, 5.0, 4.0, 0.0, monkeypatch)
    await t.nav.set_zones(_区({"id": "pool", "kind": "nogo",
                               "polygon": [[4.3, 4.16], [4.4, 4.16], [4.4, 4.6], [4.3, 4.6]]}))
    here = await t.nav._here()
    walls = await t.nav._route_walls()
    for v in (-0.15,):
        for w in (0.4, -0.4, 0.0):
            if t.nav._man_pick(here, math.pi, walls, None) == (v, w):
                assert t.nav._sweep_ok(here, v, w, walls), (v, w)


async def test_外审POC_r2_I5_路网拐角在走廊出口外的空地上_直段照直走_拐角原地转_能过(tmp_path):
    """codex POC r2 #4:按途经点插朝向,机器人在 1.2 m 的直走廊里就开始慢慢转,余量算成 0.002 m 拒了;
    实际是直段照直走、出了走廊在空地上拐。"""
    from nexwar_contract.routenet import RouteNet
    link = 会规划的转接()
    walls = [(0.1, 0.1, 4.5, 3.4), (0.1, 4.6, 4.5, 7.9)]     # 1.2 m 走廊,x 4.5 以外是空地
    t = _台(tmp_path, link, walls=walls)
    await t.start(1.5, 4.0)
    link.here = (1.5, 4.0)
    t.nav.set_route_net(RouteNet.from_wire({
        "map_id": "m", "map_version": "", "revision": 1,
        "nodes": [{"id": "A", "x": 1.5, "y": 4.0}, {"id": "B", "x": 5.0, "y": 4.0},
                  {"id": "C", "x": 5.0, "y": 7.0}],
        "edges": [["A", "B"], ["B", "C"]]}))
    await t.nav.goto(Pose.from_xy_yaw(5.0, 7.0, math.pi / 2))
    assert link.kinds("goal") and link.kinds("goal")[-1].get("via")


@pytest.mark.parametrize("x1", [4.53, 4.56])                # 车尾差 5 mm / 已经压上 2.5 cm
async def test_外审POC_r3_C2_车尾贴着或压着禁行区_不许再往里退(tmp_path, monkeypatch, x1):
    """codex POC r3 #2:离禁行区不到 1 cm 时阈值变成负数,相交以后距离恒为 0,检查失效。"""
    from test_planned_nav import _区
    t, sent = await _脱困台(tmp_path, 5.0, 4.0, 0.0, monkeypatch)
    await t.nav.set_zones(_区({"id": "pool", "kind": "nogo",
                               "polygon": [[4.3, 3.8], [x1, 3.8], [x1, 4.2], [4.3, 4.2]]}))
    _退(t, [(4.6, 4.0), (3.5, 4.0)])
    here = await t.nav._here()
    await t.nav._back_step(here, 0.1)
    assert sent and sent[-1] == (0.0, 0.0), sent


async def test_外审POC_r4_离禁行区已经不到3厘米_脱困一点都不许再靠近(tmp_path, monkeypatch):
    """codex POC r4 #1:阈值是 min(3 cm, 起点 − 1 cm),贴着的还能再靠近不到 1 cm(25 → 21 mm)。"""
    from test_planned_nav import _区

    from nexwar_agent import zone_guard as zg
    t, sent = await _脱困台(tmp_path, 5.0, 4.0, 0.02, monkeypatch)
    here = await t.nav._here()
    rect = zg.footprint(here.x, here.y, here.yaw)
    y_low = min(p[1] for p in rect)
    await t.nav.set_zones(_区({"id": "pool", "kind": "nogo",                 # 右边贴着 25 mm
                               "polygon": [[3.5, 3.0], [5.5, 3.0], [5.5, y_low - 0.025],
                                           [3.5, y_low - 0.025]]}))
    [z] = t.nav._closed
    c0 = zg.clearance((here.x, here.y, here.yaw), z, 0.03)
    assert 0.015 < c0 < 0.03, c0
    walls = await t.nav._route_walls()
    assert not t.nav._sweep_ok(here, -0.2, 0.0, walls), "倒退会往右边禁行区靠"
    assert t.nav._sweep_ok(here, 0.2, 0.0, walls), "往前是离开"


# ---------------------------------------- 外审 11-14、用户定:两侧盲带看不清不转身,先直着挪看清再转


async def test_外审1114_刚出发两侧没看过_Nav2要原地转_先直走看清再转(tmp_path):
    link = 假转接()
    t = _台(tmp_path, link)
    await t.start(3.0, 4.0)
    await t.nav.goto(Pose.from_xy_yaw(1.0, 4.0))
    x0, sent = t.r.x, []
    for _ in range(80):
        link.now += 0.1
        link.cmd = (link.now, 1, 0.0, 0.0, 0.6)
        await t.一拍()
        sent.append((round(t.nav._last_vx, 2), round(t.nav._last_wz, 2)))
    first = next(c for c in sent if c != (0.0, 0.0))
    assert first[0] > 0.1 and first[1] == 0.0, ("先直着往前挪", sent[:6])
    turned = [i for i, (_, w) in enumerate(sent) if abs(w) > 0.1]
    assert turned, ("看清以后照 Nav2 的转", sent[-5:])
    assert 0.5 < t.r.x - x0 < 1.4, ("挪了约一个车身长", t.r.x - x0)
    assert all(abs(v) < 1e-6 for v, _ in sent[turned[0]:turned[0] + 20]), "开始转以后不再挪"


async def test_外审1114_两侧没看过_前面有挡_后面没雷达_不挪不转_报被挡(tmp_path):
    link = 假转接()
    t = _台(tmp_path, link, rear=False)
    t.world.dyn["box"] = (3.6, 3.6, 3.9, 4.4)              # 车头前 0.1 m 一个箱子
    await t.start(3.0, 4.0)
    await t.nav.goto(Pose.from_xy_yaw(1.0, 4.0))
    x0 = t.r.x
    for _ in range(70):
        link.now += 0.1
        link.cmd = (link.now, 1, 0.0, 0.0, 0.6)
        await t.一拍()
    assert abs(t.r.x - x0) < 0.02 and abs(t.r.yaw) < 0.02, (t.r.x, t.r.yaw)
    assert "nav_blocked" in [k for k, _ in t.events]


async def test_外审1114_先挪的次数用完_不再自己挪_正常走出3米才清零(tmp_path):
    """Nav2 原地来回扭的时候,别一回回自己往前挪下去(那是代理在走,不是 Nav2 要的)。"""
    from nexwar_agent.bridges.nav2_nav import LOOK_RESET_M, LOOK_TRIES
    link = 假转接()
    t = _台(tmp_path, link)
    await t.start(1.5, 4.0)
    await t.nav.goto(Pose.from_xy_yaw(9.0, 4.0))
    here = await t.nav._here()
    t.nav._look_tries, t.nav._look_at = LOOK_TRIES, (here.x, here.y)
    x0 = t.r.x
    for _ in range(30):
        link.now += 0.1
        link.cmd = (link.now, 1, 0.0, 0.0, 0.6)
        await t.一拍()
    assert abs(t.r.x - x0) < 0.02, "次数用完:不挪"
    for _ in range(int((LOOK_RESET_M + 0.5) / 0.05)):     # Nav2 正常往前开 0.5 m/s
        link.now += 0.1
        link.cmd = (link.now, 1, 0.5, 0.0, 0.0)
        await t.一拍()
    assert t.r.x - x0 >= LOOK_RESET_M and t.nav._look_tries == 0


async def test_外审1114_低速抬到死区_转向同比例抬_弯不变(tmp_path):
    """外审 11-14:原来只把前进抬到死区、转向不动 —— 弯变缓(半径变大)。低速正发生在墙边、窄处、
    终点前,不是小事(用户纠正)。前进抬 k 倍,转向也抬 k 倍。"""
    t = _台(tmp_path, 假转接())
    vx, wz = t.nav._deband(0.08, 0.2)
    assert vx == pytest.approx(0.13) and wz / vx == pytest.approx(0.2 / 0.08)
    vx, wz = t.nav._deband(-0.065, 0.1)
    assert vx == pytest.approx(-0.13) and wz == pytest.approx(0.2)
    assert t.nav._deband(0.3, 0.02) == (0.3, 0.02), "够快的不动"


async def test_外审1114_抬完转速超上限_走着的截到上限_原地转的照旧不转(tmp_path):
    t = _台(tmp_path, 假转接())
    await t.start(1.5, 4)
    await t.nav.set_speed(0.6, z=0.25)
    vx, wz = t.nav._fit(0.08, 0.2, cap=0.6)              # 抬到 0.13 / 0.325,转速上限 0.25
    assert vx == pytest.approx(0.13) and wz == pytest.approx(0.25), "最接近的弯,不改成直走"
    await t.nav.set_speed(0.6, z=0.05)
    assert t.nav._fit(0.0, 0.5, cap=0.6) == (0.0, 0.0), "原地转:上限比死区还低,不转(外审 R5)"
    await t.nav.set_speed(0.1)
    vx, wz = t.nav._fit(0.5, 0.3, cap=0.1)
    assert vx == 0.0, "限速比死区还低:不往前(外审 R5)"


async def test_外审1114_先挪开始了_Nav2中间几拍要倒车撞墙_照样挪完(tmp_path):
    """仿真 11-14:挪的过程中 Nav2 有几拍发「倒车」(身后真有墙,不是只因盲带被拦),原来这几拍
    就不接着挪,10 s 到了只挪了 0.1 m,两次机会用完一直卡着。开始挪了就挪完(挪的这一步自己
    安全就行)。"""
    link = 假转接()
    t = _台(tmp_path, link)
    t.world.dyn["box"] = (2.0, 3.6, 2.2, 4.4)             # 车尾后 0.35 m:原地转扫不到,倒车撞上
    await t.start(3.0, 4.0)
    await t.nav.goto(Pose.from_xy_yaw(1.0, 4.0))
    x0 = t.r.x
    for i in range(70):
        link.now += 0.1
        link.cmd = (link.now, 1, 0.0, 0.0, 0.6) if i % 4 == 0 else (link.now, 1, -0.5, 0.0, 0.0)
        await t.一拍()
    assert t.r.x - x0 > 1.0, ("挪完一个车身长", t.r.x - x0)
