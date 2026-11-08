#!/usr/bin/env python3
"""生成 P0 极限场景库 scenarios_p0.yaml(用户 11-07 的 20 个场景里定为 P0 的那些 + 广场窄缝)。

窄路类按宽度扫:0.80 / 0.85 / 0.90 / 0.95 / 1.00 / 1.10 / 1.20 m。
**标准**(用户 11-07 认可):每边余量 ≥ 0.2 m(宽 ≥ 0.98 m,机身宽 0.58)必须过;
放不下的(< 0.98 m)PASS = 不撞、停住(expect: blocked)。

通道用「挖」的写法:先把一块区域填实,再把通道(长方形)挖空,剩下的格子合并成墙。
宽度是精确的,所以窄路类的墙不加随机偏移(扰动只加在起点、朝向、目标、行人上)。

每一趟的仿真条件(按种子抽,写进 case.json 的 sim):执行误差、定位噪声 2–6 cm / 0.5–1.5°、
障碍数据延迟 0/100/200 ms;定位故障类场景另带故障。
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import yaml

from generate_case import _cells_to_boxes

HERE = Path(__file__).resolve().parent
WIDTHS = [0.80, 0.85, 0.90, 0.95, 1.00, 1.10, 1.20]
NEED = 0.98                     # 0.58 + 2 × 0.2
RES = 0.05
PI = math.pi

SIM = {"exec_noise": True, "loc_noise_m": [0.02, 0.06], "loc_noise_deg": [0.5, 1.5],
       "obstacle_delay_ms": {"choice": [0, 100, 200]}}
TIGHT_DEFAULTS = {"start_jitter_xy_m": 0.2, "start_jitter_yaw_deg": 15, "obstacle_jitter_xy_m": 0.0,
                  "goal_jitter_xy_m": 0.05, "goal_jitter_yaw_deg": 5, "actor_jitter_xy_m": 0.1}
OPEN_DEFAULTS = {**TIGHT_DEFAULTS, "obstacle_jitter_xy_m": 0.10}


def carve(region, channels):
    """region = (x0, x1, y0, y1) 填实;channels = [(x0, x1, y0, y1), ...] 挖空 → 墙(长方形列表)。"""
    x0, x1, y0, y1 = region
    nx, ny = int(round((x1 - x0) / RES)), int(round((y1 - y0) / RES))
    cx = x0 + (np.arange(nx) + 0.5) * RES
    cy = y0 + (np.arange(ny) + 0.5) * RES
    X, Y = np.meshgrid(cx, cy)                      # 行 = y(从下往上)
    solid = np.ones((ny, nx), dtype=bool)
    for a, b, c, d in channels:
        solid &= ~((X >= a) & (X <= b) & (Y >= c) & (Y <= d))
    boxes = _cells_to_boxes(solid, RES, (x0, y0))
    return [{k: round(v, 3) for k, v in bx.items()} for bx in boxes]


def tag(w):
    return f"{int(round(w * 100)):03d}"


def width_case(fid, w, start, goals_ok, goal_in, obstacles, extra=None, timeout=150):
    blocked = w < NEED
    sc = {"id": f"{fid}_w{tag(w)}", "family": fid, "width_m": w,
          "timeout_s": timeout if not blocked else 90,
          "min_pose_clearance_m": 0.05, "defaults": TIGHT_DEFAULTS, "sim": dict(SIM),
          "start": start, "goals": goals_ok if not blocked else [goal_in], "obstacles": obstacles}
    if blocked:
        sc["expect"] = "blocked"
    if extra:
        sc.update(extra)
    return sc


def main() -> int:
    out = []
    for w in WIDTHS:
        h = w / 2
        # 1 90° 窄直角弯:竖着一段(5 m)往下,拐 90° 横着一段(6 m)往西,两段都是 w 宽
        L = carve((-9.0, 9.0, -9.0, 9.0),
                  [(-1.0, 8.8, 2.0, 8.8), (2.0, 2.0 + w, -3.0, 2.0), (-4.0, 2.0 + w, -3.0, -3.0 + w),
                   (-8.8, -4.0, -8.8, 1.0)])
        out.append(width_case("p0_L90", w, [2.0 + h, 4.5, -PI / 2],
                              [[-6.0, -3.0 + h, PI], [2.0 + h, 4.5, PI / 2]], [-6.0, -3.0 + h, PI], L))
        # 2 S 型连续反向窄弯:往东 → 拐北 → 拐东
        S = carve((-9.0, 9.0, -9.0, 9.0),
                  [(-8.8, -6.0, -8.8, 8.8), (6.0, 8.8, -8.8, 8.8),
                   (-6.0, -1.0 + h, -2.0 - h, -2.0 + h), (-1.0 - h, -1.0 + h, -2.0 - h, 2.0 + h),
                   (-1.0 - h, 6.0, 2.0 - h, 2.0 + h)])
        out.append(width_case("p0_S", w, [-7.5, -2.0, 0.0], [[7.5, 2.0, 0.0], [-7.5, -2.0, PI]],
                              [7.5, 2.0, 0.0], S))
        # 3 死胡同:4 m 深、w 宽,点在里面朝里;回来要倒出来(宽不够掉头)
        D = carve((0.0, 5.0, -3.0, 3.0), [(0.0, 4.0, -h, h)])
        out.append(width_case("p0_deadend", w, [-5.0, 0.0, 0.0], [[3.2, 0.0, 0.0], [-5.0, 0.0, PI]],
                              [3.2, 0.0, 0.0], D))
        # 5 窄门 + 门后 1.1 m 就要 90° 转弯(门后是 1.1 m 宽、往北的走廊)
        C = 1.1
        Dr = carve((-0.15, 9.0, -9.0, 9.0),
                   [(-0.15, 0.15, -h, h), (0.15, 0.15 + C, -h, 5.0), (0.15, 8.8, 5.0, 8.8)])
        out.append(width_case("p0_door_turn", w, [-5.0, 0.0, 0.0],
                              [[0.15 + C / 2, 7.0, PI / 2], [-5.0, 0.0, PI]], [0.15 + C / 2, 7.0, PI / 2], Dr))
        # 6 长窄走廊(10 m),走到一半对面进来一个人,在中间站 12 s 再原路出去:机器人要停、等(或退),不撞
        Co = carve((-5.0, 5.0, -9.0, 9.0), [(-5.0, 5.0, -h, h)])
        person = {"name": "p1", "kind": "person", "sx": 0.45, "sy": 0.45, "h": 1.7, "speed": 1.0, "mode": "once",
                  "path": [[8.0, 0.0], [5.5, 0.0], [1.5, 0.0, 12.0], [5.5, 0.0], [8.0, 3.0]],
                  "start": {"robot_within": [-4.5, 0.0, 0.8]}}
        out.append(width_case("p0_corridor_oncoming", w, [-7.0, 0.0, 0.0], [[7.0, -3.0, -PI / 2]],
                              [7.0, -3.0, -PI / 2], Co, extra={"actors": [person]}, timeout=180))
        # 15 窄走廊里定位横跳 0.2–0.5 m(走到中间触发,持续 3 s)
        Lj = carve((-4.0, 4.0, -9.0, 9.0), [(-4.0, 4.0, -h, h)])
        sim = dict(SIM)
        sim.update({"fault_trigger": "within:0.0,0.0,0.4", "lateral_m": {"choice": [-0.5, -0.35, -0.2, 0.2, 0.35, 0.5]},
                    "fault_duration_s": 3.0})
        sc = width_case("p0_loc_jump_corridor", w, [-7.0, 0.0, 0.0], [[7.0, 0.0, 0.0], [-7.0, 0.0, PI]],
                        [7.0, 0.0, 0.0], Lj)
        sc["sim"] = sim
        out.append(sc)
        # 18 货架通道连续掉头:三条 w 宽、6 m 深、一头封死的通道,依次进到底、出来、进下一条
        racks = []
        chans = []
        for i in range(3):
            yc = -3.0 + i * 3.0
            chans.append((-3.0, 3.0, yc - h, yc + h))
        A = carve((-3.0, 3.3, -5.0, 4.0), chans)
        out.append(width_case("p0_aisles", w, [-7.0, -3.0, 0.0],
                              [[2.2, -3.0, 0.0], [2.2, 0.0, 0.0], [2.2, 3.0, 0.0], [-7.0, 0.0, PI]],
                              [2.2, -3.0, 0.0], A, timeout=150))
    # 4 U 型陷阱:U 口朝机器人,目标在 U 后面;地图上有 / 地图上没有(只能现场看见)两种
    U = [{"x": 2.0, "y": 0.0, "sx": 0.3, "sy": 6.0}, {"x": 0.5, "y": 3.0, "sx": 3.3, "sy": 0.3},
         {"x": 0.5, "y": -3.0, "sx": 3.3, "sy": 0.3}]
    for mapped in (True, False):
        obs = [dict(o, **({} if mapped else {"unmapped": True})) for o in U]
        out.append({"id": f"p0_utrap_{'mapped' if mapped else 'unmapped'}", "family": "p0_utrap",
                    "timeout_s": 150, "defaults": OPEN_DEFAULTS, "sim": dict(SIM),
                    "start": [-6.0, 0.0, 0.0], "goals": [[6.0, 0.0, 0.0], [-6.0, 0.0, PI]], "obstacles": obs})
    # 16 掉头时朝向突跳 10–30°:1.8 m 宽走廊尽头的点,到了要 180° 回头
    Yt = carve((-6.0, 4.0, -3.0, 3.0), [(-6.0, 3.0, -0.9, 0.9)])
    sim = dict(SIM)
    sim.update({"fault_trigger": "turning", "yaw_jump_deg": {"choice": [-30, -20, -10, 10, 20, 30]},
                "fault_duration_s": 3.0})
    out.append({"id": "p0_yaw_jump_uturn", "family": "p0_yaw_jump_uturn", "timeout_s": 150,
                "min_pose_clearance_m": 0.05, "defaults": TIGHT_DEFAULTS, "sim": sim,
                "start": [-7.5, 0.0, 0.0], "goals": [[2.0, 0.0, 0.0], [-7.5, 0.0, PI]], "obstacles": Yt})
    # 20 停车场综合:两排停好的车、车道边柱子、迎面开来的车、车缝里走出的人、地图上没有的箱子
    cars = []
    for x in (-6.0, -3.5, -1.0, 1.5, 4.0, 6.5):
        for y in (4.6, -4.6):
            cars.append({"x": x, "y": y, "sx": 1.8, "sy": 4.5})
    pillars = [{"x": x, "y": y, "sx": 0.6, "sy": 0.6} for x in (-4.75, 0.25, 5.25) for y in (2.0, -2.0)]
    box = [{"x": 2.8, "y": -0.9, "sx": 0.8, "sy": 0.6, "h": 0.8, "unmapped": True}]
    actors = [
        {"name": "car1", "kind": "vehicle", "sx": 4.5, "sy": 1.8, "h": 1.5, "speed": 2.0, "mode": "once",
         "path": [[9.5, 0.9], [-9.5, 0.9]], "start": {"robot_within": [-3.0, -0.6, 1.0]}},
        {"name": "p1", "kind": "person", "sx": 0.45, "sy": 0.45, "h": 1.7, "speed": 1.2, "mode": "once",
         "path": [[-2.25, -4.0], [-2.25, 3.5]], "start": {"robot_within": [-4.5, -0.6, 0.8]}},
        {"name": "p2", "kind": "person", "sx": 0.45, "sy": 0.45, "h": 1.7, "speed": 0.9, "mode": "pingpong",
         "path": [[3.0, 2.0], [7.0, 1.2]]},
    ]
    out.append({"id": "p0_parking_complex", "family": "p0_parking_complex", "timeout_s": 150,
                "defaults": OPEN_DEFAULTS, "sim": dict(SIM), "start": [-7.5, -0.6, 0.0],
                "goals": [[7.5, -0.6, 0.0], [-7.5, -0.6, PI]], "obstacles": cars + pillars + box,
                "actors": actors})
    # 广场窄缝(现场地图)
    site = {"dir": "runs/field-c40221/maps-build/plaza-c40221-v2",
            "nogo": "runs/field-c40221/maps-build/plaza-c40221-v2-nogo-user.json", "crop": [12.0, 34.0, -22.0, 2.0]}
    out.append({"id": "p0_plaza_gap", "family": "p0_plaza_gap", "timeout_s": 120, "min_pose_clearance_m": 0.05,
                "defaults": {**TIGHT_DEFAULTS, "start_jitter_xy_m": 0.1}, "sim": dict(SIM), "site_map": site,
                "start": [29.77, -15.88, -1.209], "goals": [[21.57, -15.59, 3.106]], "obstacles": []})
    base = yaml.safe_load((HERE / "scenarios.yaml").read_text(encoding="utf-8"))
    doc = {"version": 1, "defaults": base["defaults"], "scenarios": out}
    (HERE / "scenarios_p0.yaml").write_text(
        "# 自动生成(make_p0.py),别手改\n" + yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=200),
        encoding="utf-8")
    print(len(out), "个场景")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
