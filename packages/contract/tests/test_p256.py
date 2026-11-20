"""P-256 验签(手机指纹登录,用户 11-20):跟 OpenSSL 互相核对;坏格式、别的钥匙、改过的消息都不认。"""

import shutil
import subprocess

import pytest

from nexwar_contract import p256

openssl = shutil.which("openssl")


def test_自己签自己验_改一个字节就不认():
    d, pub = p256.new_key()
    sig = p256.sign(d, b"nonce-1")
    assert p256.verify(pub, b"nonce-1", sig)
    assert not p256.verify(pub, b"nonce-2", sig)
    _, other = p256.new_key()
    assert not p256.verify(other, b"nonce-1", sig)
    bad = bytearray(sig)
    bad[-1] ^= 1
    assert not p256.verify(pub, b"nonce-1", bytes(bad))


@pytest.mark.parametrize("sig", [b"", b"\x30\x00", b"\x30\x06\x02\x01\x00\x02\x01\x01",
                                 b"\x30\x06\x02\x01\x01\x02\x01\x01\x00", b"x" * 72])
def test_签名格式不对_不认_不抛(sig):
    _, pub = p256.new_key()
    assert not p256.verify(pub, b"m", sig)


def test_公钥不对_不认():
    d, pub = p256.new_key()
    sig = p256.sign(d, b"m")
    assert not p256.verify(pub[:-1], b"m", sig)
    off = bytearray(pub)
    off[-1] ^= 1                      # 点不在曲线上
    assert not p256.verify(bytes(off), b"m", sig)
    with pytest.raises(p256.BadKey):
        p256.public_point(bytes(off))


@pytest.mark.skipif(openssl is None, reason="没有 openssl")
def test_跟OpenSSL互相核对(tmp_path):
    key, pub = tmp_path / "k.pem", tmp_path / "p.der"
    subprocess.run([openssl, "ecparam", "-name", "prime256v1", "-genkey", "-noout", "-out", key],
                   check=True, capture_output=True)
    subprocess.run([openssl, "ec", "-in", key, "-pubout", "-outform", "DER", "-out", pub],
                   check=True, capture_output=True)
    msg = tmp_path / "m"
    msg.write_bytes(b"site-nonce:abc")
    for i in range(5):
        sig = tmp_path / f"s{i}"
        subprocess.run([openssl, "dgst", "-sha256", "-sign", key, "-out", sig, msg],
                       check=True, capture_output=True)
        assert p256.verify(pub.read_bytes(), b"site-nonce:abc", sig.read_bytes())
    # 反过来:我们签的 OpenSSL 认
    d, mine = p256.new_key()
    (tmp_path / "mine.der").write_bytes(mine)
    (tmp_path / "ms").write_bytes(p256.sign(d, b"site-nonce:abc"))
    out = subprocess.run([openssl, "dgst", "-sha256", "-verify", tmp_path / "mine.der",
                          "-keyform", "DER", "-signature", tmp_path / "ms", msg],
                         capture_output=True, text=True)
    assert out.returncode == 0, out.stdout + out.stderr
