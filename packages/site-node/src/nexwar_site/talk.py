"""1.1-4 远程喊话(按住说话)+ 听回话(设计 ``docs/1.1-4-远程喊话-设计.md``)。

- **按住说话**:保安在 App / 网页上按住说话、松开 → 录音(App 是 m4a / AAC,网页是 webm / ogg Opus)
  整个文件 ``POST /api/robots/<id>/talk`` 传上来,存在 ``<home>/talk/``;站点给那台机器人发喇叭命令
  ``clip = talk:<编号>``(人手动的优先级),机器人从狗专用口 ``GET /talk/<编号>`` 拉下来放。
- **听回话**:``POST /api/robots/<id>/listen`` → 站点先记一条「等回话」,给机器人发 ``mic``
  命令;机器人录几秒、``POST /talk/<编号>`` 传回来;App / 网页在「对讲记录」里点开听。
  机器人没报 ``mic`` 就没有这个按钮。
- **留多久**:录音是个人数据(声音),只留 :data:`KEEP_MS`(一天),到点连文件带记录一起删。谁说的、
  谁听的进审计(接口那头记)。
- 一段最多 :data:`MAX_SECONDS` 秒、:data:`MAX_BYTES` 字节。
"""

from __future__ import annotations

import logging
import secrets
from collections.abc import Callable
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

MAX_BYTES = 1024 * 1024
MAX_SECONDS = 30
LISTEN_SECONDS = 10
#: 外审 1.1 #11:等回话最多等这么久(录 ≤ 20 s + 传),过了算没录到
REPLY_TIMEOUT_MS = 90_000
KEEP_MS = 24 * 3600_000
#: 收的录音格式 → 存盘的后缀。
MIMES = {"audio/mp4": "m4a", "audio/m4a": "m4a", "audio/x-m4a": "m4a", "audio/aac": "aac",
         "audio/webm": "webm", "audio/ogg": "ogg", "audio/wav": "wav", "audio/x-wav": "wav",
         "audio/mpeg": "mp3"}
SERVE_MIME = {v: k for k, v in reversed(list(MIMES.items()))}


class TalkError(ValueError):
    """录音不收(接口回 400)。"""


class TalkDesk:
    def __init__(self, db: Any, root: Path, *, now_ms: Callable[[], int]) -> None:
        self.db = db
        self.root = Path(root)
        self._now = now_ms
        self._stuck: set[str] = set()

    def _file(self, tid: str, ext: str) -> Path:
        return self.root / f"{tid}.{ext}"

    def save_out(self, robot: str, account: str, data: bytes, mime: str) -> dict[str, Any]:
        """保安说的一段 → 记下、存盘,回这一条。"""
        mime = (mime or "").split(";", 1)[0].strip().lower()
        ext = MIMES.get(mime)
        if ext is None:
            raise TalkError("录音格式不认(要 m4a / aac / webm / ogg / wav / mp3)")
        if not data:
            raise TalkError("没有录到声音")
        if len(data) > MAX_BYTES:
            raise TalkError(f"录音太长(最多 {MAX_SECONDS} 秒)")
        tid = secrets.token_hex(8)
        self.root.mkdir(parents=True, exist_ok=True)
        self._file(tid, ext).write_bytes(data)
        now = self._now()
        with self.db.tx() as c:
            c.execute("INSERT INTO talk_clips(id, robot, direction, account, ext, bytes, "
                      "created_ms, state) VALUES (?,?,?,?,?,?,?,?)",
                      (tid, robot, "out", account, ext, len(data), now, "saved"))
        return self.get(tid)

    def want_reply(self, robot: str, account: str) -> dict[str, Any]:
        """听回话:先记一条「等回话」,机器人录完按这个编号传回来。"""
        tid = secrets.token_hex(8)
        with self.db.tx() as c:
            c.execute("INSERT INTO talk_clips(id, robot, direction, account, ext, bytes, "
                      "created_ms, state) VALUES (?,?,?,?,?,?,?,?)",
                      (tid, robot, "in", account, "wav", 0, self._now(), "waiting"))
        return self.get(tid)

    def mark(self, tid: str, state: str, error: str = "") -> None:
        with self.db.tx() as c:
            c.execute("UPDATE talk_clips SET state=?, error=? WHERE id=?",
                      (state, error[:200], tid))

    def on_event(self, robot: str, e: Any) -> None:
        """机器人报听回话没成(``deter`` mic ``ended: failed``):那条标「没录到」。"""
        d = getattr(e, "data", None)
        if getattr(e, "kind", None) != "deter" or not isinstance(d, dict) \
                or d.get("output") != "mic" or d.get("ended") != "failed":
            return
        clip = str(d.get("clip") or "")
        if not clip.startswith("talk:"):
            return
        with self.db.tx() as c:
            c.execute("UPDATE talk_clips SET state='failed', error=? WHERE id=? AND robot=? "
                      "AND direction='in' AND state='waiting'",
                      (str(d.get("reason") or "机器人没录成")[:200], clip[5:], robot))

    def expire(self) -> int:
        """等回话等过了 :data:`REPLY_TIMEOUT_MS`:标「没录到」(机器人掉线、事件丢了也不会一直等)。"""
        with self.db.tx() as c:
            return c.execute("UPDATE talk_clips SET state='failed', error='超时,机器人没传回来' "
                             "WHERE direction='in' AND state='waiting' AND created_ms<?",
                             (self._now() - REPLY_TIMEOUT_MS,)).rowcount

    def get(self, tid: str) -> dict[str, Any]:
        rows = self.db.query("SELECT * FROM talk_clips WHERE id=?", (tid,))
        if not rows:
            raise KeyError(tid)
        return dict(rows[0])

    def list(self, robot: str, limit: int = 20) -> list[dict[str, Any]]:
        self.expire()
        return [dict(r) for r in self.db.query(
            "SELECT * FROM talk_clips WHERE robot=? ORDER BY created_ms DESC LIMIT ?",
            (robot, limit))]

    # ------------------------------------------------------------ 狗专用口

    def for_robot(self, robot: str, tid: str) -> Path | None:
        """机器人来拉:是发给它的、还在。"""
        rows = self.db.query("SELECT * FROM talk_clips WHERE id=? AND robot=? AND direction='out'",
                             (tid, robot))
        if not rows:
            return None
        p = self._file(tid, rows[0]["ext"])
        if not p.is_file():
            return None
        with self.db.tx() as c:
            c.execute("UPDATE talk_clips SET state='fetched' WHERE id=? AND state='saved'", (tid,))
        return p

    def save_reply(self, robot: str, tid: str, data: bytes) -> bool:
        """机器人传回话:是它的那条「等回话」才收。"""
        rows = self.db.query("SELECT * FROM talk_clips WHERE id=? AND robot=? AND direction='in' "
                             "AND state='waiting'", (tid, robot))
        if not rows or not data or len(data) > 2 * MAX_BYTES:
            return False
        self.root.mkdir(parents=True, exist_ok=True)
        self._file(tid, "wav").write_bytes(data)
        with self.db.tx() as c:
            c.execute("UPDATE talk_clips SET state='recorded', bytes=? WHERE id=?",
                      (len(data), tid))
        return True

    def audio(self, tid: str) -> tuple[bytes, str]:
        """给人听:→ (字节, Content-Type)。"""
        r = self.get(tid)
        p = self._file(tid, r["ext"])
        if not p.is_file():
            raise KeyError(tid)
        return p.read_bytes(), SERVE_MIME.get(r["ext"], "application/octet-stream")

    def prune(self) -> int:
        """过了 :data:`KEEP_MS` 的连文件带记录删掉。回删了几条。顺带把等太久的回话标失败。"""
        self.expire()
        old = self.db.query("SELECT id, ext FROM talk_clips WHERE created_ms<?",
                            (self._now() - KEEP_MS,))
        gone = []
        for r in old:
            try:
                self._file(r["id"], r["ext"]).unlink(missing_ok=True)
                gone.append(r["id"])
            except OSError:
                # 外审 1.1 #5:文件删不掉记录留着,下一拍再删(不然文件永远没人管)
                if r["id"] not in self._stuck:
                    self._stuck.add(r["id"])
                    log.warning("录音 %s 删不掉,下次再试", r["id"])
        if gone:
            with self.db.tx() as c:
                c.executemany("DELETE FROM talk_clips WHERE id=?", [(i,) for i in gone])
            self._stuck.difference_update(gone)
        return len(gone)
