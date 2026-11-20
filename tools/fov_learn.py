"""从录包学这台机器人的雷达视野表(``/etc/nexwar/fov.json``,见 ``nexwar_agent.fovmask``)。

前、后雷达照感知节点一样算每一帧「看得见」的格子,每格看得见的帧占多少,≥ 门槛的算视野里。
``--mirror`` 左右镜像取并(录的时候一侧一直贴墙才用;C40221 左右视野不对称,镜像会补出雷达看不到的
格子,默认不开)。顺带报:按写死的视野锥和按学到的视野表,遮挡限速每帧会压到多少
(不算 2 s 记忆,粗看)。

**只用空旷地方的那一段学**(``--from`` / ``--to``,包开头起的秒数):一直贴着货架、墙走,
学出来的视野会窄。

用法(开发机,ROS 的系统 Python)::

    source /opt/ros/humble/setup.bash
    PYTHONPATH=packages/localizer/src:packages/contract/src:packages/robot-agent/src \\
        python3 tools/fov_learn.py <包目录> --frames frames.json --lidars lidars.json \\
        --from 0 --to 80 --out fov.json
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

# 遮挡限速的粗算(跟 nav2_nav._occ_cap 的 E2 一样的几何;不算地图墙、不算记忆)
HL, HW = 0.515, 0.29
SIDE_M, MARGIN_M, REACT_S, DECEL = 2.0, 0.1, 0.5, 0.5
SELF_BLIND_M, CREEP = 0.05, 0.2


def e2(known, occ, fov, cc):
    import numpy as np
    n = len(cc)
    XX, YY = np.meshgrid(cc, cc, indexing="ij")
    jl = int(np.searchsorted(cc, HW))
    jr = int(np.searchsorted(cc, -HW)) - 1
    sh = np.zeros((n, n), dtype=bool)
    sh[:, jl:] = np.logical_or.accumulate(occ[:, jl:], axis=1)
    sh[:, :jr + 1] = np.logical_or.accumulate(occ[:, :jr + 1][:, ::-1], axis=1)[:, ::-1]
    gap = np.abs(YY) - HW
    em = (~known) & fov & (~sh) & (gap > 0) & (gap <= SIDE_M) & (XX > HL + SELF_BLIND_M)
    if not em.any():
        return 1.0
    room = float((XX[em] - HL).min()) - MARGIN_M
    v = DECEL * (-REACT_S + math.sqrt(REACT_S ** 2 + 2 * room / DECEL)) if room > 0 else 0.0
    return max(CREEP, v)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("bag", type=Path)
    p.add_argument("--frames", required=True, type=Path)
    p.add_argument("--lidars", type=Path, default=None, help="后雷达外参(没有 = 只用前雷达)")
    p.add_argument("--from", dest="t0", type=float, default=0.0, help="包开头起第几秒开始学")
    p.add_argument("--to", dest="t1", type=float, default=math.inf)
    p.add_argument("--threshold", type=float, default=None)
    p.add_argument("--out", type=Path, default=None)
    p.add_argument("--every", type=int, default=2, help="每几帧前雷达用一帧")
    p.add_argument("--mirror", action="store_true", help="左右镜像取并(录的时候一侧一直贴墙时用)")
    p.add_argument("--use", type=Path, default=None,
                   help="不学,直接用这张视野表(fov.json)比遮挡限速(拿别的包核一张学好的表)")
    a = p.parse_args(argv)

    import numpy as np
    import rosbag2_py
    from nexwar_localizer.build import cloud_xyz
    from nexwar_localizer.frames import Frames
    from nexwar_localizer.obstacles import Config, Mount, Perception, RearMount
    from rclpy.serialization import deserialize_message
    from sensor_msgs.msg import PointCloud2

    from nexwar_agent import fovmask
    from nexwar_contract.obsbridge import unpack_bits

    thr = fovmask.FOV_THRESHOLD if a.threshold is None else a.threshold
    cfg = Config()
    fr = Frames.load(a.frames)
    front = Mount.from_frames(fr)
    rear = RearMount.from_lidars(front, fr, a.lidars) if a.lidars else None
    clock = [0.0]
    per = Perception(front, rear=rear, cfg=cfg, clock=lambda: clock[0])
    storage = "mcap" if any(a.bag.glob("*.mcap")) else "sqlite3"
    r = rosbag2_py.SequentialReader()
    r.open(rosbag2_py.StorageOptions(uri=str(a.bag), storage_id=storage),
           rosbag2_py.ConverterOptions("", ""))
    r.set_filter(rosbag2_py.StorageFilter(topics=["/front_lidar", "/rear_lidar"]))
    n, nf, start = cfg.size, 0, None
    knowns, occs = [], []
    while r.has_next():
        topic, raw, t_ns = r.read_next()
        start = t_ns if start is None else start
        rel = (t_ns - start) / 1e9
        if rel > a.t1:
            break
        clock[0] = t_ns / 1e9
        pts = cloud_xyz(deserialize_message(raw, PointCloud2))
        if topic == "/rear_lidar":
            per.on_rear(pts)
            continue
        nf += 1
        if nf % a.every:
            continue
        g = per.on_front(pts, t_ns)
        if g is None or per.check.height is None or rel < a.t0:
            continue
        knowns.append(np.frombuffer(unpack_bits(g["known"], n), dtype=np.uint8)
                      .astype(bool).reshape(n, n))
        occs.append(np.frombuffer(unpack_bits(g["occ"], n), dtype=np.uint8)
                    .astype(bool).reshape(n, n))
    if len(knowns) < fovmask.FOV_MIN_FRAMES:
        print(f"只有 {len(knowns)} 帧能用(至少 {fovmask.FOV_MIN_FRAMES}):换一段长一点的",
              file=sys.stderr)
        return 1
    if a.use is not None:
        mask = fovmask.from_wire(json.loads(a.use.read_text(encoding="utf-8")))[0]
        a.out = None
    else:
        mask = fovmask.learn(knowns, threshold=thr)
    if a.mirror:
        mask |= mask[:, ::-1]                              # 左右镜像取并:只会更宽(更保守)
    cc = (np.arange(n) - n / 2 + 0.5) * cfg.res
    XX, YY = np.meshgrid(cc, cc, indexing="ij")
    cone = np.abs(YY) <= 0.6 + 0.9 * np.maximum(np.abs(XX) - 0.465, 0.0)
    cone &= np.abs(XX) > 0.465
    if a.use:
        print(f"用的视野表 {a.use}")
    verb = "看了" if a.use else "学了"
    print(f"{verb} {len(knowns)} 帧(包里 {a.t0:g}–{min(a.t1, rel):.0f} s),门槛 {thr:.0%},"
          f"后雷达 {'用了' if rear is not None else '没有'}")
    print(f"视野表 {int(mask.sum())} 格;写死的锥 {int(cone.sum())} 格;锥里视野表看不见的 "
          f"{int((cone & ~mask).sum())} 格(这些以前被当成阴影)")
    freq = np.mean(knowns, axis=0)
    print("每格看得见的比例(行 x 从 +2.5 到 -2.5,列 y 从 +2 到 -2;0–9 = 0–90%,# ≥ 95%,"
          "| = 写死的锥边):")
    for i in range(n - 1, -1, -1):
        if abs(cc[i]) > 2.5:
            continue
        row = ""
        for j in range(n - 1, -1, -1):
            if abs(cc[j]) > 2.0:
                continue
            v = freq[i, j]
            row += "#" if v >= 0.95 else str(min(9, int(v * 10)))
        print(f"{cc[i]:+.2f} {row}")
    old = np.array([e2(k, o, cone & (XX > 0), cc) for k, o in zip(knowns, occs, strict=True)])
    new = np.array([e2(k, o, mask & (XX > 0), cc) for k, o in zip(knowns, occs, strict=True)])
    for name, v in (("写死的锥", old), ("视野表", new)):
        print(f"遮挡限速(往前走,粗算) {name}:中位 {np.median(v):.2f} m/s,≤0.3 的帧 "
              f"{np.mean(v <= 0.3):.0%},不限的帧 {np.mean(v >= 0.99):.0%}")
    if a.out:
        a.out.write_text(json.dumps(fovmask.to_wire(mask, res=cfg.res, frames=len(knowns),
                                                     threshold=thr, source=str(a.bag.name)),
                                    ensure_ascii=False), encoding="utf-8")
        print(f"写到 {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
