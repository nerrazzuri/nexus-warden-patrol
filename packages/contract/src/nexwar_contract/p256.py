"""ECDSA P-256 + SHA-256 验签,纯 Python,**只用标准库**(跟 :mod:`nexwar_contract.ed25519` 一个理由:
站点、狗上不加 Python 依赖)。

用在手机指纹登录上(用户 11-20):手机在 Android Keystore 里生成一把 P-256 私钥(要按指纹才能用),
站点只存公钥;登录时站点出一次性的随机数,手机按指纹签名,站点在这里验。Android Keystore 不支持
Ed25519,所以是 P-256。

公钥是 X.509 SubjectPublicKeyInfo 的 DER(Java ``PublicKey.getEncoded()``),签名是 DER 的
``SEQUENCE { r, s }``(Java ``Signature("SHA256withECDSA")``)。验签只用公开的数据,不在乎侧信道。
:func:`sign` 只给测试用(随机 k,不是常数时间)。用 OpenSSL 互相核对(见测试)。
"""

from __future__ import annotations

import hashlib
import secrets

_P = 0xFFFFFFFF00000001000000000000000000000000FFFFFFFFFFFFFFFFFFFFFFFF
_A = _P - 3
_B = 0x5AC635D8AA3A93E7B3EBBD55769886BC651D06B0CC53B0F63BCE3C3E27D2604B
_N = 0xFFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551
_G = (0x6B17D1F2E12C4247F8BCE6E563A440F277037D812DEB33A0F4A13945D898C296,
      0x4FE342E2FE1A7F9B8EE7EB4A7C0F9E162BCE33576B315ECECBB6406837BF51F5)
#: SubjectPublicKeyInfo(id-ecPublicKey, prime256v1)里放未压缩点之前的那一段。
SPKI_PREFIX = bytes.fromhex("3059301306072a8648ce3d020106082a8648ce3d030107034200")


class BadKey(ValueError):
    pass


def _on_curve(x: int, y: int) -> bool:
    return 0 <= x < _P and 0 <= y < _P and (y * y - x * x * x - _A * x - _B) % _P == 0


# Jacobian 坐标:(X, Y, Z) 表示 (X/Z², Y/Z³);无穷远点 Z = 0。
def _dbl(p: tuple[int, int, int]) -> tuple[int, int, int]:
    x, y, z = p
    if z == 0 or y == 0:
        return (0, 1, 0)
    yy = y * y % _P
    s = 4 * x * yy % _P
    zz = z * z % _P
    m = 3 * (x - zz) * (x + zz) % _P
    x3 = (m * m - 2 * s) % _P
    y3 = (m * (s - x3) - 8 * yy * yy) % _P
    return (x3, y3, 2 * y * z % _P)


def _add(p: tuple[int, int, int], q: tuple[int, int, int]) -> tuple[int, int, int]:
    if p[2] == 0:
        return q
    if q[2] == 0:
        return p
    x1, y1, z1 = p
    x2, y2, z2 = q
    z1z1, z2z2 = z1 * z1 % _P, z2 * z2 % _P
    u1, u2 = x1 * z2z2 % _P, x2 * z1z1 % _P
    s1, s2 = y1 * z2 * z2z2 % _P, y2 * z1 * z1z1 % _P
    if u1 == u2:
        return _dbl(p) if s1 == s2 else (0, 1, 0)
    h, r = (u2 - u1) % _P, (s2 - s1) % _P
    hh = h * h % _P
    hhh = h * hh % _P
    v = u1 * hh % _P
    x3 = (r * r - hhh - 2 * v) % _P
    y3 = (r * (v - x3) - s1 * hhh) % _P
    return (x3, y3, h * z1 * z2 % _P)


def _mul2(a: int, p: tuple[int, int], b: int, q: tuple[int, int]) -> tuple[int, int] | None:
    """a·P + b·Q(Shamir 一起算);无穷远点回 None。"""
    jp, jq = (p[0], p[1], 1), (q[0], q[1], 1)
    jpq = _add(jp, jq)
    acc = (0, 1, 0)
    for i in range(max(a.bit_length(), b.bit_length()) - 1, -1, -1):
        acc = _dbl(acc)
        bit = ((a >> i) & 1, (b >> i) & 1)
        if bit == (1, 1):
            acc = _add(acc, jpq)
        elif bit == (1, 0):
            acc = _add(acc, jp)
        elif bit == (0, 1):
            acc = _add(acc, jq)
    x, y, z = acc
    if z == 0:
        return None
    zi = pow(z, _P - 2, _P)
    return (x * zi * zi % _P, y * zi * zi * zi % _P)


def public_point(spki: bytes) -> tuple[int, int]:
    """SubjectPublicKeyInfo DER → 曲线上的点。不是 P-256 未压缩公钥、点不在曲线上:
    抛 :class:`BadKey`。"""
    if len(spki) != len(SPKI_PREFIX) + 65 or not spki.startswith(SPKI_PREFIX) \
            or spki[len(SPKI_PREFIX)] != 4:
        raise BadKey("不是 P-256 公钥(SubjectPublicKeyInfo,未压缩点)")
    raw = spki[len(SPKI_PREFIX) + 1:]
    x, y = int.from_bytes(raw[:32], "big"), int.from_bytes(raw[32:], "big")
    if not _on_curve(x, y):
        raise BadKey("公钥的点不在 P-256 上")
    return (x, y)


def _der_int(b: bytes, i: int) -> tuple[int, int]:
    if i + 2 > len(b) or b[i] != 0x02:
        raise ValueError("签名格式不对")
    n = b[i + 1]
    if n == 0 or n > 33 or i + 2 + n > len(b):
        raise ValueError("签名格式不对")
    v = b[i + 2:i + 2 + n]
    if v[0] & 0x80 or (n > 1 and v[0] == 0 and not v[1] & 0x80):
        raise ValueError("签名格式不对")       # 负数、多余的前导 0:严格 DER
    return int.from_bytes(v, "big"), i + 2 + n


def _parse_sig(sig: bytes) -> tuple[int, int]:
    if len(sig) < 8 or sig[0] != 0x30 or sig[1] != len(sig) - 2:
        raise ValueError("签名格式不对")
    r, i = _der_int(sig, 2)
    s, i = _der_int(sig, i)
    if i != len(sig):
        raise ValueError("签名格式不对")
    return r, s


def verify(spki: bytes, msg: bytes, sig: bytes) -> bool:
    """``sig`` 是不是 ``spki`` 那把私钥对 ``msg`` 的 SHA256withECDSA 签名。格式不对一律 False。"""
    try:
        q = public_point(spki)
        r, s = _parse_sig(sig)
    except ValueError:
        return False
    if not (1 <= r < _N and 1 <= s < _N):
        return False
    e = int.from_bytes(hashlib.sha256(msg).digest(), "big")
    w = pow(s, _N - 2, _N)
    pt = _mul2(e * w % _N, _G, r * w % _N, q)
    return pt is not None and pt[0] % _N == r


# ------------------------------------------------------------ 只给测试用


def new_key() -> tuple[int, bytes]:
    """(私钥整数, SubjectPublicKeyInfo DER)。测试用。"""
    d = secrets.randbelow(_N - 1) + 1
    x, y = _mul2(d, _G, 0, _G) or (0, 0)
    return d, SPKI_PREFIX + b"\x04" + x.to_bytes(32, "big") + y.to_bytes(32, "big")


def _der(v: int) -> bytes:
    b = v.to_bytes((v.bit_length() + 8) // 8, "big")
    return b"\x02" + bytes([len(b)]) + b


def sign(d: int, msg: bytes) -> bytes:
    """测试用的签名(随机 k,不是常数时间,别拿去签真东西)。回 DER。"""
    e = int.from_bytes(hashlib.sha256(msg).digest(), "big")
    while True:
        k = secrets.randbelow(_N - 1) + 1
        pt = _mul2(k, _G, 0, _G)
        if pt is None:
            continue
        r = pt[0] % _N
        s = pow(k, _N - 2, _N) * (e + r * d) % _N
        if r and s:
            body = _der(r) + _der(s)
            return b"\x30" + bytes([len(body)]) + body
