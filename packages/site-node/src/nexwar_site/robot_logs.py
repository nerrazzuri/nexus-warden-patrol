"""站点收、存机器人传上来的日志(日志设计 第 5 条,用户 11-10:留 90 天)。

- 收件口 ``/logs/api/intake/put``(mTLS,机器人号按证书认):``run`` = 机器人那边收的时刻
  ``YYYYMMDD-HHMMSS[-n]``,``rel`` = ``<服务>.log.gz``。存成
  ``<站点目录>/robot-logs/<机器人>/<run>/<服务>.log.gz``(分块、断点续传同证据库)。
- 留 :data:`KEEP_DAYS` 天;每台最多 :data:`MAX_PER_ROBOT` 字节,超了从最旧的删。
- :meth:`RobotLogs.read` 给诊断包:按时间段、可选按关键字(任务号)取出各服务的行。
"""

from __future__ import annotations

import contextlib
import gzip
import logging
import re
import shutil
import time
from pathlib import Path

from nexwar_site.evidence import ChunkWriter, PathRefused, Stored, safe_join

log = logging.getLogger(__name__)

KEEP_DAYS = 90                       # 用户 11-10:日志、记录默认都留 90 天
MAX_PER_ROBOT = 2 * 2**30
_RUN = re.compile(r"^(\d{8})-(\d{6})(?:-\d{1,4})?$")
_REL = re.compile(r"^[a-z0-9_.@-]{1,64}\.log\.gz$")


def run_time(run: str) -> float | None:
    m = _RUN.match(run)
    if m is None:
        return None
    try:
        return time.mktime(time.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S"))
    except ValueError:
        return None


class RobotLogs:
    def __init__(self, root: Path, *, now_s=time.time) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.writer = ChunkWriter()
        self._now = now_s

    def put(self, robot_id: str, run: str, rel: str, *, offset: int, data: bytes,
            total: int) -> Stored:
        if run_time(run) is None:
            raise PathRefused(f"日志批次名要是 YYYYMMDD-HHMMSS:{run!r}")
        if not _REL.match(rel):
            raise PathRefused(f"站点只收 <服务>.log.gz:{rel!r}")
        path = safe_join(self.root, robot_id, run, rel)
        got = self.writer.write(path, offset=offset, data=data, total=total)
        if got.size >= total:
            log.debug("收齐 %s 的日志 %s/%s(%d 字节)", robot_id, run, rel, total)
        return got

    def robots(self) -> list[str]:
        return sorted(p.name for p in self.root.iterdir() if p.is_dir())

    def prune(self, *, keep_days: int = KEEP_DAYS, max_per_robot: int = MAX_PER_ROBOT) -> int:
        """过了留存期的、超了每台上限的(从最旧的)删掉。回删了几批。"""
        cut = self._now() - keep_days * 86_400
        n = 0
        for rdir in [p for p in self.root.iterdir() if p.is_dir()]:
            runs = sorted((p for p in rdir.iterdir() if p.is_dir()), key=lambda p: p.name)
            sizes = {p: sum(f.stat().st_size for f in p.rglob("*") if f.is_file()) for p in runs}
            total = sum(sizes.values())
            for p in runs:
                t = run_time(p.name)
                if (t is not None and t < cut) or total > max_per_robot:
                    shutil.rmtree(p, ignore_errors=True)
                    total -= sizes[p]
                    n += 1
        if n:
            log.info("机器人日志过了 %d 天或超了上限:删了 %d 批", keep_days, n)
        return n

    def read(self, robot_id: str, *, since_s: float, until_s: float | None = None,
             grep: str | None = None, max_bytes: int = 32 * 2**20) -> dict[str, str]:
        """→ ``{服务: 文本}``。一批是「上一次收到这一次收」之间写的,批次名是收的时刻:
        取 ``since_s`` 之后、结束后两天内收的批次,行的时刻按行头判。"""
        rdir = self.root / robot_id
        if not rdir.is_dir():
            return {}
        runs = sorted((p for p in rdir.iterdir() if p.is_dir() and run_time(p.name) is not None),
                      key=lambda p: p.name)
        # 断网时那段日志要等连上了才收到:出事后两天内收的批次都看(行按行头时刻再筛)
        hi = (until_s if until_s is not None else self._now()) + 2 * 86_400
        picked = [p for p in runs if since_s <= (run_time(p.name) or 0) <= hi]
        out: dict[str, list[str]] = {}
        size = 0
        for p in picked:
            for f in sorted(p.glob("*.log.gz")):
                name = f.name.removesuffix(".log.gz")
                try:
                    with gzip.open(f, "rt", encoding="utf-8", errors="replace") as fh:
                        lines = fh.readlines()
                except (OSError, EOFError):
                    continue
                for ln in lines:
                    if grep is not None and grep not in ln:
                        continue
                    at = _journal_time(ln)
                    if at is not None and (at < since_s or (until_s is not None and at > until_s)):
                        continue
                    out.setdefault(name, []).append(ln)
                    size += len(ln)
                    if size > max_bytes:
                        break
        return {k: "".join(v) for k, v in out.items()}


def _journal_time(line: str) -> float | None:
    """``journalctl -o short-iso-precise`` 的行头(``2026-11-10T08:30:00.123456+0800``),或我们自己
    日志格式的行头;都不是给 ``None``(那行不按时刻筛)。"""
    from nexwar_contract.logsetup import _line_time
    with contextlib.suppress(Exception):
        return _line_time(line)
    return None
