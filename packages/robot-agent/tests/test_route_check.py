"""导航 V1 第 2 节:Route Validator V1.0 的几何检查(纯 Python,不碰 ROS)。

沿 Nav2 规划出的路线每 5 cm 放一个「物理车身 + 基础余量」(1.03 × 0.58),算每处离地图墙还剩多少
余量;最窄处 < 0.10 m(底线)就拒绝出发,报出是哪一处;0.10–0.20 m 放行但标「偏窄」
(用户 11-09:0.2 过不去就改成 0.1)。"""
from __future__ import annotations

import math

import numpy as np
import pytest

from nexwar_agent.route_check import check_route, densify, pose_margins
from nexwar_contract.footprint import BASE_HALF_LEN, BASE_HALF_WID, ROUTE_MARGIN, ROUTE_MARGIN_MIN

RES = 0.05


def _走廊(width, length=10.0, turn=False):
    """地图:x 方向的直走廊(中心 y = 2.0),宽 ``width``;``turn`` 时在 x = 6 处左转 90° 往 +y。
    返回 (walls, res, origin):walls[行 = y, 列 = x],True = 墙。"""
    n = int(12 / RES)
    yy, xx = np.mgrid[0:n, 0:n]
    cx, cy = (xx + 0.5) * RES, (yy + 0.5) * RES
    free = (np.abs(cy - 2.0) <= width / 2) & (cx <= length)
    if turn:
        free |= (np.abs(cx - 6.0) <= width / 2) & (cy >= 2.0 - width / 2)
        free &= ~((cx > 6.0 + width / 2) & (cy > 2.0 + width / 2))
    return ~free, RES, (0.0, 0.0)


def _直线(x0, x1, y=2.0, yaw=0.0, step=0.025):
    n = int(round((x1 - x0) / step))
    return [[x0 + i * step, y, yaw] for i in range(n + 1)]


def test_常数_三层车身口径():
    assert (BASE_HALF_LEN, BASE_HALF_WID) == pytest.approx((0.515, 0.29))
    assert ROUTE_MARGIN == pytest.approx(0.20)
    assert ROUTE_MARGIN_MIN == pytest.approx(0.10)


def test_插值到5厘米_朝向走最短角():
    d = densify([[0.0, 0.0, 3.0], [0.2, 0.0, -3.0]], step=0.05)
    assert len(d) == 6                     # 平移要 4 步;转 0.28 rad 角点扫 0.22 m → 5 步
    assert all(math.dist(a[:2], b[:2]) <= 0.05 + 1e-9 for a, b in zip(d, d[1:], strict=False))
    assert all(abs(p[2]) >= 3.0 - 1e-6 for p in d), "3.0 → -3.0 走过 π,不从 0 绕"


def test_居中直通道_余量等于半宽减车身半宽():
    walls, res, org = _走廊(1.2)
    m = pose_margins(densify(_直线(2.0, 8.0)), walls, res, org)
    assert m.min() == pytest.approx(0.6 - BASE_HALF_WID, abs=0.03)


def test_一米二直通道放行():
    walls, res, org = _走廊(1.2)
    r = check_route(_直线(1.0, 8.0), walls, res, org)
    assert r.ok and r.code == "" and r.margin >= ROUTE_MARGIN and not r.tight


def test_一米通道_路线偏离中心8厘米_能横向挪回去_放行():
    """1.0 m 走廊居中每边剩 0.21 m,只比要求多 1 cm;Smac 的线常常不在正中,控制器也不死贴线走。"""
    walls, res, org = _走廊(1.0)
    r = check_route(_直线(1.0, 8.0, y=2.08), walls, res, org)
    assert r.ok, r.why


def test_九十厘米通道_留不够二十厘米_放行但标偏窄():
    walls, res, org = _走廊(0.9)
    r = check_route(_直线(1.0, 8.0), walls, res, org)
    assert r.ok and r.code == "" and r.tight, r
    assert ROUTE_MARGIN_MIN <= r.margin < ROUTE_MARGIN


def test_七十厘米通道_不到底线_拒绝_报最窄处和要多宽():
    walls, res, org = _走廊(0.7)
    r = check_route(_直线(1.0, 8.0), walls, res, org)
    assert not r.ok and r.code == "route_too_narrow"
    assert r.margin == pytest.approx(0.35 - BASE_HALF_WID, abs=0.03)
    assert "0.78" in r.why and "0.10" in r.why and "离墙只剩" in r.why, r.why


def test_起步那一段不查_机器人本来就站在那儿():
    walls, res, org = _走廊(1.2)
    ys = (np.arange(walls.shape[0])[:, None] + 0.5) * RES
    walls[:, :int(0.75 / RES)] |= np.abs(ys - 2.0) > 0.4
    r = check_route(_直线(1.0, 8.0), walls, res, org)       # 起步时车尾那截窄,走开 0.5 m 后就宽
    assert r.ok, r.why


def test_终点贴墙_报目标点离墙太近():
    walls, res, org = _走廊(1.2)
    r = check_route(_直线(1.0, 9.75), walls, res, org)      # 走廊在 x = 10 封死,车头顶到墙
    assert not r.ok and r.code == "goal_too_close_to_wall", r
    assert "目标点" in r.why


def test_路线穿墙_余量为负_拒绝():
    walls, res, org = _走廊(1.2)
    r = check_route(_直线(1.0, 8.0, y=2.5), walls, res, org)
    assert not r.ok and r.margin < 0


@pytest.mark.parametrize(("width", "ok"), [(1.5, True), (1.4, False), (1.1, False)])
def test_L弯_按车身朝向扫(width, ok):
    """在拐角正中原地转 90°:车身外角(半对角 0.59 m)+ 底线 0.10 要离墙约 0.69 m,墙格再按方格
    算(扣半格):1.5 m 放行、偏窄;1.4 m 剩 0.08 不够。原来 1.3 m 靠每个位姿横挪 0.15 m 放行 ——
    挪过去的线不是要执行的路线(外审 11-14),现在拒。"""
    walls, res, org = _走廊(width, length=6.0 + width / 2, turn=True)
    path = _直线(1.0, 6.0) + [[6.0, 2.0 + i * 0.025, math.pi / 2] for i in range(1, 160)]
    r = check_route(path, walls, res, org)
    assert r.ok is ok, r
    if ok:
        assert r.tight


# ---- 11-14 外审(master 31bb0b5a 上复现):只查当前路线本身,三个漏查反例 ----

def _开阔地(n_m=6.0):
    n = int(n_m / RES)
    return np.zeros((n, n), dtype=bool)


def test_外审_原地转半圈_中间转到横着时扫到墙_要查出来():
    """同一位置朝向 0 → 180°:只插两头的话,转到 90° 那一刻车身半长朝墙、压进墙也查不到。"""
    walls = _开阔地()
    yy = (np.arange(walls.shape[0]) + 0.5) * RES
    walls[yy < 2.0 - 0.45, :] = True                         # 墙在中心下方 0.45 m
    pre = [[1.0 + i * 0.05, 2.0, 0.0] for i in range(41)]    # 先走 2 m(躲开起步免检)
    r = check_route(pre + [[3.0, 2.0, 0.0], [3.0, 2.0, math.pi]], walls, RES, (0.0, 0.0))
    assert r.status == "refused" and not r.ok, r
    assert r.margin < 0


def test_外审_插值按车身角点限步_转一个大角也拆细():
    pts = densify([[0.0, 0.0, 0.0], [0.0, 0.0, math.pi / 2]])
    corner = math.hypot(BASE_HALF_LEN + ROUTE_MARGIN, BASE_HALF_WID + ROUTE_MARGIN)
    for a, b in zip(pts, pts[1:], strict=False):
        assert abs(b[2] - a[2]) * corner <= 0.05 + 1e-9


def test_外审_车身伸出地图边_图外当墙():
    """中心离地图下边 0.10 m,图里没有墙:车身一半在图外,不能报余量 0.5。"""
    r = check_route([[1.0 + i * 0.05, 0.10, 0.0] for i in range(60)], _开阔地(), RES, (0.0, 0.0))
    assert r.status == "refused" and r.margin < 0, r


def test_外审_空路线_不算通过_算没查成():
    r = check_route([], _开阔地(), RES, (0.0, 0.0))
    assert not r.ok and r.status == "unchecked" and r.code == "no_route", r


def test_外审_已在终点不用动_算通过():
    walls = _开阔地()
    r = check_route([[3.0, 3.0, 0.5]], walls, RES, (0.0, 0.0))
    assert r.ok and r.status == "ok" and r.code == "at_goal", r


def test_外审_终点离墙零点二五_不许靠横挪背书_拒绝():
    """仿真 p0_goal_wall_d025:中心离墙 0.25 m(要 0.39 m),原来每个位姿横挪 0.15 m 找最宽的位置,
    就放行了 —— 挪过去的那条线不是要执行的路线。"""
    walls = _开阔地()
    yy = (np.arange(walls.shape[0]) + 0.5) * RES
    xx = (np.arange(walls.shape[1]) + 0.5) * RES
    walls[(yy > 4.0)[:, None] & (xx > 3.6)[None, :]] = True      # 墙只在终点边上
    r = check_route(_直线(1.0, 4.0, y=4.0 - 0.25), walls, RES, (0.0, 0.0))
    assert r.status == "refused" and r.code == "goal_too_close_to_wall", r
