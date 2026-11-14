"""几何判定器(导航 V1 第 2、6 节):在真实地图上用有效车身做 (x, y, 朝向) 全搜索,判断几何上
能不能从起点走到终点。

跟 Route Validator(``nexwar_agent.route_check``)是**两套独立实现**:Validator 只查 Smac 给出的那
一条路线;这里搜所有位姿,用来量 Validator 的误拒率和正确拒绝率。

做法:
- 朝向分 ``yaw_bins`` 档。每档按那个角度的车身矩形(半长 ``half_len``、半宽 ``half_wid``)跟地图
  障碍做闵可夫斯基和 → 朝这个方向时机器人中心不能去的格子。
- 从一档原地转到下一档:这一格上两档之间转过去扫过的面积(取 5 个角度的并集)都要空着。
- 起点放不下时在 0.5 m 内找放得下的(同 Validator 出发头 0.5 m 不查);终点一定要放得下。
- 同一档里可以前后走、横移(D1 能横移):8 邻接连通。
- 起点所在的连通块里有终点 → 可行。

**两种运动能力**(``motion``,外审 11-14、用户定:本轮禁止横移):

- ``omni``(上面那套):同一档里 8 邻接走,含横移。只做能力探索,**不进**当前版本的误拒率、
  必须通过率结论。
- ``diff``:跟正式控制器一样不能横移(Nav2 MPPI ``DiffDrive``、``vy_max: 0``,Smac 用 diff 运动
  基元,HAL 下发 ``vy`` 恒为 0)。同一档里只能**沿车头方向**前进、后退:每档取一个整数格位移
  (方向跟这一档的朝向差不超过半档),一步走过去中间每处车身都要放得下;档之间照旧原地转。
  到点按 Nav2 的到点容差的一半算:位置 ±:data:`GOAL_XY_TOL_M`、朝向 ±:data:`GOAL_YAW_TOL_BINS` 档。
  连通块用 scipy(仿真台的系统 Python 有);没有 scipy 时退回纯 numpy(慢,只适合测试里的小图)。

omni 只用 numpy(CI 环境没有 scipy)。栅格约定跟 ``nexwar_contract.planning.costmap`` 一样:
``blocked[r, c]``,``x = origin_x + (c + 0.5) * res``,``y = origin_y + (r + 0.5) * res``。
地图外当障碍。
"""

from __future__ import annotations

import math
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

_SRC = Path(__file__).resolve().parents[2] / "packages" / "contract" / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
from nexwar_contract.footprint import (  # noqa: E402
    BASE_HALF_LEN,
    BASE_HALF_WID,
    ROUTE_MARGIN,
    ROUTE_MARGIN_MIN,
)

#: 默认按路线余量的目标:有效车身 1.03 × 0.58 + 每边 0.20 m = 1.43 × 0.98。
HALF_LEN = BASE_HALF_LEN + ROUTE_MARGIN
HALF_WID = BASE_HALF_WID + ROUTE_MARGIN
#: 底线:每边 0.10 m = 1.23 × 0.78(Route Validator 不到就拒绝)。
HALF_LEN_MIN = BASE_HALF_LEN + ROUTE_MARGIN_MIN
HALF_WID_MIN = BASE_HALF_WID + ROUTE_MARGIN_MIN
YAW_BINS = 72
#: 每档内取几个角度合成车身(档两端 + 中间)。
SAMPLES_PER_BIN = 5
#: 起点放不下有效车身时,在这么远以内找一个放得下的(同一档朝向)。跟 Route Validator 一样:
#: 出发后头 0.5 m 不查(机器人就站在那儿,贴墙也得先走出来)。
START_SLACK_M = 0.5
#: diff 模式到点容差:Nav2 ``xy_goal_tolerance`` 0.2 / ``yaw_goal_tolerance`` 0.15 rad 取严一点。
GOAL_XY_TOL_M = 0.10
GOAL_YAW_TOL_BINS = 1
#: diff 模式沿车头走一步最多几格(找跟朝向差不到半档的整数位移)。
MAX_STEP_CELLS = 16


@dataclass(frozen=True)
class Verdict:
    feasible: bool
    #: ``ok`` / ``start_blocked``(起点放不下车身)/ ``goal_blocked``(终点哪个朝向都放不下,
    #: 或要求的朝向放不下)/ ``no_path``(两边都放得下,但连不起来)/ ``outside``(点在图外)
    reason: str


def _kernel(theta_lo: float, theta_hi: float, half_len: float, half_wid: float,
            res: float, samples: int) -> np.ndarray:
    """档 [theta_lo, theta_hi] 内车身矩形的并集,以格为单位,中心在核正中。"""
    rad = math.hypot(half_len, half_wid)
    n = int(math.ceil(rad / res)) + 1
    d = np.arange(-n, n + 1) * res
    dx, dy = np.meshgrid(d, d)                  # dx 沿列(x),dy 沿行(y)
    k = np.zeros(dx.shape, dtype=bool)
    for t in np.linspace(theta_lo, theta_hi, samples):
        ct, st = math.cos(t), math.sin(t)
        along = dx * ct + dy * st
        across = -dx * st + dy * ct
        # 障碍按格中心算、机器人位置也只落在格中心,两头各差不到半格、大致抵消。原来车身再外扩
        # 半格,1.0 m 直走廊(居中每边 0.01 m 富余)就判过不去,跟 0.98 m 的口径对不上。
        k |= (np.abs(along) <= half_len) & (np.abs(across) <= half_wid)
    return k


def _cspace(blocked: np.ndarray, kernels: list[np.ndarray]) -> np.ndarray:
    """每档的「中心不能去」:障碍 ⊕ 车身。FFT 卷积,地图外当障碍。返回 (档, 行, 列)。"""
    h, w = blocked.shape
    pad = max(k.shape[0] for k in kernels) // 2 + 1
    big = np.ones((h + 2 * pad, w + 2 * pad), dtype=np.float32)
    big[pad:pad + h, pad:pad + w] = blocked
    H, W = big.shape
    kh = max(k.shape[0] for k in kernels)
    fs = (H + kh, W + kh)
    fb = np.fft.rfft2(big, fs)
    out = np.empty((len(kernels), h, w), dtype=bool)
    for i, k in enumerate(kernels):
        m = k.shape[0] // 2
        conv = np.fft.irfft2(fb * np.fft.rfft2(k.astype(np.float32), fs), fs)
        conv = conv[m:m + H, m:m + W]           # 跟 big 对齐(核对称,方向无所谓)
        out[i] = conv[pad:pad + h, pad:pad + w] > 0.5
    return out


class _UF:
    def __init__(self) -> None:
        self.p: list[int] = []

    def add(self) -> int:
        self.p.append(len(self.p))
        return len(self.p) - 1

    def find(self, a: int) -> int:
        p = self.p
        while p[a] != a:
            p[a] = p[p[a]]
            a = p[a]
        return a

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[ra] = rb


def _runs(row: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """一行里连续可走的段:(起列, 止列),都含。"""
    x = np.concatenate(([0], row.view(np.int8), [0]))
    d = np.diff(x)
    return np.flatnonzero(d == 1), np.flatnonzero(d == -1) - 1


def _overlap_pairs(a0, a1, b0, b1, slack: int):
    """两组段(各自按列排好)里重叠的对;``slack`` = 1 时斜着挨着也算(8 邻接)。"""
    i = j = 0
    while i < len(a0) and j < len(b0):
        if a0[i] <= b1[j] + slack and b0[j] <= a1[i] + slack:
            yield i, j
        if a1[i] < b1[j]:
            i += 1
        else:
            j += 1


def _label(free: np.ndarray, sweep: np.ndarray
           ) -> tuple[_UF, list[list[tuple[np.ndarray, np.ndarray, int]]]]:
    """按段做并查集:层内 8 邻接;从第 k 档转到第 k+1 档(含 最后一档↔第一档)要这一格上转过去
    扫过的面积都空着(``sweep[k]``)。返回并查集和每层每行的段 (起列, 止列, 第一个段号)。"""
    uf = _UF()
    nb, h, _ = free.shape
    layers: list[list[tuple[np.ndarray, np.ndarray, int]]] = []
    for k in range(nb):
        rows = []
        for r in range(h):
            s, e = _runs(free[k, r])
            first = len(uf.p)
            for _ in range(len(s)):
                uf.add()
            rows.append((s, e, first))
            if r > 0:
                ps, pe, pf = rows[r - 1]
                for i, j in _overlap_pairs(s, e, ps, pe, 1):
                    uf.union(first + i, pf + j)
        layers.append(rows)
    for k in range(nb):
        k2 = (k + 1) % nb
        if k2 == k:
            break
        for r in range(h):
            ss, _ = _runs(sweep[k, r])
            for c in ss:                      # 扫过的都空 ⊂ 两档都能站:段起点落在两档各自的段里
                a, b = _node(layers, k, r, int(c)), _node(layers, k2, r, int(c))
                if a is not None and b is not None:
                    uf.union(a, b)
    return uf, layers


def _node(layers, k: int, r: int, c: int) -> int | None:
    s, e, f = layers[k][r]
    i = int(np.searchsorted(s, c, side="right")) - 1
    if i >= 0 and c <= e[i]:
        return f + i
    return None


def _near_start(free: np.ndarray, layers, ks, rc: tuple[int, int], n: int) -> list[int]:
    """起点 ``n`` 格以内、这几档朝向里放得下车身的最近那些格所在的块。"""
    r0, c0 = rc
    _, h, w = free.shape
    ra, rb, ca, cb = max(0, r0 - n), min(h, r0 + n + 1), max(0, c0 - n), min(w, c0 + n + 1)
    out = []
    for k in ks:
        rr, cc = np.nonzero(free[k, ra:rb, ca:cb])
        if len(rr) == 0:
            continue
        d2 = (rr + ra - r0) ** 2 + (cc + ca - c0) ** 2
        j = int(d2.argmin())
        if d2[j] <= n * n:
            node = _node(layers, k, int(rr[j] + ra), int(cc[j] + ca))
            if node is not None:
                out.append(node)
    return out


def _bin(yaw: float, nb: int) -> int:
    step = 2 * math.pi / nb
    return int(round((yaw % (2 * math.pi)) / step)) % nb


def _heading_step(theta: float, tol: float) -> tuple[int, int]:
    """朝 ``theta`` 走一步的整数格位移 (行, 列):方向差 ≤ ``tol`` 里最短的那个。"""
    for n in range(1, MAX_STEP_CELLS + 1):
        dc, dr = int(round(n * math.cos(theta))), int(round(n * math.sin(theta)))
        if (dc or dr) and abs(_wrap(math.atan2(dr, dc) - theta)) <= tol + 1e-9:
            g = math.gcd(abs(dr), abs(dc))
            return dr // g, dc // g
    raise ValueError(f"朝向 {math.degrees(theta):.1f}° 在 {MAX_STEP_CELLS} 格内找不到合适的位移")


def _wrap(a: float) -> float:
    return (a + math.pi) % (2 * math.pi) - math.pi


def _shift(a: np.ndarray, dr: int, dc: int) -> np.ndarray:
    """``b[r, c] = a[r + dr, c + dc]``,出界当 False。"""
    h, w = a.shape
    b = np.zeros_like(a)
    r0, r1 = max(0, -dr), min(h, h - dr)
    c0, c1 = max(0, -dc), min(w, w - dc)
    if r0 < r1 and c0 < c1:
        b[r0:r1, c0:c1] = a[r0 + dr:r1 + dr, c0 + dc:c1 + dc]
    return b


def _components(n: int, src: np.ndarray, dst: np.ndarray) -> np.ndarray:
    """无向图的连通块标号。"""
    try:
        from scipy.sparse import coo_matrix
        from scipy.sparse.csgraph import connected_components
    except ImportError:
        lab = np.arange(n)
        while True:
            m = np.minimum(lab[src], lab[dst])
            new = lab.copy()
            np.minimum.at(new, src, m)
            np.minimum.at(new, dst, m)
            new = new[new]
            if np.array_equal(new, lab):
                return lab
            lab = new
    g = coo_matrix((np.ones(len(src), dtype=bool), (src, dst)), shape=(n, n))
    return connected_components(g, directed=False)[1]


def _diff_labels(free: np.ndarray, sweep: np.ndarray) -> np.ndarray:
    """diff 模式:节点 (档, 行, 列),边 = 沿车头前进 / 后退一步 + 原地转一档。返回每个节点的块号
    (形状同 ``free``;放不下的节点也有号,用的时候先看 ``free``)。"""
    nb, h, w = free.shape
    step = 2 * math.pi / nb
    ids = np.arange(nb * h * w).reshape(nb, h, w)
    src, dst = [], []
    for k in range(nb):
        dr, dc = _heading_step(k * step, step / 2)
        m = int(math.ceil(math.hypot(dr, dc)))
        ok = free[k].copy()
        for i in range(1, m + 1):                       # 一步走过去,中间每处车身都放得下
            ok &= _shift(free[k], int(round(dr * i / m)), int(round(dc * i / m)))
        rr, cc = np.nonzero(ok)
        src.append(ids[k, rr, cc])
        dst.append(ids[k, rr + dr, cc + dc])
        k2 = (k + 1) % nb
        rot = sweep[k] & free[k] & free[k2]
        rr, cc = np.nonzero(rot)
        src.append(ids[k, rr, cc])
        dst.append(ids[k2, rr, cc])
    return _components(nb * h * w, np.concatenate(src), np.concatenate(dst)).reshape(nb, h, w)


def _judge_diff(free: np.ndarray, sweep: np.ndarray, res: float, sc: tuple[int, int],
                gc: tuple[int, int], start_yaw: float | None, goal_yaw: float | None,
                goal_xy: tuple[float, float], origin: tuple[float, float]) -> Verdict:
    nb, h, w = free.shape
    lab = _diff_labels(free, sweep)
    sks = range(nb) if start_yaw is None else [_bin(start_yaw, nb)]
    starts = [lab[k, sc[0], sc[1]] for k in sks if free[k, sc[0], sc[1]]]
    if not starts:
        n = int(round(START_SLACK_M / res))
        r0, c0 = sc
        ra, rb, ca, cb = max(0, r0 - n), min(h, r0 + n + 1), max(0, c0 - n), min(w, c0 + n + 1)
        for k in sks:
            rr, cc = np.nonzero(free[k, ra:rb, ca:cb])
            if len(rr):
                d2 = (rr + ra - r0) ** 2 + (cc + ca - c0) ** 2
                j = int(d2.argmin())
                if d2[j] <= n * n:
                    starts.append(lab[k, rr[j] + ra, cc[j] + ca])
    if not starts:
        return Verdict(False, "start_blocked")
    rr, cc = np.mgrid[0:h, 0:w]
    gx = origin[0] + (cc + 0.5) * res
    gy = origin[1] + (rr + 0.5) * res
    near = (gx - goal_xy[0]) ** 2 + (gy - goal_xy[1]) ** 2 <= max(GOAL_XY_TOL_M, res) ** 2
    near[gc[0], gc[1]] = True
    if goal_yaw is None:
        gks = list(range(nb))
    else:
        b0 = _bin(goal_yaw, nb)
        gks = [(b0 + d) % nb for d in range(-GOAL_YAW_TOL_BINS, GOAL_YAW_TOL_BINS + 1)]
    goals = np.concatenate([lab[k][near & free[k]] for k in gks])
    if not len(goals):
        return Verdict(False, "goal_blocked")
    if np.isin(goals, np.asarray(starts)).any():
        return Verdict(True, "ok")
    return Verdict(False, "no_path")


def judge(blocked: np.ndarray, res: float, origin: tuple[float, float],
          start: tuple[float, float, float | None], goal: tuple[float, float, float | None], *,
          half_len: float = HALF_LEN, half_wid: float = HALF_WID,
          yaw_bins: int = YAW_BINS, motion: str = "omni") -> Verdict:
    """``start``、``goal`` = (x, y, 朝向或 None)。起点 None = 哪个朝向站得下都行(机器人原地能转到
    的那几档算同一块);终点 None = 到了就行,朝向不限。``motion``:``omni``(含横移)/ ``diff``
    (不能横移,见模块说明)。"""
    blocked = np.asarray(blocked, dtype=bool)
    h, w = blocked.shape

    def cell(x: float, y: float) -> tuple[int, int] | None:
        c = int(math.floor((x - origin[0]) / res))
        r = int(math.floor((y - origin[1]) / res))
        return (r, c) if 0 <= r < h and 0 <= c < w else None

    sc, gc = cell(start[0], start[1]), cell(goal[0], goal[1])
    if sc is None or gc is None:
        return Verdict(False, "outside")
    step = 2 * math.pi / yaw_bins
    exact = [_kernel(k * step, k * step, half_len, half_wid, res, 1) for k in range(yaw_bins)]
    turns = [_kernel(k * step, (k + 1) * step, half_len, half_wid, res, SAMPLES_PER_BIN)
             for k in range(yaw_bins)]
    cs = _cspace(blocked, exact + turns)
    free, sweep = ~cs[:yaw_bins], ~cs[yaw_bins:]
    if motion == "diff":
        return _judge_diff(free, sweep, res, sc, gc, start[2], goal[2], (goal[0], goal[1]), origin)
    if motion != "omni":
        raise ValueError(f"motion 只能是 omni / diff:{motion!r}")
    uf, layers = _label(free, sweep)
    sks = range(yaw_bins) if start[2] is None else [_bin(start[2], yaw_bins)]
    sns = [n for n in (_node(layers, k, *sc) for k in sks) if n is not None]
    if not sns:
        sns = _near_start(free, layers, sks, sc, int(round(START_SLACK_M / res)))
    if not sns:
        return Verdict(False, "start_blocked")
    gks = range(yaw_bins) if goal[2] is None else [_bin(goal[2], yaw_bins)]
    gns = [n for n in (_node(layers, k, *gc) for k in gks) if n is not None]
    if not gns:
        return Verdict(False, "goal_blocked")
    roots = {uf.find(n) for n in sns}
    if any(uf.find(n) in roots for n in gns):
        return Verdict(True, "ok")
    return Verdict(False, "no_path")
