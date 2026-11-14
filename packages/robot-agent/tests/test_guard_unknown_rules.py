"""外审 11-14、用户定:看不见的格子按方向、按动作分规则,不再一律「降到 0.3 m/s 接着走」;
站着不动时留着的旧帧(最多 60 s)只能说「那儿有东西」,不能单独证明「那儿现在是空的」。

规则(``ObstacleGuard.check`` 的 ``kind``):
- 两侧盲带(机身前后沿之间,前后雷达都看不见)里有看不见的 → ``blind``,停。任何动作都一样:
  转身、急弯时车角甩进去,里面站着人也看不见。
- 前进(``vx`` ≥ 转向门槛)、看不见的只在车头那侧雷达视野里(被挡住后面) → ``unknown``,降到
  0.3 m/s 再走;人一进视野守卫就看得见。
- 后退:有后雷达、外参标过,跟前进同一规矩;没有或没标过 → ``blind``,停。
- 原地转,扫过区里有看不见的 → ``blind``,停。降速不让车角撞人变安全。
"""
from __future__ import annotations

from test_obstacle_avoid import _grid

from nexwar_agent.obstacles import MEMORY_S, ObstacleGuard, ObstacleView

N = 40                                                    # 4 m × 4 m,0.1 m 一格,机身在正中


def _c(i):
    return (i - N / 2 + 0.5) * 0.1


def _view(unknown_where, t=None):
    """一帧栅格:``unknown_where(x, y)`` 为真的格子看不见,别处看过、空。"""
    t = t if t is not None else [0.0]
    v = ObstacleView(monotonic=lambda: t[0], latency_s=0.0)
    v.note_odom(0.0, 0.0, 0.0)
    known = [(r, k) for r in range(N) for k in range(N) if not unknown_where(_c(r), _c(k))]
    v.on_grid(_grid(cells_known=known, size=N))
    return v


def _band(x, y):
    return abs(x) <= 0.4 and abs(y) > 0.3               # 两侧盲带(机身矩形外)


def _ahead(x, y):
    return x > 0.9 and abs(y) < 0.5                       # 车头前方雷达视野里一块(被挡住后面)


def _behind(x, y):
    return x < -0.6 and abs(y) < 0.5


G = ObstacleGuard()


def test_原地转_盲带看不见_停_不再降速放行():
    v = G.check(0.0, 0.6, 0.0, _view(_band), (0, 0, 0))
    assert v.cause == "blind" and v.stops, v


def test_前进_只有车头视野里看不见_降速走():
    v = G.check(0.8, 0.0, 0.0, _view(_ahead), (0, 0, 0))
    assert v.cause == "unknown" and not v.stops, v


def test_后退_有后雷达且标过_身后视野里看不见_跟前进一样降速走():
    """车尾外 0.47 m 那段地面后雷达本来就看不见(跟车头一样);有后雷达、标过,按前进同一规矩。"""
    v = _view(_behind)
    v.rear = v.rear_cal = True
    verdict = G.check(-0.2, 0.0, 0.0, v, (0, 0, 0))
    assert verdict.cause == "unknown" and not verdict.stops, verdict


def test_后退_没后雷达或没标过_身后视野里看不见_停():
    for rear, cal in ((False, False), (True, False)):
        v = _view(_behind)
        v.rear, v.rear_cal = rear, cal
        verdict = G.check(-0.2, 0.0, 0.0, v, (0, 0, 0))
        assert verdict.cause == "blind" and verdict.stops, (rear, cal, verdict)


def test_后退_身后视野里看不见_停():
    v = G.check(-0.2, 0.0, 0.0, _view(_behind), (0, 0, 0))
    assert v.cause == "blind" and v.stops, v


def test_前进急弯_车尾甩进盲带看不见_停():
    """前进 0.2 m/s、左转 1.2 rad/s(转弯半径比车身外接圆小):车尾右角甩进右侧盲带。"""
    v = G.check(0.2, 1.2, 0.0, _view(_band), (0, 0, 0))
    assert v.cause == "blind" and v.stops, v


def test_原地转_车头视野里看不见_也停():
    """原地转时车头两角扫的那一小块在前雷达视野里、看不见(被挡):停,不按前进的降速处理。"""
    v = G.check(0.0, 1.0, 0.0, _view(lambda x, y: 0.45 < x < 0.7 and abs(y) > 0.2), (0, 0, 0))
    assert v.cause == "blind" and v.stops, v


def test_站着不动_十秒以前的帧只能说有东西_不能证明是空():
    t = [0.0]
    v = ObstacleView(monotonic=lambda: t[0], latency_s=0.0)
    v.note_odom(0.0, 0.0, 0.0)
    v.on_grid(_grid(cells_occ=[(10, 2)], size=20))        # 全看过:左侧盲带里 (0.05, -0.75) 有东西
    front_only = [(r, k) for r in range(15, 20) for k in range(20)]
    for i in range(1, int(MEMORY_S) + 6):
        t[0] = float(i)
        v.note_odom(0.0, 0.0, 0.0)                        # 一直站着
        v.on_grid(_grid(cells_known=front_only, seq=i + 1, size=20))
    hit, unk = v.lookup([(0.05, 0.75), (0.05, -0.75)], (0.0, 0.0, 0.0))
    assert unk == [0], "旧帧说空:超过 10 s 不算数,当看不见"
    assert hit == [1], "旧帧说有东西:照样记着"


def test_站着十秒以内_旧帧说空照样算():
    t = [0.0]
    v = ObstacleView(monotonic=lambda: t[0], latency_s=0.0)
    v.note_odom(0.0, 0.0, 0.0)
    v.on_grid(_grid(size=20))
    t[0] = MEMORY_S - 1.0
    v.note_odom(0.0, 0.0, 0.0)
    v.on_grid(_grid(cells_known=[(r, k) for r in range(15, 20) for k in range(20)], seq=2,
                    size=20))
    _, unk = v.lookup([(0.05, 0.75)], (0.0, 0.0, 0.0))
    assert unk == []


def test_站着超过十秒再原地转_盲带旧记忆不算_停():
    """场景:机器人在巡逻点站了 30 s,有人可能走到它侧面(两侧前后雷达都看不见)。原来 60 s 的旧帧
    说那儿空,原地转照转;现在停,交给脱困(先直着挪、看清再转)。"""
    t = [0.0]
    v = ObstacleView(monotonic=lambda: t[0], latency_s=0.0)
    v.note_odom(0.0, 0.0, 0.0)
    v.on_grid(_grid(size=N))                              # 走到这儿时全看过、空
    see = [(r, k) for r in range(N) for k in range(N) if not _band(_c(r), _c(k))]
    for i in range(1, 31):
        t[0] = float(i)
        v.note_odom(0.0, 0.0, 0.0)
        v.on_grid(_grid(cells_known=see, seq=i + 1, size=N))
    verdict = G.check(0.0, 0.6, 0.0, v, (0, 0, 0))
    assert verdict.cause == "blind" and verdict.stops, verdict


def test_盲带拦的_结论里带盲带几处_后退拦的不带():
    v = G.check(0.0, 0.6, 0.0, _view(_band), (0, 0, 0))
    assert v.band > 0
    v = G.check(-0.2, 0.0, 0.0, _view(_behind), (0, 0, 0))
    assert v.cause == "blind" and v.band == 0


def _走着_十二秒前看过两侧():
    """机器人一直在慢慢走(不算站着);12 s 前那一帧全看过、空,之后只看见前面。"""
    t = [0.0]
    v = ObstacleView(monotonic=lambda: t[0], latency_s=0.0)
    v.note_odom(0.0, 0.0, 0.0)
    v.on_grid(_grid(size=N))
    see = [(r, k) for r in range(N) for k in range(N) if not _band(_c(r), _c(k))]
    for i in range(1, 13):
        t[0] = float(i)
        v.note_odom(0.02 * i, 0.0, 0.0)                    # 每秒挪 2 cm:挪了窝
        v.on_grid(_grid(cells_known=see, seq=i + 1, size=N))
    return v


def test_脱困掉头时_盲带空的记忆认15秒_平时10秒():
    """用户 11-14:1.3 m 死胡同掉头(先挪 1.2 m 看清、再转 180° 要 8 s 多)跟 10 s 冲突;只在脱困动作
    进行中认 15 s(机器人在动、看得见、有声音),平时照旧 10 s。"""
    from nexwar_agent.obstacles import REC_FREE_S
    assert REC_FREE_S == 15.0
    v = _走着_十二秒前看过两侧()
    pose = (0.24, 0.0, 0.0)
    assert G.check(0.0, 0.6, 0.0, v, pose).cause == "blind", "平时:12 s 前的不算"
    assert G.check(0.0, 0.6, 0.0, v, pose, free_s=REC_FREE_S).ok, "脱困:15 s 以内的算"
