#!/usr/bin/env python3
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]


def check_cmd(name):
    return shutil.which(name) is not None


def ros_pkg(name):
    try:
        subprocess.check_output(["ros2","pkg","prefix",name],stderr=subprocess.STDOUT,timeout=10)
        return True
    except Exception:
        return False


def main():
    checks={
      "Ubuntu/ROS target": os.environ.get("ROS_DISTRO")=="humble",
      "ros2": check_cmd("ros2"),
      "Gazebo ign": check_cmd("ign"),
      "nav2_controller": ros_pkg("nav2_controller") if check_cmd("ros2") else False,
      "nav2_smac_planner": ros_pkg("nav2_smac_planner") if check_cmd("ros2") else False,
      "nav2_mppi_controller": ros_pkg("nav2_mppi_controller") if check_cmd("ros2") else False,
      "ros_gz_bridge": ros_pkg("ros_gz_bridge") if check_cmd("ros2") else False,
      "production params": (ROOT/"deploy/nav2/params.yaml").exists(),
      "production BT": (ROOT/"deploy/nav2/navigate_to_pose_d1max.xml").exists(),
    }
    evidence={
      "ros2 bag": check_cmd("ros2"),
      "ffmpeg (MP4 evidence)": check_cmd("ffmpeg"),
      "Xvfb (headless MP4)": bool(os.environ.get("DISPLAY")) or check_cmd("xvfb-run"),
    }
    width=max(map(len,checks))
    for k,v in checks.items(): print(f"{'PASS' if v else 'FAIL':4}  {k:<{width}}")
    print("\nEvidence capture (optional for numeric-only gate):")
    ewidth=max(map(len,evidence))
    for k,v in evidence.items(): print(f"{'PASS' if v else 'WARN':4}  {k:<{ewidth}}")
    bad=[k for k,v in checks.items() if not v]
    if bad:
        print("\nNot ready:", ", ".join(bad), file=sys.stderr)
        return 2
    print("\nNavigation simulation host is ready.")
    return 0

if __name__=="__main__": raise SystemExit(main())
