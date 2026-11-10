"""路沿、绿化岛(用户 11-10,11-16 工厂 POC):高出路面 7–40 cm 的陡边在建图时认出来,单独一层
``curb.pbm``,Nav2 当「尽量别走」(代价高、不是墙)。实时避障的 15 cm 线不动。

合成数据跟 ``test_loc_grid`` 同一套:MOLA 系 X 朝上,地图平面系里摆东西再转回去。"""

from __future__ import annotations

import pytest

np = pytest.importorskip("numpy")

from nexwar_localizer import grid as G  # noqa: E402
from test_loc_grid import _frames  # noqa: E402


def _yard(frames, *, island=0.15, slope=0.0, noise=0.0, walk_y=0.0, stones=(), seed=7, wall_y=None):
    """开阔的停车场:24 × 16 m 路面,一个 3 × 2 m 的绿化岛(x 4–7、y 2–4,比路面高 ``island``,
    四边是竖着的路沿面),狗沿 y = ``walk_y`` 从 x = 0 走到 10。``stones``:(x, y, 高) 的小石头,
    边长 0.1 m。地面按 ``slope`` 往 +x 升;``noise``:测距噪声(米)。"""
    L = np.asarray(frames.level_matrix())
    rng = np.random.default_rng(seed)
    g = rng.uniform([-6, -8], [18, 8], (400000, 2))
    on = (g[:, 0] >= 4) & (g[:, 0] <= 7) & (g[:, 1] >= 2) & (g[:, 1] <= 4)
    z = slope * g[:, 0] + np.where(on, island, 0.0)
    pts = [np.c_[g, z]]
    if island:
        for h in np.linspace(0.0, island, 6):           # 路沿竖着的那一面
            xs = np.arange(4, 7, 0.02)
            ys = np.arange(2, 4, 0.02)
            pts += [np.c_[xs, np.full_like(xs, 2.0), slope * xs + h],
                    np.c_[xs, np.full_like(xs, 4.0), slope * xs + h],
                    np.c_[np.full_like(ys, 4.0), ys, np.full_like(ys, slope * 4.0 + h)],
                    np.c_[np.full_like(ys, 7.0), ys, np.full_like(ys, slope * 7.0 + h)]]
    if wall_y is not None:                                # 一堵墙(竖面从地面一直到 2 m)
        xs = np.arange(-2, 12, 0.02)
        pts += [np.c_[xs, np.full_like(xs, wall_y), slope * xs + hh]
                for hh in np.arange(0, 2.0, 0.03)]
    for x, y, h in stones:
        s = rng.uniform([x - 0.05, y - 0.05], [x + 0.05, y + 0.05], (40, 2))
        pts.append(np.c_[s, slope * s[:, 0] + h])
    P = np.vstack(pts)
    if noise:
        P[:, 2] += rng.normal(0.0, noise, len(P))
    xs = np.linspace(0, 10, 60)
    traj = np.c_[xs, np.full(60, walk_y), slope * xs + 0.6]
    body = traj[:, :2].copy()
    return P @ L, traj @ L, body


def _curb(g, x, y):
    c = g.cell_of(x, y)
    assert c is not None, (x, y)
    return bool(g.curb[c]) if g.curb is not None else False


def test_绿化岛四边的路沿认出来_路面上没有():
    f = _frames()
    P, T, body = _yard(f)
    g = G.render(P, T, f, scans=[], body_path=body)
    assert g.curb is not None and g.curb.shape == g.image.shape
    for x, y in ((4.0, 3.0), (7.0, 3.0), (5.5, 2.0), (5.5, 4.0)):
        assert _curb(g, x, y), (x, y)
    for x, y in ((2.0, 0.0), (5.5, -2.0), (10.0, 3.0), (2.0, 3.0), (9.0, 5.0)):
        assert not _curb(g, x, y), (x, y)
    assert not (g.curb & (g.image != G.FREE)).any(), "只标在能走的格子上"


def test_十厘米的矮路沿也认_五厘米的不认():
    f = _frames()
    P, T, body = _yard(f, island=0.10)
    g = G.render(P, T, f, scans=[], body_path=body)
    assert _curb(g, 4.0, 3.0) and _curb(g, 5.5, 4.0)
    P, T, body = _yard(f, island=0.05)
    g = G.render(P, T, f, scans=[], body_path=body)
    assert g.curb is None or not g.curb.any(), "5 cm 的高差(井盖、减速带)不算路沿"


def test_平地有测距噪声_坡地_都不冒假路沿():
    f = _frames()
    for kw in ({"noise": 0.02}, {"slope": 0.1}, {"slope": 0.15, "noise": 0.02}):
        P, T, body = _yard(f, island=0.0, **kw)
        g = G.render(P, T, f, scans=[], body_path=body)
        assert g.curb is None or not g.curb.any(), kw


def test_零星的小石头不算路沿():
    f = _frames()
    P, T, body = _yard(f, island=0.0, stones=((3.0, 2.0, 0.15), (8.0, -3.0, 0.2)))
    g = G.render(P, T, f, scans=[], body_path=body)
    assert g.curb is None or not g.curb.any()


def test_建图时机器人从路沿上走过去的地方_不标():
    """扫图的人把机器人开过了路沿(比如那里是斜坡口、本来就该走):走过的那一段留个口子。"""
    f = _frames()
    P, T, body = _yard(f, walk_y=3.0)                     # 沿 y=3 穿过绿化岛
    g = G.render(P, T, f, scans=[], body_path=body)
    assert not _curb(g, 4.0, 3.0) and not _curb(g, 7.0, 3.0), "走过的那一处留口子"
    assert _curb(g, 4.0, 2.4) or _curb(g, 4.0, 2.3), "口子旁边照样是路沿"
    assert _curb(g, 5.5, 2.0) and _curb(g, 5.5, 4.0)


def test_写出_curb_pbm_跟_floor_pgm_一样大_没有路沿不写(tmp_path):
    f = _frames()
    P, T, body = _yard(f)
    g = G.render(P, T, f, scans=[], body_path=body)
    p = G.write_curb(g, tmp_path / "curb.pbm")
    assert p is not None
    raw = p.read_bytes()
    head, w, h = raw.split(b"\n", 2)[0], *map(int, raw.split(b"\n", 2)[1].split())
    assert head == b"P4" and (h, w) == g.image.shape
    P, T, body = _yard(f, island=0.0)
    g = G.render(P, T, f, scans=[], body_path=body)
    assert G.write_curb(g, tmp_path / "none.pbm") is None
    assert not (tmp_path / "none.pbm").exists()


def test_墙根不冒假路沿():
    """11-10 广场图:墙脚那一格既有地面点、又有墙面下半截的点,取出来的「地面」被抬高,跟旁边路面一比
    成了路沿,整张图的墙边一圈红。只比两边都平整的格。"""
    f = _frames()
    P, T, body = _yard(f, island=0.0, wall_y=-3.0, noise=0.01)
    g = G.render(P, T, f, scans=[], body_path=body)
    assert g.curb is None or not g.curb.any(), int(g.curb.sum())


def test_离建图路线太远的不认():
    f = _frames()
    P, T, body = _yard(f, walk_y=-7.5)                     # 路线离绿化岛 9.5 m 以上
    g = G.render(P, T, f, scans=[], body_path=body)
    assert g.curb is None or not g.curb.any()
