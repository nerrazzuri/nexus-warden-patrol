"""审计(W00c3 设计决定三 A):只追加的 ``audit`` 表。记登录成功/失败/锁定、注销、每一次改动类
API 调用(谁、什么动作、对象、结果、时刻、来源地址)。派单本身在 ``commands`` 表(带 ``issued_by``),
审计这一行的 ``detail`` 里带 ``command_id`` 指过去。"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any

from nexwar_site.db import SiteDB

#: ``detail`` 落库最多这么长。**落进去的必须是一份完整的 JSON**(W20 外审:原来序列化之后硬截,25 个
#: 防区名的临时撤防一截,``list()`` 就读不回来了)。
MAX_DETAIL = 2000
_KEEP_ITEMS = 10
_KEEP_CHARS = 200
#: 用户看的操作记录留多久(用户 11-10:一年)。
KEEP_DAYS = 365
#: 请求内容存进操作记录时,名字里带这些词的字段只记「有」,不记值。
_SECRET_WORDS = ("password", "passwd", "pin", "token", "secret", "key", "otp", "code", "cookie",
                 "cert", "credential")


#: 全站活动日志的操作类别(liang-d5 第 5 轮前:「11 月 5 日晚上谁撤的防、谁派的机器人」要能筛出来)。
#: 动作是「方法 路径」,用 SQLite GLOB 认;网页上每行怎么写成人话还是网页自己的表。
AUDIT_GROUPS: dict[str, tuple[str, ...]] = {
    "dispatch": ("* /api/robots/*/goto", "* /api/robots/*/patrol", "* /api/robots/*/home/return",
                 "* /api/robots/*/standby/return", "* /api/routes/*/run"),
    "stop": ("* /api/robots/*/halt", "* /api/robots/*/abort", "* /api/robots/*/resume",
             "* /api/robots/stop-all", "* /api/robots/resume-all"),
    "arming": ("* /api/mode", "* /api/mode/*", "* /api/arming/*"),
    "alarms": ("* /api/alerts/*", "* /api/alert-test*"),
    "accounts": ("login*", "* /api/login", "* /api/logout", "* /api/accounts*", "* /api/me*"),
    "setup": ("* /api/routes*", "* /api/route-schedules*", "* /api/schedule*", "* /api/zones*",
              "* /api/nav-zones*", "* /api/maps*", "* /api/admin/maps*", "* /api/standby*",
              "* /api/cameras*", "* /api/admin/cameras*", "* /api/layout*", "* /api/guard-routes*"),
    "robots": ("* /api/admin/robots*", "* /api/admin/bind*"),
    "views": ("VIEW", "DOWNLOAD"),
    #: 日志设计 第 2 条:系统自己做的事(日程、机器人上下线、告警)
    "system": ("schedule *", "robot *", "alert *"),
}
#: 一次导出最多这么多行;再多让人缩小日期范围(不悄悄截)。
EXPORT_MAX = 20_000


def _shrink(v: Any) -> Any:
    """长列表留前几项、写总数;长字符串截短。结构不变,读的人还看得懂。"""
    if isinstance(v, dict):
        return {str(k)[:_KEEP_CHARS]: _shrink(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        head = [_shrink(x) for x in v[:_KEEP_ITEMS]]
        return head + [f"…共 {len(v)} 项"] if len(v) > _KEEP_ITEMS else head
    if isinstance(v, str) and len(v) > _KEEP_CHARS:
        return v[:_KEEP_CHARS] + "…"
    return v


def encode_detail(detail: dict[str, Any] | None) -> str:
    """→ 不超过 ``MAX_DETAIL`` 的完整 JSON:原样放得下就原样;放不下先缩;还放不下只留键名。"""
    for d in (detail or {}, _shrink(detail or {})):
        raw = json.dumps(d, ensure_ascii=False)
        if len(raw) <= MAX_DETAIL:
            return raw
    keys = [str(k)[:64] for k in (detail or {})][:20]
    return json.dumps({"truncated": True, "keys": keys}, ensure_ascii=False)


def redact(v: Any, depth: int = 0) -> Any:
    """请求内容去敏、压短(日志设计 第 1 条):密码、PIN、令牌、密钥之类只记「***」;长串截短,
    长列表只留前几个和总数。"""
    if isinstance(v, dict):
        out: dict[str, Any] = {}
        for k, x in list(v.items())[:30]:
            name = str(k)[:64]
            low = name.lower()
            out[name] = "***" if any(w in low for w in _SECRET_WORDS) else (
                redact(x, depth + 1) if depth < 3 else "…")
        return out
    if isinstance(v, list):
        head = [redact(x, depth + 1) if depth < 3 else "…" for x in v[:_KEEP_ITEMS]]
        return head if len(v) <= _KEEP_ITEMS else head + [f"…共 {len(v)} 项"]
    if isinstance(v, str):
        v = _URL_CRED.sub(r"\1***@", v)            # rtsp://用户:密码@ 这种,密码打码
        return v if len(v) <= _KEEP_CHARS else v[:_KEEP_CHARS] + "…"
    return v


_URL_CRED = re.compile(r"([a-z][a-z0-9+.-]*://[^/\s:@]*:)[^/\s@]*@", re.I)


def decode_detail(raw: str) -> dict[str, Any]:
    """读回来。以前硬截坏了的行(W20 外审之前写的)不许让整张审计读不出来:原文给一截看。"""
    try:
        d = json.loads(raw)
    except ValueError:
        return {"unreadable": True, "raw": raw[:_KEEP_CHARS]}
    return d if isinstance(d, dict) else {"value": d}


def site_event(db: SiteDB, at_ms: int, *, actor: str, action: str, target: str = "",
               detail: dict[str, Any] | None = None) -> None:
    """系统自己做的事进同一张活动日志(日志设计 第 2 条,用户 11-10:用户也看得到):
    ``actor`` 用 ``site:schedule`` / ``site:robot`` / ``site:alerts`` 这样的。写不进去只记日志。"""
    import logging
    try:
        AuditLog(db, now_ms=lambda: at_ms).record(actor=actor, action=action, target=target,
                                                  status=200, detail=detail)
    except Exception:
        logging.getLogger(__name__).exception("系统事件写不进活动日志:%s %s", action, target)


class AuditLog:
    def __init__(self, db: SiteDB, *, now_ms: Callable[[], int]) -> None:
        self.db = db
        self._now = now_ms

    def record(self, *, actor: str, action: str, target: str = "", status: int = 0,
               detail: dict[str, Any] | None = None, remote: str = "") -> None:
        with self.db.tx() as c:
            c.execute("INSERT INTO audit(at, actor, action, target, status, detail, remote) "
                      "VALUES (?,?,?,?,?,?,?)",
                      (self._now(), actor[:128], action[:128], target[:256], int(status),
                       encode_detail(detail), remote[:64]))

    def prune(self, keep_days: int = KEEP_DAYS) -> int:
        """删掉超过留存期的(用户 11-10:一年)。返回删了几条。"""
        cut = self._now() - keep_days * 86_400_000
        with self.db.tx() as c:
            return c.execute("DELETE FROM audit WHERE at < ?", (cut,)).rowcount

    def search(self, *, since_ms: int = 0, until_ms: int = 2 ** 53, actor: str | None = None,
               group: str | None = None, limit: int = 200, offset: int = 0) -> dict[str, Any]:
        """全站活动日志:一段时间里、某个人、某类操作;新的在前,能翻页,带总数。"""
        where = ["a.at >= ?", "a.at < ?"]
        args: list[Any] = [since_ms, until_ms]
        if actor:
            where.append("(a.actor = ? OR a.actor = ?)")      # 登录那一行记成 login:名字
            args += [actor, f"login:{actor}"]
        if group:
            pats = AUDIT_GROUPS[group]
            where.append("(" + " OR ".join("a.action GLOB ?" for _ in pats) + ")")
            args += pats
        w = " AND ".join(where)
        total = self.db.query(f"SELECT COUNT(*) AS n FROM audit a WHERE {w}", tuple(args))[0]["n"]
        rows = self.db.query(f"SELECT a.*, c.role AS actor_role FROM audit a LEFT JOIN accounts c "
                             f"ON c.name = a.actor WHERE {w} ORDER BY a.id DESC LIMIT ? OFFSET ?",
                             (*args, int(limit), int(offset)))
        return {"audit": [dict(r) | {"detail": decode_detail(r["detail"])} for r in rows],
                "total": total, "limit": limit, "offset": offset}

    def list(self, limit: int = 200, actor: str | None = None) -> list[dict[str, Any]]:
        """新的在前。``actor``:只看这个人做的(W44 第二期,用户页「他做过什么」)。每行带
        ``actor_role``(这个账号现在的角色;删了的账号、站点自己是 ``None``)。"""
        where, args = ("WHERE a.actor=?", (actor,)) if actor is not None else ("", ())
        rows = self.db.query(f"SELECT a.*, c.role AS actor_role FROM audit a LEFT JOIN accounts c "
                             f"ON c.name = a.actor {where} ORDER BY a.id DESC LIMIT ?",
                             (*args, int(limit)))
        return [dict(r) | {"detail": decode_detail(r["detail"])} for r in rows]
