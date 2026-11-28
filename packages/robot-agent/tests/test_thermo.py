"""1.1-6 热像测温:读 ISAPI 回的最高温度(JSON、XML 都认,按名字找);
连着两次过线才报(高温 → 起火能升级);降回高温线 5 °C 以下连着三次才报回落;
问不到连着 6 次报一次,问到了报恢复;Digest 账号口令取 RTSP 地址里的;
cameras.json 的 thermometry 写错了代理不起。"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from nexwar_agent.thermo import ThermoError, ThermoWatch, isapi_reader, max_temperature
from nexwar_agent.video_push import CameraConfigError, load_cameras


def test_最高温度_JSON和XML都认_按名字找():
    j = {"ThermometryRulesTemperatureInfoList": {"ThermometryRulesTemperatureInfo": [
        {"id": 1, "maxTemperature": 36.5, "minTemperature": 20.1},
        {"id": 2, "maxTemperature": 88.2, "averageTemperature": 40}]}}
    assert max_temperature(json.dumps(j).encode()) == 88.2
    x = (b'<?xml version="1.0"?><ThermometryRulesTemperatureInfoList xmlns="http://www.hikvision.com">'
         b"<ThermometryRulesTemperatureInfo><maxTemperature>151.0</maxTemperature>"
         b"<minTemperature>10</minTemperature></ThermometryRulesTemperatureInfo>"
         b"</ThermometryRulesTemperatureInfoList>")
    assert max_temperature(x) == 151.0
    with pytest.raises(ThermoError, match="测温规则"):
        max_temperature(b'{"minTemperature": 3}')
    with pytest.raises(ThermoError):
        max_temperature(b"{bad")


def _表(mono):
    ev = []
    box = {"c": 0.0}

    async def read():
        if isinstance(box["c"], Exception):
            raise box["c"]
        return box["c"]
    w = ThermoWatch(read, emit=lambda k, d: ev.append((k, d)), mono=lambda: mono[0],
                    hot_c=70, fire_c=150)
    return w, ev, box


async def test_两次过线才报_高温升到起火_回落要连着三次低于65():
    mono = [0.0]
    w, ev, box = _表(mono)

    async def feed(*cs):
        for c in cs:
            box["c"] = c
            await w.step()
            mono[0] += w.every_s
    await feed(30, 75, 40, 75)
    assert ev == [], "一次过线不算"
    await feed(80)
    assert ev == [("thermal_hot", {"level": "hot", "max_c": 80, "hot_c": 70.0, "fire_c": 150.0})]
    await feed(160)
    assert len(ev) == 1
    await feed(170)
    assert ev[-1][0] == "thermal_hot" and ev[-1][1]["level"] == "fire" and w.level == "fire"
    await feed(68, 60, 60)
    assert ev[-1][1]["level"] == "fire", "68 没低于 65:不算回落"
    await feed(60)
    assert ev[-1] == ("thermal_normal", {"max_c": 60, "peak_c": 170, "was": "fire"})
    assert w.level == "normal"


async def test_问不到连着6次报一次_问到了报恢复_没到点不问():
    mono = [0.0]
    w, ev, box = _表(mono)
    box["c"] = ThermoError("连不上热像:timed out")
    for _ in range(8):
        await w.step()
        mono[0] += w.every_s
    assert ev == [("thermometry_failed", {"reason": "连不上热像:timed out", "times": 6})]
    box["c"] = 30.0
    await w.step()
    assert ev[-1] == ("thermometry_ok", {"max_c": 30.0}) and w.last_c == 30.0
    await w.step()
    assert len(ev) == 2 and not w.due(), "没到点不问"


def test_Digest账号口令取RTSP地址里的():
    seen = []

    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            auth = self.headers.get("Authorization") or ""
            seen.append((self.path, auth[:6]))
            if not auth.startswith("Digest"):
                self.send_response(401)
                self.send_header("WWW-Authenticate",
                                 'Digest realm="thermal", nonce="abc", qop="auth"')
                self.end_headers()
                return
            assert 'username="admin"' in auth
            body = b'{"maxTemperature": 42.5}'
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass
    srv = HTTPServer(("127.0.0.1", 0), H)
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()
    import asyncio
    read = isapi_reader("rtsp://admin:p%40ss@127.0.0.1:554/ch1", port=srv.server_port,
                        path="/ISAPI/Thermal/x?format=json")
    assert asyncio.run(read()) == 42.5
    srv.shutdown()
    assert seen[0] == ("/ISAPI/Thermal/x?format=json", "") and seen[-1][1] == "Digest"


def test_cameras_json的thermometry(tmp_path):
    p = tmp_path / "c.json"
    p.write_text(json.dumps({"thermal": {"url": "rtsp://u:p@10.0.0.5:554/ch1",
                                         "thermometry": {"hot_c": 60, "fire_c": 120}}}))
    got = load_cameras(p)["thermal"]["thermometry"]
    assert got == {"path": "/ISAPI/Thermal/channels/2/thermometry/1/rulesTemperatureInfo"
                           "?format=json", "port": 80, "hot_c": 60.0, "fire_c": 120.0}
    p.write_text(json.dumps({"thermal": {"url": "rtsp://u:p@10.0.0.5:554/ch1"}}))
    assert "thermometry" not in load_cameras(p)["thermal"], "不写就不测温"
    for bad in ({"hot_c": 200, "fire_c": 120}, {"path": "/x"}, {"port": 0}, {"what": 1}):
        p.write_text(json.dumps({"thermal": {"url": "rtsp://u:p@10.0.0.5:554/ch1",
                                             "thermometry": bad}}))
        with pytest.raises(CameraConfigError):
            load_cameras(p)
    p.write_text(json.dumps({"front": {"url": "rtsp://10.0.0.6/x", "thermometry": {}}}))
    with pytest.raises(CameraConfigError, match="只给热像"):
        load_cameras(p)
