"""几何判定器(导航 V1 第 2、6 节):在真实地图上用有效车身做 (x, y, 朝向) 全搜索,判断几何上
能不能从起点走到终点。

跟 Route Validator(``nexwar_agent.route_check``)是**两套独立实现**:Validator 只查 Smac 给出的那
一条路线;这里搜所有位姿,用来量 Validator 的误拒率和正确拒绝率。

做法:
- 朝向分 ``yaw_bins`` 档。每档把车身矩形(半长 ``half_len``、半宽 ``half_wid``)在档内几个角度
  取并集,跟地图障碍做闵可夫斯基和 → 这一档里机器人中心不能去的格子。档内转动扫过的面积都算进去,
  所以宁严勿松(档宽 5° 时残差 < 1 cm)。
- 同一档里可以前后走、横移(D1 能横移):8 邻接连通。
- 相邻两档、同一个格子都能站:可以原地转过去。
- 起点所在的连通块里有终点 → 可行。

只用 numpy(CI 环境没有 scipy)。栅格约定跟 ``nexwar_contract.planning.costmap`` 一样:
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
from nexwar_contract.footprint import BASE_HALF_LEN, BASE_HALF_WID, ROUTE_MARGIN  # noqa: E402

#: 默认按 Route Validator 的口径:有效车身 1.03 × 0.58 + 每边 0.20 m = 1.43 × 0.98。
HALF_LEN = BASE_HALF_LEN + ROUTE_MARGIN
HALF_WID = BASE_HALF_WID + ROUTE_MARGIN
YAW_BINS = 72
#: 每档内取几个角度合成车身(档两端 + 中间)。
SAMPLES_PER_BIN = 5


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
        # 格中心落在矩形里,或者离矩形不到半格(格子本身有大小):宁严勿松
        k |= (np.abs(along) <= half_len + res / 2) & (np.abs(across) <= half_wid + res / 2)
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


def _label(free: np.ndarray) -> tuple[_UF, list[list[tuple[np.ndarray, np.ndarray, int]]]]:
    """按段做并查集:层内 8 邻接,相邻层(含 最后一档↔第一档)同一格都能站就连上。
    返回并查集和每层每行的段 (起列, 止列, 第一个段号)。"""
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
            s, e, f = layers[k][r]
            s2, e2, f2 = layers[k2][r]
            for i, j in _overlap_pairs(s, e, s2, e2, 0):
                uf.union(f + i, f2 + j)
    return uf, layers


def _node(layers, k: int, r: int, c: int) -> int | None:
    s, e, f = layers[k][r]
    i = int(np.searchsorted(s, c, side="right")) - 1
    if i >= 0 and c <= e[i]:
        return f + i
    return None


def _bin(yaw: float, nb: int) -> int:
    step = 2 * math.pi / nb
    return int(round((yaw % (2 * math.pi)) / step)) % nb


def judge(blocked: np.ndarray, res: float, origin: tuple[float, float],
          start: tuple[float, float, float | None], goal: tuple[float, float, float | None], *,
          half_len: float = HALF_LEN, half_wid: float = HALF_WID,
          yaw_bins: int = YAW_BINS) -> Verdict:
    """``start``、``goal`` = (x, y, 朝向或 None)。起点 None = 哪个朝向站得下都行(机器人原地能转到
    的那几档算同一块);终点 None = 到了就行,朝向不限。"""
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
    kernels = [_kernel(k * step - step / 2, k * step + step / 2, half_len, half_wid, res,
                       SAMPLES_PER_BIN) for k in range(yaw_bins)]
    free = ~_cspace(blocked, kernels)
    uf, layers = _label(free)
    sks = range(yaw_bins) if start[2] is None else [_bin(start[2], yaw_bins)]
    sns = [n for n in (_node(layers, k, *sc) for k in sks) if n is not None]
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
