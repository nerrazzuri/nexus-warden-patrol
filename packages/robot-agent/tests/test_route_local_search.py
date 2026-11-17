"""外审 11-14、用户定:路线检查的局部搜索不能横移,而且要输出一条查过余量的路,Nav2 就按这条走。

Smac 规划的路只保证车身不碰墙(1.2 m 宽的 L 形走廊在拐角正中原地转,只剩 0 cm),达不到每边 0.10 m
的底线;其实边走边转、往外侧让一让就过得去。局部搜索在窄的那一段周围,按 (x, y, 朝向) 只用
「沿车头前进 / 后退」和「原地转」找一条每处都留够余量的走法,拼回路线里,整条再按原来的规矩
逐个位姿查一遍 —— 查过的就是要执行的。
"""
from __future__ import annotations

import math

import numpy as np
import pytest

from nexwar_agent.route_check import check_route, densify, pose_margins
from nexwar_agent.route_cspace import search_path
from nexwar_contract.footprint import ROUTE_MARGIN_MIN

RES = 0.05


def _lmap(w: float) -> np.ndarray:
    """6 × 6 m:横臂 y∈[1, 1+w]、x∈[0.5, 4];竖臂 x∈[4−w, 4]、y∈[1, 5]。"""
    walls = np.ones((120, 120), dtype=bool)

    def free(x0, x1, y0, y1):
        walls[round(y0 / RES):round(y1 / RES), round(x0 / RES):round(x1 / RES)] = False
    free(0.5, 4.0, 1.0, 1.0 + w)
    free(4.0 - w, 4.0, 1.0, 5.0)
    return walls


def _smac_l(w: float):
    """Smac 的样子:直走到拐角正中、原地转 90°、直走上去。"""
    cx, cy = 4.0 - w / 2, 1.0 + w / 2
    return [(1.2, cy, 0.0), (cx, cy, 0.0), (cx, cy, math.pi / 2), (cx, 4.3, math.pi / 2)]


def _no_strafe(path, tol_m=0.002):
    """相邻两个位姿:要么原地转(位置不动),要么沿车头(前 / 后)走,横向分量不超过 ``tol_m``
    (外审 11-17 I2:原来许 3° + 3.6 cm,接缝的横移和每步偏半档都放过去了)。"""
    bad = []
    for a, b in zip(path, path[1:], strict=False):
        dx, dy = b[0] - a[0], b[1] - a[1]
        d = math.hypot(dx, dy)
        if d < 1e-6:
            continue
        yaw = a[2] if abs(math.remainder(b[2] - a[2], 2 * math.pi)) < 1e-6 else None
        if yaw is None:
            bad.append((a, b, "边走边转的一步"))
            continue
        lat = abs(-math.sin(yaw) * dx + math.cos(yaw) * dy)
        if lat > tol_m:
            bad.append((a, b, round(lat, 3)))
    return bad


def test_L形1米2_拐角原地转余量不够_局部搜索找到不横移的路_整条查过():
    walls = _lmap(1.2)
    r = check_route(_smac_l(1.2), walls, RES, (0.0, 0.0))
    assert r.ok and r.status == "ok" and r.tight, r
    assert r.path is not None, "放行靠的是局部搜索:要执行的路得给出来"
    p = r.path
    assert math.dist(p[0][:2], (1.2, 1.6)) < 1e-6 and p[0][2] == pytest.approx(0.0)
    assert math.dist(p[-1][:2], (3.4, 4.3)) <= 0.1 + 1e-6
    assert abs(math.remainder(p[-1][2] - math.pi / 2, 2 * math.pi)) <= math.radians(5.1)
    assert not _no_strafe(p), _no_strafe(p)[:3]
    dense = densify(p)
    along = np.concatenate([[0.0], np.cumsum([math.dist(a[:2], b[:2])
                                              for a, b in zip(dense, dense[1:], strict=False)])])
    m = pose_margins([q for q, s in zip(dense, along, strict=True) if s >= 0.5], walls, RES,
                     (0.0, 0.0))
    assert m.min() >= ROUTE_MARGIN_MIN - 1e-9, "拼好的整条路每处都留够底线"
    assert r.margin == pytest.approx(float(m.min()))


def test_L形1米0_不横移过不去_照旧拒():
    r = check_route(_smac_l(1.0), _lmap(1.0), RES, (0.0, 0.0))
    assert r.status == "refused" and r.path is None, r


def test_原路线本来就够宽_不搜_不给路():
    r = check_route(_smac_l(1.6), _lmap(1.6), RES, (0.0, 0.0))
    assert r.ok and r.path is None


def test_开阔地_搜出来的路不倒车():
    walls = np.zeros((80, 80), dtype=bool)
    walls[38:42, 36:48] = True                             # 正前方 x 1.8–2.4 一道矮墙,绕过去
    p = search_path((1.0, 2.0, 0.0), (3.4, 2.0, 0.0), walls, RES, (0.0, 0.0),
                    ROUTE_MARGIN_MIN, span=[(1.0, 2.0, 0.0), (3.4, 2.0, 0.0)])
    assert p is not None
    for a, b in zip(p, p[1:], strict=False):
        dx, dy = b[0] - a[0], b[1] - a[1]
        assert math.cos(a[2]) * dx + math.sin(a[2]) * dy >= -1e-6, ("倒车了", a, b)


def test_窗口太大_不搜():
    walls = np.zeros((2000, 2000), dtype=bool)
    p = search_path((1.0, 1.0, 0.0), (90.0, 90.0, 0.0), walls, RES, (0.0, 0.0),
                    ROUTE_MARGIN_MIN, span=[(1.0, 1.0, 0.0), (90.0, 90.0, 0.0)])
    assert p is None


def test_搜一次不慢():
    import time
    walls = _lmap(1.2)
    t0 = time.perf_counter()
    check_route(_smac_l(1.2), walls, RES, (0.0, 0.0))
    assert time.perf_counter() - t0 < 3.0


def test_窄的那一小段周围搜不到_整条路线再搜一次_照样整条查过才放行(monkeypatch):
    """仿真 11-15(C 组):过门转弯、终点贴墙,在窄的那一小段周围截的窗里搜不到(要多退一点、绕
    远一点才转得过来);整条路线一次搜能找到、整条查也过。小窗搜不到时整条再搜一次。"""
    from nexwar_agent import route_check as rck
    from nexwar_agent import route_cspace as rcs
    real = rcs.search_path
    calls = []

    def fake(entry, exit_, walls, res, origin, need, *, span=(), goal_end=False, **kw):
        whole = math.dist(entry[:2], (1.2, 1.6)) < 1e-6 and goal_end
        calls.append("整条" if whole else "小窗")
        if not whole:
            return None                                    # 小窗搜不到
        return real(entry, exit_, walls, res, origin, need, span=span, goal_end=goal_end, **kw)
    monkeypatch.setattr(rck, "search_path", fake)
    walls = _lmap(1.2)
    r = check_route(_smac_l(1.2), walls, RES, (0.0, 0.0))
    assert calls[0] == "小窗" and calls[-1] == "整条", calls
    assert r.ok and r.path is not None, r
    dense = densify(r.path)
    m = pose_margins([q for q in dense if math.dist(q[:2], (1.2, 1.6)) > 0.5], walls, RES,
                     (0.0, 0.0))
    assert m.min() >= ROUTE_MARGIN_MIN - 1e-9


def test_整条也搜不到_照旧拒(monkeypatch):
    from nexwar_agent import route_check as rck
    monkeypatch.setattr(rck, "search_path", lambda *a, **k: None)
    r = check_route(_smac_l(1.2), _lmap(1.2), RES, (0.0, 0.0))
    assert r.status == "refused" and r.path is None


def test_小窗拼好的整条查不过_也整条再搜一次(monkeypatch):
    from nexwar_agent import route_check as rck
    real = rck._spliced
    monkeypatch.setattr(rck, "_spliced", lambda segs, dense, *a: [*dense[:5], (3.4, 1.0, 0.0),
                                                                *dense[5:]])   # 拼出一条压墙的
    r = check_route(_smac_l(1.2), _lmap(1.2), RES, (0.0, 0.0))
    assert r.ok and r.path is not None and (3.4, 1.0, 0.0) not in r.path
    monkeypatch.setattr(rck, "_spliced", real)


@pytest.mark.parametrize(("width", "at_least"), [(1.3, 0.18), (1.2, 0.15)])
def test_仿真11_16_搜路先要宽的_有宽路不贴着底线走(width, at_least):
    """A/B/C 仿真(11-16):只按底线 0.10 搜,搜出来的路余量中位 0.105,机器人走偏几厘米就被守卫挡住。
    先按每边 0.20 搜,搜不到再 0.15,最后才 0.10。1.3 m 那条只要 0.18:终点本身离顶头 0.185。"""
    r = check_route(_smac_l(width), _lmap(width), RES, (0.0, 0.0))
    assert r.ok and r.path is not None, r
    assert r.margin >= at_least - 0.005, r


@pytest.mark.parametrize("entry", [(1.0, 2.0, 0.0), (1.013, 1.982, 0.03), (1.0, 2.0, 0.6)])
def test_外审1117_I2_入口不在格子中心_接上去也不横移_每一步沿车头(entry):
    """外审 11-17 I2:原来入口直接连到格子中心((1, 2) → (0.975, 1.975) 横着 2.5 cm),每档按 5° 整档
    走、一步最多偏半档。现在只用原地转 + 沿车头直走接上,整条验收。"""
    walls = np.zeros((80, 80), dtype=bool)
    walls[38:42, 36:48] = True
    p = search_path(entry, (3.4, 2.0, 0.0), walls, RES, (0.0, 0.0), ROUTE_MARGIN_MIN,
                    span=[entry, (3.4, 2.0, 0.0)])
    assert p is not None
    assert p[0] == pytest.approx(entry) and p[-1] == pytest.approx((3.4, 2.0, 0.0))
    assert not _no_strafe(p, 1e-6), _no_strafe(p, 1e-6)[:3]


def _phys_hits(path, walls, res, origin):
    """物理车身(半长 0.465、半宽 0.24 的矩形)跟墙格(方格)按分离轴判相交 → 碰到的位姿。"""
    rr, cc = np.nonzero(walls)
    wx, wy = origin[0] + (cc + 0.5) * res, origin[1] + (rr + 0.5) * res
    out = []
    for px, py, a in densify(path):
        c, s = math.cos(a), math.sin(a)
        dx, dy = wx - px, wy - py
        hit = ((abs(dx) <= 0.465 * abs(c) + 0.24 * abs(s) + res / 2)
               & (abs(dy) <= 0.465 * abs(s) + 0.24 * abs(c) + res / 2)
               & (abs(dx * c + dy * s) <= 0.465 + res / 2 * (abs(c) + abs(s)))
               & (abs(-dx * s + dy * c) <= 0.24 + res / 2 * (abs(c) + abs(s))))
        if hit.any():
            out.append((px, py, math.degrees(a)))
    return out


def test_外审1117第2轮_贴墙起步_搜出来的入口原地转不吃起步豁免_转的时候不许比站着更贴墙():
    """外审 11-17 第 2 轮(codex 复现):墙从 x=3.0 起,机器人在 (2.485, 2, 15°) 贴墙起步,
    原路线先倒过一段窄处再绕到终点(物理上不碰)。局部搜索在入口先原地转,
    转到约 27.5° 车身压进墙 8 mm,可整条复查按走过的路程跳过起步 0.5 m,原地转一步都没查,
    放行了。现在:插在起步那段的位姿照查,余量不低于 min(要求, 站着时);转向也按细角度查。"""
    res, origin = 0.05, (-2.0, -2.0)
    rr, cc = np.indices((200, 200))
    x, y = origin[0] + (cc + 0.5) * res, origin[1] + (rr + 0.5) * res
    q = (2.485, 2.0, math.radians(15))
    lat = -(x - q[0]) * math.sin(q[2]) + (y - q[1]) * math.cos(q[2])
    walls = (x >= 3.0) | ((x >= 0.5) & (x < 1.95) & (abs(lat) >= 0.34) & (abs(lat) < 0.7))
    b = (-0.4, 2.0 + (-0.4 - q[0]) * math.tan(q[2]), q[2])
    route = [q, b, (*b[:2], math.pi / 2), (-0.4, 4.0, math.pi / 2), (-0.4, 4.0, 0.0),
             (2.2, 4.0, 0.0), (2.2, 4.0, math.pi / 2)]
    assert not _phys_hits(route, walls, res, origin)             # 原路线本身物理上不碰
    r = check_route(route, walls, res, origin)
    if r.ok and r.path is not None:
        hits = _phys_hits(r.path, walls, res, origin)
        assert not hits, hits[:3]
        here = float(pose_margins([q], walls, res, origin)[0])
        fine = [p for p in densify(r.path) if math.dist(p[:2], q[:2]) < 1e-6]   # 起点上原地转的那些
        m = pose_margins(fine, walls, res, origin)
        assert float(m.min()) >= min(ROUTE_MARGIN_MIN, here) - 1e-9, (float(m.min()), here)
