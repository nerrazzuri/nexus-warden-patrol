"""日志文件的统一写法(日志设计 第 3、4 条)。"""

from __future__ import annotations

import logging
import os
import re
import time

import pytest

from nexwar_contract import logsetup


@pytest.fixture
def 根(tmp_path):
    root = logging.getLogger()
    old = (root.level, list(root.handlers))
    root.handlers = []
    hs = logsetup.setup(name="site", log_dir=tmp_path, level="INFO", stream=False)
    yield tmp_path
    for h in hs:
        h.close()
    root.handlers = old[1]
    root.setLevel(old[0])


def _flush():
    for h in logging.getLogger().handlers:
        h.flush()


def test_每行带时区时间_级别_模块_编号(根):
    log = logging.getLogger("nexwar_site.api")
    with logsetup.context(req="r1", task="t-9", pt=3):
        log.warning("拒绝 POST /api/mode code=0x0213 dispatch.refused")
    log.info("没有编号的一行")
    _flush()
    lines = (根 / "site.log").read_text(encoding="utf-8").splitlines()
    assert re.match(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}[+-]\d\d:\d\d WARNING nexwar_site\.api "
                    r"\[req=r1 task=t-9 pt=3\] 拒绝 POST", lines[0]), lines[0]
    assert re.search(r" INFO nexwar_site\.api 没有编号的一行$", lines[1]), lines[1]


def test_访问记录只进access_log_不进主日志(根):
    log = logging.getLogger("nexwar_site.api")
    log.info("GET /api/robots 200", extra={"access": True})
    log.info("POST /api/mode 200")
    _flush()
    assert "GET /api/robots" in (根 / "access.log").read_text(encoding="utf-8")
    main = (根 / "site.log").read_text(encoding="utf-8")
    assert "GET /api/robots" not in main and "POST /api/mode" in main


def test_按时间段_按任务号取行_堆栈跟着上一行(根):
    log = logging.getLogger("x")
    with logsetup.context(task="t-1"):
        try:
            raise RuntimeError("炸了")
        except RuntimeError:
            log.exception("任务出错")
    with logsetup.context(task="t-2"):
        log.info("别的任务")
    _flush()
    got = logsetup.read_range(根, "site", since_s=time.time() - 60, grep="task=t-1")
    assert "任务出错" in got and "RuntimeError: 炸了" in got and "别的任务" not in got
    assert logsetup.read_range(根, "site", since_s=time.time() + 60) == ""


def test_目录超上限从最旧的删_还在写的不删_超过天数的也删(tmp_path):
    now = time.time()
    for i, name in enumerate(["site.log.2026-10-01", "site.log.2026-10-02", "site.log.2026-11-09"]):
        p = tmp_path / name
        p.write_bytes(b"x" * 1000)
        os.utime(p, (now - (40 - i * 10) * 86_400,) * 2)
    (tmp_path / "site.log").write_bytes(b"x" * 1000)
    gone = logsetup.trim_dir(tmp_path, 10_000, keep_days=30, now_s=now)
    assert [p.name for p in gone] == ["site.log.2026-10-01"]              # 40 天前
    gone = logsetup.trim_dir(tmp_path, 2_500, now_s=now)
    assert [p.name for p in gone] == ["site.log.2026-10-02"]              # 超上限删最旧的
    assert (tmp_path / "site.log").exists()


def test_装两次不叠_写的是当时的标准错误(tmp_path, monkeypatch):
    import io
    import logging

    from nexwar_contract import logsetup
    root = logging.getLogger()
    before = list(root.handlers)
    try:
        logsetup.setup(name="x", log_dir=tmp_path)
        logsetup.setup(name="x", log_dir=tmp_path)
        ours = [h for h in root.handlers if getattr(h, "_nexwar_logsetup", False)]
        assert len(ours) == 3, "标准错误 + 主日志 + 访问记录,各一份"
        buf = io.StringIO()
        monkeypatch.setattr("sys.stderr", buf)
        logging.getLogger("t").warning("换了标准错误以后")
        assert "换了标准错误以后" in buf.getvalue()
    finally:
        for h in [h for h in root.handlers if h not in before]:
            root.removeHandler(h)
            h.close()


def test_真机1120_后台写_标准错误塞住了也不卡调用方_编号堆栈照样带上_满了丢(monkeypatch):
    """11-20:journald 写不动、标准错误的管道塞满,代理写一行日志事件循环停 10–20 s。"""
    import io
    import logging
    import sys
    import threading
    import time

    from nexwar_contract import logsetup

    gate = threading.Event()

    class 塞住的(io.StringIO):
        def write(self, s):
            gate.wait(5)
            return super().write(s)
    err = 塞住的()
    monkeypatch.setattr(sys, "stderr", err)
    monkeypatch.setattr(logsetup, "BACKGROUND_QUEUE", 50)
    try:
        logsetup.setup(name="t", log_dir=None, level="INFO", background=True)
        log = logging.getLogger("x")
        t0 = time.monotonic()
        with logsetup.context(task="T1"):
            log.info("第 %d 行", 1)
            try:
                raise ValueError("坏了")
            except ValueError:
                log.exception("出错")
        for i in range(200):
            log.info("灌 %d", i)
        assert time.monotonic() - t0 < 0.5, "塞住了也不等"
        gate.set()
        deadline = time.monotonic() + 5
        while "丢了" not in err.getvalue() and time.monotonic() < deadline:
            log.info("再来一行")
            time.sleep(0.05)
        out = err.getvalue()
        assert "[task=T1] 第 1 行" in out and "ValueError: 坏了" in out
        assert "日志写不过来,丢了" in out
    finally:
        gate.set()
        logsetup._stop_listener()
        logging.getLogger().handlers.clear()
