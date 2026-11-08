#!/usr/bin/env python3
"""Batch runner for the Gazebo/Nav2 navigation stability benchmark."""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SCENARIOS = HERE / "scenarios.yaml"

LOG_PATTERNS = {
    "progress_failures": re.compile(r"Failed to make progress|progress checker", re.I),
    "planner_failures": re.compile(r"failed to create plan|no valid path|planning failed", re.I),
    "controller_failures": re.compile(r"controller.*failed|followpath.*failed", re.I),
    "localization_resets": re.compile(r"locali[sz].*reset|重置.*定位", re.I),
    "safety_rejections": re.compile(r"safety.*reject|守卫.*拦|速度.*拒", re.I),
}




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

def ids(doc: dict) -> list[str]:
    return [s["id"] for s in doc["scenarios"]]


def count_logs(text: str) -> dict[str, int]:
    return {key: len(rx.findall(text)) for key, rx in LOG_PATTERNS.items()}


def run_one(scenario: str, seed: int, out_root: Path, startup_s: float) -> dict:
    case_dir = out_root / scenario / f"seed-{seed:04d}"
    case_dir.mkdir(parents=True, exist_ok=True)
    slot = getattr(run_one, "_slot", 0); run_one._slot = slot + 1
    _isolate(slot)
    gen = [sys.executable, str(HERE / "generate_case.py"), "--scenario", scenario, "--seed", str(seed), "--out", str(case_dir)]
    subprocess.run(gen, cwd=ROOT, check=True)
    case = json.loads((case_dir / "case.json").read_text(encoding="utf-8"))
    launch_cmd = [
        "ros2", "launch", str(HERE / "nav_bench.launch.py"),
        f"world:={case_dir / 'world.sdf'}",
        f"map:={case_dir / 'map.yaml'}",
        f"params_file:={ROOT / 'deploy/nav2/params.yaml'}",
        f"start_x:={_odom_start(case)[0]}", f"start_y:={_odom_start(case)[1]}",
        f"start_yaw:={_odom_start(case)[2]}",
    ]
    env = dict(os.environ)
    env.setdefault("IGN_VERSION", "fortress")
    log_path = case_dir / "launch.log"
    metrics_path = case_dir / "metrics.json"
    with log_path.open("w", encoding="utf-8") as log:
        proc = subprocess.Popen(launch_cmd, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, env=env, start_new_session=True)
        try:
            time.sleep(startup_s)
            goal = [sys.executable, str(HERE / "goal_driver.py"), "--case", str(case_dir / "case.json"), "--out", str(metrics_path)]
            completed = subprocess.run(goal, cwd=ROOT, env=env, timeout=float(case.get("timeout_s", 90)) * len(case["goals"]) + 30)
            rc = completed.returncode
        except subprocess.TimeoutExpired:
            rc = 124
            metrics_path.write_text(json.dumps({"success": False, "reason": "driver timeout"}, indent=2), encoding="utf-8")
        finally:
            try:
                os.killpg(proc.pid, signal.SIGTERM)
                proc.wait(timeout=8)
            except (ProcessLookupError, subprocess.TimeoutExpired):
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
    metrics = json.loads(metrics_path.read_text(encoding="utf-8")) if metrics_path.exists() else {"success": False, "reason": "no metrics"}
    log_text = log_path.read_text(encoding="utf-8", errors="replace")
    row = {
        "scenario": scenario,
        "seed": seed,
        "returncode": rc,
        **metrics,
        **count_logs(log_text),
    }
    (case_dir / "result.json").write_text(json.dumps(row, indent=2), encoding="utf-8")
    return row


def flatten(row: dict) -> dict:
    return {k: v for k, v in row.items() if not isinstance(v, (dict, list))}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenarios", default="all", help="all or comma-separated scenario ids")
    ap.add_argument("--seeds", type=int, default=50, help="number of seeds per scenario")
    ap.add_argument("--seed-start", type=int, default=0)
    ap.add_argument("--startup-s", type=float, default=8.0)
    ap.add_argument("--out", type=Path, default=Path("runs/nav-stability"))
    ap.add_argument("--fail-fast", action="store_true")
    args = ap.parse_args()
    doc = yaml.safe_load(SCENARIOS.read_text(encoding="utf-8"))
    selected = ids(doc) if args.scenarios == "all" else [x.strip() for x in args.scenarios.split(",") if x.strip()]
    unknown = sorted(set(selected) - set(ids(doc)))
    if unknown:
        raise SystemExit(f"unknown scenarios: {', '.join(unknown)}")
    args.out.mkdir(parents=True, exist_ok=True)
    rows = []
    for scenario in selected:
        for seed in range(args.seed_start, args.seed_start + args.seeds):
            print(f"[nav-bench] {scenario} seed={seed}", flush=True)
            row = run_one(scenario, seed, args.out, args.startup_s)
            rows.append(row)
            with (args.out / "results.jsonl").open("a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
            if args.fail_fast and (not row.get("success") or row.get("clearance_violation")):
                break
    if rows:
        fields = sorted({k for r in rows for k in flatten(r)})
        with (args.out / "results.csv").open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            for row in rows:
                w.writerow(flatten(row))
    subprocess.run([sys.executable, str(HERE / "summarize.py"), "--input", str(args.out / "results.jsonl"), "--out", str(args.out / "summary.json")], check=False)
    failures = [r for r in rows if not r.get("success") or r.get("clearance_violation")]
    return 0 if not failures else 2


if __name__ == "__main__":
    raise SystemExit(main())
