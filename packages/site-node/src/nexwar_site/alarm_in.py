"""1.1-3 现有报警器一响 → 派机器人去核实:不会签名的报警设备怎么接进来
(设计 ``docs/1.1-3-报警核实-设计.md``)。

外部设备(:mod:`nexwar_site.devices`)原来只有一种接法:签名回调(``X-Nexwar-Signature``)。客户现场的
红外、门磁、报警主机多半不会签名,这里加三种:

- **触发网址**(``via: url``):站点给这台设备一个带随机口令的网址
  ``/api/alarm-in/<口令>``,设备(录像机、报警主机的 HTTP 联动、集成商的脚本)一触发就
  GET / POST 它。口令只在生成时给一次,站点只存哈希。
- **报警主机**(``via: sia``):站点当报警中心的接收机,收 **SIA DC-09**(TCP)—— 常见的
  IP 报警主机(Hikvision AX PRO、Ajax、Paradox、DSC、Risco…)都能报到「报警中心」。
  认 ``SIA-DCS`` 和 ``ADM-CID`` 两种格式(**不加密**的;加密的回 NAK、记日志)。按
  「用户号 + 防区号」对到设备;入侵类(SIA 的 BA/BV/PA/HA/TA,Contact ID 的 120–139、144、
  145 新事件)才派,别的(布撤防、恢复、故障、心跳)只回 ACK。
  端口在 ``site.json`` 的 ``alarm_receiver.sia_port``(默认不开)。
- **干接点**(``via: modbus``):红外、门磁的干接点接到一个**以太网 IO 模块**(Modbus TCP,几十块钱
  一个),站点每 :data:`POLL_S` 秒读一次离散输入;常开 / 常闭可选;连着两次读到报警态才算(去抖)。
  IO 模块连着 :data:`LOST_MS` 读不到报 P2「报警输入断了」(线被剪、模块掉电也要有人知道)。

三种进来以后都跟签名回调一样走 :meth:`IncidentDesk.handle`(限流、布防判断、合并、选机器人)。
"""

from __future__ import annotations

import hashlib
import logging
import re
import secrets
import socket
import socketserver
import struct
import threading
import time
import uuid
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor, wait
from typing import Any

log = logging.getLogger(__name__)

VIAS = ("signed", "url", "sia", "modbus")
POLL_S = 0.5
#: IO 模块连着多久读不到报 P2(毫秒)。
LOST_MS = 60_000
TIMEOUT_S = 2.0
#: 外审 1.1 第 8 轮 #2:几个 IO 模块一起读(各读各的,掉线模块的超时不拖慢正常模块),最多几个。
MAX_IO_PARALLEL = 32
#: 外审 1.1 第 9 轮 #1:报警交给后台一条一条派(派单要等机器人回执,
#: 别让读 IO 模块、回 SIA 的 ACK 跟着等);排着没派的最多这么多条,再多的记日志不收。
MAX_FIRE_QUEUE = 100
#: SIA 入侵类事件码;Contact ID 入侵类(新事件 qualifier 1)。
SIA_CODES = frozenset({"BA", "BV", "PA", "HA", "TA"})
CID_CODES = frozenset({*range(120, 140), 144, 145})
_ACCT = re.compile(r"^[0-9A-Fa-f]{3,16}$")
_HOST = re.compile(r"^[A-Za-z0-9.-]{1,253}$")
_FRAME = re.compile(
    rb'^\n?(?P<crc>[0-9A-Fa-f]{4})(?P<len>0[0-9A-Fa-f]{3})(?P<body>"(?P<id>\*?[A-Z-]+)"'
    rb'(?P<seq>[0-9]{4})(?P<rcv>R[0-9A-Fa-f]{0,6})?(?P<pref>L[0-9A-Fa-f]{0,6})'
    rb'#(?P<acct>[0-9A-Fa-f]{3,16})\[(?P<data>[^\]]*)\](?P<ts>_[0-9:,\-]*)?)\r?$')


class LinkError(ValueError):
    """接入方式写得不对(接口回 400)。"""


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def clean_link(raw: Any, old: dict[str, Any] | None) -> tuple[dict[str, Any], str | None]:
    """→ (存库的接入方式, 新给的触发口令或 None)。``raw`` 没给 = 不变(老设备是 ``signed``)。"""
    if raw is None:
        return (old or {"via": "signed"}), None
    if not isinstance(raw, dict) or raw.get("via") not in VIAS:
        raise LinkError(f"接入方式 via 要是 {' / '.join(VIAS)}")
    via = raw["via"]
    if via == "signed":
        return {"via": "signed"}, None
    if via == "url":
        if (old or {}).get("via") == "url" and raw.get("new_token") is not True:
            return old, None
        return {"via": "url"}, secrets.token_hex(16)
    if via == "sia":
        acct = str(raw.get("account") or "").strip()
        if not _ACCT.match(acct):
            raise LinkError("报警主机的用户号(account)要是 3–16 位十六进制")
        zone = str(raw.get("zone") or "").strip()
        if zone not in ("", "*") and not re.fullmatch(r"[0-9]{1,4}", zone):
            raise LinkError("防区号要是 1–4 位数字(空着 = 这台主机的所有防区)")
        return {"via": "sia", "account": acct.upper(),
                "zone": "" if zone in ("", "*") else str(int(zone))}, None
    host = str(raw.get("host") or "").strip()
    if not _HOST.match(host):
        raise LinkError("要填 IO 模块的地址")
    port, unit, inp = raw.get("port", 502), raw.get("unit", 1), raw.get("input")
    for v, lo, hi, what in ((port, 1, 65535, "端口"), (unit, 0, 255, "站号(unit)"),
                            (inp, 0, 255, "输入号")):
        if not isinstance(v, int) or isinstance(v, bool) or not lo <= v <= hi:
            raise LinkError(f"{what}要是 {lo}–{hi} 的整数")
    nc = raw.get("nc", False)
    if not isinstance(nc, bool):
        raise LinkError("nc(常闭)要是 true / false")
    return {"via": "modbus", "host": host, "port": port, "unit": unit, "input": inp,
            "nc": nc}, None


# ---------------------------------------------------------------- SIA DC-09


def crc16(data: bytes) -> int:
    """DC-09 的 CRC(CRC-16/ARC:多项式 0x8005 反射、初值 0)。"""
    crc = 0
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc


def frame(body: bytes) -> bytes:
    return b"\n" + f"{crc16(body):04X}0{len(body):03X}".encode() + body + b"\r"


def _ack(m: re.Match[bytes] | None, kind: bytes = b"ACK") -> bytes:
    if m is None or kind == b"NAK":
        ts = time.strftime("_%H:%M:%S,%m-%d-%Y", time.gmtime()).encode()
        return frame(b'"NAK"0000R0L0A0[]' + ts)
    rcv = m.group("rcv") or b""
    return frame(b'"ACK"' + m.group("seq") + rcv + m.group("pref") + b"#" + m.group("acct")
                 + b"[]")


def parse_sia(raw: bytes) -> tuple[bytes, list[tuple[str, int | None, str]]]:
    """一帧 → (回给主机的 ACK / NAK, [(用户号, 防区号或 None, 事件说明)] 里入侵类的)。"""
    m = _FRAME.match(raw.strip(b"\x00"))
    if m is None:
        return _ack(None, b"NAK"), []
    body = m.group("body")
    if int(m.group("crc"), 16) != crc16(body) or int(m.group("len")[1:], 16) != len(body):
        return _ack(None, b"NAK"), []
    kind = m.group("id").decode()
    if kind.startswith("*"):
        log.warning("报警主机发来加密的 DC-09(%s):站点只收不加密的,请在主机上关掉加密", kind)
        return _ack(None, b"NAK"), []
    acct = m.group("acct").decode().upper()
    data = m.group("data").decode("ascii", "replace")
    if "|" in data:
        data = data.split("|", 1)[1]
    hits: list[tuple[str, int | None, str]] = []
    if kind == "SIA-DCS":
        # 「Nri1/BA501」「NBA01」:N 开头的新事件;/ 隔开几段,每段两个字母的码 + 防区号
        if data.startswith("N"):
            for part in data[1:].split("/"):
                mm = re.fullmatch(r"(?:ri[0-9]+)?([A-Z]{2})([0-9]{0,4})", part.strip())
                if mm and mm.group(1) in SIA_CODES:
                    hits.append((acct, int(mm.group(2)) if mm.group(2) else None,
                                 f"SIA {mm.group(1)}{mm.group(2)}"))
    elif kind == "ADM-CID":
        # 「1130 01 015」:qualifier(1 新事件)、事件码、分区、防区
        mm = re.fullmatch(r"\s*([136])([0-9]{3})\s*([0-9]{2})\s*([0-9]{3})\s*", data)
        if mm and mm.group(1) == "1" and int(mm.group(2)) in CID_CODES:
            hits.append((acct, int(mm.group(4)), f"Contact ID {mm.group(2)}"))
    return _ack(m), hits


# ---------------------------------------------------------------- Modbus TCP


def read_inputs(host: str, port: int, unit: int, count: int, *,
                timeout: float = TIMEOUT_S) -> list[bool]:
    """读 0..count-1 号离散输入(功能码 02)。读不到抛 ``OSError``。"""
    tid = int(time.monotonic() * 1000) & 0xFFFF
    req = struct.pack(">HHHBBHH", tid, 0, 6, unit, 2, 0, count)
    with socket.create_connection((host, port), timeout=timeout) as s:
        s.sendall(req)
        head = _recv(s, 7)
        _tid, proto, length, _unit = struct.unpack(">HHHB", head)
        if proto != 0 or not 2 <= length <= 260:
            raise OSError("IO 模块回的不是 Modbus TCP")
        pdu = _recv(s, length - 1)
    if pdu[0] & 0x80:
        raise OSError(f"IO 模块回异常码 {pdu[1] if len(pdu) > 1 else '?'}")
    # 外审 1.1 第 7 轮 #2:回的字节要够盖住要读的那几路(短了当读坏了,不当场炸)
    if pdu[0] != 2 or len(pdu) < 2 or len(pdu) < 2 + pdu[1] or pdu[1] < (count + 7) // 8:
        raise OSError("IO 模块回的长度不对")
    bits = pdu[2:2 + pdu[1]]
    return [bool(bits[i // 8] >> (i % 8) & 1) for i in range(count)]


def _recv(s: socket.socket, n: int) -> bytes:
    out = b""
    while len(out) < n:
        got = s.recv(n - len(out))
        if not got:
            raise OSError("IO 模块断开了")
        out += got
    return out


# ---------------------------------------------------------------- 总台


class AlarmInputs:
    """三种接法收进来 → :meth:`trigger`。``fire``:``(source, body) -> 账``,站点主程序接到
    ``IncidentDesk`` 上(事件循环里跑)。"""

    def __init__(self, db: Any, *, fire: Callable[[str, dict[str, Any]], Any],
                 allow: Callable[[str], bool] | None = None,
                 now_ms: Callable[[], int], read: Callable[..., list[bool]] = read_inputs,
                 background: bool = True) -> None:
        self.db = db
        self._background = background
        self._fireq: ThreadPoolExecutor | None = None
        self._queued = 0
        self._qlock = threading.Lock()
        self._fire = fire
        self._allow = allow
        self._now = now_ms
        self._read = read
        #: 告警台(站点主程序接上):IO 模块读不到报 P2。
        self.alerts: Any = None
        #: 设备号 → ``{"last_ms", "error", "state"}``(给网页看)。
        self.status: dict[str, dict[str, Any]] = {}
        self._modbus: dict[str, dict[str, Any]] = {}      # 设备号 → 去抖、上一次的态
        self._lost: dict[tuple[str, int, int], int] = {}  # IO 模块 → 第一次读不到的时刻
        self._sia: socketserver.ThreadingTCPServer | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._pool: ThreadPoolExecutor | None = None
        #: 外审 1.1 第 8 轮 #2:还在读的模块(掉线的等超时,不挡别的模块下一轮)
        self._inflight: dict[tuple[str, int, int], Future[list[bool]]] = {}

    def _devices(self, via: str) -> list[dict[str, Any]]:
        import json
        out = []
        for r in self.db.query("SELECT id, link FROM ext_devices"):
            try:
                link = json.loads(r["link"] or "{}")
            except ValueError:
                continue
            if link.get("via") == via:
                out.append({"id": r["id"], **link})
        return out

    def trigger(self, dev_id: str, *, via: str, what: str) -> dict[str, Any] | None:
        """这台设备报警了:按签名回调那一路处理(限流、布防、合并、派机器人)。"""
        source = f"dev-{dev_id}"
        st = self.status.setdefault(dev_id, {})
        st.update(last_ms=self._now(), what=what)
        if self._allow is not None and not self._allow(source):
            log.warning("设备 %s 一分钟内报得太多,这次不收(%s)", dev_id, what)
            return None
        body = {"event_id": f"{via}-{uuid.uuid4().hex[:16]}", "type": "intrusion",
                "zone": "-", "detail": {"via": via, "what": what[:200]}}
        log.info("报警输入:设备 %s(%s)%s", dev_id, via, what)
        if not self._background:
            return self._fire_one(dev_id, source, body)
        with self._qlock:
            if self._queued >= MAX_FIRE_QUEUE:
                log.error("报警输入排着没派的已有 %d 条:设备 %s 这次不收(%s)", self._queued,
                          dev_id, what)
                return None
            self._queued += 1
            if self._fireq is None:
                self._fireq = ThreadPoolExecutor(max_workers=1, thread_name_prefix="alarm-in-fire")
            q = self._fireq

        def run() -> None:
            try:
                self._fire_one(dev_id, source, body)
            finally:
                with self._qlock:
                    self._queued -= 1
        q.submit(run)
        return {"outcome": "queued"}

    def _fire_one(self, dev_id: str, source: str, body: dict[str, Any]) -> dict[str, Any] | None:
        try:
            return self._fire(source, body)
        except Exception:
            log.exception("设备 %s 的报警没处理成", dev_id)
            return None

    # ------------------------------------------------------------ 触发网址

    def by_token(self, token: str) -> str | None:
        if not re.fullmatch(r"[0-9a-f]{32}", token or ""):
            return None
        rows = self.db.query("SELECT id, link FROM ext_devices WHERE token_hash=?",
                             (token_hash(token),))
        return rows[0]["id"] if rows and '"url"' in rows[0]["link"] else None

    # ------------------------------------------------------------ SIA

    def on_sia(self, raw: bytes) -> bytes:
        ack, hits = parse_sia(raw)
        if not hits:
            return ack
        devs = self._devices("sia")
        for acct, zone, what in hits:
            match = [d for d in devs if d["account"] == acct and (
                not d.get("zone") or (zone is not None and int(d["zone"]) == zone))]
            exact = [d for d in match if d.get("zone")]
            for d in exact or match:
                self.trigger(d["id"], via="sia", what=f"{what} 用户 {acct} 防区 {zone}")
            if not match:
                log.warning("报警主机 %s 防区 %s 报警(%s),没对上任何设备", acct, zone, what)
        return ack

    def start_sia(self, port: int, host: str = "0.0.0.0") -> int:
        desk = self

        class Handler(socketserver.StreamRequestHandler):
            def handle(self) -> None:
                self.request.settimeout(120)
                buf = b""
                while True:
                    try:
                        got = self.request.recv(1024)
                    except OSError:
                        return
                    if not got:
                        return
                    buf += got
                    while b"\r" in buf:
                        one, buf = buf.split(b"\r", 1)
                        try:
                            self.request.sendall(desk.on_sia(one + b"\r"))
                        except OSError:
                            return
                    if len(buf) > 4096:
                        buf = b""

        socketserver.ThreadingTCPServer.allow_reuse_address = True
        srv = socketserver.ThreadingTCPServer((host, port), Handler)
        srv.daemon_threads = True
        self._sia = srv
        threading.Thread(target=srv.serve_forever, daemon=True, name="sia-rx").start()
        log.info("报警主机接收(SIA DC-09)在端口 %s", srv.server_address[1])
        return int(srv.server_address[1])

    # ------------------------------------------------------------ Modbus

    def poll_once(self) -> None:
        """每个 IO 模块读一次;报警态连着两次才算(去抖);回到正常再报警才再算一次。

        外审 1.1 第 8 轮 #2:各模块一起读(线程池),这一拍最多等 :data:`POLL_S`;没读完的(掉线、
        等超时)留着下一拍再收,不拖慢别的模块 —— 正常模块照样每拍都读到。"""
        groups: dict[tuple[str, int, int], list[dict[str, Any]]] = {}
        for d in self._devices("modbus"):
            groups.setdefault((d["host"], d["port"], d["unit"]), []).append(d)
        if groups and self._pool is None:
            self._pool = ThreadPoolExecutor(max_workers=MAX_IO_PARALLEL,
                                            thread_name_prefix="alarm-io-read")
        for key, devs in groups.items():
            if key not in self._inflight:
                n = max(d["input"] for d in devs) + 1
                self._inflight[key] = self._pool.submit(self._read, key[0], key[1], key[2], n)
        fresh = [f for k, f in self._inflight.items() if k in groups]
        if fresh:
            wait(fresh, timeout=POLL_S)                   # 没读完的(掉线等超时)下一拍再收
        for key in [k for k, f in self._inflight.items() if f.done()]:
            fut = self._inflight.pop(key)
            if key in groups:
                self._apply(key, groups[key], fut)
        known = {g for g in groups}
        for key in [k for k in self._lost if k not in known]:
            self._lost.pop(key, None)

    def _apply(self, key: tuple[str, int, int], devs: list[dict[str, Any]],
               fut: Future[list[bool]]) -> None:
        now = self._now()
        n = max(d["input"] for d in devs) + 1
        try:
            bits = fut.result()
            if len(bits) < n:
                raise OSError("IO 模块回的路数不够")
        except Exception as exc:  # noqa: BLE001 - 外审 1.1 第 7 轮 #2:一个模块坏不挡别的模块
                first = self._lost.setdefault(key, now)
                for d in devs:
                    self.status.setdefault(d["id"], {})["error"] = str(exc)[:200]
                if now - first >= LOST_MS:
                    self._raise_lost(key, str(exc))
                return
        if self._lost.pop(key, None) is not None:
            self._resolve_lost(key)
        for d in devs:
            on = bits[d["input"]] != d["nc"]            # 常闭:断开(0)= 报警
            st = self.status.setdefault(d["id"], {})
            st.update(error="", state="alarm" if on else "normal")
            m = self._modbus.setdefault(d["id"], {"streak": 0, "fired": False})
            m["streak"] = m["streak"] + 1 if on else 0
            if not on:
                m["fired"] = False
            elif m["streak"] >= 2 and not m["fired"]:
                m["fired"] = True
                self.trigger(d["id"], via="modbus",
                             what=f"IO 模块 {key[0]} 输入 {d['input']}")

    def _raise_lost(self, key: tuple[str, int, int], why: str) -> None:
        if self.alerts is None:
            return
        from nexwar_site.alert_sources import SITE
        if not self.alerts.has_open(SITE, "alarm_input_lost"):
            self.alerts.raise_alert(kind="alarm_input_lost", robot=SITE,
                                    title=f"报警输入断了:IO 模块 {key[0]} 读不到",
                                    detail=f"{why[:200]};看模块的电源、网线,这期间那几路报警收不到")

    def _resolve_lost(self, key: tuple[str, int, int]) -> None:
        if self.alerts is None or self._lost:
            return
        from nexwar_site.alert_sources import SITE
        if self.alerts.has_open(SITE, "alarm_input_lost"):
            self.alerts.resolve_all(SITE, "alarm_input_lost", who="site:alarm_input_ok")

    def start_polling(self) -> None:
        def run() -> None:
            while not self._stop.wait(POLL_S):
                try:
                    self.poll_once()
                except Exception:
                    log.exception("读 IO 模块这一拍没办成")
        self._thread = threading.Thread(target=run, daemon=True, name="alarm-io")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._pool is not None:
            self._pool.shutdown(wait=False, cancel_futures=True)
        if self._fireq is not None:
            self._fireq.shutdown(wait=False)
        if self._sia is not None:
            self._sia.shutdown()
            self._sia.server_close()
