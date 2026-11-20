import sys, time, rclpy
from std_srvs.srv import Trigger
rclpy.init(); n = rclpy.create_node("probe")
cl = {k: n.create_client(Trigger, f"/{k}/ping") for k in ("s0", "s1")}
t0 = time.monotonic()
while time.monotonic() - t0 < float(sys.argv[1]):
    bad = []
    for k, c in cl.items():
        f = c.call_async(Trigger.Request()); end = time.monotonic() + 1.0
        while not f.done() and time.monotonic() < end:
            rclpy.spin_once(n, timeout_sec=0.05)
        if not f.done(): bad.append(k)
    print(f"{time.monotonic()-t0:6.1f} nodes={len(n.get_node_names())} bad={bad}", flush=True)
    time.sleep(1.0)
