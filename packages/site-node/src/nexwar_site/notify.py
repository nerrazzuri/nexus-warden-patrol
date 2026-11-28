"""1.1-2 告警推到 WhatsApp / Telegram / 邮件 / webhook(设计 ``docs/1.1-2-告警外发-设计.md``)。

手机 App 推送(:mod:`nexwar_site.push`)之外,再按「渠道」往外发一份:保安主管都在 WhatsApp 上,不用非装
我们的 App。

- **渠道**(``notify_channels``):管理员在网页「系统」页加。种类 :data:`KINDS`;每个渠道写收件人
  (Telegram 的 chat id、邮箱、手机号、URL)、发哪几级(默认只 P1,可加 P2)、用哪种语言。机器人令牌、
  邮箱口令、WhatsApp 令牌、webhook 签名密钥整串加密存(站点 ``secrets.key``);站点没配密钥就不收。
- **发什么**:只发**文字**:站点名、级别、告警标题(按种类翻译)、哪台机器人、站点时间,和一句「打开
  Nexus Warden 处理」。**不带照片、不带位置**(同决策 53 的推送;照片要出站点到第三方,以后单独做成
  选项)。升到下一档还没人确认,再发一次,写「仍未确认」。
- **怎么发**:告警写库的同一个事务里,每个开着、级别对得上的渠道排一行进
  ``notify_outbox``(记下了就一定会发);站点循环里单独一条道往外发(:meth:`NotifyDesk.tick`),发不出去退避重试;已经有人确认、解决了的
  不发;一个小时还没发出去的作废。每个渠道每小时最多发 :data:`HOURLY_CAP` 条(告警风暴不刷爆主管的
  手机、不烧 WhatsApp 的钱),超了的作废并记原因。
- **发不出去**连续 :data:`STUCK_MS` 报 **P2**「告警外发发不出去」(``notify_failed``),发出去一条
  就自动解决。这条 P2 自己不外发(不然渠道坏了自己报自己)。
"""

from __future__ import annotations

import hashlib
import hmac
import http.client
import json
import logging
import re
import smtplib
import socket
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from nexwar_site.alert_sources import SITE

log = logging.getLogger(__name__)

KINDS = ("telegram", "whatsapp", "email", "webhook")
LEVELS = ("P1", "P2")
LANGS = ("en", "zh")
#: 这几种告警不外发(渠道坏了不能自己报自己)。
NEVER = frozenset({"notify_failed", "push_failed"})
MAX_CHANNELS = 20
MAX_TARGETS = 10
#: 多久还没发出去就作废(毫秒)。
EXPIRE_MS = 3600_000
#: 发不出去连续这么久报 P2(毫秒)。
STUCK_MS = 10 * 60_000
#: 每个渠道每小时最多发几条。
HOURLY_CAP = 30
#: 外审 1.1 第 4 轮 #3:一个渠道一拍最多发多久(坏渠道不拖别人);几个渠道一起发,最多几个。
CHANNEL_BUDGET_S = 20.0
#: 外审 1.1 第 5 轮 #1:每个渠道各取各的(不让一个渠道的积压占满全局的前 N 条),每渠道一拍最多取几条。
CHANNEL_BATCH = 100
MAX_PARALLEL = MAX_CHANNELS
BACKOFF_BASE_S, BACKOFF_MAX_S = 10, 300
TIMEOUT_S = 10
TELEGRAM_URL = "https://api.telegram.org/bot{token}/sendMessage"
WHATSAPP_URL = "https://graph.facebook.com/v21.0/{phone_id}/messages"
_TITLES = Path(__file__).parent / "i18n" / "alerts.json"
_PHONE = re.compile(r"^\+?[1-9][0-9]{6,15}$")
_CHAT = re.compile(r"^(-?[0-9]{1,20}|@[A-Za-z0-9_]{5,32})$")
_EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,190}\.[^@\s]{2,}$")
_HOST = re.compile(r"^[A-Za-z0-9.-]{1,253}$")
_TEMPLATE = re.compile(r"^[a-z0-9_]{1,512}$")


class NotifyError(ValueError):
    """渠道写得不对(接口回 400,原因是给人看的)。"""


class SendError(Exception):
    """这一次没发出去(网络、密钥、对方拒了)。``sent``:失败之前已经发到的收件人(外审 1.1 #6:
    重试只发没发到的)。``failed``:这一次试过、没发到的收件人(外审 1.1 第 6 轮 #2:
    下次先发没试过的)。"""

    def __init__(self, text: str, sent: list[str] | None = None,
                 failed: list[str] | None = None) -> None:
        super().__init__(text)
        self.sent = list(sent or [])
        self.failed = list(failed or [])


_TOKENISH = (re.compile(r"bot\d+:[A-Za-z0-9_-]{20,}"), re.compile(r"(?i)bearer\s+\S+"),
             re.compile(r"(?i)(access_token|token|key|password|secret)=[^&\s\"']+"))


def scrub(text: str, secret: str | None = None) -> str:
    """外审 1.1 #7:对方回的错误正文可能带着请求地址(Telegram 的令牌就在路径里)、口令。
    进日志、库、接口回包之前抹掉。"""
    out = str(text)
    if secret:
        for s in {secret, urllib.parse.quote(secret, safe=""), urllib.parse.quote(secret)}:
            if s:
                out = out.replace(s, "***")
    for r in _TOKENISH:
        out = r.sub(lambda m: (m.group(1) + "=***") if m.lastindex else "***", out)
    return out


# ---------------------------------------------------------------- 正文


_catalog: dict[str, dict[str, str]] | None = None


def _title(kind: str, lang: str, fallback: str) -> str:
    global _catalog
    if _catalog is None:
        try:
            _catalog = json.loads(_TITLES.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            _catalog = {}
    t = (_catalog or {}).get(kind)
    return t.get(lang) or fallback if isinstance(t, dict) else fallback


def message(*, site: str, level: str, kind: str, title: str, robot: str, ms: int, tz: Any,
            tier: int, lang: str) -> dict[str, str]:
    """一条告警的外发文字:``head``(一行)、``body``(几行)、``when``。"""
    when = datetime.fromtimestamp(ms / 1000, tz).strftime("%Y-%m-%d %H:%M")
    name = _title(kind, lang, title) if lang == "en" else (title or _title(kind, "zh", kind))
    if lang == "zh":
        again = "(仍未确认)" if tier > 0 else ""
        head = f"{site or '站点'} · {level}{again}:{name}"
        lines = [head, f"机器人:{robot}" if robot and robot != SITE else "站点",
                 f"时间:{when}", "打开 Nexus Warden App 或网页控制台处理。"]
    else:
        again = " (still not acknowledged)" if tier > 0 else ""
        head = f"{site or 'Site'} · {level}{again}: {name}"
        lines = [head, f"Robot: {robot}" if robot and robot != SITE else "Site",
                 f"Time: {when}", "Open the Nexus Warden app or web console to handle it."]
    return {"head": head, "body": "\n".join(lines), "when": when, "name": name}


def test_message(site: str, lang: str) -> dict[str, str]:
    if lang == "zh":
        head = f"{site or '站点'}:测试消息"
        return {"head": head, "body": head + "\n收到说明这个告警渠道已配置好。", "when": "",
                "name": "测试"}
    head = f"{site or 'Site'}: test message"
    return {"head": head, "body": head + "\nIf you can read this, the alert channel works.",
            "when": "", "name": "Test"}


# ---------------------------------------------------------------- 渠道


class _Watchdog:
    """外审 1.1 第 7 轮 #1:到了这一拍的截止时间,把盯着的连接的套接字掐断(``shutdown``)——
    卡在读写里的(一行一行慢慢回、零零碎碎地传)当场出错返回,不管它一次调用里读了几回。
    盯的是对象(连接、SMTP),掐的时候读它**当时**的 ``sock``(STARTTLS 换过的也掐得到)。"""

    def __init__(self, deadline: float | None) -> None:
        self.deadline = deadline
        self._objs: list[Any] = []
        self._lock = threading.Lock()
        self.fired = False
        self._t: threading.Timer | None = None
        if deadline is not None:
            self._t = threading.Timer(max(0.0, deadline - time.monotonic()), self._fire)
            self._t.daemon = True
            self._t.start()

    def watch(self, obj: Any) -> None:
        with self._lock:
            self._objs.append(obj)
            fired = self.fired
        if fired:
            self._cut(obj)

    def check(self) -> None:
        if self.fired:
            raise TimeoutError("这一拍时间用完")

    def cancel(self) -> None:
        if self._t is not None:
            self._t.cancel()

    @staticmethod
    def _cut(obj: Any) -> None:
        s = getattr(obj, "sock", None)
        if s is not None:
            try:
                s.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

    def _fire(self) -> None:
        with self._lock:
            self.fired = True
            objs = list(self._objs)
        for o in objs:
            self._cut(o)


#: 外审 1.1 第 13 轮 #2:同时卡在查域名上的最多几个(查域名不能中途掐,卡着的线程不再加)。
MAX_DNS_HUNG = 8
_DNS_SLOTS = threading.BoundedSemaphore(MAX_DNS_HUNG)


def _resolve(host: str, port: int, deadline: float | None) -> str:
    """外审 1.1 第 13 轮 #2:查域名也算进这一拍的截止时间。``getaddrinfo`` 掐不断、那时还没有套接字给
    看门狗掐 —— 放到单独的线程里查,最多等到截止;到点没查到抛 ``socket.timeout``(算没发成)。
    卡着的线程最多 :data:`MAX_DNS_HUNG` 个,满了的直接算超时。没截止时间、本来就是 IP 的照旧。"""
    if deadline is None:
        return host
    try:
        socket.inet_pton(socket.AF_INET6 if ":" in host else socket.AF_INET, host)
        return host
    except OSError:
        pass
    if deadline - time.monotonic() <= 0 or not _DNS_SLOTS.acquire(blocking=False):
        raise TimeoutError(f"查域名 {host} 没时间了(这一拍时间用完或查域名的都卡着)")
    box: dict[str, Any] = {}
    done = threading.Event()

    def run() -> None:
        try:
            box["r"] = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        except Exception as exc:                       # noqa: BLE001 - 交回调用的线程去报
            box["e"] = exc
        finally:
            _DNS_SLOTS.release()
            done.set()
    threading.Thread(target=run, daemon=True, name="notify-dns").start()
    if not done.wait(max(0.0, deadline - time.monotonic())):
        raise TimeoutError(f"查域名 {host} 超时(这一拍时间用完)")
    if "e" in box:
        raise box["e"]
    if not box["r"]:
        raise socket.gaierror(f"查不到 {host}")
    return str(box["r"][0][4][0])


def _dog_conn(base: type, dog: _Watchdog) -> Callable[..., Any]:
    """urllib 建连接用的:建出来的连接交给看门狗盯着;连上以后已经到点了就当场算超时。
    查域名也按截止时间(:func:`_resolve`);HTTPS 的证书、SNI 照旧按域名。"""
    class Conn(base):  # type: ignore[valid-type,misc]
        def connect(self) -> None:
            dog.watch(self)
            orig = self._create_connection

            def create(addr: Any, *a: Any, **kw: Any) -> Any:
                return orig((_resolve(addr[0], addr[1], dog.deadline), addr[1]), *a, **kw)
            self._create_connection = create
            super().connect()
            # 第 8 轮 #1:urllib 拿到回头以后把连接上的 sock 清掉,正文从响应文件接着读 ——
            # 看门狗另外记住这个套接字本身(HTTPS 是包了 TLS 的那个),读正文时到点也掐得到
            dog.watch(SimpleNamespace(sock=self.sock))
            dog.check()
    return Conn


class _DogHTTP(urllib.request.HTTPHandler):
    def __init__(self, dog: _Watchdog) -> None:
        super().__init__()
        self._dog = dog

    def http_open(self, req: Any) -> Any:
        return self.do_open(_dog_conn(http.client.HTTPConnection, self._dog), req)


class _DogHTTPS(urllib.request.HTTPSHandler):
    def __init__(self, dog: _Watchdog) -> None:
        super().__init__()
        self._dog = dog

    def https_open(self, req: Any) -> Any:
        return self.do_open(_dog_conn(http.client.HTTPSConnection, self._dog), req,
                            context=self._context)


def _post_json(url: str, body: dict[str, Any], headers: dict[str, str] | None = None,
               timeout: float = TIMEOUT_S, deadline: float | None = None) -> bytes:
    raw = json.dumps(body, ensure_ascii=False).encode()
    req = urllib.request.Request(url, data=raw, method="POST",
                                 headers={"Content-Type": "application/json", **(headers or {})})
    dog = _Watchdog(deadline)
    try:
        opener = urllib.request.build_opener(_DogHTTP(dog), _DogHTTPS(dog))
        with opener.open(req, timeout=timeout) as r:
            out = r.read(4096)
        dog.check()                                  # 掐断以后读到的半截不算发成
        return out
    except urllib.error.HTTPError as exc:
        try:
            detail = exc.read(300).decode("utf-8", "replace")
        except (OSError, TimeoutError, http.client.HTTPException):
            # 读错误正文时被看门狗掐断 / 对方断开:照样算这一次没发成,别把原始异常漏出去
            detail = "(正文没读完)"
        if dog.fired:
            raise SendError(f"HTTP {exc.code}:这一拍时间用完(对方太慢)") from exc
        raise SendError(f"HTTP {exc.code}:{detail}") from exc
    except (urllib.error.URLError, OSError, TimeoutError, http.client.HTTPException) as exc:
        if dog.fired:
            raise SendError("连不上:这一拍时间用完(对方太慢)") from exc
        raise SendError(f"连不上:{exc}") from exc
    finally:
        dog.cancel()


class OutOfTime(SendError):
    """外审 1.1 第 5 轮 #1:这一拍给这个渠道的时间用完了 —— 发到的记下,没轮到的下一拍接着
    (不算失败、不退避)。"""


def _timeout(ch: dict[str, Any]) -> float:
    """一次网络调用最多等多久:不超过 :data:`TIMEOUT_S`,也不超过这一拍剩下的时间(至少 1 秒)。"""
    dl = ch.get("_deadline")
    if dl is None:
        return TIMEOUT_S
    return max(1.0, min(float(TIMEOUT_S), dl - time.monotonic()))


class _DeadlineSMTP:
    """外审 1.1 第 6 轮 #3:SMTP 每一步(STARTTLS、登录、每个 RCPT、DATA)收发之前按剩下的时间重设超时;
    第 7 轮 #1:再加看门狗,到点把套接字掐断(一次回复里一行一行慢慢回也拖不过)。
    到点报 ``SMTPServerDisconnected``:发完了正文、在 QUIT 时到点的不算没发成。"""

    _deadline: float | None = None
    _dog: _Watchdog | None = None

    def _left(self) -> None:
        dl = self._deadline
        if dl is None:
            return
        left = dl - time.monotonic()
        if left <= 0 or (self._dog is not None and self._dog.fired):
            raise smtplib.SMTPServerDisconnected("这一拍时间用完")
        sock = getattr(self, "sock", None)
        if sock is not None:
            sock.settimeout(min(float(TIMEOUT_S), left))

    def _get_socket(self, host: str, port: int, timeout: float) -> Any:
        # 外审 1.1 第 13 轮 #2:查域名按截止时间;TLS 的证书、SNI 用的是 self._host(域名),不受影响
        return super()._get_socket(_resolve(host, port, self._deadline), port,  # type: ignore[misc]
                                   timeout)

    def send(self, s: Any) -> None:
        self._left()
        super().send(s)  # type: ignore[misc]

    def getreply(self) -> Any:
        self._left()
        return super().getreply()  # type: ignore[misc]

    def _arm(self, deadline: float | None) -> None:
        self._deadline = deadline
        self._dog = _Watchdog(deadline)
        self._dog.watch(self)

    def close(self) -> None:
        try:
            super().close()  # type: ignore[misc]
        finally:
            if self._dog is not None:
                self._dog.cancel()


class _SMTP(_DeadlineSMTP, smtplib.SMTP):
    def __init__(self, *a: Any, deadline: float | None = None, **kw: Any) -> None:
        self._arm(deadline)
        try:
            super().__init__(*a, **kw)
        except BaseException:
            self.close()
            raise


class _SMTP_SSL(_DeadlineSMTP, smtplib.SMTP_SSL):
    def __init__(self, *a: Any, deadline: float | None = None, **kw: Any) -> None:
        self._arm(deadline)
        try:
            super().__init__(*a, **kw)
        except BaseException:
            self.close()
            raise


class Sender:
    """真去发的那一层(测试换成假的)。``ch``:渠道的配置 + 打开了的密钥;
    ``ch["_deadline"]``(可没有):这一拍到哪个 ``time.monotonic()`` 为止。"""

    def send(self, ch: dict[str, Any], msg: dict[str, str], alert: dict[str, Any]) -> None:
        try:
            getattr(self, f"_{ch['kind']}")(ch, msg, alert)
        except SendError:
            raise
        except Exception as exc:  # noqa: BLE001 - 外审 1.1 第 2 轮 #9:别的异常里可能带着令牌地址
            raise SendError(f"发不出去({type(exc).__name__})") from None

    @staticmethod
    def _each(targets: list[str], one: Callable[[str], Any],
              deadline: float | None = None) -> None:
        """每个都试一遍(外审 1.1 第 2 轮 #7:前面坏一个不挡后面的);有没发到的带上发到了的。
        外审 1.1 第 5 轮 #1:到了 ``deadline`` 就停,没轮到的下一拍接着。"""
        sent: list[str] = []
        errs: list[str] = []
        failed: list[str] = []
        for i, t in enumerate(targets):
            if i and deadline is not None and time.monotonic() >= deadline:
                if errs:
                    break
                raise OutOfTime("这一拍时间用完,剩下的下一拍发", sent)
            try:
                one(t)
            except SendError as exc:
                errs.append(str(exc))
                failed.append(t)
                continue
            except Exception as exc:  # noqa: BLE001 - 原样的异常里可能带着令牌地址
                errs.append(f"发不出去({type(exc).__name__})")
                failed.append(t)
                continue
            sent.append(t)
        if errs:
            more = f"(共 {len(errs)} 个没发到)" if len(errs) > 1 else ""
            raise SendError(errs[0] + more, sent, failed)

    def _telegram(self, ch: dict[str, Any], msg: dict[str, str], alert: dict[str, Any]) -> None:
        url = TELEGRAM_URL.format(token=ch["secret"])
        self._each(ch["targets"], lambda chat: _post_json(
            url, {"chat_id": chat, "text": msg["body"], "disable_web_page_preview": True},
            timeout=_timeout(ch), deadline=ch.get("_deadline")), ch.get("_deadline"))

    def _whatsapp(self, ch: dict[str, Any], msg: dict[str, str], alert: dict[str, Any]) -> None:
        # 主动发给人要用 Meta 批过的模板(三个参数:站点 · 级别:告警、机器人、时间)
        cfg = ch["config"]
        url = WHATSAPP_URL.format(phone_id=cfg["phone_number_id"])
        params = [msg["head"], alert.get("robot") or "-", msg["when"] or "-"]
        self._each(ch["targets"], lambda to: _post_json(url, {
                "messaging_product": "whatsapp", "to": to.lstrip("+"), "type": "template",
                "template": {"name": cfg["template"], "language": {"code": cfg.get("template_lang")
                                                                    or "en"},
                             "components": [{"type": "body", "parameters": [
                                 {"type": "text", "text": p[:200]} for p in params]}]}},
                headers={"Authorization": f"Bearer {ch['secret']}"}, timeout=_timeout(ch),
                deadline=ch.get("_deadline")),
                   ch.get("_deadline"))

    def _email(self, ch: dict[str, Any], msg: dict[str, str], alert: dict[str, Any]) -> None:
        cfg = ch["config"]
        m = EmailMessage()
        m["Subject"] = msg["head"]
        m["From"] = cfg.get("from") or cfg.get("user")
        m["To"] = ", ".join(ch["targets"])
        m.set_content(msg["body"])
        host, port = cfg["host"], int(cfg.get("port") or 587)
        sec = cfg.get("security") or "starttls"
        try:
            if sec == "ssl":
                s: smtplib.SMTP = _SMTP_SSL(host, port, timeout=_timeout(ch),
                                            context=ssl.create_default_context(),
                                            deadline=ch.get("_deadline"))
            else:
                s = _SMTP(host, port, timeout=_timeout(ch), deadline=ch.get("_deadline"))
            with s:
                if sec == "starttls":
                    s.starttls(context=ssl.create_default_context())
                if cfg.get("user"):
                    s.login(cfg["user"], ch["secret"])
                refused = s.send_message(m) or {}
        except smtplib.SMTPRecipientsRefused as exc:
            raise SendError(f"邮件收件人都被拒:{len(exc.recipients)} 个") from None
        except (smtplib.SMTPException, OSError, TimeoutError) as exc:
            raise SendError(f"邮件发不出去:{exc}") from None
        if refused:                                  # 外审 1.1 第 2 轮 #6:拒了一部分的,只重发拒了的
            bad = {str(k).lower() for k in refused}
            raise SendError(f"邮件有 {len(refused)} 个收件人被拒",
                            [t for t in ch["targets"] if t.lower() not in bad])

    def _webhook(self, ch: dict[str, Any], msg: dict[str, str], alert: dict[str, Any]) -> None:
        body = {"site": alert.get("site", ""), "alert_key": alert.get("key", ""),
                "level": alert.get("level", ""), "kind": alert.get("kind", ""),
                "title": msg["name"], "robot": alert.get("robot", ""),
                "time_ms": alert.get("ms", 0), "tier": alert.get("tier", 0),
                "text": msg["body"]}
        headers = {}
        if ch.get("secret"):
            raw = json.dumps(body, ensure_ascii=False).encode()
            sig = hmac.new(ch["secret"].encode(), raw, hashlib.sha256).hexdigest()
            headers["X-Nexwar-Signature"] = sig
        self._each(ch["targets"], lambda url: _post_json(url, body, headers,
                                                          timeout=_timeout(ch),
                                                          deadline=ch.get("_deadline")),
                   ch.get("_deadline"))


# ---------------------------------------------------------------- 排队


def enqueue(tx: Any, alert: Any, now_ms: int) -> None:
    """告警写库的那个事务里调:没确认、没解决的,每个开着、级别对得上的渠道排一行。"""
    level = getattr(alert.level, "name", str(alert.level))
    if level not in LEVELS or alert.kind in NEVER \
            or alert.acked_ms is not None or alert.resolved_ms is not None:
        return
    for r in tx.execute("SELECT id, levels FROM notify_channels WHERE enabled=1").fetchall():
        if level in str(r["levels"]).split(","):
            tx.execute("INSERT OR IGNORE INTO notify_outbox(alert_key, tier, channel_id, "
                       "created_ms, next_ms) VALUES (?,?,?,?,?)",
                       (alert.key, int(alert.escalated), r["id"], now_ms, now_ms))


def _clean_targets(kind: str, raw: Any) -> list[str]:
    if isinstance(raw, str):
        raw = re.split(r"[,;\s]+", raw)
    if not isinstance(raw, list):
        raise NotifyError("收件人要是列表")
    out = [str(x).strip() for x in raw if str(x).strip()]
    if not out:
        raise NotifyError("至少要一个收件人")
    if len(out) > MAX_TARGETS:
        raise NotifyError(f"一个渠道最多 {MAX_TARGETS} 个收件人")
    check = {"telegram": (_CHAT, "Telegram chat id 要是数字(群是负数)或 @频道名"),
             "whatsapp": (_PHONE, "手机号要带国家码,比如 +60123456789"),
             "email": (_EMAIL, "邮箱地址不对")}.get(kind)
    for t in out:
        if check and not check[0].match(t):
            raise NotifyError(f"{check[1]}:{t[:60]}")
        if kind == "webhook":
            u = urllib.parse.urlparse(t)
            if u.scheme not in ("https", "http") or not u.hostname:
                raise NotifyError(f"webhook 地址要是 http(s)://…:{t[:60]}")
    return out


def _clean_config(kind: str, raw: Any) -> dict[str, Any]:
    cfg = raw if isinstance(raw, dict) else {}
    if kind == "email":
        host = str(cfg.get("host") or "").strip()
        if not _HOST.match(host):
            raise NotifyError("要填邮件服务器(SMTP)地址")
        port = cfg.get("port", 587)
        if not isinstance(port, int) or isinstance(port, bool) or not 1 <= port <= 65535:
            raise NotifyError("端口要是 1–65535")
        sec = cfg.get("security") or "starttls"
        if sec not in ("starttls", "ssl", "none"):
            raise NotifyError("加密方式要是 starttls / ssl / none")
        user = str(cfg.get("user") or "").strip()[:190]
        frm = str(cfg.get("from") or user).strip()[:190]
        if not _EMAIL.match(frm):
            raise NotifyError("要填发件人邮箱")
        return {"host": host, "port": port, "security": sec, "user": user, "from": frm}
    if kind == "whatsapp":
        pid = str(cfg.get("phone_number_id") or "").strip()
        if not re.fullmatch(r"[0-9]{5,25}", pid):
            raise NotifyError("要填 WhatsApp 的 Phone number ID(Meta 后台里的一串数字)")
        tpl = str(cfg.get("template") or "").strip()
        if not _TEMPLATE.match(tpl):
            raise NotifyError("要填 Meta 批过的消息模板名(小写字母、数字、下划线)")
        tl = str(cfg.get("template_lang") or "en").strip()
        if not re.fullmatch(r"[a-z]{2,3}(_[A-Z]{2})?", tl):
            raise NotifyError("模板语言要像 en、en_US、zh_CN")
        return {"phone_number_id": pid, "template": tpl, "template_lang": tl}
    return {}


class NotifyDesk:
    def __init__(self, db: Any, *, now_ms: Callable[[], int], sender: Any = None,
                 site_name: str = "", tz: Callable[[], Any] | None = None) -> None:
        self.db = db
        self._now = now_ms
        self.sender = sender if sender is not None else Sender()
        self.site_name = site_name
        self._tz = tz
        #: 告警台(站点主程序接上):发不出去报 P2。
        self.alerts: Any = None

    # ------------------------------------------------------------ 渠道增删改

    def _box(self) -> Any:
        box = getattr(self.db, "sealbox", None)
        if box is None:
            raise NotifyError("站点没配密钥(secrets.key),不能存渠道的令牌、口令")
        return box

    def _row_view(self, r: Any) -> dict[str, Any]:
        return {"id": r["id"], "kind": r["kind"], "name": r["name"],
                "targets": json.loads(r["targets"]), "levels": str(r["levels"]).split(","),
                "lang": r["lang"], "enabled": bool(r["enabled"]),
                "config": json.loads(r["config"] or "{}"), "has_secret": bool(r["secret"]),
                "last_ok_ms": r["last_ok_ms"], "last_error": r["last_error"],
                "updated_ms": r["updated_ms"]}

    def channels(self) -> list[dict[str, Any]]:
        return [self._row_view(r) for r in self.db.query("SELECT * FROM notify_channels "
                                                         "ORDER BY id")]

    def view(self) -> dict[str, Any]:
        recent = [dict(r) for r in self.db.query(
            "SELECT o.id, o.alert_key, o.tier, o.channel_id, o.created_ms, o.sent_ms, o.dropped, "
            "o.error, o.attempts, c.name AS channel FROM notify_outbox o "
            "LEFT JOIN notify_channels c ON c.id = o.channel_id ORDER BY o.id DESC LIMIT 20")]
        return {"channels": self.channels(), "recent": recent,
                "sealed": getattr(self.db, "sealbox", None) is not None,
                "kinds": list(KINDS), "hourly_cap": HOURLY_CAP}

    def save(self, d: dict[str, Any], *, cid: int | None = None) -> dict[str, Any]:
        """新建(``cid`` 是 ``None``)或改一个渠道。改的时候 ``secret`` 不给 = 不变。"""
        old = None
        if cid is not None:
            rows = self.db.query("SELECT * FROM notify_channels WHERE id=?", (cid,))
            if not rows:
                raise KeyError(cid)
            old = rows[0]
        kind = old["kind"] if old is not None else d.get("kind")
        if kind not in KINDS:
            raise NotifyError(f"种类要是 {' / '.join(KINDS)}")
        name = str(d.get("name") if "name" in d else (old["name"] if old else "")).strip()
        if not name or len(name) > 60:
            raise NotifyError("要起个名字(60 字以内)")
        targets = _clean_targets(kind, d["targets"] if "targets" in d
                                 else json.loads(old["targets"]) if old else None)
        levels = d.get("levels", str(old["levels"]).split(",") if old else ["P1"])
        if not isinstance(levels, list) or not levels or any(x not in LEVELS for x in levels):
            raise NotifyError("级别要从 P1、P2 里选,至少一个")
        lang = d.get("lang", old["lang"] if old else "en")
        if lang not in LANGS:
            raise NotifyError("语言要是 en / zh")
        config = _clean_config(kind, d["config"] if "config" in d
                               else json.loads(old["config"] or "{}") if old else {})
        enabled = d.get("enabled", bool(old["enabled"]) if old else True)
        if not isinstance(enabled, bool):
            raise NotifyError("enabled 要是 true / false")
        secret = d.get("secret")
        if secret is not None and not isinstance(secret, str):
            raise NotifyError("secret 要是字符串")
        sealed = old["secret"] if old is not None else ""
        if secret:
            if len(secret) > 1000:
                raise NotifyError("密钥太长")
            if any(ord(ch_) < 32 or ord(ch_) == 127 for ch_ in secret.strip()):
                raise NotifyError("密钥里有换行或控制字符,只粘贴令牌 / 口令本身")
            sealed = self._box().seal(secret.strip())
        if kind in ("telegram", "whatsapp") and not sealed:
            raise NotifyError("要填" + ("Telegram 机器人令牌(bot token)" if kind == "telegram"
                                       else "WhatsApp 访问令牌(access token)"))
        if kind == "email" and config.get("user") and not sealed:
            raise NotifyError("填了邮箱账号就要填口令")
        lv = ",".join(x for x in LEVELS if x in levels)
        now = self._now()
        with self.db.tx() as c:
            if old is None:
                n = c.execute("SELECT COUNT(*) AS n FROM notify_channels").fetchone()["n"]
                if n >= MAX_CHANNELS:
                    raise NotifyError(f"最多 {MAX_CHANNELS} 个渠道")
                cur = c.execute(
                    "INSERT INTO notify_channels(kind, name, targets, levels, lang, enabled, "
                    "config, secret, created_ms, updated_ms) VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (kind, name, json.dumps(targets), lv, lang, int(enabled), json.dumps(config),
                     sealed, now, now))
                cid = int(cur.lastrowid)
            else:
                c.execute("UPDATE notify_channels SET name=?, targets=?, levels=?, lang=?, "
                          "enabled=?, config=?, secret=?, updated_ms=? WHERE id=?",
                          (name, json.dumps(targets), lv, lang, int(enabled), json.dumps(config),
                           sealed, now, cid))
        return self._row_view(self.db.query("SELECT * FROM notify_channels WHERE id=?",
                                            (cid,))[0])

    def remove(self, cid: int) -> bool:
        with self.db.tx() as c:
            n = c.execute("DELETE FROM notify_channels WHERE id=?", (cid,)).rowcount
            c.execute("UPDATE notify_outbox SET dropped='渠道已删除' WHERE channel_id=? "
                      "AND sent_ms IS NULL AND dropped=''", (cid,))
        return bool(n)

    # ------------------------------------------------------------ 发

    def _channel(self, cid: int) -> dict[str, Any] | None:
        rows = self.db.query("SELECT * FROM notify_channels WHERE id=?", (cid,))
        if not rows:
            return None
        ch = self._row_view(rows[0])
        ch["secret"] = self._box().open(rows[0]["secret"]) if rows[0]["secret"] else ""
        return ch

    def _tzinfo(self) -> Any:
        if self._tz is not None:
            return self._tz()
        from nexwar_site.sitetime import site_tz
        return site_tz(self.db)

    def _robot_name(self, rid: str) -> str:
        if not rid or rid == SITE:
            return rid
        rows = self.db.query("SELECT display_name FROM robots WHERE robot_id=?", (rid,))
        return (rows[0]["display_name"] if rows else "") or rid

    def send_test(self, cid: int) -> dict[str, Any]:
        """给这个渠道发一条测试消息(当场发,回成没成)。"""
        ch = self._channel(cid)
        if ch is None:
            raise KeyError(cid)
        msg = test_message(self.site_name, ch["lang"])
        try:
            self.sender.send(ch, msg, {"site": self.site_name, "key": "test", "level": "test",
                                       "kind": "notify_test", "robot": "", "ms": self._now(),
                                       "tier": 0})
        except SendError as exc:
            err = scrub(str(exc), ch.get("secret"))[:300]
            self._mark(cid, error=err)
            return {"ok": False, "error": err}
        self._mark(cid, ok=True)
        return {"ok": True, "error": ""}

    def _mark(self, cid: int, *, ok: bool = False, error: str = "") -> None:
        with self.db.tx() as c:
            if ok:
                c.execute("UPDATE notify_channels SET last_ok_ms=?, last_error='' WHERE id=?",
                          (self._now(), cid))
            else:
                c.execute("UPDATE notify_channels SET last_error=? WHERE id=?", (error, cid))

    def _skip(self, row: dict[str, Any], now: int) -> str:
        if now - row["created_ms"] > EXPIRE_MS:
            return "一个小时未发出去,作废"
        a = self.db.query("SELECT acked_ms, resolved_ms FROM alerts WHERE key=?",
                          (row["alert_key"],))
        if a and (a[0]["acked_ms"] is not None or a[0]["resolved_ms"] is not None):
            return "已有人确认或解决了"
        return ""

    def _drop(self, oid: int, why: str) -> None:
        with self.db.tx() as c:
            c.execute("UPDATE notify_outbox SET dropped=? WHERE id=?", (why, oid))

    def tick(self) -> None:
        """要发的都发出去(要等网络:站点主程序放在线程里跑)。

        外审 1.1 第 4 轮 #3:各渠道各发各的(几个渠道一起发),每个渠道这一拍最多发
        :data:`CHANNEL_BUDGET_S` 秒,剩下的下一拍接着 —— 坏掉的渠道(一直超时)只拖它自己,
        不挡别的渠道,也不会让别的渠道的告警排到过期。

        外审 1.1 第 5 轮 #1:按渠道各取各的队列(坏渠道积压再多,也占不掉别的渠道的名额);
        预算一路传到每个收件人和每次网络调用,一条消息的多个超时收件人也不能拖过预算。"""
        now = self._now()
        due = "sent_ms IS NULL AND dropped='' AND next_ms<=?"
        by: dict[int, list[dict[str, Any]]] = {}
        for r in self.db.query(f"SELECT DISTINCT channel_id FROM notify_outbox WHERE {due}",
                               (now,)):
            cid = int(r["channel_id"])
            by[cid] = [dict(x) for x in self.db.query(
                f"SELECT * FROM notify_outbox WHERE {due} AND channel_id=? "
                "ORDER BY id LIMIT ?", (now, cid, CHANNEL_BATCH))]

        def run(queue: list[dict[str, Any]]) -> None:
            deadline = time.monotonic() + CHANNEL_BUDGET_S
            for row in queue:
                if time.monotonic() >= deadline:
                    break
                try:
                    self._send_row(row, deadline)
                except Exception:
                    log.exception("告警外发一条没处理成(下一拍再来)")

        if len(by) <= 1:
            for q in by.values():
                run(q)
        else:
            with ThreadPoolExecutor(max_workers=min(MAX_PARALLEL, len(by)),
                                    thread_name_prefix="notify") as ex:
                list(ex.map(run, by.values()))
        self._stuck(self._now())

    def _send_row(self, row: dict[str, Any], deadline: float | None = None) -> None:
        now = self._now()
        why = self._skip(row, now)
        if why:
            self._drop(row["id"], why)
            return
        try:
            ch = self._channel(row["channel_id"])
        except Exception as exc:  # noqa: BLE001 - 密钥打不开:这一条发不了,记原因
            self._drop(row["id"], f"渠道的密钥打不开:{exc}"[:300])
            return
        if ch is None or not ch["enabled"]:
            self._drop(row["id"], "渠道已删除或停用")
            return
        # 外审 1.1 #6:上限按「发出去过」算(发到一半的也算一条);发到一半的不再拦
        sent = self.db.query("SELECT COUNT(*) AS n FROM notify_outbox WHERE channel_id=? "
                             "AND first_sent_ms>?", (ch["id"], now - 3600_000))[0]["n"]
        done = [t for t in (row.get("done") or "").split("\n") if t]
        if not done and sent >= HOURLY_CAP:
            self._drop(row["id"], f"这个渠道一小时已发 {HOURLY_CAP} 条,这条不发")
            return
        a = self.db.query("SELECT * FROM alerts WHERE key=?", (row["alert_key"],))
        if not a:
            self._drop(row["id"], "告警不在了")
            return
        al = a[0]
        msg = message(site=self.site_name, level=al["level"], kind=al["kind"],
                      title=al["title"], robot=self._robot_name(al["robot"]),
                      ms=al["first_ms"], tz=self._tzinfo(), tier=row["tier"], lang=ch["lang"])
        # 外审 1.1 第 6 轮 #2:这一轮还没试过的排前面,试过没发到的排后面 —— 前面几个一直超时,
        # 后面的也轮得到;都试过一遍了再从头来
        tried = {t for t in (row.get("tried") or "").split("\n") if t}
        left = [t for t in ch["targets"] if t not in done]
        todo = dict(ch, targets=[t for t in left if t not in tried]
                    + [t for t in left if t in tried])
        if deadline is not None:
            todo["_deadline"] = deadline
        try:
            self.sender.send(todo, msg, {"site": self.site_name, "key": al["key"],
                                       "level": al["level"], "kind": al["kind"],
                                       "robot": self._robot_name(al["robot"]),
                                       "ms": al["first_ms"], "tier": row["tier"]})
        except OutOfTime as exc:                     # 时间用完:发到的记下,下一拍接着,不退避
            got = done + [t for t in exc.sent if t not in done]
            with self.db.tx() as c:
                c.execute("UPDATE notify_outbox SET done=?, "
                          "first_sent_ms=COALESCE(first_sent_ms, ?) WHERE id=?",
                          ("\n".join(got), now if got else None, row["id"]))
            return
        except SendError as exc:
            err = scrub(str(exc), ch.get("secret"))[:300]
            wait = min(BACKOFF_MAX_S, BACKOFF_BASE_S * 2 ** min(row["attempts"], 10))
            got = done + [t for t in getattr(exc, "sent", []) if t not in done]
            now_tried = (tried | set(getattr(exc, "failed", []))) - set(got)
            rest = [t for t in left if t not in got]
            if set(rest) <= now_tried:                   # 剩下的都试过一遍了:下一轮从头来
                now_tried = set()
            with self.db.tx() as c:
                c.execute("UPDATE notify_outbox SET attempts=attempts+1, next_ms=?, error=?, "
                          "done=?, tried=?, first_sent_ms=COALESCE(first_sent_ms, ?) WHERE id=?",
                          (now + wait * 1000, err, "\n".join(got),
                           "\n".join(t for t in left if t in now_tried),
                           now if got else None, row["id"]))
            self._mark(ch["id"], error=err)
            log.warning("告警外发(%s)没发出去,%s 秒后再试:%s", ch["name"], wait, err)
            return
        with self.db.tx() as c:
            c.execute("UPDATE notify_outbox SET sent_ms=?, error='', "
                      "first_sent_ms=COALESCE(first_sent_ms, ?) WHERE id=?",
                      (self._now(), self._now(), row["id"]))
        self._mark(ch["id"], ok=True)
        log.info("告警外发(%s)发出去了:%s", ch["name"], row["alert_key"])

    def _stuck(self, now: int) -> None:
        if self.alerts is None:
            return
        oldest = self.db.query("SELECT MIN(created_ms) AS t FROM notify_outbox WHERE "
                               "sent_ms IS NULL AND dropped='' AND attempts>0")[0]["t"]
        stuck = oldest is not None and now - oldest >= STUCK_MS
        open_ = self.alerts.has_open(SITE, "notify_failed")
        if stuck and not open_:
            err = self.db.query("SELECT name, last_error FROM notify_channels "
                                "WHERE last_error!='' ORDER BY updated_ms DESC LIMIT 1")
            detail = f"{err[0]['name']}:{err[0]['last_error']}" if err else "一直发不出去"
            self.alerts.raise_alert(kind="notify_failed", robot=SITE,
                                    title="告警外发发不出去:WhatsApp / Telegram / 邮件收不到",
                                    detail=detail[:250] + ";看站点能不能上外网、渠道的令牌是否正确")
        elif not stuck and oldest is None and open_:
            # 外审 1.1 第 2 轮 #8:积压的过期作废不算恢复;开着的渠道最近一次都发成了才算
            bad = self.db.query("SELECT 1 FROM notify_channels WHERE enabled=1 AND "
                                "last_error!='' LIMIT 1")
            if not bad:
                self.alerts.resolve_all(SITE, "notify_failed", who="site:notify_ok")

