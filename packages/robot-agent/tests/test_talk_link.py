"""1.1-4 机器人拉站点录音转码(外审 1.1 第 3 轮 #7):压得很小的长录音转出来不许撑满磁盘。"""

from __future__ import annotations

import shutil
import subprocess
import wave

import pytest

from nexwar_agent import talk
from nexwar_agent.talk import TalkLink

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="没装 ffmpeg")


async def test_外审1_1_第3轮_7_长录音转码截到上限_缓存有总字节上限(tmp_path, monkeypatch):
    src = tmp_path / "long.webm"
    subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-f", "lavfi", "-i",
                    "anullsrc=r=8000:cl=mono", "-t", "120", "-c:a", "libopus", "-b:a", "6k",
                    str(src)], check=True)
    raw = src.read_bytes()
    assert len(raw) < talk.MAX_BYTES
    link = TalkLink("https://site", None, tmp_path / "work")
    monkeypatch.setattr(link, "_get", lambda tid: raw)
    out = await link.fetch("talk:0123456789abcdef")
    with wave.open(str(out)) as w:
        secs = w.getnframes() / w.getframerate()
    assert secs <= talk.MAX_PLAY_S + 0.1, secs
    assert out.stat().st_size <= talk.MAX_OUT_BYTES
    assert not list((tmp_path / "work").glob("*.part.wav")) and not list(
        (tmp_path / "work").glob("*.src"))
    monkeypatch.setattr(talk, "KEEP_BYTES", out.stat().st_size + 10)
    out2 = await link.fetch("talk:fedcba9876543210")
    assert out2.is_file() and not out.exists(), "超了总字节:老的删掉,新的留着"


async def test_转码失败_半截文件不留(tmp_path, monkeypatch):
    link = TalkLink("https://site", None, tmp_path / "work")
    monkeypatch.setattr(link, "_get", lambda tid: b"not audio")
    with pytest.raises(talk.TalkError):
        await link.fetch("talk:0123456789abcdef")
    assert list((tmp_path / "work").iterdir()) == []
