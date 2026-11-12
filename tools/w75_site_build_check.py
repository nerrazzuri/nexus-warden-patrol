"""W75 站点出图自检:录包 → 模拟机器人边走边存关键帧 → 站点出图任务出图、登记,报用时和内存最高值。

在站点主机(POC 是现场笔记本)上装好出图组件以后跑一次,看 3 分钟能不能做到、内存够不够。

    python3 tools/w75_site_build_check.py <录包目录> <工作目录> --runner <出图命令...>
        [--pose /d1max_loc/lio/odom]

- 录包要有 ``/front_lidar``、Super-LIO 位姿(默认 ``/d1max_loc/lio/odom``)、``/odom/mc_odom``。
- 工作目录会被清空重建。站点数据库、地图目录都建在里面,不碰真站点。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import resource
import shutil
import time
from pathlib import Path


def keyframes_from_bag(bag: Path, out: Path, pose_topic: str) -> dict:
    import rosbag2_py
    from nav_msgs.msg import Odometry
    from nexwar_localizer import livemap as L
    from nexwar_localizer import superlio as S
    from nexwar_localizer.build import cloud_xyz
    from rclpy.serialization import deserialize_message
    from sensor_msgs.msg import PointCloud2

    ext = S.extrinsic(S.config_path())
    def decode(raw):
        return cloud_xyz(deserialize_message(raw, PointCloud2))
    kf = S.LiveKeyframes(S.Keyframer(out, ext[0], ext[1], decode, voxel=S.KF_VOXEL_M),
                         log=out / "lio.tum")
    clock = [0.0]
    h = L.Handlers(L.Feeder(L.LiveGrid(), window=L.SUPERLIO_PAIR_WINDOW_S, extrinsic=ext),
                   decode_cloud=decode, keyframes=kf, now=lambda: clock[0])
    meta = (bag / "metadata.yaml").read_text()
    r = rosbag2_py.SequentialReader()
    storage = "mcap" if "mcap" in meta else "sqlite3"
    r.open(rosbag2_py.StorageOptions(uri=str(bag), storage_id=storage),
           rosbag2_py.ConverterOptions("cdr", "cdr"))
    r.set_filter(rosbag2_py.StorageFilter(topics=["/front_lidar", pose_topic, "/odom/mc_odom"]))
    n = 0
    while r.has_next():
        topic, raw, t_ns = r.read_next()
        clock[0] = t_ns * 1e-9
        if topic == "/front_lidar":
            h.on_scan(raw)
            n += 1
        elif topic == pose_topic:
            h.on_pose(deserialize_message(raw, Odometry))
        else:
            h.on_odom(deserialize_message(raw, Odometry))
    summary = kf.close()
    L.write_live(out, h, summary)
    return {"scans": n, "summary": summary}


def site_build(kd: Path, home: Path, runner: list[str]) -> dict:
    from nexwar_site.db import SiteDB
    from nexwar_site.mapbuild import KF_MANIFEST, SiteMapBuilder
    from nexwar_site.maps import MapCatalog

    db = SiteDB(home / "site.db")
    cat = MapCatalog(home, db, now_ms=lambda: int(time.time() * 1000))
    with db.tx() as c:
        c.execute("INSERT INTO commands(command_id, task_id, robot_id, kind, payload, issued_by, "
                  "issued_at, priority) VALUES ('c1','t1','A','mapping',?, 'check', 1, 0)",
                  (json.dumps({"action": "start", "name": "check", "map_id": "check",
                               "version": "1", "pack": "site"}),))
    done: list = []
    b = SiteMapBuilder(home, cat, runner=runner, on_done=done.append, start_thread=False)
    files = []
    for p in sorted(kd.rglob("*")):
        rel = p.relative_to(kd).as_posix()
        if not p.is_file() or rel.split("/")[-1].startswith(".") or rel == KF_MANIFEST:
            continue
        d = p.read_bytes()
        files.append({"name": rel, "size": len(d), "sha256": hashlib.sha256(d).hexdigest()})
        b.put_chunk("A", "check/1", rel, offset=0, data=d, total=len(d))
    m = json.dumps({"map_id": "check", "version": "1", "files": files}).encode()
    b.put_chunk("A", "check/1", KF_MANIFEST, offset=0, data=m, total=len(m))
    t = time.monotonic()
    b.run_pending()
    ref = cat.get("check", "1") if done and done[0]["ok"] else None
    return {"seconds": round(time.monotonic() - t, 1), "result": done,
            "files": sorted(f.name for f in ref.files) if ref else []}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("bag", type=Path)
    ap.add_argument("work", type=Path)
    ap.add_argument("--runner", nargs="+", required=True,
                    help="出图命令,跟 site.json 的 mapbuild.runner 一样")
    ap.add_argument("--pose", default="/d1max_loc/lio/odom")
    a = ap.parse_args()
    shutil.rmtree(a.work, ignore_errors=True)
    kd, home = a.work / "kf", a.work / "site"
    kd.mkdir(parents=True)
    home.mkdir()
    t = time.monotonic()
    k = keyframes_from_bag(a.bag, kd, a.pose)
    print("关键帧:", k["scans"], "帧雷达,", k["summary"], f"用时 {time.monotonic() - t:.1f} s")
    r = site_build(kd, home, a.runner)
    peak = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss / 1024 / 1024
    print(f"站点出图用时 {r['seconds']:.1f} s,出图进程内存最高 {peak:.1f} GB")
    print("结果:", r["result"])
    print("登记的文件:", r["files"])


if __name__ == "__main__":
    main()
