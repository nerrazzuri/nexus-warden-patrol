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

    params = ParameterFile(
        RewrittenYaml(
            source_file=params_file,
            param_rewrites={
                "use_sim_time": "true",
                "autostart": "true",
                "yaml_filename": map_yaml,
                "default_nav_to_pose_bt_xml": str(nav_dir / "navigate_to_pose_d1max.xml"),
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
        ExecuteProcess(cmd=["ign", "gazebo", "-r", "-s", world], output="screen", condition=UnlessCondition(gui)),
        ExecuteProcess(cmd=["ign", "gazebo", "-r", world], output="screen", condition=IfCondition(gui)),
        Node(package="ros_gz_bridge", executable="parameter_bridge", name="nav_bench_bridge",
             arguments=bridge_args, output="screen"),
        ExecuteProcess(cmd=["/usr/bin/python3", str(here / "faulted_tf.py"),
                            "--at-s", fault_at, "--duration-s", fault_duration,
                            "--jump-m", pose_jump, "--yaw-deg", yaw_jump,
                            "--dropout-s", tf_dropout,
                            "--start-x", start_x, "--start-y", start_y,
                            "--start-yaw", start_yaw], output="screen"),
        ExecuteProcess(cmd=["/usr/bin/python3", str(here / "sensor_proxy.py"),
                            "--seed", seed, "--delay-ms", obs_delay,
                            "--drop-rate", obs_drop, "--dynamic", dynamic], output="screen"),
        Node(package="nav2_map_server", executable="map_server", name="map_server", output="screen",
             parameters=[params, {"yaml_filename": map_yaml}]),
        nav2("nav2_controller", "controller_server"),
        nav2("nav2_planner", "planner_server"),
        nav2("nav2_behaviors", "behavior_server"),
        nav2("nav2_bt_navigator", "bt_navigator"),
        Node(package="nav2_lifecycle_manager", executable="lifecycle_manager",
             name="lifecycle_manager_navigation", output="screen",
             parameters=[{"use_sim_time": True}, {"autostart": True}, {"node_names": lifecycle_nodes}]),
    ])
