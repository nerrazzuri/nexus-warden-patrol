> **两个目录**:`tools/nav_stability_bench/` 是 2026-11-06 拿到的原版 v1.1,原样保留作对照;本目录是导航 V1 实际在用的版本(修过仿真台的 bug,加了行人/车、守卫模拟、跑批 `run_sweep.py`、报告 `sweep_report.py`,口径见 `REPORT_SPEC.md`)。结果目录在 `runs/nav-*`(不入库)。

# Nexus Warden Navigation Product Simulation Gate v1.0

This is a **productization regression platform** for the current D1 Max navigation stack. It is not a pretty Gazebo demo and it is not a legged-dynamics certification. Its job is to decide whether a candidate Nav2/localization/perception change is safe enough to proceed to real-robot acceptance.

## Scope

The bench executes the repository's production `deploy/nav2/params.yaml` (Smac Lattice + MPPI) against a navigation proxy with the same production footprint: **1.03 x 0.58 m**. Gazebo supplies odometry and LiDAR. `sensor_proxy.py` converts `/scan` into the production perception interfaces `/nexwar/obs_occ` and `/nexwar/obs_free`, so obstacle-layer behavior is exercised instead of bypassed.

It validates:

- outbound + return stability;
- 90/180 degree turns;
- narrow gates, corridors, wall-side goals, U-shapes and slaloms;
- randomized start, goal and obstacle pose;
- geometric collision using the production footprint;
- minimum LiDAR clearance and commanded-but-not-moving stall time;
- planner/controller/progress failures from Nav2 logs;
- dynamic crossing obstacle injection;
- localization pose jump, yaw jump and TF dropout;
- obstacle observation delay and random drop;
- deterministic seeds and resumable long runs;
- environment + parameter fingerprints for traceability;
- automatic PASS/FAIL release report.

## What it does **not** certify

This proxy does not validate quadruped gait, grass, stairs, slip, slope, foot contact, payload vibration or outdoor weather. Those remain MuJoCo / real-robot / field acceptance items. Passing the simulation gate must never be presented as field reliability evidence.

## Target platform

Ubuntu 22.04 + ROS 2 Humble + Gazebo Fortress.

```bash
sudo apt update
sudo apt install -y \
  ros-humble-ros-gz \
  ros-humble-navigation2 \
  ros-humble-nav2-bringup
source /opt/ros/humble/setup.bash
```

## Gates

### 1. Smoke — installation sanity

```bash
python3 tools/nav_stability_bench/run_product_gate.py \
  --profile smoke --out runs/nav-gate-smoke
```

5 runs. Use after installing the simulator.

### 2. Core — daily navigation regression

```bash
python3 tools/nav_stability_bench/run_product_gate.py \
  --profile core --out runs/nav-gate-core
```

100 runs focusing on the field-sensitive return/turn/obstacle cases. Run before merging navigation parameter or behavior changes.

### 3. Release — RC simulation gate

```bash
python3 tools/nav_stability_bench/run_product_gate.py \
  --profile release --out runs/nav-gate-release
```

21 scenario families x 50 seeds = 1050 runs. Current gate:

- aggregate pass >= 99.5%;
- every scenario >= 98%;
- **0 geometric collisions**;
- **0 clearance violations**;
- P95 commanded stall <= 6 s;
- progress-checker failures <= 1 per 100 runs.

### 4. Fault — degraded-system gate

```bash
python3 tools/nav_stability_bench/run_product_gate.py \
  --profile fault --out runs/nav-gate-fault
```

Fault matrix includes:

- +0.30 m localization jump;
- +15 degree yaw jump;
- 2 s localization/TF dropout;
- 250 ms obstacle latency;
- 20% obstacle observation loss.

The point is not that navigation must ignore every fault. It must fail/recover **without collision or unsafe motion** and meet the gate in `gates.yaml`.

## Outputs

Every run is traceable:

```text
runs/nav-gate-release/
  environment.json        # git SHA, dirty state, ROS/Gazebo, params/scenario hashes
  run_manifest.json       # exact profile and fault matrix
  results.jsonl
  product_gate.json       # machine-readable PASS/FAIL
  PRODUCT_GATE.md         # human release report
  cases/<fault>/<scenario>/seed-XXXX/
    case.json
    world.sdf
    map.pgm
    map.yaml
    launch.log
    metrics.json
    result.json
```

Use `--resume` after interruption; completed cases are not repeated.

## Product release policy

Simulation is **Gate A**, not final acceptance:

1. **Gate A — simulation:** Core + Release + Fault pass.
2. **Gate B — real robot controlled area:** 30–50 consecutive mission loops, target >=95%, zero collision / dangerous motion.
3. **Gate C — site soak:** multi-day operation with real localization, networking and payload; measure interventions / 100 km and missions-between-intervention.
4. **Gate D — customer acceptance:** agreed site routes, alarms and recovery cases.

Only Gate A is implemented by this package. The framework deliberately keeps this boundary explicit so a green simulator cannot be misrepresented as a green field deployment.

## Why this matches the current field problem

The 2026-11-02 D1 Max evidence shows outbound Nav2 can be smooth while return + turn around obstacle geometry can stall, trigger progress checks, be safety-rejected, or interact badly with localization resets. The `core` profile therefore overweights return, turnaround, narrow gate and corridor cases; the `fault` profile then deliberately injects the localization/perception disturbances that exposed those failures.
