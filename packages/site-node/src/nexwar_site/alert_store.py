"""站点的告警台(W00c5a):``AlertBook`` 接上站点库与 SSE。

每一次变化(新起、吸收、确认、解决、升级)都**写穿**到 ``alerts`` 表,再推一帧
``{"kind": "alert", "alert": …}`` 给 SSE。站点重启时从库里读回(``AlertBook.restore``):
未解决的告警还在、升到第几档还在、序号接着走。

确认人由调用方(API 层)从**登录账号**取,不信请求体(W00c3 的规矩)。
"""

from __future__ import annotations

import json
import logging
import threading
from collections.abc import Callable
from typing import Any

from nexwar_contract import errcodes
from nexwar_site.alerts import Alert, AlertBook, AlertNotFound, Channel, Level
from nexwar_site.db import SiteDB

log = logging.getLogger(__name__)

#: 告警测试模式(POC):最长多少分钟;标题前缀。
TEST_MAX_MIN = 120
TEST_PREFIX = "测试："
#: 第 4 轮 duty r3-N10:演练只练「人能故意触发的」—— 在摄像头前走过、到机器人跟前、
#: 推倒 / 抱起 / 罩住它、按急停。原来反过来列「不算演练的」,机器人自己的毛病(出发前检查不过、
#: 连续到不了点)和派单记录也被标成「测试：」、结束时一起删了。没列在这里的一律是真报警。
DRILL_KINDS = frozenset({
    "intrusion", "intrusion_unanswered", "intrusion_person", "dog_sees_person", "person_left",
    "person_overdue", "authorized_person", "force_lifted", "force_covered", "force_flipped",
    "fallen", "estop_pressed", "deter_cornered", "lens_blocked",
    "payload_siren", "payload_strobe", "payload_spotlight",
})


def drillable(robot: str, kind: str) -> bool:
    """演练期间这条报警算不算演练的(打「测试：」、能一键删)。
    ``robot`` 不看:入侵没机器人去也记在站点名下。"""
    del robot
    return kind in DRILL_KINDS


#: 开张时内存里读回多少条最近的(已解决的也算);未解决的全读回。
RESTORE_RECENT = 200

_COLS = ("key", "level", "kind", "robot", "title", "detail", "first_ms", "last_ms", "count",
         "acked_by", "acked_ms", "resolved_by", "resolved_ms", "escalated", "context",
         "shelved_by", "shelved_ms", "shelved_until_ms", "shelved_reason", "verdict")


def _from_row(r: Any) -> Alert:
    return Alert(key=r["key"], level=Level(r["level"]), kind=r["kind"], robot=r["robot"],
                 title=r["title"], detail=r["detail"], first_ms=r["first_ms"],
                 last_ms=r["last_ms"], count=r["count"], acked_by=r["acked_by"],
                 acked_ms=r["acked_ms"], resolved_by=r["resolved_by"],
                 resolved_ms=r["resolved_ms"], escalated=r["escalated"],
                 context=_context(r["context"]), shelved_by=r["shelved_by"],
                 shelved_ms=r["shelved_ms"], shelved_until_ms=r["shelved_until_ms"],
                 shelved_reason=r["shelved_reason"], verdict=r["verdict"])


def _context(raw: Any) -> dict[str, Any]:
    try:
        got = json.loads(raw or "{}")
    except ValueError:
        return {}
    return got if isinstance(got, dict) else {}


#: 这几种告警要保安点过「已到场」才能关(W74:看见人以后人跑了,远程看一眼就关等于没人去)。
ARRIVAL_KINDS: frozenset[str] = frozenset({"dog_sees_person"})


class ArrivalNeeded(ValueError):
    """这条要保安先到场(点「已到场」)才能关。"""


class AlertDesk:
    def __init__(self, db: SiteDB, *, now_ms: Callable[[], int],
                 publish: Callable[[dict[str, Any]], None] | None = None) -> None:
        self.db = db
        self._now = now_ms
        self._publish = publish
        #: 一台狗的现场(W17):告警源接上(狗最后在哪、在跑哪一趟)。调用方给的 ``context`` 盖在上面。
        self.context_for: Callable[[str], dict[str, Any]] | None = None
        #: 商业化 A6:P1 推到手机(站点主程序配了推送才打开)。
        self.push = False
        self.book = AlertBook(sink=self._write)
        #: 外审 2 #2:正在进行的「一组一起提交」的事务;None = 每笔自己一个事务
        self._tx: Any = None
        self._deferred: list[dict[str, Any]] = []
        # 只读回未解决的与最近 RESTORE_RECENT 条:整张历史表读进内存会一直涨,升级每 5 s 还要遍历。
        # 序号从整张表的键里算(只读键),读回的只是一部分也不撞号。
        max_seq: dict[str, int] = {}
        for (key,) in db.query("SELECT key FROM alerts"):
            group, _, seq = key.rpartition("#")
            if seq.isdigit():
                max_seq[group] = max(max_seq.get(group, 0), int(seq))
        # 外审 r1 #8:清掉的测试告警的号不许再用(推送队列按告警号去重,重用了真告警推不出去)
        from nexwar_site.site_settings import SiteSettings
        floor = SiteSettings(db).get("alert_seq_floor")
        for group, seq in (floor.items() if isinstance(floor, dict) else ()):
            if isinstance(seq, int) and not isinstance(seq, bool):
                max_seq[group] = max(max_seq.get(group, 0), seq)
        rows = db.query("SELECT * FROM alerts WHERE resolved_ms IS NULL UNION "
                        "SELECT * FROM (SELECT * FROM alerts ORDER BY last_ms DESC LIMIT ?)",
                        (RESTORE_RECENT,))
        self.book.restore((_from_row(r) for r in rows), max_seq=max_seq)

    # ------------------------------------------------------------ 写穿

    def _write(self, a: Alert) -> None:
        w = a.to_wire()
        vals = tuple(json.dumps(w[c], ensure_ascii=False) if c == "context" else w[c]
                     for c in _COLS)
        if self._tx is not None:
            # 外审 2 #2:一组相关的改动(请求支援 = 起一条 + 原告警记一笔)写进同一个事务,
            # 发布攒到提交后
            self._write_in(self._tx, a, vals)
            self._deferred.append(w)
            return
        with self.db.tx() as c:
            self._write_in(c, a, vals)
        if self._publish is not None:
            try:
                self._publish({"kind": "alert", "alert": w})
            except Exception:
                log.exception("告警推不出去(%s),库里已经记下", a.key)

    def _write_in(self, c: Any, a: Alert, vals: tuple[Any, ...]) -> None:
        c.execute(f"INSERT INTO alerts({', '.join(_COLS)}) VALUES "
                  f"({', '.join('?' * len(_COLS))}) ON CONFLICT(key) DO UPDATE SET "
                  + ", ".join(f"{k}=excluded.{k}" for k in _COLS[1:]), vals)
        if self.push:
            # 商业化 A6:没确认的 P1 新起、升档,跟告警同一个事务排进推送队列(记下了就一定会推)
            from nexwar_site.push import enqueue
            enqueue(c, a, self._now())

    def backup(self, key: str, *, who: str) -> Alert:
        """redesign 第 8 期 / 外审 2 #2 / 外审 3 #1:保安请求支援 —— 起一条 ``backup_requested``
        (推经理、管理员)、原告警记下谁几点叫的人,**两笔写进同一个事务**;事务没提交成功就把告警簿的
        内存也退回去(不然重试时内存里「已经叫过人」,数据库里却没有)。叫过的直接回原告警;关了的、
        没有的抛 ``AlertNotFound`` / ``ValueError``。"""
        orig = self.book.get(key)
        if orig is None:
            raise AlertNotFound(key)
        if orig.resolved_ms is not None:
            raise ValueError("这条告警已经关闭,不用再叫人")
        if orig.context.get("backup_by"):
            return orig
        now = self._now()
        ctx: dict[str, Any] = {}
        if self.context_for is not None:
            try:
                ctx.update(self.context_for(orig.robot) or {})
            except Exception:
                log.exception("%s 的现场拿不到", orig.robot)
        ctx.update({"for": key, "by": who})
        code = errcodes.for_alert("backup_requested")
        if code is not None:
            ctx.setdefault("err", code.hex)
        snap = self.book.snapshot()
        self._deferred = []
        try:
            with self.db.tx() as c:
                self._tx = c
                try:
                    new = self.book.raise_alert(kind="backup_requested", robot=orig.robot,
                                                title=f"请求支援：{orig.title}",
                                                detail=f"{who} 正在处理，请求支援", now_ms=now,
                                                context=ctx, merge=False)
                    a = self.book.amend(key, now_ms=now,
                                        context={"backup_by": who, "backup_ms": now})
                finally:
                    self._tx = None
        except Exception:
            self.book.restore_snapshot(snap)        # 外审 3 #1:库没写成,内存也退回去
            self._deferred = []
            raise
        pending, self._deferred = self._deferred, []
        if self._publish is not None:
            for w in pending:
                try:
                    self._publish({"kind": "alert", "alert": w})
                except Exception:
                    log.exception("告警推不出去(%s),库里已经记下", w.get("key"))
        self._event("alert raised", new)
        return a

    # ------------------------------------------------------------ 操作

    # ------------------------------------------------------------ POC:告警测试模式

    def test_mode(self) -> dict[str, Any] | None:
        """开着的告警测试模式 ``{"until_ms", "by"}``;没开、到点了(自动结束,不删)是 None。"""
        from nexwar_site.site_settings import SiteSettings
        got = SiteSettings(self.db).get("alert_test")
        if not isinstance(got, dict) or not isinstance(got.get("until_ms"), int):
            return None
        return got if self._now() < got["until_ms"] else None

    def start_test(self, minutes: Any, *, by: str) -> dict[str, Any]:
        from nexwar_site.site_settings import SiteSettings
        if isinstance(minutes, bool) or not isinstance(minutes, int) \
                or not 1 <= minutes <= TEST_MAX_MIN:
            raise ValueError(f"测试时长要是 1–{TEST_MAX_MIN} 分钟")
        mode = {"until_ms": self._now() + minutes * 60_000, "by": by}
        SiteSettings(self.db).put("alert_test", mode)
        return mode

    def test_alarms(self) -> list[dict[str, Any]]:
        """带测试标记、还在库里的报警(结束演练删之前给人看删哪些)。"""
        rows = self.db.query("SELECT key, kind, robot, title, first_ms FROM alerts "
                             "WHERE json_extract(context, '$.test') = 1 "
                             "ORDER BY rowid DESC LIMIT 200")
        # 第 4 轮 duty N2:带上种类、哪台,网页按种类说人话(原来只有站点中文原文)
        return [{"key": r["key"], "kind": r["kind"], "robot": r["robot"], "title": r["title"],
                 "first_ms": r["first_ms"]} for r in rows]

    def end_test(self, *, clear: bool, keep: frozenset[str] = frozenset()) -> int:
        """结束测试;``clear`` 就删掉所有带测试标记的告警(没标记的不动;``keep`` 里的留着,
        第 4 轮 duty r3-N10:删之前能逐条取消勾选)。回删了几条。"""
        from nexwar_site.site_settings import SiteSettings
        SiteSettings(self.db).put("alert_test", None)
        if not clear:
            return 0
        rows = self.db.query("SELECT key FROM alerts WHERE json_extract(context, '$.test') = 1")
        keys = {r["key"] for r in rows} - keep
        if keys:
            st = SiteSettings(self.db)
            floor = st.get("alert_seq_floor")
            floor = dict(floor) if isinstance(floor, dict) else {}
            for k in keys:
                group, _, seq = k.rpartition("#")
                if seq.isdigit():
                    floor[group] = max(int(floor.get(group, 0) or 0), int(seq))
            st.put("alert_seq_floor", floor)
            with self.db.tx() as c:
                c.executemany("DELETE FROM alerts WHERE key=?", [(k,) for k in keys])
            self.book.forget(keys)
            if self._publish is not None:
                try:
                    self._publish({"kind": "alerts_cleared", "keys": sorted(keys)})
                except Exception:
                    log.exception("清掉测试告警推不出去")
        return len(keys)

    def raise_alert(self, *, kind: str, robot: str, title: str, detail: str = "",
                    context: dict[str, Any] | None = None, merge: bool = True,
                    record: str = "") -> Alert:
        if self.test_mode() is not None and drillable(robot, kind):
            # POC 告警测试模式:打标记、标题前加「测试」;不合进真告警(清掉时别把真的一起删了)
            cur = self.book.absorbing(robot, kind, now_ms=self._now())
            if cur is not None and not cur.context.get("test"):
                merge = False
            context = {**(context or {}), "test": True}
            if not title.startswith(TEST_PREFIX):
                title = TEST_PREFIX + title
        else:
            # 外审 r1 #7:反过来也一样 —— 测试结束后的真告警不合进还在吸收的测试告警
            cur = self.book.absorbing(robot, kind, now_ms=self._now())
            if cur is not None and cur.context.get("test"):
                merge = False
        ctx: dict[str, Any] = {}
        if self.context_for is not None:
            try:
                ctx.update(self.context_for(robot) or {})
            except Exception:                        # 现场拿不到不许挡住告警
                log.exception("%s 的现场拿不到", robot)
        ctx.update(context or {})
        code = errcodes.for_alert(kind)
        if code is not None:
            ctx.setdefault("err", code.hex)          # 日志设计 第 7 条:告警带错误码
        a = self.book.raise_alert(kind=kind, robot=robot, title=title, detail=detail,
                                  now_ms=self._now(), context=ctx, merge=merge, record=record)
        if a.count == 1:                    # 新起的一条(合进旧的只是计数加一,不再记)
            log.warning("告警 %s %s code=%s robot=%s key=%s:%s %s", "记一笔" if record else "产生",
                        a.level.value if hasattr(a.level, "value") else a.level,
                        errcodes.tag(errcodes.ALERT.get(kind, kind)), robot, a.key, title,
                        detail[:200])
            self._event("alert recorded" if record else "alert raised", a)
        return a

    def _event(self, action: str, a: Alert, **extra: Any) -> None:
        from nexwar_site.audit import site_event
        lvl = a.level.value if hasattr(a.level, "value") else str(a.level)
        site_event(self.db, self._now(), actor="site:alerts", action=action, target=a.key,
                   detail={"robot": a.robot, "kind": a.kind, "level": lvl,
                           "title": a.title[:120]} | errcodes.wire(errcodes.ALERT.get(a.kind))
                   | extra)

    def absorbing(self, robot: str, kind: str) -> Alert | None:
        return self.book.absorbing(robot, kind, now_ms=self._now())

    def ack(self, key: str, *, who: str) -> Alert:
        return self.book.ack(key, who=who, now_ms=self._now())

    def resolve(self, key: str, *, who: str, verdict: str = "", note: str = "") -> Alert:
        a = self.book.get(key)
        if a is not None and a.kind in ARRIVAL_KINDS and a.resolved_ms is None \
                and a.context.get("arrived_ms") is None:
            raise ArrivalNeeded("要保安先到场:到了现场点「已到场」,再处置完成或标误报")
        done = self.book.resolve(key, who=who, verdict=verdict, now_ms=self._now(), note=note)
        self._close_backups({key})
        return done

    def _close_backups(self, keys: set[str]) -> int:
        """用户 11-27:原告警关了,为它起的「请求支援」(P3)跟着关 —— 以前一直挂着。回关了几条。"""
        n = 0
        for b in self.book.open():
            if b.kind == "backup_requested" and b.context.get("for") in keys:
                try:
                    self.book.resolve(b.key, who="site:incident_closed", now_ms=self._now())
                except Exception:
                    log.exception("请求支援 %s 跟着原告警关没关成", b.key)
                    continue
                self._event("alert auto-resolved", b, by="site:incident_closed")
                n += 1
        return n

    def sweep_backups(self) -> int:
        """站点起来时对一遍:原告警已经关了(或者没了)的「请求支援」关掉(用户 11-27)。"""
        live = {a.key for a in self.book.open()}
        gone = {str(b.context.get("for")) for b in self.book.open()
                if b.kind == "backup_requested" and b.context.get("for") not in live}
        return self._close_backups(gone) if gone else 0

    def reopen(self, key: str) -> Alert:
        """撤销处置(点错了,``alerts.REOPEN_MS`` 内)。"""
        return self.book.reopen(key, now_ms=self._now())

    def arrive(self, key: str, *, who: str) -> Alert:
        return self.book.arrive(key, who=who, now_ms=self._now())

    def amend_open(self, robot: str, kind: str, *, title: str | None = None,
                   detail: str | None = None,
                   context: dict[str, Any] | None = None) -> Alert | None:
        """这一位这一种还开着的那条(最新的)改标题 / 内容、合进现场;没有开着的回 ``None``。"""
        cur = [a for a in self.book.open() if a.robot == robot and a.kind == kind]
        if not cur:
            return None
        a = max(cur, key=lambda x: x.first_ms)
        return self.book.amend(a.key, now_ms=self._now(), title=title, detail=detail,
                               context=context)

    def amend(self, key: str, *, title: str | None = None, detail: str | None = None,
              context: dict[str, Any] | None = None) -> Alert | None:
        """按 key 改那一条(还开着才改;关了、没有回 ``None``)。值守记跟人的账用:不会记到同一位
        后来开的另一条上(外审 W74 r2 #5)。"""
        a = self.book.get(key)
        if a is None or a.resolved_ms is not None:
            return None
        return self.book.amend(key, now_ms=self._now(), title=title, detail=detail,
                               context=context)

    def open_of(self, robot: str, kind: str) -> Alert | None:
        """这一位这一种还开着的那条(最新的);没有 ``None``。"""
        cur = [a for a in self.book.open() if a.robot == robot and a.kind == kind]
        return max(cur, key=lambda x: x.first_ms) if cur else None

    def shelve(self, key: str, *, who: str, until_ms: int, reason: str) -> Alert:
        return self.book.shelve(key, who=who, until_ms=until_ms, reason=reason, now_ms=self._now())

    def unshelve(self, key: str) -> Alert:
        return self.book.unshelve(key, now_ms=self._now())

    def resolve_all(self, robot: str, kind: str, *, who: str,
                    only: Callable[[Alert], bool] | None = None) -> int:
        """这一位(狗、站点、``cctv:<名字>``)这一种还没解决的告警全解决(W19:摄像头恢复、删了)。回几条。
        ``only``:只关它说是的(用户 11-27:RTK 那种里「基站挪了」不随定位好了关)。"""
        n = 0
        for a in self.book.open():
            if a.robot == robot and a.kind == kind and (only is None or only(a)):
                self.book.resolve(a.key, who=who, now_ms=self._now())
                log.info("告警 %s 自动解除 code=%s robot=%s by=%s", a.key,
                         errcodes.tag(errcodes.ALERT.get(kind, kind)), robot, who)
                self._event("alert auto-resolved", a, by=who)
                n += 1
                self._close_backups({a.key})
        return n

    def resolve_except(self, kind: str, prefix: str, keep: set[str], *, who: str) -> int:
        """这一种、记在 ``<prefix><名字>`` 名下、名字不在 ``keep`` 里的没解决的全解决(W19 复查:
        站点停机期间删掉的摄像头,它的「连不上」不能一直挂着)。回几条。"""
        n = 0
        for a in self.book.open():
            if a.kind == kind and a.robot.startswith(prefix) and a.robot[len(prefix):] not in keep:
                self.book.resolve(a.key, who=who, now_ms=self._now())
                n += 1
        return n

    def has_open(self, robot: str, kind: str) -> bool:
        """这一位这一种有没有还没解决的(持久化的告警簿说了算,不看谁的内存)。"""
        return any(a.robot == robot and a.kind == kind for a in self.book.open())

    def escalate(self) -> list[tuple[Alert, Channel]]:
        """P1 未确认的,到时限就升一档(换通道)。站点主循环每 5 s 调一次。顺带对一遍「请求支援」
        (原告警别的路子关的、站点重启前关的,跟着关;用户 11-27)。"""
        try:
            self.sweep_backups()
        except Exception:
            log.exception("请求支援对账没成")
        out = list(self.book.due_escalations(now_ms=self._now()))
        for a, ch in out:
            log.warning("告警 %s 没人确认,升级到 %s code=%s robot=%s", a.key, ch,
                        errcodes.tag(errcodes.ALERT.get(a.kind, a.kind)), a.robot)
            self._event("alert escalated", a, channel=str(getattr(ch, "value", ch)))
        return out

    # ------------------------------------------------------------ 读

    def open(self) -> list[dict[str, Any]]:
        """未解决的,P1 在最上面。"""
        return [a.to_wire() for a in self.book.open()]

    def trim(self) -> int:
        """内存里多余的已解决告警放掉(库里一条不少)。站点主循环每拍调。"""
        return self.book.trim()

    def recent(self, limit: int = 200) -> list[dict[str, Any]]:
        """最近的(含已解决),按最后一次触发倒序。从库里读:内存里的已解决的会被修剪。"""
        rows = self.db.query("SELECT * FROM alerts ORDER BY last_ms DESC, key LIMIT ?",
                             (limit,))
        return [_from_row(r).to_wire() for r in rows]

    def history(self, *, since_ms: int, until_ms: int, kinds: list[str] | None = None,
                robot: str | None = None, level: str | None = None, limit: int = 200,
                offset: int = 0) -> dict[str, Any]:
        """某一段时间里出过的报警(这段时间里触发过、或还开着跨进来的),按第一次触发倒序;能翻页。
        原来报警记录只拿最近 500 条在网页里按日期筛:站点跑几周以后,一个月前的那天就是空的。"""
        where = ["last_ms >= ?", "first_ms < ?"]
        args: list[Any] = [since_ms, until_ms]
        if kinds:
            where.append(f"kind IN ({','.join('?' * len(kinds))})")
            args += kinds
        if robot:
            where.append("robot = ?")
            args.append(robot)
        if level:
            where.append("level = ?")
            args.append(level)
        w = " AND ".join(where)
        total = self.db.query(f"SELECT COUNT(*) AS n FROM alerts WHERE {w}", tuple(args))[0]["n"]
        rows = self.db.query(f"SELECT * FROM alerts WHERE {w} ORDER BY first_ms DESC, key "
                             "LIMIT ? OFFSET ?", (*args, limit, offset))
        return {"alerts": [_from_row(r).to_wire() for r in rows], "total": total,
                "limit": limit, "offset": offset}

    def open_counts(self) -> dict[str, dict[str, int]]:
        """每台狗(以及 ``site``)未解决的告警按级别计数。"""
        out: dict[str, dict[str, int]] = {}
        for a in self.book.open():
            per = out.setdefault(a.robot, {"P1": 0, "P2": 0, "P3": 0})
            per[a.level.value] += 1
        return out


class LoopAlerts:
    """别的线程(判读、备份、接收口)报告警用的:**跳到事件循环里去报**。告警簿只许在事件循环里改
    (W00c5d 内部评审:别的线程直接改,循环里正在遍历的那一边会炸「字典在遍历时变了」,同一组两条
    还可能撞同一个键丢一条)。"""

    def __init__(self, desk: AlertDesk, loop) -> None:
        self.desk = desk
        self.loop = loop

    def _on_loop(self, fn: Any, *args: Any, **kw: Any) -> Any:
        """在事件循环里跑完、回结果;出错照样抛给调用方(调用方据此决定下一拍重试)。"""
        t = getattr(self.loop, "_thread", None)
        if t is not None and t is threading.current_thread():
            return fn(*args, **kw)                 # 已经在事件循环里:直接调(等自己会死锁)

        async def go() -> Any:
            return fn(*args, **kw)
        return self.loop.call(go, timeout_s=10.0)

    def raise_alert(self, **kw: Any) -> Any:
        return self._on_loop(self.desk.raise_alert, **kw)

    def resolve_all(self, robot: str, kind: str, *, who: str,
                    only: Callable[[Alert], bool] | None = None) -> int:
        return self._on_loop(self.desk.resolve_all, robot, kind, who=who, only=only)

    def resolve_except(self, kind: str, prefix: str, keep: set[str], *, who: str) -> int:
        return self._on_loop(self.desk.resolve_except, kind, prefix, keep, who=who)

    def has_open(self, robot: str, kind: str) -> bool:
        return self._on_loop(self.desk.has_open, robot, kind)
