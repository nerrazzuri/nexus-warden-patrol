#!/usr/bin/env python3
"""Drive NavigateToPose goals and emit product-gate navigation metrics."""
from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path

from safety_geom import SafetyTracker


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


def _box_dist(x, y, b):
    dx = max(abs(x - b["x"]) - b["sx"] / 2.0, 0.0)
    dy = max(abs(y - b["y"]) - b["sy"] / 2.0, 0.0)
    return math.hypot(dx, dy)


def _body_clearance(pose, boxes):
    """车身矩形外沿到最近障碍盒的距离(米;压上了 = 0)。沿四条边每 10 cm 取一点。"""
    poly = _corners(*pose)
    best = math.inf
    for i in range(4):
        (x1, y1), (x2, y2) = poly[i], poly[(i + 1) % 4]
        n = max(2, int(math.hypot(x2 - x1, y2 - y1) / 0.1))
        for k in range(n + 1):
            x, y = x1 + (x2 - x1) * k / n, y1 + (y2 - y1) * k / n
            for b in boxes:
                best = min(best, _box_dist(x, y, b))
    return best


def main() -> int:
    import rclpy
    from action_msgs.msg import GoalStatus
    from geometry_msgs.msg import PoseArray, PoseStamped, Twist
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
            # 判停口径(REPORT_SPEC.md §5,11-07):只有真实车身碰上才算碰撞、终止这趟;
            # 外扩 5 cm 的框碰上只记余量侵入(margin_touch),接着走。
            self.collision = False
            self.collision_samples = 0
            self.margin_touch = None              # 第一次外扩框碰上的是什么:"wall" 或人/车的名字
            self.safety = SafetyTracker(case.get("collision_obstacles", case.get("obstacles", [])))
            self.create_subscription(LaserScan, "/scan", self.on_scan, 10)
            self.create_subscription(Odometry, "/odom", self.on_odom, 20)
            self.create_subscription(Twist, "/cmd_vel", self.on_cmd, 20)
            # 行人/车辆(actor_driver 发的实际位置,顺序同 case["actors"])
            self.actors = case.get("actors") or []
            self.actor_xy: list = []
            self.actor_hit = None                 # 机器人在动时碰上的那个:算机器人的错
            self.bumped_while_stopped = 0         # 机器人已停、被人走上来碰到:单独记,不算失败
            self.min_actor_gap = float("inf")
            self.robot_speed = 0.0
            self.create_subscription(PoseArray, "/nav_bench/actors", self.on_actors, 10)
            # 智驾式安全指标:车身外沿最小净距(几何)、TTC(按此刻速度多久撞上;只在走着时算)
            self.min_body_clear = math.inf
            self.min_body_clear_moving = math.inf
            self.min_ttc = math.inf
            self.ttc_under_1s = 0
            self._k = 0

        def on_actors(self, msg):
            self.actor_xy = [(p.position.x, p.position.y) for p in msg.poses]

        def _check_actors(self, poly, wx, wy):
            for i, (ax, ay) in enumerate(self.actor_xy[:len(self.actors)]):
                a = self.actors[i]
                box = {"x": ax, "y": ay, "sx": float(a["sx"]), "sy": float(a["sy"])}
                # 粗量间隙:中心距减去两边半宽(机身取半宽 0.29)
                gap = math.hypot(wx - ax, wy - ay) - 0.29 - max(box["sx"], box["sy"]) / 2.0
                self.min_actor_gap = min(self.min_actor_gap, gap)
                if _poly_intersects_box(poly, box):
                    if self.robot_speed > 0.05:
                        if self.margin_touch is None:
                            self.margin_touch = a["name"]
                    else:
                        self.bumped_while_stopped += 1

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
                if abs(obs["x"] - wx) > obs["sx"] / 2 + 0.6 or abs(obs["y"] - wy) > obs["sy"] / 2 + 0.6:
                    continue                      # 车身半对角线 0.59 m,够不着
                if _poly_intersects_box(poly, obs):
                    if self.margin_touch is None:
                        self.margin_touch = "wall"
                    break
            t = msg.twist.twist
            # 「在动」含原地转:转身时机身角点的线速度(半对角线 0.59 m)也算 —— 转身甩到旁边的人是机器人的错
            self.robot_speed = math.hypot(t.linear.x, t.linear.y) + abs(t.angular.z) * 0.59
            self._check_actors(poly, wx, wy)
            st = msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9
            boxes = [(self.actors[i]["name"], {"x": ax, "y": ay, "sx": float(self.actors[i]["sx"]),
                                                "sy": float(self.actors[i]["sy"])})
                     for i, (ax, ay) in enumerate(self.actor_xy[:len(self.actors)])]
            self.safety.step(st, (wx, wy, yaw), self.robot_speed, boxes)
            ss = self.safety.s
            if ss["static_physical"] or ss["dynamic_physical"]:
                if not self.collision and ss["dynamic_physical"]:
                    self.actor_hit = ss["dynamic_physical_actor"]
                self.collision = True
                self.collision_samples += 1
            self._k += 1
            if self._k % 5 == 0:                  # 10 Hz
                self._safety(wx, wy, yaw, t.linear.x, t.linear.y, t.angular.z)
            self.last_odom_speed = math.hypot(t.linear.x, t.linear.y) + abs(t.angular.z) * 0.15
            self.odom_samples += 1
            self._update_stall()

        def _near_boxes(self, wx, wy, r):
            out = [b for b in self.case.get("collision_obstacles", self.case.get("obstacles", []))
                   if abs(b["x"] - wx) <= b["sx"] / 2 + r and abs(b["y"] - wy) <= b["sy"] / 2 + r]
            for i, (ax, ay) in enumerate(self.actor_xy[:len(self.actors)]):
                a = self.actors[i]
                if abs(ax - wx) <= r + 3 and abs(ay - wy) <= r + 3:
                    out.append({"x": ax, "y": ay, "sx": float(a["sx"]), "sy": float(a["sy"])})
            return out

        def _safety(self, wx, wy, yaw, vx, vy, wz):
            near = self._near_boxes(wx, wy, 1.5)
            c = _body_clearance((wx, wy, yaw), near) if near else math.inf
            self.min_body_clear = min(self.min_body_clear, c)
            moving = math.hypot(vx, vy) > 0.05 or abs(wz) > 0.1
            if moving:
                self.min_body_clear_moving = min(self.min_body_clear_moving, c)
            if math.hypot(vx, vy) <= 0.05:
                return
            # 按此刻的机身系速度往前推 3 s(0.1 s 一步),第一次压上障碍的时刻 = TTC
            far = self._near_boxes(wx, wy, 3.5)
            x, y, th = wx, wy, yaw
            for k in range(1, 31):
                dt = 0.1
                x += (math.cos(th) * vx - math.sin(th) * vy) * dt
                y += (math.sin(th) * vx + math.cos(th) * vy) * dt
                th += wz * dt
                poly = _corners(x, y, th)
                if any(_poly_intersects_box(poly, b) for b in far):
                    ttc = k * dt
                    self.min_ttc = min(self.min_ttc, ttc)
                    if ttc < 1.0:
                        self.ttc_under_1s += 1
                    break

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
                    why = f"hit moving actor {self.actor_hit}" if self.actor_hit else "geometric collision"
                    results.append({"goal": idx, "success": False, "reason": why})
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
            arrived = len(results) == len(self.case["goals"]) and all(r["success"] for r in results)
            # blocked 场景:过不去是对的,只要不撞(也不该"到位"——到了说明穿过了障碍)
            success = (not arrived) if self.case.get("expect") == "blocked" else arrived
            return {
                "success": success and not self.collision,
                "goal_results": results,
                "elapsed_s": round(time.monotonic() - total_start, 3),
                "max_stall_s": round(self.max_stall, 3),
                "min_clearance_m": clearance,
                "clearance_violation": clearance is not None and clearance < threshold,
                "collision": self.collision,
                "stop_rule": "physical",
                "margin_touch": self.margin_touch,
                "safety": self.safety.result(),
                "collision_samples": self.collision_samples,
                "distance_m": round(self.distance_m, 3),
                "odom_samples": self.odom_samples,
                "expect": self.case.get("expect", "arrive"),
                "actor_hit": self.actor_hit,
                "bumped_while_stopped": self.bumped_while_stopped,
                "min_body_clearance_m": None if not math.isfinite(self.min_body_clear) else round(self.min_body_clear, 3),
                "min_body_clearance_moving_m": (None if not math.isfinite(self.min_body_clear_moving)
                                                else round(self.min_body_clear_moving, 3)),
                "min_ttc_s": None if not math.isfinite(self.min_ttc) else round(self.min_ttc, 2),
                "ttc_under_1s_samples": self.ttc_under_1s,
                "min_actor_gap_m": None if not math.isfinite(self.min_actor_gap) else round(self.min_actor_gap, 3),
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
