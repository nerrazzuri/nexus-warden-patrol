#!/usr/bin/env python3
"""行人/车辆驱动:让 case.json 里的 actors 在 Gazebo 世界里按路线动起来。

每个 actor 是一个只有外形、没有碰撞体、不受重力的模型(雷达看得见,推不动机器人,
也不会被机器人推开),带 VelocityControl(收 /model/<名>/cmd_vel)和 OdometryPublisher
(发 /model/<名>/odom,世界坐标)。本节点:

- 起一个 parameter_bridge 把这些话题接到 ROS;
- 按时间表算每个 actor 此刻该在哪,用"前馈 + 位置反馈"发速度,不会越走越偏;
- 把 actor 的实际位置汇总发到 /nav_bench/actors(PoseArray,顺序同 case.json),
  goal_driver 用它判碰撞。

actor 的写法(scenarios.yaml):
    actors:
      - {name: p1, sx: 0.5, sy: 0.5, h: 1.7, speed: 1.2, mode: once,
         path: [[7.5, 0.2], [-7.5, 0.2]],          # 第三个数 = 到这一点后停几秒
         start: {robot_within: [-4.5, 0.0, 1.0]}}   # 或 {at_s: 3.0}(仿真开始后几秒)
    mode: once 走完停下;pingpong 来回;loop 走回第一个点再接着绕。
"""
from __future__ import annotations

import argparse
import json
import math
import subprocess
from pathlib import Path

BRIDGE = "/opt/ros/humble/lib/ros_gz_bridge/parameter_bridge"


class Timeline:
    """把路线展开成 [(t0, t1, p0, p1)] 一段段:走路段 p0≠p1,停留段 p0==p1。"""

    def __init__(self, path: list[list[float]], speed: float, mode: str):
        pts = [(float(p[0]), float(p[1]), float(p[2]) if len(p) > 2 else 0.0) for p in path]
        if mode == "pingpong" and len(pts) > 1:
            seq = pts + [(x, y, w) for x, y, w in reversed(pts[:-1])]
        elif mode == "loop" and len(pts) > 1:
            seq = pts + [pts[0]]
        else:
            seq = pts
        self.segs: list[tuple[float, float, tuple[float, float], tuple[float, float]]] = []
        t = 0.0
        for i, (x, y, wait) in enumerate(seq):
            if wait > 0:
                self.segs.append((t, t + wait, (x, y), (x, y)))
                t += wait
            if i + 1 < len(seq):
                nx, ny, _ = seq[i + 1]
                dur = math.hypot(nx - x, ny - y) / max(speed, 1e-3)
                if dur > 0:
                    self.segs.append((t, t + dur, (x, y), (nx, ny)))
                    t += dur
        self.period = t
        self.repeat = mode in ("pingpong", "loop") and t > 0
        self.home = (pts[0][0], pts[0][1])

    def at(self, t: float) -> tuple[float, float]:
        if t <= 0 or not self.segs:
            return self.home
        if self.repeat:
            t = t % self.period
        elif t >= self.period:
            return self.segs[-1][3]
        for t0, t1, p0, p1 in self.segs:
            if t <= t1:
                a = 0.0 if t1 <= t0 else (t - t0) / (t1 - t0)
                return (p0[0] + (p1[0] - p0[0]) * a, p0[1] + (p1[1] - p0[1]) * a)
        return self.segs[-1][3]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", default="")
    args = ap.parse_args()
    case = json.loads(Path(args.case).read_text(encoding="utf-8")) if args.case else {}
    actors = case.get("actors") or []

    import rclpy
    from geometry_msgs.msg import Pose, PoseArray, Twist
    from nav_msgs.msg import Odometry
    from rclpy.node import Node
    from rosgraph_msgs.msg import Clock

    rclpy.init()
    node = Node("nav_bench_actor_driver")
    pub = node.create_publisher(PoseArray, "/nav_bench/actors", 10)
    if not actors:
        # 没有 actor 也发空数组,goal_driver 不用分情况
        node.create_timer(0.5, lambda: pub.publish(PoseArray()))
        try:
            rclpy.spin(node)
        finally:
            node.destroy_node()
            rclpy.shutdown()
        return 0

    topics = []
    for a in actors:
        topics += [f"/model/{a['name']}/cmd_vel@geometry_msgs/msg/Twist]ignition.msgs.Twist",
                   f"/model/{a['name']}/odom@nav_msgs/msg/Odometry[ignition.msgs.Odometry"]
    bridge = subprocess.Popen([BRIDGE, *topics])

    state = {"now": None, "robot": None}
    lines = [Timeline(a["path"], float(a.get("speed", 1.0)), a.get("mode", "once")) for a in actors]
    began: list[float | None] = [None] * len(actors)
    actual: list[tuple[float, float] | None] = [None] * len(actors)
    cmd_pubs = [node.create_publisher(Twist, f"/model/{a['name']}/cmd_vel", 10) for a in actors]

    def on_clock(msg):
        state["now"] = msg.clock.sec + msg.clock.nanosec / 1e9

    def on_robot(msg):
        p = msg.pose.pose.position
        state["robot"] = (p.x, p.y)

    def make_odom_cb(i):
        def cb(msg):
            p = msg.pose.pose.position
            actual[i] = (p.x, p.y)
        return cb

    node.create_subscription(Clock, "/clock", on_clock, 10)
    node.create_subscription(Odometry, "/odom", on_robot, 20)
    for i, a in enumerate(actors):
        node.create_subscription(Odometry, f"/model/{a['name']}/odom", make_odom_cb(i), 20)

    dt = 0.05

    def tick():
        now = state["now"]
        if now is None:
            return
        out = PoseArray()
        out.header.frame_id = "map"
        out.header.stamp = node.get_clock().now().to_msg()
        for i, a in enumerate(actors):
            st = a.get("start") or {"at_s": 0.0}
            if began[i] is None:
                if "robot_within" in st:
                    rx, ry, r = st["robot_within"]
                    if state["robot"] and math.hypot(state["robot"][0] - rx, state["robot"][1] - ry) <= r:
                        began[i] = now
                elif now >= float(st.get("at_s", 0.0)):
                    began[i] = now
            t = 0.0 if began[i] is None else now - began[i]
            want_next = lines[i].at(t + dt)
            here = actual[i] or lines[i].at(t)
            # 前馈:按时间表下一刻该到哪;反馈:把实际位置拉回时间表
            vx = (want_next[0] - here[0]) / dt
            vy = (want_next[1] - here[1]) / dt
            cap = 1.5 * float(a.get("speed", 1.0)) + 0.5
            n = math.hypot(vx, vy)
            if n > cap:
                vx, vy = vx * cap / n, vy * cap / n
            tw = Twist()
            tw.linear.x, tw.linear.y = vx, vy
            cmd_pubs[i].publish(tw)
            p = Pose()
            p.position.x, p.position.y = here
            p.orientation.w = 1.0
            out.poses.append(p)
        pub.publish(out)

    node.create_timer(dt, tick)
    try:
        rclpy.spin(node)
    finally:
        bridge.terminate()
        node.destroy_node()
        rclpy.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
