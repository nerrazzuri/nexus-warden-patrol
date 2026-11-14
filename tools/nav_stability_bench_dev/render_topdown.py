#!/usr/bin/env python3
"""把一次场景运行的录包画成俯视视频(现场地图、行人车辆、地图上没有的障碍都画)(PIL 画帧,管道给 ffmpeg)。

用法: render.py <run_dir> <out.mp4> <标题>
画:墙/障碍(灰)、目标车身(绿虚线)、机器人车身(蓝)、走过的轨迹、Nav2 规划路径(橙)、雷达点(红)。
"""
import json
import pathlib
import math
import subprocess
import sys
from pathlib import Path

import rosbag2_py
from geometry_msgs.msg import PoseArray
from nav_msgs.msg import Odometry, Path as NavPath
from PIL import Image, ImageDraw, ImageFont
from safety_geom import BASE_HX, BASE_HY
from rclpy.serialization import deserialize_message
from sensor_msgs.msg import LaserScan

run, out_mp4, title = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
case = json.loads((run / "case.json").read_text())
metrics = json.loads((run / "metrics.json").read_text())

r = rosbag2_py.SequentialReader()
r.open(rosbag2_py.StorageOptions(uri=str(run / "bag"), storage_id="sqlite3"), rosbag2_py.ConverterOptions("", ""))
odom, plans, scans, crowd = [], [], [], []
while r.has_next():
    topic, data, t = r.read_next()
    if topic == "/odom":
        m = deserialize_message(data, Odometry)
        p, q = m.pose.pose.position, m.pose.pose.orientation
        odom.append((t, p.x, p.y, math.atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z))))
    elif topic == "/plan":
        m = deserialize_message(data, NavPath)
        plans.append((t, [(ps.pose.position.x, ps.pose.position.y) for ps in m.poses]))
    elif topic == "/nav_bench/actors":
        m = deserialize_message(data, PoseArray)
        crowd.append((t, [(q.position.x, q.position.y) for q in m.poses]))
    elif topic == "/scan":
        m = deserialize_message(data, LaserScan)
        scans.append((t, m.angle_min, m.angle_increment, list(m.ranges)))
# 从第一次动起来前 1 s 开始画
moving = next((i for i in range(1, len(odom)) if math.hypot(odom[i][1] - odom[0][1], odom[i][2] - odom[0][2]) > 0.02), 0)
t0 = odom[max(0, moving - 50)][0]
t_end = odom[-1][0]

W, H = case.get("map_size_m", [18.0, 18.0])
X0, X1, Y0, Y1 = case.get("map_bounds") or [-W / 2, W / 2, -H / 2, H / 2]
W, H = X1 - X0, Y1 - Y0
SITE = bool(case.get("site_map"))
PX = 40 if SITE else 44                                   # 每米像素
SIZE = int(W * PX)
SIZEH = int(H * PX)
PANEL = 120
FPS, SPEED = 10, 2.0                      # 10 帧/秒,2 倍速


def to_px(x, y):
    return ((x - X0) * PX, (Y1 - y) * PX + PANEL)


def box_poly(b):
    hx, hy = b["sx"] / 2, b["sy"] / 2
    return [to_px(b["x"] - hx, b["y"] - hy), to_px(b["x"] + hx, b["y"] - hy),
            to_px(b["x"] + hx, b["y"] + hy), to_px(b["x"] - hx, b["y"] + hy)]


def body(x, y, yaw, hx=BASE_HX, hy=BASE_HY):
    c, s = math.cos(yaw), math.sin(yaw)
    return [to_px(x + c * lx - s * ly, y + s * lx + c * ly) for lx, ly in ((hx, hy), (hx, -hy), (-hx, -hy), (-hx, hy))]


try:
    font = ImageFont.truetype("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", 22)
    small = ImageFont.truetype("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", 17)
except OSError:
    font = small = ImageFont.load_default()

wall = 0.2
boundary = [{"x": 0, "y": H / 2 - wall / 2, "sx": W, "sy": wall}, {"x": 0, "y": -H / 2 + wall / 2, "sx": W, "sy": wall},
            {"x": W / 2 - wall / 2, "y": 0, "sx": wall, "sy": H}, {"x": -W / 2 + wall / 2, "y": 0, "sx": wall, "sy": H}]
base = Image.new("RGB", (SIZE, SIZEH + PANEL), (250, 250, 248))
d = ImageDraw.Draw(base)
if SITE:
    import numpy as np
    from PIL import Image as _I
    import yaml as _y
    my = _y.safe_load((run / "map.yaml").read_text())
    mg = np.array(_I.open(run / "map.pgm"))[::-1]
    mres, mo = my["resolution"], my["origin"]
    ys, xs = np.nonzero(mg < 100)
    for r_, c_ in zip(ys, xs):
        x_, y_ = mo[0] + c_ * mres, mo[1] + r_ * mres
        if X0 <= x_ <= X1 and Y0 <= y_ <= Y1:
            a_, b_ = to_px(x_, y_ + mres); d.rectangle([a_, b_, a_ + mres * PX, b_ + mres * PX], fill=(222, 222, 222))
    nogo = case["site_map"].get("nogo")
    if nogo:
        root = pathlib.Path(__file__).resolve().parents[2]          # 仓库根
        for z in json.loads((root / nogo).read_text())["zones"]:
            d.polygon([to_px(*pt) for pt in z["points"]], fill=(250, 190, 190), outline=(220, 90, 90))
for i in range(int(W) + 1):                                  # 1 m 网格
    d.line([(i * PX, PANEL), (i * PX, PANEL + SIZEH)], fill=(232, 232, 228))
for j in range(int(H) + 1):
    d.line([(0, PANEL + j * PX), (SIZE, PANEL + j * PX)], fill=(232, 232, 228))
for b in (case["collision_obstacles"] if SITE else boundary + case["obstacles"]):
    if b.get("unmapped"):     # 地图上没有的:黄褐色斜线
        d.polygon(box_poly(b), fill=(214, 170, 60), outline=(150, 110, 20))
    else:
        d.polygon(box_poly(b), fill=(120, 120, 120))
for gi, g in enumerate(case["goals"]):
    pts = body(*g)
    for k in range(4):
        d.line([pts[k], pts[(k + 1) % 4]], fill=(20, 150, 60), width=2)
    gx, gy = to_px(g[0], g[1])
    d.text((gx + 8, gy - 30), f"目标{gi + 1}", fill=(20, 120, 50), font=small)
clear = case.get("pose_clearance_m", {})

ff = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                       "-s", f"{SIZE}x{SIZEH + PANEL}", "-r", str(FPS), "-i", "-", "-c:v", "libx264",
                       "-pix_fmt", "yuv420p", "-crf", "23", str(out_mp4)], stdin=subprocess.PIPE)
oi = pi = si = ci = 0
gidx = 0
actors = case.get("actors") or []
trail = []
step_ns = int(1e9 * SPEED / FPS)
t = t0
dist = 0.0
last = None
while t <= t_end + 2 * step_ns:
    while oi + 1 < len(odom) and odom[oi + 1][0] <= t:
        oi += 1
        o = odom[oi]
        if last:
            dist += math.hypot(o[1] - last[0], o[2] - last[1])
        last = (o[1], o[2])
        trail.append(to_px(o[1], o[2]))
    while pi + 1 < len(plans) and plans[pi + 1][0] <= t:
        pi += 1
    while si + 1 < len(scans) and scans[si + 1][0] <= t:
        si += 1
    while ci + 1 < len(crowd) and crowd[ci + 1][0] <= t:
        ci += 1
    img = base.copy()
    d = ImageDraw.Draw(img)
    if plans and plans[pi][0] <= t and len(plans[pi][1]) > 1:
        d.line([to_px(*p) for p in plans[pi][1]], fill=(240, 140, 20), width=3)
    if len(trail) > 1:
        d.line(trail, fill=(90, 150, 230), width=2)
    _, x, y, yaw = odom[oi]
    if scans and scans[si][0] <= t:
        _, a0, da, rr = scans[si]
        lx, ly = x + 0.40 * math.cos(yaw), y + 0.40 * math.sin(yaw)
        for k, rng in enumerate(rr[::2]):
            if math.isfinite(rng) and 0.08 < rng < 12:
                a = yaw + a0 + 2 * k * da
                px, py = to_px(lx + rng * math.cos(a), ly + rng * math.sin(a))
                d.ellipse([px - 1.5, py - 1.5, px + 1.5, py + 1.5], fill=(220, 40, 40))
    if crowd and crowd[ci][0] <= t:
        for k, (ax, ay) in enumerate(crowd[ci][1][:len(actors)]):
            a = actors[k]
            box = {"x": ax, "y": ay, "sx": float(a["sx"]), "sy": float(a["sy"])}
            col = (240, 130, 30) if a.get("kind", "person") == "person" else (40, 90, 200)
            if a.get("kind", "person") == "person":
                cx, cy = to_px(ax, ay); rr = float(a["sx"]) / 2 * PX
                d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], fill=col, outline=(120, 60, 0))
            else:
                d.polygon(box_poly(box), fill=col, outline=(10, 30, 90))
    d.polygon(body(x, y, yaw), fill=(60, 110, 210), outline=(20, 50, 140))
    hx, hy = to_px(x + 0.45 * math.cos(yaw), y + 0.45 * math.sin(yaw))
    d.ellipse([hx - 4, hy - 4, hx + 4, hy + 4], fill=(255, 255, 255))
    # 顶部信息栏
    d.rectangle([0, 0, SIZE, PANEL], fill=(255, 255, 255))
    d.text((14, 8), title, fill=(30, 30, 30), font=font)
    # 到过当前目标 0.25 m 内就换下一个(录包里没有"到位"事件,按位置推)
    if gidx + 1 < len(case["goals"]) and math.hypot(x - case["goals"][gidx][0], y - case["goals"][gidx][1]) < 0.25:
        gidx += 1
    g = case["goals"][gidx]
    to_goal = math.hypot(x - g[0], y - g[1])
    elapsed = (t - t0) / 1e9
    d.text((14, 44), f"时间 {elapsed:5.1f} s(2 倍速)  已走 {dist:5.1f} m  离目标{gidx + 1} {to_goal:4.2f} m",
           fill=(60, 60, 60), font=small)
    res = "、".join(f"目标{gr['goal'] + 1}:{'到位' if gr.get('success') else {'timeout': '超时没到位'}.get(gr.get('reason'), gr.get('reason', '失败'))}"
                   for gr in metrics["goal_results"])
    hit = metrics.get("actor_hit")
    extra = f"  撞到 {hit}" if hit else ""
    d.text((14, 74), f"结果:{res}{extra}" + (f"  离行人/车辆最近 {metrics.get('min_actor_gap_m') or 0:.2f} m" if actors else ""),
           fill=(60, 60, 60), font=small)
    ff.stdin.write(img.tobytes())
    t += step_ns
ff.stdin.close()
ff.wait()
print(out_mp4, "frames", int((t - t0) / step_ns))
