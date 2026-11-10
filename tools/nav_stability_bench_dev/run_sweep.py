#!/usr/bin/env python3
"""场景库批量跑(一晚上那种):场景 × 种子 × 配置,N 路并行,可断点续跑。

    python3 run_sweep.py --scenarios scenarios_p0.yaml --seeds 12 --parallel 12 \\
        --config today:guard=true,tight=false --config tight:guard=true,tight=true --out runs/nav-sweep-p0

每一趟:生成场景(generate_case)→ 起仿真(独占一个 ROS 域 + Gazebo 分区)→ 录包 → goal_driver 下目标、
算指标 → 停仿真 → 从 launch.log 数脱困动作和 Nav2 的典型报错 → 写 result.json。
已有 result.json 的跳过(断点续跑)。录包:失败的留;成功的每个(配置, 场景)只留第一个。
顺序是「种子在外层」:中途停下,每个场景都已经有几次。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PARAMS = ROOT / "deploy" / "nav2" / "params.yaml"
BT = ROOT / "deploy" / "nav2" / "navigate_to_pose_d1max.xml"


def _here(p) -> str:
    """配置里写的相对路径:当前目录下有就用,没有按本目录算(params=params/params_rpp.yaml)。"""
    p = Path(p)
    if p.is_absolute() or p.exists():
        return str(p.resolve())
    return str(HERE / p)
BAG_TOPICS = ["/odom", "/plan", "/scan", "/cmd_vel", "/cmd_vel_nav", "/nav_bench/actors"]
LOG_PATTERNS = {
    "rec_backup": r"\[behavior_server\]: Running backup",
    "rec_spin": r"\[behavior_server\]: Running spin",
    "rec_wait": r"\[behavior_server\]: Running wait",
    "rec_drive": r"\[behavior_server\]: Running drive_on_heading",
    "err_start_lethal": r"Starting point in lethal space",
    "err_optimizer": r"Optimizer fail to compute path",
    "err_collision_ahead": r"Collision Ahead",
    "err_no_path": r"failed to generate a valid path",
    "fault_fired": r"故障触发",
}
SIM_ARGS = {"exec_noise": "exec_noise", "obstacle_delay_ms": "obstacle_delay_ms", "fault_trigger": "fault_trigger",
            "lateral_m": "lateral_m", "loc_noise_m": "loc_noise_m", "loc_noise_deg": "loc_noise_deg",
            "yaw_jump_deg": "yaw_jump_deg", "pose_jump_m": "pose_jump_m", "fault_duration_s": "fault_duration_s",
            "tf_dropout_s": "tf_dropout_s", "fault_at_s": "fault_at_s"}


def _cfg(s: str) -> tuple[str, dict]:
    name, _, rest = s.partition(":")
    kv = dict(p.split("=", 1) for p in rest.split(",") if p)
    return name, kv


def _arg(v) -> str:
    return ("true" if v else "false") if isinstance(v, bool) else str(v)


def _stop(proc, sig=signal.SIGINT, timeout=20):
    if proc is None or proc.poll() is not None:
        return
    try:
        os.killpg(proc.pid, sig)
        proc.wait(timeout=timeout)
    except Exception:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait(timeout=5)
        except Exception:
            pass


def run_one(job: dict, slot: int, args) -> dict:
    d: Path = job["dir"]
    if (d / "result.json").exists():
        return json.loads((d / "result.json").read_text())
    if d.exists():
        shutil.rmtree(d)                       # 上次没跑完的半截
    d.mkdir(parents=True)
    env = dict(os.environ, ROS_DOMAIN_ID=str(args.domain_base + slot),
               IGN_PARTITION=f"nav_sweep_{os.getpid()}_{slot}", IGN_VERSION="fortress", PYTHONDONTWRITEBYTECODE="1")
    t0 = time.time()
    gen = subprocess.run([sys.executable, str(HERE / "generate_case.py"), "--scenarios", str(args.scenarios),
                          "--scenario", job["scenario"], "--seed", str(job["seed"]), "--out", str(d)],
                         cwd=ROOT, env=env, capture_output=True, text=True)
    if gen.returncode != 0:
        res = {"success": False, "reason": "generate failed", "stderr": gen.stderr[-500:]}
        (d / "result.json").write_text(json.dumps({**job_info(job), **res}, ensure_ascii=False, default=str))
        return res
    case = json.loads((d / "case.json").read_text())
    cfg = job["config"]
    try:                                       # 几何判定器的答案(导航 V1 第 2 节):这一趟该过还是该拒
        from oracle_label import label
        oracle = label(d)
    except Exception as e:                     # 标不出来不影响跑
        oracle = {"error": repr(e)[:200]}
    launch_args = [f"world:={d / 'world.sdf'}", f"map:={d / 'map.yaml'}", f"params_file:={_here(cfg.get('params', PARAMS))}",
                   f"bt_xml:={_here(cfg.get('bt', BT))}",
                   f"seed:={job['seed']}", f"case_json:={d / 'case.json'}",
                   f"agent_guard:={cfg.get('guard', 'false')}", f"guard_tight:={cfg.get('tight', 'false')}",
                   f"guard_log:={d / 'guard.jsonl'}", f"guard_mode:={cfg.get('mode', 'A')}",
                   f"blind_band:={cfg.get('blind', 'false')}"]
    for k, v in (case.get("sim") or {}).items():
        if k in SIM_ARGS:
            launch_args.append(f"{SIM_ARGS[k]}:={_arg(v)}")
    launch = bag = None
    with (d / "launch.log").open("w") as log:
        try:
            launch = subprocess.Popen(["ros2", "launch", str(HERE / "nav_bench.launch.py"), *launch_args],
                                      cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            bag = subprocess.Popen(["ros2", "bag", "record", "-o", str(d / "bag"), *BAG_TOPICS], cwd=ROOT, env=env,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
            time.sleep(10)
            budget = float(case.get("timeout_s", 90)) * len(case["goals"]) + 60
            try:
                gate = ["--route-gate"] if cfg.get("route_gate") == "true" else []
                subprocess.run([sys.executable, str(HERE / "goal_driver.py"), "--case", str(d / "case.json"),
                                "--out", str(d / "metrics.json"), *gate], cwd=ROOT, env=env, timeout=budget,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except subprocess.TimeoutExpired:
                pass
        finally:
            _stop(bag, signal.SIGINT, 15)
            _stop(launch, signal.SIGINT, 25)
    metrics = json.loads((d / "metrics.json").read_text()) if (d / "metrics.json").exists() else \
        {"success": False, "reason": "no metrics (driver timeout/crash)"}
    text = (d / "launch.log").read_text(errors="replace")
    counts = {k: len(re.findall(p, text)) for k, p in LOG_PATTERNS.items()}
    guard = {}
    if (d / "guard.jsonl").exists():
        for line in (d / "guard.jsonl").read_text().splitlines():
            if '"summary"' in line:
                guard = json.loads(line)["summary"]
    res = {**job_info(job), "case_sim": case.get("sim"), "expect": case.get("expect", "arrive"),
           "family": case.get("family"), "width_m": case.get("width_m"), **metrics, "log": counts,
           "guard": guard, "oracle": oracle, "wall_s": round(time.time() - t0, 1)}
    keep = (not res.get("success")) or job["first"]
    if not keep and (d / "bag").exists():
        shutil.rmtree(d / "bag")
    (d / "result.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str))
    return res


def job_info(job: dict) -> dict:
    return {"config": job["config_name"], "scenario": job["scenario"], "seed": job["seed"]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenarios", type=Path, default=HERE / "scenarios_p0.yaml")
    ap.add_argument("--ids", default="all", help="逗号分隔的场景 id,或 all")
    ap.add_argument("--seeds", type=int, default=12)
    ap.add_argument("--seeds-for", action="append", default=[], help="id前缀=种子数,例如 p0_plaza=30")
    ap.add_argument("--config", action="append", required=True,
                    help="名字:guard=true,tight=false[,mode=A|B|C][,blind=true][,params=...][,bt=...]")
    ap.add_argument("--parallel", type=int, default=12)
    ap.add_argument("--domain-base", type=int, default=100)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    args.scenarios = args.scenarios.resolve()
    import yaml
    scs = yaml.safe_load(args.scenarios.read_text(encoding="utf-8"))["scenarios"]
    ids = [s["id"] for s in scs] if args.ids == "all" else args.ids.split(",")
    per = {}
    for item in args.seeds_for:
        pre, n = item.split("=")
        per[pre] = int(n)

    def nseeds(sid):
        best = None
        for pre, n in per.items():
            if sid.startswith(pre) and (best is None or len(pre) > len(best[0])):
                best = (pre, n)
        return best[1] if best else args.seeds

    configs = [_cfg(c) for c in args.config]
    jobs = []
    for seed in range(max(nseeds(i) for i in ids)):
        for sid in ids:
            if seed >= nseeds(sid):
                continue
            for cname, cfg in configs:
                jobs.append({"scenario": sid, "seed": seed, "config_name": cname, "config": cfg, "first": seed == 0,
                             "dir": args.out / cname / sid / f"s{seed:03d}"})
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "sweep.json").write_text(json.dumps({"scenarios": str(args.scenarios), "ids": ids,
                                                     "configs": dict(configs), "jobs": len(jobs),
                                                     "started": time.strftime("%F %T")}, ensure_ascii=False, indent=1))
    lock = threading.Lock()
    done = {"n": 0, "ok": 0, "t0": time.time()}
    slots = list(range(args.parallel))

    def worker(job):
        with lock:
            slot = slots.pop()
        try:
            r = run_one(job, slot, args)
        except Exception as e:                     # 一趟出错不拖垮整晚
            r = {"success": False, "reason": f"runner error: {e!r}"}
        finally:
            with lock:
                slots.append(slot)
        with lock:
            done["n"] += 1
            done["ok"] += 1 if r.get("success") else 0
            el = time.time() - done["t0"]
            eta = el / done["n"] * (len(jobs) - done["n"])
            (args.out / "progress.txt").write_text(
                f"{done['n']}/{len(jobs)} 完成,成功 {done['ok']};已用 {el / 3600:.1f} h,预计还要 {eta / 3600:.1f} h\n")
        return r

    with ThreadPoolExecutor(max_workers=args.parallel) as ex:
        list(ex.map(worker, jobs))
    (args.out / "progress.txt").write_text((args.out / "progress.txt").read_text() + "全部跑完\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
