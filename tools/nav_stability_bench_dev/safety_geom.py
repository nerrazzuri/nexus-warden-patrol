"""安全指标的几何:真实车身(0.93 × 0.48,不加 5 cm)到障碍盒的精确最小距离。

报告规范(11-07,见 REPORT_SPEC.md)把「碰撞」拆成两种:
- 真实碰撞:车身矩形和障碍真的重叠(距离 = 0);
- 余量侵入:没碰上,但车身离障碍 < 5 cm / < 10 cm。
墙(地图上的、地图外的箱子)和人/车分开统计。
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[2] / "packages" / "contract" / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
from nexwar_contract.footprint import BASE_HALF_LEN, BASE_HALF_WID, BODY_LEN, BODY_WID  # noqa: E402

BODY_HX, BODY_HY = BODY_LEN / 2, BODY_WID / 2          # 真实车身半长、半宽
#: 车身 + 基础余量(守卫、Nav2 footprint 用的)
BASE_HX, BASE_HY = BASE_HALF_LEN, BASE_HALF_WID
MARGIN_BANDS = (0.05, 0.10)             # 余量侵入的两档


def body_corners(x, y, yaw, hx=BODY_HX, hy=BODY_HY):
    c, s = math.cos(yaw), math.sin(yaw)
    return [(x + c * lx - s * ly, y + s * lx + c * ly) for lx, ly in ((hx, hy), (hx, -hy), (-hx, -hy), (-hx, hy))]


def _box_corners(b):
    hx, hy = b["sx"] / 2.0, b["sy"] / 2.0
    return [(b["x"] - hx, b["y"] - hy), (b["x"] + hx, b["y"] - hy), (b["x"] + hx, b["y"] + hy), (b["x"] - hx, b["y"] + hy)]


def _sat_overlap(p, q):
    for poly in (p, q):
        for i in range(4):
            x1, y1 = poly[i]
            x2, y2 = poly[(i + 1) % 4]
            ax, ay = -(y2 - y1), x2 - x1
            pa = [u * ax + v * ay for u, v in p]
            qa = [u * ax + v * ay for u, v in q]
            if max(pa) < min(qa) or max(qa) < min(pa):
                return False
    return True


def _pt_seg(px, py, x1, y1, x2, y2):
    ex, ey = x2 - x1, y2 - y1
    L = ex * ex + ey * ey
    t = 0.0 if L == 0 else max(0.0, min(1.0, ((px - x1) * ex + (py - y1) * ey) / L))
    return math.hypot(px - x1 - t * ex, py - y1 - t * ey)


def body_box_distance(pose, box) -> float:
    """车身到一个轴对齐障碍盒的最小距离(米);重叠 = 0。两个凸四边形不相交时,
    最近点一定是一方的顶点到另一方的边,所以逐对算就是精确值。"""
    p = body_corners(*pose)
    q = _box_corners(box)
    if _sat_overlap(p, q):
        return 0.0
    best = math.inf
    for a, b in ((p, q), (q, p)):
        for vx, vy in a:
            for i in range(4):
                x1, y1 = b[i]
                x2, y2 = b[(i + 1) % 4]
                best = min(best, _pt_seg(vx, vy, x1, y1, x2, y2))
    return best


def min_distance(pose, boxes, reach=1.6) -> float:
    x, y = pose[0], pose[1]
    best = math.inf
    for b in boxes:
        if abs(b["x"] - x) > b["sx"] / 2 + reach or abs(b["y"] - y) > b["sy"] / 2 + reach:
            continue
        best = min(best, body_box_distance(pose, b))
    return best


class SafetyTracker:
    """逐帧喂位姿,累计真实碰撞 / 余量侵入。「在动」= 平移 > 0.05 m/s 或角点线速度(|wz|·0.59)> 0.05。
    人/车:只算机器人在动时的(停着被人走上来碰到另记 dyn_bumped_while_stopped)。
    墙:不管动没动都算(停在墙里也是走进去的)。"""

    def __init__(self, static_boxes):
        self.static = static_boxes
        self.s = {"static_min_m": math.inf, "dynamic_min_moving_m": math.inf,
                  "static_physical": False, "dynamic_physical": False, "dynamic_physical_actor": None,
                  "dyn_bumped_while_stopped": False, "dynamic_contact_speed": None,
                  "dynamic_contact_after_5cm_s": None, "dynamic_contact_cmd": None, "dynamic_5cm_speed": None, "dynamic_5cm_cmd": None, "_t5": None,
                  "static_under_5cm_s": 0.0, "static_under_10cm_s": 0.0,
                  "dynamic_under_5cm_s": 0.0, "dynamic_under_10cm_s": 0.0}
        self._t = None

    def step(self, t, pose, speed, actors, cmd=None):
        """actors: [(name, box)],box 同障碍盒格式(世界坐标)。"""
        dt = 0.0 if self._t is None else max(0.0, min(0.2, t - self._t))
        self._t = t
        s = self.s
        ds = min_distance(pose, self.static)
        s["static_min_m"] = min(s["static_min_m"], ds)
        if ds <= 0.0:
            s["static_physical"] = True
        if ds < 0.05:
            s["static_under_5cm_s"] += dt
        if ds < 0.10:
            s["static_under_10cm_s"] += dt
        moving = speed > 0.05
        dmin, who = math.inf, None
        for name, box in actors:
            dd = min_distance(pose, [box], reach=2.0)
            if dd < dmin:
                dmin, who = dd, name
        if not math.isfinite(dmin):
            return
        if not moving:
            if dmin <= 0.0:
                s["dyn_bumped_while_stopped"] = True
            return
        s["dynamic_min_moving_m"] = min(s["dynamic_min_moving_m"], dmin)
        if dmin < 0.05 and s["_t5"] is None:
            s["_t5"] = t
            s["dynamic_5cm_speed"], s["dynamic_5cm_cmd"] = speed, cmd   # 进 5 cm 那一刻:守卫看见了没有
        if dmin <= 0.0 and not s["dynamic_physical"]:
            s["dynamic_physical"], s["dynamic_physical_actor"] = True, who
            s["dynamic_contact_speed"] = speed           # 碰上那一刻机器人多快(平移 + 角点线速度)
            s["dynamic_contact_after_5cm_s"] = t - s["_t5"]   # 从进 5 cm 到碰上隔了多久
            s["dynamic_contact_cmd"] = cmd                  # 碰上时下发的 (vx, wz):0 = 守卫已经叫停
        if dmin < 0.05:
            s["dynamic_under_5cm_s"] += dt
        if dmin < 0.10:
            s["dynamic_under_10cm_s"] += dt

    def result(self) -> dict:
        out = {}
        for k, v in self.s.items():
            if k.startswith("_"):
                continue
            out[k] = (None if isinstance(v, float) and not math.isfinite(v)
                      else round(v, 3) if isinstance(v, float) else v)
        return out
