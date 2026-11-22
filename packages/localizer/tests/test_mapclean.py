"""W70 三维定位地图去噪(用户 2026-11-03 现场:「需要先做地图噪点清理」)。"""

from __future__ import annotations

import numpy as np
from nexwar_localizer import mapclean as C

V = 0.25


def _wall(x: float, y0: float, y1: float, z1: float = 2.0) -> np.ndarray:
    ys, zs = np.meshgrid(np.arange(y0, y1, 0.1), np.arange(0.0, z1, 0.1))
    return np.stack([np.full(ys.size, x), ys.ravel(), zs.ravel()], 1)


def _floor(x0: float, x1: float, y0: float, y1: float) -> np.ndarray:
    xs, ys = np.meshgrid(np.arange(x0, x1, 0.1), np.arange(y0, y1, 0.1))
    return np.stack([xs.ravel(), ys.ravel(), np.zeros(xs.size)], 1)


def _person(x: float, y: float) -> np.ndarray:
    zs = np.arange(0.2, 1.7, 0.1)
    return np.array([(x + dx, y + dy, z) for z in zs for dx in (0, 0.1) for dy in (0, 0.1)])


def _scan(sensor: np.ndarray, world: np.ndarray) -> np.ndarray:
    """「雷达看见了」这些点:按方向去掉被前面的点挡住的(粗略,够测试用)。"""
    d = world - sensor
    r = np.linalg.norm(d, axis=1)
    az = np.round(np.arctan2(d[:, 1], d[:, 0]) / 0.02).astype(int)
    el = np.round(np.arcsin(d[:, 2] / np.maximum(r, 1e-9)) / 0.03).astype(int)
    key = az * 10000 + el
    order = np.lexsort((r, key))
    _, first = np.unique(key[order], return_index=True)
    return world[order[first]]


def _scene() -> tuple[np.ndarray, list[tuple[np.ndarray, np.ndarray]], np.ndarray]:
    """走廊:两面墙(y=±2)、尽头一面墙(x=10)、地面;建图开头有个人站在 (6, 0)(后来走了)。"""
    static = np.vstack([_wall(10.0, -2, 2, z1=4.0), _floor(0, 10, -2, 2),
                        ])
    side = np.vstack([np.stack([xx.ravel(), np.full(xx.size, s), zz.ravel()], 1)
                      for s in (-2.0, 2.0)
                      for xx, zz in [np.meshgrid(np.arange(0, 10, 0.1), np.arange(0, 2, 0.1))]])
    static = np.vstack([static, side])
    person = _person(6.0, 0.0)
    scans = []
    for k, x in enumerate(np.arange(0.5, 5.0, 0.25)):
        s = np.array([x, 0.0, 0.5])
        world = np.vstack([static, person]) if k < 3 else static     # 前 3 帧人还在
        scans.append((s, _scan(s, world)))
    pts = np.vstack([static, person])
    return pts, scans, person


def test_W70_建图时站着的人_后来射线穿过去了_从地图里删掉_墙和地面不删() -> None:
    pts, scans, person = _scene()
    m = C.voxel(pts, V)
    rc = C.RayClear(m, V)
    for s, p in scans:
        rc.add(s, p)
    h = m[:, 2]                                            # 测试场景地面就是 z=0
    dyn = rc.dynamic(height=h)
    pk = {tuple(k) for k in np.floor(person / V).astype(int)}
    mk = np.floor(m / V).astype(int)
    is_person = np.array([tuple(k) in pk for k in mk])
    body = is_person & (h >= C.FLOOR_KEEP_M)
    assert dyn[body].all()                                 # 人(脚下那格算地面)全清掉
    wall_end = np.abs(m[:, 0] - 10.0) < 0.2
    assert not dyn[wall_end].any()                         # 尽头的墙一个不删
    floor = h < 0.1
    assert not dyn[floor].any()                            # 擦地的射线不清地面


def test_W70_零星孤点删掉_成片的墙不删() -> None:
    wall = C.voxel(_wall(5.0, -2, 2), V)
    lone = np.array([[1.0, 1.0, 1.0], [-3.0, 4.0, 0.5]])
    m = np.vstack([wall, lone])
    iso = C.isolated(m, V)
    assert iso[-2:].all()
    assert not iso[:-2].any()


def test_W70_一步删得太多_这步不做_记下来() -> None:
    m = np.arange(30, dtype=float).reshape(10, 3)
    mask = np.zeros(10, bool)
    mask[:6] = True                                        # 一步要删 60%
    kept, stats = C.apply(m, {"dynamic": mask})
    assert len(kept) == 10
    assert stats["dynamic"] == 0 and "dynamic" in stats["skipped"][0]
    mask2 = np.zeros(10, bool)
    mask2[:1] = True
    kept, stats = C.apply(m, {"dynamic": mask2})
    assert len(kept) == 9 and stats == {"before": 10, "dynamic": 1, "kept": 9, "skipped": []}


def test_W70_几步删的点重叠_各算各的不重复扣() -> None:
    m = np.zeros((100, 3))
    a = np.zeros(100, bool)
    a[:5] = True
    b = np.zeros(100, bool)
    b[3:8] = True                                          # 跟上一步重了 2 个
    kept, stats = C.apply(m, {"dynamic": a, "isolated": b})
    assert stats["dynamic"] == 5 and stats["isolated"] == 3 and stats["kept"] == 92
    assert len(kept) == 92


def test_W70_只透过开口看到的格子上的点删掉_别的格子不动() -> None:
    seen = np.zeros((4, 4), bool)
    seen[0, 3] = True                                      # 行 0 = y 最大:格子 x∈[3,4), y∈[3,4)
    pts = np.array([[3.5, 3.5, 1.0], [3.5, 3.5, 2.5], [0.5, 0.5, 1.0], [9.0, 9.0, 1.0]])
    m = C.through_mask(pts, pts[:, :2], seen, (0.0, 0.0), 1.0)
    assert m.tolist() == [True, True, False, False]
    assert not C.through_mask(pts, pts[:, :2], None, (0.0, 0.0), 1.0).any()


def test_离路多远_纯numpy_跟逐个算的一样():
    rng = np.random.default_rng(3)
    traj = np.cumsum(rng.normal(0, 0.2, (400, 3)), 0)
    pts = rng.uniform(-20, 20, (3000, 3))
    got = C.traj_distance(pts, traj, step=1e-9, chunk=700)       # 不抽稀:跟暴力算逐个比
    want = np.sqrt(((pts[:, None, :] - traj[None, :, :]) ** 2).sum(2)).min(1)
    assert np.allclose(got, want, atol=1e-6)
    coarse = C.traj_distance(pts, traj)                          # 抽稀以后最多差半格多一点
    assert np.all(coarse >= want - 1e-9) and np.all(coarse - want <= C.FAR_TRAJ_STEP_M * 1.8)
    assert np.isinf(C.traj_distance(pts[:3], np.zeros((0, 3)))).all()


def test_远处稀点_近处照旧_远处要的邻居多_真墙留着():
    """用户 11-22:远距离零散噪点。近处一个两个挨着的不删(交给孤点那一步);远处两个挨着的删;
    远处成片的墙(稀,但每点都有好几个邻居)留着。"""
    traj = np.stack([np.linspace(0, 5, 50), np.zeros(50), np.zeros(50)], 1)
    pair_near = np.array([[5.0, 8.0, 1.0], [5.25, 8.0, 1.0]])            # 离路 8 m
    pair_mid = np.array([[5.0, 20.0, 1.0], [5.25, 20.0, 1.0]])           # 20 m:各 1 个邻居 < 2
    # 两头各 1 个邻居、中间 2 个
    trio_mid = np.array([[0.0, -20.0, 1.0], [0.25, -20.0, 1.0], [0.5, -20.0, 1.0]])
    # 40 m 外一面墙:真地图是很多帧叠起来再按体素降采样的,远处的墙在体素上也连成片(Top Glove 站点图
    # 20–60 m 有 2.8 万个点,邻居不到 3 个的约 1200 个);隔一格才有一个点的「墙」孤点那一步本来就删
    ys, zs = np.meshgrid(np.arange(-6, 6, 0.25), np.arange(0, 4, 0.25))
    wall = np.stack([np.full(ys.size, 45.0), ys.ravel(), zs.ravel()], 1)
    pts = np.vstack([pair_near, pair_mid, trio_mid, wall])
    m = C.far_sparse(pts, V, traj)
    assert not m[:2].any()                                               # 近处:不归这一步管
    assert m[2:4].all()
    assert list(m[4:7]) == [True, False, True]
    assert not m[7:].any(), "远处的真墙不能删"
    assert not C.far_sparse(pts, V, traj, tiers=()).any()
    assert C.far_sparse(np.zeros((0, 3)), V, traj).shape == (0,)
