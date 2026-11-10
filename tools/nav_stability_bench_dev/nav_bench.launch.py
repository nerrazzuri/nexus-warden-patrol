"""Gazebo Fortress + production Nav2 + production perception-topic proxy."""
from pathlib import Path

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess
from launch.substitutions import LaunchConfiguration
from launch.conditions import IfCondition, UnlessCondition
from launch_ros.actions import Node
from launch_ros.descriptions import ParameterFile
from nav2_common.launch import RewrittenYaml


def generate_launch_description():
    here = Path(__file__).resolve().parent
    root = here.parents[1]
    nav_dir = root / "deploy" / "nav2"

    world = LaunchConfiguration("world")
    map_yaml = LaunchConfiguration("map")
    params_file = LaunchConfiguration("params_file")
    seed = LaunchConfiguration("seed")
    fault_at = LaunchConfiguration("fault_at_s")
    fault_duration = LaunchConfiguration("fault_duration_s")
    pose_jump = LaunchConfiguration("pose_jump_m")
    yaw_jump = LaunchConfiguration("yaw_jump_deg")
    tf_dropout = LaunchConfiguration("tf_dropout_s")
    obs_delay = LaunchConfiguration("obstacle_delay_ms")
    obs_drop = LaunchConfiguration("obstacle_drop_rate")
    dynamic = LaunchConfiguration("dynamic")
    gui = LaunchConfiguration("gui")
    start_x = LaunchConfiguration("start_x")
    start_y = LaunchConfiguration("start_y")
    start_yaw = LaunchConfiguration("start_yaw")
    case_json = LaunchConfiguration("case_json")
    agent_guard = LaunchConfiguration("agent_guard")
    guard_log = LaunchConfiguration("guard_log")
    guard_tight = LaunchConfiguration("guard_tight")
    guard_mode = LaunchConfiguration("guard_mode")
    blind_band = LaunchConfiguration("blind_band")
    exec_noise = LaunchConfiguration("exec_noise")
    fault_trigger = LaunchConfiguration("fault_trigger")
    lateral_m = LaunchConfiguration("lateral_m")
    loc_noise_m = LaunchConfiguration("loc_noise_m")
    loc_noise_deg = LaunchConfiguration("loc_noise_deg")

    params = ParameterFile(
        RewrittenYaml(
            source_file=params_file,
            param_rewrites={
                "use_sim_time": "true",
                "autostart": "true",
                "yaml_filename": map_yaml,
                "default_nav_to_pose_bt_xml": LaunchConfiguration("bt_xml"),
                "default_nav_through_poses_bt_xml": str(nav_dir / "navigate_through_poses_d1max.xml"),
            },
            convert_types=True,
        ), allow_substs=True,
    )

    def nav2(package, executable, remap=()):
        return Node(package=package, executable=executable, name=executable, output="screen",
                    parameters=[params], remappings=list(remap))

    bridge_args = [
        "/clock@rosgraph_msgs/msg/Clock[ignition.msgs.Clock",
        "/odom@nav_msgs/msg/Odometry[ignition.msgs.Odometry",
        "/tf@tf2_msgs/msg/TFMessage[ignition.msgs.Pose_V",
        "/scan@sensor_msgs/msg/LaserScan[ignition.msgs.LaserScan",
        "/cmd_vel@geometry_msgs/msg/Twist]ignition.msgs.Twist",
    ]
    lifecycle_nodes = ["map_server", "controller_server", "planner_server", "behavior_server", "bt_navigator"]

    return LaunchDescription([
        DeclareLaunchArgument("world"), DeclareLaunchArgument("map"),
        DeclareLaunchArgument("params_file", default_value=str(nav_dir / "params.yaml")),
        # 导航 V1 第 4 步:换行为树(MPPI 失败再 RPP,见 make_rpp.py)
        DeclareLaunchArgument("bt_xml", default_value=str(nav_dir / "navigate_to_pose_d1max.xml")),
        DeclareLaunchArgument("seed", default_value="0"),
        DeclareLaunchArgument("fault_at_s", default_value="1000000000"),
        DeclareLaunchArgument("fault_duration_s", default_value="2.0"),
        DeclareLaunchArgument("pose_jump_m", default_value="0.0"),
        DeclareLaunchArgument("yaw_jump_deg", default_value="0.0"),
        DeclareLaunchArgument("tf_dropout_s", default_value="0.0"),
        DeclareLaunchArgument("obstacle_delay_ms", default_value="0.0"),
        DeclareLaunchArgument("obstacle_drop_rate", default_value="0.0"),
        DeclareLaunchArgument("dynamic", default_value="false"),
        DeclareLaunchArgument("gui", default_value="false"),
        DeclareLaunchArgument("start_x", default_value="0.0"),
        DeclareLaunchArgument("start_y", default_value="0.0"),
        DeclareLaunchArgument("start_yaw", default_value="0.0"),
        DeclareLaunchArgument("case_json", default_value=""),
        # true:Nav2 的速度(控制器、脱困动作)先过正式代码的守卫(agent_guard.py)再给机器人
        DeclareLaunchArgument("agent_guard", default_value="false"),
        # 守卫模式:A 现在的 / B 软守卫(余量随速度缩放 + 放行/减速/停)/ C 只管紧急停
        DeclareLaunchArgument("guard_mode", default_value="A"),
        # true:Nav2 的障碍数据去掉机身两侧盲带(跟真机一样)
        DeclareLaunchArgument("blind_band", default_value="false"),
        DeclareLaunchArgument("guard_log", default_value=""),
        DeclareLaunchArgument("guard_tight", default_value="false"),
        # 执行误差(exec_model.py)、定位噪声、按位置/转身触发的定位故障(faulted_tf.py)
        DeclareLaunchArgument("exec_noise", default_value="false"),
        DeclareLaunchArgument("fault_trigger", default_value="time"),
        DeclareLaunchArgument("lateral_m", default_value="0.0"),
        DeclareLaunchArgument("loc_noise_m", default_value="0.0"),
        DeclareLaunchArgument("loc_noise_deg", default_value="0.0"),
        ExecuteProcess(cmd=["ign", "gazebo", "-r", "-s", world], output="screen", condition=UnlessCondition(gui)),
        ExecuteProcess(cmd=["ign", "gazebo", "-r", world], output="screen", condition=IfCondition(gui)),
        Node(package="ros_gz_bridge", executable="parameter_bridge", name="nav_bench_bridge",
             arguments=bridge_args, output="screen", condition=UnlessCondition(exec_noise)),
        # 有执行误差时:/cmd_vel → exec_model → /cmd_vel_exec → 仿真里的机器人
        Node(package="ros_gz_bridge", executable="parameter_bridge", name="nav_bench_bridge",
             arguments=bridge_args, output="screen", remappings=[("/cmd_vel", "/cmd_vel_exec")],
             condition=IfCondition(exec_noise)),
        ExecuteProcess(cmd=["/usr/bin/python3", str(here / "exec_model.py"), "--seed", seed],
                       output="screen", condition=IfCondition(exec_noise)),
        ExecuteProcess(cmd=["/usr/bin/python3", str(here / "faulted_tf.py"),
                            "--at-s", fault_at, "--duration-s", fault_duration,
                            "--jump-m", pose_jump, "--yaw-deg", yaw_jump,
                            "--dropout-s", tf_dropout,
                            "--start-x", start_x, "--start-y", start_y,
                            "--start-yaw", start_yaw, "--trigger", fault_trigger,
                            "--lateral-m", lateral_m, "--noise-m", loc_noise_m, "--noise-deg", loc_noise_deg,
                            "--seed", seed], output="screen"),
        ExecuteProcess(cmd=["/usr/bin/python3", str(here / "sensor_proxy.py"),
                            "--seed", seed, "--delay-ms", obs_delay,
                            "--drop-rate", obs_drop, "--dynamic", dynamic, "--blind-band", blind_band],
                       output="screen"),
        # 行人/车辆:按 case.json 的 actors 让它们动(没有就只发空位置表)
        ExecuteProcess(cmd=["/usr/bin/python3", str(here / "actor_driver.py"), "--case", case_json],
                       output="screen"),
        Node(package="nav2_map_server", executable="map_server", name="map_server", output="screen",
             parameters=[params, {"yaml_filename": map_yaml}]),
        Node(package="nav2_controller", executable="controller_server", name="controller_server", output="screen",
             parameters=[params], remappings=[("cmd_vel", "cmd_vel_nav")], condition=IfCondition(agent_guard)),
        Node(package="nav2_controller", executable="controller_server", name="controller_server", output="screen",
             parameters=[params], condition=UnlessCondition(agent_guard)),
        Node(package="nav2_behaviors", executable="behavior_server", name="behavior_server", output="screen",
             parameters=[params], remappings=[("cmd_vel", "cmd_vel_nav")], condition=IfCondition(agent_guard)),
        Node(package="nav2_behaviors", executable="behavior_server", name="behavior_server", output="screen",
             parameters=[params], condition=UnlessCondition(agent_guard)),
        ExecuteProcess(cmd=["/usr/bin/python3", str(here / "agent_guard.py"), "--case", case_json,
                            "--log", guard_log, "--tight", guard_tight, "--mode", guard_mode,
                            "--delay-ms", obs_delay], output="screen", condition=IfCondition(agent_guard)),
        nav2("nav2_planner", "planner_server"),
        nav2("nav2_bt_navigator", "bt_navigator"),
        Node(package="nav2_lifecycle_manager", executable="lifecycle_manager",
             name="lifecycle_manager_navigation", output="screen",
             parameters=[{"use_sim_time": True}, {"autostart": True}, {"node_names": lifecycle_nodes}]),
    ])
