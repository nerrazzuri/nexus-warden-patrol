"""几何判定器(tools/nav_stability_bench_dev/geom_oracle.py):导航 V1 第 2 节验收用的独立判定。"""

from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path

import numpy as np
import pytest

_P = Path(__file__).resolve().parents[1] / "tools" / "nav_stability_bench_dev" / "geom_oracle.py"
_spec = importlib.util.spec_from_file_location("geom_oracle", _P)
go = importlib.util.module_from_spec(_spec)
sys.modules["geom_oracle"] = go
_spec.loader.exec_module(go)

RES = 0.05


def grid(w_m: float, h_m: float) -> np.ndarray:
    """全是墙,下面再挖出能走的地方。"""
    return np.ones((int(round(h_m / RES)), int(round(w_m / RES))), dtype=bool)


def carve(g: np.ndarray, x0: float, y0: float, x1: float, y1: float) -> None:
    g[int(round(y0 / RES)):int(round(y1 / RES)), int(round(x0 / RES)):int(round(x1 / RES))] = False


def judge(g, start, goal):
    return go.judge(g, RES, (0.0, 0.0), start, goal)


def corridor(width: float) -> np.ndarray:
    g = grid(7.0, 3.0)
    carve(g, 0.5, 1.5 - width / 2, 6.5, 1.5 + width / 2)
    return g


def test_default_body_is_route_validator_size():
    assert 2 * go.HALF_LEN == pytest.approx(1.43)
    assert 2 * go.HALF_WID == pytest.approx(0.98)


# 栅格 0.05 m:宽度取整格(0.95 m 画出来会变成 1.0 m)
@pytest.mark.parametrize(("width", "ok"), [(1.20, True), (1.10, True), (1.00, True), (0.90, False)])
def test_straight_corridor_by_width(width, ok):
    v = judge(corridor(width), (2.0, 1.5, 0.0), (5.0, 1.5, 0.0))
    assert v.feasible is ok
    if not ok:
        assert v.reason == "start_blocked"            # 不到 0.98 m:连站都站不下


def test_pinch_in_the_middle_is_no_path():
    g = corridor(1.20)
    g[:, int(3.4 / RES):int(3.7 / RES)] = True
    carve(g, 3.4, 1.5 - 0.45, 3.7, 1.5 + 0.45)        # 中间 0.3 m 长只剩 0.9 m 宽
    v = judge(g, (2.0, 1.5, 0.0), (5.0, 1.5, 0.0))
    assert (v.feasible, v.reason) == (False, "no_path")


def test_turn_around_in_dead_end_needs_room():
    # 1.2 m 宽的死胡同:车身对角线 1.72 m,原地转不开
    g = corridor(1.20)
    v = judge(g, (3.0, 1.5, 0.0), (3.0, 1.5, math.pi))
    assert (v.feasible, v.reason) == (False, "no_path")
    # 左头接一个 3 × 3 m 的房间:退回去在房间里掉头,再回来
    g2 = grid(10.0, 4.0)
    carve(g2, 0.5, 0.5, 3.5, 3.5)
    carve(g2, 3.5, 2.0 - 0.6, 9.5, 2.0 + 0.6)
    assert judge(g2, (6.0, 2.0, 0.0), (6.0, 2.0, math.pi)).feasible


def test_goal_heading_free_when_none():
    assert judge(corridor(1.20), (3.0, 1.5, 0.0), (5.0, 1.5, None)).feasible


def test_strafe_sideways_into_a_side_pocket():
    # 走廊旁边一个 1.6 × 1.1 m 的凹进去:朝向不变横移进去(D1 能横移),不用转
    g = corridor(1.20)
    carve(g, 3.0, 2.0, 4.6, 2.95)
    assert judge(g, (2.0, 1.5, 0.0), (3.8, 2.3, 0.0)).feasible


def test_outside_and_goal_in_wall():
    g = corridor(1.20)
    assert judge(g, (2.0, 1.5, 0.0), (9.0, 1.5, 0.0)).reason == "outside"
    assert judge(g, (2.0, 1.5, 0.0), (3.0, 0.2, None)).reason == "goal_blocked"


def test_start_heading_free_when_none():
    # 1.25 m 宽的南北向走廊只有朝南北站得下(车身长 1.43 m);起点朝东站不下,不限朝向就行
    g = grid(3.0, 6.0)
    carve(g, 1.0, 0.5, 2.25, 5.5)                     # 1.25 m 宽、竖着的走廊
    assert judge(g, (1.6, 2.0, 0.0), (1.6, 4.0, None)).reason == "start_blocked"
    assert judge(g, (1.6, 2.0, None), (1.6, 4.0, None)).feasible


def test_start_against_wall_gets_half_metre_slack():
    # 起点贴着走廊尽头的墙(车身放不下),往外 0.3 m 就放得下:跟 Validator 一样头 0.5 m 不查
    g = corridor(1.20)
    assert judge(g, (0.9, 1.5, 0.0), (5.0, 1.5, 0.0)).feasible
    # 离能站的地方超过 0.5 m:照旧放不下
    g2 = corridor(1.20)
    g2[:, :int(3.0 / RES)] = True
    carve(g2, 2.0, 1.5 - 0.3, 3.0, 1.5 + 0.3)           # 0.6 m 宽的小口,往前 1 m 才到走廊
    assert judge(g2, (2.1, 1.5, 0.0), (5.0, 1.5, 0.0)).reason == "start_blocked"
