#!/usr/bin/env python3
"""生成守卫 A/B/C 对比 + 全向对比用的场景库 scenarios_ab.yaml(11-07)。

两部分:
1. 从 P0 库里挑「必须过 / 刚好不够」的窄路档(0.95–1.20 m)和几类综合场景 —— 看通过率;
2. 新加的安全场景 —— 看会不会撞,专门防「守卫越弱越好」的错误结论:
   - 转身时人站在机身侧面盲带里(人从前方走来,前雷达看见过,然后进了两侧谁都看不见的那条带;
     机器人到点要 180° 掉头,角点会甩到人)—— 左、右各一个;
   - 窄弯后有地图上没有的箱子把路堵死(应停,不撞);
   - 宽走廊里地图上没有的箱子占掉一半(应绕过去);
   - 感知延迟 300 ms 的停车场、窄走廊迎面来人。
"""
from __future__ import annotations

import math
from pathlib import Path

import yaml

from make_p0 import OPEN_DEFAULTS, SIM, TIGHT_DEFAULTS, carve

HERE = Path(__file__).resolve().parent
PI = math.pi

PICK_WIDTH = ("p0_L90", "p0_S", "p0_door_turn", "p0_aisles", "p0_deadend")
PICK_W = (0.95, 1.0, 1.1, 1.2)
PICK_IDS = ("p0_corridor_oncoming_w100", "p0_corridor_oncoming_w110", "p0_loc_jump_corridor_w100",
            "p0_utrap_unmapped", "p0_parking_complex", "p0_yaw_jump_uturn", "p0_plaza_gap")


def side_person(side: int) -> dict:
    """side = +1 人停在机器人左边,−1 右边。"""
    y = 0.72 * side
    person = {"name": "p1", "kind": "person", "sx": 0.45, "sy": 0.45, "h": 1.7, "speed": 1.0, "mode": "once",
              "path": [[6.5, 2.5 * side], [3.1, y, 25.0], [6.5, 3.0 * side]],
              "start": {"robot_within": [0.0, 0.0, 1.0]}}
    # 大厅:四周有墙(感知要有东西可看),中间空
    walls = [{"x": 0.5, "y": 4.0, "sx": 15.0, "sy": 0.3}, {"x": 0.5, "y": -4.0, "sx": 15.0, "sy": 0.3},
             {"x": 8.0, "y": 0.0, "sx": 0.3, "sy": 8.3}, {"x": -7.0, "y": 0.0, "sx": 0.3, "sy": 8.3}]
    return {"id": f"ab_side_person_uturn_{'left' if side > 0 else 'right'}", "family": "ab_side_person_uturn",
            "timeout_s": 150, "defaults": {**OPEN_DEFAULTS, "goal_jitter_xy_m": 0.05, "start_jitter_xy_m": 0.1},
            "sim": dict(SIM), "start": [-5.0, 0.0, 0.0], "goals": [[3.0, 0.0, 0.0], [-5.0, 0.0, PI]],
            "obstacles": walls, "actors": [person]}


def main() -> int:
    p0 = {s["id"]: s for s in yaml.safe_load((HERE / "scenarios_p0.yaml").read_text(encoding="utf-8"))["scenarios"]}
    out = []
    for fam in PICK_WIDTH:
        for w in PICK_W:
            out.append(p0[f"{fam}_w{int(round(w * 100)):03d}"])
    out += [p0[i] for i in PICK_IDS]
    out += [side_person(+1), side_person(-1)]
    # 窄弯(1.2 m 的 L)后面 1.5 m 有地图上没有的箱子把横段堵死:目标在箱子后面,应停住不撞
    w, h = 1.2, 0.6
    L = carve((-9.0, 9.0, -9.0, 9.0),
              [(-1.0, 8.8, 2.0, 8.8), (2.0, 2.0 + w, -3.0, 2.0), (-4.0, 2.0 + w, -3.0, -3.0 + w),
               (-8.8, -4.0, -8.8, 1.0)])
    box = {"x": 0.3, "y": -3.0 + h, "sx": 0.5, "sy": w + 0.1, "h": 0.6, "unmapped": True}
    out.append({"id": "ab_unmapped_block_after_corner", "family": "ab_unmapped_block_after_corner",
                "expect": "blocked", "timeout_s": 90, "min_pose_clearance_m": 0.05, "defaults": TIGHT_DEFAULTS,
                "sim": dict(SIM), "start": [2.0 + h, 4.5, -PI / 2], "goals": [[-6.0, -3.0 + h, PI]],
                "obstacles": L + [box]})
    # 2 m 宽走廊里地图上没有的箱子占掉一边(剩 1.4 m):应绕过去
    C = carve((-5.0, 5.0, -9.0, 9.0), [(-5.0, 5.0, -1.0, 1.0)])
    out.append({"id": "ab_unmapped_partial", "family": "ab_unmapped_partial", "timeout_s": 120,
                "min_pose_clearance_m": 0.05, "defaults": TIGHT_DEFAULTS, "sim": dict(SIM),
                "start": [-7.0, 0.0, 0.0], "goals": [[7.0, 0.0, 0.0], [-7.0, 0.0, PI]],
                "obstacles": C + [{"x": 0.0, "y": 0.7, "sx": 0.6, "sy": 0.6, "h": 0.6, "unmapped": True}]})
    # 感知延迟 300 ms
    for src, nid in (("p0_parking_complex", "ab_parking_delay300"),
                     ("p0_corridor_oncoming_w110", "ab_oncoming_delay300")):
        sc = dict(p0[src])
        sc["id"], sc["family"] = nid, nid
        sc.pop("width_m", None)
        sc["sim"] = {**sc["sim"], "obstacle_delay_ms": 300}
        out.append(sc)
    base = yaml.safe_load((HERE / "scenarios.yaml").read_text(encoding="utf-8"))
    doc = {"version": 1, "defaults": base["defaults"], "scenarios": out}
    (HERE / "scenarios_ab.yaml").write_text(
        "# 自动生成(make_ab.py),别手改\n" + yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=200),
        encoding="utf-8")
    print(len(out), "个场景")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
