"""系统设置跟着升级走(用户 11-23:「装机脚本可以做一下，能不能做成一键式的？这样对客户也简单」)。

- 执行器自己(和验签模块)随发行换:验过签的那一份字节才装,新的编译不过不换,上一份留着。
- 系统设置(logind 不清服务账号的共享内存、服务账号常驻 —— 真机 11-20 Nav2 失联根因)开机准备、
  换版本以后都补一次;内容跟装机脚本 ②b 一字不差。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from nexwar_contract import relsign
from nexwar_contract.digest import tree_sha256
from tests.test_ops_runner import ROOT, R, Rec, _cfg


def _install_sh_logind() -> str:
    s = (ROOT / "deploy" / "install.sh").read_text(encoding="utf-8")
    m = re.search(r"cat > /etc/systemd/logind\.conf\.d/nexwar\.conf <<'LOGIND'\n(.*?)LOGIND\n",
                  s, re.S)
    assert m, "装机脚本 ②b 没找到"
    return m.group(1)


def test_系统设置跟装机脚本一字不差():
    assert R.LOGIND_TEXT == _install_sh_logind()
    assert R.LOGIND_CONF == "systemd/logind.conf.d/nexwar.conf"


def _linger(state: dict):
    calls: list[list[str]] = []

    def run(argv, timeout):
        calls.append(argv)
        if argv[:2] == ["loginctl", "show-user"]:
            return (0, "yes\n") if state["on"] \
                else (1, "User robot is not logged in or lingering\n")
        if argv[:2] == ["loginctl", "enable-linger"]:
            state["on"] = True
        return 0, ""
    return run, calls


def test_缺了就补_补过一次就不再动(tmp_path):
    cfg = _cfg(tmp_path)
    etc = tmp_path / "etc"
    state = {"on": False}
    run, calls = _linger(state)
    ops = R.Ops(cfg, run=run, etc=etc)
    assert ops.system_settings() == ["logind", "linger"]
    assert (etc / R.LOGIND_CONF).read_text(encoding="utf-8") == R.LOGIND_TEXT
    assert ["loginctl", "enable-linger", cfg["requester"]] in calls
    calls.clear()
    assert ops.system_settings() == []
    assert not any(c[:2] == ["loginctl", "enable-linger"] for c in calls)
    (etc / R.LOGIND_CONF).write_text("[Login]\nRemoveIPC=yes\n")     # 被人改回去了
    assert ops.system_settings() == ["logind"]
    assert "RemoveIPC=no" in (etc / R.LOGIND_CONF).read_text()


def test_常驻开不成_说清楚_不抛(tmp_path):
    cfg = _cfg(tmp_path)

    def run(argv, timeout):
        if argv[:2] == ["loginctl", "enable-linger"]:
            return 1, "Failed to enable linger: Access denied"
        return 1, ""
    got = R.Ops(cfg, run=run, etc=tmp_path / "etc").system_settings()
    assert got[0] == "logind" and got[1].startswith("linger 没开成") and "Access denied" in got[1]


def test_站点上不动系统设置(tmp_path):
    rec = Rec()
    assert R.Ops(_cfg(tmp_path, "site"), run=rec, etc=tmp_path / "etc").system_settings() == []
    assert rec.calls == [] and not (tmp_path / "etc" / R.LOGIND_CONF).exists()


def test_开机准备一上来就补系统设置(tmp_path):
    cfg = _cfg(tmp_path)
    run, calls = _linger({"on": False})
    R.boot(R.Ops(cfg, run=run, etc=tmp_path / "etc"), sleep=lambda s: None)
    assert (tmp_path / "etc" / R.LOGIND_CONF).is_file()
    assert calls[0][:2] == ["loginctl", "show-user"], "不等网络、路由,最先做"


def _files(runner: bytes | None = None) -> dict[str, bytes]:
    return {
        "packages/contract/src/nexwar_contract/ed25519.py":
            (ROOT / "packages/contract/src/nexwar_contract/ed25519.py").read_bytes(),
        "packages/contract/src/nexwar_contract/relsign.py":
            (ROOT / "packages/contract/src/nexwar_contract/relsign.py").read_bytes(),
        "deploy/nexwar_ops_runner":
            runner if runner is not None else (ROOT / "deploy/nexwar_ops_runner").read_bytes(),
    }


def test_执行器换新_一样就不动_旧的留一份(tmp_path):
    lib = tmp_path / "lib"
    lib.mkdir()
    (lib / "ops-runner").write_bytes(b"#!/usr/bin/env python3\n# old\n")
    assert R.install_runner(_files(), lib) is True
    assert (lib / "ops-runner").read_bytes() == (ROOT / "deploy/nexwar_ops_runner").read_bytes()
    assert (lib / "ops-runner").stat().st_mode & 0o777 == 0o755
    assert (lib / "ops-runner.prev").read_bytes() == b"#!/usr/bin/env python3\n# old\n"
    assert (lib / "nexwar_contract" / "relsign.py").is_file()
    assert R.install_runner(_files(), lib) is False


@pytest.mark.parametrize("bad", [b"def main(:\n", b"print('no main')\n"])
def test_执行器编不过或不完整_不换(tmp_path, bad):
    lib = tmp_path / "lib"
    lib.mkdir()
    (lib / "ops-runner").write_bytes(b"old")
    with pytest.raises(R.OpError):
        R.install_runner(_files(bad), lib)
    assert (lib / "ops-runner").read_bytes() == b"old"
    assert not (lib / "nexwar_contract").exists(), "执行器不换,模块也不先换"


def test_换版本以后_执行器和系统设置跟着这一版走(tmp_path, monkeypatch):
    """网页升级(换版本)以后代理调 units_apply:以 root 跑时把执行器换成这一版、补系统设置。"""
    keys = tmp_path / "keys"
    relsign.keygen(keys / "priv.pem", keys / "pub.pem")
    name = "2026-11-23-abcdef12"
    root = tmp_path / "opt" / "releases" / name
    for src, data in _files().items():
        (root / src).parent.mkdir(parents=True, exist_ok=True)
        (root / src).write_bytes(data)
    from nexwar_agent.engine.release import _packed
    man = {"name": name, "version": "1.0", "requires_mission_schema": 1,
           "content_sha256": tree_sha256(root, skip="release.json", keep=_packed)}
    man["signature"] = relsign.sign(man, keys / "priv.pem")
    (root / "release.json").write_text(json.dumps(man))
    cfg = _cfg(tmp_path) | {"lib_dir": str(tmp_path / "lib")}
    (tmp_path / "lib").mkdir()
    sysd = tmp_path / "systemd"
    sysd.mkdir()
    run, _ = _linger({"on": False})
    ops = R.Ops(cfg, run=run, etc=tmp_path / "etc", systemd_dir=sysd)
    monkeypatch.setattr(R.os, "geteuid", lambda: 1000)
    assert ops.do("units_apply", {"release": name}) == {"changed": [], "bind": False}, \
        "不是 root(测试、仿真):不动系统"
    monkeypatch.setattr(R.os, "geteuid", lambda: 0)
    monkeypatch.setattr(R.os, "chown", lambda *a, **k: None)
    got = ops.do("units_apply", {"release": name})
    assert got["runner"] is True and got["system"] == ["logind", "linger"]
    assert (tmp_path / "lib" / "ops-runner").read_bytes() == _files()["deploy/nexwar_ops_runner"]
    assert ops.do("units_apply", {"release": name}) == {"changed": [], "bind": False}


def test_装机清单里执行器装的模块_跟随发行换的一样():
    s = (ROOT / "deploy" / "install.sh").read_text(encoding="utf-8")
    m = re.search(r"for m in ([a-z0-9_ ]+); do\n\s+install -m 0644 -o root -g root "
                  r"\"\$PKG/packages/contract/src/nexwar_contract/\$m\.py\" "
                  r"/usr/local/lib/nexwar/", s)
    assert m
    assert {f"nexwar_contract/{x}.py" for x in m.group(1).split()} \
        == {v for v in R.RUNNER_FILES.values() if v.startswith("nexwar_contract/")}
    assert Path(R.RUNNER_FILES["deploy/nexwar_ops_runner"]).name == "ops-runner"


def test_真机1123_chrony重启以后站点对时源自己加回来(tmp_path):
    """真机 11-23:厂家 chrony.conf 不读 conf.d,站点源是开机运行时加的,谁重启一下 chrony 就没了。
    装一个 chrony 的单元片段,每次起来以后加回去;厂家的 chrony.conf 不改。没装 chrony 的机器不动。"""
    cfg = _cfg(tmp_path)
    etc = tmp_path / "etc"
    run, calls = _linger({"on": True})
    ops = R.Ops(cfg, run=run, etc=etc)
    assert ops.system_settings() == ["logind"], "没有 chrony 的机器不装片段"
    (etc / "chrony").mkdir(parents=True)
    (etc / "chrony" / "chrony.conf").write_text("server 192.168.168.19 iburst\n")
    assert ops.system_settings() == ["chrony"]
    drop = (etc / R.CHRONY_DROPIN).read_text(encoding="utf-8")
    assert "ExecStartPost=-" in drop and "--chrony-site" in drop
    assert ["systemctl", "daemon-reload"] in calls
    assert ops.system_settings() == []
    assert (etc / "chrony" / "chrony.conf").read_text() == "server 192.168.168.19 iburst\n"


def test_真机1123_加上站点源以后催一次_选上了差得多就拨一次钟(tmp_path):
    cfg = _cfg(tmp_path)
    env = tmp_path / "etc" / "nexwar" / "env"
    env.parent.mkdir(parents=True, exist_ok=True)
    env.write_text("NEXWAR_SITE_NTP=192.168.234.232\n")
    track = {"ref": "192.168.168.19", "off": "-20000000.5"}
    calls = []

    def run(argv, timeout):
        calls.append(argv)
        if argv[:3] == ["chronyc", "-c", "tracking"]:
            return 0, (f"C0A8A813,{track['ref']},3,1795402791.0,{track['off']},"
                       "0,0,0,0,0,0,0,0,Normal\n")
        return 0, ""
    ops = R.Ops(cfg, run=run, etc=tmp_path / "etc")
    assert ops.chrony_site({})["chrony"] == "added"
    assert ["chronyc", "burst", "4/4", "192.168.234.232"] in calls, \
        "路由晚加时 iburst 白发了,再催一次"
    assert ops.chrony_step() == {"step": "not_selected", "ref": "192.168.168.19"}
    assert ["chronyc", "makestep"] not in calls, "还跟着竞品板,不拨"
    track["ref"] = "192.168.234.232"
    assert ops.chrony_step()["step"] == "stepped"
    assert ["chronyc", "makestep"] in calls
    calls.clear()
    track["off"] = "0.002"
    assert ops.chrony_step()["step"] == "ok" and ["chronyc", "makestep"] not in calls
