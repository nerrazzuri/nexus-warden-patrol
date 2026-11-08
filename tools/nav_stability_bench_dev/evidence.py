#!/usr/bin/env python3
"""Evidence capture helpers for the navigation product gate.

Primary runs always capture a focused rosbag so a failure is reproducible from the
exact run. Successful bags are pruned immediately unless selected as a deterministic
sample. Visual MP4 capture is performed as a second deterministic replay only for
retained cases, avoiding the cost of rendering every Monte-Carlo run.
"""
from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
from pathlib import Path

BAG_TOPICS = [
    "/clock", "/tf", "/tf_static", "/odom", "/scan", "/cmd_vel",
    "/cmd_vel_nav", "/cmd_vel_behavior", "/nexwar/obs_occ", "/nexwar/obs_free",
    "/plan", "/local_plan", "/nav_bench/actors",
]


def is_failure(row: dict) -> bool:
    return (not bool(row.get("success"))) or bool(row.get("collision")) or bool(row.get("clearance_violation"))


def retain_success(seed: int, samples_per_case: int) -> bool:
    """Deterministic success sampling: the first N seeds of every scenario/fault pair."""
    return samples_per_case > 0 and seed < samples_per_case


def evidence_dir(case_dir: Path) -> Path:
    p = Path(case_dir) / "evidence"
    p.mkdir(parents=True, exist_ok=True)
    return p


def start_rosbag(case_dir: Path, enabled: bool = True):
    if not enabled or shutil.which("ros2") is None:
        return None
    out = evidence_dir(case_dir) / "bag"
    if out.exists():
        shutil.rmtree(out)
    cmd = ["ros2", "bag", "record", "-o", str(out), *BAG_TOPICS]
    log = (evidence_dir(case_dir) / "rosbag.log").open("w", encoding="utf-8")
    proc = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    proc._nexwar_log = log  # type: ignore[attr-defined]
    return proc


def stop_process(proc, timeout: float = 8.0) -> None:
    if proc is None:
        return
    try:
        os.killpg(proc.pid, signal.SIGINT)
        proc.wait(timeout=timeout)
    except Exception:
        try:
            os.killpg(proc.pid, signal.SIGTERM)
            proc.wait(timeout=3)
        except Exception:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except Exception:
                pass
    log = getattr(proc, "_nexwar_log", None)
    if log is not None:
        log.close()


def prune_bag(case_dir: Path) -> None:
    ev = evidence_dir(case_dir)
    shutil.rmtree(ev / "bag", ignore_errors=True)
    try:
        (ev / "rosbag.log").unlink()
    except FileNotFoundError:
        pass


def write_metadata(case_dir: Path, row: dict, retained: bool, reason: str) -> None:
    ev = evidence_dir(case_dir)
    meta = {
        "retained": retained,
        "reason": reason,
        "primary_rosbag": "bag" if retained and (ev / "bag").exists() else None,
        "video": "replay.mp4" if (ev / "replay.mp4").exists() else None,
        "visual_replay_result": "replay_result.json" if (ev / "replay_result.json").exists() else None,
        "warning": "MP4 is a deterministic visual replay; rosbag is the evidence from the exact primary run.",
        "result": {k: row.get(k) for k in ("success", "collision", "clearance_violation", "reason", "max_stall_s")},
    }
    (ev / "evidence.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
