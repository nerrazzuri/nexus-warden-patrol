# 只读抓取：不在竞品上落盘，全部写 stdout（JSON 行；点云按 float32 x,y,z,intensity + uint16 ring 打包成 base64）
import sys, json, time, base64, struct, math, rospy
from sensor_msgs.msg import PointCloud2, LaserScan
import sensor_msgs.point_cloud2 as pc2
SECS = float(sys.argv[1]) if len(sys.argv) > 1 else 20
rospy.init_node('nexwar_ro_cap', anonymous=True, disable_signals=True)
out = sys.stdout
def emit(d): out.write(json.dumps(d, ensure_ascii=False) + "\n"); out.flush()
n = {'pc': 0}
def on_pc(m):
    if n['pc'] >= int(SECS):     # 约每秒存 1 帧
        return
    if time.time() - n.get('t', 0) < 0.95: return
    n['t'] = time.time(); n['pc'] += 1
    buf = bytearray()
    for x, y, z, i, r in pc2.read_points(m, ('x', 'y', 'z', 'intensity', 'ring'), skip_nans=True):
        buf += struct.pack('<ffffH', x, y, z, i, int(r))
    emit({'t': 'rslidar', 'stamp': m.header.stamp.to_sec(), 'recv': time.time(), 'frame': m.header.frame_id,
          'n': len(buf) // 18, 'fmt': '<ffffH', 'data': base64.b64encode(bytes(buf)).decode()})
def on_scan(topic):
    def f(m):
        emit({'t': topic, 'stamp': m.header.stamp.to_sec(), 'recv': time.time(), 'frame': m.header.frame_id,
              'amin': m.angle_min, 'ainc': m.angle_increment, 'rmin': m.range_min, 'rmax': m.range_max,
              'ranges': [None if (math.isinf(r) or math.isnan(r)) else round(r, 3) for r in m.ranges]})
    return f
rospy.Subscriber('/rslidar_points', PointCloud2, on_pc, queue_size=1, buff_size=2**24)
for t in ('/anbot/obstacle/laser', '/anbot/obstacle/laser2stop', '/pclob/scan2', '/kinect_scan'):
    rospy.Subscriber(t, LaserScan, on_scan(t), queue_size=5)
end = time.time() + SECS
while time.time() < end: time.sleep(0.2)
emit({'t': 'end', 'recv': time.time()})
