#!/usr/bin/env python3
"""从录包重算安全指标(真实碰撞 / 余量侵入,墙和人车分开)→ 每趟目录里写 safety.json。

    python3 safety_from_bag.py runs/nav-sweep-ab-1107        # 有 bag 的趟都算,已有 safety.json 的跳过

给 11-07 之前的扫描补数用;之后的趟 goal_driver 当场算好写进 result.json 的 "safety"。
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

from safety_geom import SafetyTracker


def analyze(run: Path) -> dict:
    import rosbag2_py
    from geometry_msgs.msg import PoseArray, Twist
    from nav_msgs.msg import Odometry
    from rclpy.serialization import deserialize_message
    case = json.loads((run / "case.json").read_text())
    static = case.get("collision_obstacles", case.get("obstacles", []))
    actors = case.get("actors") or []
    sx, sy, syaw = (case.get("start", (0.0, 0.0, 0.0)) if case.get("odom_origin", "spawn") == "spawn"
                    else (0.0, 0.0, 0.0))
    c, s = math.cos(syaw), math.sin(syaw)
    r = rosbag2_py.SequentialReader()
    r.open(rosbag2_py.StorageOptions(uri=str(run / "bag"), storage_id="sqlite3"), rosbag2_py.ConverterOptions("", ""))
    tr = SafetyTracker(static)
    axy = []
    cmd = None
    while r.has_next():
        topic, data, t = r.read_next()
        if topic == "/cmd_vel":
            m = deserialize_message(data, Twist)
            cmd = [round(m.linear.x, 2), round(m.angular.z, 2)]
        elif topic == "/nav_bench/actors":
            m = deserialize_message(data, PoseArray)
            axy = [(p.position.x, p.position.y) for p in m.poses]
        elif topic == "/odom":
            m = deserialize_message(data, Odometry)
            p, q = m.pose.pose.position, m.pose.pose.orientation
            yaw = math.atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z)) + syaw
            wx, wy = sx + c * p.x - s * p.y, sy + s * p.x + c * p.y
            tw = m.twist.twist
            speed = math.hypot(tw.linear.x, tw.linear.y) + abs(tw.angular.z) * 0.59
            boxes = [(actors[i]["name"], {"x": ax, "y": ay, "sx": float(actors[i]["sx"]), "sy": float(actors[i]["sy"])})
                     for i, (ax, ay) in enumerate(axy[:len(actors)])]
            tr.step(t * 1e-9, (wx, wy, yaw), speed, boxes, cmd)
    return tr.result()


def main() -> int:
    root = Path(sys.argv[1])
    n = 0
    for bag in sorted(root.glob("*/*/s*/bag")):
        run = bag.parent
        if (run / "safety.json").exists() or not (run / "result.json").exists():
            continue                              # 算过的、还在跑的(没 result.json)跳过
        try:
            res = analyze(run)
        except Exception as e:                    # 包坏了:记下来,别停
            res = {"error": repr(e)}
        (run / "safety.json").write_text(json.dumps(res, ensure_ascii=False))
        n += 1
    print(n, "趟算完")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
