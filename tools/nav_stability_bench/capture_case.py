#!/usr/bin/env python3
"""Create an MP4 visual replay for one deterministic navigation case.

If DISPLAY is unavailable, automatically uses Xvfb when installed. The visual replay
is intentionally secondary evidence: the exact failed primary run is preserved in
its rosbag; this replay exists so an engineer can quickly see the failure geometry.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PARAMS = ROOT / "deploy" / "nav2" / "params.yaml"




def _isolate(slot: int, replay: bool = False) -> None:
    """每次仿真独占一个 ROS 域和 Gazebo 分区。

    带画面的 Gazebo 把服务端/界面拆到别的进程组,按进程组停不干净;残留的仿真会继续发
    /clock 和 odom->base_link,下一轮的 Nav2 收到更晚的时间戳,把新位姿全当过期丢掉。
    子进程(launch、goal_driver、rosbag、capture)都继承这里设的环境。
    """
    domain = 10 + (2 * slot) % 80 + (1 if replay else 0)
    os.environ["ROS_DOMAIN_ID"] = str(domain)
    os.environ["IGN_PARTITION"] = f"nav_bench_{os.getpid()}_{slot}{'_replay' if replay else ''}"

def _odom_start(case: dict) -> list:
    """map->odom 要带的起点:/odom 从出生点算起时才需要,世界坐标的里程计给 0。"""
    return case["start"] if case.get("odom_origin", "spawn") == "spawn" else [0.0, 0.0, 0.0]

def stop(proc, sig=signal.SIGTERM, timeout=8):
    if proc is None:
        return
    try:
        os.killpg(proc.pid, sig); proc.wait(timeout=timeout)
    except Exception:
        try: os.killpg(proc.pid, signal.SIGKILL)
        except Exception: pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--fault", type=Path, help="JSON object with fault parameters")
    ap.add_argument("--startup-s", type=float, default=10.0)
    ap.add_argument("--slot", type=int, default=None, help="隔离用:跟主运行同一 slot 的 replay 域")
    ap.add_argument("--fps", type=int, default=20)
    ap.add_argument("--size", default="1280x720")
    ap.add_argument("--inside-xvfb", action="store_true")
    args = ap.parse_args()

    if not os.environ.get("DISPLAY") and not args.inside_xvfb:
        if shutil.which("xvfb-run") is None:
            print("capture skipped: DISPLAY is unset and xvfb-run is unavailable", file=sys.stderr)
            return 3
        cmd = ["xvfb-run", "-a", "-s", f"-screen 0 {args.size}x24", sys.executable,
               str(Path(__file__).resolve()), "--case", str(args.case), "--out", str(args.out),
               "--startup-s", str(args.startup_s), "--fps", str(args.fps), "--size", args.size,
               "--inside-xvfb"]
        if args.fault: cmd += ["--fault", str(args.fault)]
        if args.slot is not None: cmd += ["--slot", str(args.slot)]
        return subprocess.run(cmd, cwd=ROOT).returncode

    if shutil.which("ffmpeg") is None:
        print("capture skipped: ffmpeg unavailable", file=sys.stderr)
        return 4

    if args.slot is not None:
        _isolate(args.slot, replay=True)
    case = json.loads(args.case.read_text(encoding="utf-8"))
    fault = json.loads(args.fault.read_text(encoding="utf-8")) if args.fault else {"name":"nominal"}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    replay_result = args.out.parent / "replay_result.json"
    launch_log = args.out.parent / "replay_launch.log"
    metrics = args.out.parent / "replay_metrics.json"

    launch_cmd = [
        "ros2", "launch", str(HERE / "nav_bench.launch.py"),
        f"world:={args.case.parent / 'world.sdf'}", f"map:={args.case.parent / 'map.yaml'}",
        f"params_file:={PARAMS}", f"seed:={case['seed']}", "gui:=true",
        f"start_x:={_odom_start(case)[0]}", f"start_y:={_odom_start(case)[1]}",
        f"start_yaw:={_odom_start(case)[2]}",
        f"fault_at_s:={fault.get('at_s', 1e9)}", f"fault_duration_s:={fault.get('duration_s', 2.0)}",
        f"pose_jump_m:={fault.get('pose_jump_m', 0.0)}", f"yaw_jump_deg:={fault.get('yaw_jump_deg', 0.0)}",
        f"tf_dropout_s:={fault.get('tf_dropout_s', 0.0)}", f"obstacle_delay_ms:={fault.get('obstacle_delay_ms', 0.0)}",
        f"obstacle_drop_rate:={fault.get('obstacle_drop_rate', 0.0)}",
        f"dynamic:={'true' if case.get('dynamic') else 'false'}",
    ]
    env = dict(os.environ); env.setdefault("IGN_VERSION", "fortress")
    with launch_log.open("w", encoding="utf-8") as log:
        launch = subprocess.Popen(launch_cmd, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        video = None
        try:
            time.sleep(args.startup_s)
            video_cmd = ["ffmpeg", "-y", "-loglevel", "warning", "-f", "x11grab", "-framerate", str(args.fps),
                         "-video_size", args.size, "-i", os.environ["DISPLAY"], "-c:v", "libx264",
                         "-preset", "veryfast", "-crf", "25", "-pix_fmt", "yuv420p", str(args.out)]
            video = subprocess.Popen(video_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, start_new_session=True)
            cp = subprocess.run([sys.executable, str(HERE / "goal_driver.py"), "--case", str(args.case), "--out", str(metrics)],
                                cwd=ROOT, env=env, timeout=float(case.get("timeout_s",90))*len(case["goals"])+30)
            result = json.loads(metrics.read_text(encoding="utf-8")) if metrics.exists() else {"success":False,"reason":"no replay metrics"}
            result["returncode"] = cp.returncode
            replay_result.write_text(json.dumps(result, indent=2), encoding="utf-8")
        except subprocess.TimeoutExpired:
            replay_result.write_text(json.dumps({"success":False,"reason":"visual replay timeout"}, indent=2), encoding="utf-8")
        finally:
            stop(video, signal.SIGINT, 5)
            stop(launch)
    return 0 if args.out.exists() and args.out.stat().st_size > 0 else 5


if __name__ == "__main__":
    raise SystemExit(main())
