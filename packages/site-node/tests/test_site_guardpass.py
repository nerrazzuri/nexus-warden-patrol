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
    assert a["kind"] == "guard_passed" and a["title"] == "保安 gina 经过 B区"
    assert "人脸认出,约 2.4 m" in a["detail"] and a["context"]["zone"] == "B区"
    assert a["record"] == "site:guard_passed", "只记一笔,不推送"
    now[0] += MERGE_MS - 1000
    gp.faces_seen("A", [{"feat": _脸(3)}])
    assert len(desk.raised) == 1, "5 分钟内并成一笔"
    zone["z"] = "C区"
    gp.faces_seen("A", [{"feat": _脸(3)}, {"feat": _脸(7)}])
    assert [r["title"] for r in desk.raised[1:]] == ["保安 gina 经过 C区", "保安 hugo 经过 C区"]
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
    assert sorted(a.title for a in got) == ["保安 gina 经过", "保安 hugo 经过"]
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
