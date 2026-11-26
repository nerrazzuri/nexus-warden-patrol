"""狗没在驱离时自己看见人(W33,决策 48):布防时报 P1、一回只报一次、留守临时撤防撤防不报、驱离中不报;
就地驱离。"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from test_site_charging import 假告警台

from nexwar_site.db import SiteDB
from nexwar_site.modes import ArmingDesk
from nexwar_site.sightings import PersonWatch


class 假派遣:
    def __init__(self):
        self.clients = {"A": SimpleNamespace(
            status=SimpleNamespace(online=True, task=None),
            capabilities=SimpleNamespace(tasks={"persons": {"state": "ok", "present": False}}),
            telemetry=SimpleNamespace(pose=SimpleNamespace(map_id="m", map_version="1",
                                                           x=3.0, y=4.0, yaw=0.0)))}

    def persons(self, rid, **kw):
        self.clients[rid].capabilities.tasks["persons"] = {"state": "ok", **kw}


@pytest.fixture
def 台(tmp_path):
    ms = [1_800_000_000_000]
    db = SiteDB(tmp_path / "s.db")
    d = 假派遣()
    arming = ArmingDesk(db, now_ms=lambda: ms[0])
    det = SimpleNamespace(sessions={})
    w = PersonWatch(db, d, now_ms=lambda: ms[0], arming=arming, deterrence=det)
    w.alerts = 假告警台()
    return SimpleNamespace(db=db, d=d, w=w, arming=arming, det=det, ms=ms)


def test_布防时看见人报P1_带人数距离位置_现场照片在persons那几趟(台):
    t = 台
    t.d.persons("A", present=True, count=2, nearest_m=3.5)
    t.w.tick()
    [a] = t.w.alerts.raised
    assert a["kind"] == "dog_sees_person" and a["robot"] == "A"
    assert "2 个人" in a["title"] and "3.5 m" in a["title"]
    assert a["context"]["task_id"] == "persons" and a["context"]["pose"]["x"] == 3.0
    assert "就地驱离" in a["detail"]


def test_一回看见只报一次_人走了才清_再看见再报_说不清不清(台):
    t = 台
    t.d.persons("A", present=True, count=1)
    t.w.tick()
    t.w.tick()
    assert len(t.w.alerts.raised) == 1
    t.d.persons("A", present=None)                       # 检测断了:说不清
    t.w.tick()
    t.w.alerts.raised.clear()                             # 保安已经处理掉了那一条
    t.d.persons("A", present=True, count=1)
    t.w.tick()
    assert t.w.alerts.raised == [], "说不清不算走了:不重报"
    t.d.persons("A", present=False)
    t.w.tick()
    t.d.persons("A", present=True, count=1)
    t.w.tick()
    assert [x["kind"] for x in t.w.alerts.raised] == ["dog_sees_person"]


def test_易用性37第十二轮_报警关了检测断流很久_清掉这一回_再看见照报P1_闪断不清(台):
    t = 台
    t.d.persons("A", present=True, count=1)
    t.w.tick()
    assert len(t.w.alerts.raised) == 1
    t.w.alerts.raised.clear()                             # 那条关了(假告警台没有 open_of = 都算关了)
    t.d.clients["A"].capabilities.tasks["persons"] = {"state": "stale"}   # 人员流断了:说不清
    t.w.tick()
    t.ms[0] += 30_000
    t.w.tick()
    t.d.persons("A", present=True, count=1)
    t.w.tick()
    assert t.w.alerts.raised == [], "闪断 30 秒:不清,人还在不重报"
    t.d.clients["A"].capabilities.tasks["persons"] = {"state": "stale"}
    t.w.tick()
    t.ms[0] += 61_000
    t.w.tick()
    assert t.db.query("SELECT 1 FROM person_sightings WHERE robot_id='A'") == []
    t.d.persons("A", present=True, count=1)
    t.w.tick()
    assert [x["kind"] for x in t.w.alerts.raised] == ["dog_sees_person"], "另起一回照报 P1"


@pytest.mark.parametrize("mode", ["home", "visitor"])
def test_留守临时撤防不报_切回布防人还在就报(台, mode):
    t = 台
    kw = {"zones": ["drive"], "minutes": 30} if mode == "visitor" else {}
    t.arming.set_mode(mode, by="olga", **kw)
    t.d.persons("A", present=True, count=1)
    t.w.tick()
    assert t.w.alerts.raised == []
    t.arming.set_mode("armed", by="gina")
    t.w.tick()
    assert len(t.w.alerts.raised) == 1


def test_驱离中不报_那一场归W24管(台):
    t = 台
    t.det.sessions["A"] = object()
    t.d.persons("A", present=True, count=1)
    t.w.tick()
    assert t.w.alerts.raised == []


def test_狗掉线_检测不在正常看_都不报(台):
    t = 台
    t.d.clients["A"].capabilities.tasks["persons"] = {"state": "stale", "present": True}
    t.w.tick()
    t.d.persons("A", present=True, count=1)
    t.d.clients["A"].status.online = False
    t.w.tick()
    assert t.w.alerts.raised == []


def test_告警台报不出去_下一拍补报_不重复记(台):
    t = 台
    t.w.alerts = None
    t.d.persons("A", present=True, count=1)
    t.w.tick()
    assert t.db.query("SELECT 1 FROM pending_alerts")
    t.w.alerts = 假告警台()
    t.w.tick()
    assert len(t.w.alerts.raised) == 1


# ---- 外审 R2:时间表部分布防时,按机器人可靠的现在位置看它那个防区布不布防 ----

def _分区台(台, *, default_on: bool = True):
    """gate(0–10)全天布防、house(20–30)撤防;「全部防区一样」那份 default_on 决定没画到的地方。"""
    from datetime import timezone

    from nexwar_site.areas import AreaBook
    from nexwar_site.arming_schedule import ArmingSchedule
    t = 台
    sch = t.arming.schedule = ArmingSchedule(t.db, now_ms=lambda: t.ms[0], tz=lambda: timezone.utc)
    slots = [{"zone": "gate", "day": d, "start": "00:00", "end": "24:00"} for d in range(7)]
    slots += [{"zone": "house", "day": 6, "start": "00:00", "end": "00:01"}]
    slots += [{"zone": "", "day": d, "start": "00:00", "end": "24:00" if default_on else "00:01"}
              for d in range(7)]
    sch.put({"enabled": True, "slots": slots}, by="olga")
    areas = AreaBook(t.db, now_ms=lambda: t.ms[0])
    areas.set("m", "1", "gate", [[0, 0], [10, 0], [10, 10], [0, 10]], by="olga")
    areas.set("m", "1", "house", [[20, 0], [30, 0], [30, 10], [20, 10]], by="olga")
    t.w.areas = areas
    c = t.d.clients["A"]
    c.status.ready = SimpleNamespace(loc_ok=True)
    t.d.telemetry_at, t.d.stale_ms = {"A": t.ms[0]}, 10_000
    assert t.arming.view()["state"] == "partial"
    return t


def _站在(t, x, y):
    t.d.clients["A"].telemetry.pose.x, t.d.clients["A"].telemetry.pose.y = x, y


def test_外审R2_部分布防_机器人在布防的门口看见人报P1(台):
    t = _分区台(台)
    _站在(t, 3, 4)
    t.d.persons("A", present=True, count=1)
    t.w.tick()
    assert [a["kind"] for a in t.w.alerts.raised] == ["dog_sees_person"]


def test_外审R2_在撤防的建筑边不报_走进布防的门口就报(台):
    t = _分区台(台)
    _站在(t, 25, 4)
    t.d.persons("A", present=True, count=1)
    t.w.tick()
    assert t.w.alerts.raised == [] and t.db.query("SELECT * FROM person_sightings") == []
    _站在(t, 3, 4)
    t.w.tick()
    assert [a["kind"] for a in t.w.alerts.raised] == ["dog_sees_person"]


def test_外审R2_位置说不清_部分布防时宁可报(台):
    t = _分区台(台)
    _站在(t, 25, 4)                                   # 最后报的位置在撤防的建筑边,但已经过期
    t.d.telemetry_at["A"] = t.ms[0] - 60_000
    t.d.persons("A", present=True, count=1)
    t.w.tick()
    assert len(t.w.alerts.raised) == 1
    t.w.alerts.raised.clear()
    with t.db.tx() as c:
        c.execute("DELETE FROM person_sightings")
    t.d.telemetry_at["A"] = t.ms[0]
    t.d.clients["A"].status.ready.loc_ok = False      # 定位丢了
    t.w.tick()
    assert len(t.w.alerts.raised) == 1


def test_外审R2_没画防区的地方按全部防区那一份(台):
    t = _分区台(台, default_on=False)
    _站在(t, 50, 50)                                  # 位置可靠,不在任何防区里;那一份此刻撤防
    t.d.persons("A", present=True, count=1)
    t.w.tick()
    assert t.w.alerts.raised == []


def test_外审R2_布防的门口授权在场不报_授权没了补报(台):
    t = _分区台(台)
    who = ["王师傅"]
    t.arming.authz = SimpleNamespace(active=lambda zone: who[0] if zone == "gate" else None)
    _站在(t, 3, 4)
    t.d.persons("A", present=True, count=1)
    t.w.tick()
    assert [a["kind"] for a in t.w.alerts.raised] == ["authorized_person"]
    who[0] = None
    t.w.tick()
    assert [a["kind"] for a in t.w.alerts.raised] == ["authorized_person", "dog_sees_person"]


def test_外审R2_armed_now_给受力警报用(台):
    t = _分区台(台)
    _站在(t, 3, 4)
    assert t.w.armed_now("A") is True
    _站在(t, 25, 4)
    assert t.w.armed_now("A") is False
    t.arming.set_mode("home", by="olga")              # 手动留守:老约定,不报
    _站在(t, 3, 4)
    assert t.w.armed_now("A") is False


def _具名都撤防台(台, *, default_on=True):
    """gate、house 此刻都撤防;「全部防区一样」那份(没画到的地方)按 default_on。"""
    from datetime import timezone

    from nexwar_site.areas import AreaBook
    from nexwar_site.arming_schedule import ArmingSchedule
    t = 台
    sch = t.arming.schedule = ArmingSchedule(t.db, now_ms=lambda: t.ms[0], tz=lambda: timezone.utc)
    slots = [{"zone": z, "day": 6, "start": "00:00", "end": "00:01"} for z in ("gate", "house")]
    slots += [{"zone": "", "day": d, "start": "00:00", "end": "24:00" if default_on else "00:01"}
              for d in range(7)]
    sch.put({"enabled": True, "slots": slots}, by="olga")
    areas = AreaBook(t.db, now_ms=lambda: t.ms[0])
    areas.set("m", "1", "gate", [[0, 0], [10, 0], [10, 10], [0, 10]], by="olga")
    areas.set("m", "1", "house", [[20, 0], [30, 0], [30, 10], [20, 10]], by="olga")
    t.w.areas = areas
    t.d.clients["A"].status.ready = SimpleNamespace(loc_ok=True)
    t.d.telemetry_at, t.d.stale_ms = {"A": t.ms[0]}, 10_000
    return t


def test_外审复查R2_具名防区都撤防_没画到的地方还布防_整体算部分布防_站在外面看见人照报(台):
    t = _具名都撤防台(台)
    assert t.arming.view()["state"] == "partial", "默认区域还布防:不是全站撤防"
    _站在(t, 50, 50)
    assert t.w.armed_now("A") is True
    t.d.persons("A", present=True, count=1)
    t.w.tick()
    assert [a["kind"] for a in t.w.alerts.raised] == ["dog_sees_person"]
    _站在(t, 3, 4)                                     # 在撤防的门口:不报
    assert t.w.armed_now("A") is False


def test_外审复查R2_具名都撤防_定位说不清宁可报_全站都撤防才不报(台):
    t = _具名都撤防台(台)
    t.d.clients["A"].status.ready.loc_ok = False
    assert t.w.armed_now("A") is True
    t2 = _具名都撤防台(台, default_on=False)
    assert t2.arming.view()["state"] == "disarmed"
    assert t2.w.armed_now("A") is False, "全站都撤防:说不清也不报"


def test_W73_站在值守位上_按它盯着的那个防区判(台):
    """设计 §5.4:值守位常在防区边上、甚至在防区外;站在那儿看见人,按它盯着的防区布不布防判。"""
    t = _分区台(台, default_on=False)
    _站在(t, 15, 4)                                    # 两个防区中间:按「全部防区一样」那份,撤防
    t.d.persons("A", present=True, count=1)
    t.w.tick()
    assert t.w.alerts.raised == []
    t.w.watching = lambda rid: "gate" if rid == "A" else None
    t.w.tick()
    assert [a["kind"] for a in t.w.alerts.raised] == ["dog_sees_person"]


def test_W73_值守位上定位说不清_不按盯着的防区算(台):
    t = _分区台(台, default_on=False)
    t.w.watching = lambda rid: "house"
    t.d.clients["A"].status.ready = SimpleNamespace(loc_ok=False)
    _站在(t, 15, 4)
    t.d.persons("A", present=True, count=1)
    t.w.tick()
    assert [a["kind"] for a in t.w.alerts.raised] == ["dog_sees_person"], "说不清宁可报(同外审 R2)"


# ---------------------------------------------------------------- 用户 11-13:布防见人就喊话、开警灯

class 假上装派遣(假派遣):
    def __init__(self, outputs=("strobe", "speaker"), clips=("restricted", "distance")):
        super().__init__()
        self.clients["A"].capabilities.tasks["deter"] = {"outputs": list(outputs),
                                                          "clips": list(clips)}
        self.sent: list[tuple[str, dict, int]] = []

    async def deter(self, rid, payload, *, issued_by, priority):
        self.sent.append((rid, payload, priority))
        return {"ack": {"result": "accepted"}}


def _上装台(t, **kw):
    import asyncio  # noqa: F401
    d = 假上装派遣(**kw)
    w = PersonWatch(t.db, d, now_ms=lambda: t.ms[0], arming=t.arming, deterrence=t.det)
    w.alerts = 假告警台()
    return d, w


async def _拍(w):
    import asyncio
    w.tick()
    for _ in range(3):
        await asyncio.sleep(0)


async def test_用户1113_布防看见人_开警灯放话术_人一直在每30秒再来一次_低于人手动喊话(台):
    from nexwar_site.priorities import MANUAL
    from nexwar_site.sightings import WARN_EVERY_MS
    t = 台
    d, w = _上装台(t)
    d.persons("A", present=True, count=1, nearest_m=4.0)
    await _拍(w)
    outs = {p["output"]: (p, pri) for _, p, pri in d.sent}
    assert outs["strobe"][0]["on"] is True and outs["strobe"][0]["max_s"] > WARN_EVERY_MS / 1000
    assert outs["speaker"][0]["clip"] == "restricted" and outs["speaker"][1] < MANUAL
    n = len(d.sent)
    await _拍(w)
    assert len(d.sent) == n, "30 秒里不重复"
    t.ms[0] += WARN_EVERY_MS
    await _拍(w)
    assert len(d.sent) == 2 * n, "人还在:再来一次"
    d.persons("A", present=False)
    await _拍(w)
    t.ms[0] += WARN_EVERY_MS
    await _拍(w)
    ons = [p for _, p, _ in d.sent if p["on"]]
    assert len(ons) == 2 * n, "人走了不再喊(用户 11-15:人走了警灯当场关)"


async def test_用户1113_撤防_授权在场_驱离中_都不喊不开灯(台):
    t = 台
    d, w = _上装台(t)
    t.arming.set_mode("home", by="olga")
    d.persons("A", present=True, count=1)
    await _拍(w)
    assert d.sent == []
    t.arming.set_mode("armed", by="gina")
    t.det.sessions["A"] = object()                       # 驱离中:归驱离那一场管
    await _拍(w)
    assert d.sent == []


async def test_用户1113_没有那段话术只开灯_没接警灯只放话术_没上装什么都不发(台):
    t = 台
    d, w = _上装台(t, clips=("distance",))
    d.persons("A", present=True, count=1)
    await _拍(w)
    assert [p["output"] for _, p, _ in d.sent] == ["strobe"]
    d2, w2 = _上装台(t, outputs=("speaker",))
    d2.persons("A", present=True, count=1)
    await _拍(w2)
    assert [p["output"] for _, p, _ in d2.sent] == ["speaker"]
    t3 = 假派遣()                                         # 没装上装
    w3 = PersonWatch(t.db, t3, now_ms=lambda: t.ms[0], arming=t.arming, deterrence=t.det)
    w3.alerts = 假告警台()
    t3.persons("A", present=True, count=1)
    await _拍(w3)                                         # 不抛


async def test_用户1113_我们的上装_中英文轮着放(台):
    from nexwar_site.sightings import WARN_EVERY_MS
    t = 台
    d, w = _上装台(t, clips=("warn-zh", "warn-en", "notified-zh"))
    d.persons("A", present=True, count=1)
    got = []
    for _ in range(3):
        await _拍(w)
        t.ms[0] += WARN_EVERY_MS
    got = [p["clip"] for _, p, _ in d.sent if p["output"] == "speaker"]
    assert got == ["warn-zh", "warn-en", "warn-zh"]


async def test_用户1113_报警说明_开了灯喊话写已警告(台):
    t = 台
    d, w = _上装台(t)
    d.persons("A", present=True, count=1)
    await _拍(w)
    [a] = w.alerts.raised
    assert a["detail"].startswith("布防中,机器人已开警灯、喊话警告") and "就地驱离" in a["detail"]


def test_用户1113_没上装的机器人_报警说明照旧(台):
    t = 台
    t.d.persons("A", present=True, count=1)
    t.w.tick()
    [b] = t.w.alerts.raised
    assert b["detail"].startswith("布防中,机器人不在驱离")


async def test_用户1113_有警灯没喇叭_只开灯_不推进话术轮次(台):
    t = 台
    d, w = _上装台(t, outputs=("strobe",), clips=("warn-zh", "warn-en"))
    d.persons("A", present=True, count=1)
    await _拍(w)
    assert [p["output"] for _, p, _ in d.sent] == ["strobe"]
    assert w._warn_n == {}


# ------------------------------------------------ 用户 11-15:见人还要开警笛;人走了关


async def test_用户1115_布防看见人_警灯警笛话术一起开_人走了警灯警笛当场关(台):
    t = 台
    d, w = _上装台(t, outputs=("strobe", "siren", "speaker"))
    d.persons("A", present=True, count=1, nearest_m=6.0)
    await _拍(w)
    on = {p["output"]: p for _, p, _ in d.sent}
    assert on["siren"]["on"] is True and on["strobe"]["on"] is True and "speaker" in on
    [a] = w.alerts.raised
    assert "警笛" in a["detail"]
    d.sent.clear()
    d.persons("A", present=False)
    await _拍(w)
    off = {p["output"]: p for _, p, _ in d.sent}
    assert set(off) == {"strobe", "siren"} and not any(p["on"] for p in off.values())
    d.sent.clear()
    await _拍(w)
    assert d.sent == [], "关过了不重复关"


async def test_用户1115_没接警笛的_照旧灯加话术(台):
    t = 台
    d, w = _上装台(t)
    d.persons("A", present=True, count=1)
    await _拍(w)
    assert "siren" not in {p["output"] for _, p, _ in d.sent}


def _定位好(t):
    t.d.clients["A"].status.ready = SimpleNamespace(loc_ok=True)
    t.d.telemetry_at, t.d.stale_ms = {"A": t.ms[0]}, 10_000


def test_用户1115_报警时就把人在地图上的位置放进去_按机器人位置加方向距离(台):
    import math
    t = 台
    _定位好(t)
    t.d.clients["A"].telemetry.pose.yaw = math.pi / 2          # 机器人朝北
    t.d.persons("A", present=True, count=1, nearest_m=6.0, bearing_deg=-90.0)   # 人在它右手边
    t.w.tick()
    [a] = t.w.alerts.raised
    p = a["context"]["person"]
    assert abs(p["x"] - 9.0) < 0.01 and abs(p["y"] - 4.0) < 0.01, p
    assert p["at_ms"] == t.ms[0]


def test_用户1115_没方向或没距离_不瞎标人的位置(台):
    t = 台
    t.d.persons("A", present=True, count=1, nearest_m=6.0)
    t.w.tick()
    [a] = t.w.alerts.raised
    assert "person" not in a["context"]


async def test_用户1115_保安开了驱离_人走了不关灯笛_归驱离那一场管(台):
    t = 台
    d, w = _上装台(t, outputs=("strobe", "siren", "speaker"))
    d.persons("A", present=True, count=1)
    await _拍(w)
    t.det.sessions["A"] = object()                       # 保安点了「就地驱离」
    d.sent.clear()
    d.persons("A", present=False)
    await _拍(w)
    assert d.sent == [], "驱离中的灯笛归驱离管"
    del t.det.sessions["A"]
    await _拍(w)
    assert d.sent == [], "驱离接手过,这边的账清了,不补关"


# -------------------- 外审 W77-1 #6 #7:灯笛关不掉要重试、重启认得回来、不关别人的


async def test_外审W77_1_6_关灯笛没成_过一会儿再关_关成了才销账(台):
    from nexwar_site.sightings import UNWARN_RETRY_MS
    t = 台
    d, w = _上装台(t, outputs=("strobe", "siren", "speaker"))
    d.persons("A", present=True, count=1)
    await _拍(w)
    real = d.deter

    async def 断了(rid, payload, *, issued_by, priority):
        if not payload["on"]:
            raise RuntimeError("断网")
        return await real(rid, payload, issued_by=issued_by, priority=priority)
    d.deter = 断了
    d.persons("A", present=False)
    await _拍(w)
    d.deter = real
    d.sent.clear()
    await _拍(w)
    assert d.sent == [], "没到重试的点"
    t.ms[0] += UNWARN_RETRY_MS
    await _拍(w)
    assert {p["output"] for _, p, _ in d.sent if not p["on"]} == {"strobe", "siren"}
    d.sent.clear()
    t.ms[0] += UNWARN_RETRY_MS
    await _拍(w)
    assert d.sent == [], "关成了:不再关"


async def test_外审W77_1_6_开着灯笛站点重启_人走了照样关(台):
    t = 台
    d, w = _上装台(t, outputs=("strobe", "siren", "speaker"))
    d.persons("A", present=True, count=1)
    await _拍(w)
    w2 = PersonWatch(t.db, d, now_ms=lambda: t.ms[0], arming=t.arming, deterrence=t.det)
    w2.alerts = w.alerts
    d.sent.clear()
    d.persons("A", present=False)
    await _拍(w2)
    assert {p["output"] for _, p, _ in d.sent if not p["on"]} == {"strobe", "siren"}


async def test_外审W77_1_7_受力警报还管着灯笛_人走了不关_只撤自己的(台):
    t = 台
    d, w = _上装台(t, outputs=("strobe", "siren", "speaker"))
    w.held_by_others = lambda rid: {"siren", "strobe"}
    d.persons("A", present=True, count=1)
    await _拍(w)
    d.sent.clear()
    d.persons("A", present=False)
    await _拍(w)
    assert d.sent == [], "受力警报还管着:不关"
    w.held_by_others = lambda rid: set()
    await _拍(w)
    assert {p["output"] for _, p, _ in d.sent if not p["on"]} == {"strobe", "siren"}, \
        "外审 W77-5 #2:受力警报放手了,见人开的(期限可能比它长)这边关"


async def test_外审W77_2_2_关的回执迟到_人又出现灯笛重开了_旧回执不销新账(台):
    import asyncio

    from nexwar_site.sightings import UNWARN_RETRY_MS, WARN_EVERY_MS
    t = 台
    d, w = _上装台(t, outputs=("strobe", "siren", "speaker"))
    d.persons("A", present=True, count=1)
    await _拍(w)
    real = d.deter
    gate = asyncio.Event()

    async def 慢关(rid, payload, *, issued_by, priority):
        if not payload["on"]:
            await gate.wait()                            # 关的回执迟到
        return await real(rid, payload, issued_by=issued_by, priority=priority)
    d.deter = 慢关
    d.persons("A", present=False)
    await _拍(w)                                         # 发出关,回执没到
    t.ms[0] += WARN_EVERY_MS
    d.persons("A", present=True, count=1)
    await _拍(w)                                         # 人又出现:重开
    gate.set()
    for _ in range(5):
        await asyncio.sleep(0)                           # 旧的关回执到了
    d.sent.clear()
    d.persons("A", present=False)
    t.ms[0] += UNWARN_RETRY_MS
    await _拍(w)
    for _ in range(5):
        await asyncio.sleep(0)
    assert {p["output"] for _, p, _ in d.sent if not p["on"]} == {"strobe", "siren"}, \
        "第二次人走了照样关"


async def test_外审W77_3_2_关的回执迟到_中间驱离接管又结束_重开了_旧回执不销新账(台):
    import asyncio

    from nexwar_site.sightings import UNWARN_RETRY_MS, WARN_EVERY_MS
    t = 台
    d, w = _上装台(t, outputs=("strobe", "siren", "speaker"))
    d.persons("A", present=True, count=1)
    await _拍(w)
    real = d.deter
    gate = asyncio.Event()

    async def 慢关(rid, payload, *, issued_by, priority):
        if not payload["on"]:
            await gate.wait()
        return await real(rid, payload, issued_by=issued_by, priority=priority)
    d.deter = 慢关
    d.persons("A", present=False)
    await _拍(w)                                         # 第 1 代的关发出,回执没到
    t.det.sessions["A"] = object()                       # 保安开了驱离:账清掉
    await _拍(w)
    del t.det.sessions["A"]                              # 驱离很快结束
    t.ms[0] += WARN_EVERY_MS
    d.persons("A", present=True, count=1)
    await _拍(w)                                         # 人又出现:重开
    gate.set()
    for _ in range(5):
        await asyncio.sleep(0)                           # 旧回执到了
    d.deter = real
    d.sent.clear()
    d.persons("A", present=False)
    t.ms[0] += UNWARN_RETRY_MS
    await _拍(w)
    for _ in range(5):
        await asyncio.sleep(0)
    assert {p["output"] for _, p, _ in d.sent if not p["on"]} == {"strobe", "siren"}


async def test_外审W77_5_2_人一直在_受力警报放手了_马上续开_不留空档(台):
    t = 台
    d, w = _上装台(t, outputs=("strobe", "siren", "speaker"))
    d.persons("A", present=True, count=1)
    await _拍(w)
    w.held_by_others = lambda rid: {"siren", "strobe"}
    t.ms[0] += 2000
    await _拍(w)
    d.sent.clear()
    w.held_by_others = lambda rid: set()                 # 受力警报到期(它的期限可能把灯笛缩短了)
    t.ms[0] += 1000
    await _拍(w)
    assert {p["output"] for _, p, _ in d.sent if p["on"]} >= {"strobe", "siren"}, "马上续开"


async def test_外审W77_6_2_关灯笛排着队_保安开了驱离_不关驱离的灯(台):
    import asyncio
    t = 台
    d, w = _上装台(t, outputs=("strobe", "siren", "speaker"))
    d.persons("A", present=True, count=1)
    await _拍(w)
    d.sent.clear()
    d.persons("A", present=False)
    w.tick()                                             # 关的协程排上了,还没跑
    t.det.sessions["A"] = object()                       # 保安点了就地驱离
    for _ in range(5):
        await asyncio.sleep(0)
    assert not [p for _, p, _ in d.sent if not p["on"]], "驱离接手了:排着的关不发"


async def test_外审W77_9_1_受力占着警笛时保安开了驱离_受力那几样账留着_都结束了照样关(台):
    t = 台
    d, w = _上装台(t, outputs=("strobe", "siren", "speaker"))
    held = {"siren"}
    w.held_by_others = lambda rid: set(held)
    d.persons("A", present=True, count=1)
    await _拍(w)
    t.det.sessions["A"] = object()                       # 保安开了驱离
    await _拍(w)
    assert set(w._lit_of("A")) == {"siren"}, "受力占着的那一样:关的责任留在这边"
    del t.det.sessions["A"]                              # 驱离结束
    d.sent.clear()
    d.persons("A", present=False)
    await _拍(w)
    assert not [p for _, p, _ in d.sent if not p["on"]], "受力还占着:先不关"
    held.clear()
    t.ms[0] += 5000
    await _拍(w)
    assert {p["output"] for _, p, _ in d.sent if not p["on"]} == {"siren"}


def test_外审W77_10_1_定位丢了_不标人的位置_照样报P1(台):
    t = 台
    _定位好(t)
    t.d.clients["A"].status.ready.loc_ok = False
    t.d.persons("A", present=True, count=1, nearest_m=6.0, bearing_deg=-90.0)
    t.w.tick()
    [a] = t.w.alerts.raised
    assert "person" not in a["context"]


def test_外审W77_10_1_位置过期_不标人的位置_照样报P1(台):
    t = 台
    _定位好(t)
    t.d.telemetry_at["A"] = t.ms[0] - 60_000              # 位置停更了
    t.d.persons("A", present=True, count=1, nearest_m=6.0, bearing_deg=-90.0)
    t.w.tick()
    [a] = t.w.alerts.raised
    assert "person" not in a["context"]


# ------------------------------------------------ 真机 11-25:撤防了还亮灯、还在喊

async def test_真机1125_撤防了人还在_见人开的警灯警笛当场关(台):
    t = 台
    t.arming.set_mode("armed", by="gina")
    d, w = _上装台(t, outputs=("strobe", "siren", "speaker"))
    d.persons("A", present=True, count=1, nearest_m=1.8)
    await _拍(w)
    assert {p["output"] for _, p, _ in d.sent} >= {"strobe", "siren"}
    d.sent.clear()
    t.arming.set_mode("home", by="olga")                 # 撤防,人还站在旁边
    await _拍(w)
    off = {p["output"]: p for _, p, _ in d.sent}
    assert set(off) == {"strobe", "siren"} and not any(p["on"] for p in off.values())


class 假话术派遣(假上装派遣):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.clients["A"].capabilities.tasks["auto_voice"] = {"person": False}
        self.voice: list[bool] = []

    async def auto_voice(self, rid, person, *, issued_by):
        self.voice.append(person)
        self.clients["A"].capabilities.tasks["auto_voice"] = {"person": person}
        return {"ack": {"result": "accepted"}}


async def test_真机1125_机器人自己的有人走近话术_只在布防且没静音时放(台):
    t = 台
    d = 假话术派遣(outputs=("strobe", "siren", "speaker"))
    w = PersonWatch(t.db, d, now_ms=lambda: t.ms[0], arming=t.arming, deterrence=t.det)
    w.alerts = 假告警台()
    t.arming.set_mode("armed", by="gina")
    await _拍(w)
    assert d.voice == [True], "布防:告诉机器人放"
    await _拍(w)
    assert d.voice == [True], "一样的不重发"
    t.arming.set_mode("home", by="olga")
    await _拍(w)
    assert d.voice == [True, False], "撤防:告诉机器人别喊"


async def test_真机1125_静音_当场停喇叭警笛_见人只开灯_重新布防自动解除(台):
    t = 台
    d = 假话术派遣(outputs=("strobe", "siren", "speaker"))
    w = PersonWatch(t.db, d, now_ms=lambda: t.ms[0], arming=t.arming, deterrence=t.det)
    w.alerts = 假告警台()
    t.arming.set_mode("armed", by="gina")
    await _拍(w)
    assert await w.mute("A", True, by="gina") is True
    await _拍(w)
    stop = {p["output"]: p["on"] for _, p, _ in d.sent}
    assert stop == {"speaker": False, "siren": False}, "当场停掉喇叭、警笛"
    assert d.voice[-1] is False and d.voice_muted == {"A": "gina"}
    d.sent.clear()
    d.persons("A", present=True, count=1, nearest_m=1.8)
    await _拍(w)
    assert [p["output"] for _, p, _ in d.sent] == ["strobe"], "静音了:见人只开灯,不喊不响"
    t.arming.set_mode("home", by="olga")
    await _拍(w)
    t.arming.set_mode("armed", by="gina")
    await _拍(w)
    assert "A" not in w.muted and d.voice[-1] is True, "撤防再布防:静音自动解除"
    assert await w.mute("A", False, by="gina") is False
