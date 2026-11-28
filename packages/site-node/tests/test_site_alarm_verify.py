"""1.1-3 现有报警器一响 → 派机器人去核实。

- 门磁、报警主机登记时默认「先核实」:报警先报 P2「报警器报警:机器人去核实」,不是 P1。
- 机器人看见人(``dog_sees_person``)→ 关 P2,写「看见人了」;到了 30 秒没看见人 → 关 P2、标误报;
  没到现场 → 另报 P1「无机器人去」。
- 不会签名的设备:触发网址(口令只给一次、只存哈希)、报警主机 SIA DC-09、IO 模块干接点(Modbus TCP,
  去抖、常闭、读不到报 P2)。
"""

from __future__ import annotations

import json
import socket
import struct
import threading

import pytest
from test_site_incidents import 站, 签  # noqa: F401  (夹具)
from test_site_w73_devices import MAP, 设备  # noqa: F401  (夹具)

from nexwar_site import alarm_in
from nexwar_site.alarm_in import AlarmInputs, crc16, frame, parse_sia, read_inputs
from nexwar_site.alert_sources import SiteAlertSources
from nexwar_site.alert_store import AlertDesk
from nexwar_site.devices import DeviceError
from nexwar_site.incidents import VERIFY_HOLD_MS


@pytest.fixture
def 核(设备):  # noqa: F811
    t = 设备
    t.alerts = AlertDesk(t.db, now_ms=t.clock)
    t.src = SiteAlertSources(t.alerts, now_ms=t.clock)
    t.desk.on_outcome = t.src.on_incident
    t.desk.on_verdict = t.src.on_verdict
    fired = []

    def fire(source, body):
        fired.append((source, body))
        return {"outcome": "noted"}
    t.fired = fired
    t.rx = AlarmInputs(t.db, fire=fire, now_ms=t.clock, background=False)
    return t


def _门磁(t, dev="door-1", **kw):
    return t.book.put(dev, {"kind": "contact", "map_id": MAP[0], "map_version": MAP[1],
                            "x": 3.0, "y": 1.0, **kw}, by="alice")


async def _触发(t, dev="door-1"):
    body = t.desk.prepare(f"dev-{dev}", {"event_id": f"e{t.clock()}", "type": "intrusion",
                                         "zone": "-"})
    return await t.send(t.desk.handle(f"dev-{dev}", body))


def _能看(t, rid="A", state="ok"):
    """模拟机器人没有人员检测:核实要它「在看」才算数(外审 1.1 第 2 轮 #1),测试里给它补上。"""
    t.desk.dispatcher.clients[rid].capabilities.tasks["persons"] = {"state": state,
                                                                    "present": False}


def _开着(t, kind):
    return [a for a in t.alerts.book.open() if a.kind == kind]


async def test_门磁默认先核实_报P2不报P1_到了没看见人_关掉标误报(核):
    t = 核
    await t.run(12)
    assert _门磁(t)["device"]["verify_first"] is True
    cam = t.book.put("cam-1", {"kind": "camera", "map_id": MAP[0], "map_version": MAP[1],
                               "x": 0.0, "y": 0.0}, by="alice")["device"]
    assert cam["verify_first"] is False, "摄像头(AI 判过的)照旧直接 P1"
    r = await _触发(t)
    assert r["outcome"] == "dispatched" and r["verify"] == 1
    [v] = _开着(t, "intrusion_verifying")
    assert v.level.name == "P2" and "报警器报警:A 去核实" in v.title
    assert not _开着(t, "intrusion")
    await t.run(200)                                     # 走到了
    assert t.desk.list()[0]["result"] == "done"
    _能看(t)
    assert t.desk.verify_tick() == 0, "到了还要再看 30 秒"
    t.clock.advance(VERIFY_HOLD_MS / 1000 + 1)
    assert t.desk.verify_tick() == 1
    assert not _开着(t, "intrusion_verifying")
    done = t.alerts.book.get(v.key)
    assert done.verdict == "false_alarm" and done.resolved_by == "site:verify"
    assert t.desk.list()[0]["verdict"] == "clear"
    assert t.desk.verify_tick() == 0, "下过结论的不再下"


async def test_核实时看见人_关P2写看见人了_不另报(核):
    t = 核
    await t.run(12)
    _门磁(t)
    await _触发(t)
    t.alerts.raise_alert(kind="dog_sees_person", robot="A", title="机器人看见人了")
    assert t.desk.verify_tick() == 1
    assert not _开着(t, "intrusion_verifying") and _开着(t, "dog_sees_person")
    assert t.desk.list()[0]["verdict"] == "person"


async def test_机器人没到现场_另报P1无机器人去(核):
    t = 核
    await t.run(12)
    _门磁(t)
    r = await _触发(t)
    with t.db.tx() as c:
        c.execute("UPDATE incidents SET result='aborted', result_ms=? WHERE id=?",
                  (t.clock(), r["id"]))
    assert t.desk.verify_tick() == 1
    [p1] = _开着(t, "intrusion_unanswered")
    assert p1.level.name == "P1" and "没核实成" in p1.title
    assert not _开着(t, "intrusion_verifying")


async def test_关掉先核实_照旧直接P1(核):
    t = 核
    await t.run(12)
    _门磁(t, verify_first=False)
    await _触发(t)
    assert _开着(t, "intrusion") and not _开着(t, "intrusion_verifying")


def test_触发网址_口令只给一次_只存哈希_对得上才认(核):
    t = 核
    got = _门磁(t, link={"via": "url"})
    tok = got["token"]
    assert len(tok) == 32
    raw = t.db.query("SELECT token_hash FROM ext_devices")[0]["token_hash"]
    assert tok not in raw and raw == alarm_in.token_hash(tok)
    assert "token_hash" not in got["device"]
    assert t.rx.by_token(tok) == "door-1"
    assert t.rx.by_token("0" * 32) is None and t.rx.by_token("x") is None
    again = _门磁(t, link={"via": "url"})
    assert again["token"] is None and t.rx.by_token(tok) == "door-1", "改别的不换口令"
    new = _门磁(t, link={"via": "url", "new_token": True})["token"]
    assert new != tok and t.rx.by_token(tok) is None and t.rx.by_token(new) == "door-1"
    _门磁(t, link={"via": "signed"})
    assert t.rx.by_token(new) is None, "改回签名回调:网址作废"


def _sia(body: bytes) -> bytes:
    return frame(body)


def test_SIA_入侵类派_恢复和心跳只回ACK_对到设备_坏帧NAK(核):
    t = 核
    _门磁(t, "pir-5", link={"via": "sia", "account": "1234", "zone": "5"})
    _门磁(t, "panel", link={"via": "sia", "account": "ABCD", "zone": ""})
    with pytest.raises(DeviceError, match="已经接在"):
        _门磁(t, "pir-5b", link={"via": "sia", "account": "1234", "zone": "5"})
    ack = t.rx.on_sia(_sia(b'"SIA-DCS"0007R0L0#1234[#1234|Nri1/BA005]_10:00:00,11-28-2026'))
    assert b'"ACK"0007R0L0#1234[]' in ack
    assert [s for s, _ in t.fired] == ["dev-pir-5"]
    t.rx.on_sia(_sia(b'"ADM-CID"0008L0#ABCD[#ABCD|1130 01 015]'))
    assert [s for s, _ in t.fired][-1] == "dev-panel", "空防区 = 这台主机的所有防区"
    n = len(t.fired)
    t.rx.on_sia(_sia(b'"ADM-CID"0009L0#ABCD[#ABCD|3130 01 015]'))       # 恢复
    t.rx.on_sia(_sia(b'"SIA-DCS"0010L0#1234[#1234|NOP001]'))             # 撤防
    t.rx.on_sia(_sia(b'"NULL"0011L0#1234[]'))                            # 心跳
    assert len(t.fired) == n
    bad = _sia(b'"SIA-DCS"0012L0#1234[#1234|NBA005]').replace(b'BA005', b'BA006')
    assert b'"NAK"' in t.rx.on_sia(bad), "CRC 对不上"
    assert b'"NAK"' in t.rx.on_sia(_sia(b'"*SIA-DCS"0013L0#1234[abc]')), "加密的不收"
    assert len(t.fired) == n


def test_SIA_报文格式():
    assert crc16(b"123456789") == 0xBB3D
    f = frame(b'"NULL"0000R0L0#1234[]')
    assert f.startswith(b"\n") and f.endswith(b"\r") and f[5:9] == b"0015"
    ack, hits = parse_sia(f)
    assert hits == [] and b'"ACK"0000R0L0#1234[]' in ack


class 假模块:
    def __init__(self):
        self.bits = [False] * 8
        self.down = False

    def read(self, host, port, unit, n):
        if self.down:
            raise OSError("连不上")
        return self.bits[:n]


def test_IO模块干接点_去抖_常闭_回正常才再报_读不到一分钟报P2(核, monkeypatch):
    t = 核
    m = 假模块()
    t.rx._read = m.read
    t.rx.alerts = t.alerts
    _门磁(t, "pir-1", link={"via": "modbus", "host": "10.0.0.9", "port": 502, "unit": 1,
                          "input": 0, "nc": False})
    _门磁(t, "door-nc", link={"via": "modbus", "host": "10.0.0.9", "port": 502, "unit": 1,
                            "input": 3, "nc": True})
    m.bits[3] = True                                      # 常闭的门关着 = 1
    t.rx.poll_once()
    assert t.fired == []
    m.bits[0] = True
    t.rx.poll_once()
    assert t.fired == [], "一次不算(去抖)"
    t.rx.poll_once()
    t.rx.poll_once()
    assert [s for s, _ in t.fired] == ["dev-pir-1"], "连着两次才算,一直报警只算一次"
    m.bits[0] = False
    t.rx.poll_once()
    m.bits[0] = True
    t.rx.poll_once()
    t.rx.poll_once()
    assert [s for s, _ in t.fired].count("dev-pir-1") == 2, "回正常再报警才再算"
    m.bits[3] = False                                     # 常闭断开 = 报警
    t.rx.poll_once()
    t.rx.poll_once()
    assert t.fired[-1][0] == "dev-door-nc"
    m.down = True
    t.rx.poll_once()
    assert not _开着(t, "alarm_input_lost")
    t.clock.advance(61)
    t.rx.poll_once()
    assert _开着(t, "alarm_input_lost") and t.rx.status["pir-1"]["error"] == "连不上"
    m.down = False
    t.rx.poll_once()
    assert not _开着(t, "alarm_input_lost")


def test_modbus报文_真的读一回():
    """一个最小的假 IO 模块(TCP):回功能码 02 的位。"""
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]

    def serve():
        c, _ = srv.accept()
        req = c.recv(12)
        tid, _p, _l, unit, fc, start, n = struct.unpack(">HHHBBHH", req)
        assert fc == 2 and start == 0 and n == 10
        c.sendall(struct.pack(">HHHBBB", tid, 0, 5, unit, 2, 2) + bytes([0b00000101, 0b10]))
        c.close()
    th = threading.Thread(target=serve)
    th.start()
    bits = read_inputs("127.0.0.1", port, 1, 10)
    th.join()
    srv.close()
    assert [i for i, b in enumerate(bits) if b] == [0, 2, 9]


def test_接入方式写错的拒(核):
    t = 核
    for bad in ({"via": "x"}, {"via": "sia", "account": "zz"}, {"via": "sia", "account": "1234",
                                                                "zone": "abc"},
                {"via": "modbus", "host": ""}, {"via": "modbus", "host": "h", "input": 999}):
        with pytest.raises(DeviceError):
            _门磁(t, link=bad)


async def test_外审1_1_第8_9条_并进来的报警从它起再看满_合并的告警都下结论才关(核):
    t = 核
    await t.run(12)
    _门磁(t)
    t.desk.merge_window_ms = 10 ** 9
    await _触发(t)
    await t.run(200)
    assert t.desk.list()[0]["result"] == "done"
    _能看(t)
    t.clock.advance(VERIFY_HOLD_MS / 1000 + 1)
    r2 = await _触发(t)
    assert r2["outcome"] == "merged"
    [v] = _开着(t, "intrusion_verifying")
    assert t.desk.verify_tick() == 1, "第一条下结论;第二条刚报,机器人还没在它之后看满"
    assert _开着(t, "intrusion_verifying"), "第二条还没结论:合并的告警先不关"
    t.clock.advance(VERIFY_HOLD_MS / 1000 + 1)
    assert t.desk.verify_tick() == 1
    assert not _开着(t, "intrusion_verifying")
    assert t.alerts.book.get(v.key).verdict == "false_alarm"


def test_外审1_1_第2轮_5_触发网址的口令不进审计_不进日志(tmp_path, caplog):
    import logging

    from test_site_api import 站 as 真站

    from nexwar_site.api import _mask_path
    tok = "0123456789abcdef0123456789abcdef"
    assert _mask_path(f"POST /api/alarm-in/{tok} HTTP/1.1") == "POST /api/alarm-in/*** HTTP/1.1"
    s = 真站(tmp_path)
    try:
        class 假报警输入:
            status: dict = {}

            def by_token(self, t):
                return "door-1" if t == tok else None
        s.api.alarm_in = 假报警输入()
        caplog.set_level(logging.DEBUG)
        code, _ = s.req("POST", f"/api/alarm-in/{tok}", {})
        assert code == 404                       # 这个夹具没开事件派遣:口令对上了、后面 404
        code, _ = s.req("POST", "/api/alarm-in/" + "f" * 32, {})
        assert code == 404
        rows = s.api.audit.list(limit=20)
        mine = [r for r in rows if "alarm-in" in r["action"]]
        assert mine and all(tok not in json.dumps(r, ensure_ascii=False) for r in rows)
        assert mine[0]["action"] == "POST /api/alarm-in/***" and mine[0]["target"] == "dev-door-1"
        assert tok not in caplog.text and "f" * 32 not in caplog.text
    finally:
        s.close()


async def test_外审1_1_第2轮_1_看的时候断了_从恢复起重新数_一直看不了算没核实成(核):
    t = 核
    await t.run(12)
    _门磁(t)
    await _触发(t)
    await t.run(200)
    assert t.desk.list()[0]["result"] == "done"
    _能看(t, state="lost")                                # 人员检测断了
    t.clock.advance(VERIFY_HOLD_MS / 1000 + 1)
    assert t.desk.verify_tick() == 0, "看不了的这段不算"
    _能看(t)
    assert t.desk.verify_tick() == 0, "恢复了:从这时重新数"
    t.clock.advance(VERIFY_HOLD_MS / 1000 + 1)
    assert t.desk.verify_tick() == 1
    assert t.desk.list()[0]["verdict"] == "clear"


async def test_外审1_1_第2轮_1_到了一直看不了_到超时算没核实成_报P1写原因(核):
    from nexwar_site.incidents import VERIFY_TIMEOUT_MS
    t = 核
    await t.run(12)
    _门磁(t)
    await _触发(t)
    await t.run(200)
    _能看(t, state="lost")
    t.clock.advance(VERIFY_HOLD_MS / 1000 + 1)
    assert t.desk.verify_tick() == 0
    t.clock.advance(VERIFY_TIMEOUT_MS / 1000)
    t.desk.dispatcher._fresh = lambda c: True            # 钟拨了十分钟:状态照算新鲜,只看检测
    assert t.desk.verify_tick() == 1
    assert t.desk.list()[0]["verdict"] == "unverified"
    [p1] = _开着(t, "intrusion_unanswered")
    assert "人员检测不可用" in p1.title
    assert not _开着(t, "intrusion_verifying")


def test_外审1_1_第2轮_3_合并的告警按记下的报警下结论_有人的不标误报(核):
    t = 核
    src = t.src
    base = {"outcome": "dispatched", "robot_id": "A", "verify": 1, "zone": "Z1",
            "source": "dev-door-1", "task_id": "inc-1"}
    with t.db.tx() as c:
        for i in (1, 2):
            c.execute("INSERT INTO incidents (id, source, event_id, type, zone, received_at, "
                      "outcome, robot_id, task_id, verify, verdict) VALUES "
                      "(?, 'dev-door-1', ?, 'intrusion', 'Z1', ?, 'dispatched', 'A', "
                      "'inc-1', 1, '')",
                      (i, f"e{i}", t.clock() - 1000))
    for i, r in ((1, base | {"id": 1}), (2, base | {"id": 2, "outcome": "merged"})):
        key = src.on_incident(r)                       # 报警派遣那头把告警号记在报警上
        with t.db.tx() as c:
            c.execute("UPDATE incidents SET verify_alert=? WHERE id=?", (key, i))
    [v] = _开着(t, "intrusion_verifying")
    assert [r["id"] for r in t.db.query("SELECT id FROM incidents WHERE verify_alert=? "
                                        "ORDER BY id", (v.key,))] == [1, 2]
    with t.db.tx() as c:
        c.execute("UPDATE incidents SET verdict='person' WHERE id=1")
    src.on_verdict(base | {"id": 2, "verdict": "clear"})
    got = t.alerts.book.get(v.key)
    assert got.resolved_ms is not None and got.verdict != "false_alarm", "有一条看见人:不算误报"


async def _到了(t):
    await t.run(12)
    _门磁(t)
    r = await _触发(t)
    await t.run(200)
    assert t.desk.list()[0]["result"] == "done"
    _能看(t)
    return r


async def test_外审1_1_第3轮_2_被派走过_做完了也不算回到现场_当场没核实成(核):
    import dataclasses
    from types import SimpleNamespace
    t = 核
    await _到了(t)
    c = t.desk.dispatcher.clients["A"]
    c.status = dataclasses.replace(c.status, task=SimpleNamespace(
        task_id="adhoc-x", state=SimpleNamespace(value="done")))      # 被派去别处、已经做完
    assert t.desk.verify_tick() == 1
    assert t.desk.list()[0]["verdict"] == "unverified"
    [p1] = _开着(t, "intrusion_unanswered")
    assert "被派去做别的" in p1.title


async def test_外审1_1_第3轮_3_站点重启_从启动起再看满(核):
    t = 核
    await _到了(t)
    t.clock.advance(VERIFY_HOLD_MS / 1000 + 1)
    t.desk._born = t.clock()                             # 像刚重启
    assert t.desk.verify_tick() == 0, "重启前看的那段不算"
    t.clock.advance(VERIFY_HOLD_MS / 1000 + 1)
    assert t.desk.verify_tick() == 1
    assert t.desk.list()[0]["verdict"] == "clear"


async def test_外审1_1_第3轮_6_驱离里看见人报的也算看见人(核):
    t = 核
    await _到了(t)
    t.alerts.raise_alert(kind="intrusion_person", robot="A", title="拦截点看到 1 个人")
    t.clock.advance(VERIFY_HOLD_MS / 1000 + 1)
    assert t.desk.verify_tick() == 1
    assert t.desk.list()[0]["verdict"] == "person"


def test_外审1_1_第3轮_4_同一趟还有没下结论的_不收驱离(核):
    from types import SimpleNamespace

    from nexwar_site.main import Server
    t = 核
    with t.db.tx() as c:
        for i, (verify, verdict) in enumerate([(1, "clear"), (1, ""), (0, "")], start=1):
            c.execute("INSERT INTO incidents (id, source, event_id, type, zone, received_at, "
                      "outcome, robot_id, task_id, verify, verdict) VALUES "
                      "(?, 'dev-door-1', ?, 'intrusion', 'Z1', 1, 'dispatched', 'A', ?, ?, ?)",
                      (i, f"e{i}", "inc-1" if i < 3 else "inc-2", verify, verdict))
    assert not t.desk.task_settled("inc-1", 1), "第 2 条还在核实"
    assert t.desk.task_settled("inc-2", 99) is False, "不用核实的真入侵在这一趟上"
    downs: list = []
    me = SimpleNamespace(alert_sources=SimpleNamespace(on_verdict=lambda r: None),
                         incidents=t.desk,
                         deterrence=SimpleNamespace(stand_down=lambda *a: downs.append(a)))
    Server._on_verdict(me, {"id": 1, "verdict": "clear", "robot_id": "A", "task_id": "inc-1"})
    assert downs == []
    with t.db.tx() as c:
        c.execute("UPDATE incidents SET verdict='clear' WHERE id=2")
    Server._on_verdict(me, {"id": 2, "verdict": "clear", "robot_id": "A", "task_id": "inc-1"})
    assert downs and downs[0][:2] == ("A", "inc-1")


async def test_外审1_1_第3轮_5_告警号记在报警上_不限条数(核):
    t = 核
    await t.run(12)
    _门磁(t)
    t.desk.merge_window_ms = 10 ** 9
    await _触发(t)
    for _ in range(60):
        t.clock.advance(3)                          # 报警编号按时刻起;一分钟别超过事件源上限
        await _触发(t)
    [v] = _开着(t, "intrusion_verifying")
    n = t.db.query("SELECT COUNT(*) AS n FROM incidents WHERE verify_alert=?", (v.key,))[0]["n"]
    assert n == 61
    assert t.src._members(v.key)[0] == t.db.query("SELECT MIN(id) AS m FROM incidents")[0]["m"]


def test_外审1_1_第4轮_2_旧机器人的去核实没报警挂着了就关(核):
    t = 核
    a = t.alerts.raise_alert(kind="intrusion_verifying", robot="A", title="报警器报警:A 去核实")
    t.src.on_verify_moved([a.key])
    got = t.alerts.book.get(a.key)
    assert got.resolved_ms is not None and "改派" in got.context["note"]


def test_外审1_1_第4轮_1_最后一条没核实成_整趟都定了也收驱离(核):
    from types import SimpleNamespace

    from nexwar_site.main import Server
    t = 核
    with t.db.tx() as c:
        for i, verdict in ((1, "clear"), (2, "unverified")):
            c.execute("INSERT INTO incidents (id, source, event_id, type, zone, received_at, "
                      "outcome, robot_id, task_id, verify, verdict) VALUES "
                      "(?, 'dev-door-1', ?, 'intrusion', 'Z1', 1, 'dispatched', 'A', "
                      "'inc-1', 1, ?)",
                      (i, f"e{i}", verdict))
    downs: list = []
    me = SimpleNamespace(alert_sources=SimpleNamespace(on_verdict=lambda r: None),
                         incidents=t.desk,
                         deterrence=SimpleNamespace(stand_down=lambda *a: downs.append(a)))
    Server._on_verdict(me, {"id": 2, "verdict": "unverified", "robot_id": "A",
                            "task_id": "inc-1"})
    assert downs and downs[0][:2] == ("A", "inc-1") and "没核实成" in downs[0][2]


async def test_外审1_1_第6轮_1_看满之前机器人报有人_不判没人_从人不见了重新数(核):
    t = 核
    await _到了(t)
    t.clock.advance(VERIFY_HOLD_MS / 1000 - 1)
    t.desk.dispatcher.clients["A"].capabilities.tasks["persons"] = {"state": "ok",
                                                                    "present": True}
    t.clock.advance(2)
    assert t.desk.verify_tick() == 0, "这会儿有人:不能判误报"
    assert t.desk.list()[0]["verdict"] == ""
    _能看(t)                                              # 人走了(没报出见人告警)
    t.clock.advance(2)
    assert t.desk.verify_tick() == 0, "没人的那段从人不见了重新数"
    t.clock.advance(VERIFY_HOLD_MS / 1000 + 1)
    assert t.desk.verify_tick() == 1


def test_外审1_1_第7轮_2_modbus回包太短_当读坏了():
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]

    def serve():
        c, _ = srv.accept()
        req = c.recv(12)
        tid, _p, _l, unit, _fc, _s, _n = struct.unpack(">HHHBBHH", req)
        c.sendall(struct.pack(">HHHBBB", tid, 0, 4, unit, 2, 1) + bytes([0b1]))  # 16 路只回 8 路
        c.close()
    th = threading.Thread(target=serve)
    th.start()
    with pytest.raises(OSError, match="长度不对"):
        read_inputs("127.0.0.1", port, 1, 16)
    th.join()
    srv.close()


def test_外审1_1_第7轮_2_一个模块读炸了_别的模块照读_一分钟报输入断了(核):
    t = 核
    good = 假模块()

    def read(host, port, unit, n):
        if host == "10.0.0.8":
            raise IndexError("index out of range")        # 意外的坏回包
        return good.read(host, port, unit, n)
    t.rx._read = read
    t.rx.alerts = t.alerts
    _门磁(t, "bad-1", link={"via": "modbus", "host": "10.0.0.8", "port": 502, "unit": 1,
                          "input": 0, "nc": False})
    _门磁(t, "pir-2", link={"via": "modbus", "host": "10.0.0.9", "port": 502, "unit": 1,
                          "input": 0, "nc": False})
    good.bits[0] = True
    t.rx.poll_once()
    t.rx.poll_once()
    assert [s for s, _ in t.fired] == ["dev-pir-2"], "坏模块不挡后面的模块"
    t.clock.advance(61)
    t.rx.poll_once()
    assert _开着(t, "alarm_input_lost") and "index" in t.rx.status["bad-1"]["error"]


def test_外审1_1_第8轮_2_几个模块掉线等超时_正常模块照样每拍读到(核):
    import time as _t
    t = 核
    good = 假模块()

    def read(host, port, unit, n):
        if host.startswith("10.0.1."):
            _t.sleep(1.0)                                 # 掉线:等超时
            raise OSError("timed out")
        return good.read(host, port, unit, n)
    t.rx._read = read
    for i in range(5):
        _门磁(t, f"off-{i}", link={"via": "modbus", "host": f"10.0.1.{i}", "port": 502,
                                  "unit": 1, "input": 0, "nc": False})
    _门磁(t, "pir-3", link={"via": "modbus", "host": "10.0.0.9", "port": 502, "unit": 1,
                          "input": 0, "nc": False})
    good.bits[0] = True
    t0 = _t.monotonic()
    t.rx.poll_once()
    t.rx.poll_once()
    took = _t.monotonic() - t0
    assert [s for s, _ in t.fired] == ["dev-pir-3"], "两拍就读到两次,去抖过了就报"
    assert took < 1.5, f"不等掉线的五个模块一个个超时:{took:.2f}"
    t.rx.stop()


def test_外审1_1_第9轮_1_派单等回执的时候_照样每拍读IO模块_不漏别的输入(核):
    import threading
    import time as _t
    t = 核
    gate = threading.Event()
    fired: list = []

    def 慢派(source, body):                               # 等机器人回执(最长 10 秒)
        fired.append(source)
        gate.wait(5)
        return {"outcome": "dispatched"}
    m = 假模块()
    rx = AlarmInputs(t.db, fire=慢派, now_ms=t.clock, read=m.read)
    _门磁(t, "pir-a", link={"via": "modbus", "host": "10.0.0.9", "port": 502, "unit": 1,
                          "input": 0, "nc": False})
    _门磁(t, "pir-b", link={"via": "modbus", "host": "10.0.0.9", "port": 502, "unit": 1,
                          "input": 1, "nc": False})
    m.bits[0] = True
    t0 = _t.monotonic()
    rx.poll_once()
    rx.poll_once()                                        # pir-a 报警,派单卡着等回执
    m.bits[1] = True
    rx.poll_once()
    rx.poll_once()                                        # 这期间 pir-b 报警也照样读到、排上
    assert _t.monotonic() - t0 < 1.0, "读 IO 模块不跟着等回执"
    assert rx.status["pir-b"]["state"] == "alarm"
    gate.set()
    for _ in range(50):
        if fired == ["dev-pir-a", "dev-pir-b"]:
            break
        _t.sleep(0.02)
    assert fired == ["dev-pir-a", "dev-pir-b"], "两条都派了,按先后"
    rx.stop()


def test_外审1_1_第11轮_1_报警排满了不丢(核, monkeypatch):
    """SIA 回 NAK;IO 欠一次下一拍再交,短脉冲也不丢;排满了报 P2,排空了自己关。"""
    import threading
    import time as _t
    t = 核
    monkeypatch.setattr(alarm_in, "MAX_FIRE_QUEUE", 1)
    gate = threading.Event()
    fired: list = []

    def 慢派(source, body):                               # 等机器人回执
        fired.append(source)
        gate.wait(5)
        return {"outcome": "dispatched"}
    m = 假模块()
    rx = AlarmInputs(t.db, fire=慢派, now_ms=t.clock, read=m.read)
    rx.alerts = t.alerts
    for dev, inp in (("pir-a", 0), ("pir-b", 1)):
        _门磁(t, dev, link={"via": "modbus", "host": "10.0.0.9", "port": 502, "unit": 1,
                            "input": inp, "nc": False})
    _门磁(t, "pir-5", link={"via": "sia", "account": "1234", "zone": "5"})
    sia = _sia(b'"SIA-DCS"0007R0L0#1234[#1234|Nri1/BA005]')

    def 等(cond):
        for _ in range(250):
            if cond():
                return True
            _t.sleep(0.02)
        return False
    m.bits[0] = True
    rx.poll_once()
    rx.poll_once()                                        # pir-a 占满了队(卡着等回执)
    assert 等(lambda: fired == ["dev-pir-a"])
    assert b'"NAK"' in rx.on_sia(sia), "排满了没收:回 NAK 让主机重发,不能回 ACK 吞掉"
    assert _开着(t, "alarm_input_overload"), "排满了报 P2"
    m.bits[1] = True
    rx.poll_once()
    rx.poll_once()                                        # pir-b 报警,排不上
    m.bits[1] = False
    rx.poll_once()                                        # 短脉冲:已经回到正常
    assert rx._modbus["pir-b"]["owed"] is True
    gate.set()
    assert 等(lambda: rx._queued == 0)
    assert 等(lambda: not _开着(t, "alarm_input_overload")), "排空了自己关"
    rx.poll_once()                                        # 欠的那次下一拍交上去
    assert 等(lambda: fired == ["dev-pir-a", "dev-pir-b"]), fired
    assert 等(lambda: rx._queued == 0)
    assert b'"ACK"0007R0L0#1234[]' in rx.on_sia(sia), "主机重发:这回收了"
    assert 等(lambda: fired == ["dev-pir-a", "dev-pir-b", "dev-pir-5"]), fired
    assert rx._modbus["pir-b"]["owed"] is False and rx._modbus["pir-b"]["fired"] is False
    rx.poll_once()
    _t.sleep(0.1)
    assert fired.count("dev-pir-b") == 1, "交上去了就不再重交"
    rx.stop()
