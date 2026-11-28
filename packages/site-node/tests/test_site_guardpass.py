"""1.1-1 第 4 步:机器人报的脸认出来 → 记「保安经过」+ P3;5 分钟内同一人同一台同一防区并成一笔;
认不出、格式不对的不记;接口:管理员看所有人、保安只看自己的,看了进审计;撤销同意一起删;留 90 天。"""

from __future__ import annotations

import pytest
from test_site_api import PW, 站
from test_site_faces import _照, 假引擎

from nexwar_site.db import SiteDB
from nexwar_site.faces import FaceBook
from nexwar_site.guardpass import KEEP_MS, MERGE_MS, GuardPasses
from nexwar_site.sealbox import SealBox, load_or_create_key


def _脸(n: int) -> list[float]:
    return [1.0 if i == n else 0.0 for i in range(128)]


class _台:
    def __init__(self):
        self.raised = []

    def raise_alert(self, **kw):
        self.raised.append(kw)


@pytest.fixture
def 记(tmp_path):
    db = SiteDB(tmp_path / "site.db")
    db.sealbox = SealBox(load_or_create_key(tmp_path / "keys" / "secrets.key"))
    now = [1_800_000_000_000]
    faces = FaceBook(db, now_ms=lambda: now[0], engine=假引擎())
    faces.add_photo("gina", consent=True, jpeg_b64=_照("face:3"))
    faces.add_photo("hugo", consent=True, jpeg_b64=_照("face:7"))
    zone = {"z": "B区"}
    desk = _台()
    gp = GuardPasses(db, now_ms=lambda: now[0], faces=faces, desk=desk,
                     zone_of=lambda rid: zone["z"])
    return gp, desk, now, zone


def test_认出来记一笔出P3_五分钟内并成一笔_换防区另记(记):
    gp, desk, now, zone = 记
    assert gp.faces_seen("A", [{"feat": _脸(3), "dist_m": 2.4}, {"feat": _脸(50)}]) == ["gina"]
    [a] = desk.raised
    assert a["kind"] == "guard_passed" and a["title"] == "登记过的保安经过 B区"
    assert "gina" not in repr(a), "外审 1.1 #2:P3 谁都看得见,不写是谁"
    assert "人脸认出,约 2.4 m" in a["detail"] and a["context"]["zone"] == "B区"
    assert a["record"] == "site:guard_passed", "只记一笔,不推送"
    now[0] += MERGE_MS - 1000
    gp.faces_seen("A", [{"feat": _脸(3)}])
    assert len(desk.raised) == 1, "5 分钟内并成一笔"
    zone["z"] = "C区"
    gp.faces_seen("A", [{"feat": _脸(3)}, {"feat": _脸(7)}])
    assert [r["title"] for r in desk.raised[1:]] == ["登记过的保安经过 C区"] * 2
    got = gp.list(since=0, until=now[0] + 1)["passes"]
    b = [p for p in got if p["zone"] == "B区"][0]
    assert b["n"] == 2 and b["account"] == "gina" and b["how"] == "face"
    assert [p["account"] for p in gp.list(since=0, until=now[0] + 1, account="hugo")["passes"]] \
        == ["hugo"]


def test_格式不对_认不出_不记(记):
    gp, desk, *_ = 记
    for bad in (None, "x", [{"feat": [1.0] * 5}], [{"feat": _脸(3)[:-1] + [float("nan")]}],
                [{"feat": [True] * 128}], [{"feat": _脸(60)}]):
        assert gp.faces_seen("A", bad) == []
    assert desk.raised == []


def test_外审1_1_第4条_到期不靠下一次认人_读的时候也不给(记):
    gp, desk, now, _ = 记
    gp.faces_seen("A", [{"feat": _脸(3)}])
    now[0] += KEEP_MS + 1
    assert gp.list(since=0, until=now[0] + 1)["passes"] == []
    gp._pruned = 0
    gp.tick()
    assert gp.db.query("SELECT COUNT(*) AS n FROM guard_passes")[0]["n"] == 0


def test_外审1_1_第1条_人脸特征值不落事件表_不进事件流_回调拿到原样():
    from nexwar_contract.messages import Event
    from nexwar_site.dispatcher import private_view
    e = Event(event_id="f1", seq=1, boot_id="b", stamp=1, kind="face_seen",
              data={"faces": [{"feat": _脸(3), "dist_m": 2.0}, {"feat": _脸(4)}]})
    v = private_view(e)
    assert v.data == {"faces": 2, "dist_m": [2.0, None], "redacted": True}
    assert "feat" not in str(v.to_wire()) and e.data["faces"][0]["feat"] == _脸(3)
    other = Event(event_id="x", seq=2, boot_id="b", stamp=1, kind="deter", data={"a": 1})
    assert private_view(other) is other


def test_留90天_撤销同意一起删(记):
    gp, desk, now, _ = 记
    gp.faces_seen("A", [{"feat": _脸(3)}])
    gp.faces_seen("A", [{"feat": _脸(7)}])
    assert gp.forget("gina") == 1
    now[0] += KEEP_MS + 3_600_001
    gp.faces_seen("B", [{"feat": _脸(3)}])
    assert [p["robot"] for p in gp.list(since=0, until=now[0] + 1)["passes"]] == ["B"]


@pytest.fixture
def 站点(tmp_path):
    s = 站(tmp_path)
    s.db.sealbox = SealBox(load_or_create_key(tmp_path / "keys" / "secrets.key"))
    s.api.faces = FaceBook(s.db, now_ms=lambda: 5, engine=假引擎())
    s.api.guard_passes = GuardPasses(s.db, now_ms=lambda: 1_800_000_000_000, faces=s.api.faces)
    s.accounts.add("gina", PW, role="guard")
    s.accounts.add("hugo", PW, role="guard")
    s.accounts.add("olly", PW, role="owner")
    yield s
    s.close()


def _登(s, name):
    code, d = s.req("POST", "/api/login", {"name": name, "password": PW})
    assert code == 200, d
    return d["token"]


def test_真告警台_两个保安各记一笔_当场算已解决(tmp_path):
    from nexwar_site.alert_store import AlertDesk
    db = SiteDB(tmp_path / "s.db")
    db.sealbox = SealBox(load_or_create_key(tmp_path / "keys" / "secrets.key"))
    faces = FaceBook(db, now_ms=lambda: 5, engine=假引擎())
    faces.add_photo("gina", consent=True, jpeg_b64=_照("face:3"))
    faces.add_photo("hugo", consent=True, jpeg_b64=_照("face:7"))
    desk = AlertDesk(db, now_ms=lambda: 1_800_000_000_000)
    gp = GuardPasses(db, now_ms=lambda: 1_800_000_000_000, faces=faces, desk=desk)
    gp.faces_seen("A", [{"feat": _脸(3)}, {"feat": _脸(7)}])
    got = [a for a in desk.book.all() if a.kind == "guard_passed"]
    assert [a.title for a in got] == ["登记过的保安经过"] * 2
    assert all(a.resolved_ms is not None and a.level.name == "P3" for a in got)
    assert not [a for a in desk.book.open() if a.kind == "guard_passed"]


def test_接口_管理员看所有人_保安只看自己_进审计_撤销一起删(站点):
    s = 站点
    gina, alice = _登(s, "gina"), _登(s, "alice")
    for tok, t in ((gina, "face:1"), (_登(s, "hugo"), "face:2")):
        assert s.req("POST", "/api/faces/me/photo", {"consent": True, "jpeg_b64": _照(t)},
                     token=tok)[0] == 200
    s.api.guard_passes.faces_seen("A", [{"feat": _脸(1)}, {"feat": _脸(2)}])
    q = "/api/guard-passes?since=1799999000000&until=1800000001000"
    code, d = s.req("GET", q, token=alice)
    assert code == 200 and sorted(p["account"] for p in d["passes"]) == ["gina", "hugo"], d
    code, d = s.req("GET", q, token=_登(s, "olly"))
    assert code == 200 and len(d["passes"]) == 2, "外审 1.1 #14:经理看所有人"
    code, d = s.req("GET", q, token=gina)
    assert code == 200 and [p["account"] for p in d["passes"]] == ["gina"]
    assert s.req("GET", q + "&account=hugo", token=gina)[0] == 403
    assert s.req("GET", "/api/guard-passes?since=0&until=9999999999999", token=alice)[0] == 400
    rows = [(r["actor"], r["target"]) for r in s.api.audit.list() if r["target"]
            and r["target"].startswith("guard-passes")]
    assert ("alice", "guard-passes/*") in rows and ("gina", "guard-passes/gina") in rows
    assert s.req("POST", "/api/faces/me/remove", token=gina)[0] == 200
    code, d = s.req("GET", q, token=alice)
    assert [p["account"] for p in d["passes"]] == ["hugo"], "撤销同意:经过记录一起删"


def test_外审1_1_第2轮_4_撤销跟建缓存撞上_撤销以后认不出_不再记(记):
    import threading
    gp, desk, now, _ = 记
    faces = gp.faces
    in_build, go = threading.Event(), threading.Event()
    real = faces._feats

    def slow(acc):
        in_build.set()
        go.wait(5)
        return real(acc)
    faces._cache = None
    faces._feats = slow
    got: list = []
    t1 = threading.Thread(target=lambda: got.append(faces.match(_脸(3))))
    t1.start()
    assert in_build.wait(5)
    t2 = threading.Thread(target=lambda: faces.remove("gina"))
    t2.start()
    t2.join(0.2)
    assert t2.is_alive(), "撤销要等正在建的缓存建完"
    go.set()
    t1.join(5)
    t2.join(5)
    faces._feats = real
    assert faces.match(_脸(3)) is None, "撤销以后旧缓存不许盖回来"
    assert gp.seen("A", "gina", how="face", score=0.9) == 0, "认到一半撤销了:不记"
    assert not [p for p in gp.list(since=0, until=now[0] + 1)["passes"] if p["account"] == "gina"]
