#!/bin/bash
# nexwar DDS 诊断(台式机 11-20):跟 Nav2 无关的域 62,6 个 rclpy 节点 + 1 个探针,三种配置各跑 SECS 秒。
# 用法:bash ddsdiag.sh [SECS=60]   (用跟 nexwar_nav2 一样的账号跑)
SECS=${1:-60}
W=/tmp/ddsdiag; rm -rf $W; mkdir -p $W; cd $W
cat > srv.py <<'PY'
import sys, rclpy
from std_srvs.srv import Trigger
from std_msgs.msg import UInt8MultiArray
rclpy.init()
n = rclpy.create_node(sys.argv[1])
n.create_service(Trigger, f"/{sys.argv[1]}/ping", lambda req, res: (setattr(res, "success", True), res)[1])
pub = n.create_publisher(UInt8MultiArray, "/big", 1)
big = UInt8MultiArray(); big.data = bytes(800_000)   # like the 978x832 map
if sys.argv[1] == "s0":
    n.create_timer(1.0, lambda: pub.publish(big))
rclpy.spin(n)
PY
cat > probe.py <<'PY'
import sys, time, rclpy
from std_srvs.srv import Trigger
from std_msgs.msg import UInt8MultiArray
names = sys.argv[2].split(",")
dur = float(sys.argv[1])
rclpy.init()
n = rclpy.create_node("probe")
got = [0]
n.create_subscription(UInt8MultiArray, "/big", lambda m: got.__setitem__(0, got[0] + 1), 1)
cl = {k: n.create_client(Trigger, f"/{k}/ping") for k in names}
t0 = time.monotonic(); fails = 0; rounds = 0; first_ok = None
while time.monotonic() - t0 < dur:
    rounds += 1; bad = []
    for k, c in cl.items():
        f = c.call_async(Trigger.Request())
        end = time.monotonic() + 1.5
        while not f.done() and time.monotonic() < end:
            rclpy.spin_once(n, timeout_sec=0.05)
        if not f.done():
            bad.append(k)
    if bad:
        fails += 1
        print(f"{time.monotonic()-t0:6.1f}s missing {bad}", flush=True)
    elif first_ok is None:
        first_ok = time.monotonic() - t0
    end = time.monotonic() + 2
    while time.monotonic() < end:
        rclpy.spin_once(n, timeout_sec=0.1)
print(f"RESULT rounds={rounds} bad_rounds={fails} first_all_ok={first_ok} big_msgs={got[0]}", flush=True)
PY
cat > shm.xml <<'XML'
<?xml version="1.0" encoding="UTF-8" ?>
<!--
  我们 Nav2 这个域(61)的 FastDDS 传输(真机 11-20 C40221 商场):ROS_LOCALHOST_ONLY=1 时 Humble 的
  rmw_fastrtps 只开 127.0.0.1 上的 UDP、不开共享内存;商场图 978×832 一条 /map、代价地图约 800 KB,
  比接收缓冲(rmem_default 212992)还大,冲爆缓冲(UDP receive buffer errors 启动十几秒 +2190),
  心跳、服务回话、发现包跟着丢,节点互相失联。
  这里:数据走共享内存(段 16 MB,装得下整张图),UDP 只留本机(跟 ROS_LOCALHOST_ONLY 一样只认
  127.0.0.1)。nexwar_nav2_start 在 NEXWAR_NAV2_DDS=shm 时用它(同时不设 ROS_LOCALHOST_ONLY,不然
  rmw 会把这里的传输换掉)。
-->
<profiles xmlns="http://www.eprosima.com/XMLSchemas/fastRTPS_Profiles">
  <transport_descriptors>
    <transport_descriptor>
      <transport_id>nexwar_shm</transport_id>
      <type>SHM</type>
      <segment_size>16777216</segment_size>
    </transport_descriptor>
    <transport_descriptor>
      <transport_id>nexwar_udp_lo</transport_id>
      <type>UDPv4</type>
      <interfaceWhiteList>
        <address>127.0.0.1</address>
      </interfaceWhiteList>
      <maxInitialPeersRange>64</maxInitialPeersRange>
    </transport_descriptor>
  </transport_descriptors>
  <participant profile_name="nexwar_nav2" is_default_profile="true">
    <rtps>
      <builtin>
        <initialPeersList>
          <locator>
            <udpv4>
              <address>127.0.0.1</address>
            </udpv4>
          </locator>
        </initialPeersList>
      </builtin>
      <userTransports>
        <transport_id>nexwar_shm</transport_id>
        <transport_id>nexwar_udp_lo</transport_id>
      </userTransports>
      <useBuiltinTransports>false</useBuiltinTransports>
    </rtps>
  </participant>
</profiles>
XML
cat > udp.xml <<'XML'
<?xml version="1.0" encoding="UTF-8" ?>
<!--
  我们 Nav2 这个域(61)的 FastDDS 传输(真机 11-20 C40221 商场):ROS_LOCALHOST_ONLY=1 时 Humble 的
  rmw_fastrtps 只开 127.0.0.1 上的 UDP、不开共享内存;商场图 978×832 一条 /map、代价地图约 800 KB,
  比接收缓冲(rmem_default 212992)还大,冲爆缓冲(UDP receive buffer errors 启动十几秒 +2190),
  心跳、服务回话、发现包跟着丢,节点互相失联。
  这里:数据走共享内存(段 16 MB,装得下整张图),UDP 只留本机(跟 ROS_LOCALHOST_ONLY 一样只认
  127.0.0.1)。nexwar_nav2_start 在 NEXWAR_NAV2_DDS=shm 时用它(同时不设 ROS_LOCALHOST_ONLY,不然
  rmw 会把这里的传输换掉)。
-->
<profiles xmlns="http://www.eprosima.com/XMLSchemas/fastRTPS_Profiles">
  <transport_descriptors>
    <transport_descriptor>
      <transport_id>nexwar_udp_lo</transport_id>
      <type>UDPv4</type>
      <interfaceWhiteList>
        <address>127.0.0.1</address>
      </interfaceWhiteList>
      <maxInitialPeersRange>64</maxInitialPeersRange>
    </transport_descriptor>
  </transport_descriptors>
  <participant profile_name="nexwar_nav2" is_default_profile="true">
    <rtps>
      <builtin>
        <initialPeersList>
          <locator>
            <udpv4>
              <address>127.0.0.1</address>
            </udpv4>
          </locator>
        </initialPeersList>
      </builtin>
      <userTransports>
        <transport_id>nexwar_udp_lo</transport_id>
      </userTransports>
      <useBuiltinTransports>false</useBuiltinTransports>
    </rtps>
  </participant>
</profiles>
XML
. /opt/ros/humble/setup.bash
export ROS_DOMAIN_ID=62 RMW_IMPLEMENTATION=rmw_fastrtps_cpp
echo "== /dev/shm fastrtps 文件数: $(ls /dev/shm | grep -c fastrtps)"
run() {
  name=$1; shift
  ( export "$@"
    pids=()
    for i in 0 1 2 3 4 5; do python3 srv.py s$i >/dev/null 2>&1 & pids+=($!); sleep 0.3; done
    sleep 2
    python3 probe.py $SECS s0,s1,s2,s3,s4,s5 2>&1 | grep -E "RESULT|missing" | tail -6 | sed "s/^/[$name] /"
    echo "[$name] node list: $(timeout 20 ros2 node list --no-daemon 2>/dev/null | sort | tr '\n' ' ')"
    kill "${pids[@]}" 2>/dev/null; wait 2>/dev/null )
}
run udp ROS_LOCALHOST_ONLY=0 FASTRTPS_DEFAULT_PROFILES_FILE=$W/udp.xml
run shm ROS_LOCALHOST_ONLY=0 FASTRTPS_DEFAULT_PROFILES_FILE=$W/shm.xml
run localhost ROS_LOCALHOST_ONLY=1
echo "== 完。每行 RESULT:bad_rounds=0 且 big_msgs≈秒数 = 这种配置通;node list 应有 /s0…/s5"
