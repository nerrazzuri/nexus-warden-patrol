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
#: 起点放不下有效车身时,在这么远以内找一个放得下的(同一档朝向)。跟 Route Validator 一样:
#: 出发后头 0.5 m 不查(机器人就站在那儿,贴墙也得先走出来)。
START_SLACK_M = 0.5


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
    exact = [_kernel(k * step, k * step, half_len, half_wid, res, 1) for k in range(yaw_bins)]
    turns = [_kernel(k * step, (k + 1) * step, half_len, half_wid, res, SAMPLES_PER_BIN)
             for k in range(yaw_bins)]
    cs = _cspace(blocked, exact + turns)
    free, sweep = ~cs[:yaw_bins], ~cs[yaw_bins:]
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
