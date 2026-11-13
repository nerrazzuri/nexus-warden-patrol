"""机器人日志存到站点、按场景导出诊断包(日志设计 第 5 条,用户 11-10)。"""

from __future__ import annotations

import gzip
import io
import json
import os
import tarfile
import time

import pytest

from nexwar_site.db import SiteDB
from nexwar_site.evidence import PathRefused
from nexwar_site.health import scene_window, support_bundle
from nexwar_site.robot_logs import RobotLogs


def _iso(t: float) -> str:
    z = time.strftime("%z", time.localtime(t))
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(t)) + f".000{z[:3]}:{z[3:]}"


def _gz(text: str) -> bytes:
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb") as fh:
        fh.write(text.encode())
    return buf.getvalue()


def _放一批(logs: RobotLogs, rid: str, t: float, name: str, text: str) -> None:
    data = _gz(text)
    run = time.strftime("%Y%m%d-%H%M%S", time.localtime(t))
    logs.put(rid, run, f"{name}.log.gz", offset=0, data=data, total=len(data))


def test_只收批次名和服务名对的_存到机器人名下(tmp_path):
    logs = RobotLogs(tmp_path)
    with pytest.raises(PathRefused):
        logs.put("A", "../x", "a.log.gz", offset=0, data=b"", total=0)
    with pytest.raises(PathRefused):
        logs.put("A", "20261110-083000", "a.txt", offset=0, data=b"", total=0)
    _放一批(logs, "A", time.time(), "nexwar_agent", "x\n")
    assert logs.robots() == ["A"]


def test_按时间段_按任务号取行(tmp_path):
    logs = RobotLogs(tmp_path)
    t0 = time.time() - 3600
    _放一批(logs, "A", t0 + 300, "nexwar_agent",
            f"{_iso(t0 + 10)} INFO x [task=t-1 pt=2] 去这个点\n"
            f"{_iso(t0 + 20)} INFO x [task=t-2] 别的任务\n"
            f"{_iso(t0 - 7200)} INFO x 很早的\n")
    got = logs.read("A", since_s=t0, until_s=t0 + 600)
    assert "去这个点" in got["nexwar_agent"] and "很早的" not in got["nexwar_agent"]
    only = logs.read("A", since_s=t0, until_s=t0 + 600, grep="task=t-1")
    assert "别的任务" not in only["nexwar_agent"]


def test_过了90天和超了上限的删掉(tmp_path):
    now = time.time()
    logs = RobotLogs(tmp_path, now_s=lambda: now)
    _放一批(logs, "A", now - 100 * 86_400, "nexwar_agent", "old\n")
    _放一批(logs, "A", now - 10, "nexwar_agent", "new\n")
    assert logs.prune() == 1
    assert [p.name for p in (tmp_path / "A").iterdir()] == [
        time.strftime("%Y%m%d-%H%M%S", time.localtime(now - 10))]


def test_按告警导出_时间段取告警前后_轨迹合上机器人日志里补的位置_README写出现过的错误码(tmp_path):
    db = SiteDB(tmp_path / "site.db")
    (tmp_path / "site.json").write_text("{}")
    now_ms = int(time.time() * 1000)
    first = now_ms - 3 * 86_400_000                     # 三天前出的事,今天才导
    db.query("INSERT INTO alerts(key, kind, level, robot, title, detail, first_ms, last_ms, count, "
             "acked_by, resolved_by, escalated, context) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
             ("A/stuck#1", "stuck", "P1", "A", "机器人卡住了", "", first, first + 60_000, 1, "",
              "", 0, json.dumps({"err": "0x0216"})))
    db.query("INSERT INTO pose_track(robot_id, stamp_ms, map_id, map_version, x, y) "
             "VALUES (?,?,?,?,?,?)", ("A", first - 60_000, "estate", "3", 1.0, 2.0))
    logs = RobotLogs(tmp_path / "robot-logs")
    t = first / 1000
    _放一批(logs, "A", t + 600, "nexwar_agent",
            f"{_iso(t - 30)} INFO nexwar_agent.runtime 位置 (1.50, 2.50, 0.10) map=estate:3 "
            "task=t-9 定位=可信 质量=0.90\n"
            f"{_iso(t)} WARNING nexwar_agent.engine.machine [task=t-9 pt=3] 没到 "
            "code=0x0406 nav.robot_trapped 第 1 次 用时 60.0 s why=被困\n")
    win = scene_window(db, now_ms=now_ms, alert="A/stuck#1")
    assert win["robot"] == "A" and win["since_ms"] < first - 60_000 < win["until_ms"] < now_ms
    assert win["ref"] == "alert:A/stuck#1" and win["scene"].startswith("报警 "), win  # W6-07/08
    out = support_bundle(tmp_path / "b.tar.gz", home=tmp_path, db=db, health=None, now_ms=now_ms,
                         journal=lambda u, h: "", robot_logs=logs, by="alice", **win)
    with tarfile.open(out) as tf:
        files = {m.name.removeprefix("nexwar_support/"): tf.extractfile(m).read().decode()
                 for m in tf.getmembers()}
    assert "没到 code=0x0406" in files["robots/A/logs/nexwar_agent.log"]
    track = files["robots/A/track.csv"].splitlines()
    assert track[0] == "time_ms,source,x,y,yaw,map,task,loc"
    assert [r.split(",")[1] for r in track[1:]] == ["site", "robot"]   # 站点记的 + 机器人补的
    readme = files["README.md"]
    assert "alice" in readme and "报警 A/stuck#1" in readme
    assert "`0x0406`" in readme and "`0x0216`" in readme and "机器人被困住" in readme
    db.close()


def test_场景找不到_时间段太长_都拒(tmp_path):
    db = SiteDB(tmp_path / "site.db")
    with pytest.raises(ValueError, match="没有这条报警"):
        scene_window(db, now_ms=10**12, alert="nope")
    with pytest.raises(ValueError, match="没有这个任务"):
        scene_window(db, now_ms=10**12, task="nope")
    with pytest.raises(ValueError, match="最多取"):
        scene_window(db, now_ms=10**12, since_ms=0)
    db.close()
    assert os.path.exists(tmp_path / "site.db")


def test_按一趟巡检取时间段_从机器人上开始的时刻往前10分钟(tmp_path):
    db = SiteDB(tmp_path / "site.db")
    t0 = 1_790_000_000_000
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(t0 / 1000))
    db.query("INSERT INTO runs(robot_id, mission, stamp, first_ms, last_ms) VALUES (?,?,?,?,?)",
             ("B", "夜巡", stamp, t0 + 5 * 86_400_000, t0 + 5 * 86_400_000))   # 五天后才传上来
    rid = db.query("SELECT id FROM runs")[0]["id"]
    win = scene_window(db, now_ms=t0 + 6 * 86_400_000, run=rid)
    assert win["robot"] == "B" and win["since_ms"] == t0 - 600_000
    # 补测 W6-08:操作记录里写成和导出列表一样的「机器人 · 路线」,不写「第 25 趟巡逻」
    assert win["ref"] == f"run:{rid}:B:夜巡" and win["scene"].startswith("巡逻 "), win
    assert win["until_ms"] == t0 + 86_400_000 + 600_000, "晚传上来的最多按一天算"
    db.close()


def test_接口_先问时间段_再下载_下载记操作记录(tmp_path):
    from test_site_api import _等, 站

    from nexwar_site.health import HealthDesk
    s = 站(tmp_path)
    try:
        s.api.health = HealthDesk(s.db, home=tmp_path, now_ms=s.api._now)
        tok = s.login()
        now = s.api._now()
        code, w = s.req("GET", f"/api/support-bundle/window?robot=A&from={now - 3_600_000}",
                        token=tok)
        assert code == 200 and w["robot"] == "A" and w["since_ms"] == now - 3_600_000
        assert s.req("GET", "/api/support-bundle/window?alert=nope", token=tok)[0] == 400
        assert s.req("GET", "/api/support-bundle/window?robot=../x", token=tok)[0] == 400
        import urllib.request
        r = urllib.request.Request(
            s.api.url + f"/api/support-bundle?robot=A&from={now - 3_600_000}")
        r.add_header("Authorization", f"Bearer {tok}")
        with urllib.request.urlopen(r, timeout=60) as resp:
            blob = resp.read()
        with tarfile.open(fileobj=io.BytesIO(blob)) as tf:
            assert "nexwar_support/README.md" in tf.getnames()
        r = _等(lambda: next((r for r in s.api.audit.list()
                              if r["action"].startswith("DOWNLOAD")), None))
        # 易用性第 6 轮 W6-07:对象是能拆开的引用(网页按界面语言写人话),不是一句中文
        assert r["target"].startswith("support-bundle/robot:A/"), r["target"]
    finally:
        s.close()


def test_断网一天后才收到的那批_照样按行头时刻取到(tmp_path):
    logs = RobotLogs(tmp_path)
    t0 = time.time() - 3 * 86_400
    _放一批(logs, "A", t0 + 86_400, "agent", f"{_iso(t0 + 10)} WARNING x 没到 code=0x0406\n")
    got = logs.read("A", since_s=t0, until_s=t0 + 600)
    assert "没到" in got["agent"]


def test_11_11_W6_03_这段时间没日志_写明原因不留空文件_日程记录不超出所选时段(tmp_path):
    db = SiteDB(tmp_path / "site.db")
    (tmp_path / "site.json").write_text("{}")
    now_ms = int(time.time() * 1000)
    since, until = now_ms - 3 * 3_600_000, now_ms - 2 * 3_600_000
    ldir = tmp_path / "logs"
    ldir.mkdir()
    (ldir / "site.log").write_text(f"{_iso(now_ms / 1000 - 600)} INFO nexwar_site 起来了\n")
    for at in (since - 86_400_000, since + 60_000):     # 前一天那条不该进包
        db.query("INSERT INTO schedule_runs(entry_id, scheduled_ms, outcome, decided_at) "
                 "VALUES ('e', ?, 'skip', ?)", (at, at))
    out = support_bundle(tmp_path / "b.tar.gz", home=tmp_path, db=db, health=None, now_ms=now_ms,
                         journal=lambda u, h: "", since_ms=since, until_ms=until, by="alice")
    with tarfile.open(out) as tf:
        files = {m.name.removeprefix("nexwar_support/"): tf.extractfile(m).read().decode()
                 for m in tf.getmembers()}
    for name in ("site/site.log", "site/access.log"):
        assert files[name].strip(), f"{name} 不能是空文件"
        assert "这段时间" in files[name]
    assert "最早一条" in files["site/site.log"], "写出日志从什么时候开始有"
    runs = json.loads(files["records/schedule_runs.json"])
    assert [r["scheduled_ms"] for r in runs] == [since + 60_000]
    db.close()


def test_11_11_W6_08_巡逻列表带谁派的_几个点(tmp_path):
    """liang-d5 第 6 轮 W6-08:诊断导出「按某一趟巡逻」只列 temp-1794158305644,
    看不出是哪条路线、谁派的。"""
    from nexwar_site.evidence import run_origins
    db = SiteDB(tmp_path / "site.db")
    t0 = 1_794_158_305_644
    for i, (mission, by, n, robot) in enumerate([("temp-1", "demo", 10, "A"),
                                                 ("demo-loop", "site:schedule", 4, "A"),
                                                 ("temp-1", "gina", 3, "B")]):
        pts = [{"name": f"P{k}"} for k in range(n)]
        db.query("INSERT INTO commands(command_id, task_id, robot_id, kind, payload, issued_by, "
                 "issued_at) VALUES (?,?,?,?,?,?,?)",
                 (f"c{i}", f"adhoc-{i}", robot, "patrol",
                  json.dumps({"mission": {"mission": mission, "waypoints": pts}}), by, t0 - 500))
    runs = [{"id": 1, "robot_id": "A", "mission": "temp-1", "first_ms": t0},
            {"id": 2, "robot_id": "A", "mission": "demo-loop", "first_ms": t0},
            {"id": 3, "robot_id": "C", "mission": "x", "first_ms": t0}]
    out = run_origins(db, runs)
    assert (out[0]["by"], out[0]["points"]) == ("demo", 10), "同名临时路线按机器人分开"
    assert (out[1]["by"], out[1]["points"]) == ("site:schedule", 4)
    assert "by" not in out[2], "找不到派单的:不编"
    db.close()


def test_11_11_W6_08补_去看看那趟也写谁派的_点数不算自动加的回起点(tmp_path):
    """补测:「去看看」那一趟在导出列表里是 task-60a9ef78b711;点了 3 个点的临时路线写「4 个点」
    (末尾自动加的「走回起点」也算进去了)。"""
    from nexwar_site.evidence import run_origins
    db = SiteDB(tmp_path / "site.db")
    t0 = 1_794_158_305_644
    pts = [{"name": "P1"}, {"name": "P2"}, {"name": "P3"}, {"name": "return-1"},
           {"name": "return-2"}, {"name": "start"}]
    db.query("INSERT INTO commands(command_id, task_id, robot_id, kind, payload, issued_by, "
             "issued_at) VALUES (?,?,?,?,?,?,?)",
             ("c1", "adhoc-1", "A", "patrol",
              json.dumps({"mission": {"mission": "temp-9", "waypoints": pts}}), "demo", t0 - 500))
    db.query("INSERT INTO commands(command_id, task_id, robot_id, kind, payload, issued_by, "
             "issued_at) VALUES (?,?,?,?,?,?,?)",
             ("c2", "task-60a9ef78b711", "B", "goto", json.dumps({"pose": {}}), "gina", t0 - 500))
    out = run_origins(db, [{"id": 1, "robot_id": "A", "mission": "temp-9", "first_ms": t0},
                           {"id": 2, "robot_id": "B", "mission": "task-60a9ef78b711",
                            "first_ms": t0}])
    assert out[0]["points"] == 3
    assert (out[1]["by"], out[1]["kind"]) == ("gina", "goto")
    db.close()


def test_11_11_W6_03补_机器人那边这段时间没日志_写明原因():
    """补测:robots/<id>/live/*.log 只有一行 -- No entries --,没写为什么。"""
    from nexwar_site.health import robot_live_log
    for empty in ("", "-- No entries --\n", "  "):
        t = robot_live_log("A", "nexwar_agent", empty, 3)
        assert "No entries" not in t and "A" in t and "nexwar_agent" in t and "3 小时" in t
        assert "robots/A/logs/" in t and "{" not in t, "复核:少了 f 前缀,写成字面的 {robot}"
    assert robot_live_log("A", "nexwar_agent", "x 1\n", 3) == "x 1\n"


def test_11_11_W6_03补_诊断包说明用报警_巡逻_报警标题跟列表一样(tmp_path):
    """补测:README 里的报警标题和列表里不一样,还在用「告警 / 巡检」。"""
    db = SiteDB(tmp_path / "site.db")
    db.query("INSERT INTO alerts(key, kind, level, robot, title, detail, first_ms, last_ms, count, "
             "acked_by, resolved_by, escalated, context) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
             ("A/disk_80#1", "disk_80", "P2", "A", "机器人的发件箱所在的盘即将写满", "",
              1_790_000_000_000, 1_790_000_000_000, 1, "", "", 0, "{}"))
    win = scene_window(db, now_ms=1_790_000_100_000, alert="A/disk_80#1")
    assert "机器人存储空间不足" in win["scene"] and "发件箱" not in win["scene"], win["scene"]
    from nexwar_site.health import _readme
    text = _readme({}, since="a", until="b", scene=win["scene"], robot="A", task=None, by="x",
                   now="n")
    assert "告警" not in text and "巡检" not in text, text
    db.close()


def test_minor19_回原点回待命点那趟写人话_README场景行不露编号(tmp_path):
    """liang-d5 W6 补测:问题包列表里「回原点」那趟是 standby-3cf9d8fb1ceb;README 场景行写
    「巡逻 temp-1794…」。"""
    from nexwar_site.evidence import run_origins
    db = SiteDB(tmp_path / "site.db")
    t0 = 1_794_158_305_644
    tgt = {"map_id": "m", "map_version": "7", "frame_id": "map", "yaw": 0.0}
    db.query("INSERT INTO homes(robot_id, map_id, map_version, name, x, y, yaw) "
             "VALUES ('A','m','7','home',1.0,2.0,0.0)")
    # 第 10 轮 A10-01:回原点认任务号 standby-home-…(以前按目标点认:待命点设在原点上的,自动回待命点
    # 也被写成回原点,列表和详情对不上)
    for i, (task, x, y) in enumerate([("standby-home-aaa", 1.05, 2.0), ("standby-bbb", 1.05, 2.0)]):
        db.query("INSERT INTO commands(command_id, task_id, robot_id, kind, payload, issued_by, "
                 "issued_at) VALUES (?,?,?,?,?,?,?)",
                 (f"c{i}", task, "A", "goto", json.dumps({"target": {**tgt, "x": x, "y": y}}),
                  "demo", t0 - 500))
    db.query("INSERT INTO commands(command_id, task_id, robot_id, kind, payload, issued_by, "
             "issued_at) VALUES ('c9','adhoc-9','A','patrol',?,'gina',?)",
             (json.dumps({"mission": {"mission": "temp-9", "waypoints": [{"name": "P1"},
                                                                          {"name": "P2"}]}}),
              t0 - 500))
    out = run_origins(db, [{"id": 1, "robot_id": "A", "mission": "standby-home-aaa",
                            "first_ms": t0},
                           {"id": 2, "robot_id": "A", "mission": "standby-bbb", "first_ms": t0}])
    assert (out[0]["by"], out[0]["kind"]) == ("demo", "home")
    assert out[1]["kind"] == "standby"
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(t0 / 1000))
    for mission in ("temp-9", "standby-home-aaa"):
        db.query("INSERT INTO runs(robot_id, mission, stamp, first_ms, last_ms) VALUES (?,?,?,?,?)",
                 ("A", mission, stamp, t0, t0))
    ids = [r["id"] for r in db.query("SELECT id FROM runs ORDER BY id")]
    assert scene_window(db, now_ms=t0 + 1000, run=ids[0])["scene"].startswith("临时路线 2 个点 ")
    assert scene_window(db, now_ms=t0 + 1000, run=ids[1])["scene"].startswith("回原点 ")
    db.close()


def test_第10轮_A10_01_记录带任务号_被接替_正在跑(tmp_path):
    """liang-d5 第 10 轮 A10-01:App 记录里正在跑的、被接替的都写「没跑完」。"""
    from nexwar_site.evidence import run_origins
    db = SiteDB(tmp_path / "site.db")
    t0 = 1_794_158_305_644
    for i, task in enumerate(("adhoc-1", "adhoc-2", "adhoc-3")):
        db.query("INSERT INTO commands(command_id, task_id, robot_id, kind, payload, issued_by, "
                 "issued_at) VALUES (?,?,?,?,?,?,?)",
                 (f"c{i}", task, "AB"[i % 2], "patrol",
                  json.dumps({"mission": {"mission": f"r{i}", "waypoints": []}}), "demo",
                  t0 - 500))
    db.query("INSERT INTO events(robot_id, boot_id, seq, event_id, kind, data, stamp, received_at) "
             "VALUES ('A','b',1,'e1','task_preempted',?,?,?)",
             (json.dumps({"task_id": "adhoc-1"}), t0 + 10, t0 + 10))
    runs = [{"id": 1, "robot_id": "A", "mission": "r0", "first_ms": t0, "finished": False},
            {"id": 2, "robot_id": "B", "mission": "r1", "first_ms": t0, "finished": False},
            {"id": 3, "robot_id": "A", "mission": "r2", "first_ms": t0, "finished": False}]
    out = run_origins(db, runs, current={"B": "adhoc-2", "A": "something-else"})
    assert out[0]["task_id"] == "adhoc-1" and out[0]["ended"] == "preempted"
    assert out[0].get("running") is not True
    assert out[1]["running"] is True, "机器人现在跑的就是这一趟"
    assert out[2].get("running") is not True and "ended" not in out[2], "没收尾、也不在跑:照旧"
    db.close()
