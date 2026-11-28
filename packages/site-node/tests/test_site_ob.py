"""1.1-5 电子值班簿 + 事件报告。

- 手写的只追加:写错了另写一条更正,列出来时原来那条标「已更正」;补记最多 24 小时前,不能写到将来。
- 一本里自动带上报警(报、确认、关、结论)、机器人巡检、外部报警器、交班留言,按时间排。
- 作者取登录账号;保安能写,只读账号只能看;写了、打印了进审计。
- 能打印的网页:值班簿一页、一条报警一页(经过、到场、喊话、值班簿里关于它的、结论、照片嵌在里面)。
"""

from __future__ import annotations

import time
import urllib.error
import urllib.request
from datetime import timezone
from urllib.parse import quote

import pytest
from test_site_api import PW, 站

from nexwar_site.db import SiteDB
from nexwar_site.ob import ObError, OccurrenceBook, incident_report, report_html


def _now():
    return int(time.time() * 1000)


@pytest.fixture
def 站点(tmp_path):
    s = 站(tmp_path, alerts=True)
    s.accounts.add("gina", PW, role="guard")
    s.accounts.add("vic", PW, role="viewer")
    yield s
    s.close()


def _登(s, name):
    code, d = s.req("POST", "/api/login", {"name": name, "password": PW})
    assert code == 200, d
    return d["token"]


async def _sync(fn, *a, **kw):
    return fn(*a, **kw)


def _html(s, path, tok):
    r = urllib.request.Request(s.api.url + path)
    r.add_header("Authorization", f"Bearer {tok}")
    try:
        with urllib.request.urlopen(r, timeout=15) as resp:
            return resp.status, resp.headers.get("Content-Type"), resp.read().decode()
    except urllib.error.HTTPError as exc:
        return exc.code, None, ""


def test_手写只追加_更正另写一条_补记最多24小时(tmp_path):
    now = [10 * 86_400_000]
    ob = OccurrenceBook(SiteDB(tmp_path / "s.db"), now_ms=lambda: now[0])
    a = ob.add("gina", {"category": "visitor", "text": "  送货车 WXY 1234 进 "})
    assert a["text"] == "送货车 WXY 1234 进" and a["author"] == "gina" and a["at_ms"] == now[0]
    b = ob.add("gina", {"category": "visitor", "text": "车牌是 WXY 1243", "corrects": a["id"]})
    late = ob.add("gina", {"category": "patrol", "text": "北区围栏查过",
                           "at_ms": now[0] - 3600_000})
    assert late["written_ms"] == now[0]
    for bad in ({"category": "x", "text": "a"}, {"category": "other", "text": " "},
                {"category": "other", "text": "a" * 1001},
                {"category": "other", "text": "a", "at_ms": now[0] - 25 * 3600_000},
                {"category": "other", "text": "a", "at_ms": now[0] + 120_000},
                {"category": "other", "text": "a", "corrects": 999}, [1]):
        with pytest.raises(ObError):
            ob.add("gina", bad)
    book = ob.book(now[0] - 86_400_000, now[0] + 1)["entries"]
    assert [e["id"] for e in book] == [late["id"], a["id"], b["id"]]
    assert book[1]["corrected_by"] == b["id"] and book[2]["corrects"] == a["id"]
    with pytest.raises(ObError):
        ob.book(now[0], now[0] - 1)


def test_一本里自动带上报警_确认_关_结论_交班留言_按时间排_中英文(站点):
    s = 站点
    gina, vic = _登(s, "gina"), _登(s, "vic")
    t0 = _now()
    a = s.loop.call(lambda: _sync(s.desk.raise_alert, kind="intrusion", robot="A",
                                  title="北区有人闯入"))
    k = quote(a.key, safe="")
    assert s.req("POST", f"/api/alerts/{k}/ack", {}, token=gina)[0] == 200
    code, d = s.req("POST", "/api/ob", {"category": "incident", "text": "到北区看了,是猫",
                                        "alert": a.key, "author": "mallory"}, token=gina)
    assert code == 200 and d["entry"]["author"] == "gina"
    assert s.req("POST", f"/api/alerts/{k}/resolve", {"verdict": "false_alarm"},
                 token=gina)[0] == 200
    s.req("POST", "/api/shift-notes", {"text": "北区东边的灯坏了"}, token=gina)
    assert s.req("POST", "/api/ob", {"category": "other", "text": "x"}, token=vic)[0] == 403
    code, d = s.req("GET", f"/api/ob?since={t0 - 1000}&until={_now() + 1000}&lang=zh", token=vic)
    assert code == 200
    got = [(e["source"], e["text"]) for e in d["entries"]]
    assert ("alarm", "P1 北区有人闯入") in got
    assert ("alarm", "确认:P1 北区有人闯入") in got
    assert ("alarm", "关闭:P1 北区有人闯入(误报)") in got
    assert ("manual", "到北区看了,是猫") in got and ("handover", "北区东边的灯坏了") in got
    assert [e["at_ms"] for e in d["entries"]] == sorted(e["at_ms"] for e in d["entries"])
    code, d = s.req("GET", f"/api/ob?since={t0 - 1000}&until={_now() + 1000}", token=vic)
    assert ("alarm", "Closed: P1 北区有人闯入 (false alarm)") in \
        [(e["source"], e["text"]) for e in d["entries"]]
    assert s.req("GET", "/api/ob?since=x", token=vic)[0] == 400
    acts = [r["action"] for r in s.api.audit.list() if r["actor"] == "gina"]
    assert "POST /api/ob" in acts


def test_能打印的值班簿和事件报告(站点):
    s = 站点
    gina = _登(s, "gina")
    t0 = _now()
    a = s.loop.call(lambda: _sync(s.desk.raise_alert, kind="intrusion", robot="A",
                                  title="北区有人闯入<script>"))
    k = quote(a.key, safe="")
    s.req("POST", f"/api/alerts/{k}/arrive", {}, token=gina)
    s.req("POST", "/api/ob", {"category": "incident", "text": "到北区看了,是猫", "alert": a.key},
          token=gina)
    code, mime, page = _html(s, f"/api/ob/print?since={t0 - 1000}&until={_now() + 1000}&lang=zh",
                             gina)
    assert code == 200 and mime.startswith("text/html")
    assert "值班簿" in page and "到北区看了,是猫" in page and "接班人签名" in page
    assert "&lt;script&gt;" in page and "<script>" not in page
    code, mime, page = _html(s, f"/api/alerts/{k}/report?lang=zh", gina)
    assert code == 200 and "事件报告" in page and "保安到场" in page and "到北区看了,是猫" in page
    assert "&lt;script&gt;" in page and "<script>" not in page, "标题里的东西要转义"
    assert "window.print()" in page
    assert _html(s, "/api/alerts/nope/report", gina)[0] == 404
    assert any(r["action"] == "VIEW" and "report" in str(r.get("target"))
               for r in s.api.audit.list())


def test_事件报告带那段时间的照片_嵌进页面(tmp_path):
    db = SiteDB(tmp_path / "s.db")
    with db.tx() as c:
        c.execute("INSERT INTO alerts(key, level, kind, robot, title, detail, first_ms, last_ms,"
                  " count, acked_by, acked_ms, resolved_by, resolved_ms, escalated, context,"
                  " verdict)"
                  " VALUES ('k1','P1','dog_sees_person','A','看见人','',1000,2000,2,'',NULL,'gina',"
                  "5000,0,'{\"last_seen\": {\"map_id\": \"m\", \"x\": 1.5, \"y\": 2}}','intruder')")
    asked = []

    def photos(robot, a, b):
        asked.append((robot, a, b))
        return [("10:00:01 · persons · P1.jpg", b"\xff\xd8jpeg")] * 10
    rep = incident_report(db, "k1", lang="en", photos=photos)
    assert asked == [("A", 1000 - 60_000, 5000 + 600_000)]
    assert len(rep["photos"]) == 8
    page = report_html(rep, site="Estate", tz=timezone.utc, lang="en")
    assert page.count("data:image/jpeg;base64,") == 8
    assert "Closed (real intrusion)" in page and "x=1.5 y=2.0" in page
    assert "Last raised (2 times)" in page
    with pytest.raises(KeyError):
        incident_report(db, "nope", lang="en")


def test_外审1_1_第13条_更正跟着原来那条的报警_报告标出更正_更正过的不能再更正(tmp_path):
    db = SiteDB(tmp_path / "s.db")
    now = [10 * 86_400_000]
    with db.tx() as c:
        c.execute("INSERT INTO alerts(key, level, kind, robot, title, detail, first_ms, last_ms,"
                  " count, acked_by, acked_ms, resolved_by, resolved_ms, escalated, context,"
                  " verdict) VALUES ('k1','P1','intrusion','A','闯入','',?,?,1,'',NULL,'',NULL,0,"
                  "'{}','')", (now[0] - 5000, now[0] - 5000))
    ob = OccurrenceBook(db, now_ms=lambda: now[0])
    a = ob.add("gina", {"category": "incident", "text": "是狗", "alert": "k1", "robot": "A"})
    b = ob.add("gina", {"category": "incident", "text": "是猫", "corrects": a["id"]})
    assert (b["alert_key"], b["robot"]) == ("k1", "A"), "不带 alert 也跟着原来那条"
    with pytest.raises(ObError, match="已经更正过了"):
        ob.add("gina", {"category": "incident", "text": "是鸟", "corrects": a["id"]})
    steps = [s[2] for s in incident_report(db, "k1", lang="zh")["steps"]]
    assert any(f"#{a['id']} " in x and "是狗" in x and f"已由 #{b['id']} 更正" in x for x in steps)
    assert any(f"#{b['id']} 更正 #{a['id']}" in x and "是猫" in x for x in steps)


def test_外审1_1_第2轮_12_13_两人同时更正只成一个_更正不能改挂别的报警(tmp_path):
    import threading
    db = SiteDB(tmp_path / "s.db")
    now = [10 * 86_400_000]
    ob = OccurrenceBook(db, now_ms=lambda: now[0])
    a = ob.add("gina", {"category": "incident", "text": "原文", "alert": "k1", "robot": "A"})
    with pytest.raises(ObError, match="不能改挂"):
        ob.add("gina", {"category": "incident", "text": "改", "corrects": a["id"], "alert": "k2"})
    with pytest.raises(ObError, match="不能改挂"):
        ob.add("gina", {"category": "incident", "text": "改", "corrects": a["id"], "robot": "B"})
    ok = ob.add("gina", {"category": "incident", "text": "改", "corrects": a["id"], "alert": "k1"})
    assert ok["alert_key"] == "k1", "跟原来一样的照收"
    c = ob.add("gina", {"category": "incident", "text": "再一条", "robot": "A"})
    go = threading.Barrier(8)
    res: list = []

    def one(i):
        go.wait()
        try:
            res.append(ob.add(f"g{i}", {"category": "incident", "text": f"更{i}",
                                        "corrects": c["id"]})["id"])
        except ObError as exc:
            res.append(str(exc))
    ts = [threading.Thread(target=one, args=(i,)) for i in range(8)]
    for t in ts:
        t.start()
    for t in ts:
        t.join(10)
    assert sum(isinstance(r, int) for r in res) == 1, res
    assert len(db.query("SELECT 1 FROM ob_entries WHERE corrects=?", (c["id"],))) == 1
    db.close()


def test_事件报告按拍摄时刻取照片_断网补传的旧照片不混进来_晚到的现场照片不漏(tmp_path):
    """外审 1.1 第 10 轮:原来按收齐时刻(done_ms)筛 —— 一小时前拍、现在才补传的照片混进这次事件,
    事件当时拍、20 分钟后才传上来的现场照片反而漏掉。"""
    from datetime import datetime

    from nexwar_site.sitetime import site_tz
    s = 站(tmp_path, alerts=True, runs={})
    try:
        s.accounts.add("gina", PW, role="guard")
        gina = _登(s, "gina")
        a = s.loop.call(lambda: _sync(s.desk.raise_alert, kind="intrusion", robot="A",
                                      title="北区有人闯入"))
        t = s.db.query("SELECT first_ms FROM alerts WHERE key=?", (a.key,))[0]["first_ms"]

        def st(ms):
            return datetime.fromtimestamp(ms / 1000, timezone.utc).strftime("%Y%m%dT%H%M%SZ")

        def 传(run, name):
            data = b"\xff\xd8" + name.encode()
            s.store.put("A", run, f"photos/{name}", offset=0, data=data, total=len(data))
        old = f"P1__front__{st(t - 3600_000)}.jpg"           # 一小时前拍的,现在才补传
        scene = f"P2__front__{st(t + 5000)}.jpg"             # 事件当时拍的
        传(f"巡检一/{st(t - 3700_000)}", old)
        传(f"巡检二/{st(t - 1000)}", scene)
        with s.db.tx() as c:                                 # 现场那张 20 分钟后才收齐
            c.execute("UPDATE run_photos SET done_ms=? WHERE name=?", (t + 1200_000, scene))
        code, _, page = _html(s, f"/api/alerts/{quote(a.key, safe='')}/report?lang=zh", gina)
        assert code == 200
        assert scene in page, "事件当时拍的照片晚到了也要在报告里"
        assert old not in page, "一小时前拍的不该混进来"
        when = datetime.fromtimestamp((t + 5000) // 1000, site_tz(s.db)).strftime("%H:%M:%S")
        assert f"{when} · 巡检二 · {scene}" in page, "标拍摄时刻,不标收齐时刻"
    finally:
        s.close()
