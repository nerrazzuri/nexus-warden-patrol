import sys, rclpy
from std_srvs.srv import Trigger
rclpy.init(); n = rclpy.create_node(sys.argv[1])
n.create_service(Trigger, f"/{sys.argv[1]}/ping", lambda q, r: (setattr(r, "success", True), r)[1])
rclpy.spin(n)
