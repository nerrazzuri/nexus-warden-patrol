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
    assert "alice" in readme and "告警 A/stuck#1" in readme
    assert "`0x0406`" in readme and "`0x0216`" in readme and "机器人被困住" in readme
    db.close()


def test_场景找不到_时间段太长_都拒(tmp_path):
    db = SiteDB(tmp_path / "site.db")
    with pytest.raises(ValueError, match="没有这条告警"):
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
        assert "support-bundle/机器人 A" in r["target"] + r["action"]
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
