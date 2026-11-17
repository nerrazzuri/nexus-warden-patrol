"""定位地图去动态点:一块地方的点为什么没删(Top Glove 11-17 西边拖影)。

先建图时设 ``NEXWAR_DENOISE_DUMP=/tmp/dn.npz`` 存下每个点的计数,再:

    python3 tools/denoise_why.py /tmp/dn.npz --box X0 X1 Y0 Y1   # 地图平面坐标(米),跟网页上一样

按 ``mapclean`` 的规矩(依次)数:删了的;贴地(离地不到 FLOOR_KEEP_M,不按射线删);射线没穿过几帧
(< PASS_MIN);穿过的不够打中的 PASS_PER_HIT 倍;离地多高不知道的。再给穿过、打中、离地的分位数。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

_ROOT = Path(__file__).resolve().parents[1]
for _pkg in ("localizer", "contract"):              # 笔记本 11-17:光有 localizer 缺 contract
    sys.path.insert(0, str(_ROOT / "packages" / _pkg / "src"))
from nexwar_localizer import mapclean as C  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("dump", type=Path)
    ap.add_argument("--box", type=float, nargs=4, metavar=("X0", "X1", "Y0", "Y1"), required=True)
    a = ap.parse_args()
    d = np.load(a.dump)
    x0, x1, y0, y1 = a.box
    p = d["plane"]
    m = (p[:, 0] >= x0) & (p[:, 0] <= x1) & (p[:, 1] >= y0) & (p[:, 1] <= y1)
    n = int(m.sum())
    print(f"框里 {n} 个点(整张 {len(p)};逐帧扫描 {int(d['scans'])} 帧)")
    if not n:
        return 1
    ps, hs, h, dyn = d["passes"][m], d["hits"][m], d["height"][m], d["dynamic"][m]
    left = ~dyn
    rows = [("删了", dyn)]
    for name, cond in (("离地多高不知道", ~np.isfinite(h)),
                       (f"贴地(< {C.FLOOR_KEEP_M} m)", np.isfinite(h) & (h < C.FLOOR_KEEP_M)),
                       (f"射线穿过不到 {C.PASS_MIN} 帧", ps < C.PASS_MIN),
                       (f"穿过不到打中的 {C.PASS_PER_HIT:g} 倍", ps < C.PASS_PER_HIT * hs)):
        hit = left & cond
        rows.append((name, hit))
        left = left & ~cond
    rows.append(("别的(该删没删?)", left))
    for name, r in rows:
        print(f"  {name:22s} {int(r.sum()):7d}  {r.mean():6.1%}")
    for name, v in (("穿过帧数", ps), ("打中帧数", hs), ("离地 m", h[np.isfinite(h)])):
        if len(v):
            q = np.percentile(v, [10, 50, 90])
            print(f"  {name}:10% {q[0]:.2f} / 中位 {q[1]:.2f} / 90% {q[2]:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
