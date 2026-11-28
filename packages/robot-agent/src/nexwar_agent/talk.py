"""1.1-4 远程喊话(按住说话)+ 听回话:跟站点之间搬录音(设计 ``docs/1.1-4-远程喊话-设计.md``)。

- **按住说话**:保安在 App / 网页上按住说话、松开,录音存在站点;站点发喇叭命令 ``clip =
  talk:<编号>``。这里从狗专用口(mTLS,跟拉地图同一套证书)``GET /talk/<编号>`` 拉下来,用 ffmpeg 转成
  48 kHz 双声道 s16 的 wav(跟英文合成同一个格式,竞品 dmix、自己的声卡都放得了),交给 HAL 放。
- **听回话**:站点发 ``mic`` 命令(带编号、最多 20 秒);HAL 录一段 wav,这里 ``POST /talk/<编号>`` 传回
  站点。

录音只在这台机器人上留到放完(``work`` 目录里最多留 :data:`KEEP` 个,老的删掉)。
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

TALK_ID = re.compile(r"^talk:([0-9a-f]{16})$")
#: 站点给的录音最多多大(字节)。
MAX_BYTES = 2 * 1024 * 1024
KEEP = 20
#: 外审 1.1 第 2 轮后第 3 轮 #7:转出来的最多放多久(按住说话最多 30 秒,前后各垫 0.3 秒)、
#: 一段最大多少字节(48 kHz 双声道 s16),缓存一共最多多少字节。压得很小的长录音不许撑满磁盘
MAX_PLAY_S = 31.0
MAX_OUT_BYTES = int(MAX_PLAY_S * 48000 * 2 * 2) + 4096
KEEP_BYTES = 64 * 1024 * 1024
TIMEOUT_S = 20.0
CONVERT_TIMEOUT_S = 20.0


class TalkError(RuntimeError):
    pass


class TalkLink:
    def __init__(self, base_url: str, ssl_context: Any, work: Path, *,
                 ffmpeg: str = "ffmpeg") -> None:
        self.base = base_url.rstrip("/")
        self.ctx = ssl_context
        self.work = Path(work)
        self.ffmpeg = ffmpeg

    def _get(self, tid: str) -> bytes:
        req = urllib.request.Request(f"{self.base}/talk/{tid}")
        try:
            with urllib.request.urlopen(req, context=self.ctx, timeout=TIMEOUT_S) as r:
                data = r.read(MAX_BYTES + 1)
        except urllib.error.HTTPError as exc:
            raise TalkError(f"站点不给这段录音(HTTP {exc.code})") from exc
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            raise TalkError(f"连不上站点拉录音:{exc}") from exc
        if len(data) > MAX_BYTES:
            raise TalkError("录音太大")
        return data

    def _post(self, tid: str, data: bytes) -> None:
        req = urllib.request.Request(f"{self.base}/talk/{tid}", data=data, method="POST",
                                     headers={"Content-Type": "audio/wav"})
        try:
            with urllib.request.urlopen(req, context=self.ctx, timeout=TIMEOUT_S) as r:
                r.read(1024)
        except urllib.error.HTTPError as exc:
            raise TalkError(f"站点不收回话(HTTP {exc.code})") from exc
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            raise TalkError(f"连不上站点传回话:{exc}") from exc

    async def fetch(self, clip: str) -> Path:
        """``talk:<编号>`` → 转好的 wav 路径。"""
        m = TALK_ID.match(clip)
        if m is None:
            raise TalkError(f"不是站点的录音:{clip!r}")
        tid = m.group(1)
        self.work.mkdir(parents=True, exist_ok=True)
        out = self.work / f"talk-{tid}.wav"
        if out.is_file():
            return out
        raw = await asyncio.to_thread(self._get, tid)
        src = self.work / f"talk-{tid}.src"
        part = self.work / f"talk-{tid}.part.wav"      # 转成了才改名:半截的不当成放得了的
        src.write_bytes(raw)
        ok = False
        try:
            try:
                proc = await asyncio.create_subprocess_exec(
                    self.ffmpeg, "-nostdin", "-y", "-loglevel", "error", "-i", str(src),
                    "-af", "adelay=300|300,apad=pad_dur=0.3", "-ar", "48000", "-ac", "2",
                    "-sample_fmt", "s16", "-t", f"{MAX_PLAY_S:g}", "-fs", str(MAX_OUT_BYTES),
                    str(part),
                    stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE)
            except OSError as exc:
                raise TalkError(f"ffmpeg 起不来:{exc}") from exc
            try:
                _, err = await asyncio.wait_for(proc.communicate(), CONVERT_TIMEOUT_S)
            except asyncio.TimeoutError as exc:
                with contextlib.suppress(ProcessLookupError):
                    proc.kill()
                with contextlib.suppress(Exception):
                    await proc.wait()
                raise TalkError("录音转码超时") from exc
            if proc.returncode != 0 or not part.is_file():
                raise TalkError("录音转码失败:" + (err or b"").decode("utf-8", "replace")[:150])
            if part.stat().st_size > MAX_OUT_BYTES:
                raise TalkError("录音转出来太大")
            part.replace(out)
            ok = True
        finally:
            with contextlib.suppress(OSError):
                src.unlink()
            if not ok:
                with contextlib.suppress(OSError):
                    part.unlink()
        self._prune()
        return out

    async def upload(self, clip: str, data: bytes) -> None:
        m = TALK_ID.match(clip)
        if m is None:
            raise TalkError(f"不是站点的录音编号:{clip!r}")
        if not data:
            raise TalkError("没录到声音")
        await asyncio.to_thread(self._post, m.group(1), data[:MAX_BYTES])

    def _prune(self) -> None:
        files = sorted(self.work.glob("talk-*.wav"), key=lambda f: f.stat().st_mtime,
                       reverse=True)
        total = 0
        for i, f in enumerate(files):
            with contextlib.suppress(OSError):
                total += f.stat().st_size
                if i >= KEEP or (i > 0 and total > KEEP_BYTES):
                    f.unlink()
