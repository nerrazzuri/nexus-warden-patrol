#!/usr/bin/env python3
"""Reproducible product navigation simulation gate.

Runs named profiles, resumes safely, records environment fingerprints, applies a
fault matrix, and returns non-zero unless the configured release gate passes.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import yaml

from evidence import (evidence_dir, is_failure, prune_bag, retain_success, start_rosbag, stop_process, write_metadata)

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SCENARIOS = HERE / "scenarios.yaml"
PROFILES = HERE / "profiles.yaml"
GATES = HERE / "gates.yaml"
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

def load(path):
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def scenario_ids():
    return [x["id"] for x in load(SCENARIOS)["scenarios"]]


def run(cmd, **kw):
    print("+", " ".join(map(str, cmd)), flush=True)
    return subprocess.run(list(map(str, cmd)), **kw)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", choices=tuple(load(PROFILES)["profiles"]), default="core")
    ap.add_argument("--out", type=Path, default=Path("runs/nav-product-gate"))
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--startup-s", type=float, default=10.0)
    ap.add_argument("--evidence", choices=("none", "failures", "all"), default="failures",
                    help="retain exact-run rosbag and MP4 replay evidence")
    ap.add_argument("--success-evidence-per-case", type=int, default=1,
                    help="successful seeds retained per scenario/fault pair")
    ap.add_argument("--no-video", action="store_true", help="retain bags but skip MP4 visual replay")
    args = ap.parse_args()

    profile = load(PROFILES)["profiles"][args.profile]
    selected = scenario_ids() if profile["scenarios"] == "all" else profile["scenarios"]
    args.out.mkdir(parents=True, exist_ok=True)

    run([sys.executable, HERE / "environment.py", "--root", ROOT, "--scenarios", SCENARIOS,
         "--params", PARAMS, "--out", args.out / "environment.json"], check=True)
    manifest = {"profile": args.profile, "gate": profile["gate"], "scenarios": selected,
                "seeds": int(profile["seeds"]), "fault_matrix": profile.get("fault_matrix", [])}
    (args.out / "run_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    faults = profile.get("fault_matrix") or [{"name": "nominal"}]
    all_results = args.out / "results.jsonl"
    if all_results.exists() and not args.resume:
        all_results.unlink()

    for fault in faults:
        fault_name = fault.get("name", "nominal")
        for scenario in selected:
            for seed in range(int(profile["seeds"])):
                case_dir = args.out / "cases" / fault_name / scenario / f"seed-{seed:04d}"
                result_path = case_dir / "result.json"
                if args.resume and result_path.exists():
                    continue
                case_dir.mkdir(parents=True, exist_ok=True)
                slot = getattr(main, "_slot", 0); main._slot = slot + 1
                _isolate(slot)
                run([sys.executable, HERE / "generate_case.py", "--scenario", scenario,
                     "--seed", seed, "--out", case_dir], cwd=ROOT, check=True,
                    stdout=subprocess.DEVNULL)
                case = json.loads((case_dir / "case.json").read_text(encoding="utf-8"))
                launch_log = case_dir / "launch.log"
                metrics = case_dir / "metrics.json"
                launch_cmd = [
                    "ros2", "launch", str(HERE / "nav_bench.launch.py"),
                    f"world:={case_dir / 'world.sdf'}", f"map:={case_dir / 'map.yaml'}",
                    f"params_file:={PARAMS}", f"seed:={seed}",
                    f"start_x:={_odom_start(case)[0]}", f"start_y:={_odom_start(case)[1]}",
                    f"start_yaw:={_odom_start(case)[2]}",
                    f"case_json:={case_dir / 'case.json'}",
                    f"fault_at_s:={fault.get('at_s', 1e9)}",
                    f"fault_duration_s:={fault.get('duration_s', 2.0)}",
                    f"pose_jump_m:={fault.get('pose_jump_m', 0.0)}",
                    f"yaw_jump_deg:={fault.get('yaw_jump_deg', 0.0)}",
                    f"tf_dropout_s:={fault.get('tf_dropout_s', 0.0)}",
                    f"obstacle_delay_ms:={fault.get('obstacle_delay_ms', 0.0)}",
                    f"obstacle_drop_rate:={fault.get('obstacle_drop_rate', 0.0)}",
                    f"dynamic:={'true' if case.get('dynamic') else 'false'}",
                ]
                env = dict(os.environ); env.setdefault("IGN_VERSION", "fortress")
                import signal, time
                bag = None
                with launch_log.open("w", encoding="utf-8") as log:
                    proc = subprocess.Popen(launch_cmd, cwd=ROOT, env=env, stdout=log,
                                            stderr=subprocess.STDOUT, start_new_session=True)
                    rc = 124
                    try:
                        if args.evidence != "none":
                            bag = start_rosbag(case_dir, enabled=True)
                        time.sleep(args.startup_s)
                        cp = run([sys.executable, HERE / "goal_driver.py", "--case", case_dir / "case.json",
                                  "--out", metrics], cwd=ROOT, env=env,
                                 timeout=float(case.get("timeout_s", 90))*len(case["goals"])+30)
                        rc = cp.returncode
                    except subprocess.TimeoutExpired:
                        metrics.write_text(json.dumps({"success": False, "reason": "driver timeout"}), encoding="utf-8")
                    finally:
                        stop_process(bag)
                        try:
                            os.killpg(proc.pid, signal.SIGTERM); proc.wait(timeout=8)
                        except Exception:
                            try: os.killpg(proc.pid, signal.SIGKILL)
                            except Exception: pass
                m = json.loads(metrics.read_text(encoding="utf-8")) if metrics.exists() else {"success": False, "reason": "no metrics"}
                from run_bench import count_logs
                logs = launch_log.read_text(encoding="utf-8", errors="replace")
                row = {"profile": args.profile, "fault": fault_name, "scenario": scenario,
                       "seed": seed, "returncode": rc, **m, **count_logs(logs)}
                failed = is_failure(row)
                sampled = retain_success(seed, max(0, args.success_evidence_per_case))
                retain = args.evidence == "all" or (args.evidence == "failures" and (failed or sampled))
                reason = "failure" if failed else ("success-sample" if sampled else "not-retained")
                if not retain:
                    prune_bag(case_dir)
                elif not args.no_video:
                    fault_json = evidence_dir(case_dir) / "fault.json"
                    fault_json.write_text(json.dumps(fault, indent=2), encoding="utf-8")
                    video = evidence_dir(case_dir) / "replay.mp4"
                    cap = [sys.executable, HERE / "capture_case.py", "--case", case_dir / "case.json",
                           "--fault", fault_json, "--out", video, "--startup-s", args.startup_s,
                           "--slot", slot]
                    cap_rc = run(cap, cwd=ROOT).returncode
                    row["video_capture_rc"] = cap_rc
                write_metadata(case_dir, row, retain, reason)
                row["evidence_retained"] = retain
                row["evidence_reason"] = reason
                row["evidence_path"] = str((case_dir / "evidence").relative_to(args.out)) if retain else None
                result_path.write_text(json.dumps(row, indent=2), encoding="utf-8")
                with all_results.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(row, ensure_ascii=False)+"\n")

    cp = run([sys.executable, HERE / "product_report.py", "--input", all_results,
              "--gates", GATES, "--gate", profile["gate"], "--out", args.out], cwd=ROOT)
    return cp.returncode


if __name__ == "__main__":
    raise SystemExit(main())
