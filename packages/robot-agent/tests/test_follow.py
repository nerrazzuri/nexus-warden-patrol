"""W74 二期:跟人(设计 §五、§六)。真引擎 + 规划后端 + 仿真狗;人是假的(按机器人此刻的位姿算方向、
距离)。

人往前走 → 机器人跟上、保持 3 m 左右;人停 → 机器人在人后方停;人消失 10 秒 → 回最后看见人的地方、朝人
离开的方向停、任务结束(result lost);跟到上限按跟丢办;被中止照常停稳再终态;路上发轨迹事件。
"""

from __future__ import annotations

import math

import pytest
from test_planned_engine import _一拍, 台子  # noqa: F401  (pytest 夹具)

from nexwar_agent.tasks.follow import FollowTask
from nexwar_contract.errors import ContractError
from nexwar_contract.follow import FollowRequest, parse_follow
from nexwar_contract.messages import TaskState


class 人:
    """一个人在地图上 (x, y);``seen`` False = 看不到。按机器人位姿给 ``(方向°, 距离 m)``。"""

    def __init__(self, r, x, y):
        self.r, self.x, self.y, self.seen = r, x, y, True

    def target(self):
        if not self.seen:
            return None
        dx, dy = self.x - self.r.x, self.y - self.r.y
        b = math.degrees(math.atan2(dy, dx) - self.r.yaw)
        b = (b + 180) % 360 - 180
        return (b, math.hypot(dx, dy))


def _任务(台, p, *, others=(), **kw):
    c, r, parts = 台
    emits = []

    class 簿:
        def emit(self, kind, data):
            emits.append((kind, data))

    t = FollowTask(task_id="follow-1", req=FollowRequest(**kw), parts=parts, events=簿(),
                   now_ms=lambda: int(c.mono * 1000), wall_ms=c,
                   targets=lambda: [x for x in (p.target(), *(o.target() for o in others))
                                    if x is not None],
                   here=lambda: (r.x, r.y, r.yaw), map_ref=("m", "v"), priority=80)
    return t, emits


async def _跑(台, t, secs, each=None):
    c, r, parts = 台
    for _ in range(int(secs * 10)):
        await t.step(0.1)
        await _一拍(c, r, parts)
        if each is not None:
            each()
        if t.done:
            return


def test_契约_默认_越界拒():
    assert parse_follow(None) == FollowRequest()
    assert parse_follow({"keep_m": 4}).keep_m == 4.0
    for bad in ({"keep_m": 0.5}, {"max_s": 1.5}, {"x": 1}, {"lost_s": float("nan")}, []):
        with pytest.raises(ContractError):
            parse_follow(bad)


async def test_人往前走_机器人跟上_保持3米左右_路上发轨迹(台子):  # noqa: F811
    """跟的机制(这张图有隔墙,地方小:按 3 m 跟;默认 4.5 m 见下面没有隔墙的那几个)。"""
    c, r, parts = 台子
    p = 人(r, 3.0, 3.0)
    t, emits = _任务(台子, p, keep_m=3.0)
    await t.start()

    def 走():
        if p.y < 7.0:
            p.y += 0.05                                   # 0.5 m/s 往北
    await _跑(台子, t, 20, 走)
    assert t.state is TaskState.RUNNING
    d = math.hypot(p.x - r.x, p.y - r.y)
    assert r.y > 2.0 + 1.0, "跟上去了"
    assert 2.0 <= d <= 4.5, d
    track = [d for k, d in emits if k == "follow_track"]
    assert track and track[-1]["task_id"] == "follow-1"
    pt = track[-1]["points"][-1]
    assert abs(pt["x"] - p.x) < 0.6 and abs(pt["y"] - p.y) < 0.6


async def test_人消失10秒_回最后看见的地方_朝人走的方向_结束说跟丢(台子):  # noqa: F811
    c, r, parts = 台子
    p = 人(r, 4.0, 2.0)
    t, emits = _任务(台子, p)
    await t.start()

    def 走():
        if p.seen:
            p.y += 0.04                                   # 往北走
            if p.y > 4.0:
                p.seen = False
    await _跑(台子, t, 80, 走)
    assert t.state is TaskState.DONE, t.detail
    assert t.detail["result"] == "lost"
    last = t.detail["last"]
    assert abs(last["x"] - 4.0) < 0.5 and abs(last["y"] - 4.0) < 0.6
    assert abs(t.detail["heading_deg"] - 90) < 30, "人往北走的"
    assert math.dist((r.x, r.y), (last["x"], last["y"])) < 0.5, "回到最后看见人的地方"
    assert abs(math.degrees(r.yaw) - 90) < 25, "朝人离开的方向"
    assert t.detail["track"]


async def test_跟到时限_不再追_原地守着_人不见了才收尾(台子):  # noqa: F811
    """外审 W77-1 #4:到上限不再往前追,原地守着(人靠近照样退,见下面);人看不到 ``lost_s`` 才收尾。"""
    c, r, parts = 台子
    p = 人(r, 3.0, 3.0)
    t, emits = _任务(台子, p, max_s=10, keep_m=3.0)

    def 走():
        p.y = min(p.y + 0.05, 9.0)
    await t.start()
    await _跑(台子, t, 30, 走)
    assert t.state is TaskState.RUNNING and t.phase == "keep"
    assert [d["result"] for k, d in emits if k == "follow_lost"] == ["limit"]
    y = r.y
    await _跑(台子, t, 5, 走)
    assert abs(r.y - y) < 0.05, "到上限:不再往前追"
    p.seen = False
    await _跑(台子, t, 30)
    assert t.state is TaskState.DONE and t.detail["result"] == "limit"


async def test_中止_停稳再终态(台子):  # noqa: F811
    c, r, parts = 台子
    p = 人(r, 5.0, 2.0)
    t, _ = _任务(台子, p)
    await t.start()
    await _跑(台子, t, 2)
    await t.abort("人工")
    await _跑(台子, t, 20)
    assert t.state is TaskState.ABORTED


async def test_一开始就看不到人_也按跟丢办_不乱跑(台子):  # noqa: F811
    c, r, parts = 台子
    p = 人(r, 4.0, 2.0)
    p.seen = False
    t, _ = _任务(台子, p, lost_s=3)
    await t.start()
    await _跑(台子, t, 20)
    assert t.state is TaskState.DONE and t.detail["result"] == "lost"
    assert math.dist((r.x, r.y), (2.0, 2.0)) < 0.3, "没看到过人:原地"


async def test_运行时_能力里有跟人_收命令_能力报在跟(tmp_path):
    from test_planned_engine import 画图
    from test_runtime_maps import _cmd
    from test_standoff import _拍, _真台
    broker, c, ears, dog, rt = await _真台(tmp_path)
    try:
        画图(tmp_path)
        rt.parts.nav.load_grid(tmp_path)
        rt.processor.supported = rt._supported()          # 真的换图时运行时自己刷
        dog.teleport(2.0, 2.0, 0.0)
        await rt._publish_caps()
        await broker.drain()
        caps = ears.by["capabilities"][-1]
        assert caps["tasks"]["follow"] == {"state": "idle"}
        await rt._on_cmd(_cmd("follow", {"keep_m": 20}, "f0", c))
        await broker.drain()
        assert ears.by["cmd/ack"][-1]["result"] != "accepted", "keep_m 越界:拒"
        await rt._on_cmd(_cmd("follow", {"max_s": 60}, "f1", c))
        await broker.drain()
        assert ears.by["cmd/ack"][-1]["result"] == "accepted", str(ears.by["cmd/ack"][-1])
        await _拍(rt, broker, dog, c, 5, person=6.0)
        await rt._publish_caps()
        await broker.drain()
        st = ears.by["capabilities"][-1]["tasks"]["follow"]
        assert st["state"] == "follow" and st["task_id"] == "follow-f1", st
        t = rt.processor.current
        assert t._hal is rt.hal and t._backoff is not None, "用户 11-15:人走近就退,真装上了"
    finally:
        await rt.close()


async def test_外审8_到上限_人回头靠近_不往人身上走(台子):  # noqa: F811
    c, r, parts = 台子
    p = 人(r, 2.0, 5.0)
    t, _ = _任务(台子, p, max_s=6, keep_m=3.0)
    await t.start()

    def 走():
        if t.phase == "follow":
            p.y = min(p.y + 0.15, 9.0)                    # 1.5 m/s 往北,机器人跟不上
        else:
            p.y = max(p.y - 0.15, r.y + 2.0)              # 人回头走到机器人前面 2 m
    await _跑(台子, t, 40, 走)
    assert t.phase == "keep"
    d = math.hypot(p.x - r.x, p.y - r.y)
    assert d >= 1.9, f"人回头靠近了还往前走:只剩 {d:.2f} m"


async def test_外审9_两个人_被跟的还看得见_旁边更近的不抢(台子):  # noqa: F811
    c, r, parts = 台子
    p = 人(r, 3.0, 5.5)
    t, _ = _任务(台子, p, others=())
    await t.start()
    await _跑(台子, t, 1)
    q = 人(r, 3.5, 2.0)                                  # 另一个人站在机器人旁边,比被跟的近
    t2_others = [q]
    t._targets = lambda: [x for x in (p.target(), *(o.target() for o in t2_others))
                          if x is not None]

    def 走():
        p.y = min(p.y + 0.05, 8.0)
    await _跑(台子, t, 8, 走)
    assert t._person is not None and math.dist(t._person, (p.x, p.y)) < 1.0, \
        (t._person, (p.x, p.y))


# ---------------------------------------------------------------- 用户 11-15:保持 4–5 m,人靠近就退


@pytest.fixture
async def 空台(tmp_path):
    """没有隔墙的 12 × 8 m(人往机器人走、机器人往后退要地方)。"""
    from test_planned_engine import 画图, 钟

    from nexwar_adapter_sim.robot import SimRobot
    from nexwar_agent.assembly import build_engine
    from nexwar_agent.planning.planner import Planner
    from nexwar_patrol.protocol.nav_types import Pose
    c = 钟()
    r = SimRobot(now_ms=c, max_vx=0.6, max_wz=1.5, stop_latency_s=0.2)
    await r.connect()
    await r.acquire_control()
    画图(tmp_path)
    parts = build_engine(r, runs_root=tmp_path / "runs", now_ms=c, monotonic=lambda: c.mono,
                         map_id="m", home=Pose.from_xy_yaw(2.5, 4.0), nav_kind="planned",
                         planner=Planner(in_process=True))
    parts.nav.load_grid(tmp_path)
    await parts.nav.connect()
    r.teleport(2.5, 4.0, 0.0)
    yield c, r, parts
    await parts.engine.aclose()


class 守卫:
    def __init__(self, ok=True):
        self.ok, self.reason = ok, "" if ok else "后面有挡"

    def __call__(self, vx, wz):
        return self


def _退的任务(台, p, ok=True, **kw):
    from nexwar_agent.tasks.standoff import Backoff
    c, r, parts = 台
    t, emits = _任务(台, p, **kw)
    t._hal = r
    t._backoff = Backoff(check=守卫(ok), here=lambda: (r.x, r.y, r.yaw), nogo=lambda x, y, d: "")
    return t, emits


def test_用户1115_跟人保持4到5米_保持距离也是4进5出():
    from nexwar_contract import follow, standoff
    assert FollowRequest().keep_m == 4.5
    assert follow.BACK_M == 4.0 and follow.CLEAR_M == 5.0
    assert standoff.TOO_CLOSE_M == 4.0 and standoff.CLEAR_M == 5.0


async def test_人往前走_跟上去_停在人后面4到5米(空台):
    c, r, parts = 空台
    p = 人(r, 6.0, 4.0)
    t, _ = _退的任务(空台, p)
    await t.start()

    def 走():
        p.x = min(p.x + 0.05, 10.5)
    await _跑(空台, t, 30, 走)
    d = math.hypot(p.x - r.x, p.y - r.y)
    assert r.x > 4.5, "跟上去了"
    assert 4.0 <= d <= 5.6, d


async def test_人走近到4米以内_往后退到5米以外才停_从不往人那边走(空台):
    c, r, parts = 空台
    p = 人(r, 7.0, 4.0)                                  # 4.5 m:站着不动
    t, _ = _退的任务(空台, p)
    await t.start()
    await _跑(空台, t, 1)
    assert r.x == pytest.approx(2.5, abs=0.05), "4–5 m 之间站着"
    xs, modes = [], set()

    def 逼近():
        p.x = max(p.x - 0.06, 6.3)                      # 人往机器人走,停在 6.3
        xs.append(r.x)
        modes.add(t.caps()["state"])
    await _跑(空台, t, 15, 逼近)
    assert "retreat" in modes
    assert all(b <= a + 0.02 for a, b in zip(xs, xs[1:], strict=False)), "退的时候不往人那边走"
    d = math.hypot(p.x - r.x, p.y - r.y)
    assert 4.9 <= d <= 5.6, d
    assert t.state is TaskState.RUNNING and t.caps()["state"] == "follow", "退够了接着跟"


async def test_人靠近_退不了_原地站定_报无路可退一次(空台):
    c, r, parts = 空台
    p = 人(r, 6.0, 4.0)
    t, emits = _退的任务(空台, p, ok=False)
    await t.start()

    def 逼近():
        p.x = max(p.x - 0.06, 5.5)
    await _跑(空台, t, 10, 逼近)
    assert r.x == pytest.approx(2.5, abs=0.1), "退不了:不动"
    assert t.caps()["state"] == "cornered"
    corner = [d for k, d in emits if k == "follow_cornered"]
    assert len(corner) == 1 and corner[0]["task_id"] == "follow-1"
    assert "后面有挡" in corner[0]["why"]


async def test_退着的时候被中止_停稳再终态(空台):
    c, r, parts = 空台
    p = 人(r, 6.0, 4.0)
    t, _ = _退的任务(空台, p)
    await t.start()

    def 逼近():
        p.x = max(p.x - 0.06, 5.0)
    await _跑(空台, t, 3, 逼近)
    assert t.caps()["state"] == "retreat"
    await t.abort("人工")
    await _跑(空台, t, 5)
    assert t.state is TaskState.ABORTED
    o = await r.odometry()
    assert abs(o.vx) < 0.05


# ---------------------------------------------------------------- 外审 W77-1


class 慢停的狗:
    """包一层仿真狗:``stopped()`` 一直说没停(看收尾等不等停稳)。"""

    def __init__(self, r):
        self.r, self.stop_n, self.never = r, 0, True

    async def set_velocity(self, cmd):
        return await self.r.set_velocity(cmd)

    async def stop(self):
        self.stop_n += 1
        return await self.r.stop()

    async def stopped(self):
        return False if self.never else await self.r.stopped()


async def test_外审1_2_退着的时候不安全断线_马上停车_不再退_连回来接着退(空台):
    c, r, parts = 空台
    p = 人(r, 6.0, 4.0)
    t, _ = _退的任务(空台, p)
    await t.start()

    def 逼近():
        p.x = max(p.x - 0.06, 5.0)
    await _跑(空台, t, 3, 逼近)
    assert t.caps()["state"] == "retreat"
    await t.on_offline(False)
    await _跑(空台, t, 3)
    x = r.x
    await _跑(空台, t, 3)
    assert abs(r.x - x) < 0.02 and abs((await r.odometry()).vx) < 0.05, "断线:停住不退"
    await t.on_online()
    await _跑(空台, t, 3)
    assert r.x < x - 0.2, "连回来:人还近,接着退"


async def test_外审1_3_退完了还没停稳就被抢占_等停稳再终态(空台):
    c, r, parts = 空台
    p = 人(r, 6.0, 4.0)
    t, _ = _退的任务(空台, p)
    hal = 慢停的狗(r)
    t._hal = hal
    await t.start()

    def 逼近():
        p.x = max(p.x - 0.06, 5.0)
    await _跑(空台, t, 3, 逼近)
    assert t.caps()["state"] == "retreat"
    p.seen = False                                       # 看不到人了:停下不退
    await _跑(空台, t, 1.0)
    assert t.caps()["state"] != "retreat"
    await t.abort("preempted")
    await _跑(空台, t, 2)
    assert t.state is TaskState.RUNNING, "还没停稳:不能交接"
    hal.never = False
    await _跑(空台, t, 2)
    assert t.state is TaskState.PREEMPTED


async def test_外审1_3_退完了没停稳_不起往前跟的那一段(空台):
    c, r, parts = 空台
    p = 人(r, 6.0, 4.0)
    t, _ = _退的任务(空台, p)
    hal = 慢停的狗(r)
    t._hal = hal
    await t.start()

    def 逼近():
        p.x = max(p.x - 0.06, 5.0)
    await _跑(空台, t, 3, 逼近)
    p.x = 11.0                                           # 人一下走远了:该往前跟
    await _跑(空台, t, 2)
    assert t._leg is None, "上一下退还没停稳:先不起导航段"
    hal.never = False
    await _跑(空台, t, 3)
    assert t._leg is not None or r.x > 1.5, "停稳了接着跟"


async def test_外审1_4_到上限时人还近_守着照样退_不卡死_人走了收尾(空台):
    c, r, parts = 空台
    p = 人(r, 6.0, 4.0)
    t, _ = _退的任务(空台, p, max_s=3)
    await t.start()

    def 逼近():
        p.x = max(p.x - 0.06, 6.3)
    await _跑(空台, t, 6, 逼近)
    assert t.phase == "keep"
    d = math.hypot(p.x - r.x, p.y - r.y)
    assert d >= 4.9, "到上限以后人靠近照样退"
    p.seen = False
    await _跑(空台, t, 20)
    assert t.state is TaskState.DONE and t.detail["result"] == "limit"


async def test_外审1_1_往后退_查出不出地图(tmp_path):
    from test_planned_engine import 画图
    from test_standoff import _真台
    broker, c, ears, dog, rt = await _真台(tmp_path)
    try:
        画图(tmp_path)
        rt.parts.nav.load_grid(tmp_path)
        assert "地图" in rt._standoff_nogo(-0.5, 3.0, 0.15), "图外"
        assert "地图" in rt._standoff_nogo(0.05, 3.0, 0.15), "图边的墙"
        assert rt._standoff_nogo(3.0, 3.0, 0.15) == ""
    finally:
        await rt.close()


async def test_外审W77_2_1_一直确认不了停稳_不放行_重发停车_报一次(空台):
    c, r, parts = 空台
    p = 人(r, 6.0, 4.0)
    t, emits = _退的任务(空台, p)
    hal = 慢停的狗(r)
    t._hal = hal
    await t.start()

    def 逼近():
        p.x = max(p.x - 0.06, 5.0)
    await _跑(空台, t, 3, 逼近)
    p.x = 11.0                                           # 人走远了:该往前跟
    await _跑(空台, t, 12)
    assert t._leg is None, "一直没确认停稳:不起导航段"
    assert hal.stop_n >= 2, "过一阵重发停车"
    assert len([d for k, d in emits if k == "follow_stop_unconfirmed"]) == 1
    await t.abort("preempted")
    await _跑(空台, t, 8)
    assert t.state is TaskState.RUNNING, "没停稳:不交接"
    hal.never = False
    await _跑(空台, t, 2)
    assert t.state is TaskState.PREEMPTED


async def test_外审W77_3_1_导航段停不稳收尾_不往后退_停稳了再退(空台):
    c, r, parts = 空台
    p = 人(r, 9.0, 4.0)
    t, _ = _退的任务(空台, p)
    assert parts.hal is r
    await t.start()
    await _跑(空台, t, 2)
    assert t._leg is not None, "人在 8 m 外:起导航段跟"
    real_stopped, real_vel = r.stopped, r.set_velocity
    sent = []

    async def 没停():
        return False

    async def 记(cmd):
        sent.append(cmd.vx)
        return await real_vel(cmd)
    r.stopped, r.set_velocity = 没停, 记
    p.x = r.x + 3.5                                      # 人一下走近到 3.5 m
    await _跑(空台, t, 10)
    assert not [v for v in sent if v < 0], "导航段还没确认停稳:不发后退速度"
    assert t._leg is None
    r.stopped = real_stopped
    await _跑(空台, t, 2)
    assert [v for v in sent if v < 0], "停稳了:接着退"


async def test_外审W77_4_1_跟人途中返航_导航段停不稳_先别交出去(空台):
    c, r, parts = 空台
    p = 人(r, 9.0, 4.0)
    t, _ = _退的任务(空台, p)
    await t.start()
    await _跑(空台, t, 2)
    assert t._leg is not None
    leg = t._leg
    real_stopped = r.stopped

    async def 没停():
        return False
    from unittest import mock
    r.stopped = 没停
    leg.state, leg.detail = TaskState.FAILED, {"reason": "stop_unconfirmed"}
    with mock.patch.object(type(parts.engine), "returned", new_callable=mock.PropertyMock,
                           return_value="电量到线"):
        await _跑(空台, t, 6)
        assert t.state is TaskState.RUNNING, "没停稳:不交出去"
        r.stopped = real_stopped
        await _跑(空台, t, 2)
    assert t.state is TaskState.FAILED and "返航" in t.detail["reason"]


async def test_外审W77_5_1_退着的时候电量掉到停止线下_停车_停稳了收尾(空台):
    c, r, parts = 空台
    p = 人(r, 6.0, 4.0)
    t, _ = _退的任务(空台, p)
    await t.start()

    def 逼近():
        p.x = max(p.x - 0.06, 5.0)
    await _跑(空台, t, 3, 逼近)
    assert t.caps()["state"] == "retreat" and t._leg is None
    r.inject_battery(14.0)
    await _跑(空台, t, 0.5, 逼近)
    x = r.x
    await _跑(空台, t, 2, 逼近)
    assert abs(r.x - x) < 0.05, "电量到停止线:不再退"
    assert t.state is TaskState.FAILED and "电量" in t.detail["reason"]


async def test_外审W77_11_4_往后退也守任务限速(空台):
    c, r, parts = 空台
    p = 人(r, 6.0, 4.0)
    t, _ = _退的任务(空台, p, max_speed_mps=0.2)
    real_vel, sent = r.set_velocity, []

    async def 记(cmd):
        sent.append(cmd.vx)
        return await real_vel(cmd)
    r.set_velocity = 记
    await t.start()

    def 逼近():
        p.x = max(p.x - 0.06, 5.0)
    await _跑(空台, t, 3, 逼近)
    back = [v for v in sent if v < 0]
    assert back and min(back) >= -0.2 - 1e-9, f"限速 0.2:退的最快 {min(back) if back else None}"


async def test_外审W77_12_3_往后退也守地图限速区(空台):
    from nexwar_contract.zones import Zone, ZoneSet
    c, r, parts = 空台
    p = 人(r, 6.0, 4.0)
    t, _ = _退的任务(空台, p)
    m, v = t._map
    await parts.nav.set_zones(ZoneSet(map_id=m, map_version=v, revision=1, zones=(
        Zone(id="slow", kind="slow", polygon=((0.0, 0.0), (12.0, 0.0), (12.0, 8.0), (0.0, 8.0)),
             max_speed_mps=0.2),)))
    real_vel, sent = r.set_velocity, []

    async def 记(cmd):
        sent.append(cmd.vx)
        return await real_vel(cmd)
    r.set_velocity = 记
    await t.start()

    def 逼近():
        p.x = max(p.x - 0.06, 5.0)
    await _跑(空台, t, 3, 逼近)
    back = [x for x in sent if x < 0]
    assert back and min(back) >= -0.2 - 1e-9, f"限速区 0.2:退的最快 {min(back) if back else None}"


async def test_外审W77_13_2_keep_m给小了_也不追近退开来回打转(空台):
    c, r, parts = 空台
    p = 人(r, 7.0, 4.0)
    t, _ = _退的任务(空台, p, keep_m=3.0)
    n = {"退": 0, "prev": ""}
    await t.start()

    def 数():
        s = t.caps()["state"]
        if s == "retreat" and n["prev"] != "retreat":
            n["退"] += 1
        n["prev"] = s
    await _跑(空台, t, 60, 数)
    assert n["退"] <= 1, f"人不动:退了 {n['退']} 回"
    d = math.hypot(p.x - r.x, p.y - r.y)
    assert 4.0 <= d <= 5.6, d
