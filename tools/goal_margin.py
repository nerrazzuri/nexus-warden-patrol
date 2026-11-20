"""查一个航点在地图上「离墙余量」是怎么算出来的(路线检查 ``route_check.pose_margins`` 同一个算法)。

报:按现在的规矩(未知格、占用格都算墙)的余量,是哪一格卡住的(地图系坐标、像素值:0 黑 = 占用,
205 灰 = 未知),只算占用格时的余量;这个点换朝向、附近挪一挪能到多少。

用法(装了仓库的机器,不要 ROS)::

    PYTHONPATH=packages/robot-agent/src:packages/contract/src \\
        python3 tools/goal_margin.py <地图目录(有 floor.pgm / floor.yaml)> 7.36 5.61 0.09
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("map_dir", type=Path)
    p.add_argument("x", type=float)
    p.add_argument("y", type=float)
    p.add_argument("yaw", type=float)
    a = p.parse_args(argv)

    import numpy as np

    from nexwar_agent import route_check as rc
    from nexwar_contract.footprint import BASE_HALF_LEN, BASE_HALF_WID, ROUTE_MARGIN_MIN
    from nexwar_contract.planning.costmap import load_floor, parse_pgm, parse_yaml

    free, res, origin = load_floor(a.map_dir)
    walls = ~np.asarray(free, dtype=bool)
    meta = parse_yaml((a.map_dir / "floor.yaml").read_text(encoding="utf-8"))
    img = np.flipud(parse_pgm((a.map_dir / "floor.pgm").read_bytes()))
    occ = img.astype(np.float32) / 255.0
    if not meta["negate"]:
        occ = 1.0 - occ
    occupied = occ > meta["occupied_thresh"]
    ox, oy = float(origin[0]), float(origin[1])
    pose = (a.x, a.y, a.yaw)
    m_all = float(rc.pose_margins([pose], walls, res, (ox, oy))[0])
    m_occ = float(rc.pose_margins([pose], occupied, res, (ox, oy))[0])
    print(f"地图 {a.map_dir}:分辨率 {res} m;车身(含基础余量)半长 {BASE_HALF_LEN:.3f}、"
          f"半宽 {BASE_HALF_WID:.3f};要求每边 ≥ {ROUTE_MARGIN_MIN:.2f} m")
    print(f"({a.x:.2f}, {a.y:.2f}, 朝向 {a.yaw:.2f}):余量 {m_all:.3f} m"
          f"(未知、占用都算墙,现在的规矩);只算占用格 {m_occ:.3f} m")
    # 卡住的那几格
    c, s = math.cos(a.yaw), math.sin(a.yaw)
    rr, kk = np.nonzero(walls)
    cx = ox + (kk + 0.5) * res - a.x
    cy = oy + (rr + 0.5) * res - a.y
    near = np.hypot(cx, cy) < 1.5
    rr, kk, cx, cy = rr[near], kk[near], cx[near], cy[near]
    lx, ly = np.abs(c * cx + s * cy), np.abs(-s * cx + c * cy)
    need = np.maximum(lx - BASE_HALF_LEN, ly - BASE_HALF_WID) - res / 2
    order = np.argsort(need)[:5]
    print("最近的 5 格墙(余量从小到大):")
    for i in order:
        v = int(img[rr[i], kk[i]])
        kind = "占用(黑)" if occupied[rr[i], kk[i]] else f"未知(灰 {v})"
        print(f"  ({ox + (kk[i] + 0.5) * res:.2f}, {oy + (rr[i] + 0.5) * res:.2f})  {kind}  "
              f"余量 {need[i]:.3f}  车身系 前 {c * cx[i] + s * cy[i]:+.2f} 左 "
              f"{-s * cx[i] + c * cy[i]:+.2f}")
    best = max(((float(rc.pose_margins([(a.x, a.y, y)], walls, res, (ox, oy))[0]), y)
                for y in np.linspace(-math.pi, math.pi, 73)), key=lambda t: t[0])
    print(f"同一个位置换朝向:最好 {best[0]:.3f} m(朝向 {best[1]:.2f})")
    cand = []
    for dx in np.arange(-0.3, 0.31, 0.05):
        for dy in np.arange(-0.3, 0.31, 0.05):
            for y in (a.yaw, best[1]):
                q = (a.x + dx, a.y + dy, y)
                cand.append((float(rc.pose_margins([q], walls, res, (ox, oy))[0]), q))
    m, q = max(cand, key=lambda t: t[0])
    print(f"附近 ±0.3 m 挪一挪:最好 {m:.3f} m 在 ({q[0]:.2f}, {q[1]:.2f}, 朝向 {q[2]:.2f})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
