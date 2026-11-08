"""仿真台上的出发前路线检查(导航 V1 第 2 节,Route Validator V1.0)。

goal_driver 每个目标出发前:向 Nav2 要一条路线(ComputePathToPose,只规划不走),用**正式代码**的
``nexwar_agent.route_check`` 查有效车身离地图墙的余量;不过就不发这个目标,记成「主动拒绝」。
跟真机一样:规划不出、超时 → 不挡路,照常交给 Nav2。

地图用这一趟目录里的 map.yaml / map.pgm(只有地图墙;地图外的箱子、人、车不在里面)。
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for p in ("packages/robot-agent/src", "packages/contract/src"):
    if str(ROOT / p) not in sys.path:
        sys.path.insert(0, str(ROOT / p))

PLAN_TIMEOUT_S = 5.0


def _pgm(data: bytes):
    """P2(文本,仿真台写的)或 P5 → 行从上往下的 uint8 数组。"""
    import numpy as np
    if data[:2] == b"P5":
        from nexwar_contract.planning.costmap import parse_pgm
        return parse_pgm(data)
    toks = [t for line in data.decode().splitlines() for t in line.split("#")[0].split()]
    w, h, mx = int(toks[1]), int(toks[2]), int(toks[3])
    a = np.array(toks[4:4 + w * h], dtype=np.float32).reshape(h, w)
    return (a * (255.0 / mx)).astype(np.uint8)


def load_walls(case_dir: Path):
    """map.yaml + map.pgm → (walls[行 = y 从下往上, 列 = x], res, (ox, oy));未知格当墙。"""
    import numpy as np

    import yaml

    meta = yaml.safe_load((case_dir / "map.yaml").read_text(encoding="utf-8"))
    img = _pgm((case_dir / meta.get("image", "map.pgm")).read_bytes())
    occ = img.astype(np.float32) / 255.0
    if not meta["negate"]:
        occ = 1.0 - occ
    free = np.flipud(occ < meta["free_thresh"]).copy()
    o = meta["origin"]
    return ~free, float(meta["resolution"]), (float(o[0]), float(o[1]))


class RouteGate:
    def __init__(self, node, case_dir: Path):
        from nav2_msgs.action import ComputePathToPose
        from rclpy.action import ActionClient
        self.node = node
        self.walls = load_walls(case_dir)
        self.goal_t = ComputePathToPose.Goal
        self.client = ActionClient(node, ComputePathToPose, "compute_path_to_pose")

    def check(self, goal_pose_msg) -> dict:
        """→ ``{"checked": bool, "ok": bool, "code", "why", "margin", "at"}``;没查成 ``checked`` 为 False。"""
        import rclpy

        from nexwar_agent.route_check import check_route
        if not self.client.wait_for_server(timeout_sec=10.0):
            return {"checked": False, "why": "compute_path_to_pose unavailable"}
        g = self.goal_t()
        g.goal = goal_pose_msg
        g.use_start = False                                # 规划器按 TF 取此刻位姿
        send = self.client.send_goal_async(g)
        rclpy.spin_until_future_complete(self.node, send, timeout_sec=PLAN_TIMEOUT_S)
        h = send.result()
        if h is None or not h.accepted:
            return {"checked": False, "why": "plan rejected"}
        res = h.get_result_async()
        rclpy.spin_until_future_complete(self.node, res, timeout_sec=PLAN_TIMEOUT_S)
        r = res.result()
        poses = [] if r is None else r.result.path.poses
        if not poses:
            return {"checked": False, "why": "no path"}
        pts = [[p.pose.position.x, p.pose.position.y,
                2.0 * math.atan2(p.pose.orientation.z, p.pose.orientation.w)] for p in poses]
        v = check_route(pts, *self.walls)
        return {"checked": True, "ok": v.ok, "code": v.code, "why": v.why,
                "margin": round(v.margin, 3), "at": None if v.at is None else [round(a, 2) for a in v.at],
                "poses": len(pts)}
