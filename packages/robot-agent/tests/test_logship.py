"""机器人日志按批收起来、等发件箱传到站点(日志设计 第 5 条)。"""

from __future__ import annotations

import gzip

from nexwar_agent import logship


class 假journal:
    def __init__(self):
        self.calls = []
        self.out = {"nexwar_agent": "2026-11-10T08:00:00.000000+0800 h a[1]: 第一行 token=abc\n"}

    def __call__(self, argv, timeout):
        self.calls.append(list(argv))
        unit = argv[2].removesuffix(".service")
        text = self.out.pop(unit, "")
        return 0, text + "-- cursor: s=CUR-" + unit + "\n"


def test_按游标接着读_打码_写完放done_游标才挪(tmp_path):
    j = 假journal()
    s = logship.LogShipper(tmp_path / "outbox" / "logs", units=("nexwar_agent",), run=j,
                           now_s=lambda: 1_794_000_000.0)
    d = s.tick()
    assert d is not None and (d / logship.DONE).is_file()
    text = gzip.open(d / "nexwar_agent.log.gz", "rt").read()
    assert "第一行" in text and "abc" not in text, "令牌打码"
    assert "--since" in j.calls[0]
    assert s.tick() is None, "没新东西不写"
    assert j.calls[1][-2:] == ["--after-cursor", "s=CUR-nexwar_agent"]
    assert logship.classify("nexwar_agent.log.gz") == 9 and logship.classify("done") is None


def test_文件按偏移接着读_半行留到下一次(tmp_path):
    f = tmp_path / "agent.log"
    f.write_text("一\n二\n半")
    s = logship.LogShipper(tmp_path / "ob" / "logs", files=(f,), run=lambda a, t: (1, ""))
    d = s.tick()
    assert gzip.open(d / "agent.log.gz", "rt").read() == "一\n二\n"
    with open(f, "a") as fh:
        fh.write("行\n三\n")
    d2 = s.tick()
    assert gzip.open(d2 / "agent.log.gz", "rt").read() == "半行\n三\n"


def test_攒多了删最旧的(tmp_path):
    t = [1_794_000_000.0]
    f = tmp_path / "a.log"
    s = logship.LogShipper(tmp_path / "ob" / "logs", files=(f,), run=lambda a, x: (1, ""),
                           now_s=lambda: t[0], cap_bytes=1)
    for i in range(3):
        f.write_text("x" * 100 * (i + 1) + "\n")
        t[0] += 60
        s.tick()
    left = [p for p in (tmp_path / "ob" / "logs").iterdir() if p.is_dir()]
    assert len(left) <= 1
