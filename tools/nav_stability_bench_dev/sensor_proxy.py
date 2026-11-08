#!/usr/bin/env python3
"""Production perception-topic proxy for the navigation benchmark.

Gazebo publishes /scan, while production Nav2 consumes PointCloud2 on
/nexwar/obs_occ and /nexwar/obs_free. This node converts the simulated scan to
those production topics and can inject deterministic latency/dropout and
synthetic dynamic obstacles. It intentionally does not alter production
params.yaml.
"""
from __future__ import annotations

import argparse
import math
import random
import struct
import time
from collections import deque
from pathlib import Path

BLIND_X = 0.4043


def main() -> int:
    import rclpy
    from builtin_interfaces.msg import Time as TimeMsg
    from rclpy.node import Node
    from sensor_msgs.msg import LaserScan, PointCloud2, PointField

    class Proxy(Node):
        def __init__(self, args):
            super().__init__("nav_bench_sensor_proxy")
            self.args = args
            self.rng = random.Random(args.seed ^ 0x5EED)
            self.started = time.monotonic()
            self.queue = deque()
            self.pub_occ = self.create_publisher(PointCloud2, "/nexwar/obs_occ", 10)
            self.pub_free = self.create_publisher(PointCloud2, "/nexwar/obs_free", 10)
            self.create_subscription(LaserScan, "/scan", self.scan, 10)
            self.create_timer(0.02, self.flush)

        def cloud(self, points, stamp: TimeMsg, frame: str):
            msg = PointCloud2()
            msg.header.stamp = stamp
            msg.header.frame_id = frame
            msg.height = 1
            msg.width = len(points)
            msg.fields = [
                PointField(name="x", offset=0, datatype=PointField.FLOAT32, count=1),
                PointField(name="y", offset=4, datatype=PointField.FLOAT32, count=1),
                PointField(name="z", offset=8, datatype=PointField.FLOAT32, count=1),
            ]
            msg.is_bigendian = False
            msg.point_step = 12
            msg.row_step = msg.point_step * msg.width
            msg.is_dense = True
            msg.data = b"".join(struct.pack("<fff", float(x), float(y), float(z)) for x, y, z in points)
            return msg

        def dynamic_points(self, elapsed):
            # Synthetic person-sized obstacle crossing in front of the robot.
            if not self.args.dynamic:
                return []
            phase = max(0.0, min(1.0, (elapsed - 5.0) / 8.0))
            if elapsed < 5.0 or elapsed > 15.0:
                return []
            cx = 2.2
            cy = -2.0 + 4.0 * phase
            pts = []
            for i in range(24):
                a = 2.0 * math.pi * i / 24
                pts.append((cx + 0.25 * math.cos(a), cy + 0.25 * math.sin(a), 0.5))
            return pts

        def scan(self, msg):
            if self.rng.random() < self.args.drop_rate:
                return
            pts = []
            angle = msg.angle_min
            for r in msg.ranges:
                if math.isfinite(r) and msg.range_min <= r <= msg.range_max:
                    px = self.args.lidar_x + r * math.cos(angle)
                    # 真机前后两台半球雷达在 x = ±0.404,机身两侧 |x| ≤ 0.404 那条带谁都看不见;仿真这台
                    # 360° 的看得见 —— 不去掉的话 Nav2 比真机多看见侧面,对「弱守卫」的结论偏乐观
                    py = r * math.sin(angle)
                    if self.args.blind_band == "cone":          # 实测锥形视野(obs-3f4)
                        if abs(px) <= BLIND_X or abs(py) > 0.6 + 0.9 * max(abs(px) - 0.465, 0.0):
                            angle += msg.angle_increment
                            continue
                        pts.append((px, py, 0.35))
                    elif not (self.args.blind_band and abs(px) <= BLIND_X):
                        pts.append((px, r * math.sin(angle), 0.35))
                angle += msg.angle_increment
            pts.extend(self.dynamic_points(time.monotonic() - self.started))
            occ = self.cloud(pts, msg.header.stamp, "base_link")
            # Raytrace clearing can use the same end points: they represent visible
            # free rays up to the current obstacle returns.
            free = self.cloud(pts, msg.header.stamp, "base_link")
            ready = time.monotonic() + self.args.delay_ms / 1000.0
            self.queue.append((ready, occ, free))

        def flush(self):
            now = time.monotonic()
            while self.queue and self.queue[0][0] <= now:
                _, occ, free = self.queue.popleft()
                self.pub_occ.publish(occ)
                self.pub_free.publish(free)

    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--delay-ms", type=float, default=0.0)
    ap.add_argument("--drop-rate", type=float, default=0.0)
    ap.add_argument("--dynamic", choices=("true", "false"), default="false")
    ap.add_argument("--blind-band", choices=("true", "false", "cone"), default="false",
                    help="true:去掉机身两侧盲带里的点(跟真机一样)")
    ap.add_argument("--lidar-x", type=float, default=0.40, help="雷达在 base_link 前方的安装位置 (m),跟 world.sdf 一致")
    args = ap.parse_args()
    args.dynamic = args.dynamic == "true"
    args.blind_band = "cone" if args.blind_band == "cone" else args.blind_band == "true"
    args.drop_rate = min(1.0, max(0.0, args.drop_rate))
    args.delay_ms = max(0.0, args.delay_ms)
    rclpy.init()
    node = Proxy(args)
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
