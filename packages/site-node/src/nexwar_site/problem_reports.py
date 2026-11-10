"""问题单(日志设计 第 6 条,用户 11-10):手机 App 上谁都能传日志,站点开一张单、给一个编号,
工程师按编号直接取整包 —— 不经过管理员转。

- **传**:``POST /api/problem-reports``,登录了的谁都能传;登录页上(登不进去的时候最需要)不登录
  也能传。请求体是 App 打好的 gzip 日志(最多 :data:`MAX_BYTES`);说明、机器人、手机型号、App
  版本放在查询参数里。同一个来源地址每小时最多 :data:`PER_HOUR` 张;整个目录最多
  :data:`MAX_TOTAL_BYTES`,超了删最旧的。
- **编号** ``NW-MMDD-XXXX``:App 上显示,用户报给工程师(电话、微信)。
- **工程师取**:``GET /api/problem-reports``(列表)、``…/<编号>/bundle``(整包)要 ``maintain``
  (管理员、临时工程师账号;工程师不在现场时走远程运维通道登录)。整包是**取的时候**现打的:
  传单前 2 小时到传单后 10 分钟的站点日志、机器人日志和轨迹、各种记录,加上 App 的日志 ——
  那几分钟里机器人还没传上来的日志,过一会儿再取就有了。
- **站点连不了外网、也没开远程通道**:登录着传的人拿到一个只管这张单的凭证,App 用它把整包下载到
  手机,用手机的分享发给工程师。不登录传的没有这个凭证(不然局域网里谁都能借开单把站点日志拿走)。
- 留 :data:`KEEP_DAYS` 天。
"""

from __future__ import annotations

import collections
import hashlib
import json
import logging
import re
import secrets
import shutil
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

KEEP_DAYS = 90
MAX_BYTES = 5 * 2**20
PER_HOUR = 10
MAX_TOTAL_BYTES = 2 * 2**30
#: 整包取传单前多久、传单后多久的(毫秒)。
BEFORE_MS = 2 * 3_600_000
AFTER_MS = 10 * 60_000
CODE = re.compile(r"^NW-\d{4}-[0-9A-F]{4}$")
_GZIP = b"\x1f\x8b"


class ReportRefused(Exception):
    def __init__(self, status: int, msg: str) -> None:
        super().__init__(msg)
        self.status = status


def _hash(tok: str) -> str:
    return hashlib.sha256(tok.encode()).hexdigest()


class ProblemReports:
    def __init__(self, root: Path, *, now_ms: Callable[[], int]) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._now = now_ms
        self._lock = threading.Lock()
        self._recent: dict[str, collections.deque[int]] = {}

    def _limit(self, remote: str, now: int) -> None:
        q = self._recent.setdefault(remote, collections.deque())
        while q and q[0] < now - 3_600_000:
            q.popleft()
        if len(q) >= PER_HOUR:
            raise ReportRefused(429, f"这台手机这一小时已经传了 {PER_HOUR} 次,过一会儿再传")
        q.append(now)
        if len(self._recent) > 5000:
            self._recent.clear()

    def submit(self, *, data: bytes, by: str, remote: str, note: str = "", robot: str = "",
               device: str = "", app: str = "", signed_in: bool) -> dict[str, Any]:
        """开一张单。→ ``{code, at_ms}``,登录着传的还有 ``token``(只管这张单的下载凭证)。"""
        if not data:
            raise ReportRefused(400, "没有日志")
        if len(data) > MAX_BYTES:
            raise ReportRefused(413, f"日志超过 {MAX_BYTES // 2**20} MB")
        if not data.startswith(_GZIP):
            raise ReportRefused(400, "日志要是 gzip 打包的")
        now = self._now()
        with self._lock:
            self._limit(remote, now)
            mmdd = time.strftime("%m%d", time.localtime(now / 1000))
            for _ in range(20):
                code = f"NW-{mmdd}-{secrets.token_hex(2).upper()}"
                d = self.root / code
                if not d.exists():
                    break
            else:  # pragma: no cover —— 一天六万五千张才会撞满
                raise ReportRefused(503, "编号用完了")
            d.mkdir()
        token = secrets.token_urlsafe(24) if signed_in else ""
        meta = {"code": code, "at_ms": now, "by": by[:64], "remote": remote[:64],
                "note": note.strip()[:500], "robot": robot[:64], "device": device[:120],
                "app": app[:40], "bytes": len(data), "signed_in": signed_in,
                "token_hash": _hash(token) if token else ""}
        (d / "app.log.gz").write_bytes(data)
        tmp = d / "meta.json.tmp"
        tmp.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
        tmp.replace(d / "meta.json")
        log.warning("收到问题单 %s by=%s robot=%s %d 字节 说明=%s", code, by, robot or "-",
                    len(data), meta["note"][:80])
        self._trim()
        out: dict[str, Any] = {"code": code, "at_ms": now}
        if token:
            out["token"] = token
        return out

    @staticmethod
    def _public(meta: dict[str, Any]) -> dict[str, Any]:
        return {k: v for k, v in meta.items() if k != "token_hash"}

    def get(self, code: str) -> dict[str, Any] | None:
        if not CODE.match(code):
            return None
        try:
            return json.loads((self.root / code / "meta.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def list(self, limit: int = 200) -> list[dict[str, Any]]:
        out = []
        for d in self.root.iterdir():
            m = self.get(d.name) if d.is_dir() else None
            if m is not None:
                out.append(self._public(m))
        out.sort(key=lambda m: m["at_ms"], reverse=True)
        return out[:limit]

    def token_ok(self, code: str, token: str) -> bool:
        m = self.get(code)
        return bool(m and m.get("token_hash") and token
                    and secrets.compare_digest(m["token_hash"], _hash(token)))

    def app_log(self, code: str) -> bytes:
        return (self.root / code / "app.log.gz").read_bytes()

    def window(self, code: str) -> tuple[int, int]:
        m = self.get(code) or {}
        at = int(m.get("at_ms") or self._now())
        return at - BEFORE_MS, min(self._now(), at + AFTER_MS)

    def _dirs(self) -> list[tuple[int, Path, int]]:
        out = []
        for d in self.root.iterdir():
            m = self.get(d.name) if d.is_dir() else None
            if m is None:
                continue
            size = sum(f.stat().st_size for f in d.iterdir() if f.is_file())
            out.append((int(m["at_ms"]), d, size))
        out.sort(key=lambda r: r[0])
        return out

    def _trim(self) -> None:
        rows = self._dirs()
        total = sum(r[2] for r in rows)
        for _at, d, size in rows[:-1]:                 # 刚传的那张不删
            if total <= MAX_TOTAL_BYTES:
                break
            shutil.rmtree(d, ignore_errors=True)
            total -= size
            log.warning("问题单超过 %d MB:删掉最旧的 %s", MAX_TOTAL_BYTES // 2**20, d.name)

    def prune(self, keep_days: int = KEEP_DAYS) -> int:
        cut = self._now() - keep_days * 86_400_000
        n = 0
        for at, d, _size in self._dirs():
            if at < cut:
                shutil.rmtree(d, ignore_errors=True)
                n += 1
        if n:
            log.info("问题单过了 %d 天:删了 %d 张", keep_days, n)
        return n
