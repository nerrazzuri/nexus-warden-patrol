"""日志文件的统一写法(日志设计 第 3、4 条):站点、机器人代理共用。

- **每行格式**:
  ``2026-11-10T08:30:00.123+08:00 WARNING nexwar_site.api [req=… task=… pt=…] 事件 键=值``。
  时间带时区;方括号里是当时的编号(:func:`context` 设的),没有就不写方括号。
- **按天切分**:``<目录>/<名字>.log``,半夜换一个文件,旧的叫 ``<名字>.log.2026-11-09``;
  留 ``keep_days`` 天(默认 30),**整个目录**超过 ``max_total_bytes`` 就从最旧的删起(当天的不删)。
- **访问记录另放**:``extra={"access": True}`` 的记录只进 ``access.log``(同样按天切、30 天),
  不进主日志,也不进标准输出(systemd 日志里不再全是轮询)。
- **级别**:``level`` 给启动级别;:class:`~nexwar_contract.debuglog.DebugWatch` 照旧负责「详细日志
  N 分钟」,它调的是根日志器的级别,文件这边不另外拦。
"""

from __future__ import annotations

import contextlib
import contextvars
import logging
import logging.handlers
import os
import sys
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

KEEP_DAYS = 30
#: 一个日志目录最多占这么多(站点 2 GiB;机器人代理自己的另给)。
MAX_TOTAL_BYTES = 2 * 2**30

_CTX: contextvars.ContextVar[dict[str, Any] | None] = contextvars.ContextVar("nexwar_log_ctx",
                                                                             default=None)
#: 方括号里按这个顺序写(别的键排在后面)。
_ORDER = ("req", "robot", "task", "pt", "point", "map", "cmd")


@contextlib.contextmanager
def context(**kw: Any) -> Iterator[None]:
    """这一段代码里写的日志都带上这些编号(``None`` 的不写)。可以套着用,里层的覆盖外层。"""
    cur = dict(_CTX.get() or {})
    cur.update({k: v for k, v in kw.items()})
    token = _CTX.set({k: v for k, v in cur.items() if v is not None})
    try:
        yield
    finally:
        _CTX.reset(token)


def set_context(**kw: Any) -> None:
    """不用 with 的地方(一个任务从头到尾):直接改当前上下文。``None`` 删掉那一项。"""
    cur = dict(_CTX.get() or {})
    for k, v in kw.items():
        if v is None:
            cur.pop(k, None)
        else:
            cur[k] = v
    _CTX.set(cur)


def current() -> dict[str, Any]:
    return dict(_CTX.get() or {})


def _ctx_text(ctx: dict[str, Any]) -> str:
    if not ctx:
        return ""
    keys = [k for k in _ORDER if k in ctx] + sorted(k for k in ctx if k not in _ORDER)
    return "[" + " ".join(f"{k}={ctx[k]}" for k in keys) + "] "


class ContextFilter(logging.Filter):
    """把当前编号挂到记录上(``record.ctx``),格式里用 ``%(ctx)s``。"""

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "ctx"):
            record.ctx = _ctx_text(_CTX.get() or {})
        return True


class Formatter(logging.Formatter):
    """时间写成 ISO 8601、带毫秒和时区。"""

    def __init__(self) -> None:
        super().__init__("%(asctime)s %(levelname)s %(name)s %(ctx)s%(message)s")

    def formatTime(self, record: logging.LogRecord, datefmt: str | None = None) -> str:
        t = time.localtime(record.created)
        z = time.strftime("%z", t)
        return (time.strftime("%Y-%m-%dT%H:%M:%S", t) + f".{int(record.msecs):03d}"
                + (f"{z[:3]}:{z[3:]}" if z else ""))

    def format(self, record: logging.LogRecord) -> str:
        if not hasattr(record, "ctx"):
            record.ctx = _ctx_text(_CTX.get() or {})
        return super().format(record)


class _OnlyAccess(logging.Filter):
    def __init__(self, want: bool) -> None:
        super().__init__()
        self.want = want

    def filter(self, record: logging.LogRecord) -> bool:
        return bool(getattr(record, "access", False)) is self.want


class DailyFile(logging.handlers.TimedRotatingFileHandler):
    """半夜换文件,留 ``keep_days`` 份;换完量一下整个目录,超了从最旧的删起。"""

    def __init__(self, path: Path, *, keep_days: int = KEEP_DAYS,
                 max_total_bytes: int = MAX_TOTAL_BYTES) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        super().__init__(path, when="midnight", backupCount=keep_days, encoding="utf-8",
                         delay=True)
        self.max_total_bytes = max_total_bytes

    def doRollover(self) -> None:
        super().doRollover()
        trim_dir(Path(self.baseFilename).parent, self.max_total_bytes)


def trim_dir(d: Path, max_total_bytes: int, *, keep_days: int | None = None,
             now_s: float | None = None) -> list[Path]:
    """日志目录超过上限就删最旧的切出来的文件(还在写的 ``*.log`` 不删);``keep_days`` 给了,
    更早的也删。回删了哪些。"""
    try:
        files = [p for p in d.iterdir() if p.is_file()]
    except OSError:
        return []
    old = [p for p in files if not p.name.endswith(".log")]
    old.sort(key=lambda p: p.stat().st_mtime)
    gone: list[Path] = []
    if keep_days is not None:
        cut = (now_s if now_s is not None else time.time()) - keep_days * 86_400
        for p in list(old):
            if p.stat().st_mtime < cut:
                with contextlib.suppress(OSError):
                    p.unlink()
                    gone.append(p)
                old.remove(p)
    total = sum(p.stat().st_size for p in files if p.exists())
    for p in old:
        if total <= max_total_bytes:
            break
        try:
            n = p.stat().st_size
            p.unlink()
        except OSError:
            continue
        total -= n
        gone.append(p)
    return gone


def setup(*, name: str, log_dir: Path | None, level: str | int = "INFO",
          keep_days: int = KEEP_DAYS, max_total_bytes: int = MAX_TOTAL_BYTES,
          stream: bool = True, access: bool = True) -> list[logging.Handler]:
    """装到根日志器上。``log_dir`` 为 ``None`` 只写标准错误(命令行小工具)。回装上的处理器。"""
    root = logging.getLogger()
    lvl = level if isinstance(level, int) else logging.getLevelName(str(level).upper())
    root.setLevel(lvl if isinstance(lvl, int) else logging.INFO)
    fmt = Formatter()
    out: list[logging.Handler] = []
    if stream:
        h = logging.StreamHandler(sys.stderr)
        h.setFormatter(fmt)
        h.addFilter(_OnlyAccess(False))
        out.append(h)
    if log_dir is not None:
        log_dir = Path(log_dir)
        main = DailyFile(log_dir / f"{name}.log", keep_days=keep_days,
                         max_total_bytes=max_total_bytes)
        main.setFormatter(fmt)
        main.addFilter(_OnlyAccess(False))
        out.append(main)
        if access:
            acc = DailyFile(log_dir / "access.log", keep_days=keep_days,
                            max_total_bytes=max_total_bytes)
            acc.setFormatter(fmt)
            acc.addFilter(_OnlyAccess(True))
            out.append(acc)
        with contextlib.suppress(OSError):
            os.chmod(log_dir, 0o750)
        trim_dir(log_dir, max_total_bytes, keep_days=keep_days)
    for h in out:
        root.addHandler(h)
    return out


def read_range(log_dir: Path, name: str, *, since_s: float, until_s: float | None = None,
               grep: str | None = None, max_bytes: int = 32 * 2**20) -> str:
    """从按天切的文件里取一段时间的行(诊断包用)。按每行开头的 ISO 时间判;``grep`` 给了只要含它
    的行(任务号、机器人号)。取不出时间的行(堆栈)跟着上一行走。最多 ``max_bytes``,超了留最新的。"""
    files = sorted((p for p in Path(log_dir).glob(f"{name}.log*") if p.is_file()),
                   key=lambda p: p.stat().st_mtime)
    files = [p for p in files if p.stat().st_mtime >= since_s]
    out: list[str] = []
    size = 0
    keep = False
    for p in files:
        try:
            fh = open(p, encoding="utf-8", errors="replace")
        except OSError:
            continue
        with fh:
            for line in fh:
                at = _line_time(line)
                if at is not None:
                    keep = at >= since_s and (until_s is None or at <= until_s) \
                        and (grep is None or grep in line)
                if keep:
                    out.append(line)
                    size += len(line)
                    while size > max_bytes and out:
                        size -= len(out.pop(0))
    return "".join(out)


def _line_time(line: str) -> float | None:
    if len(line) < 19 or line[4] != "-" or line[10] != "T":
        return None
    try:
        t = time.strptime(line[:19], "%Y-%m-%dT%H:%M:%S")
    except ValueError:
        return None
    base = time.mktime(t)
    z = line[23:29] if len(line) >= 29 and line[19] == "." else ""
    if len(z) == 6 and z[0] in "+-" and z[3] == ":":
        # 文件里写的是写的那台机器的时区:换成 UTC 再按本机算(两台机器时区不同时照样对)
        off = (int(z[1:3]) * 3600 + int(z[4:6]) * 60) * (1 if z[0] == "+" else -1)
        local_off = -time.altzone if time.localtime(base).tm_isdst > 0 else -time.timezone
        base += local_off - off
    return base
