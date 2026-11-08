#!/usr/bin/env python3
"""Drive NavigateToPose goals and emit product-gate navigation metrics."""
from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path


def _corners(x, y, yaw, hx=0.515, hy=0.29):
    c, s = math.cos(yaw), math.sin(yaw)
    out = []
    for lx, ly in ((hx, hy), (hx, -hy), (-hx, -hy), (-hx, hy)):
        out.append((x + c * lx - s * ly, y + s * lx + c * ly))
    return out


def _project(poly, axis):
    vals = [p[0] * axis[0] + p[1] * axis[1] for p in poly]
    return min(vals), max(vals)


def _overlap(a, b):
    return min(a[1], b[1]) >= max(a[0], b[0])


def _poly_intersects_box(poly, obs):
    hx, hy = obs["sx"] / 2.0, obs["sy"] / 2.0
    box = [(obs["x"]-hx, obs["y"]-hy), (obs["x"]+hx, obs["y"]-hy),
           (obs["x"]+hx, obs["y"]+hy), (obs["x"]-hx, obs["y"]+hy)]
    axes = [(1.0, 0.0), (0.0, 1.0)]
    for i in range(len(poly)):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % len(poly)]
        ex, ey = x2-x1, y2-y1
        n = math.hypot(ex, ey) or 1.0
        axes.append((-ey/n, ex/n))
    return all(_overlap(_project(poly, a), _project(box, a)) for a in axes)


def main() -> int:
    import rclpy
    from action_msgs.msg import GoalStatus
    from geometry_msgs.msg import PoseStamped, Twist
    from nav2_msgs.action import NavigateToPose
    from nav_msgs.msg import Odometry
    from rclpy.action import ActionClient
    from rclpy.node import Node
    from sensor_msgs.msg import LaserScan

    class Driver(Node):
        def __init__(self, case: dict):
            super().__init__("nav_stability_goal_driver")
            self.case = case
            self.client = ActionClient(self, NavigateToPose, "navigate_to_pose")
            self.min_clearance = float("inf")
            self.last_odom_speed = 0.0
            self.last_cmd_mag = 0.0
            self.active_since = None
            self.stall_started = None
            self.max_stall = 0.0
            self.odom_samples = 0
            self.distance_m = 0.0
            self.last_xy = None
            self.first_world = None
            self.last_world = None
            self.collision = False
            self.collision_samples = 0
            self.create_subscription(LaserScan, "/scan", self.on_scan, 10)
            self.create_subscription(Odometry, "/odom", self.on_odom, 20)
            self.create_subscription(Twist, "/cmd_vel", self.on_cmd, 20)

        def on_scan(self, msg):
            vals = [x for x in msg.ranges if math.isfinite(x) and x > 0]
            if vals:
                self.min_clearance = min(self.min_clearance, min(vals))

        def on_odom(self, msg):
            p = msg.pose.pose.position
            q = msg.pose.pose.orientation
            yaw = math.atan2(2*(q.w*q.z + q.x*q.y), 1 - 2*(q.y*q.y + q.z*q.z))
            # /odom 从出生点算起;碰撞要在世界坐标里判,先叠上起点位姿。
            sx, sy, syaw = (self.case.get("start", (0.0, 0.0, 0.0))
                            if self.case.get("odom_origin", "spawn") == "spawn" else (0.0, 0.0, 0.0))
            c, s = math.cos(syaw), math.sin(syaw)
            wx, wy = sx + c * p.x - s * p.y, sy + s * p.x + c * p.y
            yaw += syaw
            xy = (wx, wy)
            self.last_world = (wx, wy, yaw)
            if self.first_world is None:
                self.first_world = (wx, wy, yaw)
            if self.last_xy is not None:
                self.distance_m += math.hypot(xy[0]-self.last_xy[0], xy[1]-self.last_xy[1])
            self.last_xy = xy
            poly = _corners(wx, wy, yaw)
            for obs in self.case.get("collision_obstacles", self.case.get("obstacles", [])):
                if _poly_intersects_box(poly, obs):
                    self.collision = True
                    self.collision_samples += 1
                    break
            t = msg.twist.twist
            self.last_odom_speed = math.hypot(t.linear.x, t.linear.y) + abs(t.angular.z) * 0.15
            self.odom_samples += 1
            self._update_stall()

        def on_cmd(self, msg):
            self.last_cmd_mag = math.hypot(msg.linear.x, msg.linear.y) + abs(msg.angular.z) * 0.15
            self._update_stall()

        def _update_stall(self):
            if self.active_since is None:
                self.stall_started = None
                return
            now = time.monotonic()
            stalled = self.last_cmd_mag > 0.08 and self.last_odom_speed < 0.02
            if stalled and self.stall_started is None:
                self.stall_started = now
            elif not stalled and self.stall_started is not None:
                self.max_stall = max(self.max_stall, now - self.stall_started)
                self.stall_started = None

        def pose(self, p):
            x, y, yaw = p
            msg = PoseStamped()
            msg.header.frame_id = "map"
            msg.header.stamp = self.get_clock().now().to_msg()
            msg.pose.position.x = float(x)
            msg.pose.position.y = float(y)
            msg.pose.orientation.z = math.sin(float(yaw) / 2.0)
            msg.pose.orientation.w = math.cos(float(yaw) / 2.0)
            return msg

        def run(self):
            timeout = float(self.case.get("timeout_s", 90))
            if not self.client.wait_for_server(timeout_sec=30.0):
                return {"success": False, "reason": "navigate_to_pose action unavailable"}
            results = []
            total_start = time.monotonic()
            for idx, goal in enumerate(self.case["goals"]):
                self.active_since = time.monotonic()
                request = NavigateToPose.Goal()
                request.pose = self.pose(goal)
                # Nav2 的 action 服务比 bt_navigator 激活早出现;没激活时目标会被拒。
                # 第一个目标被拒就每秒重发,最多等 30 s,不把启动慢算成导航失败。
                retry_until = time.monotonic() + (30.0 if idx == 0 else 0.0)
                while True:
                    send = self.client.send_goal_async(request)
                    rclpy.spin_until_future_complete(self, send, timeout_sec=10.0)
                    handle = send.result()
                    if (handle is not None and handle.accepted) or time.monotonic() >= retry_until:
                        break
                    time.sleep(1.0)
                self.active_since = time.monotonic()
                if handle is None or not handle.accepted:
                    results.append({"goal": idx, "success": False, "reason": "goal rejected"})
                    break
                future = handle.get_result_async()
                deadline = time.monotonic() + timeout
                while rclpy.ok() and not future.done() and time.monotonic() < deadline:
                    rclpy.spin_once(self, timeout_sec=0.05)
                    if self.collision:
                        handle.cancel_goal_async()
                        break
                if self.collision:
                    results.append({"goal": idx, "success": False, "reason": "geometric collision"})
                    break
                if not future.done():
                    handle.cancel_goal_async()
                    results.append({"goal": idx, "success": False, "reason": "timeout"})
                    break
                wrapped = future.result()
                ok = wrapped is not None and wrapped.status == GoalStatus.STATUS_SUCCEEDED
                results.append({
                    "goal": idx,
                    "success": ok,
                    "status": None if wrapped is None else int(wrapped.status),
                    "elapsed_s": round(time.monotonic() - self.active_since, 3),
                })
                self.active_since = None
                if not ok:
                    break
            if self.stall_started is not None:
                self.max_stall = max(self.max_stall, time.monotonic() - self.stall_started)
            threshold = float(self.case.get("safety_min_clearance_m", 0.08))
            clearance = None if not math.isfinite(self.min_clearance) else round(self.min_clearance, 4)
            success = len(results) == len(self.case["goals"]) and all(r["success"] for r in results)
            return {
                "success": success and not self.collision,
                "goal_results": results,
                "elapsed_s": round(time.monotonic() - total_start, 3),
                "max_stall_s": round(self.max_stall, 3),
                "min_clearance_m": clearance,
                "clearance_violation": clearance is not None and clearance < threshold,
                "collision": self.collision,
                "collision_samples": self.collision_samples,
                "distance_m": round(self.distance_m, 3),
                "odom_samples": self.odom_samples,
                # 坐标核对:世界坐标下的起点/终点,应接近 case 的 start 和最后一个 goal
                "first_world_pose": None if self.first_world is None else [round(v, 3) for v in self.first_world],
                "last_world_pose": None if self.last_world is None else [round(v, 3) for v in self.last_world],
            }

    ap = argparse.ArgumentParser()
    ap.add_argument("--case", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    case = json.loads(args.case.read_text(encoding="utf-8"))
    rclpy.init()
    node = Driver(case)
    try:
        metrics = node.run()
    finally:
        node.destroy_node()
        rclpy.shutdown()
    args.out.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    print(json.dumps(metrics))
    return 0 if metrics.get("success") and not metrics.get("clearance_violation") else 2


if __name__ == "__main__":
    raise SystemExit(main())
