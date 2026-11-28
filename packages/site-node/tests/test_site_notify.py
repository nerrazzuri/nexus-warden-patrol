"""1.1-2 告警外发:WhatsApp / Telegram / 邮件 / webhook。跟告警同一个事务排队;按级别、渠道;只发文字;
确认了、解决了的不发;发不出去退避,连续 10 分钟报 P2,发出去自动解决;每小时上限;令牌加密、只进不出;
接口只给管理员。"""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import timezone

import pytest
from test_site_api import PW, 站

from nexwar_site import notify
from nexwar_site.alert_store import AlertDesk
from nexwar_site.db import SiteDB
from nexwar_site.notify import NotifyDesk, NotifyError, SendError
from nexwar_site.sealbox import PREFIX, SealBox, load_or_create_key

NOW = 1_800_000_000_000


class 假发:
    def __init__(self):
        self.sent, self.fail = [], None

    def send(self, ch, msg, alert):
        if self.fail:
            raise SendError(self.fail)
        self.sent.append((ch["name"], ch["secret"], msg, alert))


@pytest.fixture
def 台(tmp_path):
    clock = [NOW]
    db = SiteDB(tmp_path / "s.db")
    db.sealbox = SealBox(load_or_create_key(tmp_path / "keys" / "secrets.key"))
    desk = AlertDesk(db, now_ms=lambda: clock[0])
    f = 假发()
    n = NotifyDesk(db, now_ms=lambda: clock[0], sender=f, site_name="Palm Estate",
                   tz=lambda: timezone.utc)
    n.alerts = desk
    yield desk, n, f, clock, db
    db.close()


def _tg(n, **kw):
    d = {"kind": "telegram", "name": "主管群", "targets": ["-1001234567"], "secret": "123:abc"}
    d.update(kw)
    return n.save(d)


def _队(db):
    return [dict(r) for r in db.query("SELECT * FROM notify_outbox ORDER BY id")]


def test_P1排队_P2只进勾了P2的渠道_升档再排_外发失败那条不外发(台):
    desk, n, f, clock, db = 台
    a = _tg(n)
    b = _tg(n, name="经理", levels=["P1", "P2"])
    desk.raise_alert(kind="stuck", robot="A", title="机器人卡住了")
    desk.raise_alert(kind="evidence_plain", robot="A", title="机器人上未加密")      # P2
    q = _队(db)
    assert [(r["channel_id"], r["tier"]) for r in q] == [(a["id"], 0), (b["id"], 0), (b["id"], 0)]
    desk.raise_alert(kind="stuck", robot="A", title="机器人卡住了")
    assert len(_队(db)) == 3, "同一条同一档不重排"
    clock[0] += 3 * 60_000
    desk.escalate()
    assert {r["tier"] for r in _队(db)} == {0, 1}, "无人确认、升档:再发一次"
    before = len(_队(db))
    desk.raise_alert(kind="notify_failed", robot="site", title="告警外发发不出去")
    assert len(_队(db)) == before


def test_只发文字_英文按种类翻译_中文用站点原文_升档写仍未确认(台):
    desk, n, f, clock, db = 台
    _tg(n)
    _tg(n, name="中文群", lang="zh")
    desk.raise_alert(kind="intrusion_person", robot="R1", title="确认有人入侵:东门",
                     context={"pose": {"x": 3.0, "y": 4.0}})
    n.tick()
    (_, sec, en, al), (_, _, zh, _) = f.sent
    assert sec == "123:abc", "发的时候才解开"
    assert en["head"] == "Palm Estate · P1: Intruder confirmed"
    assert "Robot: R1" in en["body"] and "2027-01-15" in en["body"]
    assert zh["head"] == "Palm Estate · P1:确认有人入侵:东门"
    assert "3.0" not in en["body"] + zh["body"], "不带位置"
    assert al["level"] == "P1" and al["kind"] == "intrusion_person"
    n.tick()
    assert len(f.sent) == 2, "发过的不再发"
    m = notify.message(site="S", level="P1", kind="stuck", title="x", robot="R", ms=NOW,
                       tz=timezone.utc, tier=1, lang="en")
    assert "still not acknowledged" in m["head"]


def test_确认了不发_发不出去退避_十分钟报P2_发出去自动解决(台):
    desk, n, f, clock, db = 台
    _tg(n)
    k = desk.raise_alert(kind="stuck", robot="A", title="卡住").key
    desk.ack(k, who="gina")
    n.tick()
    assert f.sent == [] and _队(db)[0]["dropped"] == "已有人确认或解决了"
    desk.raise_alert(kind="fallen", robot="A", title="摔倒")
    f.fail = "连不上:no route"
    n.tick()
    r = _队(db)[1]
    assert r["attempts"] == 1 and r["next_ms"] == NOW + 10_000
    assert n.channels()[0]["last_error"].startswith("连不上")
    clock[0] += 11 * 60_000
    n.tick()
    assert [a for a in desk.book.open() if a.kind == "notify_failed"]
    f.fail = None
    clock[0] += 10 * 60_000
    n.tick()
    assert len(f.sent) == 1
    assert not [a for a in desk.book.open() if a.kind == "notify_failed"]


def test_每小时上限(台, monkeypatch):
    desk, n, f, clock, db = 台
    monkeypatch.setattr(notify, "HOURLY_CAP", 2)
    _tg(n)
    for i in range(3):
        desk.raise_alert(kind="stuck", robot=f"R{i}", title="卡住")
    n.tick()
    assert len(f.sent) == 2 and "一小时已发 2 条" in _队(db)[2]["dropped"]


def test_渠道校验_令牌加密_改的时候不给令牌就不变(台):
    desk, n, f, clock, db = 台
    with pytest.raises(NotifyError, match="令牌"):
        n.save({"kind": "telegram", "name": "x", "targets": ["-100"]})
    with pytest.raises(NotifyError, match="国家码"):
        n.save({"kind": "whatsapp", "name": "x", "targets": ["0123"], "secret": "t",
                "config": {"phone_number_id": "123456", "template": "nw_alert"}})
    with pytest.raises(NotifyError, match="模板"):
        n.save({"kind": "whatsapp", "name": "x", "targets": ["+60123456789"], "secret": "t",
                "config": {"phone_number_id": "123456"}})
    with pytest.raises(NotifyError, match="SMTP"):
        n.save({"kind": "email", "name": "x", "targets": ["a@b.com"]})
    with pytest.raises(NotifyError, match="http"):
        n.save({"kind": "webhook", "name": "x", "targets": ["ftp://x"]})
    ch = _tg(n)
    raw = db.query("SELECT secret FROM notify_channels")[0]["secret"]
    assert raw.startswith(PREFIX) and "abc" not in raw
    assert "secret" not in ch and ch["has_secret"] is True
    n.save({"name": "改名了", "enabled": False}, cid=ch["id"])
    assert n._channel(ch["id"])["secret"] == "123:abc"
    assert n.channels()[0]["name"] == "改名了" and n.channels()[0]["enabled"] is False
    desk.raise_alert(kind="stuck", robot="A", title="卡住")
    assert _队(db) == [], "停用的渠道不排"


def test_站点没配密钥_不收要令牌的渠道(tmp_path):
    n = NotifyDesk(SiteDB(tmp_path / "s.db"), now_ms=lambda: 1, sender=假发())
    with pytest.raises(NotifyError, match="密钥"):
        n.save({"kind": "telegram", "name": "x", "targets": ["-100"], "secret": "t"})
    n.save({"kind": "webhook", "name": "x", "targets": ["https://hook.example/a"]})


def test_真发的报文(monkeypatch):
    got = []
    monkeypatch.setattr(notify, "_post_json", lambda url, body, headers=None:
                        got.append((url, body, headers or {})))
    s = notify.Sender()
    msg = notify.message(site="S", level="P1", kind="fallen", title="摔倒", robot="R1", ms=NOW,
                         tz=timezone.utc, tier=0, lang="en")
    al = {"site": "S", "key": "R1/fallen#1", "level": "P1", "kind": "fallen", "robot": "R1",
          "ms": NOW, "tier": 0}
    s.send({"kind": "telegram", "secret": "9:x", "targets": ["-1", "-2"], "config": {}}, msg, al)
    assert [g[0] for g in got] == ["https://api.telegram.org/bot9:x/sendMessage"] * 2
    assert got[0][1]["chat_id"] == "-1" and got[0][1]["text"].startswith("S · P1: Robot fell over")
    got.clear()
    s.send({"kind": "whatsapp", "secret": "tok", "targets": ["+60123456789"],
            "config": {"phone_number_id": "555", "template": "nw_alert", "template_lang": "en"}},
           msg, al)
    url, body, h = got[0]
    assert url.endswith("/555/messages") and h["Authorization"] == "Bearer tok"
    assert body["to"] == "60123456789" and body["template"]["name"] == "nw_alert"
    assert [p["text"] for p in body["template"]["components"][0]["parameters"]] == [
        "S · P1: Robot fell over", "R1", msg["when"]]
    got.clear()
    s.send({"kind": "webhook", "secret": "k", "targets": ["https://h/x"], "config": {}}, msg, al)
    url, body, h = got[0]
    raw = json.dumps(body, ensure_ascii=False).encode()
    assert h["X-Nexwar-Signature"] == hmac.new(b"k", raw, hashlib.sha256).hexdigest()
    assert body["alert_key"] == "R1/fallen#1" and body["level"] == "P1"


@pytest.fixture
def 站点(tmp_path):
    s = 站(tmp_path)
    s.db.sealbox = SealBox(load_or_create_key(tmp_path / "keys" / "secrets.key"))
    s.api.notify = NotifyDesk(s.db, now_ms=lambda: NOW, sender=假发(), site_name="S")
    s.accounts.add("gina", PW, role="guard")
    yield s
    s.close()


def _登(s, name: str) -> str:
    code, d = s.req("POST", "/api/login", {"name": name, "password": PW})
    assert code == 200, d
    return d["token"]


def test_接口_管理员加改测删_保安不行_令牌不出来_审计不记令牌(站点):
    s = 站点
    alice, gina = _登(s, "alice"), _登(s, "gina")
    body = {"kind": "telegram", "name": "主管群", "targets": ["-1001"], "secret": "77:sekret"}
    assert s.req("POST", "/api/notify", body, token=gina)[0] == 403
    assert s.req("GET", "/api/notify", token=gina)[0] == 403
    code, ch = s.req("POST", "/api/notify", body, token=alice)
    assert code == 200 and ch["has_secret"] and "sekret" not in json.dumps(ch)
    code, d = s.req("GET", "/api/notify", token=alice)
    assert code == 200 and d["channels"][0]["name"] == "主管群" and d["sealed"] is True
    assert "sekret" not in json.dumps(d)
    code, r = s.req("POST", f"/api/notify/{ch['id']}/test", token=alice)
    assert code == 200 and r["ok"] is True
    code, d = s.req("POST", f"/api/notify/{ch['id']}", {"levels": ["P1", "P2"]}, token=alice)
    assert code == 200 and d["levels"] == ["P1", "P2"]
    code, d = s.req("POST", "/api/notify", {"kind": "telegram", "name": "x"}, token=alice)
    assert code == 400
    code, d = s.req("POST", f"/api/notify/{ch['id']}/remove", token=alice)
    assert code == 200 and d["channels"] == []
    assert s.req("POST", "/api/notify/999/test", token=alice)[0] == 404
    rows = [r for r in s.api.audit.list() if "/api/notify" in r["action"]]
    assert rows and "sekret" not in json.dumps([dict(r) for r in rows], ensure_ascii=False)


def test_外审1_1_第6条_部分收件人失败_只重发没发到的_上限按发出去过算(台, monkeypatch):
    desk, n, f, clock, db = 台
    got, bad = [], {"-2"}

    def post(url, body, headers=None):
        if body["chat_id"] in bad:
            raise SendError("HTTP 502:bad gateway")
        got.append(body["chat_id"])
    monkeypatch.setattr(notify, "_post_json", post)
    n.sender = notify.Sender()
    _tg(n, targets=["-1", "-2", "-3"])
    desk.raise_alert(kind="stuck", robot="R1", title="卡住")
    n.tick()
    assert got == ["-1"]
    row = _队(db)[0]
    assert row["done"] == "-1" and row["first_sent_ms"] == NOW and row["sent_ms"] is None
    bad.clear()
    clock[0] += 3600_000
    n.tick()
    assert got == ["-1", "-2", "-3"], "-1 不再收第二遍"
    assert _队(db)[0]["sent_ms"] is not None


def test_外审1_1_第6条_发到一半的也算进每小时上限(台, monkeypatch):
    desk, n, f, clock, db = 台
    monkeypatch.setattr(notify, "HOURLY_CAP", 1)

    def post(url, body, headers=None):
        if body["chat_id"] == "-2":
            raise SendError("HTTP 502")
    monkeypatch.setattr(notify, "_post_json", post)
    n.sender = notify.Sender()
    _tg(n, targets=["-1", "-2"])
    desk.raise_alert(kind="stuck", robot="R1", title="卡住")
    n.tick()
    desk.raise_alert(kind="stuck", robot="R2", title="卡住")
    n.tick()
    assert "一小时已发 1 条" in _队(db)[1]["dropped"]


def test_外审1_1_第7条_对方回的错误里的令牌抹掉(台, monkeypatch):
    desk, n, f, clock, db = 台
    tok = "123456:ABCDEFGHIJKLMNOPQRSTUVWXYZ_abcdef"

    def post(url, body, headers=None):
        raise SendError(f"HTTP 404:no route {url} access_token=xyz Bearer {tok}")
    monkeypatch.setattr(notify, "_post_json", post)
    n.sender = notify.Sender()
    ch = _tg(n, secret=tok)
    desk.raise_alert(kind="stuck", robot="R1", title="卡住")
    n.tick()
    r = n.send_test(ch["id"])
    rows = _队(db)
    for text in (rows[0]["error"], r["error"], n.channels()[0]["last_error"]):
        assert tok not in text and "xyz" not in text and "***" in text, text
    assert notify.scrub("https://api.telegram.org/bot9:" + "a" * 30 + "/send") \
        == "https://api.telegram.org/***/send"
