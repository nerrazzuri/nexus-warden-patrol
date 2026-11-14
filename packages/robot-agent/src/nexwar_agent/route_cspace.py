"""路线检查的局部搜索(导航 V1 第 2 节;外审 11-14、用户定:不横移、输出要执行的路)。纯 numpy。

为什么要它:Smac 规划的路只保证车身不碰墙(1.2 m 宽的 L 形走廊在拐角正中原地转,只剩 0 cm),
每边 0.10 m 的底线常常不够(仿真 11-14:判定器说过得去的 63 趟被拒,余量中位 0.043 m);其实边走
边转、往外侧让一让就过得去。

做法(:func:`search_path`):
- 截窗:这一段路线所有位姿的外框,四边再放一个车身半对角 + :data:`PAD_M`;窗外当墙。
- 朝向分 :data:`YAW_BINS` 档。每档按那个朝向的车身矩形(基础余量那一层 + 每边 ``need`` +
  :data:`EXTRA_M`)跟墙做闵可夫斯基和(FFT 卷积)→ 朝这个方向时中心能去的格子。
- 只有三种动作(跟正式控制器一样不能横移):**沿车头前进**一步(每档取一个整数格位移,方向跟
  这一档的朝向差不超过半档;一步走过去中间每处车身都要放得下),**后退**一步(代价
  :data:`REVERSE_COST` 倍),**原地转**一档(转过去扫过的面积都要空着)。
- 按代价从小到大一层层往外推(桶队列),到了出口就停,再顺着代价倒推出路。
- 入口 / 出口:那个位姿所在的格子和朝向档(放不下就看紧挨着的一圈、差一档);终点那一段的
  出口站在终点 ±``goal_shift``、朝向 ±``goal_yaw_bins`` 档以内(跟 Nav2 的到点容差比取严)。

搜出来的路由调用方(:func:`nexwar_agent.route_check.check_route`)拼回路线、**整条再按原规矩逐个
位姿查一遍**,查过的才放行;这里的卷积只是找路,不替检查背书。

跟仿真台的几何判定器(``tools/nav_stability_bench_dev/geom_oracle.py``,整张图、连通块)是两套
实现;判定器用来量这里的误拒率。
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

import numpy as np

from nexwar_contract.footprint import BASE_HALF_LEN, BASE_HALF_WID

YAW_BINS = 72
SAMPLES_PER_TURN = 5
#: 截窗在这一段外框外再放多少(米,另加车身半对角)。
PAD_M = 0.4
#: 找路时车身每边再多留这么多(卷积按格子中心算,跟逐个位姿查的算法差半格;多留一点,拼好以后
#: 整条查的时候不至于差几毫米不过)。
EXTRA_M = 0.02
#: 一块窗最多这么多格(行 × 列),再大就不搜(机器人上每次出发都要查)。
MAX_CELLS = 40_000
#: 后退一步的代价是前进的几倍(能不倒车就不倒车:倒车看得少)。
REVERSE_COST = 3
#: 原地转一档(5°)的代价,按格算(车身外角转 5° 走 6 cm,约一格)。
TURN_COST = 1
#: 沿车头走一步最多几格。
MAX_STEP_CELLS = 16
#: 最多推这么多层(代价单位 = 一格),防止大窗里推不完。
MAX_COST = 4000


def _wrap(a: float) -> float:
    return (a + math.pi) % (2 * math.pi) - math.pi


def _kernel(lo: float, hi: float, half_len: float, half_wid: float, res: float,
            samples: int) -> np.ndarray:
    n = int(math.ceil(math.hypot(half_len, half_wid) / res)) + 1
    d = np.arange(-n, n + 1) * res
    dx, dy = np.meshgrid(d, d)
    k = np.zeros(dx.shape, dtype=bool)
    for t in np.linspace(lo, hi, samples):
        c, s = math.cos(t), math.sin(t)
        k |= (np.abs(dx * c + dy * s) <= half_len) & (np.abs(-dx * s + dy * c) <= half_wid)
    return k


def _blocked_by(walls: np.ndarray, kernels: list[np.ndarray]) -> np.ndarray:
    """每个核:墙 ⊕ 车身(中心不能去)。窗外当墙。"""
    h, w = walls.shape
    kh = max(k.shape[0] for k in kernels)
    pad = kh // 2 + 1
    big = np.ones((h + 2 * pad, w + 2 * pad), dtype=np.float32)
    big[pad:pad + h, pad:pad + w] = walls
    fs = (big.shape[0] + kh, big.shape[1] + kh)
    fb = np.fft.rfft2(big, fs)
    out = np.empty((len(kernels), h, w), dtype=bool)
    for i, k in enumerate(kernels):
        m = k.shape[0] // 2
        conv = np.fft.irfft2(fb * np.fft.rfft2(k.astype(np.float32), fs), fs)
        out[i] = conv[m + pad:m + pad + h, m + pad:m + pad + w] > 0.5
    return out


def _heading_step(theta: float, tol: float) -> tuple[int, int]:
    """朝 ``theta`` 走一步的整数格位移 (行, 列):方向差 ≤ ``tol`` 里最短的那个。"""
    for n in range(1, MAX_STEP_CELLS + 1):
        dc, dr = int(round(n * math.cos(theta))), int(round(n * math.sin(theta)))
        if (dc or dr) and abs(_wrap(math.atan2(dr, dc) - theta)) <= tol + 1e-9:
            g = math.gcd(abs(dr), abs(dc))
            return dr // g, dc // g
    raise ValueError(f"朝向 {math.degrees(theta):.1f}° 在 {MAX_STEP_CELLS} 格内找不到合适的位移")


def _shift(a: np.ndarray, dr: int, dc: int) -> np.ndarray:
    """``b[r, c] = a[r + dr, c + dc]``,出界当 False。"""
    h, w = a.shape
    b = np.zeros_like(a)
    r0, r1 = max(0, -dr), min(h, h - dr)
    c0, c1 = max(0, -dc), min(w, w - dc)
    if r0 < r1 and c0 < c1:
        b[r0:r1, c0:c1] = a[r0 + dr:r1 + dr, c0 + dc:c1 + dc]
    return b


def _bin(yaw: float) -> int:
    return int(round((yaw % (2 * math.pi)) / (2 * math.pi / YAW_BINS))) % YAW_BINS


def search_path(entry: Sequence[float], exit_: Sequence[float], walls: Any, res: float,
                origin: tuple[float, float], need: float, *,
                span: Sequence[Sequence[float]] = (), goal_end: bool = False,
                goal_shift: float = 0.10, goal_yaw_bins: int = 1
                ) -> list[tuple[float, float, float]] | None:
    """从 ``entry`` 走到 ``exit_``(都是 (x, y, 朝向))的一条不横移的路,每处车身(基础余量那一层
    + 每边 ``need``)都放得下;找不到回 None。``span`` = 原路线这一段的位姿(决定截窗)。
    返回的头尾就是 ``entry``、``exit_``(终点那一段:找到的那个落点)。"""
    hl = BASE_HALF_LEN + need + EXTRA_M
    hw = BASE_HALF_WID + need + EXTRA_M
    rad = math.hypot(hl, hw) + PAD_M
    pts = [entry, exit_, *span]
    xs, ys = [float(p[0]) for p in pts], [float(p[1]) for p in pts]
    ox, oy = origin
    H, W = walls.shape
    c0 = max(0, int(math.floor((min(xs) - rad - ox) / res)))
    c1 = min(W, int(math.ceil((max(xs) + rad - ox) / res)) + 1)
    r0 = max(0, int(math.floor((min(ys) - rad - oy) / res)))
    r1 = min(H, int(math.ceil((max(ys) + rad - oy) / res)) + 1)
    if r1 <= r0 or c1 <= c0 or (r1 - r0) * (c1 - c0) > MAX_CELLS:
        return None
    win = np.asarray(walls[r0:r1, c0:c1], dtype=bool)
    h, w = win.shape
    nb, step = YAW_BINS, 2 * math.pi / YAW_BINS
    kernels = [_kernel(k * step, k * step, hl, hw, res, 1) for k in range(nb)]
    kernels += [_kernel(k * step, (k + 1) * step, hl, hw, res, SAMPLES_PER_TURN)
                for k in range(nb)]
    bl = _blocked_by(win, kernels)
    free, turn = ~bl[:nb], ~bl[nb:]
    turn &= free & np.roll(free, -1, axis=0)               # 第 k 档 → 第 k+1 档:两头都放得下
    # 每档一步:位移、代价、哪些格子能走这一步(中间每处都放得下)
    dr_k, dc_k, cost_k = np.zeros(nb, int), np.zeros(nb, int), np.zeros(nb, int)
    ok = np.zeros_like(free)
    for k in range(nb):
        dr, dc = _heading_step(k * step, step / 2)
        n = int(math.ceil(math.hypot(dr, dc)))
        o = free[k].copy()
        for i in range(1, n + 1):
            o &= _shift(free[k], int(round(dr * i / n)), int(round(dc * i / n)))
        ok[k] = o
        dr_k[k], dc_k[k], cost_k[k] = dr, dc, max(1, int(round(math.hypot(dr, dc))))

    def near(p: Sequence[float], radius: float, bins: int, *, one: bool) -> np.ndarray:
        """离位姿 ``radius`` 以内、朝向差 ``bins`` 档以内、放得下的节点;``one``:只要最近的那个
        (入口、中间段的出口:拼回原路线的那一下只差不到一格)。"""
        fr, fc = (float(p[1]) - oy) / res - r0 - 0.5, (float(p[0]) - ox) / res - c0 - 0.5
        n = int(math.ceil(radius / res)) + 1
        b0 = _bin(float(p[2]))
        out = []
        for db in range(-bins, bins + 1):
            k = (b0 + db) % nb
            for r in range(int(math.floor(fr)) - n, int(math.ceil(fr)) + n + 1):
                for c in range(int(math.floor(fc)) - n, int(math.ceil(fc)) + n + 1):
                    d = math.hypot(r - fr, c - fc) * res
                    if 0 <= r < h and 0 <= c < w and d <= radius + 1e-9 and free[k, r, c]:
                        out.append((d + abs(db) * res, (k * h + r) * w + c))
        out.sort()
        return np.asarray([i for _, i in out[:1 if one else None]], dtype=np.int64)

    # 入口、中间段出口:一格半径以内(格心到位姿最远 0.7 格)、差一档以内,取最近的
    seeds = near(entry, 1.5 * res, 1, one=True)
    targets = (near(exit_, goal_shift, goal_yaw_bins, one=False) if goal_end
               else near(exit_, 1.5 * res, 1, one=True))
    if not len(seeds) or not len(targets):
        return None
    n_all = nb * h * w
    inf = np.iinfo(np.int32).max
    dist = np.full(n_all, inf, dtype=np.int32)
    is_target = np.zeros(n_all, dtype=bool)
    is_target[targets] = True
    ok_f, turn_f = ok.ravel(), turn.ravel()
    buckets: dict[int, list[np.ndarray]] = {0: [seeds]}
    hit = -1
    t = 0
    while buckets and t <= MAX_COST:
        if t not in buckets:
            t += 1
            continue
        nodes = np.unique(np.concatenate(buckets.pop(t)))
        nodes = nodes[dist[nodes] == inf]
        if len(nodes):
            dist[nodes] = t
            done = nodes[is_target[nodes]]
            if len(done):
                hit = int(done[0])
                break
            k, rc = np.divmod(nodes, h * w)
            r, c = np.divmod(rc, w)
            # 前进:从 (k, r, c) 走到 (k, r+dr, c+dc)
            m = ok_f[nodes]
            _push(buckets, t, k[m], r[m] + dr_k[k[m]], c[m] + dc_k[k[m]], cost_k[k[m]], h, w)
            # 后退:从 (k, r, c) 退到 (k, r-dr, c-dc) —— 那一步在 (r-dr, c-dc) 上算
            rb, cb = r - dr_k[k], c - dc_k[k]
            inside = (rb >= 0) & (rb < h) & (cb >= 0) & (cb < w)
            kb, rb, cb = k[inside], rb[inside], cb[inside]
            m = ok_f[(kb * h + rb) * w + cb]
            _push(buckets, t, kb[m], rb[m], cb[m], REVERSE_COST * cost_k[kb[m]], h, w)
            # 原地转一档(两个方向)
            m = turn_f[nodes]
            _push(buckets, t, (k[m] + 1) % nb, r[m], c[m], np.full(m.sum(), TURN_COST), h, w)
            kp = (k - 1) % nb
            m = turn_f[(kp * h + r) * w + c]
            _push(buckets, t, kp[m], r[m], c[m], np.full(m.sum(), TURN_COST), h, w)
        t += 1
    if hit < 0:
        return None
    # 顺着代价倒推
    chain = [hit]
    cur = hit
    while dist[cur] > 0:
        k, rc = divmod(cur, h * w)
        r, c = divmod(rc, w)
        d = int(dist[cur])
        dr, dc, ck = int(dr_k[k]), int(dc_k[k]), int(cost_k[k])
        cands = []
        rp, cp = r - dr, c - dc                            # 前进过来的
        if 0 <= rp < h and 0 <= cp < w and ok[k, rp, cp]:
            cands.append(((k * h + rp) * w + cp, ck))
        rp, cp = r + dr, c + dc                            # 后退过来的(那一步在 (r, c) 上算)
        if 0 <= rp < h and 0 <= cp < w and ok[k, r, c]:
            cands.append(((k * h + rp) * w + cp, REVERSE_COST * ck))
        kp = (k - 1) % nb                                  # 从上一档转过来
        if turn[kp, r, c]:
            cands.append(((kp * h + r) * w + c, TURN_COST))
        kn = (k + 1) % nb                                  # 从下一档转回来
        if turn[k, r, c]:
            cands.append(((kn * h + r) * w + c, TURN_COST))
        prev = next((p for p, cost in cands if dist[p] == d - cost), None)
        if prev is None:                                   # 不该发生:代价对不上就当没找到
            return None
        chain.append(prev)
        cur = prev
    chain.reverse()
    out = [(float(entry[0]), float(entry[1]), float(entry[2]))]
    for nid in chain:
        k, rc = divmod(nid, h * w)
        r, c = divmod(rc, w)
        out.append((ox + (c0 + c + 0.5) * res, oy + (r0 + r + 0.5) * res, _wrap(k * step)))
    if not goal_end:
        out.append((float(exit_[0]), float(exit_[1]), float(exit_[2])))
    return out


def _push(buckets: dict[int, list[np.ndarray]], t: int, k: np.ndarray, r: np.ndarray,
          c: np.ndarray, cost: np.ndarray, h: int, w: int) -> None:
    if not len(k):
        return
    ids = (k * h + r) * w + c
    for cv in np.unique(cost):
        buckets.setdefault(t + int(cv), []).append(ids[cost == cv])
