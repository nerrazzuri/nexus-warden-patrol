"""Route Validator V1.0 的几何检查(导航 V1 第 2 节,``docs/导航V1-设计.md``)。纯 Python,不碰 ROS。

Nav2 规划出路线(``plan_result``,带朝向、不抽稀)之后、出发之前:

1. 把位姿插值到 ≤ 5 cm 一个(朝向走最短角);原地转也拆开:相邻两个位姿之间车身角点扫过的
   弧长也 ≤ 5 cm(外审 11-14:原地转半圈只插两头,转到横着那一刻压进墙也查不到)。
2. 每个位姿放「物理车身 + 基础余量」(半长 :data:`~nexwar_contract.footprint.BASE_HALF_LEN`、
   半宽 :data:`~nexwar_contract.footprint.BASE_HALF_WID`),算四边一起往外扩多少碰到地图墙,
   就是这一处的余量。
3. 最窄处余量 < :data:`~nexwar_contract.footprint.ROUTE_MARGIN_MIN`(底线 0.10 m)就拒绝出发:
   最窄处在终点附近报 ``goal_too_close_to_wall``,别处报 ``route_too_narrow``,原因里写在哪、剩多少、
   要多少。底线到 :data:`~nexwar_contract.footprint.ROUTE_MARGIN`(目标 0.20 m)之间放行,
   ``tight`` = True(用户 11-09:0.2 过不去就改成 0.1)。

**只查要执行的这条路线本身**(外审 11-14、用户定):原来每个位姿可以横挪 ±0.15 m 取最宽的位置,
等于拿一条不会被执行的线替这条路线背书(终点离墙 0.25 m 也放行了),已去掉。地图外当墙(车身
伸出地图边也算压墙)。

结论三种(``status``):``ok`` 查过、通过;``refused`` 查过、这条路线不满足余量;``unchecked``
没查成(空路线 ``no_route``;超时、规划失败等由调用方填)—— 没查成**不等于**通过,调用方按
降级规则处理(:mod:`nexwar_agent.bridges.nav2_nav`)。

定位:出发前的**通行性预筛**,不是安全闸门;运行时还有守卫(它本身也有已知的漏查、盲区和
未标定参数,同样不是绝对保证)。

起步那一小段(:data:`SKIP_START_M`)不查:机器人本来就站在那儿(停在墙边、桩上),不该因此走不了。
只看地图墙;人、车、临时障碍归守卫管。
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

from nexwar_contract.footprint import (
    BASE_HALF_LEN,
    BASE_HALF_WID,
    ROUTE_MARGIN,
    ROUTE_MARGIN_MIN,
)

STEP_M = 0.05
SKIP_START_M = 0.5
#: 最窄处离终点这么近(沿路线,米)算「目标点贴墙」。
GOAL_ZONE_M = 0.3
#: 余量算到这么大就够了(再远的墙不看)。
CAP_M = 0.5
#: 插值时角点按这个半径算弧长(目标余量那一层的车身外角):比它近的墙都查得到。
CORNER_R = math.hypot(BASE_HALF_LEN + ROUTE_MARGIN, BASE_HALF_WID + ROUTE_MARGIN)


@dataclass(frozen=True, slots=True)
class RouteCheck:
    #: 只有 ``status == "ok"`` 时为 True
    ok: bool
    #: 查过的位姿里最小的余量(米;负 = 车身压进墙);没有可查的位姿是 CAP_M
    margin: float
    #: 最窄处位姿 ``(x, y, yaw)``
    at: tuple[float, float, float] | None
    code: str = ""
    why: str = ""
    #: 放行了,但最窄处没留够目标余量(0.10–0.20 m)
    tight: bool = False
    #: ``ok`` / ``refused`` / ``unchecked``(见模块说明)
    status: str = "ok"


def unchecked(code: str, why: str) -> RouteCheck:
    """没查成:``ok`` 为 False,但不是「拒绝」—— 调用方按降级规则决定走不走。"""
    return RouteCheck(False, CAP_M, None, code, why, status="unchecked")


def _wrap(a: float) -> float:
    return (a + math.pi) % (2 * math.pi) - math.pi


def densify(poses: Sequence[Sequence[float]],
            step: float = STEP_M) -> list[tuple[float, float, float]]:
    """相邻位姿插值到不超过 ``step`` 米一个、车身角点(:data:`CORNER_R`)扫过的弧长也不超过
    ``step``;朝向按最短角插。"""
    if not poses:
        return []
    out = [(float(poses[0][0]), float(poses[0][1]), float(poses[0][2]))]
    for a, b in zip(poses, poses[1:], strict=False):
        d = math.dist(a[:2], b[:2])
        dyaw = _wrap(float(b[2]) - float(a[2]))
        n = max(1, math.ceil(d / step - 1e-9), math.ceil(abs(dyaw) * CORNER_R / step - 1e-9))
        for i in range(1, n + 1):
            t = i / n
            out.append((float(a[0]) + t * (float(b[0]) - float(a[0])),
                        float(a[1]) + t * (float(b[1]) - float(a[1])),
                        _wrap(float(a[2]) + t * dyaw)))
    return out


def pose_margins(poses: Sequence[tuple[float, float, float]], walls: Any, res: float,
                 origin: tuple[float, float]) -> np.ndarray:
    """每个位姿:车身(基础余量那一层)四边一起往外扩多少米碰到墙(墙格按方格算;地图外当墙)。"""
    h, w = walls.shape
    reach = math.hypot(BASE_HALF_LEN, BASE_HALF_WID) + CAP_M + res
    span = int(math.ceil(reach / res))
    out = np.full(len(poses), CAP_M)
    ox, oy = origin
    for i, (x, y, yaw) in enumerate(poses):
        r0, k0 = int((y - oy) // res), int((x - ox) // res)
        if r0 < 0 or r0 >= h or k0 < 0 or k0 >= w:
            out[i] = -1.0                                  # 中心出了地图:当压进墙
            continue
        # 以中心为心截一块 (2·span+1)²;伸出地图的部分填墙
        win = np.ones((2 * span + 1, 2 * span + 1), dtype=bool)
        rs, re_ = max(0, r0 - span), min(h, r0 + span + 1)
        ks, ke = max(0, k0 - span), min(w, k0 + span + 1)
        win[rs - (r0 - span):re_ - (r0 - span), ks - (k0 - span):ke - (k0 - span)] = \
            walls[rs:re_, ks:ke]
        rr, kk = np.nonzero(win)
        if not len(rr):
            continue
        cx = ox + (kk + k0 - span + 0.5) * res - x
        cy = oy + (rr + r0 - span + 0.5) * res - y
        c, s = math.cos(yaw), math.sin(yaw)
        lx = np.abs(c * cx + s * cy)
        ly = np.abs(-s * cx + c * cy)
        need = np.maximum(lx - BASE_HALF_LEN, ly - BASE_HALF_WID) - res / 2
        out[i] = min(CAP_M, float(need.min()))
    return out


def check_route(poses: Sequence[Sequence[float]], walls: Any, res: float,
                origin: tuple[float, float], *, need: float = ROUTE_MARGIN_MIN,
                want: float = ROUTE_MARGIN) -> RouteCheck:
    """查一条路线;``poses`` = ``plan_result.poses``(地图系)。"""
    dense = densify(poses)
    if not dense:
        return unchecked("no_route", "没拿到有效路线(空路线),没法查")
    if len(poses) == 1:
        return RouteCheck(True, CAP_M, dense[0], "at_goal")   # 已在终点、不用动
    along = np.concatenate([[0.0], np.cumsum([math.dist(a[:2], b[:2])
                                              for a, b in zip(dense, dense[1:], strict=False)])])
    keep = along >= min(SKIP_START_M, along[-1])
    keep[-1] = True                                        # 终点总要查
    idx = np.flatnonzero(keep)
    m = pose_margins([dense[i] for i in idx], walls, res, origin)
    j = int(np.argmin(m))
    worst, at = float(m[j]), dense[int(idx[j])]
    if worst >= need:
        return RouteCheck(True, worst, at, tight=worst < want)
    # 终点本身就放不下,而且连着终点的那段窄处是从终点附近(一个车身长 + GOAL_ZONE_M 以内)才开始的
    # → 墙在终点边上,报终点;整条都窄(窄通道里的终点)照旧报路线
    run = len(m) - 1
    while run > 0 and m[run - 1] < need:
        run -= 1
    if m[-1] < need and along[-1] - along[int(idx[run])] <= GOAL_ZONE_M + 2 * BASE_HALF_LEN:
        j = len(idx) - 1
        worst, at = float(m[j]), dense[int(idx[j])]
    near_goal = along[-1] - along[int(idx[j])] <= GOAL_ZONE_M
    gx, gy = dense[-1][0], dense[-1][1]
    if near_goal:
        why = (f"目标点 ({gx:.2f}, {gy:.2f}) 离墙太近:机器人站在那儿只剩 "
               f"{max(worst, 0.0):.2f} m 余量(要求每边 ≥ {need:.2f} m),把航点往空处挪一点")
        return RouteCheck(False, worst, at, "goal_too_close_to_wall", why, status="refused")
    why = (f"路线在 ({at[0]:.2f}, {at[1]:.2f}) 处离墙只剩 {max(worst, 0.0):.2f} m"
           f"(要求每边 ≥ {need:.2f} m,直通道约需 {2 * (BASE_HALF_WID + need):.2f} m 净宽),"
           "无法安全通过")
    return RouteCheck(False, worst, at, "route_too_narrow", why, status="refused")
