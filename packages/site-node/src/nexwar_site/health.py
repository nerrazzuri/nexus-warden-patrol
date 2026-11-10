"""站点健康与诊断(商业化 A1)。

- **体检**(:meth:`HealthDesk.checks`,``GET /api/health``,管理员):库能写、事件循环没卡、MQTT 连着、
  站点盘和备份盘够不够、备份和校验、推送、狗在线几台、证书还有多久到期(站点服务证书、每只狗的)、
  有没有卡住的后台道、版本。每一项 ``ok`` + 说人话的 ``detail``。
- **探活**(:meth:`HealthDesk.healthz`,``GET /healthz``,**不用登录**):外面的监控、以后的热备探它。
  只回好不好、版本,**不给细节**(不登录的人看不到站点的情况)。好回 200,不好回 503。
- **自己盯着**(:meth:`HealthDesk.tick`,每小时一拍):证书 30 天内到期、站点盘剩不到 10%、后台道卡住
  超过 5 分钟 → 报 **P2**,好了自动解决;按当前状态每拍对账(报、解决失败了下一拍再来)。
- **指标历史**(:meth:`HealthDesk.record`,每 5 分钟一笔,留 30 天):盘、狗在线、开着的 P1/P2、狗上
  待传的、事件循环延迟。诊断包里导成 CSV;以后手机画趋势用。
- **诊断包**(:func:`support_bundle`,``nexwar_site support-bundle``、``GET /api/support-bundle``):
  一个 tar.gz,给我们远程看问题用。**不带**密钥、令牌、库文件、照片录像、狗的位置;站点配置里像口令、
  密钥的值打码;日志里长串十六进制、``Bearer`` 令牌打码。
"""

from __future__ import annotations

import csv
import io
import json
import logging
import platform
import re
import shutil
import subprocess
import tarfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from nexwar_site.alert_sources import SITE

log = logging.getLogger(__name__)

_KEY_EN = {"secrets": "password encryption key", "backup": "backup encryption key",
           "evidence": "evidence encryption key"}


def _key_problem_en(problem: str) -> str:
    for zh, en in (("没有这把密钥", "missing"), ("无法读取", "cannot be read"),
                   ("长度错误", "wrong length"), ("是空的", "empty"),
                   ("权限过宽", "readable by other users")):
        if problem.startswith(zh):
            return en
    return "problem"


#: 证书剩不到这么多天报 P2。
CERT_WARN_DAYS = 30
#: 盘剩不到这么多(比例)报 P2;探活也算不好。
DISK_LOW = 0.10
#: 事件循环多久没转算卡住(秒)。
LOOP_STUCK_S = 5.0
#: 后台道一轮跑了多久算卡住(秒)。
LANE_STUCK_S = 300.0
#: 多久记一笔指标、留多久。
METRICS_EVERY_MS = 5 * 60_000
METRICS_KEEP_MS = 90 * 86_400_000    # 用户 11-10:日志、记录默认都留 90 天
#: 多久对一次账(报、解决 P2)。
TICK_EVERY_MS = 3600_000

#: 探活只看这几项:坏了站点就不能用。
CRITICAL = ("db", "loop", "broker", "disk")


def _openssl_enddate(cert: Path) -> int | None:
    """证书到期时刻(毫秒);读不了回 ``None``。"""
    try:
        got = subprocess.run(["openssl", "x509", "-enddate", "-noout", "-in", str(cert)],
                             capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return None
    m = re.search(r"notAfter=(.+)", got.stdout)
    if got.returncode != 0 or m is None:
        return None
    try:
        return int(time.mktime(time.strptime(m.group(1).strip(), "%b %d %H:%M:%S %Y %Z"))
                   - time.timezone) * 1000
    except ValueError:
        return None


def site_version() -> str:
    """产品版本(W57:站点、机器人、App 同一个号,客户看到的就是它)。"""
    from nexwar_contract.product import PRODUCT_VERSION
    return PRODUCT_VERSION


#: 英文界面(网页易用性第 2 轮 P1-01):检查说明带一份英文 ``detail_en``。
NOT_WIRED_EN = "Not connected (command-line run)"

class HealthDesk:
    def __init__(self, db: Any, *, home: Path, now_ms: Callable[[], int],
                 dispatcher: Any = None, backup: Any = None, push: Any = None,
                 loop_lag: Callable[[], float | None] | None = None,
                 lanes: Callable[[], dict[str, float]] | None = None,
                 disk_usage: Callable[[Path], Any] = shutil.disk_usage,
                 cert_end: Callable[[Path], int | None] = _openssl_enddate,
                 monotonic: Callable[[], float] = time.monotonic,
                 keys: Callable[[], list[dict[str, Any]]] | None = None) -> None:
        self.db = db
        self.home = Path(home)
        self._now = now_ms
        self.dispatcher = dispatcher
        self.backup = backup
        self.push = push
        self._loop_lag = loop_lag
        #: 正在跑的后台道:名字 → 这一轮起跑的单调钟秒。
        self._lanes = lanes
        self._disk = disk_usage
        self._cert_end = cert_end
        self._mono = monotonic
        #: 站点密钥自检(A3,``keyvault.status``)。
        self._keys = keys
        #: 告警台(站点主程序接线程安全的那个):P2。
        self.alerts: Any = None
        self._next_tick = 0
        self._next_record = 0

    # ------------------------------------------------------------ 体检

    def _free(self, path: Path) -> float | None:
        try:
            u = self._disk(path)
            return u.free / u.total if u.total else None
        except OSError:
            return None

    def _certs(self) -> list[tuple[str, int | None]]:
        """(谁, 到期时刻):站点服务证书、每只狗的证书(吊销了的不算)。"""
        out = [("站点服务证书", self._cert_end(self.home / "ca" / "server" / "server.crt"))]
        revoked = {r["robot_id"] for r in self.db.query(
            "SELECT robot_id FROM robots WHERE revoked=1")} if self._has("robots") else set()
        issued = self.home / "ca" / "issued"
        if issued.is_dir():
            for d in sorted(issued.iterdir()):
                crt = d / "robot.crt"
                if crt.is_file() and d.name not in revoked:
                    end = self._cert_end(crt)
                    used = self._in_use_end(d.name)
                    if used is not None and (end is None or used < end):
                        # 工单 9:续签后站点这边是新证书,狗上还是旧的 —— 按狗报的在用证书算
                        out.append((f"机器人 {d.name} 在用的证书", used))
                    else:
                        out.append((f"机器人 {d.name} 的证书", end))
        return out

    def _in_use_end(self, robot_id: str) -> int | None:
        """狗报的它在用的证书哪天到期(能力 ``tls.expires_ms``;老代理不报)。"""
        c = getattr(self.dispatcher, "clients", {}).get(robot_id) if self.dispatcher else None
        caps = getattr(c, "capabilities", None)
        tls = getattr(caps, "tasks", {}).get("tls") if caps is not None else None
        v = tls.get("expires_ms") if isinstance(tls, dict) else None
        return int(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None

    def _has(self, table: str) -> bool:
        return bool(self.db.query("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                                  (table,)))

    def checks(self) -> dict[str, dict[str, Any]]:
        now = self._now()
        out: dict[str, dict[str, Any]] = {}
        try:
            with self.db.tx() as c:
                c.execute("INSERT OR REPLACE INTO meta VALUES ('health_ping', ?)", (str(now),))
            out["db"] = {"ok": True, "detail": "库能写", "detail_en": "Database is writable"}
        except Exception as exc:  # noqa: BLE001
            out["db"] = {"ok": False, "detail": f"库无法写入:{exc}"[:200],
                         "detail_en": f"Cannot write to the database: {exc}"[:200]}
        lag = self._loop_lag() if self._loop_lag is not None else None
        out["loop"] = ({"ok": True, "detail": "未接入(命令行)", "detail_en": NOT_WIRED_EN}
                       if lag is None else
                       {"ok": lag < LOOP_STUCK_S, "value": round(lag, 2),
                        "detail": f"事件循环 {lag:.1f} 秒前转过"
                                  + ("" if lag < LOOP_STUCK_S else ":卡住"),
                        "detail_en": f"Event loop last ran {lag:.1f} s ago"
                                     + ("" if lag < LOOP_STUCK_S else ": stuck")})
        t = getattr(self.dispatcher, "_t", None) if self.dispatcher is not None else None
        conn = getattr(t, "connected", None)
        out["broker"] = ({"ok": True, "detail": "未接入(命令行)", "detail_en": NOT_WIRED_EN}
                         if conn is None else
                         {"ok": bool(conn), "detail": "连着 MQTT" if conn else "MQTT 已断开",
                          "detail_en": "Connected to the message broker" if conn
                          else "Message broker disconnected"})
        free = self._free(self.home)
        out["disk"] = ({"ok": False, "detail": "无法测量站点盘",
                        "detail_en": "Cannot measure the site disk"} if free is None else
                       {"ok": free >= DISK_LOW, "value": round(free, 3),
                        "detail": f"站点盘还剩 {free:.0%}",
                        "detail_en": f"Site disk {free:.0%} free"})
        dest = getattr(self.backup, "dest", None) if self.backup is not None else None
        if dest is not None:
            bfree = self._free(Path(dest))
            st = self.backup.status()
            ver = st.get("verify") or {}
            ok = bfree is not None and bfree >= DISK_LOW and not st.get("stale") \
                and ver.get("ok", True)
            out["backup"] = {"ok": ok, "value": bfree,
                             "detail": "备份盘" + (f"还剩 {bfree:.0%}" if bfree is not None
                                                   else "无法测量")
                             + (";备份已过期" if st.get("stale") else "")
                             + (";上次校验未通过" if ver and not ver.get("ok") else ""),
                             "detail_en": "Backup disk "
                             + (f"{bfree:.0%} free" if bfree is not None else "cannot be measured")
                             + ("; backup is out of date" if st.get("stale") else "")
                             + ("; last check failed" if ver and not ver.get("ok") else "")}
        else:
            out["backup"] = {"ok": False, "detail": "未配置备份:站点主机损坏将导致数据丢失",
                             "detail_en": "No backup set up: if the site computer fails, "
                                          "data will be lost"}
        if self.push is not None:
            v = self.push.view()
            out["push"] = {"ok": bool(v["configured"]) and not v["error"],
                           "detail": (v["error"] or self._push_detail(v)),
                           "detail_en": self._push_detail_en(v)}
        if self.dispatcher is not None:
            clients = getattr(self.dispatcher, "clients", {})
            online = [rid for rid, c in clients.items()
                      if c.status is not None and c.status.online]
            out["robots"] = {"ok": True, "value": len(online),
                             "detail": f"{len(online)}/{len(clients)} 台机器人在线",
                             "detail_en": f"{len(online)}/{len(clients)} robots online"}
        soon, worst = [], None
        for who, end in self._certs():
            if end is None:
                soon.append(f"{who}无法读取到期时间")
                continue
            days = (end - now) / 86_400_000
            worst = days if worst is None else min(worst, days)
            if days < CERT_WARN_DAYS:
                renewed = "在用的证书" in who
                soon.append(f"{who}还有 {max(days, 0):.0f} 天到期"
                            + ("(新证书已签发、机器人未换上:诊断页「立即续签证书」;"
                               "老代理拷到机器人上、重启代理)" if renewed else
                               "(自动续签未成:诊断页「立即续签证书」或 nexwar_site renew)"
                               if who.startswith("机器人") else ""))
        out["certs"] = {"ok": not soon, "value": None if worst is None else round(worst, 1),
                        "detail": ";".join(soon)[:300] or (f"证书最近的还有 {worst:.0f} 天到期"
                                                          if worst is not None else "没有证书"),
                        "detail_en": (f"{len(soon)} certificate(s) need attention — "
                                      "use “Renew certificates now” below" if soon else
                                      f"Next certificate expires in {worst:.0f} days"
                                      if worst is not None else "No certificates")}
        if self._keys is not None:
            bad = [f"{r['name']}:{r['problem']}" for r in self._keys() if r["problem"]]
            out["keys"] = {"ok": not bad,
                           "detail": ";".join(bad)[:300] or "站点密钥都在、权限对",
                           # 第 4 轮 admin P1-01:英文也写出是哪几把(原来只有中文悬停里有)
                           "detail_en": ("Site key problem: " + ", ".join(
                               f"{_KEY_EN.get(r['name'], r['name'])} "
                               f"({_key_problem_en(r['problem'])})"
                               for r in self._keys() if r["problem"])
                               ) if bad
                           else "Site keys present, permissions correct"}
        lanes = self._lanes() if self._lanes is not None else {}
        stuck = [n for n, t0 in lanes.items() if self._mono() - t0 > LANE_STUCK_S]
        out["lanes"] = {"ok": not stuck,
                        "detail": ("卡住:" + "、".join(stuck)) if stuck else "后台道都在转",
                        "detail_en": ("Stuck: " + ", ".join(stuck)) if stuck
                        else "Background workers running"}
        return out

    @staticmethod
    def _push_detail(v: dict[str, Any]) -> str:
        if not v["configured"]:
            return v["why_off"]
        text = f"推送已配({'、'.join(v.get('providers') or [])}),{v['devices']} 台手机登记了"
        if v.get("devices_unreachable"):
            text += f";其中 {v['devices_unreachable']} 台登记的通道站点未配置,无法接收"
        if v["why_off"]:
            text += f";{v['why_off']}"
        return text

    @staticmethod
    def _push_detail_en(v: dict[str, Any]) -> str:
        if v["error"]:
            return "Push notifications have an error"
        if not v["configured"]:
            return "Push notifications are not set up"
        text = (f"Push set up ({', '.join(v.get('providers') or [])}), "
                f"{v['devices']} phone(s) registered")
        if v.get("devices_unreachable"):
            text += (f"; {v['devices_unreachable']} of them use a channel this site "
                     "has not set up and cannot receive")
        return text

    def healthz(self) -> tuple[bool, dict[str, Any]]:
        """探活:只回好不好、版本(不登录的人看不到细节)。"""
        c = self.checks()
        ok = all(c[k]["ok"] for k in CRITICAL if k in c)
        return ok, {"ok": ok, "version": site_version()}

    def view(self) -> dict[str, Any]:
        c = self.checks()
        return {"ok": all(v["ok"] for v in c.values()),
                "critical_ok": all(c[k]["ok"] for k in CRITICAL if k in c),
                "checks": c, "version": site_version(), "now_ms": self._now()}

    # ------------------------------------------------------------ 自己盯着、记指标

    def tick(self) -> None:
        """每小时按体检结果对账 P2(证书快到期、站点盘紧、后台道卡住);每 5 分钟记一笔指标。
        站点杂事线程里调(告警走线程安全的那个告警台)。"""
        now = self._now()
        if now >= self._next_record:
            self._next_record = now + METRICS_EVERY_MS
            self.record()
        if now < self._next_tick or self.alerts is None:
            return
        c = self.checks()
        done = True
        for kind, key, title in (("cert_expiring", "certs", "证书即将到期"),
                                 ("site_disk_low", "disk", "站点盘即将写满"),
                                 ("lane_stuck", "lanes", "站点后台有活卡住")):
            try:
                open_ = self.alerts.has_open(SITE, kind)
                if not c[key]["ok"] and not open_:
                    self.alerts.raise_alert(kind=kind, robot=SITE, title=title,
                                            detail=c[key]["detail"][:300])
                elif c[key]["ok"] and open_:
                    self.alerts.resolve_all(SITE, kind, who="site:health")
            except Exception:
                log.exception("体检告警 %s 没对上(下一拍再来)", kind)
                done = False
        if done:
            self._next_tick = now + TICK_EVERY_MS

    def record(self) -> None:
        """记一笔指标(留 30 天)。"""
        now = self._now()
        vals: dict[str, float] = {}
        free = self._free(self.home)
        if free is not None:
            vals["site_disk_free"] = free
        lag = self._loop_lag() if self._loop_lag is not None else None
        if lag is not None:
            vals["loop_lag_s"] = lag
        if self.dispatcher is not None:
            clients = getattr(self.dispatcher, "clients", {})
            vals["robots_online"] = sum(1 for c in clients.values()
                                        if c.status is not None and c.status.online)
            backlog = 0
            for st in getattr(self.dispatcher, "storage", {}).values():
                backlog += getattr(st[0], "backlog_files", 0) or 0
            vals["upload_backlog"] = backlog
        if self._has("alerts"):
            for lv in ("P1", "P2"):
                vals[f"alerts_open_{lv}"] = self.db.query(
                    "SELECT COUNT(*) AS n FROM alerts WHERE level=? AND resolved_ms IS NULL",
                    (lv,))[0]["n"]
        with self.db.tx() as c:
            c.executemany("INSERT INTO metrics(ts, key, value) VALUES (?,?,?)",
                          [(now, k, float(v)) for k, v in vals.items()])
            c.execute("DELETE FROM metrics WHERE ts<?", (now - METRICS_KEEP_MS,))

    def metrics(self, *, key: str | None = None, since_ms: int = 0) -> list[dict[str, Any]]:
        q, args = "SELECT ts, key, value FROM metrics WHERE ts>=?", [since_ms]
        if key:
            q += " AND key=?"
            args.append(key)
        return [dict(r) for r in self.db.query(q + " ORDER BY ts, key LIMIT 50000", tuple(args))]


# ------------------------------------------------------------ 诊断包

_SECRET_KEY = re.compile(r"(secret|password|passwd|token|key|pin|credential)", re.I)
_LONG_HEX = re.compile(r"\b[0-9a-fA-F]{32,}\b")
_BEARER = re.compile(r"(Bearer\s+)[A-Za-z0-9._~+/=-]+")


def redact_cfg(v: Any, key: str = "") -> Any:
    """站点配置打码:键名像口令、密钥的值换成 ``***``(``*_file`` 这种路径不打:它不是密钥本身)。"""
    if isinstance(v, dict):
        return {k: redact_cfg(x, k) for k, x in v.items()}
    if isinstance(v, list):
        return [redact_cfg(x, key) for x in v]
    if isinstance(v, str) and _SECRET_KEY.search(key) and not key.endswith(("_file", "_dir")):
        return "***" if v else ""
    return v


def redact_text(s: str) -> str:
    """日志打码:``Bearer`` 令牌、长串十六进制(令牌哈希、密钥、指纹)只留前 8 位。"""
    s = _BEARER.sub(r"\1***", s)
    return _LONG_HEX.sub(lambda m: m.group(0)[:8] + "…", s)


def _journal(unit: str, hours: int) -> str:
    try:
        got = subprocess.run(["journalctl", "-u", unit, "--since", f"-{hours}h", "--no-pager",
                              "-o", "short-iso"], capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"(无法读取 {unit} 的日志:{exc})\n"
    if got.returncode != 0 and not got.stdout:
        return f"(无法读取 {unit} 的日志:{got.stderr.strip()[:300]})\n"
    return got.stdout


class RecentLog(logging.Handler):
    """网页易用性 P1-73:站点进程自己留最近的日志(带时刻),诊断包里放一份 ——
    站点不是按系统服务跑(演示站、直接起的)时 journalctl 是空的,有这份才看得到东西。"""

    def __init__(self, keep: int = 20000, keep_access: int = 5000) -> None:
        super().__init__(level=logging.INFO)
        import collections
        self.rows: collections.deque[tuple[float, str]] = collections.deque(maxlen=keep)
        # 第 3 轮 config N8:成功的 GET 访问记录另放(原来每秒几十条,5000 条只够 1 分钟)
        self.access: collections.deque[tuple[float, str]] = collections.deque(maxlen=keep_access)
        from nexwar_contract.logsetup import Formatter
        self.setFormatter(Formatter())             # 跟日志文件一个格式(日志设计 第 3 条)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            row = (record.created, self.format(record))
            (self.access if getattr(record, "access", False) else self.rows).append(row)
        except Exception:  # noqa: BLE001 —— 记日志不能把站点弄崩
            pass

    def text(self, hours: int, now_s: float) -> str:
        since = now_s - hours * 3600
        return "".join(line + "\n" for at, line in list(self.rows) if at >= since)

    def access_text(self, hours: int, now_s: float) -> str:
        since = now_s - hours * 3600
        return "".join(line + "\n" for at, line in list(self.access) if at >= since)


#: 站点进程里装上的那一个(main 起站点时装;没装 = None,诊断包里就不放这份)。
RECENT: RecentLog | None = None


def install_recent_log() -> RecentLog:
    global RECENT
    if RECENT is None:
        RECENT = RecentLog()
        logging.getLogger().addHandler(RECENT)
    return RECENT


#: 诊断包里带日志的站点主机服务(W55:加 VPN、对时)。
BUNDLE_UNITS = ("nexwar_site", "nexwar_mosquitto", "wg-quick@nexwar", "chrony", "nexwar_ops")


def support_bundle(out: Path, *, home: Path, db: Any, health: HealthDesk | None,
                   hours: int = 24, now_ms: int,
                   journal: Callable[[str, int], str] = _journal,
                   extra: dict[str, bytes] | None = None,
                   since_ms: int | None = None, until_ms: int | None = None,
                   robot: str | None = None, task: str | None = None, scene: str = "",
                   by: str = "", robot_logs: Any = None, log_dir: Path | None = None) -> Path:
    """写诊断包 ``out``(tar.gz)。回 ``out``。

    日志设计 第 5 条(用户 11-10):按时间段、按场景(某台机器人、某个任务、某条告警)导出,
    管理员下载了发给工程师。时间段是**出事的那一段**,不是导出这一刻往前(人把机器人拉回来、过几天
    再导也取得到,只要在留存期里)。分五块:

    - ``site/``:站点日志、访问记录、版本、配置(打码)、体检、库表行数、指标;
    - ``robots/<编号>/``:传上来的各服务日志、轨迹(站点记的 + 机器人日志里补的)、
      当时在线的诊断快照;
    - ``records/``:操作记录(含系统事件)、告警、日程每一轮、命令和回执、事件;
    - ``clients/``:App、网页的错误记录;
    - ``host/``:消息服务、VPN、对时等主机服务的日志。
    - ``README.md``:时间段、场景、谁导出的、这段时间出现过的错误码和次数(附手册说明)。

    不带密钥、令牌、库文件、照片录像。``extra`` 是 API 那边另外取来的(在线机器人的诊断快照、
    App 与网页的错误记录),按名字放进对应的块。"""
    import datetime as _dt
    since = since_ms if since_ms is not None else now_ms - hours * 3_600_000
    until = until_ms if until_ms is not None else now_ms
    span_h = max(1, min(24 * 90, -(-(now_ms - since) // 3_600_000)))     # 往上取整到小时
    files: dict[str, bytes] = {}

    def put(name: str, obj: Any) -> None:
        files[name] = (obj if isinstance(obj, bytes) else
                       json.dumps(obj, ensure_ascii=False, indent=1, default=str).encode())

    def query(sql: str, args: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        try:
            return [dict(r) for r in db.query(sql, args)]
        except Exception as exc:  # noqa: BLE001 —— 一张表取不到,别的照样打进包
            return [{"error": str(exc)[:300]}]

    def in_range(text: str) -> str:
        """按行头时刻筛进时间段(取不出时刻的行跟着上一行)。"""
        from nexwar_contract.logsetup import _line_time
        keep, out_ = True, []
        for ln in text.splitlines(keepends=True):
            at = _line_time(ln)
            if at is not None:
                keep = since / 1000 - 1 <= at <= until / 1000 + 1
            if keep:
                out_.append(ln)
        return "".join(out_)

    tables = {r["name"] for r in db.query("SELECT name FROM sqlite_master WHERE type='table'")}
    # ---- site/
    put("site/versions.json", {"site": site_version(), "python": platform.python_version(),
                               "os": platform.platform(), "generated_ms": now_ms,
                               "schema": (db.query("SELECT value FROM meta WHERE key='schema'")
                                          or [{"value": "?"}])[0]["value"]})
    if health is not None:
        try:
            put("site/health.json", health.view())
        except Exception as exc:  # noqa: BLE001
            put("site/health.json", {"error": str(exc)[:300]})
    try:
        cfg = json.loads((home / "site.json").read_text(encoding="utf-8"))
        put("site/site.json", redact_cfg(cfg))
    except (OSError, ValueError) as exc:
        put("site/site.json", {"error": f"无法读取:{exc}"})
    put("site/db_counts.json", {t: db.query(f'SELECT COUNT(*) AS n FROM "{t}"')[0]["n"]
                                for t in sorted(tables)})
    if "metrics" in tables:
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["ts", "key", "value"])
        for r in db.query("SELECT ts, key, value FROM metrics WHERE ts BETWEEN ? AND ? "
                          "ORDER BY ts, key", (since, until)):
            w.writerow([r["ts"], r["key"], r["value"]])
        files["site/metrics.csv"] = buf.getvalue().encode()
    from nexwar_contract import logsetup
    ldir = log_dir if log_dir is not None else home / "logs"
    grep = task or None
    if ldir.is_dir():
        files["site/site.log"] = redact_text(logsetup.read_range(
            ldir, "site", since_s=since / 1000, until_s=until / 1000)).encode()
        files["site/access.log"] = redact_text(logsetup.read_range(
            ldir, "access", since_s=since / 1000, until_s=until / 1000)).encode()
        if grep:
            files[f"site/task-{grep}.log"] = redact_text(logsetup.read_range(
                ldir, "site", since_s=since / 1000, until_s=until / 1000, grep=grep)).encode()
    if RECENT is not None:                       # 站点进程内存里的最近日志(没写文件的老装法也有)
        files["site/site-recent.log"] = redact_text(in_range(RECENT.text(span_h, now_ms / 1000))
                                                    ).encode()
        files["site/site-access-recent.log"] = redact_text(in_range(RECENT.access_text(
            span_h, now_ms / 1000))).encode()
    # ---- host/(以及站点自己的 systemd 日志)
    for unit in BUNDLE_UNITS:
        got = journal(unit, span_h)
        if not got.strip() or got.strip() == "-- No entries --":
            got = (f"(这段时间没有 {unit} 的系统服务日志。站点不是按系统服务运行时,"
                   "站点自己的日志见 site/site.log)\n")
        else:
            got = in_range(got) or got
        name = "site/journal.log" if unit == "nexwar_site" else f"host/{unit}.log"
        files[name] = redact_text(got).encode()
    # ---- records/
    rob = (robot,) if robot else ()
    rwhere = " AND robot_id=?" if robot else ""
    if "alerts" in tables:
        put("records/alerts.json", query(
            "SELECT key, kind, level, robot, title, detail, count, first_ms, last_ms, acked_by, "
            "acked_ms, resolved_by, resolved_ms, verdict, escalated, context FROM alerts "
            "WHERE last_ms>=? AND first_ms<=?" + (" AND robot=?" if robot else "")
            + " ORDER BY first_ms LIMIT 5000", (since, until, *rob)))
    if "events" in tables:
        rows = query("SELECT robot_id, kind, data, stamp, received_at FROM events "
                     "WHERE received_at BETWEEN ? AND ?" + rwhere
                     + " ORDER BY received_at LIMIT 50000", (since, until, *rob))
        if grep:
            rows = [r for r in rows if grep in str(r.get("data", ""))] or rows
        files["records/events.json"] = redact_text(json.dumps(
            rows, ensure_ascii=False, indent=1, default=str)).encode()
    if "commands" in tables:
        # 命令只带种类和回执,不带内容(换 WiFi 的命令里有密码)
        put("records/commands.json", query(
            "SELECT command_id, task_id, robot_id, kind, issued_by, issued_at, ack_result, "
            "ack_reason FROM commands WHERE issued_at BETWEEN ? AND ?" + rwhere
            + " ORDER BY issued_at LIMIT 20000", (since, until, *rob)))
    if "audit" in tables:
        files["records/audit.json"] = redact_text(json.dumps(query(
            "SELECT at, actor, action, target, status, detail, remote FROM audit "
            "WHERE at BETWEEN ? AND ? ORDER BY at LIMIT 50000", (since, until)),
            ensure_ascii=False, indent=1, default=str)).encode()
    if "schedule_runs" in tables:
        put("records/schedule_runs.json", query(
            "SELECT * FROM schedule_runs WHERE scheduled_ms BETWEEN ? AND ? ORDER BY scheduled_ms "
            "LIMIT 20000", (since - 86_400_000, until)))
    # ---- robots/
    if "robots" in tables:
        put("robots/robots.json", [{k: r[k] for k in r if k in (
            "robot_id", "enrolled_at", "revoked", "manual_only")} for r in query(
            "SELECT * FROM robots")])
    ids: set[str] = set(rob)
    if not robot:
        if "robots" in tables:
            ids |= {r["robot_id"] for r in query("SELECT robot_id FROM robots")
                    if "robot_id" in r}
        if robot_logs is not None:
            ids |= set(robot_logs.robots())
    for rid in sorted(ids):
        base = f"robots/{rid}"
        if "robot_state" in tables:
            st = query("SELECT status, updated_at FROM robot_state WHERE robot_id=?", (rid,))
            if st:
                put(f"{base}/last_status.json", st[0])
        if robot_logs is not None:
            got = robot_logs.read(rid, since_s=since / 1000, until_s=until / 1000)
            for name, text in got.items():
                files[f"{base}/logs/{name}.log"] = redact_text(text).encode()
            if grep:
                for name, text in robot_logs.read(rid, since_s=since / 1000,
                                                  until_s=until / 1000, grep=grep).items():
                    files[f"{base}/task-{grep}/{name}.log"] = redact_text(text).encode()
        files[f"{base}/track.csv"] = _track_csv(db, rid, since, until, tables, files, base)
    # ---- clients/、API 那边另取的
    for name, data in (extra or {}).items():
        if name == "client_errors.json":
            name = "clients/client_errors.json"
        files[name] = data
    # ---- README.md
    def fmt(ms: int) -> str:
        return _dt.datetime.fromtimestamp(ms / 1000).astimezone().isoformat(timespec="seconds")
    files["README.md"] = _readme(files, since=fmt(since), until=fmt(until), scene=scene,
                                 robot=robot, task=task, by=by, now=fmt(now_ms)).encode()
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.name + ".part")
    with tarfile.open(tmp, "w:gz") as tar:
        for name, data in files.items():
            info = tarfile.TarInfo(f"nexwar_support/{name}")
            info.size, info.mtime, info.mode = len(data), now_ms // 1000, 0o600
            tar.addfile(info, io.BytesIO(data))
    tmp.replace(out)
    return out


_POS = re.compile(r"位置 \(([-\d.]+), ([-\d.]+), ([-\d.]+)\) map=(\S+) task=(\S+) 定位=(\S+)")


def _track_csv(db: Any, rid: str, since: int, until: int, tables: set[str],
               files: dict[str, bytes], base: str) -> bytes:
    """轨迹:站点在线时记的(``pose_track``,1 m 或 10 s 一个点)+ 机器人日志里每 5 秒一行的位置
    (断网那段靠它补上),按时刻排在一起。"""
    from nexwar_contract.logsetup import _line_time
    rows: list[tuple[float, str, str, str, str, str, str, str]] = []
    if "pose_track" in tables:
        for r in db.query("SELECT stamp_ms, map_id, map_version, x, y FROM pose_track "
                          "WHERE robot_id=? AND stamp_ms BETWEEN ? AND ? ORDER BY stamp_ms",
                          (rid, since, until)):
            rows.append((r["stamp_ms"] / 1000, "site", f"{r['x']:.2f}", f"{r['y']:.2f}", "",
                         f"{r['map_id']}:{r['map_version']}", "", ""))
    # 代理的日志:真机器人上叫 nexwar_agent,演示里按文件传的叫 agent / agent-B
    text = "".join(data.decode("utf-8", "replace") for name, data in files.items()
                   if name.startswith(f"{base}/logs/") and "agent" in name)
    for ln in text.splitlines():
        m = _POS.search(ln)
        if m is None:
            continue
        at = _line_time(ln)
        if at is None:
            continue
        rows.append((at, "robot", m.group(1), m.group(2), m.group(3), m.group(4), m.group(5),
                     m.group(6)))
    rows.sort(key=lambda r: r[0])
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["time_ms", "source", "x", "y", "yaw", "map", "task", "loc"])
    for r in rows:
        w.writerow([int(r[0] * 1000), *r[1:]])
    return buf.getvalue().encode()


# 日志行里的 ``code=0x0201``;记录里的 ``"err": "0x0201"``(套在别的 JSON 字符串里时引号带反斜杠)
_CODE_IN_TEXT = re.compile(r'(?:code=|\\?"err\\?": ?\\?")(0x[0-9A-F]{4})')


def _readme(files: dict[str, bytes], *, since: str, until: str, scene: str, robot: str | None,
            task: str | None, by: str, now: str) -> str:
    from collections import Counter

    from nexwar_contract import errcodes
    seen: Counter[str] = Counter()
    for name, data in files.items():
        if name.endswith((".log", ".json")):
            seen.update(_CODE_IN_TEXT.findall(data.decode("utf-8", "replace")))
    lines = ["# Nexus Warden 诊断包", "",
             f"- 时间段:{since} 到 {until}",
             f"- 场景:{scene or '按时间段'}" + (f"(机器人 {robot})" if robot else "")
             + (f"(任务 {task})" if task else ""),
             f"- 导出:{by or '-'},{now}", "",
             "不含密钥、令牌、库文件、照片录像;配置里像密码、密钥的值打了码,"
             "长串十六进制只留前 8 位。",
             "", "## 目录", "",
             "- `site/`:站点日志(`site.log`)、访问记录(`access.log`)、版本、配置、体检、指标",
             "- `robots/<编号>/`:机器人传上来的各服务日志(`logs/`)、轨迹(`track.csv`,"
             "`source=site` 是站点在线时记的,`source=robot` 是机器人日志里补的)、当时的诊断快照",
             "- `records/`:操作记录(含系统事件)、告警、日程每一轮、命令和回执、事件",
             "- `clients/`:App、网页的错误记录",
             "- `host/`:消息服务、VPN、对时等主机服务的日志", "",
             "## 这段时间出现过的错误码", ""]
    if not seen:
        lines.append("(没有)")
    else:
        lines += ["| 码 | 次数 | 英文名 | 怎么回事 | 该做什么 |", "|---|---|---|---|---|"]
        for code, n in seen.most_common():
            c = errcodes.get(code)
            name, zh, do = (c.name, c.zh, c.do_zh) if c else ("?", "不在码表里", "")
            lines.append(f"| `{code}` | {n} | `{name}` | {zh} | {do or '—'} |")
    lines += ["", "完整的码表见《错误码手册》(docs/错误码手册.md)。", ""]
    return "\n".join(lines)


#: 按任务、告警导出时前后各多取这么久(毫秒):出事之前在做什么、之后怎么收尾的。
SCENE_BEFORE_MS = 10 * 60_000
SCENE_AFTER_MS = 10 * 60_000
#: 一个包最长取多少天。
BUNDLE_MAX_DAYS = 7


def scene_window(db: Any, *, now_ms: int, since_ms: int | None = None,
                 until_ms: int | None = None, robot: str | None = None, task: str | None = None,
                 alert: str | None = None, run: int | None = None) -> dict[str, Any]:
    """导出的时间段和场景(日志设计 第 5 条):给了告警或任务,时间段按它自动取(开始前 10 分钟到
    结束后 10 分钟),机器人也按它定;手动给的时间段优先。→ ``{since_ms, until_ms, robot, task,
    scene}``。找不到那条告警 / 那个任务、时间段不对:``ValueError``。"""
    scene = "按时间段"
    if alert:
        rows = db.query("SELECT robot, first_ms, last_ms, resolved_ms, kind, title FROM alerts "
                        "WHERE key=?", (alert,))
        if not rows:
            raise ValueError(f"没有这条告警:{alert}")
        a = rows[0]
        own = str(a["robot"])
        robot = robot or (own if not own.startswith(("site", "cctv:")) else None)
        end = max(a["last_ms"] or 0, a["resolved_ms"] or 0) or a["first_ms"]
        since_ms = since_ms if since_ms is not None else a["first_ms"] - 3 * SCENE_BEFORE_MS
        until_ms = until_ms if until_ms is not None else end + SCENE_AFTER_MS
        scene = f"告警 {alert}({a['title']})"
    elif run is not None:
        rows = db.query("SELECT robot_id, mission, stamp, first_ms, last_ms FROM runs WHERE id=?",
                        (run,))
        if not rows:
            raise ValueError(f"没有这一趟巡检:{run}")
        r = rows[0]
        t0 = _stamp_ms(r["stamp"]) or r["first_ms"]
        # 断网时这一趟晚传上来,last_ms 是收齐的时刻:最多按开始后一天算
        end = min(max(r["last_ms"], t0), t0 + 86_400_000)
        robot = robot or r["robot_id"]
        since_ms = since_ms if since_ms is not None else t0 - SCENE_BEFORE_MS
        until_ms = until_ms if until_ms is not None else end + SCENE_AFTER_MS
        scene = f"巡检 {r['mission']} {r['stamp']}"
    elif task:
        rows = db.query("SELECT robot_id, MIN(issued_at) AS t0, MAX(issued_at) AS t1 "
                        "FROM commands WHERE task_id=?", (task,))
        if not rows or rows[0]["t0"] is None:
            raise ValueError(f"没有这个任务:{task}")
        r = rows[0]
        ev = db.query("SELECT MAX(received_at) AS t FROM events WHERE data LIKE ?",
                      (f'%"{task}"%',))
        end = max(r["t1"] or 0, (ev[0]["t"] if ev else 0) or 0, r["t0"])
        robot = robot or r["robot_id"]
        since_ms = since_ms if since_ms is not None else r["t0"] - SCENE_BEFORE_MS
        until_ms = until_ms if until_ms is not None else end + SCENE_AFTER_MS
        scene = f"任务 {task}"
    elif robot:
        scene = f"机器人 {robot}"
    since_ms = since_ms if since_ms is not None else now_ms - 24 * 3_600_000
    until_ms = until_ms if until_ms is not None else now_ms
    if until_ms <= since_ms:
        raise ValueError("结束时间要晚于开始时间")
    if until_ms - since_ms > BUNDLE_MAX_DAYS * 86_400_000:
        raise ValueError(f"一个包最多取 {BUNDLE_MAX_DAYS} 天,缩小时间段")
    return {"since_ms": int(since_ms), "until_ms": int(until_ms), "robot": robot, "task": task,
            "scene": scene}


def _stamp_ms(stamp: str) -> int | None:
    """一趟的编号 ``20260925T010000Z``(机器人上开始的时刻,UTC)→ 毫秒。"""
    import calendar
    try:
        return calendar.timegm(time.strptime(stamp[:16], "%Y%m%dT%H%M%SZ")) * 1000
    except ValueError:
        return None
