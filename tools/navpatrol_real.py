"""整趟巡逻仿真的「真实巡逻」场景(用户 11-17):尽量覆盖现实里巡逻会遇到的环境,按现实里常见的尺寸
随机出布局,看整趟走完率。跟 ``nav-d-1116`` 那套(故意挑难的窄弯、窄门)分开。

十类环境,每类按种子随机出一份 ``<场景>/s<种子>/case.json``(格式同 Gazebo 用例,
``tools/navbench_patrol.py`` 直接跑):

- ``r_mall_loop``      商场环形走廊 3–4.5 m,柱子、花池,新摆的摊位(地图上没有),
  来回走的人、横穿的人
- ``r_mall_atrium``    商场中庭大厅,柱阵、摊位,一群乱走的人
- ``r_factory``        工厂货架区,通道 1.8–2.6 m、两头主通道 3.5 m;
  叉车(会刹车)、工人、通道里临时放的托盘
- ``r_warehouse``      仓库主通道 3 m 边上几条死胡同巷道 1.3–1.8 m,巡检点在巷子尽头
- ``r_office``         办公楼:中间走廊 1.6–2.2 m、两边房间,双开门 1.2–1.8 m;
  站着聊天的人(过一会儿走开)
- ``r_parking``        地下停车场:车道 5.5–6.5 m,停着的车(有的走了、有的新停进来)、柱子、
  开着的车(会刹车)、行人
- ``r_estate``         庄园 / 小区室外:房子、车道、小路 1.8–2.5 m、大门 1.6–2.5 m、
  草坪花池(禁行区)、路沿、来车
- ``r_hospital``       医院 U 形长走廊 2.2–2.8 m,靠墙停的推车(地图上没有)、推着走的病床、护士
- ``r_lobby``          大堂:前台、柱子、一大群人
- ``r_detour``         两条平行走廊,直走那条中间被堆的东西堵死(地图上没有):得绕另一条

所有点都能到(``expect = arrive``);尺寸都是现实里给巡逻机器人走的那种,不挑极限。

用法:``python tools/navpatrol_real.py --out runs/navpatrol-real --seeds 10``
"""

from __future__ import annotations

import argparse
import json
import math
import random
from pathlib import Path
from typing import Any

SIM = {"exec_noise": True, "loc_noise_m": 0.045, "loc_noise_deg": 1.2, "obstacle_delay_ms": 150}
WALL = 0.2
#: 点离障碍(墙、柱子、地图上没有的东西)至少这么远(米,车身外接圆 0.6 + 余量)
GOAL_CLEAR_M = 0.75


# ------------------------------------------------------------------ 小工具

def R(x0: float, y0: float, x1: float, y1: float, **kw: Any) -> dict[str, Any]:
    """左下、右上两角 → case 里的长方形(中心 + 边长)。"""
    return {"x": (x0 + x1) / 2, "y": (y0 + y1) / 2, "sx": abs(x1 - x0), "sy": abs(y1 - y0), **kw}


def frame(w: float, h: float) -> list[dict[str, Any]]:
    """场地四周的墙(场地 [-w/2, w/2] × [-h/2, h/2])。"""
    a, b = w / 2, h / 2
    return [R(-a, -b, a, -b + WALL), R(-a, b - WALL, a, b), R(-a, -b, -a + WALL, b),
            R(a - WALL, -b, a, b)]


def person(name: str, path: list, speed: float, *, mode: str = "pingpong",
           start: dict | None = None) -> dict[str, Any]:
    return {"name": name, "kind": "person", "sx": 0.45, "sy": 0.45, "h": 1.7, "speed": speed,
            "mode": mode, "path": [list(p) for p in path], "start": start or {"at_s": 0.0},
            "yields": True, "vanish": mode == "once"}


def vehicle(name: str, path: list, speed: float, *, along_x: bool, size=(4.5, 1.9),
            mode: str = "pingpong", start: dict | None = None) -> dict[str, Any]:
    ln, wd = size
    return {"name": name, "kind": "vehicle", "sx": ln if along_x else wd,
            "sy": wd if along_x else ln, "h": 1.5, "speed": speed, "mode": mode,
            "path": [list(p) for p in path], "start": start or {"at_s": 0.0}}


def _clear(x: float, y: float, rects: list[dict[str, Any]]) -> float:
    best = math.inf
    for b in rects:
        dx = max(abs(x - b["x"]) - b["sx"] / 2, 0.0)
        dy = max(abs(y - b["y"]) - b["sy"] / 2, 0.0)
        best = min(best, math.hypot(dx, dy))
    return best


def _route(pts: list[tuple[float, float]], back_yaw: float | None = None) -> list[list[float]]:
    """点序列 → 目标(朝向 = 去下一个点的方向;最后一个点朝 ``back_yaw`` 或沿用上一段)。"""
    out = []
    for i, (x, y) in enumerate(pts):
        if i + 1 < len(pts):
            nx, ny = pts[i + 1]
            yaw = math.atan2(ny - y, nx - x)
        else:
            px, py = pts[i - 1]
            yaw = back_yaw if back_yaw is not None else math.atan2(y - py, x - px)
        out.append([round(x, 3), round(y, 3), round(yaw, 4)])
    return out


def _case(name: str, seed: int, size: tuple[float, float], mapped: list, unmapped: list,
          start: tuple[float, float, float], goals: list[tuple[float, float]], *,
          actors: list | None = None, zones: list | None = None, curbs: list | None = None,
          sim: dict | None = None) -> dict[str, Any]:
    w, h = size
    allr = mapped + unmapped
    for gx, gy in goals:
        c = _clear(gx, gy, allr)
        if c < GOAL_CLEAR_M:
            raise ValueError(f"{name}/{seed}:点 ({gx:.2f}, {gy:.2f}) 离障碍只有 {c:.2f} m")
    if _clear(start[0], start[1], allr) < GOAL_CLEAR_M:
        raise ValueError(f"{name}/{seed}:起点离障碍太近")
    return {"scenario": name, "family": name, "width_m": None, "seed": seed,
            "start": [round(v, 4) for v in start],
            "goals": _route(list(goals) + [start[:2]], back_yaw=start[2]),
            "obstacles": mapped, "collision_obstacles": mapped + unmapped,
            "dynamic": bool(actors), "actors": actors or [], "zones": zones or [],
            "curbs": curbs or [], "expect": "arrive", "map_size_m": [w, h],
            "map_bounds": [-w / 2, w / 2, -h / 2, h / 2], "site_map": None,
            "odom_origin": "world", "timeout_s": 300, "safety_min_clearance_m": 0.08,
            "sim": {**SIM, **(sim or {})}}


# ------------------------------------------------------------------ 十类环境

def mall_loop(rng: random.Random, seed: int) -> dict[str, Any]:
    W, H = 40.0, 28.0
    cw = rng.uniform(3.0, 4.5)                       # 走廊宽
    ax, ay = W / 2 - WALL, H / 2 - WALL              # 外墙内边
    ix0, ix1, iy0, iy1 = -ax + cw, ax - cw, -ay + cw, ay - cw   # 中间那块(中庭栏杆 / 店铺)
    mapped = frame(W, H) + [R(ix0, iy0, ix1, iy1)]
    # 柱子:靠中间那块的边上,每 8 m 一根,伸进走廊 0.5 m
    for x in range(-12, 13, 8):
        mapped.append(R(x - 0.3, iy1, x + 0.3, iy1 + 0.5))
        mapped.append(R(x - 0.3, iy0 - 0.5, x + 0.3, iy0))
    # 宽走廊中间的花池
    if cw >= 3.8:
        mapped.append(R(-0.6, -ay + cw / 2 - 0.6, 0.6, -ay + cw / 2 + 0.6))
    unmapped = []
    if rng.random() < 0.6:                           # 新摆的摊位,靠外墙
        x = rng.uniform(-10, 10)
        unmapped.append(R(x - 0.8, ay - 1.0, x + 0.8, ay, unmapped=True))
    my0, my1 = -ay + cw / 2, ay - cw / 2              # 上下走廊中线
    mx0, mx1 = -ax + cw / 2, ax - cw / 2              # 左右走廊中线
    goals = [(mx0, 0.0), (mx0, my1), (0.0, my1 + (0.5 if not unmapped else -0.3)), (mx1, my1),
             (mx1, 0.0), (mx1, my0), (rng.uniform(-6, 6), my0), (mx0, my0)]
    goals = [(x, y) for x, y in goals]
    actors = []
    for i in range(rng.randint(4, 6)):                # 顺着走廊来回走的人
        side = rng.choice(["top", "bottom", "left", "right"])
        off = rng.uniform(-cw / 2 + 0.5, cw / 2 - 0.5)
        if side in ("top", "bottom"):
            y = (my1 if side == "top" else my0) + off
            path = [(rng.uniform(-14, -4), y), (rng.uniform(4, 14), y)]
        else:
            x = (mx0 if side == "left" else mx1) + off
            path = [(x, rng.uniform(-8, -2)), (x, rng.uniform(2, 8))]
        actors.append(person(f"walk{i}", path, rng.uniform(0.8, 1.4)))
    for i in range(2):                                # 横穿走廊(从店里出来)
        x = rng.uniform(-10, 10)
        actors.append(person(f"cross{i}", [(x, ay - 0.4), (x, iy1 + 0.4)], rng.uniform(0.9, 1.3),
                             mode="once", start={"robot_within": [x, my1, 4.0]}))
    start = (mx0, my0 + 2.0, math.pi / 2)
    return _case("r_mall_loop", seed, (W, H), mapped, unmapped, start, goals[1:] + [goals[0]],
                 actors=actors)


def mall_atrium(rng: random.Random, seed: int) -> dict[str, Any]:
    W, H = 26.0, 18.0
    mapped = frame(W, H)
    pillars = []
    for x in (-7.5, -2.5, 2.5, 7.5):
        for y in (-4.0, 4.0):
            p = R(x - 0.4, y - 0.4, x + 0.4, y + 0.4)
            pillars.append(p)
    mapped += pillars
    unmapped = []
    for _ in range(rng.randint(1, 3)):               # 摊位
        for _try in range(30):
            x, y = rng.uniform(-10, 10), rng.uniform(-6, 6)
            b = R(x - 0.75, y - 0.5, x + 0.75, y + 0.5, unmapped=True)
            if _clear(x, y, mapped + unmapped) > 2.0:
                unmapped.append(b)
                break
    pts = [(-10.0, -6.5), (10.0, -6.5), (10.0, 6.5), (0.0, 0.0), (-10.0, 6.5)]
    goals = []
    for x, y in pts:
        for _try in range(30):
            gx, gy = x + rng.uniform(-1.0, 1.0), y + rng.uniform(-0.8, 0.8)
            if _clear(gx, gy, mapped + unmapped) >= GOAL_CLEAR_M + 0.3:
                goals.append((gx, gy))
                break
    actors = []
    for i in range(rng.randint(6, 9)):
        path = [(rng.uniform(-11, 11), rng.uniform(-7, 7)) for _ in range(3)]
        actors.append(person(f"crowd{i}", path, rng.uniform(0.7, 1.3), mode="loop"))
    start = (-11.0, 0.0, 0.0)
    return _case("r_mall_atrium", seed, (W, H), mapped, unmapped, start, goals, actors=actors)


def factory(rng: random.Random, seed: int) -> dict[str, Any]:
    W, H = 38.0, 26.0
    aw = rng.uniform(1.8, 2.6)                       # 货架通道宽
    rd = 2.0                                         # 双面货架深
    mapped = frame(W, H)
    x0, x1 = -9.0, 9.0                               # 货架区(两头是 3.5 m+ 的主通道)
    n = 5
    ys = []                                          # 每条通道中线
    y = -(n * aw + (n + 1) * rd) / 2
    for i in range(n + 1):
        mapped.append(R(x0, y, x1, y + rd))          # 一排货架
        y += rd
        if i < n:
            ys.append(y + aw / 2)
            y += aw
    unmapped = []
    if rng.random() < 0.5:                           # 通道里临时放的托盘(靠一边,留够宽)
        k = rng.randrange(n)
        px = rng.uniform(-5, 5)
        unmapped.append(R(px - 0.6, ys[k] - aw / 2, px + 0.6, ys[k] - aw / 2 + 0.6,
                          unmapped=True))
    lx, rx = x0 - 3.0, x1 + 3.0                      # 两头主通道中线
    goals = []
    for i, yy in enumerate(ys[::2]):                 # 隔一条通道穿一次(蛇形)
        if i % 2 == 0:
            goals += [(lx, yy), (0.0, yy + (0.25 if unmapped else 0.0)), (rx, yy)]
        else:
            goals += [(rx, yy), (0.0, yy), (lx, yy)]
    actors = [vehicle("forklift", [(lx, -10.0), (lx, 10.0)], rng.uniform(1.5, 2.2),
                      along_x=False, size=(2.6, 1.2)),
              vehicle("forklift2", [(rx, 10.0), (rx, -10.0)], rng.uniform(1.2, 2.0),
                      along_x=False, size=(2.6, 1.2))]
    for i in range(rng.randint(2, 3)):
        yy = rng.choice(ys)
        actors.append(person(f"worker{i}", [(rng.uniform(-8, -2), yy), (rng.uniform(2, 8), yy)],
                             rng.uniform(0.8, 1.2)))
    start = (lx - 2.0, 0.0, 0.0)
    return _case("r_factory", seed, (W, H), mapped, unmapped, start, goals, actors=actors)


def warehouse(rng: random.Random, seed: int) -> dict[str, Any]:
    W, H = 30.0, 20.0
    mapped = frame(W, H)
    mc = 3.0                                         # 主通道 y ∈ [-1.5, 1.5]
    goals = []
    xs = [-10.0, -4.0, 2.0, 8.0]
    for i, cx in enumerate(xs):
        aw = rng.uniform(1.3, 1.8)
        ln = rng.uniform(5.0, 7.5)
        up = i % 2 == 0
        # 巷子两边的货架、尽头的墙
        y0, y1 = (mc / 2, mc / 2 + ln) if up else (-mc / 2 - ln, -mc / 2)
        mapped.append(R(cx - aw / 2 - 1.2, y0, cx - aw / 2, y1))
        mapped.append(R(cx + aw / 2, y0, cx + aw / 2 + 1.2, y1))
        end = (R(cx - aw / 2, y1, cx + aw / 2, y1 + 0.2) if up
               else R(cx - aw / 2, y0 - 0.2, cx + aw / 2, y0))
        mapped.append(end)
        gy = (y1 - 0.9) if up else (y0 + 0.9)
        if i < 3:
            goals.append((cx, 0.0))
            goals.append((cx, gy))                   # 巡检点在巷子尽头
    # 主通道两边的长货架(巷子口之间)
    edges = [-14.8] + sum([[x - 2.3, x + 2.3] for x in xs], []) + [14.8]
    for a, b in zip(edges[::2], edges[1::2], strict=True):
        if b - a > 0.3:
            mapped.append(R(a, mc / 2 + 4.0, b, mc / 2 + 5.0))
    actors = [person("worker", [(-12.0, 0.6), (12.0, 0.6)], rng.uniform(0.8, 1.2))]
    start = (-13.0, 0.0, 0.0)
    return _case("r_warehouse", seed, (W, H), mapped, [], start, goals, actors=actors)


def office(rng: random.Random, seed: int) -> dict[str, Any]:
    W, H = 36.0, 18.0
    cw = rng.uniform(1.6, 2.2)
    mapped = frame(W, H)
    rooms = 4
    rw = (W - 2 * WALL) / rooms
    goals, stand = [], []
    for side in (1, -1):
        wy = side * cw / 2                           # 走廊墙
        for k in range(rooms):
            rx0 = -W / 2 + WALL + k * rw
            rx1 = rx0 + rw
            door = rng.uniform(1.2, 1.8)
            dx = rng.uniform(rx0 + 0.6 + door / 2, rx1 - 0.6 - door / 2)
            y0, y1 = (wy, wy + WALL) if side > 0 else (wy - WALL, wy)
            mapped.append(R(rx0, y0, dx - door / 2, y1))
            mapped.append(R(dx + door / 2, y0, rx1, y1))
            if k < rooms - 1:                        # 房间之间的隔墙
                ya, yb = (wy, H / 2) if side > 0 else (-H / 2, wy)
                mapped.append(R(rx1 - WALL / 2, ya, rx1 + WALL / 2, yb))
            cy = side * (cw / 2 + (H / 2 - cw / 2) / 2)
            # 房间里一张大桌子(地图上有)
            mapped.append(R((rx0 + rx1) / 2 - 1.2, cy + side * 1.0 - 0.5,
                            (rx0 + rx1) / 2 + 1.2, cy + side * 1.0 + 0.5))
            if (side > 0 and k in (0, 2)) or (side < 0 and k == 1):
                goals += [(dx, 0.0), (dx, cy - side * 1.2), (dx, 0.0)]
            stand.append(dx)
    goals.append((W / 2 - 1.5, 0.0))
    goals.sort(key=lambda p: p[0])
    # 去重相邻的走廊点
    g2 = []
    for p in goals:
        if not g2 or math.dist(p, g2[-1]) > 0.5:
            g2.append(p)
    actors = []
    for i in range(2):
        y = rng.uniform(-cw / 2 + 0.4, cw / 2 - 0.4)
        actors.append(person(f"walk{i}", [(-15.0, y), (15.0, y)], rng.uniform(0.9, 1.3)))
    x = rng.uniform(-8, 8)                           # 站在走廊里聊天,过一会儿走开
    actors.append(person("chat", [(x, rng.uniform(-0.3, 0.3), rng.uniform(15, 40)),
                                  (x + 6.0, cw / 2 - 0.3)], 0.8, mode="once"))
    start = (-W / 2 + 1.5, 0.0, 0.0)
    return _case("r_office", seed, (W, H), mapped, [], start, g2, actors=actors)


def parking(rng: random.Random, seed: int) -> dict[str, Any]:
    W, H = 46.0, 30.0
    lw = rng.uniform(5.5, 6.5)                       # 车道宽
    mapped = frame(W, H)
    unmapped: list = []
    gone: list = []
    # 三排车位(上、中、下),车道在两排之间;左右两头是连接车道
    rows = [(-H / 2 + WALL, -H / 2 + WALL + 5.0), (-2.5, 2.5), (H / 2 - WALL - 5.0, H / 2 - WALL)]
    for ry0, ry1 in rows:
        x = -W / 2 + WALL + lw + 0.5
        while x + 2.5 < W / 2 - WALL - lw - 0.5:
            if rng.random() < 0.15:                  # 一根柱子
                mapped.append(R(x + 0.85, (ry0 + ry1) / 2 - 0.4, x + 1.65, (ry0 + ry1) / 2 + 0.4))
            else:
                doubles = [(ry0 + 0.2, (ry0 + ry1) / 2 - 0.1), ((ry0 + ry1) / 2 + 0.1, ry1 - 0.2)]
                if ry1 - ry0 < 5.5 and rows.index((ry0, ry1)) != 1:
                    doubles = [(ry0 + 0.2, ry1 - 0.3)] if ry0 < 0 else [(ry0 + 0.3, ry1 - 0.2)]
                for cy0, cy1 in doubles:
                    car = R(x + 0.3, cy0, x + 2.2, cy1)
                    r = rng.random()
                    if r < 0.15:
                        gone.append(car)             # 建图时有、现在开走了
                        mapped.append(car)
                    elif r < 0.75:
                        mapped.append(car)
                    elif r < 0.9:
                        unmapped.append({**car, "unmapped": True})   # 新停进来的
            x += 2.5
    phys_mapped = [b for b in mapped if b not in gone]
    l1 = -H / 2 + WALL + 5.0 + lw / 2                # 下车道中线
    l2 = H / 2 - WALL - 5.0 - lw / 2                 # 上车道中线
    ex0 = -W / 2 + WALL + lw / 2                     # 左右连接车道中线
    ex1 = W / 2 - WALL - lw / 2
    goals = [(ex0, l2), (0.0, l2), (ex1, l2), (ex1, l1), (0.0, l1), (ex0, l1)]
    actors = [vehicle("car1", [(-15.0, l1 + 1.0), (15.0, l1 + 1.0)], rng.uniform(2.0, 3.0),
                      along_x=True),
              vehicle("car2", [(15.0, l2 - 1.0), (-15.0, l2 - 1.0)], rng.uniform(2.0, 3.0),
                      along_x=True, start={"at_s": rng.uniform(5, 25)}),
              person("walker", [(rng.uniform(-15, -5), l1 - 1.5), (rng.uniform(5, 15), l1 - 1.5)],
                     rng.uniform(0.9, 1.3))]
    start = (ex0, l1 + 3.0, math.pi / 2)
    case = _case("r_parking", seed, (W, H), mapped, unmapped, start, goals, actors=actors)
    case["collision_obstacles"] = phys_mapped + unmapped
    return case


def estate(rng: random.Random, seed: int) -> dict[str, Any]:
    W, H = 44.0, 32.0
    rw = rng.uniform(4.0, 6.0)                       # 车道
    pw = rng.uniform(1.8, 2.5)                       # 小路
    gw = rng.uniform(1.6, 2.5)                       # 大门
    mapped = frame(W, H)
    # 围墙:左边一道,中间开大门
    fx = -W / 2 + 4.0
    mapped += [R(fx, -H / 2, fx + 0.3, -gw / 2), R(fx, gw / 2, fx + 0.3, H / 2)]
    # 车道:横着 y ∈ [-rw/2, rw/2],从大门进来;两边一排房子
    houses = []
    for hx in (-8.0, 4.0, 16.0):
        for side in (1, -1):
            y0 = side * (rw / 2 + 3.0)
            hb = R(hx - 4.0, y0, hx + 4.0, y0 + side * 6.0)
            houses.append(hb)
    mapped += houses
    zones = []
    for hx in (-2.0, 10.0):                          # 房子之间的花池 / 草坪(禁行区)
        for side in (1, -1):
            y0 = side * (rw / 2 + 1.0)
            y1 = side * (rw / 2 + 2.5)
            zones.append({"id": f"lawn{hx}{side}", "kind": "nogo",
                          "polygon": [[hx - 1.5, min(y0, y1)], [hx + 1.5, min(y0, y1)],
                                      [hx + 1.5, max(y0, y1)], [hx - 1.5, max(y0, y1)]]})
    # 后面的小路:上面一排房子后面,宽 pw(外侧一道围墙)
    by = rw / 2 + 3.0 + 6.0 + pw / 2                 # 小路中线
    mapped.append(R(-12.0, by + pw / 2, 21.0, by + pw / 2 + 0.3))
    # 路沿:车道到小路之间的人行道边(斜着上)
    curbs = [[[-12.5, rw / 2 + 0.6], [-12.5 + 6.0, rw / 2 + 0.6]]]
    goals = [(fx + 2.0, 0.0), (-2.0, 0.0), (10.0, 0.0), (19.0, 0.0), (19.0, by),
             (4.0 + rng.uniform(-2, 2), by), (-11.0, by), (-11.0, 0.0)]
    actors = [vehicle("car", [(-14.0, -rw / 4), (19.0, -rw / 4)], rng.uniform(2.0, 3.5),
                      along_x=True, start={"at_s": rng.uniform(0, 20)}),
              person("resident", [(-6.0, rw / 2 - 0.5), (14.0, rw / 2 - 0.5)],
                     rng.uniform(0.8, 1.2)),
              person("jogger", [(18.0, by), (-10.0, by)], rng.uniform(2.0, 2.8), mode="once",
                     start={"robot_within": [19.0, 0.0, 3.0]})]
    start = (fx - 2.0, 0.0, 0.0)
    return _case("r_estate", seed, (W, H), mapped, [], start, goals, actors=actors,
                 zones=zones, curbs=curbs)


def hospital(rng: random.Random, seed: int) -> dict[str, Any]:
    W, H = 34.0, 24.0
    cw = rng.uniform(2.2, 2.8)
    mapped = frame(W, H)
    # U 形走廊:左、上、右三段,中间是病房区(一大块)
    ax, ay = W / 2 - WALL, H / 2 - WALL
    mapped.append(R(-ax + cw, -ay, ax - cw, ay - cw))
    unmapped = []
    for _ in range(rng.randint(2, 4)):               # 靠墙停的推车
        x = rng.uniform(-12, 12)
        unmapped.append(R(x - 0.5, ay - 0.6, x + 0.5, ay, unmapped=True))
    my = ay - cw / 2
    lx, rx = -ax + cw / 2, ax - cw / 2
    goals = [(lx, -8.0), (lx, my), (-5.0, my), (5.0, my), (rx, my), (rx, -8.0)]
    actors = [person("bed", [(-12.0, my - 0.2), (12.0, my - 0.2)], 0.7),
              person("nurse1", [(lx, -9.0), (lx, my - 1.0)], rng.uniform(1.0, 1.4)),
              person("nurse2", [(rx + 0.3, my - 1.0), (rx + 0.3, -9.0)], rng.uniform(1.0, 1.4))]
    actors[0].update({"sx": 2.1, "sy": 1.0})        # 推着走的病床
    start = (lx, -10.0, math.pi / 2)
    return _case("r_hospital", seed, (W, H), mapped, unmapped, start, goals, actors=actors)


def lobby(rng: random.Random, seed: int) -> dict[str, Any]:
    W, H = 24.0, 16.0
    mapped = frame(W, H) + [R(-2.0, 4.5, 2.0, 5.5)]  # 前台
    for x in (-6.0, 6.0):
        for y in (-3.0, 3.0):
            mapped.append(R(x - 0.35, y - 0.35, x + 0.35, y + 0.35))
    goals = [(-8.0, -5.5), (8.0, -5.5), (8.0, 5.5), (0.0, 3.2), (-8.0, 5.5)]
    actors = []
    for i in range(rng.randint(8, 12)):
        path = [(rng.uniform(-10, 10), rng.uniform(-6.5, 6.5)) for _ in range(3)]
        actors.append(person(f"crowd{i}", path, rng.uniform(0.7, 1.4), mode="loop"))
    start = (-10.0, 0.0, 0.0)
    return _case("r_lobby", seed, (W, H), mapped, [], start, goals, actors=actors)


def detour(rng: random.Random, seed: int) -> dict[str, Any]:
    W, H = 34.0, 16.0
    cw = rng.uniform(1.8, 2.4)
    mapped = frame(W, H)
    # 两条平行走廊 y = ±3,两头连通;中间一大块隔开
    mapped.append(R(-12.0, -3.0 + cw / 2, 12.0, 3.0 - cw / 2))
    mapped.append(R(-12.0, 3.0 + cw / 2, 12.0, H / 2))
    mapped.append(R(-12.0, -H / 2, 12.0, -3.0 - cw / 2))
    x = rng.uniform(-4, 4)                           # 下面那条中间被堆的东西堵死
    unmapped = [R(x - 0.8, -3.0 - cw / 2, x + 0.8, -3.0 + cw / 2, unmapped=True)]
    goals = [(14.0, -3.0), (14.0, 3.0), (0.0, 3.0)]
    actors = [person("walker", [(-11.0, 3.0 + rng.uniform(-0.4, 0.4)), (11.0, 3.0)],
                     rng.uniform(0.9, 1.3))]
    start = (-14.0, -3.0, 0.0)
    return _case("r_detour", seed, (W, H), mapped, unmapped, start, goals, actors=actors)


FAMILIES = [mall_loop, mall_atrium, factory, warehouse, office, parking, estate, hospital,
            lobby, detour]


def make(dst: Path, seeds: int) -> int:
    n = 0
    for fam in FAMILIES:
        for seed in range(seeds):
            rng = random.Random(f"{fam.__name__}/{seed}")
            for _try in range(100):                      # 种子多了偶尔 20 次不够(仓库 11)
                try:
                    case = fam(rng, seed)
                    break
                except ValueError:
                    continue
            else:
                raise RuntimeError(f"{fam.__name__}/{seed} 出不来合格的布局")
            d = dst / case["scenario"] / f"s{seed:03d}"
            d.mkdir(parents=True, exist_ok=True)
            (d / "case.json").write_text(json.dumps(case, ensure_ascii=False, indent=1),
                                         encoding="utf-8")
            n += 1
    return n


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--seeds", type=int, default=10)
    a = p.parse_args()
    print(make(a.out, a.seeds), "个用例")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
