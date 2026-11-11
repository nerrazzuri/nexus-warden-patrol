"""停用脚本(用户 11-11:C40221 客户改用竞品平台,我们的东西「可以不删,但是不能启动」)。

拿一个临时目录当机器人的根(``NEXWAR_DISABLE_ROOT``),假 ``systemctl`` 记下每一条调用,
看脚本:交还控制权、厂家服务开回去、我们的单元都停掉关自启、对时片段挪走、留记录;
``--undo`` 按记录恢复;``--dry-run`` 什么都不动;``--check`` 只看。
"""
from __future__ import annotations

import os
import stat
import subprocess
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "deploy" / "disable.sh"

FAKE_SYSTEMCTL = """#!/usr/bin/env bash
# 假 systemctl:单元在 $R/units/<名字> 里,文件内容就是 is-enabled 的回答
R="$NEXWAR_DISABLE_ROOT"
echo "systemctl $*" >> "$R/calls.log"
case "$1" in
  cat) [ -f "$R/units/$2" ] && { cat "$R/units/$2.unit" 2>/dev/null; true; } ;;
  is-enabled) [ -f "$R/units/$2" ] && cat "$R/units/$2" || { echo "not-found"; exit 1; } ;;
  is-active) echo inactive; exit 3 ;;
  list-unit-files) for f in "$R"/units/*; do case "$f" in *.unit) continue ;; esac
                     echo "$(basename "$f") $(cat "$f")"; done ;;
  list-units) exit 0 ;;
  *) exit 0 ;;
esac
"""


def _robot(tmp_path: Path) -> Path:
    r = tmp_path / "robot"
    (r / "units").mkdir(parents=True)
    for u, st in [("nexwar_agent.service", "enabled"), ("nexwar_sidecar.service", "enabled"),
                  ("nexwar_boot.service", "enabled"), ("nexwar_ops.path", "enabled"),
                  ("nexwar_persons.service", "disabled"), ("nexwar_extra.service", "enabled"),
                  ("d1max-agent.service", "disabled"), ("d1max_ui.service", "enabled")]:
        (r / "units" / u).write_text(st + "\n")
    # 老名字 d1max*:指向我们程序的才算我们的;厂家产品也叫 D1 Max,它的单元不许碰
    (r / "units/d1max-agent.service.unit").write_text("ExecStart=/opt/d1max/current/bin/run\n")
    (r / "units/d1max_ui.service.unit").write_text("ExecStart=/opt/robot/ui/bin/ui\n")
    (r / "etc/chrony/conf.d").mkdir(parents=True)
    (r / "etc/chrony/conf.d/nexwar.conf").write_text("server 192.168.234.2 iburst prefer trust\n")
    (r / "etc/nexwar").mkdir(parents=True)
    (r / "etc/nexwar/env").write_text("NEXWAR_HAL=d1max\n")
    (r / "var/lib/nexwar").mkdir(parents=True)
    (r / "var/lib/nexwar/vendor-autostart-off.json").write_text(
        '{"units": ["robot_slam.service", "perception.service"]}\n')
    (r / "home/robot/nexwar_sidecar/runs").mkdir(parents=True)
    os.mkfifo(r / "home/robot/nexwar_sidecar/runs/nexwar_agent.fifo")
    b = tmp_path / "bin"
    b.mkdir()
    (b / "systemctl").write_text(FAKE_SYSTEMCTL)
    (b / "systemctl").chmod(0o755)
    return r


def _run(r: Path, *args: str, stdin: str = "") -> subprocess.CompletedProcess:
    env = {**os.environ, "NEXWAR_DISABLE_ROOT": str(r), "NEXWAR_DISABLE_WAIT": "0",
           "PATH": f"{r.parent / 'bin'}:{os.environ['PATH']}"}
    return subprocess.run(["bash", str(SCRIPT), *args], input=stdin, env=env, text=True,
                          capture_output=True, timeout=60)


def _calls(r: Path) -> list[str]:
    p = r / "calls.log"
    return p.read_text().splitlines() if p.exists() else []


def _read_fifo(path: Path, out: list[str]) -> threading.Thread:
    def go() -> None:
        with open(path) as fh:
            out.append(fh.read())
    t = threading.Thread(target=go, daemon=True)
    t.start()
    return t


def test_停用_交还控制权_厂家开回去_我们的都停掉_对时片段挪走_留记录(tmp_path):
    r = _robot(tmp_path)
    got: list[str] = []
    t = _read_fifo(r / "home/robot/nexwar_sidecar/runs/nexwar_agent.fifo", got)
    p = _run(r, "--yes")
    t.join(5)
    assert p.returncode == 0, p.stdout + p.stderr
    assert got and "shutdown" in got[0], "先往旁路的命令管道写 shutdown,交还控制权"
    calls = _calls(r)
    for u in ("robot_slam.service", "perception.service"):
        assert f"systemctl enable --now {u}" in calls, "我们关过自启的厂家服务开回去"
    for u in ("nexwar_agent.service", "nexwar_sidecar.service", "nexwar_boot.service",
              "nexwar_ops.path", "nexwar_persons.service", "nexwar_extra.service",
              "d1max-agent.service"):
        assert f"systemctl disable --now {u}" in calls, u
    assert not any("d1max_ui" in c and "disable" in c for c in calls), "厂家的 d1max_* 单元不碰"
    assert not (r / "etc/chrony/conf.d/nexwar.conf").exists(), "对时片段挪走"
    assert (r / "etc/nexwar/disabled/chrony-conf.d-nexwar.conf").exists(), "挪走不是删"
    assert (r / "var/lib/nexwar/vendor-autostart-off.json.restored").exists()
    state = (r / "etc/nexwar/disabled/state.txt").read_text()
    assert "nexwar_agent.service enabled" in state and "nexwar_persons.service disabled" in state
    assert list((r / "var/log").glob("nexwar-disable-*.log")), "过程留日志"
    assert "整机断电重启" in p.stdout


def test_撤回_按记录开回原来开着的_对时片段放回(tmp_path):
    r = _robot(tmp_path)
    _run(r, "--yes")
    (r / "calls.log").unlink()
    p = _run(r, "--undo", "--yes")
    assert p.returncode == 0, p.stdout + p.stderr
    calls = _calls(r)
    assert "systemctl enable nexwar_agent.service" in calls
    assert "systemctl enable nexwar_sidecar.service" in calls
    assert "systemctl enable nexwar_persons.service" not in calls, "原来没开机自启的不开"
    assert not any("robot_slam" in c and c.split()[1] in ("disable", "stop", "mask") for c in calls), \
        "厂家服务撤回时不再关掉"
    assert (r / "etc/chrony/conf.d/nexwar.conf").exists()
    assert not (r / "etc/nexwar/disabled/state.txt").exists()


def test_只看一眼_dry_run_什么都不动(tmp_path):
    r = _robot(tmp_path)
    p = _run(r, "--dry-run")
    assert p.returncode == 0, p.stdout + p.stderr
    assert not [c for c in _calls(r) if c.split()[1] in ("disable", "enable", "stop")], _calls(r)
    assert (r / "etc/chrony/conf.d/nexwar.conf").exists()
    assert not (r / "etc/nexwar/disabled").exists()
    assert "nexwar_agent.service" in p.stdout


def test_不确认就不动(tmp_path):
    r = _robot(tmp_path)
    p = _run(r, stdin="n\n")
    assert p.returncode != 0
    assert not [c for c in _calls(r) if c.split()[1] in ("disable", "enable")]
    assert (r / "etc/chrony/conf.d/nexwar.conf").exists()


def test_检查模式_只报还开着自启的(tmp_path):
    r = _robot(tmp_path)
    p = _run(r, "--check")
    assert p.returncode == 1 and "nexwar_agent.service" in p.stdout
    _run(r, "--yes")
    for f in (r / "units").iterdir():
        f.write_text("disabled\n")
    p = _run(r, "--check")
    assert p.returncode == 0, p.stdout


@pytest.mark.skipif(os.geteuid() == 0, reason="root 跑测试时这一条没意义")
def test_真改要root(tmp_path):
    env = {k: v for k, v in os.environ.items() if k != "NEXWAR_DISABLE_ROOT"}
    p = subprocess.run(["bash", str(SCRIPT), "--yes"], env=env, text=True,
                       capture_output=True, timeout=30)
    assert p.returncode == 2 and "sudo" in p.stderr


def test_第二次停用不覆盖第一次的记录(tmp_path):
    r = _robot(tmp_path)
    _run(r, "--yes")
    for f in (r / "units").glob("*.service"):
        f.write_text("disabled\n")
    _run(r, "--yes")
    assert "nexwar_agent.service enabled" in (r / "etc/nexwar/disabled/state.txt").read_text()


def test_crontab里我们的行注释掉_撤回放回(tmp_path):
    r = _robot(tmp_path)
    cron = r / "var/spool/cron/crontabs"
    cron.mkdir(parents=True)
    (cron / "robot").write_text("@reboot /home/robot/d1max-motion/field-agent.sh\n"
                                "@reboot /opt/robot/vendor.sh\n")
    _run(r, "--yes")
    t = (cron / "robot").read_text()
    assert "#nexwar-disabled# @reboot /home/robot/d1max-motion" in t
    assert "\n@reboot /opt/robot/vendor.sh" in t, "厂家的行不动"
    _run(r, "--undo", "--yes")
    assert (cron / "robot").read_text().startswith("@reboot /home/robot/d1max-motion")


def test_每次都留检查报告_给工程师发回来(tmp_path):
    r = _robot(tmp_path)
    p = _run(r, "--check")
    rep = r / "var/log/nexwar-disable-report.txt"
    assert "检查报告" in p.stdout and rep.exists()
    t = rep.read_text()
    assert "没通过" in t and "停用记录: 没有" in t
    assert "nexwar_agent.service" in t and "enabled" in t
    _run(r, "--yes")
    t = rep.read_text()
    assert "停用之后整机重启过: 否" in t, "刚停用、还没重启"
    assert "原来: nexwar_agent.service enabled" in t and "停用做完" in t
    tmp_copy = r / "tmp/nexwar-disable-report.txt"
    assert tmp_copy.exists() and tmp_copy.stat().st_mode & 0o004, "不用 sudo 也读得到,好拷回 Windows"


def test_脚本够小_能塞进Windows一条命令():
    """Windows 那头把脚本 base64 后当一条 ssh 命令发过去,Windows 一条命令最长 32767 个字符。"""
    assert len(SCRIPT.read_bytes()) * 4 / 3 < 30000


WIN = ROOT / "deploy" / "windows"


def test_Windows双击程序_编码对_找得到脚本():
    """PowerShell 5.1 读没有 BOM 的文件按 GBK,中文就乱了;.cmd 在 chcp 之前就被解析,只能是 ASCII。"""
    ps1 = (WIN / "disable-robot.ps1").read_bytes()
    assert ps1.startswith(b"\xef\xbb\xbf"), "disable-robot.ps1 要存成带 BOM 的 UTF-8"
    text = ps1.decode("utf-8-sig")
    for want in ("disable.sh", "192.168.168.100", "192.168.234.1", "XG2WIFI_C40221", "-ne 13",
                 "sudo bash /tmp/nexwar-disable.sh $mode", "--check", "--undo --yes",
                 "base64 -w0 /tmp/nexwar-disable-report.txt", "GetFolderPath('Desktop')"):
        assert want in text, want
    cmd = (WIN / "disable-robot.cmd").read_bytes()
    cmd.decode("ascii")
    assert b"chcp 65001" in cmd and b"disable-robot.ps1" in cmd


def test_Windows发过去的那条命令在机器人上能还原脚本并跑(tmp_path):
    """照 disable-robot.ps1 的 Remote-Command 拼同一条命令(机器人上没 sudo 的假环境里去掉 sudo)。"""
    import base64
    r = _robot(tmp_path)
    b64 = base64.b64encode(SCRIPT.read_bytes().replace(b"\r", b"")).decode()
    out = tmp_path / "x.sh"
    line = (f"printf %s {b64} | base64 -d > {out} && bash {out} --check; "
            f"rc=$?; rm -f {out}; exit $rc")
    env = {**os.environ, "NEXWAR_DISABLE_ROOT": str(r),
           "PATH": f"{r.parent / 'bin'}:{os.environ['PATH']}"}
    p = subprocess.run(["bash", "-c", line], env=env, text=True, capture_output=True, timeout=60)
    assert p.returncode == 1 and "nexwar_agent.service" in p.stdout, p.stdout + p.stderr
    assert not out.exists()


def test_脚本能单独拷走用():
    """现场工程师只拿到这一个文件:不许引用仓库里别的文件。"""
    text = SCRIPT.read_text(encoding="utf-8")
    assert "$(dirname" not in text and "source " not in text
    assert SCRIPT.stat().st_mode & stat.S_IRUSR
