"""机器人日志传到站点(日志设计 第 5 条,用户 11-10:机器人的日志也存到站点上;留 90 天)。

- 每隔 ``every_s``(默认 5 分钟)把我们各服务这段时间新写的日志收一份:systemd 日志按游标接着读
  (``journalctl --after-cursor``,第一次只取最近 1 小时);演示、仿真里没有 systemd 的,按文件偏移
  接着读(``files``)。打码(令牌、口令、长串十六进制)后 gzip,写成
  ``<发件箱>/logs/<时刻>/<服务>.log.gz``,写完才放 ``done``,游标这时才往前挪。
- 上传走发件箱(:class:`~nexwar_agent.outbox.Outbox` 的 ``logs`` 一块,站点的接收口 ``/logs``,
  mTLS,断点续传);站点确认收齐才删。**断网时先攒在机器人上**,最多 ``cap_bytes``,超了删最旧的
  (日志不该把巡逻要用的盘挤满),删了记一行。
- 这一块不算进发件箱的盘况(跟录像一样),攒多了不让机器人拒巡逻。
"""

from __future__ import annotations

import contextlib
import gzip
import json
import logging
import os
import re
import shutil
import subprocess
import threading
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

#: 每隔多久收一次(秒)。
EVERY_S = 300.0
#: 机器人上最多攒这么多没传走的日志。
CAP_BYTES = 300 * 2**20
#: 一个服务一次最多收这么多(没压缩前):话特别多的服务不许一次撑爆一个文件。
MAX_PER_UNIT = 16 * 2**20
#: 第一次(没有游标)往回取多久。
FIRST_SINCE = "-1h"
DONE = "done"
GZ = ".log.gz"
_NAME = re.compile(r"[a-z0-9_.@-]{1,64}")
_CURSOR = re.compile(r"^-- cursor: (\S+)\s*$")

Run = Callable[[Sequence[str], float], tuple[int, str]]


def _run(argv: Sequence[str], timeout_s: float) -> tuple[int, str]:
    try:
        p = subprocess.run(list(argv), capture_output=True, text=True, timeout=timeout_s,
                           check=False, errors="replace")
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 127, str(exc)
    return p.returncode, p.stdout


def classify(rel: str) -> int | None:
    """发件箱 ``logs`` 一块只传 ``*.log.gz``,排在证据后面。"""
    return 9 if rel.endswith(GZ) and "/" not in rel else None


def settled(run: Path) -> bool:
    return (run / DONE).is_file()


class LogShipper:
    def __init__(self, spool: Path, *, units: Sequence[str] = (), files: Sequence[Path] = (),
                 run: Run = _run, now_s: Callable[[], float] = time.time,
                 cap_bytes: int = CAP_BYTES, redact: Callable[[str], str] | None = None) -> None:
        self.spool = Path(spool)
        self.units = tuple(u for u in units if _NAME.fullmatch(u))
        self.files = tuple(Path(f) for f in files)
        self._run = run
        self._now = now_s
        self.cap_bytes = cap_bytes
        if redact is None:
            from nexwar_agent.ops import redact as _r
            redact = _r
        self._redact = redact
        self._state_path = self.spool.parent / "logship-state.json"
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------ 游标

    def _load(self) -> dict[str, Any]:
        try:
            d = json.loads(self._state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return d if isinstance(d, dict) else {}

    def _save(self, st: dict[str, Any]) -> None:
        tmp = self._state_path.with_name(self._state_path.name + ".tmp")
        tmp.write_text(json.dumps(st), encoding="utf-8")
        tmp.replace(self._state_path)

    # ------------------------------------------------------------ 收

    def _journal(self, unit: str, cursor: str | None) -> tuple[str, str | None]:
        argv = ["journalctl", "-u", f"{unit}.service", "--no-pager", "-o", "short-iso-precise",
                "--show-cursor"]
        argv += ["--after-cursor", cursor] if cursor else ["--since", FIRST_SINCE]
        rc, out = self._run(argv, 60.0)
        if rc != 0 and not out.strip():
            return "", cursor
        lines = out.splitlines(keepends=True)
        new = cursor
        if lines and (m := _CURSOR.match(lines[-1])):
            new = m.group(1)
            lines = lines[:-1]
        text = "".join(ln for ln in lines if not ln.startswith("-- No entries --"))
        return text, new

    def _tail(self, path: Path, at: dict[str, Any] | None) -> tuple[str, dict[str, Any] | None]:
        try:
            st = path.stat()
        except OSError:
            return "", at
        off = int((at or {}).get("offset", 0))
        if at is None or at.get("ino") != st.st_ino or st.st_size < off:
            off = 0 if at is not None else max(0, st.st_size - MAX_PER_UNIT)   # 换了文件 / 被截短
        with open(path, "rb") as fh:
            fh.seek(off)
            data = fh.read(MAX_PER_UNIT)
        cut = data.rfind(b"\n") + 1                        # 半行留到下一次
        return (data[:cut].decode("utf-8", "replace"),
                {"ino": st.st_ino, "offset": off + cut})

    def tick(self) -> Path | None:
        """收一次。有新东西回写出来的目录,没有回 ``None``。"""
        st = self._load()
        cursors = dict(st.get("cursors") or {})
        tails = dict(st.get("tails") or {})
        got: dict[str, str] = {}
        for u in self.units:
            text, cur = self._journal(u, cursors.get(u))
            if text.strip():
                got[u] = text[-MAX_PER_UNIT:]
            if cur:
                cursors[u] = cur
        for f in self.files:
            name = re.sub(r"[^a-z0-9_.@-]", "_", f.name.lower())[:48].removesuffix(".log")
            text, at = self._tail(f, tails.get(str(f)))
            if text.strip():
                got[name] = text
            if at is not None:
                tails[str(f)] = at
        out = None
        if got:
            out = self._write(got)
        self._save({"cursors": cursors, "tails": tails})   # 写完了才挪游标
        self._trim()
        return out

    def _write(self, got: dict[str, str]) -> Path:
        stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(self._now()))
        d = self.spool / stamp
        n = 1
        while d.exists():
            d = self.spool / f"{stamp}-{n}"
            n += 1
        self.spool.mkdir(parents=True, exist_ok=True)
        tmp = self.spool.parent / f".logship-{d.name}.tmp"    # 发件箱外面写好再挪进去
        shutil.rmtree(tmp, ignore_errors=True)
        tmp.mkdir(parents=True)
        for name, text in got.items():
            with gzip.open(tmp / f"{name}{GZ}", "wt", encoding="utf-8") as fh:
                fh.write(self._redact(text))
        (tmp / DONE).write_text("", encoding="utf-8")
        tmp.replace(d)
        return d

    def _trim(self) -> None:
        dirs = sorted(p for p in self.spool.iterdir() if p.is_dir() and not p.name.startswith("."))
        sizes = {p: sum(f.stat().st_size for f in p.iterdir() if f.is_file()) for p in dirs}
        total = sum(sizes.values())
        for p in dirs:
            if total <= self.cap_bytes:
                break
            shutil.rmtree(p, ignore_errors=True)
            total -= sizes[p]
            log.warning("待传的日志超过 %d MB,删掉最旧的一批没传走的:%s",
                        self.cap_bytes // 2**20, p.name)

    # ------------------------------------------------------------ 线程

    def start(self, every_s: float = EVERY_S) -> None:
        self.spool.mkdir(parents=True, exist_ok=True)

        def loop() -> None:
            while not self._stop.wait(every_s):
                try:
                    self.tick()
                except Exception:
                    log.exception("收日志出错,下一回再试")
        self._thread = threading.Thread(target=loop, name="logship", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5.0)
        with contextlib.suppress(Exception):
            self.tick()                                   # 关机前最后收一次


def spool_dir(outbox: Path) -> Path:
    return Path(outbox) / "logs"


def ensure_private(p: Path) -> None:
    with contextlib.suppress(OSError):
        os.chmod(p, 0o700)
