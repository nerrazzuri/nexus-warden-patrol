#!/usr/bin/env python3
"""Drive NavigateToPose goals and emit product-gate navigation metrics."""
from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path

from safety_geom import BASE_HX, BASE_HY, SafetyTracker

#: 照路走控制器都放弃以后重查路线最多几次(跟正式代码 nav2_nav.ROUTE_RECHECKS 一样)。
ROUTE_RECHECKS = 2


def _corners(x, y, yaw, hx=BASE_HX, hy=BASE_HY):
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
    from nav2_msgs.action import FollowPath, NavigateToPose
    from nav_msgs.msg import Path as PathMsg
    from nav_msgs.msg import OccupancyGrid, Odometry
    from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy

    import route_gate  # noqa: F401  导入时把正式代码(packages/*/src)加进 sys.path
    from nexwar_agent.bridges.nav2_nav import (AVOID_R, RETREAT_MAX_S, RETREAT_MIN_M,
                                               RETREAT_ROUTE_M, TRAIL_JUMP_M, TRAIL_KEEP_M,
                                               TRAIL_STEP_M, retreat_cmd)
    from rclpy.action import ActionClient
    from rclpy.node import Node
    from sensor_msgs.msg import LaserScan

    class Driver(Node):
        def __init__(self, case: dict):
            super().__init__("nav_stability_goal_driver")
            self.case = case
            self.route_gate_dir = None
            self.path_controller = "FollowPath"
            self.recover = True
            self.route_refused = False
            self.route_checks = []
            # 用户 11-15(最高优先:整趟走完):跟真机代理同一套恢复 —— 来路(世界系,倒退用)、本趟临时
            # 绕开的地方、退过几次;没到的点跳过接着走,重试一次,一圈完了回头补
            self.trail: list = []
            self.avoid: list = []
            self.retreats: list = []
            self.detours: list = []
            self.map0 = None
            latched = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL,
                                 reliability=ReliabilityPolicy.RELIABLE)
            self.create_subscription(OccupancyGrid, "/map", self._on_map, latched)
            self.map_pub = self.create_publisher(OccupancyGrid, "/map", latched)
            self.cmd_pub = self.create_publisher(Twist, "/cmd_vel_nav", 10)
            self.client = ActionClient(self, NavigateToPose, "navigate_to_pose")
            #: 外审 11-14:路线靠局部搜索放行时照那条路走(跟真机代理 → 转接节点一样)
            self.follow = ActionClient(self, FollowPath, "follow_path")
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
                # 粗量间隙:中心距减去两边半宽(机身取加余量的半宽)
                gap = math.hypot(wx - ax, wy - ay) - BASE_HY - max(box["sx"], box["sy"]) / 2.0
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
            tr = self.trail                                # 记来路(跟真机代理 _trail_note 一样)
            d = math.dist(tr[-1], xy) if tr else math.inf
            if tr and d > TRAIL_JUMP_M:
                tr.clear()
            if not tr or d >= TRAIL_STEP_M:
                tr.append(xy)
                del tr[:max(0, len(tr) - max(2, round(TRAIL_KEEP_M / TRAIL_STEP_M)))]
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

        def _on_map(self, msg):
            if self.map0 is None and msg.header.frame_id:
                self.map0 = msg

        def _send_map(self):
            """本趟临时绕开的地方(半径 AVOID_R)盖成障碍发 /map(真机:代理送图 nogo,转接节点盖进地图)。"""
            if self.map0 is None:
                return
            import copy

            import numpy as np
            m = copy.deepcopy(self.map0)
            info = m.info
            a = np.array(m.data, dtype=np.int8).reshape(info.height, info.width)
            res, ox, oy = info.resolution, info.origin.position.x, info.origin.position.y
            yy, xx = np.mgrid[0:info.height, 0:info.width]
            cx, cy = ox + (xx + 0.5) * res, oy + (yy + 0.5) * res
            for ax, ay in self.avoid:
                a[(cx - ax) ** 2 + (cy - ay) ** 2 <= AVOID_R ** 2] = 100
            m.data = a.ravel().tolist()
            m.header.stamp = self.get_clock().now().to_msg()
            self.map_pub.publish(m)
            t_end = time.monotonic() + 1.5                 # 等代价地图吃进去
            while time.monotonic() < t_end:
                rclpy.spin_once(self, timeout_sec=0.05)

        def _trail_len(self):
            return sum(math.dist(a, b) for a, b in zip(self.trail, self.trail[1:]))

        def _retreat(self, idx, metres):
            """沿来路倒退(跟真机代理 _start_retreat / _back_step 同一个 retreat_cmd);速度照样过守卫。"""
            x, y, _ = self.last_world
            pts, acc = [(x, y)], 0.0
            for p in reversed(self.trail[:-1]):
                acc += math.dist(pts[-1], p)
                pts.append(p)
                if acc >= metres:
                    break
            path, t0, ok = pts[1:], time.monotonic(), False
            while rclpy.ok() and not self.collision:
                now = time.monotonic()
                cmd = retreat_cmd(*self.last_world, path)
                if cmd is None:
                    ok = True
                    break
                if now - t0 > RETREAT_MAX_S or (self._deadline is not None and now > self._deadline):
                    break
                tw = Twist()
                tw.linear.x, tw.angular.z = float(cmd[0]), float(cmd[1])
                self.cmd_pub.publish(tw)
                rclpy.spin_once(self, timeout_sec=0.05)
            self.cmd_pub.publish(Twist())
            self.trail.clear()
            self.retreats.append({"goal": idx, "planned_m": round(acc, 2), "ok": ok,
                                  "took_s": round(time.monotonic() - t0, 1),
                                  "moved_m": round(math.dist((x, y), self.last_world[:2]), 2)})

        def _check(self, gate, goal, idx, **tag):
            chk = gate.check(self.pose(goal))
            chk.pop("poses", None)
            self.route_checks.append({"goal": idx, **tag, **{k: v for k, v in chk.items()
                                                             if k != "path"}})
            return chk

        def _detour(self, gate, goal, idx, chk):
            """路线卡在一处:本趟把那一处标成绕开、重新查(跟真机代理 _detour 同一套规矩)。"""
            at = chk.get("at")
            if not at or self.last_world is None:
                return None
            ax, ay = float(at[0]), float(at[1])
            if (math.dist((ax, ay), self.last_world[:2]) < AVOID_R + 0.6
                    or math.dist((ax, ay), goal[:2]) < AVOID_R + 0.6
                    or any(math.dist((ax, ay), p) < AVOID_R for p in self.avoid)):
                return None
            self.avoid.append((ax, ay))
            self._send_map()
            alt = self._check(gate, goal, idx, detour=[round(ax, 2), round(ay, 2)])
            ok = bool(alt.get("checked") and alt.get("ok"))
            self.detours.append({"goal": idx, "at": [round(ax, 2), round(ay, 2)], "ok": ok})
            if ok:
                return alt
            self.avoid.remove((ax, ay))
            self._send_map()
            return None

        def _go(self, idx, goal, gate, timeout):
            """一个目标走一次(真机代理 goto 一次)→ (结果, 是不是最终失败:引擎不再按重试来)。"""
            self.active_since = time.monotonic()
            self._deadline_s, self._deadline = timeout, None    # 收下第一个目标时起算
            if self.avoid:                                       # 上一趟的临时绕开:先撤再查路
                self.avoid = []
                self._send_map()
            tried: set = set()
            chk, final = None, False
            if gate is not None:
                chk = self._check(gate, goal, idx)
                if chk.get("checked") and not chk.get("ok"):
                    alt = self._detour(gate, goal, idx, chk) if self.recover else None
                    if alt is None:
                        self.route_refused = True
                        return {"goal": idx, "success": False, "reason": "route_refused",
                                "code": chk.get("code"), "elapsed_s": 0.0}, True
                    chk = alt
            # 外审 11-14:路线靠局部搜索放行就让控制器照那条路走(FollowPath);控制器放弃了先换 RPP 跟
            # 同一条,还不行从当前位置重新查路线,最多 ROUTE_RECHECKS 次;重查也过不去先沿来路退出来再查,
            # 还不过试绕开那一处(用户 11-15)
            path = (chk or {}).get("path")
            controller, rechecks, followed = self.path_controller, 0, False
            while True:
                if path:
                    followed = True
                    out = self._drive_path(path, controller)
                else:
                    out = self._drive_nav(goal, idx)
                if out.get("reason") or out["success"] or not path:
                    break
                if controller != "RPP":
                    controller = "RPP"
                    continue
                if rechecks >= ROUTE_RECHECKS or gate is None:
                    break
                rechecks += 1
                chk = self._check(gate, goal, idx, recheck=rechecks)
                if chk.get("checked") and not chk.get("ok") and "route_retreat" not in tried \
                        and self.recover and self._trail_len() >= RETREAT_MIN_M:
                    tried.add("route_retreat")
                    self._retreat(idx, RETREAT_ROUTE_M)
                    chk = self._check(gate, goal, idx, recheck=rechecks, after="retreat")
                if chk.get("checked") and not chk.get("ok"):
                    alt = self._detour(gate, goal, idx, chk) if self.recover else None
                    if alt is None:
                        out, final = {"success": False, "reason": "route_refused",
                                      "code": chk.get("code")}, True
                        break
                    chk = alt
                path, controller = chk.get("path"), self.path_controller
            if self.avoid:
                self.avoid = []
                self._send_map()
            res = {"goal": idx, **out, "followed_path": followed, "rechecks": rechecks,
                   "elapsed_s": round(time.monotonic() - self.active_since, 3)}
            self.active_since = None
            return res, final

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

        def _wait(self, handle) -> dict:
            """等一个收下了的动作:撞了、超时就取消。"""
            if self._deadline is None:
                self._deadline = time.monotonic() + self._deadline_s
            future = handle.get_result_async()
            while rclpy.ok() and not future.done() and time.monotonic() < self._deadline:
                rclpy.spin_once(self, timeout_sec=0.05)
                if self.collision:
                    handle.cancel_goal_async()
                    break
            if self.collision:
                why = f"hit moving actor {self.actor_hit}" if self.actor_hit else "geometric collision"
                return {"success": False, "reason": why}
            if not future.done():
                handle.cancel_goal_async()
                return {"success": False, "reason": "timeout"}
            wrapped = future.result()
            ok = wrapped is not None and wrapped.status == GoalStatus.STATUS_SUCCEEDED
            return {"success": ok, "status": None if wrapped is None else int(wrapped.status)}

        def _drive_nav(self, goal, idx) -> dict:
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
            if handle is None or not handle.accepted:
                return {"success": False, "reason": "goal rejected"}
            return self._wait(handle)

        def _drive_path(self, path, controller) -> dict:
            if self.route_gate_dir is not None:
                # 11-15:留下要执行的路,事后跟里程比偏了多少(跟得紧不紧)
                with (self.route_gate_dir / "paths.jsonl").open("a", encoding="utf-8") as f:
                    f.write(json.dumps({"t": time.monotonic(), "controller": controller,
                                        "path": [[round(v, 3) for v in q] for q in path]}) + "\n")
            if not self.follow.wait_for_server(timeout_sec=30.0):
                return {"success": False, "reason": "follow_path action unavailable"}
            request = FollowPath.Goal()
            request.path = PathMsg()
            request.path.header.frame_id = "map"
            request.path.header.stamp = self.get_clock().now().to_msg()
            request.path.poses = [self.pose([x, y, yaw]) for x, y, yaw in path]
            request.controller_id = controller
            request.goal_checker_id = "general_goal_checker"
            send = self.follow.send_goal_async(request)
            rclpy.spin_until_future_complete(self, send, timeout_sec=10.0)
            handle = send.result()
            if handle is None or not handle.accepted:
                return {"success": False, "reason": "path goal rejected"}
            return self._wait(handle)

        def run(self):
            timeout = float(self.case.get("timeout_s", 90))
            if not self.client.wait_for_server(timeout_sec=30.0):
                return {"success": False, "reason": "navigate_to_pose action unavailable"}
            results = []
            gate = None
            if self.route_gate_dir is not None:
                # 导航 V1 第 2 节:跟真机一样,每个目标出发前先查路线几何,不过就不发(主动拒绝)
                from route_gate import RouteGate
                gate = RouteGate(self, self.route_gate_dir)
            total_start = time.monotonic()
            goals = self.case["goals"]
            results: list = [None] * len(goals)
            for idx, goal in enumerate(goals):             # 引擎 retry_then_skip:重试一次,再不行跳过
                if self.collision:
                    break
                r, final = self._go(idx, goal, gate, timeout)
                if not r["success"] and not final and not self.collision:
                    r, _ = self._go(idx, goal, gate, timeout)
                    r["retried"] = True
                results[idx] = r
            for idx, goal in enumerate(goals):             # 一圈走完回头补没到的(只去一次)
                if self.collision or not self.recover:
                    break
                r0 = results[idx]
                if r0 is None or r0["success"]:
                    continue
                r, _ = self._go(idx, goal, gate, timeout)
                results[idx] = ({**r, "revisited": True, "first": r0} if r["success"]
                                else {**r0, "revisit_failed": True, "revisit": r})
            results = [r for r in results if r is not None]
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
                "route_refused": self.route_refused,
                "route_checks": self.route_checks,
                "goals_reached": sum(bool(r.get("success")) for r in results),
                "goals_total": len(self.case["goals"]),
                "retreats": self.retreats,
                "detours": self.detours,
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
    ap.add_argument("--route-gate", action="store_true", help="每个目标出发前查路线几何(Route Validator)")
    ap.add_argument("--no-search", action="store_true",
                    help="对照用:路线检查不做局部搜索(跟 A 组一样,窄的直接拒)")
    ap.add_argument("--no-recover", action="store_true",
                    help="对照用:不退出来再查、不绕开、不回头补(只按交付引擎重试一次再跳过)")
    ap.add_argument("--path-controller", default=None,
                    help="照查过的路走时先用哪个控制器(缺省跟真机代理一样;放弃了照旧换 RPP)")
    args = ap.parse_args()
    case = json.loads(args.case.read_text(encoding="utf-8"))
    rclpy.init()
    node = Driver(case)
    node.route_gate_dir = args.case.parent if args.route_gate else None
    from nexwar_agent.bridges.nav2_nav import PATH_CONTROLLER
    node.path_controller = args.path_controller or PATH_CONTROLLER
    node.recover = not args.no_recover
    if args.no_search:
        from nexwar_agent import route_check as _rc
        _rc._searched = lambda *a, **k: None                # 局部搜索永远找不到 → 窄的照旧拒
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
