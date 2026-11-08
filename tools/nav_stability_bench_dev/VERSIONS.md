# Validated target stack

The benchmark is authored for the Nexus Warden deployment baseline:

- Ubuntu 22.04
- ROS 2 Humble
- Gazebo Fortress / `ign gazebo`
- `ros_gz_bridge`
- Nav2 Humble
- production `deploy/nav2/params.yaml`

Before comparing two benchmark reports, compare `environment.json`. A result is not directly comparable when the ROS/Gazebo major stack, production params hash, or scenarios hash differs.

The benchmark itself intentionally does not pin Debian package patch numbers. The exact installed versions are part of the run evidence; a release organization may additionally freeze them in its golden runner image.
