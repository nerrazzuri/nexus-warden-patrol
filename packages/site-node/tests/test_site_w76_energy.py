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
        self.c = SimpleNamespace(telemetry=SimpleNamespace(battery_pct=pct, battery_packs=None),
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


def test_换到一半站点重启照样接上_换好充好了销账_之后再掉电不再起_重启也记得(tmp_path):
    """外审 W76-2 #3:以前换好(两块 90%)之后半小时掉到 79%,旧的「因电量结束」还在,又起一轮换电。"""
    t = 台(tmp_path, pct=60.0)                           # 换到一半站点重启:合起来还不到线
    t.结束("task_done", ended="battery")
    assert t.pe.swap_line("A") == SWAP_OK_PCT
    t.c.status.task = SimpleNamespace(task_id="dock-1")  # 在回充桩上充着:不起,但充到线照样销账
    t.c.telemetry.battery_pct = 90.0
    assert t.pe.swap_line("A") is None
    t.pe.tick()                                          # 外审 W76-3 #2:销账靠每拍看电量
    t.c.status.task = None
    t.c.telemetry.battery_pct = 79.0
    assert t.pe.swap_line("A") is None and t.pe.charge_line("A") == 25.0, "补过了:按平时的线"
    again = PatrolEnergy(t.db, SimpleNamespace(clients={"A": t.c}), t.st, now_ms=lambda: t.now)
    assert again.swap_line("A") is None, "站点重启也记得补过了"
    t.c.telemetry.battery_pct = 30.0
    t.结束("task_done", ended="battery")                  # 又跑了一趟、又因电量结束:重新起
    assert t.pe.swap_line("A") == SWAP_OK_PCT


def test_过了两小时_上一趟不是电量结束_在跑任务_掉线_读不出电量_都不起(tmp_path):
    t = 台(tmp_path, pct=30.0)
    t.结束("task_done", ended="battery")
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
    assert t.pe.swap_line("A") == SWAP_OK_PCT
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


def test_外审3_两块分开报_两块都装着都到线才销账_拔着一块不算(tmp_path):
    """外审 W76-3 #1:第一块换好 [90, 35],拔第二块成 [90, None],总电量按在位的算是 90 ——
    以前就销账了。"""
    t = 台(tmp_path, pct=90.0)
    t.结束("task_done", ended="battery")
    t.c.telemetry.battery_packs = (90.0, None)
    t.pe.tick()
    assert t.pe.swap_line("A") == SWAP_OK_PCT, "还缺一块:接着引导"
    t.c.telemetry.battery_packs = (90.0, 35.0)
    t.c.telemetry.battery_pct = 62.0
    t.pe.tick()
    assert t.pe.swap_line("A") == SWAP_OK_PCT
    t.c.telemetry.battery_packs = (90.0, 95.0)
    t.c.telemetry.battery_pct = 92.0
    t.pe.tick()
    t.c.telemetry.battery_packs = (79.0, 79.0)
    t.c.telemetry.battery_pct = 79.0
    assert t.pe.swap_line("A") is None, "换好了销账,之后掉电不再起"


def test_外审3_只问要不要补能不销账_充到线之前出桩也接着要(tmp_path):
    t = 台(tmp_path, pct=81.0)
    t.结束("task_done", ended="battery")
    assert t.pe.swap_line("A") is None                   # 81%:眼下不用补
    t.c.telemetry.battery_pct = 79.0
    assert t.pe.swap_line("A") == SWAP_OK_PCT, "没经过一拍销账:还算没补好"
    t.pe.tick()
    t.c.telemetry.battery_pct = 81.0
    t.pe.tick()
    t.c.telemetry.battery_pct = 79.5
    assert t.pe.swap_line("A") is None and t.pe.charge_line("A") == 25.0


def test_外审4_巡逻欠着补能_回充至少充到85_值守要的低也不提前出桩_补好了不再管(tmp_path):
    """外审 W76-4:值守要充到 60% 就出桩,巡逻要补到 80%,空着了又进桩(四分钟 6 次);出桩线正好
    80 时达线那一下可能夹在两拍之间,没销上账。充到 85:在 80 以上要待好几分钟,每拍一定看得见。"""
    from nexwar_site.patrol_energy import CHARGE_TO_PCT
    t = 台(tmp_path, pct=30.0)
    assert t.pe.resume_line("A") is None, "没欠着:按值守 / 默认的"
    t.结束("task_done", ended="battery")
    assert CHARGE_TO_PCT == 85.0 > SWAP_OK_PCT
    t.c.status.task = SimpleNamespace(task_id="dock-1")  # 充着电也要答(出桩线在派回充时定)
    assert t.pe.resume_line("A") == CHARGE_TO_PCT
    assert combine_lines(lambda r: 60.0, t.pe.resume_line)("A") == CHARGE_TO_PCT
    assert combine_lines(lambda r: 95.0, t.pe.resume_line)("A") == 95.0
    t.c.telemetry.battery_pct = 82.0
    t.pe.tick()
    assert t.pe.resume_line("A") is None
