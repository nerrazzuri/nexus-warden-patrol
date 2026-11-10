#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
from pathlib import Path


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def cmd(*args):
    try:
        return subprocess.check_output(args, text=True, stderr=subprocess.STDOUT, timeout=10).strip()
    except Exception as e:
        return f"unavailable: {type(e).__name__}"


def collect(root: Path, scenarios: Path, params: Path) -> dict:
    return {
        "git_commit": cmd("git", "-C", str(root), "rev-parse", "HEAD"),
        "git_dirty": bool(cmd("git", "-C", str(root), "status", "--porcelain")),
        "params_sha256": sha256(params),
        "scenarios_sha256": sha256(scenarios),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "ros_distro": os.environ.get("ROS_DISTRO"),
        "ros2": cmd("ros2", "--help").splitlines()[0] if os.environ.get("ROS_DISTRO") else "not sourced",
        "gazebo": cmd("ign", "gazebo", "--versions"),
    }


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, required=True)
    ap.add_argument("--scenarios", type=Path, required=True)
    ap.add_argument("--params", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    data = collect(a.root, a.scenarios, a.params)
    a.out.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(json.dumps(data, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
