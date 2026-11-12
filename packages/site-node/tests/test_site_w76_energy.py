"""W76:巡逻因为电量到线结束、回来以后补能 —— 有桩回充,没桩起换电引导。

外审 W76-1 #3–#5 之后的规矩:看**最近一趟巡逻**(不看之后回待命点、去充电那几趟)是不是因为电量结束
(``ended: battery``)、两小时以内、机器人在线空着、电量还没到「换好」那条线(80%,跟换电引导判
换好同一条)。不跟全站电量线比:机器人可能按更高的动态返航线(回原点路远)提前回来。换好、充好
(≥80%)就不再起;站点换到一半重启,两块合起来不到 80% 照样接上。"""

from __future__ import annotations

import json
from types import SimpleNamespace

from nexwar_site.db import SiteDB
from nexwar_site.energy import SWAP_OK_PCT
from nexwar_site.patrol_energy import RECENT_MS, PatrolEnergy, combine_lines
from nexwar_site.site_settings import SiteSettings

NOW = 1_800_000_000_000


class 台:
    def __init__(self, tmp_path, pct=20.0):
        self.db = SiteDB(tmp_path / "s.db")
        self.st = SiteSettings(self.db)
        self.now = NOW
        self.c = SimpleNamespace(telemetry=SimpleNamespace(battery_pct=pct),
                                 status=SimpleNamespace(online=True, task=None))
        self.pe = PatrolEnergy(self.db, SimpleNamespace(clients={"A": self.c}), self.st,
                               now_ms=lambda: self.now)
        self.n = 0

    def 结束(self, kind, *, cmd="patrol", at=None, **data):
        self.n += 1
        tid = f"t{self.n}"
        at = self.now if at is None else at
        with self.db.tx() as c:
            c.execute("INSERT INTO commands(command_id, task_id, robot_id, kind, payload, "
                      "issued_by, issued_at) VALUES (?,?,?,?,?,?,?)",
                      (f"c{self.n}", tid, "A", cmd, "{}", "g", at - 1000))
            c.execute("INSERT INTO events(robot_id, boot_id, seq, event_id, kind, data, stamp, "
                      "received_at) VALUES (?,?,?,?,?,?,?,?)",
                      ("A", "b", self.n, f"e{self.n}", kind,
                       json.dumps({"task_id": tid, **data}), at, at))


def test_平时回充按全站电量线起(tmp_path):
    t = 台(tmp_path)
    assert t.pe.charge_line("A") == 25.0
    t.st.set_duty({"patrol_return_pct": 40}, by="alice")
    assert t.pe.charge_line("A") == 40.0


def test_巡逻因电量结束_回充换电都起_电量比全站线高也起(tmp_path):
    t = 台(tmp_path, pct=35.0)                           # 按动态返航线 35% 就回来了,全站线 25
    assert t.pe.swap_line("A") is None, "没跑过巡逻:不起"
    t.结束("task_done", ended="battery", laps=5)
    assert t.pe.swap_line("A") == SWAP_OK_PCT
    assert t.pe.charge_line("A") == SWAP_OK_PCT
    t.结束("task_failed", ended="battery", reason="电量低(半路返航,已回到原点)")
    assert t.pe.swap_line("A") == SWAP_OK_PCT, "有限圈半路电量返航也算"


def test_之后回待命点去充电那几趟不盖掉(tmp_path):
    t = 台(tmp_path, pct=30.0)
    t.结束("task_done", ended="battery")
    t.结束("task_done", cmd="goto")                       # 回待命点 / 去充电
    assert t.pe.swap_line("A") == SWAP_OK_PCT


def test_换好充好了_过了两小时_上一趟不是电量结束_在跑任务_都不起(tmp_path):
    t = 台(tmp_path, pct=30.0)
    t.结束("task_done", ended="battery")
    t.c.telemetry.battery_pct = SWAP_OK_PCT
    assert t.pe.swap_line("A") is None and t.pe.charge_line("A") == 25.0, "换好 / 充好了"
    t.c.telemetry.battery_pct = 60.0                     # 换到一半站点重启:两块合起来还不到线
    assert t.pe.swap_line("A") == SWAP_OK_PCT
    t.now = NOW + RECENT_MS + 1
    assert t.pe.swap_line("A") is None, "两小时前的事了"
    t.now = NOW
    t.c.status.task = SimpleNamespace(task_id="tele")
    assert t.pe.swap_line("A") is None, "在跑任务(遥控也是)不起"
    t.c.status.task = None
    t.c.telemetry.battery_pct = None
    assert t.pe.swap_line("A") is None
    assert t.pe.swap_line("B") is None
    t.c.telemetry.battery_pct = 30.0
    t.c.status.online = False
    assert t.pe.swap_line("A") is None
    t.c.status.online = True
    t.结束("task_done", ended="loops", laps=2)
    assert t.pe.swap_line("A") is None


def test_值守的线和巡逻的线_取高的_都没有是None_一头出错不耽误另一头():
    assert combine_lines(lambda r: None, lambda r: None)("A") is None
    assert combine_lines(lambda r: 30.0, lambda r: None)("A") == 30.0
    assert combine_lines(lambda r: 30.0, lambda r: 40.0)("A") == 40.0
    assert combine_lines(lambda r: None, lambda r: 25.0)("A") == 25.0

    def 坏(r):
        raise RuntimeError("x")
    assert combine_lines(坏, lambda r: 25.0)("A") == 25.0
