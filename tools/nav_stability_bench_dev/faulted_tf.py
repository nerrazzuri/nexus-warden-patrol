#!/usr/bin/env python3
"""发 map->odom,带定位故障和定位噪声。

仿真管 odom->base_link(真值);这里管 map->odom,所以定位跳变、朝向突跳、定位丢失、日常定位误差都
真的经过 Nav2 对 TF 的依赖。

- 触发(``--trigger``):``time``(仿真开始后 ``--at-s`` 秒)、``within:x,y,r``(机器人第一次进到这个圈
  里)、``turning``(第一次原地转身:前进 < 0.1 m/s、转速 > 0.3 rad/s)。触发后持续 ``--duration-s``。
- 跳变:``--jump-m`` 沿地图 x(老写法);``--lateral-m`` 沿机器人此刻的左侧(窄通道里横跳);
  ``--yaw-deg`` 朝向突跳 —— **绕机器人自己转**(原来绕地图原点转,机器人离原点 8 m 时 10° 等于再平移
  1.4 m)。
- 丢失:``--dropout-s`` 触发后停发这么久。
- 噪声:``--noise-m`` / ``--noise-deg`` 慢变的定位误差(Ornstein-Uhlenbeck,时间常数 3 s),一直有;
  真机定位跟腿里程比 ≤ 0.13 m(11-05 广场)。``--seed`` 定随机数。
- ``--start-*``:/odom 从出生点算起时 map->odom 要带的起点(世界坐标里程计给 0)。
"""
from __future__ import annotations

import argparse
import math
import random


def main() -> int:
    import rclpy
    from geometry_msgs.msg import TransformStamped
    from nav_msgs.msg import Odometry
    from rclpy.node import Node
    from rosgraph_msgs.msg import Clock
    from tf2_ros import TransformBroadcaster

    class FaultTF(Node):
        def __init__(self, args):
            super().__init__("nav_bench_faulted_tf")
            self.args = args
            self.br = TransformBroadcaster(self)
            self.sim_stamp = None
            self.sim_start = None
            self.robot = None              # 机器人在 odom 系里 (x, y, yaw, v, w)
            self.fired_at = None
            self.fire_pose = None
            self.rng = random.Random(args.seed)
            self.nx = self.ny = self.nyaw = 0.0
            self.last = None
            self.trig = args.trigger
            if self.trig == "time" and args.at_s >= 1e8:
                self.trig = "never"
            self.create_subscription(Clock, "/clock", self.on_clock, 10)
            self.create_subscription(Odometry, "/odom", self.on_odom, 20)
            self.create_timer(0.02, self.tick)

        def on_clock(self, msg):
            self.sim_stamp = msg.clock
            now = msg.clock.sec + msg.clock.nanosec / 1e9
            if self.sim_start is None:
                self.sim_start = now

        def on_odom(self, m):
            p, q = m.pose.pose.position, m.pose.pose.orientation
            yaw = math.atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z))
            self.robot = (p.x, p.y, yaw, m.twist.twist.linear.x, m.twist.twist.angular.z)

        def _check_trigger(self, now, elapsed):
            if self.fired_at is not None or self.trig == "never":
                return
            fire = False
            if self.trig == "time":
                fire = elapsed >= self.args.at_s
            elif self.trig.startswith("within:") and self.robot is not None:
                x, y, r = (float(v) for v in self.trig.split(":", 1)[1].split(","))
                fire = math.hypot(self.robot[0] - x, self.robot[1] - y) <= r
            elif self.trig == "turning" and self.robot is not None:
                fire = abs(self.robot[3]) < 0.1 and abs(self.robot[4]) > 0.3
            if fire:
                self.fired_at = now
                self.fire_pose = self.robot
                self.get_logger().warn(f"故障触发:{self.trig} @ {elapsed:.1f}s 机器人 {self.robot}")

        def tick(self):
            if self.sim_stamp is None or self.sim_start is None:
                return
            now = self.sim_stamp.sec + self.sim_stamp.nanosec / 1e9
            elapsed = now - self.sim_start
            self._check_trigger(now, elapsed)
            a = self.args
            since = None if self.fired_at is None else now - self.fired_at
            if since is not None and a.dropout_s > 0 and since < a.dropout_s:
                return
            active = since is not None and since < a.duration_s
            # 定位噪声:OU 过程,dt 按仿真时间
            if self.last is not None and (a.noise_m > 0 or a.noise_deg > 0):
                dt = max(0.0, min(0.2, now - self.last))
                k = dt / 3.0
                sq = math.sqrt(2 * k)
                self.nx += -k * self.nx + a.noise_m * sq * self.rng.gauss(0, 1)
                self.ny += -k * self.ny + a.noise_m * sq * self.rng.gauss(0, 1)
                self.nyaw += -k * self.nyaw + math.radians(a.noise_deg) * sq * self.rng.gauss(0, 1)
            self.last = now
            dx, dy, dyaw = self.nx, self.ny, self.nyaw
            if active:
                dx += a.jump_m
                if a.lateral_m and self.fire_pose is not None:
                    th = self.fire_pose[2]
                    dx += -math.sin(th) * a.lateral_m
                    dy += math.cos(th) * a.lateral_m
                dyaw += math.radians(a.yaw_deg)
            # 绕机器人此刻的位置转 dyaw,再平移 (dx, dy);叠在起点之上
            px, py = (self.robot[0], self.robot[1]) if self.robot else (0.0, 0.0)
            c, s = math.cos(dyaw), math.sin(dyaw)
            tx = px - (c * px - s * py) + dx
            ty = py - (s * px + c * py) + dy
            # 再复合起点 (sx, sy, syaw):map->odom = 起点 ∘ 扰动
            sc, ss = math.cos(a.start_yaw), math.sin(a.start_yaw)
            x = a.start_x + sc * tx - ss * ty
            y = a.start_y + ss * tx + sc * ty
            yaw = a.start_yaw + dyaw
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
    ap.add_argument("--trigger", default="time")
    ap.add_argument("--duration-s", type=float, default=2.0)
    ap.add_argument("--jump-m", type=float, default=0.0)
    ap.add_argument("--lateral-m", type=float, default=0.0)
    ap.add_argument("--yaw-deg", type=float, default=0.0)
    ap.add_argument("--dropout-s", type=float, default=0.0)
    ap.add_argument("--noise-m", type=float, default=0.0)
    ap.add_argument("--noise-deg", type=float, default=0.0)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--start-x", type=float, default=0.0)
    ap.add_argument("--start-y", type=float, default=0.0)
    ap.add_argument("--start-yaw", type=float, default=0.0, help="rad")
    args = ap.parse_args()
    rclpy.init()
    n = FaultTF(args)
    try:
        rclpy.spin(n)
    except KeyboardInterrupt:
        pass
    finally:
        n.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
