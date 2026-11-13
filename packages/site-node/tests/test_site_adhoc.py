"""W53 临时巡逻:估时、撞日程排到后面、排队的到点起跑 / 作废 / 取消、通知;今天的巡逻。

派遣器换成假的(只记派了什么、照样在派单事务里跑「发之前记账」),钟注入;日程用真的路线库
(``import_bundle``,22:00 那一条,吉隆坡时区)。"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from test_site_schedule import 任务, 打包

from nexwar_contract.mission import parse_mission
from nexwar_site import adhoc as ah
from nexwar_site.adhoc import AdhocDesk, AdhocError, geom_estimate_s
from nexwar_site.catalog import import_bundle
from nexwar_site.db import SiteDB
from nexwar_site.dispatcher import DispatchRefused
from nexwar_site.priorities import MANUAL
from nexwar_site.today import today_view

KL = ZoneInfo("Asia/Kuala_Lumpur")


def 毫秒(时: int, 分: int, 秒: int = 0, 日: int = 15) -> int:
    return int(datetime(2027, 3, 日, 时, 分, 秒, tzinfo=KL).timestamp() * 1000)


class 假派遣器:
    def __init__(self, db, robots=("A",)) -> None:
        self.db = db
        self.robots = list(robots)
        self.running: dict[str, str] = {}
        self.sent: list[dict] = []
        self.refuse = ""
        self.ack = "accepted"
        self.cannot: dict[str, str] = {}           # 派不出去的机器人 → 原因
        self.loaded = ("estate-1", "7")
        self.acks = []
        self.registry = SimpleNamespace(list=lambda: [SimpleNamespace(robot_id=r, revoked=False)
                                                      for r in self.robots])
        self.clients: dict = {}

    def busy(self, rid):
        return self.running.get(rid)

    def dispatchable(self, rid, kind):
        return self.cannot.get(rid, "")

    def autonomy(self, rid):
        return "autonomous"

    def _loaded(self, c):
        return self.loaded

    def on_ack(self, cb):
        self.acks.append(cb)

    async def patrol(self, rid, wire, *, issued_by, priority=0, task_id=None, before_send=None):
        if self.refuse:
            raise DispatchRefused(self.refuse)
        with self.db.tx() as tx:
            if before_send is not None:
                before_send(None, tx)
            tx.execute("INSERT INTO commands(command_id, task_id, robot_id, kind, payload, "
                       "issued_by, issued_at, priority) VALUES (?,?,?,?,?,?,?,?)",
                       (f"c-{task_id}", task_id, rid, "patrol",
                        json.dumps({"mission": wire}), issued_by, self.now(), priority))
        self.sent.append({"robot": rid, "task_id": task_id, "by": issued_by, "priority": priority,
                          "mission": wire["mission"], "wire": wire})
        if self.ack == "accepted":
            self.running[rid] = task_id
        reason = "忙" if self.ack != "accepted" else ""
        return {"task_id": task_id, "ack": {"result": self.ack, "reason": reason}}


class 假告警:
    def __init__(self) -> None:
        self.got: list[dict] = []

    def raise_alert(self, *, kind, robot, title, detail="", context=None, merge=True):
        # 跟真的告警台一个签名(外审 #2:原来多传了 now_ms,真站点上全抛 TypeError)
        self.got.append({"kind": kind, "robot": robot, "title": title, "detail": detail,
                         "context": context, "merge": merge})


@pytest.fixture
def 台(tmp_path):
    db = SiteDB(tmp_path / "s.db")
    import_bundle(db, 打包(tmp_path, 1), imported_by="alice", now_ms=1)
    now = {"t": 毫秒(20, 0)}
    d = 假派遣器(db)
    d.now = lambda: now["t"]
    a = 假告警()
    sup = {"why": ""}
    desk = AdhocDesk(db, d, now_ms=lambda: now["t"], alerts=a, refusal=lambda r: sup["why"])
    yield SimpleNamespace(db=db, now=now, disp=d, alerts=a, desk=desk, sup=sup)
    db.close()


def 跑(coro):
    return asyncio.run(coro)


def 任务定义():
    return dict(任务)


# ------------------------------------------------------------ 估时


def test_按路长估_相邻点加回待命点加动作():
    m = parse_mission(任务定义())
    # a(0.6,0) → b(0.6,0.6):0.6 m;回 (0,0.6):0.6 m;dwell 0.5 s
    assert geom_estimate_s(m, back_to=(0.0, 0.6)) == pytest.approx(1.2 * 1.3 / 0.5 + 0.5)
    assert geom_estimate_s(m) == pytest.approx(0.6 * 1.3 / 0.5 + 0.5)


def test_估时至少一分钟再乘余量_有历史按历史中位数(台):
    t = 台
    m = parse_mission(任务定义())
    assert t.desk.estimate_s("A", m) == int(60 * ah.MARGIN), "短路线按一分钟起算"
    # 三趟走完:600、900、1200 秒 → 中位数 900
    for i, dur in enumerate((600, 900, 1200)):
        t0 = 毫秒(10 + i, 0)
        with t.db.tx() as c:
            c.execute("INSERT INTO commands(command_id, task_id, robot_id, kind, payload, "
                      "issued_by, issued_at) VALUES (?,?,?,?,?,?,?)",
                      (f"c{i}", f"t{i}", "A", "patrol", json.dumps({"mission": 任务定义()}), "g",
                       t0))
            c.execute("INSERT INTO events(robot_id, boot_id, seq, event_id, kind, data, stamp, "
                      "received_at) VALUES (?,?,?,?,?,?,?,?)",
                      ("A", "b", i, f"e{i}", "task_done", json.dumps({"task_id": f"t{i}"}),
                       t0 + dur * 1000, t0 + dur * 1000))
    assert t.desk.history_s("A", "loop") == 900
    assert t.desk.estimate_s("A", m) == int(900 * ah.MARGIN)


# ------------------------------------------------------------ 派


def test_不撞日程马上派_手动优先级_记一行_告诉经理管理员(台):
    t = 台
    got = 跑(t.desk.submit("A", 任务定义(), label="loop", by="gina"))
    assert got["queued"] is False and got["ack"]["result"] == "accepted"
    sent = t.disp.sent[0]
    assert sent["priority"] == MANUAL and sent["task_id"].startswith("adhoc-")
    assert sent["by"] == "gina"
    row = t.db.query("SELECT * FROM adhoc_queue")[0]
    assert row["state"] == "started" and row["task_id"] == sent["task_id"]
    assert [a["kind"] for a in t.alerts.got] == ["adhoc_patrol"]
    assert "gina" in t.alerts.got[0]["title"] and "临时" in t.alerts.got[0]["title"]


def test_撞上日程排到日程走完之后_不派_告诉派的人排到几点(台):
    t = 台
    t.now["t"] = 毫秒(21, 59)                         # 22:00 有日程
    got = 跑(t.desk.submit("A", 任务定义(), label="loop", by="gina"))
    assert got["queued"] is True and t.disp.sent == []
    est = t.desk.estimate_s("A", parse_mission(任务定义()))
    assert got["start_after_ms"] == 毫秒(22, 0) + est * 1000 + 60_000
    assert "22:00" in got["because"] and "loop" in got["because"]
    # 第 8 轮 W8-10:写日程名(多条日程跑同一条路线时分得清),路线名放括号里
    assert "22:00 的日程 nightly(路线 loop)" in got["because"], got["because"]
    assert "排到" in t.alerts.got[0]["title"]


def test_正在跑日程也排到后面(台):
    t = 台
    t.disp.running["A"] = "sched-abc"
    with t.db.tx() as c:
        c.execute("INSERT INTO schedule_runs(entry_id, scheduled_ms, outcome, robot_id, task_id, "
                  "decided_at) VALUES ('nightly', ?, 'started', 'A', 'sched-abc', ?)",
                  (毫秒(19, 50), 毫秒(19, 50)))
        c.execute("INSERT INTO commands(command_id, task_id, robot_id, kind, payload, issued_by, "
                  "issued_at) VALUES ('c', 'sched-abc', 'A', 'patrol', '{}', 'schedule:nightly', "
                  "?)",
                  (毫秒(19, 50),))
    got = 跑(t.desk.submit("A", 任务定义(), label="loop", by="gina"))
    assert got["queued"] is True and "正在执行的日程" in got["because"]
    assert "正在执行的日程 nightly(路线 loop)" in got["because"], got["because"]


def test_日程没写哪台_别的台也能跑就不算撞_别的台跑不了就算(台):
    t = 台
    t.disp.robots = ["A", "B"]
    t.now["t"] = 毫秒(21, 59)
    assert t.desk.plan("A", 任务定义())["queued"] is False
    t.disp.cannot["B"] = "B 不在线"                 # 外审 #6:只有 A 能跑这条日程
    assert t.desk.plan("A", 任务定义())["queued"] is True
    t.disp.cannot["A"] = "A 未定位"
    assert t.desk.plan("B", 任务定义())["queued"] is False, "A 也跑无法完成:日程落不到谁头上"


def test_排队的_没到点不派_到点机器人忙不派_空了派_告诉派的人(台):
    t = 台
    t.now["t"] = 毫秒(21, 59)
    got = 跑(t.desk.submit("A", 任务定义(), label="loop", by="gina"))
    跑(t.desk.tick())
    assert t.disp.sent == []
    t.now["t"] = got["start_after_ms"]
    t.disp.running["A"] = "sched-x"
    跑(t.desk.tick())
    assert t.disp.sent == [], "还正在运行日程"
    t.disp.running.clear()
    跑(t.desk.tick())
    assert len(t.disp.sent) == 1 and t.disp.sent[0]["task_id"] == f"adhoc-{got['adhoc_id']}"
    row = t.db.query("SELECT * FROM adhoc_queue")[0]
    assert row["state"] == "started" and row["started_ms"] == got["start_after_ms"]
    last = t.alerts.got[-1]
    assert last["kind"] == "adhoc_queue" and last["context"]["to"] == "gina"


def test_排队的到点又撞上下一趟日程就再往后排(台):
    t = 台
    t.now["t"] = 毫秒(21, 59)
    got = 跑(t.desk.submit("A", 任务定义(), label="loop", by="gina"))
    # 第二天 22:00 不会撞;但把它挪到第二天 21:59 再跑一拍:又撞上那天的 22:00
    with t.db.tx() as c:
        c.execute("UPDATE adhoc_queue SET not_before_ms=?, created_ms=?", (毫秒(21, 59, 30, 16),
                                                                         毫秒(21, 59, 0, 16)))
    t.now["t"] = 毫秒(21, 59, 30, 16)
    跑(t.desk.tick())
    assert t.disp.sent == []
    nb = t.db.query("SELECT not_before_ms FROM adhoc_queue")[0]["not_before_ms"]
    assert nb > 毫秒(22, 0, 0, 16), got


def test_排了两个小时没轮上就作废_告诉派的人(台):
    t = 台
    t.now["t"] = 毫秒(21, 59)
    跑(t.desk.submit("A", 任务定义(), label="loop", by="gina"))
    t.now["t"] += ah.QUEUE_TTL_MS + 1
    跑(t.desk.tick())
    row = t.db.query("SELECT * FROM adhoc_queue")[0]
    assert row["state"] == "expired" and t.disp.sent == []
    assert t.alerts.got[-1]["context"]["to"] == "gina"


def test_排队的派不出去记失败(台):
    t = 台
    t.now["t"] = 毫秒(21, 59)
    got = 跑(t.desk.submit("A", 任务定义(), label="loop", by="gina"))
    t.now["t"] = got["start_after_ms"]
    t.disp.refuse = "A 未定位"
    跑(t.desk.tick())
    row = t.db.query("SELECT * FROM adhoc_queue")[0]
    assert row["state"] == "failed" and "未定位" in row["note"]


def test_取消_派的人自己能_别的保安不能_开始跑了不能(台):
    t = 台
    t.now["t"] = 毫秒(21, 59)
    got = 跑(t.desk.submit("A", 任务定义(), label="loop", by="gina"))
    with pytest.raises(PermissionError):
        t.desk.cancel(got["adhoc_id"], by="gary", may_others=False)
    t.desk.cancel(got["adhoc_id"], by="olga", may_others=True)
    assert t.db.query("SELECT state FROM adhoc_queue")[0]["state"] == "cancelled"
    with pytest.raises(AdhocError, match="不在排队"):
        t.desk.cancel(got["adhoc_id"], by="gina", may_others=False)
    with pytest.raises(AdhocError, match="没有"):
        t.desk.cancel("nope", by="gina", may_others=False)


def test_先看会怎样不派(台):
    t = 台
    t.now["t"] = 毫秒(21, 59)
    p = t.desk.plan("A", 任务定义())
    assert p["queued"] is True and p["estimate_s"] > 0 and t.disp.sent == []
    assert t.db.query("SELECT COUNT(*) AS n FROM adhoc_queue")[0]["n"] == 0


# ------------------------------------------------------------ 今天的巡逻


def test_今天的巡逻_日程每一轮加临时的_按时间排_下一趟(台):
    t = 台
    t.now["t"] = 毫秒(21, 59)
    跑(t.desk.submit("A", 任务定义(), label="loop", by="gina"))         # 排到 22:00 那趟后面
    v = today_view(t.db, now_ms=t.now["t"], adhoc=t.desk)
    assert v["date"] == "2027-03-15"
    kinds = [(x["kind"], x["state"]) for x in v["items"]]
    assert kinds == [("schedule", "next"), ("adhoc", "queued")], kinds
    assert v["items"][1]["by"] == "gina" and v["items"][1]["end_ms"] > v["items"][1]["at_ms"]


def test_今天的巡逻_日程走完_没跑_在跑(台):
    t = 台
    t.now["t"] = 毫秒(23, 0)
    with t.db.tx() as c:
        c.execute("INSERT INTO schedule_runs(entry_id, scheduled_ms, outcome, robot_id, task_id, "
                  "decided_at) VALUES ('nightly', ?, 'started', 'A', 'sched-1', ?)",
                  (毫秒(22, 0), 毫秒(22, 0)))
    item = today_view(t.db, now_ms=t.now["t"])["items"][0]
    assert (item["state"], item["robot"]) == ("running", "A")
    with t.db.tx() as c:
        c.execute("INSERT INTO events(robot_id, boot_id, seq, event_id, kind, data, stamp, "
                  "received_at) VALUES ('A','b',1,'e1','task_failed',?,?,?)",
                  (json.dumps({"task_id": "sched-1", "reason": "第 2 点被挡住"}), 毫秒(22, 10),
                   毫秒(22, 10)))
    item = today_view(t.db, now_ms=t.now["t"])["items"][0]
    assert item["state"] == "failed" and "挡住" in item["reason"]
    # 换一天:到点了一直没机器人,窗口(30 分钟)过了 → missed
    t.now["t"] = 毫秒(23, 0, 0, 16)
    with t.db.tx() as c:
        c.execute("INSERT INTO schedule_runs(entry_id, scheduled_ms, outcome, robot_id, note, "
                  "decided_at) VALUES ('nightly', ?, 'no_robot', NULL, 'A 离线', ?)",
                  (毫秒(22, 0, 0, 16), 毫秒(22, 0, 0, 16)))
    item = today_view(t.db, now_ms=t.now["t"])["items"][0]
    assert item["state"] == "missed" and "离线" in item["reason"]
    t.now["t"] = 毫秒(22, 5, 0, 16)
    assert today_view(t.db, now_ms=t.now["t"])["items"][0]["state"] == "waiting"


# ------------------------------------------------------------ 外审 W53-1


def test_外审1_排队的到点起跑前再查监护_没人监护就不派(台):
    t = 台
    t.now["t"] = 毫秒(21, 59)
    got = 跑(t.desk.submit("A", 任务定义(), label="loop", by="gina"))
    t.now["t"] = got["start_after_ms"]
    t.sup["why"] = "A 要人现场监护:先在手机上打开「我在现场监护」"
    跑(t.desk.tick())
    assert t.disp.sent == []
    row = t.db.query("SELECT * FROM adhoc_queue")[0]
    assert row["state"] == "failed" and "监护" in row["note"]


def test_外审2和3_通知经过真告警台_一次一条不合并_各推各的人(tmp_path):
    from nexwar_site.alert_store import AlertDesk
    db = SiteDB(tmp_path / "s.db")
    import_bundle(db, 打包(tmp_path, 1), imported_by="alice", now_ms=1)
    now = {"t": 毫秒(21, 59)}
    d = 假派遣器(db)
    d.now = lambda: now["t"]
    alerts = AlertDesk(db, now_ms=lambda: now["t"])
    desk = AdhocDesk(db, d, now_ms=lambda: now["t"], alerts=alerts)
    a = 跑(desk.submit("A", 任务定义(), label="loop", by="g1"))
    b = 跑(desk.submit("A", 任务定义(), label="loop", by="g2"))
    now["t"] = max(a["start_after_ms"], b["start_after_ms"]) + ah.QUEUE_TTL_MS
    跑(desk.tick())                                   # 两条都作废:各告诉各的人
    rows = db.query("SELECT kind, context FROM alerts ORDER BY first_ms, key")
    sent = [r for r in rows if r["kind"] == "adhoc_patrol"]
    told = sorted(json.loads(r["context"])["to"] for r in rows if r["kind"] == "adhoc_queue")
    assert len(sent) == 2 and told == ["g1", "g2"], [dict(r) for r in rows]
    db.close()


def test_外审4_机器人明确没收_记成没走成_晚到的拒收也改(台):
    t = 台
    t.disp.ack = "rejected"                            # 代理忙:回 rejected、原因 busy
    got = 跑(t.desk.submit("A", 任务定义(), label="loop", by="gina"))
    assert got["ack"]["result"] == "rejected"
    row = t.db.query("SELECT * FROM adhoc_queue")[0]
    assert row["state"] == "failed" and "rejected" in row["note"]
    assert [x["state"] for x in today_view(t.db, now_ms=t.now["t"], adhoc=t.desk)["items"]
            if x["kind"] == "adhoc"] == ["failed"]
    # 先收下(没回执)、后来才说不收
    t.disp.ack = "accepted"
    t.disp.running.clear()
    got = 跑(t.desk.submit("A", 任务定义(), label="loop", by="gina"))
    from nexwar_contract.messages import AckResult
    for cb in t.disp.acks:
        cb(SimpleNamespace(task_id=got["task_id"], result=AckResult.REJECTED, reason="busy"))
    row = t.db.query("SELECT * FROM adhoc_queue WHERE task_id=?", (got["task_id"],))[0]
    assert row["state"] == "failed"


def test_外审5_正在跑日程_排到它走完之后_不越推越远(台):
    t = 台
    t.disp.running["A"] = "sched-abc"
    with t.db.tx() as c:
        c.execute("INSERT INTO schedule_runs(entry_id, scheduled_ms, outcome, robot_id, task_id, "
                  "decided_at) VALUES ('nightly', ?, 'started', 'A', 'sched-abc', ?)",
                  (毫秒(20, 0), 毫秒(20, 0)))
        c.execute("INSERT INTO commands(command_id, task_id, robot_id, kind, payload, issued_by, "
                  "issued_at) VALUES ('c', 'sched-abc', 'A', 'patrol', '{}', 'schedule:nightly', "
                  "?)", (毫秒(20, 0),))
    t.now["t"] = 毫秒(20, 0, 30)
    est = t.desk.estimate_s("A", parse_mission(任务定义()))
    p = t.desk.plan("A", 任务定义())
    end = max(毫秒(20, 0) + est * 1000, t.now["t"] + 60_000)
    assert p["queued"] and p["start_ms"] == end + 60_000, "两分钟左右,不是四十分钟"


def test_外审7_到点还没派的那一轮也算撞(台):
    t = 台
    t.now["t"] = 毫秒(22, 0, 1)                       # 22:00 到点,执行器下一拍还没来
    assert t.desk.plan("A", 任务定义())["queued"] is True
    with t.db.tx() as c:                               # 那一轮派出去了(在别处跑):不再算
        c.execute("INSERT INTO schedule_runs(entry_id, scheduled_ms, outcome, robot_id, task_id, "
                  "decided_at) VALUES ('nightly', ?, 'skip', NULL, NULL, ?)",
                  (毫秒(22, 0), 毫秒(22, 0)))
    assert t.desk.plan("A", 任务定义())["queued"] is False
    t.now["t"] = 毫秒(22, 31)                          # 窗口(30 分钟)过了:也不算
    with t.db.tx() as c:
        c.execute("DELETE FROM schedule_runs")
    assert t.desk.plan("A", 任务定义())["queued"] is False


def test_外审8_派不出去的不排队_当场说(台):
    t = 台
    with t.db.tx() as c:                               # 日程写明了 A:A 派不出去也照样落到它头上
        c.execute("UPDATE route_schedules SET definition=json_set(definition, '$.robot', 'A')")
    t.now["t"] = 毫秒(21, 59)
    t.disp.cannot["A"] = "A 不在线"
    with pytest.raises(DispatchRefused, match="不在线"):
        跑(t.desk.submit("A", 任务定义(), label="loop", by="gina"))
    t.disp.cannot.clear()
    t.disp.loaded = ("estate-1", "6")
    with pytest.raises(DispatchRefused, match="加载的是"):
        跑(t.desk.submit("A", 任务定义(), label="loop", by="gina"))
    assert t.db.query("SELECT COUNT(*) AS n FROM adhoc_queue")[0]["n"] == 0


def test_外审11_排到明天的也在今天的列表里_能取消(台):
    t = 台
    with t.db.tx() as c:
        c.execute("UPDATE route_schedules SET definition=json_set(definition, '$.at', '00:10')")
    from nexwar_site.catalog import active_bundle
    assert active_bundle(t.db).schedule.entries[0].at_h == 0
    t.now["t"] = 毫秒(23, 59)
    got = 跑(t.desk.submit("A", 任务定义(), label="loop", by="gina"))
    if not got["queued"]:                              # 估时不够长撞不上 00:10:直接排一条明天的
        with t.db.tx() as c:
            c.execute("UPDATE adhoc_queue SET state='queued', not_before_ms=?",
                      (毫秒(0, 20, 0, 16),))
    items = [x for x in today_view(t.db, now_ms=t.now["t"], adhoc=t.desk)["items"]
             if x["kind"] == "adhoc"]
    assert items and items[0]["state"] in ("queued", "running")


def test_外审12_今天的巡逻和先看都带站点时区的偏移(台):
    t = 台
    assert today_view(t.db, now_ms=t.now["t"], adhoc=t.desk)["utc_offset_min"] == 480
    assert t.desk.plan("A", 任务定义())["utc_offset_min"] == 480


def _站在(t, x, y, path="straight"):
    t.disp.clients["A"] = SimpleNamespace(
        telemetry=SimpleNamespace(pose=SimpleNamespace(x=x, y=y, yaw=0.0)),
        capabilities=SimpleNamespace(tasks={"goto": {"path": path}}))


def test_用户1031_走完回起点_直线的沿来路回_会规划的直接回_本来在起点不加(台):
    t = 台
    _站在(t, -2.0, -1.0)
    跑(t.desk.submit("A", 任务定义(), label="loop", by="gina"))
    wps = t.disp.sent[-1]["wire"]["waypoints"]
    assert [w["name"] for w in wps] == ["a", "b", "return-1", "start"], "直线:倒着走回 a 再回起点"
    assert wps[-1]["pose"]["position"]["x"] == -2.0 and wps[-1]["pose"]["position"]["y"] == -1.0
    t.disp.running.clear()
    _站在(t, -2.0, -1.0, path="planned")
    跑(t.desk.submit("A", 任务定义(), label="loop", by="gina"))
    assert [w["name"] for w in t.disp.sent[-1]["wire"]["waypoints"]] == ["a", "b", "start"]
    t.disp.running.clear()
    _站在(t, 0.6, 0.6)                                    # 就站在最后一点:不加
    跑(t.desk.submit("A", 任务定义(), label="loop", by="gina"))
    assert [w["name"] for w in t.disp.sent[-1]["wire"]["waypoints"]] == ["a", "b"]
    t.disp.clients.clear()                               # 不知道在哪:不加
    t.disp.running.clear()
    跑(t.desk.submit("A", 任务定义(), label="loop", by="gina"))
    assert [w["name"] for w in t.disp.sent[-1]["wire"]["waypoints"]] == ["a", "b"]


def test_用户1031_排队的到点按那时站的地方回(台):
    t = 台
    t.now["t"] = 毫秒(21, 59)
    got = 跑(t.desk.submit("A", 任务定义(), label="loop", by="gina"))
    _站在(t, 3.0, 4.0)
    t.now["t"] = got["start_after_ms"]
    跑(t.desk.tick())
    start = t.disp.sent[-1]["wire"]["waypoints"][-1]
    assert start["name"] == "start" and start["pose"]["position"]["x"] == 3.0
    stored = json.loads(t.db.query("SELECT mission FROM adhoc_queue")[0]["mission"])
    assert [w["name"] for w in stored["waypoints"]] == ["a", "b"], "存的还是原来那条"


def test_W71_今天的巡逻_跳过几个点也算完成_带上跳过几个(台):
    """11-03 商场 Patrol1 15/16:站点、手机原来显示「未完成」。"""
    t = 台
    t.now["t"] = 毫秒(23, 0)
    with t.db.tx() as c:
        c.execute("INSERT INTO schedule_runs(entry_id, scheduled_ms, outcome, robot_id, task_id, "
                  "decided_at) VALUES ('nightly', ?, 'started', 'A', 'sched-1', ?)",
                  (毫秒(22, 0), 毫秒(22, 0)))
        c.execute("INSERT INTO events(robot_id, boot_id, seq, event_id, kind, data, stamp, "
                  "received_at) VALUES ('A','b',1,'e1','task_done',?,?,?)",
                  (json.dumps({"task_id": "sched-1", "reason": "跳过 1 个点(P3):被挡",
                               "skipped": 1, "skipped_names": ["P3"]}), 毫秒(22, 10),
                   毫秒(22, 10)))
    item = today_view(t.db, now_ms=t.now["t"])["items"][0]
    assert item["state"] == "done" and item["skipped"] == 1 and "P3" in item["reason"]


def test_网页第4轮_admin_N7_被叫停的那趟_写出是谁叫停的(台):
    t = 台
    t.now["t"] = 毫秒(23, 0)
    with t.db.tx() as c:
        c.execute("INSERT INTO schedule_runs(entry_id, scheduled_ms, outcome, robot_id, task_id, "
                  "decided_at) VALUES ('nightly', ?, 'started', 'A', 'sched-1', ?)",
                  (毫秒(22, 0), 毫秒(22, 0)))
        c.execute("INSERT INTO commands(command_id, task_id, robot_id, kind, payload, issued_by, "
                  "issued_at) VALUES ('c1', 'halt-1', 'A', 'halt', '{}', 'olga', ?)",
                  (毫秒(22, 9),))
        c.execute("INSERT INTO events(robot_id, boot_id, seq, event_id, kind, data, stamp, "
                  "received_at) VALUES ('A','b',1,'e1','task_aborted',?,?,?)",
                  (json.dumps({"task_id": "sched-1", "reason": "halt"}), 毫秒(22, 10),
                   毫秒(22, 10)))
    item = today_view(t.db, now_ms=t.now["t"])["items"][0]
    assert item["state"] == "aborted" and item["stopped_by"] == "olga"


def test_往天的巡逻_按日期查_那天跑了的照记录写(台):
    """liang-d5 第 5 轮前:往天每一趟(谁派的、跑没跑完)网页上要能查到。"""
    t = 台
    t.now["t"] = 毫秒(23, 0) + 2 * 86_400_000          # 两天以后
    with t.db.tx() as c:
        c.execute("INSERT INTO schedule_runs(entry_id, scheduled_ms, outcome, robot_id, task_id, "
                  "decided_at) VALUES ('nightly', ?, 'started', 'A', 'sched-1', ?)",
                  (毫秒(22, 0), 毫秒(22, 0)))
    v = today_view(t.db, now_ms=t.now["t"], day="2027-03-15")
    assert v["date"] == "2027-03-15"
    assert [(x["kind"], x["robot"]) for x in v["items"]] == [("schedule", "A")]
    assert today_view(t.db, now_ms=t.now["t"])["date"] == "2027-03-17"


def test_11_11_W6_02_机器人只许手动派_今天的巡逻写不会跑和原因_不写下一次(台):
    from nexwar_site.today import _schedule_item
    t = 台
    e = SimpleNamespace(id="demo-night", mission="demo-loop", robot="A", window_min=30)
    later = _schedule_item(t.db, e, 毫秒(22, 0), 毫秒(21, 0))
    assert later["state"] == "later"
    with t.db.tx() as c:
        c.execute("INSERT INTO robot_service(robot_id, by, at_ms, note) VALUES ('A','demo',0,'')")
    item = _schedule_item(t.db, e, 毫秒(22, 0), 毫秒(21, 0))
    assert item["state"] == "blocked" and item["reason"] == "manual_only", item
    assert item["robot"] == "A"
    e2 = SimpleNamespace(id="any", mission="loop", robot="", window_min=30)
    assert _schedule_item(t.db, e2, 毫秒(22, 0), 毫秒(21, 0))["state"] == "later", "没指定哪台:不猜"


def test_易用性第7轮_不会跑写上路线画在哪一版_机器人用哪一版(台):
    """liang-d5 r7:「不会跑」只写「A 只许手动派」,没提路线画在 v11 上 ——
    版本对不上也是到点不会跑的原因。"""
    from nexwar_site.today import _schedule_item
    t = 台
    e = SimpleNamespace(id="demo-night", mission="demo-loop", robot="A", window_min=30)
    want = ("mall", "11")
    def at(got):
        return _schedule_item(t.db, e, 毫秒(22, 0), 毫秒(21, 0), want=want, loaded=lambda rid: got)
    item = at(("mall", "12"))
    assert item["state"] == "blocked" and item["reason"] == "map_mismatch", item
    assert item["map"] == {"route": "11", "robot": "12"}
    same = at(("mall", "11"))
    assert same["state"] == "later" and "map" not in same
    unknown = at((None, None))
    assert unknown["state"] == "later", "机器人没报加载的图(离线)不猜"
    with t.db.tx() as c:
        c.execute("INSERT INTO robot_service(robot_id, by, at_ms, note) VALUES ('A','demo',0,'')")
    both = at(("mall", "12"))
    assert both["state"] == "blocked" and both["reason"] == "manual_only"
    assert both["map"] == {"route": "11", "robot": "12"}, "两个原因都写"


def test_易用性第7轮_整页今天的巡逻_按路线的那一版比(tmp_path):
    db = SiteDB(tmp_path / "s.db")
    from test_site_schedule import 排程
    import_bundle(db, 打包(tmp_path, 1, schedule=排程.replace("    mission: loop\n",
                                                              "    mission: loop\n    robot: A\n")),
                  imported_by="alice", now_ms=1)
    v = today_view(db, now_ms=毫秒(20, 0), loaded=lambda rid: ("estate-1", "8"))
    item = v["items"][0]
    assert item["robot"] == "A" and item["state"] == "blocked"
    assert item["map"] == {"route": "7", "robot": "8"}
    v = today_view(db, now_ms=毫秒(20, 0), loaded=lambda rid: ("estate-1", "7"))
    assert v["items"][0]["state"] == "next"
    db.close()


def _一直巡逻跑了(t, 圈: int, 收尾: str, at_ms: int) -> None:
    """A 上一趟一直巡逻(两个点一圈)跑了 ``圈`` 圈,然后报 ``收尾``。"""
    mission = {**任务定义(), "policy": {"loops": 0}}
    with t.db.tx() as c:
        c.execute("INSERT INTO adhoc_queue(id, robot, mission, label, by, created_ms, "
                  "not_before_ms, estimate_s, state, task_id, started_ms) VALUES "
                  "('f1','A',?,'loop','demo',?,?,600,'started','adhoc-forever-f1',?)",
                  (json.dumps(mission), 毫秒(20, 0), 毫秒(20, 0), 毫秒(20, 0)))
        c.execute("INSERT INTO commands(command_id, task_id, robot_id, kind, payload, issued_by, "
                  "issued_at) VALUES ('cf','adhoc-forever-f1','A','patrol',?,'demo',?)",
                  (json.dumps({"mission": mission}), 毫秒(20, 0)))
        for i in range(圈 * 2):
            c.execute("INSERT INTO events(robot_id, boot_id, seq, event_id, kind, data, stamp, "
                      "received_at) VALUES ('A','b',?,?,'patrol_waypoint',?,?,?)",
                      (10 + i, f"w{i}",
                       json.dumps({"task_id": "adhoc-forever-f1", "index": i % 2}),
                       毫秒(20, 1) + i, 毫秒(20, 1) + i))
        if 收尾:
            c.execute("INSERT INTO events(robot_id, boot_id, seq, event_id, kind, data, stamp, "
                      "received_at) VALUES ('A','b',999,'end',?,?,?,?)",
                      (收尾, json.dumps({"task_id": "adhoc-forever-f1", "reason": "preempted"}),
                       at_ms, at_ms))


def _临时(t):
    items = today_view(t.db, now_ms=t.now["t"], adhoc=t.desk)["items"]
    return next(x for x in items if x["kind"] == "adhoc")


def test_第8轮_W8_03_被日程接替的一直巡逻_不算未完成_写跑了几圈和哪条日程(台):
    t = 台
    _一直巡逻跑了(t, 6, "task_preempted", 毫秒(22, 0) + 2_000)
    with t.db.tx() as c:
        c.execute("INSERT INTO schedule_runs(entry_id, scheduled_ms, outcome, robot_id, task_id, "
                  "decided_at) VALUES ('nightly', ?, 'started', 'A', 'sched-1', ?)",
                  (毫秒(22, 0), 毫秒(22, 0)))
    t.now["t"] = 毫秒(22, 30)
    it = _临时(t)
    assert it["state"] == "handed_over", it
    assert it["reason"] == "", "不露 preempted 这种代号"
    assert it["handover"] == {"by": "schedule", "name": "nightly", "laps": 6}
    assert it["forever"] is True


def test_第8轮_A8_01_一直巡逻在跑_不给预计结束时间_带第几圈(台):
    t = 台
    _一直巡逻跑了(t, 2, "", 0)
    t.now["t"] = 毫秒(20, 30)
    it = _临时(t)
    assert it["state"] == "running" and it["end_ms"] is None, "一直巡逻没有固定结束时间"
    assert it["forever"] is True and it["lap"] == {"n": 3, "of": 0}
