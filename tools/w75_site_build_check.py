"""W75 站点出图自检:录包 → 模拟机器人边走边存关键帧 → 站点出图任务出图、登记,报用时和内存最高值。

在站点主机(POC 是现场笔记本)上装好出图组件以后跑一次,看 3 分钟能不能做到、内存够不够。

    source /opt/ros/humble/setup.bash
    PYTHONPATH=$(ls -d packages/*/src | tr '\n' ':')src:$PYTHONPATH \
      python3 tools/w75_site_build_check.py <录包目录> <工作目录> --runner <出图命令...> \
        [--pose /d1max_loc/lio/odom]

  PYTHONPATH 末尾要接上 ``:$PYTHONPATH``,不然 ROS 的 ``rosbag2_py`` 找不到。

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


def _reader(bag: Path, topics: list[str]):
    import rosbag2_py
    storage = "mcap" if "mcap" in (bag / "metadata.yaml").read_text() else "sqlite3"
    r = rosbag2_py.SequentialReader()
    r.open(rosbag2_py.StorageOptions(uri=str(bag), storage_id=storage),
           rosbag2_py.ConverterOptions("cdr", "cdr"))
    r.set_filter(rosbag2_py.StorageFilter(topics=topics))
    return r


def keyframes_from_bag(bag: Path, out: Path, pose_topic: str,
                       pose_bag: Path | None = None) -> dict:
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
    # 位姿在别的包里(Super-LIO 重放出来的):按报文头时刻排好,录包走到那个时刻就喂
    poses: list = []
    if pose_bag is not None:
        pr = _reader(pose_bag, [pose_topic])
        while pr.has_next():
            poses.append(deserialize_message(pr.read_next()[1], Odometry))
        poses.sort(key=lambda m: m.header.stamp.sec + m.header.stamp.nanosec * 1e-9)
    pi = 0
    topics = ["/front_lidar", "/odom/mc_odom"] + ([] if pose_bag else [pose_topic])
    r = _reader(bag, topics)
    n = 0
    while r.has_next():
        topic, raw, t_ns = r.read_next()
        clock[0] = t_ns * 1e-9
        if topic == "/front_lidar":
            h.on_scan(raw)
            n += 1
            # 真机上 Super-LIO 的位姿在这一帧之后才到:这一帧处理完再喂到它为止的位姿
            upto = L.cdr_stamp(raw) + L.SUPERLIO_PAIR_WINDOW_S[1]
            while pi < len(poses) and (poses[pi].header.stamp.sec
                                       + poses[pi].header.stamp.nanosec * 1e-9) <= upto:
                h.on_pose(poses[pi])
                pi += 1
        elif topic == pose_topic:
            h.on_pose(deserialize_message(raw, Odometry))
        else:
            h.on_odom(deserialize_message(raw, Odometry))
    for m in poses[pi:]:
        h.on_pose(m)
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
    ap.add_argument("--pose-bag", type=Path, default=None,
                    help="位姿在另一个包里(比如 Super-LIO 重放出来的 lio_bag)")
    a = ap.parse_args()
    shutil.rmtree(a.work, ignore_errors=True)
    kd, home = a.work / "kf", a.work / "site"
    kd.mkdir(parents=True)
    home.mkdir()
    t = time.monotonic()
    k = keyframes_from_bag(a.bag, kd, a.pose, a.pose_bag)
    print("关键帧:", k["scans"], "帧雷达,", k["summary"], f"用时 {time.monotonic() - t:.1f} s")
    r = site_build(kd, home, a.runner)
    peak = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss / 1024 / 1024
    print(f"站点出图用时 {r['seconds']:.1f} s,出图进程内存最高 {peak:.1f} GB")
    print("结果:", r["result"])
    print("登记的文件:", r["files"])


if __name__ == "__main__":
    main()
