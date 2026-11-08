#!/usr/bin/env python3
"""Publish map->odom with deterministic localization faults.

The simulator owns odom->base_link. This node owns map->odom so pose jumps,
yaw jumps and localization dropouts exercise Nav2's actual TF dependency.
"""
from __future__ import annotations

import argparse
import math
import time


def main() -> int:
    import rclpy
    from geometry_msgs.msg import TransformStamped
    from rclpy.node import Node
    from tf2_ros import TransformBroadcaster

    class FaultTF(Node):
        def __init__(self, args):
            super().__init__("nav_bench_faulted_tf")
            self.args = args
            self.br = TransformBroadcaster(self)
            self.sim_stamp = None
            self.sim_start = None
            from rosgraph_msgs.msg import Clock
            self.create_subscription(Clock, "/clock", self.on_clock, 10)
            self.create_timer(0.02, self.tick)

        def on_clock(self, msg):
            self.sim_stamp = msg.clock
            now = msg.clock.sec + msg.clock.nanosec / 1e9
            if self.sim_start is None:
                self.sim_start = now

        def tick(self):
            if self.sim_stamp is None or self.sim_start is None:
                return
            now = self.sim_stamp.sec + self.sim_stamp.nanosec / 1e9
            elapsed = now - self.sim_start
            active = self.args.at_s <= elapsed < self.args.at_s + self.args.duration_s
            if self.args.dropout_s > 0 and self.args.at_s <= elapsed < self.args.at_s + self.args.dropout_s:
                return
            # map->odom = 起点位姿:仿真的里程计从出生点 (0,0,0) 算起,不加这一段
            # Nav2 会以为机器人在地图原点。故障跳变叠在起点之上。
            x = self.args.start_x + (self.args.jump_m if active else 0.0)
            y = self.args.start_y
            yaw = self.args.start_yaw + (math.radians(self.args.yaw_deg) if active else 0.0)
            t = TransformStamped()
            t.header.stamp = self.sim_stamp
            t.header.frame_id = "map"
            t.child_frame_id = "odom"
            t.transform.translation.x = x
            t.transform.translation.y = y
            t.transform.rotation.z = math.sin(yaw / 2.0)
            t.transform.rotation.w = math.cos(yaw / 2.0)
            self.br.sendTransform(t)

    ap = argparse.ArgumentParser()
    ap.add_argument("--at-s", type=float, default=1e9)
    ap.add_argument("--duration-s", type=float, default=2.0)
    ap.add_argument("--jump-m", type=float, default=0.0)
    ap.add_argument("--yaw-deg", type=float, default=0.0)
    ap.add_argument("--dropout-s", type=float, default=0.0)
    ap.add_argument("--start-x", type=float, default=0.0)
    ap.add_argument("--start-y", type=float, default=0.0)
    ap.add_argument("--start-yaw", type=float, default=0.0, help="rad")
    args = ap.parse_args()
    rclpy.init()
    n = FaultTF(args)
    try:
        rclpy.spin(n)
    finally:
        n.destroy_node()
        rclpy.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
