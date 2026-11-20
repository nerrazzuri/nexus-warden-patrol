"""手机指纹登录(用户 11-20):手机 Keystore 里的 P-256 私钥按指纹才能用,站点只存公钥。
登记要先登录 + 签站点出的随机数;登录用一次性随机数换普通会话;改口令、角色、停用、删账号一起作废;
30 天到期;签名不对跟输错密码同一个锁。"""

from __future__ import annotations

import base64

import pytest
from test_site_api import PW, 站

from nexwar_contract import p256
from nexwar_site.accounts import (
    BIO_ENROLL,
    BIO_LOGIN,
    BIO_MAX,
    BIO_NONCE_MS,
    BIO_TTL_MS,
    AccountDisabled,
    Accounts,
    AuthError,
    BioGone,
    LockedOut,
)
from nexwar_site.db import SiteDB


class 钟:
    ms = 1_800_000_000_000

    def __call__(self) -> int:
        return self.ms


@pytest.fixture
def acc(tmp_path):
    db = SiteDB(tmp_path / "s.db")
    c = 钟()
    a = Accounts(db, now_ms=c)
    a.add("gina", PW, role="guard")
    yield a, c
    db.close()


def _登记(a, name="gina", label="Pixel 8"):
    d, pub = p256.new_key()
    n = a.bio_nonce(BIO_ENROLL, name)
    kid, exp = a.bio_enroll(name, pub, label, n, p256.sign(d, BIO_ENROLL + n.encode() + b"\0"
                                                           + name.encode()))
    return d, kid, exp


def _指纹登(a, d, kid):
    n = a.bio_nonce(BIO_LOGIN, kid)
    return a.bio_login(kid, n, p256.sign(d, BIO_LOGIN + n.encode() + b"\0" + kid.encode()))


def test_登记_换会话_会话就是普通会话(acc):
    a, c = acc
    d, kid, exp = _登记(a)
    assert exp == c.ms + BIO_TTL_MS
    tok, name = _指纹登(a, d, kid)
    who = a.check(tok)
    assert name == "gina" and who.role == "guard" and who.scope == ""
    [k] = a.bio_keys("gina")
    assert k["key_id"] == kid and k["label"] == "Pixel 8" and k["last_used_ms"] == c.ms
    assert a.list()[[x["name"] for x in a.list()].index("gina")]["bio_devices"] == 1


def test_随机数一次性_过期_用途和对象对不上都不认(acc):
    a, c = acc
    d, kid, _ = _登记(a)
    n = a.bio_nonce(BIO_LOGIN, kid)
    sig = p256.sign(d, BIO_LOGIN + n.encode() + b"\0" + kid.encode())
    a.bio_login(kid, n, sig)
    with pytest.raises(AuthError, match="随机数"):
        a.bio_login(kid, n, sig)                       # 用过了
    n = a.bio_nonce(BIO_LOGIN, kid)
    c.ms += BIO_NONCE_MS + 1
    with pytest.raises(AuthError, match="随机数"):
        a.bio_login(kid, n, p256.sign(d, BIO_LOGIN + n.encode() + b"\0" + kid.encode()))
    n = a.bio_nonce(BIO_ENROLL, kid)                   # 登记的随机数拿来登录
    with pytest.raises(AuthError, match="随机数"):
        a.bio_login(kid, n, p256.sign(d, BIO_LOGIN + n.encode() + b"\0" + kid.encode()))
    n = a.bio_nonce(BIO_LOGIN, kid)                    # 签的是登记的内容
    with pytest.raises(AuthError, match="签名"):
        a.bio_login(kid, n, p256.sign(d, BIO_ENROLL + n.encode() + b"\0" + kid.encode()))


def test_登记要签对_别人的钥匙签的不认_工程师不许(acc):
    a, c = acc
    d, pub = p256.new_key()
    other, _ = p256.new_key()
    n = a.bio_nonce(BIO_ENROLL, "gina")
    with pytest.raises(AuthError, match="签名"):
        a.bio_enroll("gina", pub, "", n, p256.sign(other, BIO_ENROLL + n.encode() + b"\0gina"))
    n = a.bio_nonce(BIO_ENROLL, "gina")
    with pytest.raises(AuthError, match="P-256"):
        a.bio_enroll("gina", b"junk", "", n, b"")
    eng, _, _ = a.add_engineer("修理工", 4, by="gina")
    n = a.bio_nonce(BIO_ENROLL, eng)
    with pytest.raises(AuthError, match="工程师"):
        a.bio_enroll(eng, pub, "", n, p256.sign(d, BIO_ENROLL + n.encode() + b"\0"
                                                + eng.encode()))
    assert a.bio_keys("gina") == [] and a.bio_keys(eng) == []


def test_改口令_改角色_停用_都把指纹登录作废(acc):
    a, c = acc
    for change in (lambda: a.reset_password("gina", "another-long-pw"),
                   lambda: a.set_role("gina", "owner"),
                   lambda: a.update("gina", disabled=True)):
        a.update("gina", disabled=False)
        d, kid, _ = _登记(a)
        change()
        with pytest.raises(BioGone):
            _指纹登(a, d, kid)
        assert a.bio_keys("gina") == []


def test_30天到期_最多5部_撤一部撤全部(acc):
    a, c = acc
    d, kid, _ = _登记(a)
    c.ms += BIO_TTL_MS
    with pytest.raises(BioGone):
        _指纹登(a, d, kid)
    keys = [_登记(a, label=f"p{i}") for i in range(BIO_MAX + 1)]
    assert len(a.bio_keys("gina")) == BIO_MAX
    with pytest.raises(BioGone):
        _指纹登(a, keys[0][0], keys[0][1])             # 最旧的那部被挤掉
    assert a.bio_revoke("gina", keys[1][1]) == 1
    with pytest.raises(BioGone):
        _指纹登(a, keys[1][0], keys[1][1])
    assert a.bio_revoke("gina") == BIO_MAX - 1 and a.bio_keys("gina") == []


def test_签名不对算输错密码_错五次锁(acc):
    a, c = acc
    d, kid, _ = _登记(a)
    wrong, _ = p256.new_key()
    for _ in range(5):
        with pytest.raises(AuthError, match="签名"):
            _指纹登(a, wrong, kid)
    with pytest.raises(LockedOut):
        _指纹登(a, wrong, kid)
    with pytest.raises(LockedOut):
        a.login("gina", PW)


def test_账号过期_说过期(acc):
    a, c = acc
    d, kid, _ = _登记(a)
    with a.db.tx() as tx:
        tx.execute("UPDATE accounts SET expires_ms=? WHERE name='gina'", (c.ms - 1,))
    with pytest.raises(AccountDisabled, match="过期"):
        _指纹登(a, d, kid)


@pytest.fixture
def 站点(tmp_path):
    s = 站(tmp_path)
    s.accounts.add("gina", PW, role="guard")
    yield s
    s.close()


def _b(x: bytes) -> str:
    return base64.urlsafe_b64encode(x).decode().rstrip("=")


def test_接口_登记_指纹登录_管理员一键撤(站点):
    s = 站点
    code, d = s.req("POST", "/api/login", {"name": "gina", "password": PW})
    tok = d["token"]
    key, pub = p256.new_key()
    n = s.req("POST", "/api/me/bio/challenge", {}, token=tok)[1]["nonce"]
    code, d = s.req("POST", "/api/me/bio", {
        "pub": _b(pub), "label": "Pixel 8", "nonce": n,
        "sig": _b(p256.sign(key, BIO_ENROLL + n.encode() + b"\0gina"))}, token=tok)
    assert code == 200, d
    kid = d["key_id"]
    assert [k["label"] for k in s.req("GET", "/api/me/bio", token=tok)[1]["keys"]] == ["Pixel 8"]
    # 不登录也能要随机数、换会话
    n = s.req("POST", "/api/login/bio/challenge", {"key_id": kid})[1]["nonce"]
    code, d = s.req("POST", "/api/login/bio", {
        "key_id": kid, "nonce": n, "client": {"kind": "app", "version": "1.0.0"},
        "sig": _b(p256.sign(key, BIO_LOGIN + n.encode() + b"\0" + kid.encode()))})
    assert code == 200 and d["name"] == "gina" and d["role"] == "guard", d
    assert s.req("GET", "/api/robots", token=d["token"])[0] == 200
    # 签名不对 401;钥匙号格式不对 400
    n = s.req("POST", "/api/login/bio/challenge", {"key_id": kid})[1]["nonce"]
    assert s.req("POST", "/api/login/bio", {"key_id": kid, "nonce": n, "sig": "AAAA"})[0] == 401
    assert s.req("POST", "/api/login/bio/challenge", {"key_id": "x"})[0] == 400
    # 管理员一键撤:手机再来说「已失效」(bio_gone,App 删本地钥匙改用密码)
    alice = s.login()
    code, d = s.req("POST", "/api/accounts/gina/bio/revoke", {}, token=alice)
    assert code == 200 and d["revoked"] == 1
    assert [a["bio_devices"] for a in d["accounts"] if a["name"] == "gina"] == [0]
    n = s.req("POST", "/api/login/bio/challenge", {"key_id": kid})[1]["nonce"]
    code, d = s.req("POST", "/api/login/bio", {
        "key_id": kid, "nonce": n,
        "sig": _b(p256.sign(key, BIO_LOGIN + n.encode() + b"\0" + kid.encode()))})
    assert code == 401 and d.get("bio_gone") is True, d
    # 保安撤不了别人的
    assert s.req("POST", "/api/accounts/alice/bio/revoke", {}, token=tok)[0] == 403
