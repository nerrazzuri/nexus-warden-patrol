#!/usr/bin/env python3
"""导航 V1 第 4 步:生成「MPPI 主 + RPP 备用」那一组的 Nav2 配置(跟只有 MPPI 的正式配置比)。

- ``params/params_rpp.yaml``:正式 ``deploy/nav2/params.yaml`` 原样,控制器里多挂一个 ``RPP``
  (Regulated Pure Pursuit)。最低速度都在真机死区(0.13 m/s)以上。
- ``params/bt_rpp.xml``:正式行为树原样,只把「跟线」换成先 MPPI、MPPI 失败(没进展)再 RPP。

正式配置一改就重跑这个脚本。用法(跑一组对比):

    python3 run_sweep.py --config mppi:guard=true,mode=D \\
        --config rpp:guard=true,mode=D,params=params/params_rpp.yaml,bt=params/bt_rpp.xml ...
"""
from __future__ import annotations

from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
NAV = ROOT / "deploy" / "nav2"

RPP = {
    "plugin": "nav2_regulated_pure_pursuit_controller::RegulatedPurePursuitController",
    "desired_linear_vel": 0.4,
    "lookahead_dist": 0.6, "min_lookahead_dist": 0.3, "max_lookahead_dist": 0.9,
    "lookahead_time": 1.5, "use_velocity_scaled_lookahead_dist": False,
    "rotate_to_heading_angular_vel": 0.6, "max_angular_accel": 2.0,
    "transform_tolerance": 0.5,
    "min_approach_linear_velocity": 0.15,          # 真机 0.13 m/s 以下只踏步
    "approach_velocity_scaling_dist": 0.6,
    "use_collision_detection": True, "max_allowed_time_to_collision_up_to_carrot": 1.0,
    "use_regulated_linear_velocity_scaling": True,
    "use_cost_regulated_linear_velocity_scaling": True,
    "regulated_linear_scaling_min_radius": 0.9, "regulated_linear_scaling_min_speed": 0.15,
    "use_rotate_to_heading": True, "rotate_to_heading_min_angle": 0.785, "allow_reversing": False,
    "max_robot_pose_search_dist": 10.0,
    "cost_scaling_dist": 0.3, "cost_scaling_gain": 1.0, "inflation_cost_scaling_factor": 3.0,
}

FOLLOW_OLD = '<FollowPath path="{path}" controller_id="FollowPath"/>'
FOLLOW_NEW = ('<Fallback name="MppiThenRpp">\n'
              '            <FollowPath path="{path}" controller_id="FollowPath"/>\n'
              '            <FollowPath path="{path}" controller_id="RPP"/>\n'
              '          </Fallback>')


def main() -> int:
    params = yaml.safe_load((NAV / "params.yaml").read_text(encoding="utf-8"))
    cs = params["controller_server"]["ros__parameters"]
    cs["controller_plugins"] = ["FollowPath", "RPP"]
    cs["RPP"] = RPP
    out = HERE / "params"
    (out / "params_rpp.yaml").write_text(
        "# 自动生成(make_rpp.py),别手改:正式 deploy/nav2/params.yaml + RPP 备用控制器\n"
        + yaml.safe_dump(params, allow_unicode=True, sort_keys=False), encoding="utf-8")
    bt = (NAV / "navigate_to_pose_d1max.xml").read_text(encoding="utf-8")
    assert bt.count(FOLLOW_OLD) == 1, "正式行为树里找不到那一行 FollowPath"
    (out / "bt_rpp.xml").write_text(bt.replace(FOLLOW_OLD, FOLLOW_NEW), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
