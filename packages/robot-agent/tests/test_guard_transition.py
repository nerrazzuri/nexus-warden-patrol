"""外审 11-14:守卫查「运动过渡」—— 机器人此刻还在做的运动(实测、上一拍命令)在延迟里接着走、
再刹停,跟新命令会走出的轨迹,两样的扫掠区都要查。原来距离取实测和命令的较大值、方向只跟新命令:
实测前进 0.8 m/s、新命令倒车 −0.2 时只查后方,前方一点不查。"""
from __future__ import annotations

import math

from nexwar_agent.obstacles import ObstacleGuard

G = ObstacleGuard()
HL = G.body_len / 2 + G.margin
HW = G.body_wid / 2 + G.margin


def _front(pts, beyond=0.1):
    return [p for p in pts if p[0] > HL + beyond]


def _back(pts, beyond=0.1):
    return [p for p in pts if p[0] < -HL - beyond]


def test_前进中收到倒车_前方刹停那段也查():
    pts = G.swept(-0.2, 0.0, 0.8, moving=((0.8, 0.0),))
    ahead = _front(pts)
    assert ahead, "还在以 0.8 m/s 往前冲,前方必须查"
    # 0.8 m/s:延迟 0.2 s 走 0.16 + 刹停 0.64 + 再留 0.3 ≈ 1.1 m
    assert max(x for x, _ in ahead) >= HL + 0.8 * G.latency + 0.8 ** 2 / (2 * G.decel) - 0.05
    assert _back(pts), "新命令倒车那段也查"


def test_倒车中收到前进_后方刹停那段也查():
    pts = G.swept(0.3, 0.0, -0.3, moving=((-0.3, 0.0),))
    assert _back(pts) and _front(pts)


def test_平移中收到原地转_刹停前那段平移也查():
    pts = G.swept(0.0, 0.5, 0.5, w_now=(0.0, 0.0), moving=((0.5, 0.0),))
    r = math.hypot(HL, HW)
    assert max(x for x, _ in pts) > r + 0.2, "还在往前走 0.5 m/s,前方不能只查外接圆"


def test_原地转中收到前进_接着转的那段扇形也查():
    """正在 1.0 rad/s 左转,新命令直走:延迟里接着转、刹停,车尾右角扫向右侧。"""
    still = G.swept(0.3, 0.0, 0.0)
    pts = G.swept(0.3, 0.0, 0.0, w_now=(1.0, 1.0), moving=((0.0, 1.0),))
    extra = set(pts) - set(still)
    assert any(x < 0 and y < -HW for x, y in extra), "左转时车尾往右甩"


def test_走着转向反过来_原来那一侧的弧也查():
    """前进 0.5 m/s 正在左转 0.8 rad/s,新命令右转:左前方(原来那股弯)也要查。"""
    pts = G.swept(0.5, -0.8, 0.5, w_now=(0.8, 0.8), moving=((0.5, 0.8),))
    assert any(x > HL and y > HW + 0.1 for x, y in pts)


def test_实测滞后_上一拍命令还在前进_新命令倒车_前方也查():
    """实测还是 0(里程滞后或没有),上一拍发的是 0.8 前进:按上一拍命令也算一份。"""
    pts = G.swept(-0.2, 0.0, 0.0, moving=((0.8, 0.0), (0.0, 0.0)))
    assert _front(pts)


def test_真停着_倒车不查前方_不多挡():
    pts = G.swept(-0.2, 0.0, 0.0, moving=((0.0, 0.0), (0.0, 0.0)))
    assert not _front(pts)


def test_check_把正在做的运动一路传进去(monkeypatch):
    got = {}

    def fake(vx, wz, v_meas, w_now=(), moving=()):
        got["moving"] = moving
        return []

    monkeypatch.setattr(G, "swept", fake)

    class V:
        def state(self):
            return "ok"

        def lookup(self, pts, pose):
            return [], []

    G.check(-0.2, 0.0, 0.8, V(), (0.0, 0.0, 0.0), moving=((0.8, 0.0),))
    assert got["moving"] == ((0.8, 0.0),)


async def test_导航每拍查守卫_把实测和上一拍命令都当正在做的运动传进去(tmp_path):
    from test_nav2_backend import _台, 假转接

    t = _台(tmp_path, 假转接())
    await t.start(1.5, 4.0)
    nav = t.nav
    nav._last_vx, nav._last_wz, nav._v_meas, nav._w_meas = 0.8, 0.1, 0.6, 0.2
    got = {}
    orig = nav.guard.check

    def spy(*a, **kw):
        got.update(kw)
        return orig(*a, **kw)

    nav.guard.check = spy
    nav._guard_check(-0.2, 0.0)
    assert got["moving"] == ((0.8, 0.1), (0.6, 0.2))
    assert got["w_now"] == (0.1, 0.2)


# ---- 外审 11-14:守卫结论带原因枚举,上层不靠「障碍数据」几个字决定停不停 ----

def test_守卫结论带原因枚举():
    from nexwar_agent.obstacles import ObstacleView

    class V:
        def __init__(self, st, hit=(), unk=()):
            self.st, self.hit, self.unk = st, hit, unk

        def state(self):
            return self.st

        def lookup(self, pts, pose):
            return list(self.hit), list(self.unk)

    pose = (0.0, 0.0, 0.0)
    assert G.check(0.0, 0.0, 0.0, V("ok"), pose).cause == "clear"
    assert G.check(0.3, 0.0, 0.0, V("stale"), pose).cause == "data"
    assert G.check(0.3, 0.0, 0.0, V("ok", hit=[0]), pose).cause == "hit"
    assert G.check(0.3, 0.0, 0.0, V("ok", unk=[0]), pose).cause == "unknown"
    assert G.check(0.3, 0.0, 0.0, V("ok"), pose).cause == "clear"
    assert ObstacleView is not None


async def test_导航按枚举停_原因文字怎么写都一样(tmp_path):
    from test_nav2_backend import _台, 假转接

    from nexwar_agent.obstacles import Verdict
    from nexwar_patrol.protocol.nav_types import Pose

    link = 假转接()
    t = _台(tmp_path, link)
    await t.start(1.5, 4.0)
    await t.nav.goto(Pose.from_xy_yaw(9.0, 4.0))
    t.nav._guard_check = lambda vx, wz, g=None: Verdict(False, "随便写的原因", kind="data")
    for _ in range(3):
        link.now += 0.1
        link.cmd = (link.now, 1, 0.25, 0.0, 0.0)
        await t.一拍()
    assert t.r.speed[0] == 0.0, "数据不新鲜:停,不看原因文字"
