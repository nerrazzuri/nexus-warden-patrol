"""1.1-1 第 4 步:保安经过的记录(设计 ``docs/1.1-1-认出保安-设计.md`` 判定规矩第 4 条)。

机器人拍到脸,检测节点只算特征值(第 2 步),发 ``face_seen`` 事件::

    {"faces": [{"feat": [128 个数], "dist_m": 2.4}, ...]}

站点在人脸登记(:class:`nexwar_site.faces.FaceBook`)里比对。认出来的记一笔「保安 X 经过 B 区」:

- 进 ``guard_passes`` 表(谁、哪台机器人、哪个防区、怎么认的、第一次和最后一次、几次、最高分);
- 出一条 P3 ``guard_passed``,只记一笔(``record``:当场算已解决,不响、不推送,
  两个保安各一条不合并),报警记录和值班簿里看得到。**P3 里不写是谁**(外审 1.1 #2、#3):
  报警记录、值班簿、事件报告谁都能看,写了名字就绕过了「别人只看自己的」;是谁只在
  ``guard_passes`` 里(按人过滤、到期删、撤销同意删),P3 只带那一笔的编号。
- 同一个保安、同一台机器人、同一个防区,:data:`MERGE_MS` 之内又认出来:并进上一笔,不另出 P3。

认不出的脸这里**不管**:看见人报不报 P1 还是原来的规矩(第 2 步上真机以后再按设计改)。

保安经过的记录是个人数据(PDPA):留 :data:`KEEP_MS`(90 天),到期删;谁看了进审计(在 api)。
"""

from __future__ import annotations

import logging
import math
from collections.abc import Callable
from typing import Any

from nexwar_site.db import SiteDB

log = logging.getLogger(__name__)

FEAT_LEN = 128                     # SFace 的特征值长度
MAX_FACES = 10                     # 一次事件最多几张脸
MERGE_MS = 5 * 60_000
KEEP_MS = 90 * 86_400_000
PRUNE_EVERY_MS = 3_600_000
LIST_MAX = 1000
HOWS = ("face", "phone_confirmed")
#: 能看所有人的经过记录的角色(外审 1.1 #14):管理员、经理。工程师临时账号不给(个人数据)。
SUPERVISOR_ROLES = ("admin", "owner")


class GuardPasses:
    def __init__(self, db: SiteDB, *, now_ms: Callable[[], int], faces: Any = None,
                 desk: Any = None, zone_of: Callable[[str], str | None] | None = None) -> None:
        self.db = db
        self._now = now_ms
        self.faces = faces
        self.desk = desk
        self.zone_of = zone_of
        self._pruned = 0

    def attach(self, dispatcher: Any) -> None:
        dispatcher.on_event(self.on_event)

    # ------------------------------------------------------------------ 收

    def on_event(self, rid: str, e: Any) -> None:
        if getattr(e, "kind", None) != "face_seen" or not isinstance(e.data, dict):
            return
        try:
            self.faces_seen(rid, e.data.get("faces"))
        except Exception:                         # 认人出毛病不许带走事件分发
            log.exception("%s 的人脸事件处理炸了", rid)

    def faces_seen(self, rid: str, faces: Any) -> list[str]:
        """一次事件里的几张脸 → 认出来的保安账号(按认出的先后,去重)。"""
        if self.faces is None or not isinstance(faces, list):
            return []
        got: list[str] = []
        for f in faces[:MAX_FACES]:
            feat = f.get("feat") if isinstance(f, dict) else None
            if not _feat_ok(feat):
                continue
            m = self.faces.match([float(x) for x in feat])
            if m is None:
                continue
            acc, score = m
            dist = f.get("dist_m")
            dist = float(dist) if isinstance(dist, (int, float)) and not isinstance(dist, bool) \
                and math.isfinite(dist) else None
            if acc not in got:
                got.append(acc)
                self.seen(rid, acc, how="face", score=score, dist_m=dist)
        return got

    def seen(self, rid: str, account: str, *, how: str, score: float | None = None,
             dist_m: float | None = None) -> int:
        """记一笔(并进 :data:`MERGE_MS` 之内的上一笔)。回那一笔的 id。"""
        if how not in HOWS:
            raise ValueError(f"how 只认 {HOWS}")
        now = self._now()
        zone = ""
        if self.zone_of is not None:
            try:
                zone = self.zone_of(rid) or ""
            except Exception:                     # 防区算不出来照样记
                log.exception("%s 在哪个防区算不出来", rid)
        sc = round(float(score), 3) if score is not None else None
        with self.db.tx() as c:
            row = c.execute(
                "SELECT id, score FROM guard_passes WHERE account=? AND robot=? AND zone=? "
                "AND last_ms>=? ORDER BY last_ms DESC LIMIT 1",
                (account, rid, zone, now - MERGE_MS)).fetchone()
            if row is not None:
                best = max(x for x in (row["score"], sc) if x is not None) \
                    if (row["score"] is not None or sc is not None) else None
                c.execute("UPDATE guard_passes SET last_ms=?, n=n+1, score=? WHERE id=?",
                          (now, best, row["id"]))
                pid, new = int(row["id"]), False
            else:
                pid = int(c.execute(
                    "INSERT INTO guard_passes(account, robot, zone, how, first_ms, last_ms, n, "
                    "score, dist_m) VALUES (?,?,?,?,?,?,1,?,?)",
                    (account, rid, zone, how, now, now, sc,
                     round(dist_m, 1) if dist_m is not None else None)).lastrowid)
                new = True
        if new and self.desk is not None:
            where = f"经过 {zone}" if zone else "经过"
            by = "人脸认出" if how == "face" else "手机靠近、本人确认"
            self.desk.raise_alert(
                kind="guard_passed", robot=rid, title=f"登记过的保安{where}",
                detail=f"{by}" + (f",约 {dist_m:.1f} m" if dist_m is not None else "")
                       + f";不报警。是谁看「保安经过」第 {pid} 笔",
                context={"how": how, "pass_id": pid, **({"zone": zone} if zone else {})},
                record="site:guard_passed")      # 只记一笔:当场算已解决,不推送、不合并
        self.prune()
        return pid

    # ------------------------------------------------------------------ 看

    def list(self, *, since: int, until: int, account: str | None = None) -> dict[str, Any]:
        self.prune()
        # 外审 1.1 #4:到期的读的时候也不给(清理没赶上也不露)
        q = "SELECT * FROM guard_passes WHERE last_ms>=? AND first_ms<? AND last_ms>=?"
        args: list[Any] = [since, until, self._now() - KEEP_MS]
        if account:
            q += " AND account=?"
            args.append(account)
        rows = self.db.query(q + " ORDER BY first_ms DESC LIMIT ?", (*args, LIST_MAX + 1))
        out = [{"id": r["id"], "account": r["account"], "robot": r["robot"], "zone": r["zone"],
                "how": r["how"], "first_ms": r["first_ms"], "last_ms": r["last_ms"], "n": r["n"],
                "score": r["score"], "dist_m": r["dist_m"]} for r in rows[:LIST_MAX]]
        return {"passes": out, "truncated": len(rows) > LIST_MAX,
                "keep_days": KEEP_MS // 86_400_000}

    def forget(self, account: str) -> int:
        """撤销人脸同意时一起删这个人的经过记录。"""
        with self.db.tx() as c:
            return c.execute("DELETE FROM guard_passes WHERE account=?", (account,)).rowcount

    def tick(self) -> None:
        """站点后台每拍调(外审 1.1 #4):到期删不靠下一次认出人。"""
        self.prune()

    def prune(self) -> int:
        now = self._now()
        if self._pruned and now - self._pruned < PRUNE_EVERY_MS:
            return 0
        self._pruned = now
        with self.db.tx() as c:
            return c.execute("DELETE FROM guard_passes WHERE last_ms<?",
                             (now - KEEP_MS,)).rowcount


def _feat_ok(feat: Any) -> bool:
    return isinstance(feat, list) and len(feat) == FEAT_LEN and all(
        isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)
        for x in feat)
