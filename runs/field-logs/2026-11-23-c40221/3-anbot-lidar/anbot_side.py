# 只读：收 5 帧竞品 16 线，左(60–120°)右(240–300°)扇区里去掉 0.35 m 以内(自己)的点，报最近水平距离和那些点的高度范围
import math, rospy, sensor_msgs.point_cloud2 as pc2
from sensor_msgs.msg import PointCloud2
rospy.init_node('nexwar_ro_side', anonymous=True, disable_signals=True)
res = {'左': [], '右': []}
for _ in range(5):
    m = rospy.wait_for_message('/rslidar_points', PointCloud2, timeout=3)
    best = {'左': (99, None), '右': (99, None)}
    near = {'左': [], '右': []}
    for x, y, z in pc2.read_points(m, ('x', 'y', 'z'), skip_nans=True):
        r = math.hypot(x, y)
        if r < 0.35 or r > 3.0: continue
        a = (math.degrees(math.atan2(y, x)) + 360) % 360
        s = '左' if 60 <= a <= 120 else '右' if 240 <= a <= 300 else None
        if not s: continue
        if r < best[s][0]: best[s] = (r, z)
        if r < 1.5: near[s].append(z)
    for s in res: res[s].append((best[s][0], len(near[s]), (min(near[s]), max(near[s])) if near[s] else None))
for s, v in res.items():
    rs = [b[0] for b in v]; zs = [b[2] for b in v if b[2]]
    print(f"16线 {s}侧 最近 {min(rs):.2f}–{max(rs):.2f} m，1.5 m 内点数 {[b[1] for b in v]}，这些点高度(相对雷达) {min(z[0] for z in zs):.2f}..{max(z[1] for z in zs):.2f} m" if zs else f"16线 {s}侧 1.5 m 内没点，最近 {min(rs):.2f} m")
