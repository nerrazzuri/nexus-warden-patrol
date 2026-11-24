"""tools/link_4g.sh(用户 11-23:「把 tailscale 的配置做成一个脚本」):只用 --dry-run 看它要做的事。"""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SH = ROOT / "tools" / "link_4g.sh"


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["bash", str(SH), *args, "--dry-run"], capture_output=True, text=True,
                          timeout=30)


def test_语法对():
    assert subprocess.run(["bash", "-n", str(SH)]).returncode == 0


def test_up_四步_先排自动恢复再连_只临时连():
    out = _run("up", "--ssid", "ZTE_C8DE4B", "--hours", "0.25")
    assert out.returncode == 0, out.stderr
    s = out.stdout
    assert s.index("systemd-run --on-active=900s --unit=nexwar-sta-revert") \
        < s.index("robot_sta.sh connect")
    assert "robot_sta.sh enable" not in s and "robot_sta.sh save" not in s
    assert s.index("--unit=nexwar-4g-revert") < s.index("default via 192.168.168.168")
    assert "NEXWAR_SITE_MQTT=mqtts://100.69.130.19:8883" in s
    assert "NEXWAR_SITE_NTP=100.69.130.19" in s
    assert "env.bak-B" in s and "srt_host" in s
    assert "funnel" not in SH.read_text(encoding="utf-8").replace("不开 funnel", "")


def test_down_全部改回_删sta_conf_取消定时():
    s = _run("down").stdout
    for want in ("env.bak-B", "default via 192.168.113.1", "rm -f /userdata/config/sta.conf",
                 "stop nexwar-sta-revert.timer", "stop nexwar-4g-revert.timer", "pop('srt_host'"):
        assert want in s, want


def test_参数不对_说清楚():
    assert _run("up").returncode != 0 and "--ssid" in _run("up").stderr
    bad = _run("up", "--ssid", "x;rm -rf /")
    assert bad.returncode != 0
    assert _run("up", "--ssid", "ok", "--hours", "99").returncode != 0
    assert _run("frobnicate").returncode == 2


def test_prepare_证书加地址重签():
    s = _run("prepare").stdout
    assert "h.append('100.69.130.19')" in s and "vpn reissue-cert" in s
    assert "重新添加站点" in s


def test_真机1124_站点对时也给Tailscale地址发_prepare和up都补():
    """装站点时 chrony 只 allow 私网,机器人改连 100.69.130.19 对时会被拒;
    站点升级也会把这个文件重写。"""
    for args in (("prepare",), ("up", "--ssid", "ZTE_C8DE4B")):
        assert "allow 100.64.0.0/10" in _run(*args).stdout, args
    site = (ROOT / "deploy" / "site" / "install-site.sh").read_text(encoding="utf-8")
    assert "allow 100.64.0.0/10" in site


def test_真机1124_重签用站点装的那个命令_一步不成就停():
    s = _run("prepare").stdout
    assert "/opt/nexwar_site/venv/bin/nexwar_site --home /var/lib/nexwar_site vpn reissue-cert" in s
    sh = SH.read_text(encoding="utf-8")
    assert 'bash -ec "$2"' in sh


def test_真机1124_本地一步失败_脚本退出_不说做完(tmp_path):
    """真机 11-24:重签那步 command not found,脚本照样往下跑、最后说「做完」。"""
    fake = tmp_path / "bin"
    fake.mkdir()
    (fake / "tailscale").write_text("#!/bin/sh\necho 100.69.130.19\n")
    (fake / "systemctl").write_text("#!/bin/sh\nexit 0\n")
    (fake / "sudo").write_text("#!/bin/sh\n[ \"$1\" = -u ] && shift 2\nexec \"$@\"\n")
    home = tmp_path / "site"
    home.mkdir()
    (home / "site.json").write_text('{"hostnames": ["192.168.234.232", "100.69.130.19"]}\n')
    for f in fake.iterdir():
        f.chmod(0o755)
    env = {"PATH": f"{fake}:/usr/bin:/bin", "SITE_HOME": str(home),
           "SITE_CLI": str(tmp_path / "没有这个命令"), "CHRONY_SITE_CONF": str(tmp_path / "c.conf")}
    out = subprocess.run(["bash", str(SH), "prepare"], input="yes\n", capture_output=True,
                         text=True, timeout=30, env=env)
    assert out.returncode != 0
    assert "做完" not in out.stdout


def test_真机1124_env要sudo读_wpa能应答再连_连不上再来():
    up = _run("up", "--ssid", "ZTE_C8DE4B").stdout
    assert "sudo grep -E '^NEXWAR_SITE_(MQTT|NTP)=' /etc/nexwar/env" in up
    assert "sudo test -f /etc/nexwar/env.bak-B" in up
    assert up.index("wpa_cli -i wlan0 ping") < up.index("robot_sta.sh connect")
    assert "for n in 1 2 3" in up
    down = _run("down").stdout
    assert "sudo grep -E '^NEXWAR_SITE_(MQTT|NTP)=' /etc/nexwar/env" in down
    assert "mqtts://100\\." in down, "备份里已经是 Tailscale 地址(up 跑过两次)就不拿它恢复"
    sh = SH.read_text(encoding="utf-8")
    assert "\n grep -E '^NEXWAR_SITE" not in sh and "; grep -E '^NEXWAR_SITE" not in sh
