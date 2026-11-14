#!/usr/bin/env python3
"""仿真里的代理守卫:Nav2 的速度先过一遍**正式代码**的守卫,再发给机器人。

现场(11-05 广场窄缝)机器人卡住,主因是代理的守卫一直拦 Nav2 的速度;只跑 Nav2 的仿真复现不出来。
这里把 ``nexwar_agent.obstacles`` 的 ObstacleView / ObstacleGuard 原样接进来,外加
``bridges/nav2_nav.py`` 里每拍速度要过的几道(同样的常数):

1. 小速度整形(运控死区):前进 < 0.13 m/s 抬到 0.13 或归零,原地转 < 0.15 rad/s 同理;
2. 原地转扫过地图上的墙 → 不转(``_turn_hits_map``,用 Nav2 那张图);
3. 守卫:扫过区有挡 → 停;只有「看不见」→ 快于 0.3 m/s 先降到 0.3 再查一遍,还不行也放行
   (跟正式代码一样:看不见只降速,挡才停)。

也接了「看得清就快」(``_vis_cap``,常数从 ``nav2_nav.py`` 源码读,跟正式代码一致)。
没接的:禁行区边上的刹车(``_backstop_to``)、贴边卡住(``_edge_stuck``)。

**守卫模式**(``--mode``,11-07 A/B/C 对比):

- **A** 现在的:扫过区(往前推「延迟 + 刹停 + 0.3 m」)有挡 → 停;只有看不见 → 降到 0.3 再查。
- **B** 软守卫:多留的那段跟速度挂钩(蠕行 0.2 m/s 时 0.05 m、0.6 m/s 以上 0.3 m;原地转的多留角度同理
  0.05–0.2 rad),输出三级 —— 放行 / 减速(同比例压前进和转向,走的还是 Nav2 那条弯)/ 停。
  挡的全是地图上的墙(离墙 ≤ 0.2 m)才许降到 0.3、0.2 再查;有地图之外的东西(人、箱子会动)照旧停。
- **D** 组合(11-07 A/B/C 跑完后加):先按 A 的全余量查;挡的全是地图上的墙 → 走 B 的软处理
  (按 B 的余量在当前速度查,不行再降到 0.3、0.2);有地图之外的东西 → 停(人、车按 A 的全余量)。
- **N** 不开守卫:只做正式代码里一直有的死区整形(横移原样转发,给全向那组用)。
- **C** 只管紧急停:只按刹停距离推(不多留),只有真看到挡才停,看不见的不管。
- ``--delay-ms``:守卫收到的栅格是这么久以前的世界(感知延迟)。

**感知栅格按真机造**(跟感知节点一样 0.1 m、80×80、10 Hz,行 = 朝前、列 = 朝左):前后两台半球雷达
装在机身 x = ±0.404 m、离地 0.47 m,各看自己那半边(前雷达看 x > 0.404,后雷达看 x < −0.404),
**机身两侧 |x| ≤ 0.404 那条带永远看不见** —— 转身、贴着走时靠守卫的 10 s 记忆。遮挡:从雷达到格子
中心的二维连线先碰到别的墙,这一格就看不见(墙 1 m 高,雷达 0.47 m 高,墙后的地面看不到)。
墙 = case.json 的 collision_obstacles + 行人/车辆(/nav_bench/actors)。

话题:收 /cmd_vel_nav(控制器、脱困动作的速度)、/odom、/clock、/nav_bench/actors;发 /cmd_vel。
拦截记到 ``--log``(每行一个 JSON)。
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
for p in ("packages/contract/src", "packages/robot-agent/src"):
    sys.path.insert(0, str(ROOT / p))

from nexwar_agent.obstacles import ObstacleGuard, ObstacleView  # noqa: E402
from nexwar_contract.obsbridge import Grid, pack_bits  # noqa: E402

RES, SIZE = 0.1, 80
LIDAR_X = 0.4043
#: 模式名带 C 后缀(DC / DE3C):照 C40221 实测(obs-3f4)的锥形视野 —— 机头 / 机尾外 ±0.6 m,往外每米
#: 加宽 0.9 m,两侧看不见。不带就是老的「前后两个半平面」(比真机多看见两侧)。
CONE = False


def cone_mask(lx, ly):
    """机身系的点在不在前 / 后雷达的视野锥里(跟正式代码 OCC_FOV_HALF_M / OCC_FOV_SLOPE 一样)。"""
    return np.abs(ly) <= 0.6 + 0.9 * np.maximum(np.abs(lx) - 0.465, 0.0)
MIN_TRAVEL_MPS, MIN_TURN_RPS, DEBAND_FLOOR = 0.13, 0.15, 0.03
UNKNOWN_SLOW_MPS = 0.3
TURN_VX = 0.05

# 软守卫(B):多留的距离、角度随速度从蠕行时的最小值涨到 A 的值
# 蠕行 0.2 m/s:真机前进 0.13 以下只踏步(10-29 实测),0.15 离死区太近
V_CREEP, V_FULL = 0.2, 0.6
EXTRA_MIN, EXTRA_RAD_MIN = 0.05, 0.05
W_CREEP, W_FULL = 0.15, 0.6
SLOW_STEPS = (0.3, V_CREEP)


def _prod_consts() -> dict:
    """正式代码 ``bridges/nav2_nav.py`` 里「看得清就快」用的常数(按源码读,跟它一致)。"""
    import ast
    src = (ROOT / "packages/robot-agent/src/nexwar_agent/bridges/nav2_nav.py").read_text(encoding="utf-8")
    want = {"V_FAST", "V_BASE", "VIS_SLOW_MPS", "VIS_LOOK_M", "VIS_SIDE_M", "VIS_TIERS", "STATIC_NEAR_M",
            "FRONT_BLIND_M", "CLEAR_MARGIN_M"}
    out: dict = {}
    for node in ast.parse(src).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            if name in want:
                v = node.value
                if isinstance(v, ast.Name) and v.id in out:
                    out[name] = out[v.id]
                else:
                    out[name] = ast.literal_eval(ast.parse(ast.unparse(v), mode="eval").body) \
                        if not isinstance(v, ast.Tuple) else _tuple(v, out)
    missing = want - set(out)
    if missing:
        raise SystemExit(f"nav2_nav.py 里找不到 {missing}")
    return out


def _tuple(v, known):
    import ast
    def ev(n):
        if isinstance(n, ast.Tuple):
            return tuple(ev(e) for e in n.elts)
        if isinstance(n, ast.Name):
            return known[n.id]
        return ast.literal_eval(n)
    return ev(v)


def soft_guard(vx: float, wz: float) -> ObstacleGuard:
    fv = min(1.0, max(0.0, (abs(vx) - V_CREEP) / (V_FULL - V_CREEP)))
    fw = min(1.0, max(0.0, (abs(wz) - W_CREEP) / (W_FULL - W_CREEP)))
    return ObstacleGuard(extra=EXTRA_MIN + (0.3 - EXTRA_MIN) * fv,
                         extra_rad=EXTRA_RAD_MIN + (0.2 - EXTRA_RAD_MIN) * fw)


def _deband(vx: float, wz: float) -> tuple[float, float]:
    if 0.0 < abs(vx) < MIN_TRAVEL_MPS:
        vx = 0.0 if abs(vx) < DEBAND_FLOOR else math.copysign(MIN_TRAVEL_MPS, vx)
    if vx == 0.0 and 0.0 < abs(wz) < MIN_TURN_RPS:
        wz = 0.0 if abs(wz) < DEBAND_FLOOR else math.copysign(MIN_TURN_RPS, wz)
    return vx, wz


class SimPerception:
    """世界里的长方形障碍 → 真机那样的 (挡, 看见过) 栅格。"""

    def __init__(self, boxes: list[dict]):
        b = np.array([[o["x"] - o["sx"] / 2, o["x"] + o["sx"] / 2, o["y"] - o["sy"] / 2, o["y"] + o["sy"] / 2]
                      for o in boxes] or np.zeros((0, 4)), dtype=float)
        self.static = b
        n = SIZE
        c = (np.arange(n) - n / 2 + 0.5) * RES
        self.lx = np.repeat(c, n)              # 行 → x(朝前)
        self.ly = np.tile(c, n)                # 列 → y(朝左)

    def grid(self, pose: tuple[float, float, float], actors: list[list[float]]) -> tuple[bytes, bytes]:
        x, y, th = pose
        boxes = self.static
        if actors:
            boxes = np.vstack([boxes, np.array(actors, dtype=float)])
        # 只留 7 m 内的
        near = ((boxes[:, 1] > x - 7) & (boxes[:, 0] < x + 7) & (boxes[:, 3] > y - 7) & (boxes[:, 2] < y + 7))
        B = boxes[near]
        c, s = math.cos(th), math.sin(th)
        wx = x + c * self.lx - s * self.ly
        wy = y + s * self.lx + c * self.ly
        n_cells = len(wx)
        inside = np.zeros(n_cells, dtype=bool)
        for x0, x1, y0, y1 in B:
            # 格子跟墙有重叠就算挡(雷达打在墙面上,回波落在墙面那一格;按格心判会把它漏掉)
            h = RES / 2
            inside |= (wx + h >= x0) & (wx - h <= x1) & (wy + h >= y0) & (wy - h <= y1)
        known = np.zeros(n_cells, dtype=bool)
        for sign in (1.0, -1.0):                       # 前雷达、后雷达
            fov = sign * self.lx > LIDAR_X
            if CONE:
                fov &= cone_mask(self.lx, self.ly)
            if not fov.any():
                continue
            sx, sy = x + c * sign * LIDAR_X, y + s * sign * LIDAR_X
            dx, dy = wx[fov] - sx, wy[fov] - sy
            # 每条连线跟每个长方形的第一次相交参数 t(slab 法);t < 1 - 一格 = 中途被挡
            tmin = np.full(len(dx), np.inf)
            with np.errstate(divide="ignore", invalid="ignore"):
                for x0, x1, y0, y1 in B:
                    tx0, tx1 = (x0 - sx) / dx, (x1 - sx) / dx
                    ty0, ty1 = (y0 - sy) / dy, (y1 - sy) / dy
                    tn = np.maximum(np.minimum(tx0, tx1), np.minimum(ty0, ty1))
                    tf = np.minimum(np.maximum(tx0, tx1), np.maximum(ty0, ty1))
                    hit = (tn <= tf) & (tf >= 0) & (tn <= 1)
                    tmin = np.where(hit, np.minimum(tmin, np.maximum(tn, 0.0)), tmin)
            L = np.hypot(dx, dy)
            # 挡的格子:连线进墙的地方离格子中心不超过一格半(打在墙面上那一层看得见)
            clear_to_center = ~np.isfinite(tmin) | (tmin >= 1.0)
            vis = np.where(inside[fov], clear_to_center | ((1.0 - tmin) * L <= 1.5 * RES), clear_to_center)
            known[np.nonzero(fov)[0][vis]] = True
        occ = inside & known
        return occ.astype(np.uint8).tobytes(), known.astype(np.uint8).tobytes()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", required=True)
    ap.add_argument("--log", default="")
    # 实验:离地图上的墙近(车身外沿 < TIGHT_M)= 窄处:限速 TIGHT_V,守卫往前多留的从 0.3 降到 TIGHT_EXTRA
    ap.add_argument("--tight", default="false")
    ap.add_argument("--mode", default="A", choices=("A", "B", "C", "D", "DE1", "DE2", "DE3", "DC", "DE3C", "DE4C", "DE5C", "N"))
    ap.add_argument("--delay-ms", type=float, default=0.0)
    args = ap.parse_args()
    K = _prod_consts()
    mode = args.mode
    occ_algo = ""
    global CONE
    if mode.startswith("D") and mode.endswith("C"):
        CONE, mode = True, mode[:-1]
    if mode.startswith("D") and len(mode) > 1:          # DE1 / DE2 = D + 遮挡限速(11-07,导航 V1 设计第 1 节)
        mode, occ_algo = "D", mode[1:]
    case = json.loads(Path(args.case).read_text(encoding="utf-8"))
    case_dir = Path(args.case).parent
    actors_cfg = case.get("actors") or []

    import yaml
    from PIL import Image
    my = yaml.safe_load((case_dir / "map.yaml").read_text())
    blocked = np.array(Image.open(case_dir / my["image"]))[::-1] < 100     # 行从下往上
    mres, morg = float(my["resolution"]), my["origin"]

    import rclpy
    from geometry_msgs.msg import PoseArray, Twist
    from nav_msgs.msg import Odometry
    from rclpy.node import Node
    from rosgraph_msgs.msg import Clock

    rclpy.init()
    node = Node("nav_bench_agent_guard")
    pub = node.create_publisher(Twist, "/cmd_vel", 10)
    st = {"now": None, "pose": None, "v": 0.0, "w": 0.0, "last_wz": 0.0, "last_vx": 0.0,
          "actors": [], "seq": 0,
          "blocked_ticks": 0, "ticks": 0, "tight_ticks": 0, "turn_map_ticks": 0, "slowed_ticks": 0,
          "soft_slow_ticks": 0, "vis_capped_ticks": 0, "occ_capped_ticks": 0, "hist": []}
    log = open(args.log, "a", encoding="utf-8") if args.log else None
    view = ObstacleView(monotonic=lambda: st["now"] or 0.0)
    view.on_connect()
    guard = ObstacleGuard()
    tight_on = args.tight.lower() == "true"
    tight_guard = ObstacleGuard(extra=0.1)
    TIGHT_M, TIGHT_V = 0.45, 0.15
    from scipy import ndimage
    dist_map = ndimage.distance_transform_edt(~blocked) * mres          # 每格离最近的挡多远(米)
    from goal_driver import _corners

    def map_clearance(pose):
        poly = _corners(*pose)
        best = math.inf
        hgt, wid = dist_map.shape
        for i in range(4):
            (x1, y1), (x2, y2) = poly[i], poly[(i + 1) % 4]
            for k in range(12):
                x_, y_ = x1 + (x2 - x1) * k / 12, y1 + (y2 - y1) * k / 12
                r, kk = int((y_ - morg[1]) / mres), int((x_ - morg[0]) / mres)
                if 0 <= r < hgt and 0 <= kk < wid:
                    best = min(best, dist_map[r, kk])
        return best
    perc = SimPerception(case.get("collision_obstacles", case.get("obstacles", [])))

    def note(kind: str, reason: str) -> None:
        if log:
            p = st["pose"]
            log.write(json.dumps({"t": round(st["now"] or 0.0, 2), "kind": kind, "reason": reason,
                                  "pose": [round(v, 3) for v in p] if p else None}, ensure_ascii=False) + "\n")
            log.flush()

    def on_clock(m):
        st["now"] = m.clock.sec + m.clock.nanosec / 1e9

    def on_odom(m):
        p, q = m.pose.pose.position, m.pose.pose.orientation
        yaw = math.atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z))
        st["pose"] = (p.x, p.y, yaw)
        st["v"], st["w"] = m.twist.twist.linear.x, m.twist.twist.angular.z
        if st["now"] is not None:
            view.note_odom(p.x, p.y, yaw)

    def on_actors(m):
        out = []
        for i, ps in enumerate(m.poses[:len(actors_cfg)]):
            a = actors_cfg[i]
            hx, hy = float(a["sx"]) / 2, float(a["sy"]) / 2
            out.append([ps.position.x - hx, ps.position.x + hx, ps.position.y - hy, ps.position.y + hy])
        st["actors"] = out

    def tick_grid():
        if st["now"] is None or st["pose"] is None:
            return
        st["hist"].append((st["now"], st["pose"], st["actors"]))
        d = args.delay_ms / 1000.0
        while len(st["hist"]) > 1 and st["hist"][1][0] <= st["now"] - d:
            st["hist"].pop(0)
        _, pose_d, actors_d = st["hist"][0] if d > 0 else (None, st["pose"], st["actors"])
        occ, known = perc.grid(pose_d, actors_d)
        st["seq"] += 1
        g = Grid(seq=st["seq"], stamp_ns=int(st["now"] * 1e9), res=RES, size=SIZE,
                 occ=pack_bits(occ, SIZE), known=pack_bits(known, SIZE), rear=True, rear_cal=True)
        view.on_grid(g)

    def turn_hits_map(vx: float, wz: float, g: ObstacleGuard) -> bool:
        if abs(vx) > TURN_VX or abs(wz) < 1e-6 or st["pose"] is None:
            return False
        x, y, th = st["pose"]
        c, s = math.cos(th), math.sin(th)
        h, w = blocked.shape
        for px, py in g.swept(0.0, wz, 0.0, (st["last_wz"], st["w"])):
            mx, my_ = x + c * px - s * py, y + s * px + c * py
            r, k = int((my_ - morg[1]) // mres), int((mx - morg[0]) // mres)
            if 0 <= r < h and 0 <= k < w and blocked[r, k]:
                return True
        return False

    def near_static_map(xs, ys) -> np.ndarray:
        """地图坐标的点 → 离地图上的墙 STATIC_NEAR_M 以内(仿真里里程系 = 地图系)。"""
        hgt, wid = dist_map.shape
        r = np.floor((np.asarray(ys) - morg[1]) / mres).astype(int)
        k = np.floor((np.asarray(xs) - morg[0]) / mres).astype(int)
        inb = (r >= 0) & (r < hgt) & (k >= 0) & (k < wid)
        out = np.zeros(len(r), dtype=bool)
        out[inb] = dist_map[r[inb], k[inb]] <= K["STATIC_NEAR_M"]
        return out

    def hits_all_static(hits) -> bool:
        x, y, th = st["pose"]
        c, s = math.cos(th), math.sin(th)
        P = np.asarray(hits, dtype=float)
        return bool(near_static_map(x + c * P[:, 0] - s * P[:, 1], y + s * P[:, 0] + c * P[:, 1]).all())

    def vis_cap(travel: int) -> float:
        """正式代码 ``_vis_cap`` 的同一套算法(看得清多远 + 地图之外的东西多近)。"""
        if not view.frames or view.age() > 0.3:
            return K["V_BASE"]
        f = view.frames[0]
        n, res = f.size, f.res
        cc = (np.arange(n) - n / 2 + 0.5) * res
        occ = f.occ.reshape(n, n).astype(bool)
        known = f.known.reshape(n, n).astype(bool)
        sgn = 1.0 if travel >= 0 else -1.0
        X = np.broadcast_to(cc[:, None] * sgn, (n, n))
        Y = np.broadcast_to(cc[None, :], (n, n))
        hl, hw = guard.body_len / 2 + guard.margin, guard.body_wid / 2 + guard.margin
        corr = (np.abs(Y) <= hw) & (X > hl)
        bad = corr & (occ | (~known & (X > hl + K["FRONT_BLIND_M"])))
        clear = float(X[bad].min() - hl) if bad.any() else float(X[corr].max() - hl)
        a, t = guard.decel, guard.latency
        room = clear - K["CLEAR_MARGIN_M"]
        v_clear = a * (-t + math.sqrt(t * t + 2.0 * room / a)) if room > 0 else 0.0
        v_dyn = K["V_FAST"]
        zone = occ & (X > hl - 0.2) & (X <= hl + K["VIS_LOOK_M"]) & (np.abs(Y) <= hw + K["VIS_SIDE_M"])
        if zone.any():
            xs, ys = X[zone] * sgn, Y[zone]
            dist = np.hypot(np.maximum(np.abs(X[zone]) - hl, 0.0), np.maximum(np.abs(ys) - hw, 0.0))
            fx, fy, fyaw = f.pose
            c, s = math.cos(fyaw), math.sin(fyaw)
            dyn = ~near_static_map(fx + c * xs - s * ys, fy + s * xs + c * ys)
            if dyn.any():
                d = float(dist[dyn].min())
                v_dyn = next((v for near, v in K["VIS_TIERS"] if d < near), K["V_FAST"])
        return max(min(K["V_FAST"], v_clear, v_dyn), K["VIS_SLOW_MPS"])

    def emergence(f, sgn):
        """可能冒出东西的格子:看不见、不在墙里、跟机身走廊之间横向没有挡(感知的挡或地图墙)。
        返回 (x 机头前多远, g 离走廊边横向多远) 两个数组。"""
        n, res = f.size, f.res
        cc = (np.arange(n) - n / 2 + 0.5) * res
        occ = f.occ.reshape(n, n).astype(bool)
        known = f.known.reshape(n, n).astype(bool)
        fx, fy, fyaw = f.pose
        c, s_ = math.cos(fyaw), math.sin(fyaw)
        XX, YY = np.meshgrid(cc, cc, indexing="ij")              # 行 = 朝前,列 = 朝左(拍下时机身系)
        mx, my_ = fx + c * XX - s_ * YY, fy + s_ * XX + c * YY
        hgt, wid = dist_map.shape
        r = np.floor((my_ - morg[1]) / mres).astype(int)
        k = np.floor((mx - morg[0]) / mres).astype(int)
        inb = (r >= 0) & (r < hgt) & (k >= 0) & (k < wid)
        wall = np.ones((n, n), dtype=bool)
        wall[inb] = dist_map[r[inb], k[inb]] <= 0.05
        shield = occ | wall
        hl, hw = guard.body_len / 2 + guard.margin, guard.body_wid / 2 + guard.margin
        X = XX * sgn
        gap = np.abs(YY) - hw
        jl = int(np.searchsorted(cc, hw))                         # 左边第一列在走廊外
        jr = int(np.searchsorted(cc, -hw)) - 1                    # 右边第一列在走廊外
        sh = np.zeros((n, n), dtype=bool)                         # 这一格到走廊边之间(含)有挡
        sh[:, jl:] = np.logical_or.accumulate(shield[:, jl:], axis=1)
        sh[:, :jr + 1] = np.logical_or.accumulate(shield[:, :jr + 1][:, ::-1], axis=1)[:, ::-1]
        em = (~known) & (~sh) & (gap > 0) & (X > hl + 0.05)   # 机头前:前雷达看得到的半球里看不见 = 被挡住的阴影
        if CONE:
            # E2/E3:跟正式代码一样,只算视野锥里的阴影;最近 2 s 见过的不算。
            # E4/E5:机身两侧的盲区也算(人从侧面盲区横穿到机头前),最近 2 s / 4 s 见过的不算
            mem = {"E4": 2.0, "E5": 4.0}.get(occ_algo, 2.0)
            if occ_algo not in ("E4", "E5"):
                em &= cone_mask(XX, YY)
            if em.any():
                ii, jj = np.nonzero(em)
                pts = list(zip(XX[ii, jj].tolist(), YY[ii, jj].tolist(), strict=True))
                _, unknown = view.lookup(pts, f.pose, max_age=mem)
                em = np.zeros_like(em)
                if unknown:
                    u = np.asarray(unknown)
                    em[ii[u], jj[u]] = True
        return np.maximum(X[em] - hl, 0.0), gap[em]

    def occ_cap(travel: int) -> float:
        """遮挡限速。E1:按冒出点离机身的距离分档;E2:按「反应 + 刹车」在冒出点之前停得住。"""
        if not occ_algo or not view.frames or view.age() > 0.3:
            return K["V_FAST"]
        x, gp = emergence(view.frames[0], 1.0 if travel >= 0 else -1.0)
        if occ_algo == "E1":
            sel = gp <= 1.5
            if not sel.any():
                return K["V_FAST"]
            d = float(np.hypot(x[sel], gp[sel]).min())
            return 0.2 if d < 1.0 else 0.4 if d < 2.0 else K["V_FAST"]
        # E3 = E2 看得更宽:DE2 ab_parking s33 人从车后横向 1.46 m 处冒出(1.0 m 以外不看,没限速)
        sel = gp <= (2.0 if occ_algo in ("E3", "E4", "E5") else 1.0)
        if not sel.any():
            return K["V_FAST"]
        room = float(x[sel].min()) - 0.1
        a, t = guard.decel, 0.5
        v = a * (-t + math.sqrt(t * t + 2.0 * room / a)) if room > 0 else 0.0
        return max(v, V_CREEP)

    def check(g: ObstacleGuard, vx: float, wz: float):
        return g.check(vx, wz, st["v"], view, st["pose"], w_now=(st["last_wz"], st["w"]),
                       moving=((st["last_vx"], st["last_wz"]), (st["v"], st["w"])))

    def send(vx: float, wz: float, vy: float = 0.0) -> None:
        t = Twist()
        t.linear.x, t.linear.y, t.angular.z = float(vx), float(vy), float(wz)
        pub.publish(t)
        st["last_wz"], st["last_vx"] = wz, vx

    def on_cmd(m):
        if st["pose"] is None or st["now"] is None:
            send(0.0, 0.0)
            return
        st["ticks"] += 1
        vx, wz = m.linear.x, m.angular.z
        if mode == "N":
            vx, wz = _deband(vx, wz)
            send(vx, wz, m.linear.y)
            return
        # 看得清就快:前进、转向同比例压(正式代码在整形、守卫之前做)
        cap = vis_cap(1 if vx >= 0 else -1)
        oc = occ_cap(1 if vx >= 0 else -1)
        if oc < cap:
            cap = oc
            st["occ_capped_ticks"] += 1
        if abs(vx) > cap:
            k = cap / abs(vx)
            vx, wz = vx * k, wz * k
            st["vis_capped_ticks"] += 1
        g = guard
        if mode == "B":
            g = soft_guard(vx, wz)
        elif mode == "C":
            g = ObstacleGuard(extra=0.0, extra_rad=0.0)
        if tight_on and map_clearance(st["pose"]) < TIGHT_M:
            g = tight_guard
            if abs(vx) > TIGHT_V:                      # 前进、转向同比例压(跟正式代码一样走同一条弯)
                k = TIGHT_V / abs(vx)
                vx, wz = vx * k, wz * k
            st["tight_ticks"] += 1
        vx, wz = _deband(vx, wz)
        if mode == "B":
            g = soft_guard(vx, wz)
        if turn_hits_map(vx, wz, g):
            st["turn_map_ticks"] += 1
            note("turn_map", "原地转会扫到地图上的墙(窄处不转)")
            send(0.0, 0.0)
            return
        if abs(vx) > 1e-6 or abs(wz) > 1e-6:
            v = check(g, vx, wz)
            if mode == "C" and not v.ok and not v.hits and "障碍数据" not in v.reason:
                send(vx, wz)                            # 只管紧急停:看不见的不管
                return
            if not v.ok and not v.hits and "障碍数据" not in v.reason and abs(vx) > UNKNOWN_SLOW_MPS:
                k = UNKNOWN_SLOW_MPS / abs(vx)
                vx = math.copysign(UNKNOWN_SLOW_MPS, vx)
                if mode in ("B", "D"):                  # B/D:同比例压,走同一条弯
                    wz *= k
                    if mode == "B":
                        g = soft_guard(vx, wz)
                st["slowed_ticks"] += 1
                v = check(g, vx, wz)
            if mode in ("B", "D") and not v.ok and v.hits and hits_all_static(v.hits):
                # 挡的全是地图上的墙:降速、少留,再查(墙不会动);人、箱子照旧停
                lead = abs(vx) if abs(vx) > 1e-6 else abs(wz)
                steps = ((lead,) if mode == "D" else ()) + SLOW_STEPS   # D:先按 B 的余量在原速试
                for i, target in enumerate(steps):
                    if lead <= target + 1e-9 and not (mode == "D" and i == 0):
                        continue
                    k = target / lead
                    v2x, v2z = _deband(vx * k, wz * k)
                    g2 = soft_guard(v2x, v2z)
                    if turn_hits_map(v2x, v2z, g2):
                        continue
                    v2 = check(g2, v2x, v2z)
                    if v2.ok or (not v2.hits and "障碍数据" not in v2.reason):
                        st["soft_slow_ticks"] += 1
                        send(v2x, v2z)
                        return
            if not v.ok and (v.hits or "障碍数据" in v.reason):
                st["blocked_ticks"] += 1
                note("guard", v.reason)
                send(0.0, 0.0)
                return
        send(vx, wz)

    node.create_subscription(Clock, "/clock", on_clock, 10)
    node.create_subscription(Odometry, "/odom", on_odom, 20)
    node.create_subscription(PoseArray, "/nav_bench/actors", on_actors, 10)
    node.create_subscription(Twist, "/cmd_vel_nav", on_cmd, 20)
    node.create_timer(0.1, tick_grid)
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if log:
            log.write(json.dumps({"summary": {k: st[k] for k in ("ticks", "tight_ticks", "blocked_ticks", "turn_map_ticks",
                                                                  "slowed_ticks", "soft_slow_ticks",
                                                                  "vis_capped_ticks", "occ_capped_ticks")}}) + "\n")
            log.close()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
