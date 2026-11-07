"""网页易用性第 1 轮 P0-18:几个人同时用就断连、样式加载失败。

监听队列是标准库默认的 5(浏览器一开页面就并发十几个请求,排不上的被拒);同一地址只许 16 条连接,
一个浏览器开两三个标签(每个标签有事件流、两三路实时画面)就满了,后来的请求(包括样式表)被直接关掉。
"""

from __future__ import annotations

import socket
import threading
from http.server import BaseHTTPRequestHandler

from nexwar_site.tlsserve import TlsThreadingServer


class _Slow(BaseHTTPRequestHandler):
    hold = threading.Event()

    def do_GET(self):  # noqa: N802
        self.hold.wait(5)
        self.send_response(200)
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *a):
        pass


def test_监听队列和每个地址的连接上限够一个值班台开几个标签():
    s = TlsThreadingServer(("127.0.0.1", 0), _Slow, ctx=None)
    try:
        assert s.request_queue_size >= 128
        assert s._per_ip_max >= 48
    finally:
        s.server_close()


def test_同一地址同时开40条长连接_都能接上():
    s = TlsThreadingServer(("127.0.0.1", 0), _Slow, ctx=None)
    t = threading.Thread(target=s.serve_forever, daemon=True)
    t.start()
    socks = []
    try:
        for _ in range(40):
            c = socket.create_connection(s.server_address, timeout=5)
            c.sendall(b"GET / HTTP/1.1\r\nHost: x\r\n\r\n")
            socks.append(c)
        _Slow.hold.set()
        got = [c.recv(64) for c in socks]
        assert all(g.startswith(b"HTTP/1.0 200") or g.startswith(b"HTTP/1.1 200") for g in got), got[:3]
    finally:
        _Slow.hold.set()
        for c in socks:
            c.close()
        s.shutdown()
        s.server_close()
