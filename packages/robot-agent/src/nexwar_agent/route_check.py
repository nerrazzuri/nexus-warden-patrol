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

**余量不够的那一段先局部搜索**(外审 11-14、用户定:不横移、输出要执行的路):每段前后各往外
接 :data:`CONTEXT_M`,在周围按「沿车头前进 / 后退、原地转」找一条每处都留够底线的走法
(:func:`nexwar_agent.route_cspace.search_path`),拼回路线,**整条再按上面的规矩逐个位姿查一遍**;
过了才放行,``path`` 就是这条拼好的路(调用方让 Nav2 的控制器照它走,不再让 Smac 另规划)。
小窗里搜不到(仿真 11-15:过门转弯、终点贴墙要多退一点、绕远一点才转得过来)就从起点到终点整条
再搜一次,同样整条查过才放行。都不行照旧拒。
**搜的时候先要宽的**(仿真 11-16:只按底线搜,路贴着 0.10 走,机器人走偏几厘米就被守卫挡住、
走不完):先按每边 ``want``(0.20)搜,搜不到再按两者中间(0.15),最后才按底线;放行照旧只看底线。
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

from nexwar_agent.route_cspace import WHOLE_MAX_CELLS, search_path
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
#: 局部搜索:余量不够的那一段前后各往外接这么长(沿路线,米),入口、出口落在够宽的位姿上。
CONTEXT_M = 0.5


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
    #: 靠局部搜索放行时:要执行的整条路(地图系 (x, y, 朝向),≤ 5 cm 一个,已逐个查过);
    #: 原路线本身就够的是 None(照常交给 Nav2 规划)
    path: tuple[tuple[float, float, float], ...] | None = None


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
    found = None
    for level in _search_levels(need, want):
        found = _searched(dense, along, idx, m, walls, res, origin, need, level)
        if found is not None:
            break
    if found is not None:
        return found
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


def _checked(path: Sequence[tuple[float, float, float]], walls: Any, res: float,
             origin: tuple[float, float]) -> tuple[list[tuple[float, float, float]], np.ndarray,
                                                   np.ndarray]:
    """插值、跳过起步那一段,逐个位姿算余量 → (插值后的路, 查的那些下标, 余量)。"""
    dense = densify(path)
    along = np.concatenate([[0.0], np.cumsum([math.dist(a[:2], b[:2])
                                              for a, b in zip(dense, dense[1:], strict=False)])])
    keep = along >= min(SKIP_START_M, along[-1])
    keep[-1] = True
    idx = np.flatnonzero(keep)
    return dense, idx, pose_margins([dense[i] for i in idx], walls, res, origin)


def _search_levels(need: float, want: float) -> list[float]:
    """局部搜索依次按哪几档余量搜:``want``、两者中间、``need``(从宽到窄,不低于底线)。"""
    out: list[float] = []
    for v in (want, (want + need) / 2, need):
        if v >= need and all(abs(v - o) > 1e-9 for o in out):
            out.append(v)
    return out


def _searched(dense: list[tuple[float, float, float]], along: np.ndarray, idx: np.ndarray,
              m: np.ndarray, walls: Any, res: float, origin: tuple[float, float],
              need: float, level: float | None = None) -> RouteCheck | None:
    """余量不够的每一段做局部搜索、拼回去、整条再查(见模块说明);不行回 None。
    ``level`` = 搜的时候按每边多少余量找(默认 ``need``);放行只看整条不低于 ``need``。"""
    level = need if level is None else level
    bad = m < need
    segs: list[list[int]] = []                             # [入口, 出口](``idx`` 里的位置)
    k = 0
    while k < len(idx):
        if not bad[k]:
            k += 1
            continue
        e = k
        while e + 1 < len(idx) and bad[e + 1]:
            e += 1
        lo = k - 1
        while lo > 0 and along[idx[k]] - along[idx[lo - 1]] <= CONTEXT_M and not bad[lo - 1]:
            lo -= 1
        hi = e + 1
        while (hi < len(idx) - 1 and along[idx[hi + 1]] - along[idx[e]] <= CONTEXT_M
               and not bad[hi + 1]):
            hi += 1
        if segs and lo <= segs[-1][1]:
            segs[-1][1] = hi                               # 跟上一段接上了:并成一段
        else:
            segs.append([lo, hi])
        k = e + 1
    tries = (lambda: _spliced(segs, dense, idx, walls, res, origin, level),
             # 小窗搜不到(或拼好的整条查不过):整条路线一次搜(起点就是机器人此刻站的地方)
             lambda: search_path(dense[0], dense[-1], walls, res, origin, level, span=dense,
                                 goal_end=True, max_cells=WHOLE_MAX_CELLS))
    for attempt in tries:
        out = attempt()
        if out is None:
            continue
        path, cidx, cm = _checked(out, walls, res, origin)
        if float(cm.min()) >= need and _start_ok(out, dense, walls, res, origin, need):
            j = int(np.argmin(cm))
            return RouteCheck(True, float(cm[j]), path[int(cidx[j])], tight=True,
                              path=tuple(path))
    return None


def _start_ok(out: list[tuple[float, float, float]], dense: list[tuple[float, float, float]],
              walls: Any, res: float, origin: tuple[float, float], need: float) -> bool:
    """起步豁免只给原路线自己:搜出来插在起步那段里的(入口原地转之类)逐个细查,余量不低于
    min(``need``, 站着时)—— 贴墙起步可以,转的时候不许比站着更贴(外审 11-17 第 2 轮)。"""
    orig = set(dense)
    along = 0.0
    floor = min(need, float(pose_margins([out[0]], walls, res, origin)[0]))
    new: list[tuple[float, float, float]] = []
    for a, b in zip(out, out[1:], strict=False):
        if along >= SKIP_START_M:
            break
        along += math.dist(a[:2], b[:2])
        if a not in orig or b not in orig:
            new += densify([a, b])
    return not new or float(pose_margins(new, walls, res, origin).min()) >= floor - 1e-9


def _spliced(segs: list[list[int]], dense: list[tuple[float, float, float]], idx: np.ndarray,
             walls: Any, res: float, origin: tuple[float, float],
             need: float) -> list[tuple[float, float, float]] | None:
    """每段在小窗里搜、拼回原路线;有一段搜不到回 None。"""
    out: list[tuple[float, float, float]] = []
    pos = 0                                                # ``dense`` 里拼到哪儿了
    for lo, hi in segs:
        goal_end = hi >= len(idx)
        a = int(idx[lo]) if lo >= 0 else 0
        b = len(dense) - 1 if goal_end else int(idx[hi])
        sp = search_path(dense[a], dense[b], walls, res, origin, need, span=dense[a:b + 1],
                         goal_end=goal_end)
        if sp is None:
            return None
        out += dense[pos:a] + sp
        pos = b + 1
    return out + dense[pos:]
