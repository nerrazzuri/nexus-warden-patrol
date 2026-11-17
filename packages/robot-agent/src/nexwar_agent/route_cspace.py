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
- 每档的朝向就是那一步的位移方向(外审 11-17 I2:原来按 5° 整档,走一步最多偏半档,
  16 格的一步横着偏 1.7 cm)。
- 入口 / 出口:从那个位姿到附近一个格子节点,只用「原地转 → 沿车头直走(前或后)→ 原地转」接上
  (外审 11-17 I2:原来直接连到格子中心,带几厘米横移),接上去的代价算进总代价;
  终点那一段的出口站在终点 ±``goal_shift``、朝向 ±``goal_yaw_bins`` 档以内(跟 Nav2 的到点容差比
  取严)。出来的路整条验一遍不横移(:func:`strafe_m`),不过就当没找到。

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
#: 小窗搜不到时整条路线一次搜(仿真 11-15:过门转弯、终点贴墙要多退一点才转得过来),窗最多这么多格
#: (整张 18 × 18 m 的仿真图 13 万格,搜一次约 0.3 s)。
WHOLE_MAX_CELLS = 200_000
#: 后退一步的代价是前进的几倍(能不倒车就不倒车:倒车看得少)。
REVERSE_COST = 3
#: 原地转一档(5°)的代价,按格算(车身外角转 5° 走 6 cm,约一格)。
TURN_COST = 1
#: 沿车头走一步最多几格。
MAX_STEP_CELLS = 16
#: 最多推这么多层(代价单位 = 一格),防止大窗里推不完。
MAX_COST = 4000
#: 入口:原路线头上这么远以内找一个在格子里放得下的位姿接上(先沿原路线走过去)。
ANCHOR_M = 0.5
#: 出口:原路线最后 ANCHOR_M 以内每隔这么远挑一个位姿,从它正后方的楔形里接回去。
ANCHOR_STEP_M = 0.15
LINK_MAX_M = 0.6
LINK_WEDGE_DEG = 6.0
LINK_SLACK_M = 0.03
#: 没墙时的余量(只用来比大小)。
CAP = 9.0
#: 验收:相邻两个位姿横着挪的(相对两头朝向的平均)不许超过这么多(米)。
STRAFE_TOL_M = 1e-3


def strafe_m(a: Sequence[float], b: Sequence[float]) -> float:
    """``a`` → ``b`` 横着挪了多少(米):位移在两头朝向平均方向的垂直分量。原地转、沿车头直走、
    沿圆弧边走边转都是 0。"""
    dx, dy = float(b[0]) - float(a[0]), float(b[1]) - float(a[1])
    m = float(a[2]) + _wrap(float(b[2]) - float(a[2])) / 2
    return abs(-math.sin(m) * dx + math.cos(m) * dy)


def _turn(x: float, y: float, a: float, b: float) -> list[tuple[float, float, float]]:
    """站在 (x, y) 从朝向 ``a`` 原地转到 ``b``:每 5° 一个位姿(不含 ``a``,含 ``b``)。"""
    d = _wrap(b - a)
    n = max(1, int(math.ceil(abs(d) / math.radians(5.0) - 1e-9)))
    return [(x, y, _wrap(a + d * i / n)) for i in range(1, n + 1)] if abs(d) > 1e-9 else []


def _link(a: Sequence[float], b: Sequence[float]) -> tuple[list[tuple[float, float, float]],
                                                           float, float, bool]:
    """``a`` → ``b`` 只用原地转 + 沿车头直走:回(中间和 ``b`` 的位姿, 两下转里大的那个(弧度),
    走多远, 倒没倒车)。"""
    ax, ay, ayaw = float(a[0]), float(a[1]), float(a[2])
    bx, by, byaw = float(b[0]), float(b[1]), float(b[2])
    d = math.hypot(bx - ax, by - ay)
    if d < 1e-6:
        out = _turn(ax, ay, ayaw, byaw) or [(bx, by, byaw)]
        out[-1] = (bx, by, byaw)
        return out, abs(_wrap(byaw - ayaw)), 0.0, False
    bear = math.atan2(by - ay, bx - ax)
    back = math.cos(bear - ayaw) < 0
    tau = _wrap(bear + math.pi) if back else bear
    out = [*_turn(ax, ay, ayaw, tau), (bx, by, tau), *_turn(bx, by, tau, byaw)]
    out[-1] = (bx, by, byaw)                                # 末一下转完正好是 b 的朝向
    return out, max(abs(_wrap(tau - ayaw)), abs(_wrap(byaw - tau))), d, back


def _wrap(a: float) -> float:
    return (a + math.pi) % (2 * math.pi) - math.pi


def _kernel(lo: float, hi: float, half_len: float, half_wid: float, res: float,
            samples: int, sx: float = 0.0, sy: float = 0.0) -> np.ndarray:
    """车身(朝向 ``lo`` → ``hi`` 扫过)盖住哪些格子;车身中心在格心再挪 (``sx``, ``sy``)。
    (卷积是 ``Σ 墙[p − q]·核[q]``、车身中心对称,所以核按 ``q + 挪的量`` 算。)"""
    n = int(math.ceil((math.hypot(half_len, half_wid) + math.hypot(sx, sy)) / res)) + 1
    d = np.arange(-n, n + 1) * res
    dx, dy = np.meshgrid(d, d)
    dx, dy = dx + sx, dy + sy
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
                goal_shift: float = 0.10, goal_yaw_bins: int = 1,
                max_cells: int = MAX_CELLS) -> list[tuple[float, float, float]] | None:
    """从 ``entry`` 走到 ``exit_``(都是 (x, y, 朝向))的一条不横移的路,每处车身(基础余量那一层
    + 每边 ``need``)都放得下;找不到回 None。``span`` = 原路线这一段的位姿(决定截窗;头尾就是
    ``entry``、``exit_`` 时,接上格子之前 / 之后可以先沿它走一小段)。
    返回的头尾就是 ``entry``、``exit_``(终点那一段:找到的那个落点)。"""
    from nexwar_agent.route_check import pose_margins  # 函数里导入:route_check 导入本模块

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
    if r1 <= r0 or c1 <= c0 or (r1 - r0) * (c1 - c0) > max_cells:
        return None
    win = np.asarray(walls[r0:r1, c0:c1], dtype=bool)
    h, w = win.shape
    nb, step = YAW_BINS, 2 * math.pi / YAW_BINS
    # 每档一步的整数格位移;这一档的朝向就取这一步的方向(沿车头走,一点不横)
    dr_k, dc_k, cost_k = np.zeros(nb, int), np.zeros(nb, int), np.zeros(nb, int)
    for k in range(nb):
        dr_k[k], dc_k[k] = _heading_step(k * step, step / 2)
        cost_k[k] = max(1, int(round(math.hypot(dr_k[k], dc_k[k]))))
    th = [math.atan2(int(dr_k[k]), int(dc_k[k])) for k in range(nb)]
    def masks(sx: float, sy: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """格子整张挪 (``sx``, ``sy``) 时:每档哪些格子放得下、能转到下一档、能走一步。"""
        kernels = [_kernel(th[k], th[k], hl, hw, res, 1, sx, sy) for k in range(nb)]
        kernels += [_kernel(th[k], th[k] + _wrap(th[(k + 1) % nb] - th[k]), hl, hw, res,
                            SAMPLES_PER_TURN, sx, sy) for k in range(nb)]
        bl = _blocked_by(win, kernels)
        free, turn = ~bl[:nb], ~bl[nb:]
        turn &= free & np.roll(free, -1, axis=0)           # 第 k 档 → 第 k+1 档:两头都放得下
        ok = np.zeros_like(free)                           # 哪些格子能走这一步(中间每处都放得下)
        for k in range(nb):
            dr, dc = int(dr_k[k]), int(dc_k[k])
            n = int(math.ceil(math.hypot(dr, dc)))
            o = free[k].copy()
            for i in range(1, n + 1):
                o &= _shift(free[k], int(round(dr * i / n)), int(round(dc * i / n)))
            ok[k] = o
        return free, turn, ok

    def margin(poses: list[tuple[float, float, float]]) -> float:
        return float(pose_margins(poses, walls, res, origin).min()) if poses else CAP

    lane = [tuple(map(float, q)) for q in span]
    if not lane or lane[0] != tuple(map(float, entry)) or lane[-1] != tuple(map(float, exit_)):
        lane = [tuple(map(float, entry)), tuple(map(float, exit_))]
    along = np.concatenate([[0.0], np.cumsum([math.dist(a[:2], b[:2])
                                              for a, b in zip(lane, lane[1:], strict=False)])])

    # 入口:格子整张挪到让原路线头上一个位姿正好站在节点上(卷积按挪过的算),原地转到某一档就
    # 接上;那个位姿在格子里放不下,就沿原路线往前每隔 ANCHOR_STEP_M 换一个(重算一遍)
    anchor, last = None, None
    for j in range(len(lane)):
        if along[j] > ANCHOR_M:
            break
        if last is not None and along[j] - along[last] < ANCHOR_STEP_M:
            continue
        last = j
        q = lane[j]
        ce, re = int(math.floor((q[0] - ox) / res)) - c0, int(math.floor((q[1] - oy) / res)) - r0
        if not (0 <= re < h and 0 <= ce < w):
            continue
        sx = q[0] - (ox + (c0 + ce + 0.5) * res)
        sy = q[1] - (oy + (r0 + re + 0.5) * res)
        free, turn, ok = masks(sx, sy)
        costs = _turn_seeds(q, th, free[:, re, ce], margin, need)
        if costs:
            anchor = (j, re, ce, costs)
            break
    if anchor is None:
        return None
    ja, re, ce, costs = anchor

    def node(i: int) -> tuple[float, float, float]:
        k, rc = divmod(int(i), h * w)
        r, c = divmod(rc, w)
        return (ox + (c0 + c + 0.5) * res + sx, oy + (r0 + r + 0.5) * res + sy, th[k])

    def cell(x: float, y: float) -> tuple[float, float]:
        return (y - oy - sy) / res - r0 - 0.5, (x - ox - sx) / res - c0 - 0.5

    seed_cost = {(k * h + re) * w + ce: cst for k, cst in costs.items()}
    tlink: dict[int, tuple[int, list[tuple[float, float, float]]]] = {}
    if goal_end:
        fr, fc = cell(float(exit_[0]), float(exit_[1]))
        n = int(math.ceil(goal_shift / res)) + 1
        b0, g_yaw = _bin(float(exit_[2])), float(exit_[2])
        tcost = {}
        for db in range(-goal_yaw_bins, goal_yaw_bins + 1):
            k = (b0 + db) % nb
            if abs(_wrap(th[k] - g_yaw)) > goal_yaw_bins * step + 1e-9:
                continue
            for r in range(int(math.floor(fr)) - n, int(math.ceil(fr)) + n + 1):
                for c in range(int(math.floor(fc)) - n, int(math.ceil(fc)) + n + 1):
                    if (0 <= r < h and 0 <= c < w and free[k, r, c]
                            and math.hypot(r - fr, c - fc) * res <= goal_shift + 1e-9):
                        tcost[(k * h + r) * w + c] = 0
    else:
        tcost = _exit_links(lane, along, th, free, step, res, cell, node, h, w, margin, need,
                            tlink)
    if not seed_cost or not tcost:
        return None
    n_all = nb * h * w
    inf = np.iinfo(np.int32).max
    dist = np.full(n_all, inf, dtype=np.int32)
    is_target = np.zeros(n_all, dtype=bool)
    is_target[list(tcost)] = True
    ok_f, turn_f = ok.ravel(), turn.ravel()
    buckets: dict[int, list[np.ndarray]] = {}
    for i, cst in seed_cost.items():
        buckets.setdefault(cst, []).append(np.asarray([i], dtype=np.int64))
    hit, best = -1, inf
    t = 0
    while buckets and t <= MAX_COST and t < best:
        if t not in buckets:
            t += 1
            continue
        nodes = np.unique(np.concatenate(buckets.pop(t)))
        nodes = nodes[dist[nodes] == inf]
        if len(nodes):
            dist[nodes] = t
            for i in nodes[is_target[nodes]]:                 # 加上接回去的代价,总的最小的
                if t + tcost[int(i)] < best:
                    best, hit = t + tcost[int(i)], int(i)
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
    while seed_cost.get(cur) != int(dist[cur]):
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
    head = lane[:ja + 1]
    mine = [head[-1], *_turn(head[-1][0], head[-1][1], head[-1][2], node(chain[0])[2])]
    mine[-1] = node(chain[0])
    mine += [node(i) for i in chain[1:]]
    tail: list[tuple[float, float, float]] = []
    if not goal_end:
        m_at, seg = tlink[hit]
        mine += seg
        tail = lane[m_at + 1:]
    worst = max((strafe_m(a, b) for a, b in zip(mine, mine[1:], strict=False)), default=0.0)
    if worst > STRAFE_TOL_M:
        return None                                        # 不该发生:验收不过就当没找到
    return head[:-1] + mine + tail


def _link_floor(need: float, here: float) -> float:
    """接缝上的位姿余量不低于多少:站着的余量够 ``need`` 就按 ``need``;不够(贴墙的出口、地图边上)
    许比站着时再少 :data:`LINK_SLACK_M`(整条复查照样按底线把关)。"""
    return need if here >= need else here - LINK_SLACK_M


def _turn_seeds(q: tuple[float, float, float], th: list[float], free_here: np.ndarray,
                margin: Any, need: float) -> dict[int, int]:
    """站在 ``q`` 原地转到哪几档接得上格子(那一档在这个格子里放得下;转的一路每半档一个位姿,
    余量不低于 :func:`_link_floor`)→ {档: 转了几档(代价)}。"""
    nb = len(th)
    step = 2 * math.pi / nb
    floor = _link_floor(need, margin([q]))
    out: dict[int, int] = {}
    for sign in (1, -1):
        reach = 0.0                                        # 这个方向转得到多远
        for n in range(1, nb + 1):
            a = n * step / 2
            if margin([(q[0], q[1], _wrap(q[2] + sign * a))]) < floor - 1e-9:
                break
            reach = a
        for k in range(nb):
            d = _wrap(th[k] - q[2]) * sign
            if not free_here[k] or d < -1e-9 or d > reach + 1e-9:
                continue
            if d > 1e-9 and margin([(q[0], q[1], th[k])]) < floor - 1e-9:
                continue
            cst = int(math.ceil(max(d, 0.0) / step - 1e-9))
            if k not in out or cst < out[k]:
                out[k] = cst
    return out


def _exit_links(lane: list[tuple[float, float, float]], along: np.ndarray, th: list[float],
                free: np.ndarray, step: float, res: float, cell: Any, node: Any, h: int, w: int,
                margin: Any, need: float,
                tlink: dict[int, tuple[int, list[tuple[float, float, float]]]]) -> dict[int, int]:
    """中间段的出口:原路线最后 :data:`ANCHOR_M` 里的几个位姿 ``R``,从它正后方楔形里
    (:data:`LINK_MAX_M` 以内、偏不到 :data:`LINK_WEDGE_DEG`)朝向差一档以内的节点,原地转一点、
    沿车头直走到 ``R``、再转一点接上;节点那头的转按格子查,直走和 ``R`` 那头的转按逐个位姿的余量
    查(不低于 :func:`_link_floor`)→ {节点: 接回去的代价};怎么接的写进 ``tlink``。"""
    nb = len(th)
    out: dict[int, int] = {}
    tan_w = math.tan(math.radians(LINK_WEDGE_DEG))
    picks, last = [], None
    for m in range(len(lane) - 1, -1, -1):
        if along[-1] - along[m] > ANCHOR_M:
            break
        if last is None or along[last] - along[m] >= ANCHOR_STEP_M:
            picks.append(m)
            last = m
    for m in picks:
        R = lane[m]
        floor = _link_floor(need, margin([R]))
        b0 = _bin(R[2])
        cx, cy = math.cos(R[2]), math.sin(R[2])
        fr, fc = cell(R[0], R[1])
        n = int(math.ceil(LINK_MAX_M / res)) + 1
        memo: dict[tuple[int, int], bool] = {}
        for r in range(int(math.floor(fr)) - n, int(math.ceil(fr)) + n + 1):
            for c in range(int(math.floor(fc)) - n, int(math.ceil(fc)) + n + 1):
                if not (0 <= r < h and 0 <= c < w):
                    continue
                x, y, _ = node(r * w + c)
                s = (R[0] - x) * cx + (R[1] - y) * cy          # 在 R 后面多远
                lat = -(R[0] - x) * cy + (R[1] - y) * cx
                if s <= 1e-6 or s > LINK_MAX_M or abs(lat) > s * tan_w:
                    continue
                bear = math.atan2(R[1] - y, R[0] - x)
                for db in (-1, 0, 1):
                    k = (b0 + db) % nb
                    if not free[k, r, c]:
                        continue
                    i = (k * h + r) * w + c
                    seg, _, d, _ = _link((x, y, th[k]), R)
                    # 节点那头的原地转:按格子查(每一档都放得下)
                    t1 = _wrap(bear - th[k])
                    kk = [round((th[k] + t1 * f) / step) % nb for f in (0.5, 1.0)]
                    if not all(free[q, r, c] for q in kk):
                        continue
                    if (r, c) not in memo:
                        far = [(x + (R[0] - x) * f / 4, y + (R[1] - y) * f / 4, bear)
                               for f in range(1, 5)]
                        far += _turn(R[0], R[1], bear, R[2])
                        memo[(r, c)] = margin(far) >= floor - 1e-9
                    if not memo[(r, c)]:
                        continue
                    cst = int(math.ceil(d / res + (abs(t1) + abs(_wrap(R[2] - bear))) / step
                                        - 1e-9))
                    if i not in out or cst < out[i]:
                        out[i] = cst
                        seg[-1] = R
                        tlink[i] = (m, seg)
    return out


def _push(buckets: dict[int, list[np.ndarray]], t: int, k: np.ndarray, r: np.ndarray,
          c: np.ndarray, cost: np.ndarray, h: int, w: int) -> None:
    if not len(k):
        return
    ids = (k * h + r) * w + c
    for cv in np.unique(cost):
        buckets.setdefault(t + int(cv), []).append(ids[cost == cv])
