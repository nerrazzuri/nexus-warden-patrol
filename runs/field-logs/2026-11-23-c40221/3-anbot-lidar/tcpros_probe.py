# 只读：在 Orin 上不装 ROS1，直接按 TCPROS 订竞品 /rslidar_points，收 20 帧量频率和大小
import socket, struct, time, xmlrpc.client
socket.setdefaulttimeout(5)
M = "http://192.168.113.203:11311"; ME = "/nexwar_ro_probe"; T = "/rslidar_points"
m = xmlrpc.client.ServerProxy(M)
_, _, pubs = m.registerSubscriber(ME, T, "sensor_msgs/PointCloud2", "http://192.168.113.159:1/")
m.unregisterSubscriber(ME, T, "http://192.168.113.159:1/")   # 只要发布者地址，立刻注销
print("发布者", pubs)
pub = xmlrpc.client.ServerProxy(pubs[0].replace("firefly", "192.168.113.101"))
code, msg, proto = pub.requestTopic(ME, T, [["TCPROS"]])
host, port = proto[1], proto[2]
host = "192.168.113.101" if host == "firefly" else host
print("TCPROS", host, port)
def field(k, v): b = f"{k}={v}".encode(); return struct.pack("<I", len(b)) + b
hdr = b"".join(field(k, v) for k, v in [("callerid", ME), ("topic", T), ("type", "sensor_msgs/PointCloud2"),
                                         ("md5sum", "1158d486dd51d683ce2f1be655c3c181"), ("tcp_nodelay", "1")])
s = socket.create_connection((host, port)); s.sendall(struct.pack("<I", len(hdr)) + hdr)
def rd(n):
    b = bytearray()
    while len(b) < n:
        c = s.recv(n - len(b))
        if not c: raise EOFError
        b += c
    return bytes(b)
rd(struct.unpack("<I", rd(4))[0])          # 对方回的连接头
t0 = time.time(); sizes = []; stamps = []
while len(sizes) < 20:
    n = struct.unpack("<I", rd(4))[0]; msg = rd(n); sizes.append(n)
    sec, nsec = struct.unpack("<II", msg[4:12]); stamps.append(sec + nsec * 1e-9)
dt = time.time() - t0; s.close()
print(f"收 20 帧用 {dt:.2f} s → {19/dt:.1f} Hz；每帧 {sum(sizes)/len(sizes)/1e6:.2f} MB → {sum(sizes)*8/dt/1e6:.0f} Mbit/s")
print(f"时间戳 vs Orin 当前：{time.time()-stamps[-1]:+.3f} s")
