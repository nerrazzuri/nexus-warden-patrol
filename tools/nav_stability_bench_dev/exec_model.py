#!/usr/bin/env python3
"""执行误差:机器人不会一丝不差地照速度命令走(仿真代理原来是完美执行,0.9 m 窄弯都钻得过去)。

/cmd_vel(代理/Nav2 发的)→ 这里 → /cmd_vel_exec(给仿真里的机器人),50 Hz:

- 一阶滞后(时间常数 ``--tau``,默认 0.2 s):腿式运控跟速度要时间;
- 增益误差:这一趟前进、转向各乘一个 0.92–1.08 的系数(按种子定,整趟不变);
- 步态晃动:横向 ±``--sway`` m/s、约 1.8 Hz 的正弦(四足一步一晃);
- 随机噪声:前进 σ 0.02 m/s、横向 σ 0.02 m/s、转向 σ 0.03 rad/s;
- **运控死区**(2026-10-29 C40221 实测):前进、后退命令 < 0.13 m/s 只踏步不走;原地转命令 0.15 rad/s
  实际只转 0.069 rad/s —— 转向按「实际 = 命令 − 0.081 × (0.6 − |命令|)/0.45」(0.15 → 0.069,
  0.6 以上不打折),< 0.081 不转。横移的死区没量过,先不加;
- 命令 0.5 s 没来 → 停。
"""
from __future__ import annotations

import argparse
import math
import random


DEAD_VX = 0.13
DEAD_WZ = 0.081


def deadband(vx: float, vy: float, wz: float) -> tuple[float, float, float]:
    """真机运控的死区:命令 → 实际会走的速度。"""
    if abs(vx) < DEAD_VX - 1e-6:
        vx = 0.0
    w = abs(wz)
    if w < DEAD_WZ:
        wz = 0.0
    elif w < 0.6:
        wz = math.copysign(w - DEAD_WZ * (0.6 - w) / 0.45, wz)
    return vx, vy, wz


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--tau", type=float, default=0.2)
    ap.add_argument("--sway", type=float, default=0.04)
    args = ap.parse_args()

    import rclpy
    from geometry_msgs.msg import Twist
    from rclpy.node import Node
    from rosgraph_msgs.msg import Clock

    rng = random.Random(args.seed * 7919 + 17)
    gv, gw = rng.uniform(0.92, 1.08), rng.uniform(0.92, 1.08)
    phase = rng.uniform(0, 2 * math.pi)
    rclpy.init()
    node = Node("nav_bench_exec_model")
    pub = node.create_publisher(Twist, "/cmd_vel_exec", 10)
    st = {"now": None, "cmd": (0.0, 0.0, 0.0), "cmd_at": None, "v": [0.0, 0.0, 0.0], "last": None}

    def on_clock(m):
        st["now"] = m.clock.sec + m.clock.nanosec / 1e9

    def on_cmd(m):
        st["cmd"] = (m.linear.x, m.linear.y, m.angular.z)
        st["cmd_at"] = st["now"]

    def tick():
        now = st["now"]
        if now is None:
            return
        dt = 0.02 if st["last"] is None else max(0.0, min(0.1, now - st["last"]))
        st["last"] = now
        cmd = st["cmd"] if st["cmd_at"] is not None and now - st["cmd_at"] <= 0.5 else (0.0, 0.0, 0.0)
        dv = deadband(*cmd)
        want = (dv[0] * gv, dv[1] * gv, dv[2] * gw)
        a = 1.0 - math.exp(-dt / args.tau) if dt > 0 else 0.0
        st["v"] = [v + (w - v) * a for v, w in zip(st["v"], want)]
        moving = abs(cmd[0]) > 0.02 or abs(cmd[1]) > 0.02 or abs(cmd[2]) > 0.05     # 踏步也晃
        t = Twist()
        if moving:
            t.linear.x = st["v"][0] + rng.gauss(0, 0.02)
            t.linear.y = st["v"][1] + args.sway * math.sin(2 * math.pi * 1.8 * now + phase) + rng.gauss(0, 0.02)
            t.angular.z = st["v"][2] + rng.gauss(0, 0.03)
        else:
            t.linear.x, t.linear.y, t.angular.z = st["v"][0], st["v"][1], st["v"][2]
        pub.publish(t)

    node.create_subscription(Clock, "/clock", on_clock, 10)
    node.create_subscription(Twist, "/cmd_vel", on_cmd, 20)
    node.create_timer(0.02, tick)
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
