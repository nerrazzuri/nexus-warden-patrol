"""W76:巡逻电量到全站电量线回来以后 —— 有桩按这条线起回充;没桩、上一趟因为电量到线结束、空着、
电量在线下才起换电引导(换电引导会叫停在动的机器人,低电时有人遥控不能被它打断)。"""

from __future__ import annotations

import json
from types import SimpleNamespace

from nexwar_site.db import SiteDB
from nexwar_site.patrol_energy import PatrolEnergy, combine_lines
from nexwar_site.site_settings import SiteSettings


class 台:
    def __init__(self, tmp_path, pct=20.0):
        self.db = SiteDB(tmp_path / "s.db")
        self.st = SiteSettings(self.db)
        self.c = SimpleNamespace(telemetry=SimpleNamespace(battery_pct=pct),
                                 status=SimpleNamespace(online=True, task=None))
        self.pe = PatrolEnergy(self.db, SimpleNamespace(clients={"A": self.c}), self.st)
        self.n = 0

    def 结束(self, kind, **data):
        self.n += 1
        with self.db.tx() as c:
            c.execute("INSERT INTO events(robot_id, boot_id, seq, event_id, kind, data, stamp, "
                      "received_at) VALUES (?,?,?,?,?,?,?,?)",
                      ("A", "b", self.n, f"e{self.n}", kind,
                       json.dumps({"task_id": f"t{self.n}", **data}), self.n, self.n))


def test_回充按全站电量线起(tmp_path):
    t = 台(tmp_path)
    assert t.pe.charge_line("A") == 25.0
    t.st.set_duty({"patrol_return_pct": 40}, by="alice")
    assert t.pe.charge_line("A") == 40.0


def test_换电_上一趟电量到线结束_空着_线下_才起(tmp_path):
    t = 台(tmp_path, pct=22.0)
    assert t.pe.swap_line("A") is None, "没跑过巡逻:不起"
    t.结束("task_done", ended="battery", laps=5)
    assert t.pe.swap_line("A") == 25.0
    t.结束("task_failed", ended="battery", reason="电量低(半路返航,已回到原点)")
    assert t.pe.swap_line("A") == 25.0, "有限圈半路电量返航也算"


def test_换电_上一趟不是电量结束_在跑任务_电量在线上_都不起(tmp_path):
    t = 台(tmp_path, pct=22.0)
    t.结束("task_done", ended="loops", laps=2)
    assert t.pe.swap_line("A") is None
    t.结束("task_done", ended="battery")
    t.c.status.task = SimpleNamespace(task_id="tele")
    assert t.pe.swap_line("A") is None, "在跑任务(遥控也是)不起"
    t.c.status.task = None
    t.c.telemetry.battery_pct = 30.0
    assert t.pe.swap_line("A") is None, "换好了 / 在线上"
    t.c.telemetry.battery_pct = None
    assert t.pe.swap_line("A") is None
    assert t.pe.swap_line("B") is None
    t.c.telemetry.battery_pct = 22.0
    t.c.status.online = False
    assert t.pe.swap_line("A") is None


def test_值守的线和巡逻的线_取高的_都没有是None_一头出错不耽误另一头():
    assert combine_lines(lambda r: None, lambda r: None)("A") is None
    assert combine_lines(lambda r: 30.0, lambda r: None)("A") == 30.0
    assert combine_lines(lambda r: 30.0, lambda r: 40.0)("A") == 40.0
    assert combine_lines(lambda r: None, lambda r: 25.0)("A") == 25.0

    def 坏(r):
        raise RuntimeError("x")
    assert combine_lines(坏, lambda r: 25.0)("A") == 25.0
