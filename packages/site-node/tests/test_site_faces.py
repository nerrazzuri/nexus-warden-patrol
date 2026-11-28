"""1.1-1 认出保安 第 1 步:人脸登记(本人同意、只存加密的特征值、管理员只能看和删)。"""

from __future__ import annotations

import base64

import pytest
from test_site_api import PW, 站

from nexwar_site.db import SiteDB
from nexwar_site.faces import MAX_PHOTOS, FaceBook, FaceError
from nexwar_site.sealbox import PREFIX, SealBox, load_or_create_key


class 假引擎:
    """照片内容 ``face:<n>`` → 第 n 维是 1 的特征值;``none`` → 没找到脸。"""

    def features(self, jpeg: bytes) -> list[float]:
        t = jpeg.decode()
        if t == "none":
            raise FaceError("照片里没找到脸:正对镜头、光线亮一点再拍")
        n = int(t.split(":")[1])
        return [1.0 if i == n else 0.0 for i in range(128)]


def _照(t: str) -> str:
    return base64.b64encode(t.encode()).decode()


@pytest.fixture
def 本(tmp_path):
    db = SiteDB(tmp_path / "site.db")
    db.sealbox = SealBox(load_or_create_key(tmp_path / "keys" / "secrets.key"))
    return FaceBook(db, now_ms=lambda: 1_000, engine=假引擎())


def test_本人同意了才登记_特征值加密存_不存照片(本):
    with pytest.raises(FaceError, match="同意"):
        本.add_photo("gina", consent=None, jpeg_b64=_照("face:3"))
    v = 本.add_photo("gina", consent=True, jpeg_b64=_照("face:3"))
    assert v["photos"] == 1 and v["consent_ms"] == 1_000
    raw = 本.db.query("SELECT feats FROM face_book")[0]["feats"]
    assert raw.startswith(PREFIX) and "1.0" not in raw, "特征值整串加密"
    assert {r["name"] for r in 本.db.query("SELECT name FROM sqlite_master")} >= {"face_book"}
    with pytest.raises(FaceError, match="没找到脸"):
        本.add_photo("gina", consent=True, jpeg_b64=_照("none"))
    assert 本.view("gina")["photos"] == 1, "拍坏的不算"


def test_最多五张_满了要先删(本):
    for i in range(MAX_PHOTOS):
        本.add_photo("gina", consent=True, jpeg_b64=_照(f"face:{i}"))
    with pytest.raises(FaceError, match="先删"):
        本.add_photo("gina", consent=True, jpeg_b64=_照("face:9"))


def test_认人_最像的过门槛才算_撤销以后认不出(本):
    本.add_photo("gina", consent=True, jpeg_b64=_照("face:3"))
    本.add_photo("hugo", consent=True, jpeg_b64=_照("face:7"))
    me = [0.0] * 128
    me[3], me[5] = 0.9, 0.2
    assert 本.match(me)[0] == "gina"
    other = [0.0] * 128
    other[40] = 1.0
    assert 本.match(other) is None, "谁都不像:陌生人"
    assert 本.remove("gina") is True
    assert 本.match(me) is None
    assert 本.remove("gina") is False


def test_站点没配密钥_不收人脸(tmp_path):
    book = FaceBook(SiteDB(tmp_path / "site.db"), now_ms=lambda: 1, engine=假引擎())
    with pytest.raises(FaceError, match="密钥"):
        book.add_photo("gina", consent=True, jpeg_b64=_照("face:1"))


def test_没装人脸模块_说清楚(tmp_path):
    db = SiteDB(tmp_path / "site.db")
    db.sealbox = SealBox(load_or_create_key(tmp_path / "keys" / "secrets.key"))
    with pytest.raises(FaceError, match="没装人脸模块"):
        FaceBook(db, now_ms=lambda: 1).add_photo("gina", consent=True, jpeg_b64=_照("face:1"))


@pytest.fixture
def 站点(tmp_path):
    s = 站(tmp_path)
    s.db.sealbox = SealBox(load_or_create_key(tmp_path / "keys" / "secrets.key"))
    s.api.faces = FaceBook(s.db, now_ms=lambda: 5, engine=假引擎())
    s.accounts.add("gina", PW, role="guard")
    s.accounts.add("hugo", PW, role="guard")
    yield s
    s.close()


def _登(s, name: str) -> str:
    code, d = s.req("POST", "/api/login", {"name": name, "password": PW})
    assert code == 200, d
    return d["token"]


def test_接口_保安登记自己_不能替别人登记_不能看名单(站点):
    s = 站点
    gina = _登(s, "gina")
    code, d = s.req("POST", "/api/faces/me/photo", {"consent": True, "jpeg_b64": _照("face:2")},
                    token=gina)
    assert code == 200 and d["photos"] == 1 and d["engine"] is True, d
    code, d = s.req("GET", "/api/faces/me", token=gina)
    assert code == 200 and d["photos"] == 1
    code, _ = s.req("POST", "/api/faces/hugo/photo", {"consent": True, "jpeg_b64": _照("face:4")},
                    token=gina)
    assert code == 403, "只能本人登记自己的脸"
    code, _ = s.req("GET", "/api/faces", token=gina)
    assert code == 403
    code, d = s.req("POST", "/api/faces/me/photo", {"jpeg_b64": _照("face:4")}, token=gina)
    assert code == 400 and "同意" in d["error"]


def test_接口_管理员看名单_删别人的_本人撤销_都进审计(站点):
    s = 站点
    gina, hugo, alice = _登(s, "gina"), _登(s, "hugo"), _登(s, "alice")
    for tok, t in ((gina, "face:1"), (hugo, "face:2")):
        assert s.req("POST", "/api/faces/me/photo", {"consent": True, "jpeg_b64": _照(t)},
                     token=tok)[0] == 200
    code, d = s.req("GET", "/api/faces", token=alice)
    assert code == 200 and [f["account"] for f in d["faces"]] == ["gina", "hugo"]
    assert all("feats" not in f for f in d["faces"]), "名单里不给特征值"
    code, _ = s.req("POST", "/api/faces/hugo/remove", token=gina)
    assert code == 403, "保安不能删别人的"
    code, d = s.req("POST", "/api/faces/hugo/remove", token=alice)
    assert code == 200 and [f["account"] for f in d["faces"]] == ["gina"]
    code, d = s.req("POST", "/api/faces/me/remove", token=gina)
    assert code == 200 and d["photos"] == 0
    rows = [(r["actor"], r["target"]) for r in s.api.audit.list() if "/api/faces" in r["action"]]
    assert ("alice", "faces/hugo") in rows and ("gina", "faces/gina") in rows
