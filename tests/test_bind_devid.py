"""W63 机器人这头的设备身份:设备钥匙、芯片编号、出厂申请、装出厂证书、出厂检验、答题。"""

from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest

from nexwar_contract import device_id as di
from nexwar_contract import ed25519
from nexwar_patrol.bind import devid
from nexwar_patrol.bind.paths import BindPaths, write_json

NOW = 1_800_000_000_000


@pytest.fixture
def 板(tmp_path):
    p = BindPaths(etc=tmp_path / "etc")
    p.etc.mkdir()
    write_json(p.device, {"serial": "D1M-0001", "model": "D1 Max", "code_hash": "x",
                          "hotspot_ssid": "s", "fingerprint": "f"})
    dt = tmp_path / "serial-number"
    dt.write_bytes(b"1424C21A0C3A\x00")
    return p, [dt]


def test_芯片编号_读设备树或cpuinfo_全零和读不到都不行(tmp_path):
    dt = tmp_path / "sn"
    dt.write_bytes(b"ABC123\x00")
    h = devid.read_hw_id([dt])
    assert len(h) == 64 and h == devid.read_hw_id([tmp_path / "none", dt])
    cpu = tmp_path / "cpuinfo"
    cpu.write_text("processor\t: 0\nSerial\t\t: 7c2f0a9b11223344\n")
    assert devid.read_hw_id([cpu]) != h
    zero = tmp_path / "z"
    zero.write_text("Serial\t\t: 0000000000000000\n")
    with pytest.raises(devid.DevIdError, match="芯片编号"):
        devid.read_hw_id([zero, tmp_path / "none"])


def test_芯片编号_厂家占位值不算_往下读真编号_工单11_02_2(tmp_path):
    """11-02:C40221 的 Orin 设备树 serial-number 是厂家占位 ``DummySN``,所有这种板算出来一样。占位值
    (DummySN、全同字符、顺序数字之类)跳过,往下读(Orin 是 tegra_chip_uid);都没有就报读不到。"""
    dummy = tmp_path / "dt"
    dummy.write_bytes(b"DummySN\x00\x00")
    uid = tmp_path / "uid"
    uid.write_text("0x4b7d0f2a1c0310\n")
    assert devid.read_hw_id([dummy, uid]) == devid.read_hw_id([uid])
    for bad in ("DummySN", "dummy", "FFFFFFFF", "0123456789", "123456789", "N/A", "unknown",
                "Default string", "To be filled by O.E.M."):
        f = tmp_path / "bad"
        f.write_text(bad + "\n")
        with pytest.raises(devid.DevIdError, match="芯片编号"):
            devid.read_hw_id([f])
    assert Path("/sys/module/tegra_fuse/parameters/tegra_chip_uid") in devid.HW_SOURCES


def _eeprom(serial: bytes, part: bytes = b"699-13767-0000-303 D.1", pad: bytes = b"\x00") -> bytes:
    """照 C40221 的模块 EEPROM(256 字节)摆:偏移 20 料号,74 序列号,150 ``NVCB``。"""
    raw = bytearray(b"\xff" * 256)
    raw[20:20 + len(part)] = part
    raw[74:89] = serial.ljust(15, pad)[:15]
    raw[150:154] = b"NVCB"
    return bytes(raw)


def test_芯片编号_Orin只有模块EEPROM有序列号_真机11_20(tmp_path):
    """11-20 C40221(R36.4.7):设备树 DummySN,没有 tegra_chip_uid、soc0 序号、cpuinfo Serial;
    模块 EEPROM(module1,256 字节)偏移 74 是模块序列号 ``1423925050686``。"""
    dummy = tmp_path / "serial-number"
    dummy.write_bytes(b"DummySN\x00")
    cpu = tmp_path / "cpuinfo"
    cpu.write_text("processor\t: 0\nmodel name\t: ARMv8 Processor rev 1 (v8l)\n")
    ee = tmp_path / "module1" / "nvmem"
    ee.parent.mkdir()
    ee.write_bytes(_eeprom(b"1423925050686"))
    import hashlib
    want = hashlib.sha256(b"d1max-hw|1423925050686").hexdigest()
    assert devid.read_hw_id([dummy, tmp_path / "none", cpu, ee]) == want
    # 补 0xFF、补空格也一样;i2c 那个 eeprom 文件名也认
    ee2 = tmp_path / "eeprom"
    ee2.write_bytes(_eeprom(b"1423925050686", pad=b"\xff"))
    assert devid.read_hw_id([ee2]) == want
    ee2.write_bytes(_eeprom(b"1423925050686", pad=b" "))
    assert devid.read_hw_id([ee2]) == want
    # 两块板不一样
    ee2.write_bytes(_eeprom(b"1423925050999"))
    assert devid.read_hw_id([ee2]) != want
    # 不是 Jetson 的 EEPROM、序列号是空的 / 全 0 / 全 FF / 有怪字符:都不算,报读不到
    for raw in (_eeprom(b"1423925050686", part=b"ABC-123"), _eeprom(b""), _eeprom(b"0000000000000"),
                bytes(b"\xff" * 256), _eeprom(b"14239-25050"), b"699-" + b"\x00" * 40):
        ee2.write_bytes(raw)
        with pytest.raises(devid.DevIdError, match="芯片编号"):
            devid.read_hw_id([dummy, cpu, ee2])
    # 读不了(不是 root)就往下,最后报读不到
    with pytest.raises(devid.DevIdError, match="root"):
        devid.read_hw_id([dummy, tmp_path / "nope" / "nvmem"])


def test_芯片编号_EEPROM排在最后_已签的板子hw_id不变(tmp_path):
    """新来源只往最后加:设备树(RK3588)、tegra_chip_uid 读得到的板子,有 EEPROM 也照旧用前面那个。"""
    assert devid.HW_SOURCES[-len(devid.JETSON_EEPROM):] == devid.JETSON_EEPROM
    src = devid.HW_SOURCES
    assert src.index(Path("/proc/cpuinfo")) < src.index(devid.JETSON_EEPROM[0])
    dt = tmp_path / "serial-number"
    dt.write_bytes(b"1424C21A0C3A\x00")
    ee = tmp_path / "nvmem"
    ee.write_bytes(_eeprom(b"1423925050686"))
    assert devid.read_hw_id([dt, ee]) == devid.read_hw_id([dt])


def test_出厂申请_生成设备钥匙只给root读_不覆盖(板):
    p, hw = 板
    req = devid.make_request(p, hw_sources=hw)
    key = devid.key_path(p)
    assert stat.S_IMODE(key.stat().st_mode) == 0o600
    seed = ed25519.seed_from_pem(key.read_bytes())
    assert req["serial"] == "D1M-0001" and di._unb64(req["device_pub"]) == ed25519.public_key(seed)
    assert devid.make_request(p, hw_sources=hw)["device_pub"] == req["device_pub"], "不换钥匙"
    assert json.loads(devid.request_path(p).read_text()) == req


def test_装出厂证书_要是这块板的_要是认的出厂钥匙签的(板, tmp_path):
    p, hw = 板
    factory = ed25519.new_seed()
    pubs = [ed25519.public_key(factory)]
    req = devid.make_request(p, hw_sources=hw)
    cert = di.sign_device(factory, req, now_ms=NOW)
    for bad, why in ((dict(cert, serial="D1M-0002"), "序列号"),
                     (di.sign_device(factory, dict(req, hw_id="b" * 64), now_ms=NOW), "芯片编号"),
                     (di.sign_device(factory, dict(req, device_pub=di._b64(
                         ed25519.public_key(ed25519.new_seed()))), now_ms=NOW), "设备钥匙"),
                     (di.sign_device(ed25519.new_seed(), req, now_ms=NOW), "出厂")):
        with pytest.raises(devid.DevIdError, match=why):
            devid.install_cert(p, bad, factory_pubs=pubs, hw_sources=hw)
        assert not devid.cert_path(p).exists()
    devid.install_cert(p, cert, factory_pubs=pubs, hw_sources=hw)
    assert devid.problems(p, factory_pubs=pubs, hw_sources=hw) == []


def test_出厂检验_没证书_换了板子_都报出来(板, tmp_path):
    p, hw = 板
    factory = ed25519.new_seed()
    pubs = [ed25519.public_key(factory)]
    devid.make_request(p, hw_sources=hw)
    assert any("出厂证书" in x for x in devid.problems(p, factory_pubs=pubs, hw_sources=hw))
    devid.install_cert(p, di.sign_device(factory, json.loads(devid.request_path(p).read_text()),
                                         now_ms=NOW), factory_pubs=pubs, hw_sources=hw)
    other = tmp_path / "other-sn"
    other.write_bytes(b"FFFF0000AAAA\x00")
    assert any("芯片编号" in x for x in devid.problems(p, factory_pubs=pubs, hw_sources=[other]))


def test_答题_站点验得过(板):
    p, hw = 板
    factory = ed25519.new_seed()
    pubs = [ed25519.public_key(factory)]
    req = devid.make_request(p, hw_sources=hw)
    devid.install_cert(p, di.sign_device(factory, req, now_ms=NOW), factory_pubs=pubs,
                       hw_sources=hw)
    ans = devid.answer(p, purpose="claim", site_id="s1", nonce="n" * 32, hw_sources=hw)
    cert = di.verify_cert(ans["cert"], pubs)
    di.verify_attest(ans["cert"], di.attest_message(purpose="claim", site_id="s1", nonce="n" * 32,
                                                    serial=cert.serial, hw_id=ans["hw_id"]),
                     ans["sig"])
    assert ans["hw_id"] == cert.hw_id


def test_没烧写过设备身份_答不了题_说清楚(板):
    p, hw = 板
    assert devid.answer(p, purpose="bind", site_id="s1", nonce="n" * 32, hw_sources=hw) is None


def test_没走过烧写的老机器_只补设备身份_不当成烧写过(tmp_path):
    p = BindPaths(etc=tmp_path / "etc")
    p.etc.mkdir()
    dt = tmp_path / "serial-number"
    dt.write_bytes(b"1424C21A0C3A\x00")
    req = devid.init_identity(p, serial="C40221", model="nexwar_orin", hw_sources=[dt])
    assert req["serial"] == "C40221" and not p.device.exists(), "不写 device.json(配网服务不起)"
    factory = ed25519.new_seed()
    pubs = [ed25519.public_key(factory)]
    devid.install_cert(p, di.sign_device(factory, req, now_ms=NOW), factory_pubs=pubs,
                       hw_sources=[dt])
    assert devid.problems(p, factory_pubs=pubs, hw_sources=[dt]) == []
    ans = devid.answer(p, purpose="claim", site_id="s1", nonce="n" * 32, hw_sources=[dt])
    assert di.verify_cert(ans["cert"], pubs).serial == "C40221"
    assert devid.init_identity(p, serial="C40221", hw_sources=[dt])["device_pub"] == \
        req["device_pub"], "再跑一次:同一把设备钥匙"
    with pytest.raises(devid.DevIdError, match="C40221"):
        devid.init_identity(p, serial="C40011", hw_sources=[dt])


def test_烧写过的机器_补身份的序列号要跟烧写的一样(板):
    p, hw = 板
    with pytest.raises(devid.DevIdError, match="D1M-0001"):
        devid.init_identity(p, serial="D1M-9999", hw_sources=hw)
    assert devid.init_identity(p, serial="D1M-0001", hw_sources=hw)["serial"] == "D1M-0001"
