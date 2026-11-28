"""上装命令(W21,``deter``):开 / 关一路声光,放一段话术。**不是任务**(同 ``video``):不占任务槽,
巡检、去拦截点的路上照样能开;到点关由 HAL 那一层自己做(``max_s``)。

**喇叭的优先级仲裁在这里**(台账 W21「音频优先级仲裁」):同一时间只放一段。新来的比正在放的低,回
``busy``;一样高或更高的,打断正在放的。关喇叭不看优先级(让它安静永远可以)。警灯、警笛、聚光灯是开关,
后来的覆盖先前的(开的时间从现在重算)。

每次开、关都记一条 ``deter`` 事件(谁也不用猜狗刚才响没响过,W22 驱离要按它复盘)。

W40:聚光灯可以只开一边(``side``)、警灯可以挑颜色(``color``);狗的 HAL 在 ``deter_options`` 里报了
才认,不然回 ``unsupported``(站点按能力本来就不该发)。
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from typing import Any

from nexwar_contract.deter import MAX_S, OUTPUTS, parse_deter
from nexwar_contract.errors import ContractError
from nexwar_contract.hal import HalUnsupported
from nexwar_contract.messages import Command

log = logging.getLogger(__name__)


#: 喇叭命令等这么久(秒)还没做完就先回执、后台接着做(站点等回执 10 s)。
SPEAK_ACK_S = 3.0
#: 外审 1.1 第 12 轮:喇叭指令收下以后,准备(下载录音、转码、合成、连竞品主控)最长多久(秒)。
#: 准备期间优先级照占;过了还没起播就不放了(报 ``ended: failed``)。真正起播了再从起播时刻
#: 重算放到几点 —— 慢下载不吃掉播放的时长,保安的录音不会放到一半被低优先级的自动话术截掉。
PREP_S = 60.0


class DeterDesk:
    def __init__(self, hal: Any, *, emit: Callable[[str, dict[str, Any]], Any],
                 monotonic: Callable[[], float] = time.monotonic,
                 on_estop: Callable[[], Any] | None = None) -> None:
        self.hal = hal
        self._emit = emit
        self._mono = monotonic
        #: 正在放的那一段:(优先级, 放到单调钟几点)。放完了、被关了就是 None。
        self._sound: tuple[int, float] | None = None
        #: 外审:喇叭的仲裁(看优先级 → 起播 / 关 → 记下)一把锁做完,自动播报和手动喊话、关喇叭不交错
        self._speaker_lock = asyncio.Lock()
        #: 外审 1.1 #10:喇叭指令的代次。录音下载慢、后台放的,下完了代次变了(后来有人关了喇叭、
        #: 放了别的)就不放了。
        self._speak_gen = 0
        #: 外审 1.1 第 4 轮 #4:真正叫 HAL 起播 / 关的那一步排队(等功放、起播放器可能要好几秒);
        #: 排到的时候代次已经变了的不做 —— 最后生效的总是最新那条指令
        self._hal_lock = asyncio.Lock()
        #: 外审 1.1 第 5 轮 #3:``_sound`` 记的是哪一代指令的占用;HAL 上真正起播的是哪一代。
        #: HAL 回调「放完了」说的是正在放的那段 —— 后来已接受、还没起播(在下载、等功放)的那条的
        #: 占用不能被它清掉
        self._sound_gen = 0
        self._started_gen = 0
        #: 外审 1.1 第 12 轮:最近这条喇叭指令准备到几点(单调钟)为止,过了还没起播就不放
        self._prep_until = 0.0
        #: 1.1-4:跟站点搬录音(``talk.TalkLink``);没接(没有狗专用口)就不认 ``talk:``、``mic``。
        self.talk: Any = None
        #: 本体灯开着到点关(``max_s``):哪一路 → 关灯的那个任务
        self._light_off: dict[str, asyncio.Task[None]] = {}
        #: 喇叭放完、放坏了、到点了(W21 外审):HAL 回调过来,当场放开优先级、记一条事件。
        #: HAL 不报(仿真狗)就按 ``max_s`` 算。
        listen = getattr(hal, "set_sound_listener", None)
        if callable(listen):
            listen(self._sound_ended)
        # POC 11-06:竞品上装的求助、急停按钮按下了 → 一条 ``payload_button`` 事件(站点出告警、叫停)
        buttons = getattr(hal, "set_button_listener", None)
        if callable(buttons):
            def pressed(name: str) -> None:
                self._emit("payload_button", {"button": name})
                if name == "estop" and on_estop is not None:
                    on_estop()                       # 外审 POC r1 C1:代理当场中止任务,不等站点
            buttons(pressed)

    def _sound_ended(self, ok: bool, why: str) -> None:
        if self._sound is not None and self._sound_gen != self._started_gen:
            # 外审 1.1 第 5 轮 #3:放完的是旧的一段,后来接受的那条还没起播:它的优先级照样占着
            log.info("旧的一段放完了(%s);后来接受的喇叭指令还没起播,优先级不放开", why)
            return
        self._sound = None
        self._emit("deter", {"output": "speaker", "on": False,
                             "ended": "done" if ok else "failed", "reason": why[:200]})

    def outputs(self) -> list[str]:
        acts = self.hal.hal_capabilities().actuators
        # 1.1-4:听回话要 HAL 能录(``mic``)、还要能传回站点
        return [o for o in OUTPUTS if acts.get(o) and (o != "mic" or self.talk is not None)]

    def caps(self) -> dict[str, Any] | None:
        """``capabilities.tasks.deter``:接了哪几路、喇叭能放哪些话术、能不能 TTS。
        一路都没接 → None。"""
        outs = self.outputs()
        if not outs:
            return None
        d: dict[str, Any] = {"outputs": outs, "max_s": MAX_S} | self.options()
        if "speaker" in outs:
            clips = getattr(self.hal, "sound_clips", None)
            tts = getattr(self.hal, "sound_tts", None)
            d["clips"] = list(clips()) if callable(clips) else []
            d["tts"] = bool(tts()) if callable(tts) else False
            # 第三档 #41:能念哪几种语言(竞品只会中文,英文靠 Orin 上合成);HAL 不说就不报(老站点照旧)
            langs = getattr(self.hal, "sound_tts_langs", None)
            got = langs() if callable(langs) else None
            if got is not None:
                d["tts_langs"] = [str(x) for x in got]
            d["talk"] = self.talk is not None             # 1.1-4:能放按住说话录的那一段
        return d

    def options(self) -> dict[str, Any]:
        """W40:聚光灯分不分左右、警灯有哪些颜色、警笛怎么响(HAL 不报就是都没有)。"""
        fn = getattr(self.hal, "deter_options", None)
        opts = fn() if callable(fn) else {}
        got = {k: opts[k] for k in ("spotlight_sides", "strobe_colors", "strobe_default",
                                    "siren_via") if k in opts}
        if "light" in self.outputs():
            got["light_sides"] = ["front", "back"]       # 本体灯(HAL light 的 front / back / both)
        return got

    async def aim_at(self, bearing_deg: float) -> None:
        """POC 11-06:确认看见人,云台转过去(``bearing_deg`` 狗身系,朝左为正;云台向右为正)。
        没云台不动;转不了记日志,不打断别的。"""
        if "ptz" not in self.outputs():
            return
        pan = -float(bearing_deg)
        pan = (pan + 180.0) % 360.0 - 180.0
        try:
            await self.hal.ptz(pan, 0.0)
        except Exception as exc:                     # noqa: BLE001 - 自己转的没转成:记日志
            log.warning("看见人,云台没转过去: %s", exc)
            return
        self._emit("deter", {"output": "ptz", "on": True, "pan": pan, "tilt": 0.0,
                             "auto": "person_seen"})

    def playing(self) -> tuple[int, float] | None:
        if self._sound is not None and self._mono() >= self._sound[1]:
            self._sound = None
        return self._sound

    async def auto_sound(self, clip: str, *, priority: int, max_s: float, why: str) -> bool:
        """机器人自己按情况放一段录好的话术(POC 11-05,:mod:`nexwar_agent.autovoice`)。
        这台没有这段、没接喇叭、正在放的不比它低:不放(回 False,不报错)。放了记一条 ``deter`` 事件,
        带 ``auto`` = 为什么放的。"""
        if "speaker" not in self.outputs():
            return False
        clips = getattr(self.hal, "sound_clips", None)
        if not callable(clips) or clip not in clips():
            return False
        async with self._speaker_lock:
            cur = self.playing()
            if cur is not None and cur[0] >= priority:
                return False
            self._speak_gen += 1
            try:
                await self._hal_sound(clip, max_s, self._speak_gen)
            except Exception as exc:                 # noqa: BLE001 - 自己放的没放成:记日志,不打断别的
                log.warning("自动放 %s 没放成: %s", clip, exc)
                return False
            self._sound = (priority, self._mono() + max_s)
            self._sound_gen = self._speak_gen
        self._emit("deter", {"output": "speaker", "on": True, "max_s": max_s, "clip": clip,
                             "priority": priority, "auto": why})
        return True

    async def handle(self, cmd: Command) -> str:
        """回空串 = 做了;否则拒收的理由。"""
        try:
            req = parse_deter(cmd.payload)
        except ContractError as exc:
            return f"payload: {exc}"
        if req.output not in self.outputs():
            return "unsupported"
        opts = self.options()
        sides = opts.get("light_sides" if req.output == "light" else "spotlight_sides", [])
        if req.side != "both" and req.side not in sides:
            return ("unsupported: 此机器人的本体灯不分前后" if req.output == "light"
                    else "unsupported: 此机器人的聚光灯不分左右")
        if req.color and req.color not in opts.get("strobe_colors", []):
            return f"unsupported: 警灯没有 {req.color} 色"
        if req.output == "speaker":
            async with self._speaker_lock:
                return await self._do(cmd, req)
        return await self._do(cmd, req)

    async def _light(self, side: str, on: bool, max_s: float) -> None:
        """本体灯(真机 11-20):开了 ``max_s`` 秒到点自己关;关、再开都把前一个到点关的撤掉。"""
        for k in (("front", "back") if side == "both" else (side,)):
            old = self._light_off.pop(k, None)
            if old is not None:
                old.cancel()
        await self.hal.light(side, on)
        log.info("本体灯 %s %s(上装命令%s)", side, "开" if on else "关",
                 f",{max_s:g} 秒后自己关" if on else "")
        if on:
            async def off_later(k: str) -> None:
                await asyncio.sleep(max_s)
                try:
                    await self.hal.light(k, False)
                    self._emit("deter", {"output": "light", "on": False, "side": k,
                                         "ended": "timeout"})
                except Exception:
                    log.exception("本体灯到点关没成")
                self._light_off.pop(k, None)
            for k in (("front", "back") if side == "both" else (side,)):
                self._light_off[k] = asyncio.create_task(off_later(k))

    async def _sound_now(self, cmd: Command, req: Any) -> None:
        """喇叭:``SPEAK_ACK_S`` 内做完(或当场出错)照常;没做完 —— 合成、连竞品主控、ssh 慢 —— 先回执
        收下,后台接着做,后台没做成发 ``ended: failed``(站点出「喊话没放出来」)。
        真机 11-20:喊话回执超过 10 s,站点等不到回 504,人以为没发出去。"""
        gen = self._speak_gen
        self._prep_until = prep = self._mono() + PREP_S
        if req.on and req.clip.startswith("talk:"):
            if self.talk is None:
                raise HalUnsupported("这台机器人放不了站点的录音(没接机器人专用口)")
            t = asyncio.ensure_future(self._talk_play(req, gen, prep))  # 1.1-4:先拉下来
        else:
            t = asyncio.ensure_future(self._hal_sound(req.clip if req.on else "", req.max_s, gen,
                                                      prep if req.on else None))
        try:
            await asyncio.wait_for(asyncio.shield(t), SPEAK_ACK_S)
            return
        except asyncio.TimeoutError:
            pass
        log.warning("喊话 %g 秒内没起来(合成、连竞品慢):先回执收下,后台接着做", SPEAK_ACK_S)

        def done(f: asyncio.Future) -> None:
            if f.cancelled() or f.exception() is None:
                return
            log.warning("喊话后台没做成: %s", f.exception())
            if gen != self._speak_gen:
                # 外审 1.1 第 2 轮 #10:后来又有喇叭指令(可能优先级更高、正在放):不动它的状态
                return
            if req.on:
                self._sound = None
            self._emit("deter", {"task_id": cmd.task_id, "output": "speaker", "on": False,
                                 "ended": "failed", "reason": str(f.exception())[:200]})
        t.add_done_callback(done)

    async def _talk_play(self, req: Any, gen: int, prep: float) -> None:
        path = await self.talk.fetch(req.clip)
        if gen != self._speak_gen:
            # 下载期间有人关了喇叭、放了别的(可能优先级更高):这段不放了。检查和起播之间没有 await
            log.info("录音 %s 下完时已经被后来的喇叭指令取代,不放", req.clip)
            return
        await self._hal_sound(f"talk:{path}", req.max_s, gen, prep)

    async def _hal_sound(self, clip: str, max_s: float, gen: int,
                         prep: float | None = None) -> None:
        """叫 HAL 放 / 关(排队);排到时已经有更新的喇叭指令就不做。

        ``prep``:外审 1.1 第 12 轮 —— 准备到这个时刻(单调钟)还没轮到起播就不放了(抛错,
        后台回调报 ``ended: failed``、放开优先级);起播了从起播时刻重算放到几点。"""
        async with self._hal_lock:
            if gen != self._speak_gen:
                log.info("喇叭指令 %r 排到时已被后来的指令取代,不做", clip or "关")
                return
            if prep is None:
                await self.hal.sound(clip, max_s)
            else:
                await self._sound_by(clip, max_s, prep)
            self._started_gen = gen
            if clip and self._sound is not None and self._sound_gen == gen:
                self._sound = (self._sound[0], self._mono() + max_s)

    async def _sound_by(self, clip: str, max_s: float, prep: float) -> None:
        """外审 1.1 第 13 轮 #1:HAL 起播(等功放、起播放器、连竞品主控)也算进准备的截止时间 ——
        到点还没起来就取消、再叫一次关喇叭清掉可能半起来的,抛错(后台回调报 failed、放开优先级)。
        按单调钟(``monotonic``)每 0.1 秒看一次,跟优先级用的是同一个钟。"""
        if self._mono() > prep:
            raise RuntimeError(f"准备超过 {PREP_S:g} 秒还没起播,不放了")
        t = asyncio.ensure_future(self.hal.sound(clip, max_s))
        while not t.done():
            try:
                await asyncio.wait({t}, timeout=0.1)
            except asyncio.CancelledError:
                t.cancel()                           # 自己被取消:起播也一起取消
                raise
            if not t.done() and self._mono() > prep:
                t.cancel()
                await asyncio.wait({t})              # 等它真退出(不往外抛它的取消)
                if not t.cancelled() and t.exception() is not None:
                    log.info("准备超时取消起播时它出错了: %s", t.exception())
                try:
                    await self.hal.sound("", 0)
                except Exception:                    # 关不掉也照样报没放成
                    log.exception("准备超时后关喇叭没成")
                raise RuntimeError(f"准备超过 {PREP_S:g} 秒还没起播,不放了")
        t.result()

    async def _listen(self, cmd: Command, req: Any) -> None:
        """1.1-4 听回话:录 ``max_s`` 秒、传回站点;成没成都记一条 ``deter`` 事件。"""
        try:
            data = await self.hal.record(req.max_s)
            await self.talk.upload(req.clip, data)
        except Exception as exc:                     # noqa: BLE001 - 录不了、传不上:告诉站点
            log.warning("听回话没成: %s", exc)
            self._emit("deter", {"task_id": cmd.task_id, "output": "mic", "on": False,
                                 "ended": "failed", "reason": str(exc)[:200], "clip": req.clip})
            return
        self._emit("deter", {"task_id": cmd.task_id, "output": "mic", "on": False,
                             "ended": "done", "clip": req.clip})

    async def _do(self, cmd: Command, req: Any) -> str:
        if req.output == "speaker" and req.on:
            cur = self.playing()
            if cur is not None and req.priority < cur[0]:
                return "busy"
        if req.output == "speaker":
            self._speak_gen += 1
        try:
            if req.output == "strobe":
                await self.hal.strobe(req.color or "warn", "flash" if req.on else "off",
                                      req.max_s)
            elif req.output == "siren":
                await self.hal.siren(req.on, req.max_s)
            elif req.output == "spotlight" and req.side != "both":
                await self.hal.spotlight_side(req.side, req.on, req.max_s)
            elif req.output == "spotlight":
                await self.hal.spotlight(req.on, req.max_s)
            elif req.output == "wiper":
                await self.hal.wiper(req.on, req.max_s)
            elif req.output == "ptz":
                await self.hal.ptz(req.pan, req.tilt)
            elif req.output == "light":
                await self._light(req.side, req.on, req.max_s)
            elif req.output == "mic":
                if not req.on:
                    return ""
                self._listening = asyncio.ensure_future(self._listen(cmd, req))
            else:
                await self._sound_now(cmd, req)
        except HalUnsupported:
            return "unsupported"
        except Exception as exc:                     # noqa: BLE001 - 设备的错原样回给站点(继电器板没回…)
            log.warning("上装 %s 没做成: %s", req.output, exc)
            return f"device: {str(exc)[:200]}"
        if req.output == "speaker":
            if not req.on:
                self._sound = None
            elif self._started_gen == self._speak_gen:      # 已经起播了:从现在放 max_s
                self._sound = (req.priority, self._mono() + req.max_s)
            else:
                # 外审 1.1 第 12 轮:还在准备(下载、转码…):占到准备截止 + 播放时长,起播时重算
                self._sound = (req.priority, self._prep_until + req.max_s)
            self._sound_gen = self._speak_gen
        data: dict[str, Any] = {"task_id": cmd.task_id, "output": req.output, "on": req.on}
        if req.output == "ptz":
            data |= {"pan": req.pan, "tilt": req.tilt}
        elif req.on:
            data["max_s"] = req.max_s
        if req.side != "both":
            data["side"] = req.side
        if req.color:
            data["color"] = req.color
        if req.output == "mic" and req.on:
            data["clip"] = req.clip
        if req.output == "speaker" and req.on:
            data |= {"clip": req.clip[:64] if not req.clip.startswith("tts:") else "tts",
                     "priority": req.priority}
        self._emit("deter", data)
        return ""
