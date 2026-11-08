#!/usr/bin/env python3
"""Generate one deterministic Gazebo Fortress + Nav2 benchmark case.

The generated robot is intentionally a navigation proxy, not a D1 Max legged
physics model. Its collision envelope matches the production Nav2 footprint
(1.03 x 0.58 m) and it uses a differential-drive command interface, which is
what the current MPPI configuration assumes.
"""
from __future__ import annotations

import argparse
import json
import math
import random
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SCENARIOS = Path(__file__).with_name("scenarios.yaml")


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _scenario(doc: dict, scenario_id: str) -> tuple[dict, dict]:
    for item in doc["scenarios"]:
        if item["id"] == scenario_id:
            return doc.get("defaults", {}), item
    raise KeyError(f"unknown scenario: {scenario_id}")


def _jitter_pose(pose: list[float], rng: random.Random, xy: float, yaw_deg: float) -> list[float]:
    return [
        pose[0] + rng.uniform(-xy, xy),
        pose[1] + rng.uniform(-xy, xy),
        pose[2] + math.radians(rng.uniform(-yaw_deg, yaw_deg)),
    ]


def _jitter_obstacles(obstacles: list[dict], rng: random.Random, xy: float) -> list[dict]:
    out = []
    for obs in obstacles:
        o = dict(obs)
        o["x"] = float(o["x"]) + rng.uniform(-xy, xy)
        o["y"] = float(o["y"]) + rng.uniform(-xy, xy)
        out.append(o)
    return out


def _box_sdf(name: str, x: float, y: float, sx: float, sy: float, h: float = 1.0) -> str:
    return f"""
    <model name='{name}'>
      <static>true</static>
      <pose>{x:.5f} {y:.5f} {h/2:.3f} 0 0 0</pose>
      <link name='body'>
        <collision name='collision'><geometry><box><size>{sx:.5f} {sy:.5f} {h:.3f}</size></box></geometry></collision>
        <visual name='visual'><geometry><box><size>{sx:.5f} {sy:.5f} {h:.3f}</size></box></geometry></visual>
      </link>
    </model>"""


def _world_sdf(start: list[float], obstacles: list[dict], width: float, height: float, wall: float) -> str:
    boundary = [
        {"x": 0.0, "y": height / 2 - wall / 2, "sx": width, "sy": wall},
        {"x": 0.0, "y": -height / 2 + wall / 2, "sx": width, "sy": wall},
        {"x": width / 2 - wall / 2, "y": 0.0, "sx": wall, "sy": height},
        {"x": -width / 2 + wall / 2, "y": 0.0, "sx": wall, "sy": height},
    ]
    all_obs = boundary + obstacles
    boxes = "\n".join(_box_sdf(f"obs_{i}", **o) for i, o in enumerate(all_obs))
    x, y, yaw = start
    return f"""<?xml version='1.0'?>
<sdf version='1.8'>
  <world name='nav_bench'>
    <physics name='1ms' type='ignored'><max_step_size>0.002</max_step_size><real_time_factor>1.0</real_time_factor></physics>
    <plugin filename='libignition-gazebo-physics-system.so' name='ignition::gazebo::systems::Physics'/>
    <plugin filename='libignition-gazebo-user-commands-system.so' name='ignition::gazebo::systems::UserCommands'/>
    <plugin filename='libignition-gazebo-scene-broadcaster-system.so' name='ignition::gazebo::systems::SceneBroadcaster'/>
    <plugin filename='libignition-gazebo-sensors-system.so' name='ignition::gazebo::systems::Sensors'><render_engine>ogre2</render_engine></plugin>
    <light type='directional' name='sun'><pose>0 0 10 0 0 0</pose><diffuse>0.8 0.8 0.8 1</diffuse><direction>-0.5 0.2 -1</direction></light>
    <model name='ground'><static>true</static><link name='ground_link'><collision name='c'><geometry><plane><normal>0 0 1</normal><size>100 100</size></plane></geometry></collision><visual name='v'><geometry><plane><normal>0 0 1</normal><size>100 100</size></plane></geometry></visual></link></model>
    {boxes}
    <model name='d1max_nav_proxy'>
      <pose>{x:.5f} {y:.5f} 0.24 0 0 {yaw:.7f}</pose>
      <link name='base_link'>
        <gravity>false</gravity>
        <inertial><mass>45</mass><inertia><ixx>1.4</ixx><iyy>3.8</iyy><izz>4.5</izz></inertia></inertial>
        <collision name='body_collision'><pose>0 0 0.18 0 0 0</pose><geometry><box><size>1.03 0.58 0.36</size></box></geometry></collision>
        <visual name='body_visual'><pose>0 0 0.18 0 0 0</pose><geometry><box><size>1.03 0.58 0.36</size></box></geometry></visual>
        <sensor name='lidar' type='gpu_lidar'>
          <pose>0.40 0 0.34 0 0 0</pose><topic>scan</topic><update_rate>10</update_rate>
          <ray><scan><horizontal><samples>720</samples><resolution>1</resolution><min_angle>-3.14159</min_angle><max_angle>3.14159</max_angle></horizontal></scan><range><min>0.08</min><max>12.0</max><resolution>0.01</resolution></range></ray>
          <always_on>true</always_on><visualize>false</visualize>
        </sensor>
      </link>
      <!-- 运动学代理:直接按 cmd_vel 设速度、按真实位姿发里程计(从出生点 0,0,0 算起)。
           原来两轮差速 + 车身贴地拖着走,轮子打滑,里程计几米就漂开,Nav2 拿着错位姿导航。
           定位误差由 faulted_tf 的故障注入专门测,这里的里程计必须是真值。 -->
      <plugin filename='libignition-gazebo-velocity-control-system.so' name='ignition::gazebo::systems::VelocityControl'>
        <topic>cmd_vel</topic>
      </plugin>
      <plugin filename='libignition-gazebo-odometry-publisher-system.so' name='ignition::gazebo::systems::OdometryPublisher'>
        <odom_frame>odom</odom_frame><robot_base_frame>base_link</robot_base_frame>
        <odom_topic>odom</odom_topic><tf_topic>tf</tf_topic><odom_publish_frequency>50</odom_publish_frequency>
        <dimensions>2</dimensions>
      </plugin>
    </model>
  </world>
</sdf>
"""


def _inside_box(x: float, y: float, obs: dict, pad: float) -> bool:
    return abs(x - obs["x"]) <= obs["sx"] / 2 + pad and abs(y - obs["y"]) <= obs["sy"] / 2 + pad


def _write_map(out: Path, obstacles: list[dict], width: float, height: float, resolution: float, wall: float) -> None:
    cols = int(round(width / resolution))
    rows = int(round(height / resolution))
    boundary = [
        {"x": 0.0, "y": height / 2 - wall / 2, "sx": width, "sy": wall},
        {"x": 0.0, "y": -height / 2 + wall / 2, "sx": width, "sy": wall},
        {"x": width / 2 - wall / 2, "y": 0.0, "sx": wall, "sy": height},
        {"x": -width / 2 + wall / 2, "y": 0.0, "sx": wall, "sy": height},
    ]
    obs_all = boundary + obstacles
    vals = []
    for r in range(rows):
        y = height / 2 - (r + 0.5) * resolution
        row = []
        for c in range(cols):
            x = -width / 2 + (c + 0.5) * resolution
            occupied = any(_inside_box(x, y, o, 0.0) for o in obs_all)
            row.append("0" if occupied else "254")
        vals.append(" ".join(row))
    pgm = f"P2\n{cols} {rows}\n255\n" + "\n".join(vals) + "\n"
    (out / "map.pgm").write_text(pgm, encoding="ascii")
    map_yaml = {
        "image": "map.pgm",
        "mode": "trinary",
        "resolution": resolution,
        "origin": [-width / 2, -height / 2, 0.0],
        "negate": 0,
        "occupied_thresh": 0.65,
        "free_thresh": 0.196,
    }
    (out / "map.yaml").write_text(yaml.safe_dump(map_yaml, sort_keys=False), encoding="utf-8")



def _footprint_clearance(pose: list[float], boxes: list[dict]) -> float:
    """车身矩形(1.03 x 0.58)到最近障碍盒的距离;重叠返回负数。沿四条边取样。"""
    from goal_driver import _corners, _poly_intersects_box
    poly = _corners(*pose)
    if any(_poly_intersects_box(poly, b) for b in boxes):
        return -1.0
    best = float("inf")
    for i in range(4):
        (x1, y1), (x2, y2) = poly[i], poly[(i + 1) % 4]
        for k in range(41):
            t = k / 40.0
            x, y = x1 + (x2 - x1) * t, y1 + (y2 - y1) * t
            for b in boxes:
                dx = max(abs(x - b["x"]) - b["sx"] / 2.0, 0.0)
                dy = max(abs(y - b["y"]) - b["sy"] / 2.0, 0.0)
                best = min(best, math.hypot(dx, dy))
    return best

def generate(scenarios: Path, scenario_id: str, seed: int, out: Path) -> dict:
    doc = _load(scenarios)
    defaults, sc = _scenario(doc, scenario_id)
    rng = random.Random(seed)
    start = _jitter_pose(sc["start"], rng, float(defaults.get("start_jitter_xy_m", 0)), float(defaults.get("start_jitter_yaw_deg", 0)))
    goals = [_jitter_pose(g, rng, float(defaults.get("goal_jitter_xy_m", 0.08)), float(defaults.get("goal_jitter_yaw_deg", 5))) for g in sc["goals"]]
    obstacles = _jitter_obstacles(sc.get("obstacles", []), rng, float(defaults.get("obstacle_jitter_xy_m", 0)))
    width, height = map(float, defaults.get("map_size_m", [18, 18]))
    resolution = float(defaults.get("resolution_m", 0.05))
    wall = float(defaults.get("boundary_wall_thickness_m", 0.2))
    boundary = [
        {"x": 0.0, "y": height / 2 - wall / 2, "sx": width, "sy": wall},
        {"x": 0.0, "y": -height / 2 + wall / 2, "sx": width, "sy": wall},
        {"x": width / 2 - wall / 2, "y": 0.0, "sx": wall, "sy": height},
        {"x": -width / 2 + wall / 2, "y": 0.0, "sx": wall, "sy": height},
    ]
    min_clear = float(defaults.get("min_pose_clearance_m", 0.0))
    pose_clearance = {}
    for name, pose in [("start", start)] + [(f"goal{i}", g) for i, g in enumerate(goals)]:
        c = _footprint_clearance(pose, obstacles + boundary)
        pose_clearance[name] = round(c, 3)
        if c < min_clear:
            raise SystemExit(f"{scenario_id} seed {seed}: {name} 车身离障碍 {c:.2f} m < {min_clear} m,场景不合理")
    out.mkdir(parents=True, exist_ok=True)
    (out / "world.sdf").write_text(_world_sdf(start, obstacles, width, height, wall), encoding="utf-8")
    _write_map(out, obstacles, width, height, resolution, wall)
    manifest = {
        "scenario": scenario_id,
        "seed": seed,
        "start": start,
        "goals": goals,
        "obstacles": obstacles,
        "collision_obstacles": obstacles,
        "dynamic": bool(sc.get("dynamic", False)),
        # /odom 由 OdometryPublisher 按世界位姿发,map->odom 不用再带起点
        "odom_origin": "world",
        "pose_clearance_m": pose_clearance,
        "timeout_s": int(sc.get("timeout_s", defaults.get("timeout_s", 90))),
        "safety_min_clearance_m": float(defaults.get("safety_min_clearance_m", 0.08)),
        "params_file": str(ROOT / "deploy" / "nav2" / "params.yaml"),
    }
    (out / "case.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--scenarios", type=Path, default=DEFAULT_SCENARIOS)
    p.add_argument("--scenario", required=True)
    p.add_argument("--seed", type=int, required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    print(json.dumps(generate(a.scenarios, a.scenario, a.seed, a.out), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
