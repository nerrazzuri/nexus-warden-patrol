"""跟人任务(W74 二期;规矩见 :mod:`nexwar_contract.follow`)。

一段一段走:每段是一趟单点 ``goto``(:class:`~nexwar_agent.tasks.engine_goto.EngineGotoTask`,
同一个任务号),
目标是人后方 ``keep_m``、朝着人;走着的时候人挪开了 :data:`RETARGET_M` 以上,就让引擎**中途换目标**
(:meth:`~nexwar_agent.engine.machine.MissionEngine.retarget`,不停车),最快每 :data:`RETARGET_EVERY_S`
秒一次。一段走到了、人还在 ``keep_m`` 附近 → 站着等;人又走远了 → 再起一段。

**人在哪**:人员检测此刻看到的每一个人(方向 + 距离,狗身系)加上此刻的地图位姿,算出地图上的点。
连起来跟同一个人(外审 r1 #9):先在这些点里找离被跟的人最近、又在人能走到的范围里
(:data:`GATE_M` + :data:`PERSON_MAX_MPS` × 隔了多久)的那个;旁边有更近的别人也不换。被跟的人
:data:`SWITCH_S` 秒没看到以后才谁近跟谁。只有方向、没测到距离的不算(不知道在哪)。

**到上限**(外审 W77-1 #4,原来外审 r1 #8 的往回收尾去掉了):不再往前追,原地守着,人靠近照样退,
人看不到 ``lost_s`` 秒才收尾(``result: limit``)。

**跟丢**(``lost_s`` 秒没看到被跟的人、规划不出去人那儿的路)、**到上限**(``max_s`` / ``max_m``)→
走着的
那一段停下,回最后看见人的地方、朝人离开的方向(没算出方向就朝人最后所在的方向),到了任务 ``DONE``,
``result`` 写 ``lost`` / ``limit``。一开始就没看到过人:原地不动,到时限按跟丢收。半路电量到线、引擎
返航:任务失败(不再跟)。中止、抢占:那一段停稳再终态。
"""

from __future__ import annotations

import logging
import math
from collections import deque
from collections.abc import Callable
from typing import Any

from nexwar_agent.assembly import EngineParts
from nexwar_agent.engine.mission import Policy
from nexwar_agent.tasks.base import Task
from nexwar_agent.tasks.engine_goto import EngineGotoTask
from nexwar_contract.charging import ALARM_FLOOR_PCT, ALARM_PRIORITY
from nexwar_contract.follow import BACK_M, CLEAR_M, TRACK_EVERY_S, TRACK_KEEP, FollowRequest
from nexwar_contract.messages import MapPose, TaskState

log = logging.getLogger(__name__)

#: 目标挪开这么多(米)才换目标;最快多久换一次(秒)。
RETARGET_M = 1.0
RETARGET_EVERY_S = 1.0
#: 离人比 ``keep_m`` 远这么多(米)才起新的一段。要比退到的 :data:`CLEAR_M` 远(4.5 + 1 = 5.5 m),
#: 不然刚退到 5 m 又往前跟。
START_EXTRA_M = 1.0
#: 退过以后等停稳:这么久(秒)还没确认停稳,重发停车、报一次 ``follow_stop_unconfirmed``;一直不放行
#: (不起导航段、不进终态,外审 W77-2 #1)。
STOP_CONFIRM_TIMEOUT_S = 5.0
#: 查限速区时看身边多远(米):退一下(1.5 秒 × 0.3 m/s)加机身。
BACK_REACH_M = 1.0
#: 退的时候,人要是这么久(毫秒)以内看到的才算数;看不到了就不退(不知道往哪退)。
BACK_FRESH_MS = 500
#: 退的速度命令有效期(毫秒):一拍不来 HAL 自己停。
BACK_CMD_TTL_MS = 300
#: 认同一个人:人最快走多快(米/秒)、再宽出这么多(米)。
PERSON_MAX_MPS = 3.0
GATE_M = 1.5
#: 被跟的人多久没看到以后,谁近跟谁(秒)。
SWITCH_S = 2.0
#: 人走了这么远(米)才算得出方向。
HEADING_MIN_M = 0.8
#: 方向按最近这么久(秒)的轨迹算。
HEADING_SPAN_S = 4.0
#: 每隔这么久(秒)记一个轨迹点。
TRACK_STEP_S = 0.5


class FollowTask(Task):
    def __init__(self, *, task_id: str, req: FollowRequest, parts: EngineParts, events: Any,
                 now_ms: Callable[[], int], wall_ms: Callable[[], int],
                 targets: Callable[[], list[tuple[float, float]]],
                 here: Callable[[], tuple[float, float, float] | None],
                 map_ref: tuple[str, str], priority: int = 80,
                 hal: Any = None, backoff: Any = None) -> None:
        super().__init__(task_id=task_id, kind="follow", priority=priority)
        self.req = req
        self._parts = parts
        self._events = events
        self._mono = now_ms
        self._wall = wall_ms
        self._targets = targets
        self._here = here
        self._map = map_ref
        #: ``follow`` 跟着;``back`` 回最后看见人的地方;收尾了按 ``_result`` 进终态。
        self.phase = "follow"
        self._leg: EngineGotoTask | None = None
        self._leg_goal: tuple[float, float] | None = None
        self._leg_n = 0
        self._retarget_at = -math.inf
        self._t0 = 0
        self._dist_m = 0.0
        self._prev_here: tuple[float, float] | None = None
        #: 被跟的人:最后一次在哪、什么时候(单调毫秒)。
        self._person: tuple[float, float] | None = None
        self._seen_ms = 0
        #: 轨迹:``(单调毫秒, x, y, 墙钟毫秒)``。
        self._track: deque[tuple[int, float, float, int]] = deque(maxlen=TRACK_KEEP)
        self._unsent: list[dict[str, Any]] = []
        self._sent_at = 0
        self._result = ""
        self._abort_reason: str | None = None
        self._final: tuple[TaskState, dict[str, Any]] | None = None
        #: 跟丢 / 到上限了、还没起回最后位置的那一段。
        self._pending_back = False
        #: 用户 11-15:人走近就退(:class:`~nexwar_agent.tasks.standoff.Backoff`)。
        #: 没给就不退(老装配)。
        self._hal = hal
        self._backoff = backoff
        #: ``""`` 没在退;``retreat`` 在退;``cornered`` 退不了、原地站定。
        self._backing = ""
        self._vseq = 0
        #: 退过以后发了停车、还没确认停稳:等了多久(秒);``None`` 不用等(外审 W77-1 #3:停稳之前
        #: 不起导航段、不进终态;停车出错也不清这一笔)。
        self._stop_wait: float | None = None
        self._stop_alarmed = False
        #: 不安全的断线(外审 W77-1 #2):停车、不退、不起新的一段,连回来再接着。
        self._paused = False

    @property
    def aborting(self) -> bool:
        return self._abort_reason is not None and not self.done

    # ------------------------------------------------------------ 能力里给站点看的

    def caps(self) -> dict[str, Any]:
        d: dict[str, Any] = {"state": "idle" if self.done else (self._backing or self.phase)}
        if self._person is not None:
            d["person"] = {"x": round(self._person[0], 2), "y": round(self._person[1], 2)}
        return d

    # ------------------------------------------------------------ 生命周期

    async def start(self) -> None:
        self.state = TaskState.RUNNING
        self._t0 = self._mono()
        self._seen_ms = self._t0
        self._sent_at = self._t0
        log.info("跟人 %s 开始:保持 %.1f m,最多 %d 秒 / %.0f m", self.task_id, self.req.keep_m,
                 self.req.max_s, self.req.max_m)

    async def abort(self, reason: str) -> None:
        if self.done:
            return
        self._abort_reason = reason or "abort"
        if self._leg is not None and not self._leg.done:
            await self._leg.abort(self._abort_reason)

    async def on_offline(self, safe: bool) -> None:
        # 跟随在机器人上做:断网照样跟(设计 §三)。不安全的断线才暂停:那一段交给它自己,
        # 往后退的这边停车、不再退(外审 W77-1 #2)。
        if not safe:
            self._paused = True
            await self._stop_backing()
        if self._leg is not None and not self._leg.done:
            await self._leg.on_offline(safe)

    async def on_online(self) -> None:
        self._paused = False
        if self._leg is not None and not self._leg.done:
            await self._leg.on_online()

    # ------------------------------------------------------------ 每拍

    async def step(self, dt_s: float) -> None:
        if self.state is not TaskState.RUNNING:
            return
        now = self._mono()
        here = self._here()
        if here is not None:
            if self._prev_here is not None:
                self._dist_m += math.dist(self._prev_here, here[:2])
            self._prev_here = (here[0], here[1])
        if self._leg is not None:
            await self._leg.step(dt_s)
            if self._leg.done:
                leg, self._leg, self._leg_goal = self._leg, None, None
                if self._leg_finished(leg):
                    return
        if (self._abort_reason is not None or self._final is not None) \
                and not await self._settled(dt_s):
            return
        if self._abort_reason is not None:
            if self._leg is None:
                self.state = (TaskState.PREEMPTED if self._abort_reason == "preempted"
                              else TaskState.ABORTED)
                self.detail = {"reason": self._abort_reason, **self._report()}
            return
        if self._final is not None:
            if self._leg is None:
                self.state, self.detail = self._final
            return
        self._observe(now, here)
        self._send_track(now)
        if self._paused:
            await self._stop_backing()
            await self._stop_confirmed(dt_s)
            return
        if self._leg is None:
            low = await self._battery_low()
            if low:
                # 外审 W77-5 #1:没有导航段(在退、在守着)时电量也要管;有导航段的引擎自己管
                log.warning("跟人 %s:%s,原地停下收尾", self.task_id, low)
                await self._stop_backing()
                self._final = (TaskState.FAILED, {"reason": f"跟人途中{low},原地停下"[:200],
                                                  **self._report()})
                return
        if await self._keep_off(now, here, dt_s):
            return
        if not await self._stop_confirmed(dt_s):
            return                                       # 退过的那一下停稳了,才起导航段
        if self.phase == "follow":
            await self._follow(now, here)
        elif self.phase == "keep":
            if self._leg is not None and not self._leg.aborting:
                await self._leg.abort("follow_limit")     # 到上限:不再往前追
        elif self._pending_back and self._final is None:
            if self._leg is not None:
                if not self._leg.aborting:
                    await self._leg.abort("follow_back")     # 先停下跟着的那一段
            else:
                self._pending_back = False
                await self._go_back()

    def _leg_finished(self, leg: EngineGotoTask) -> bool:
        """一段走完了;回 True = 任务这一拍已经收尾。"""
        if leg.state is TaskState.FAILED:
            why = str(leg.detail.get("reason", ""))
            if why == "stop_unconfirmed" and self._stop_wait is None:
                self._stop_wait = 0.0                     # 外审 W77-3 #1:接着等停稳,别的都先不动
            if self._parts.engine.returned or "返航" in why:
                # 外审 W77-4 #1:跟别的收尾一样,停稳了才进终态
                self._final = (TaskState.FAILED, {"reason": f"跟人途中电量到线、返航:{why}"[:200],
                                                  **self._report()})
                return False
            if self.phase == "back":
                # 回最后位置也走不到:停在这儿,照样算跟丢收尾
                self._final = (TaskState.DONE, {"result": self._result or "lost",
                                                "reason": f"回不到最后看见人的地方:{why}"[:200],
                                                **self._report()})
                return False
            log.info("跟人 %s:去人那儿的路走不通(%s),按跟丢办", self.task_id, why)
            self._lose("lost")
            return False
        if self.phase == "back" and leg.state is TaskState.DONE:
            self._final = (TaskState.DONE, {"result": self._result, **self._report()})
        return False

    # ------------------------------------------------------------ 人在哪

    def _observe(self, now: int, here: tuple[float, float, float] | None) -> None:
        obs = self._targets() or []
        p = None
        if obs and here is not None:
            pts = []
            for b, r in obs:
                a = here[2] + math.radians(b)
                pts.append((here[0] + r * math.cos(a), here[1] + r * math.sin(a)))
            p = self._pick(pts, here, now)
            if p is not None:
                self._person, self._seen_ms = p, now
                if not self._track or now - self._track[-1][0] >= TRACK_STEP_S * 1000:
                    self._track.append((now, p[0], p[1], self._wall()))
                    self._unsent.append({"x": round(p[0], 2), "y": round(p[1], 2),
                                         "at_ms": self._wall()})
                if self.phase == "back" and self._result == "lost":
                    log.info("跟人 %s:又看见了,接着跟", self.task_id)
                    self.phase, self._result, self._pending_back = "follow", "", False
        if self.phase == "keep" and self._final is None \
                and now - self._seen_ms >= self.req.lost_s * 1000:
            log.info("跟人 %s:到上限以后守着,人看不到了,收尾", self.task_id)
            self._final = (TaskState.DONE, {"result": "limit", **self._report()})
            return
        if self.phase != "follow" or self._final is not None:
            return
        if now - self._seen_ms >= self.req.lost_s * 1000:
            self._lose("lost")
        elif now - self._t0 >= self.req.max_s * 1000 or self._dist_m >= self.req.max_m:
            self._lose("limit")

    def _pick(self, pts: list[tuple[float, float]], here: tuple[float, float, float],
              now: int) -> tuple[float, float] | None:
        """这一帧里哪个是被跟的人:还认得的(在人能走到的范围里)取离上一个位置最近的;好一会儿没看到
        (或者还没开始跟)取离机器人最近的;都不像回 ``None``。"""
        gap_s = (now - self._seen_ms) / 1000
        if self._person is None or gap_s >= SWITCH_S:
            return min(pts, key=lambda q: math.dist(q, here[:2]))
        prev = self._person
        best = min(pts, key=lambda q: math.dist(q, prev))
        return best if math.dist(best, prev) <= GATE_M + PERSON_MAX_MPS * gap_s else None

    async def _keep_off(self, now: int, here: tuple[float, float, float] | None,
                        dt_s: float = 0.0) -> bool:
        """用户 11-15:人走近到 :data:`BACK_M` 以内 → 停下这一段、往远离人的方向退,
        退到 :data:`CLEAR_M` 以外再接着跟;退不了原地站定、发 ``follow_cornered``(一次)。
        回 True = 这一拍在退(别的不办)。"""
        if self._backoff is None or self._hal is None or self._final is not None:
            return False
        d = None
        if self._person is not None and here is not None and now - self._seen_ms <= BACK_FRESH_MS:
            d = math.dist(self._person, here[:2])
        if d is None or d >= (CLEAR_M if self._backing else BACK_M):
            if self._backing:
                log.info("跟人 %s:离人够远了,接着跟", self.task_id)
                await self._stop_backing()
            return False
        if self._leg is not None:
            if not self._leg.aborting:
                log.info("跟人 %s:人走近到 %.1f m,停下往后退", self.task_id, d)
                if self.phase == "back":
                    self._pending_back = True            # 退完再接着回最后位置
                await self._leg.abort("follow_backoff")
            return True                                  # 这一段停稳了再退
        if not await self._stop_confirmed(dt_s):
            return True                                  # 上一下(导航段或后退)还没停稳:先不退
        assert here is not None and self._person is not None
        b = math.degrees(math.atan2(self._person[1] - here[1], self._person[0] - here[0]) - here[2])
        b = (b + 180.0) % 360.0 - 180.0
        cmd, why = self._backoff.choose(b, d, max_v=self._back_speed(here))
        if cmd is None:
            if self._backing != "cornered":
                log.warning("跟人 %s:人在 %.1f m,退不了,原地站定(%s)", self.task_id, d, why)
                self._events.emit("follow_cornered", {"task_id": self.task_id,
                                                      "range_m": round(d, 2), "why": why,
                                                      **self._last()})
                await self._halt_pending()
            self._backing = "cornered"
            return True
        from nexwar_contract.hal import VelocityCommand
        self._backing = "retreat"
        self._vseq += 1
        got = await self._hal.set_velocity(VelocityCommand(
            seq=self._vseq, ttl_ms=BACK_CMD_TTL_MS, frame="base", vx=cmd[0], vy=0.0, wz=cmd[1]))
        if getattr(got, "rejected", False):
            log.warning("跟人 %s:退的速度被 HAL 拒了(%s)", self.task_id, getattr(got, "reason", ""))
        return True

    def _back_speed(self, here: tuple[float, float, float]) -> float:
        """往后退的限速:任务限速和身边(退一下能到的范围)地图限速区里低的那个
        (外审 W77-11 #4、12 #3)。"""
        v = self.req.max_speed_mps
        cap = getattr(getattr(self._parts, "nav", None), "speed_cap_near", None)
        if callable(cap):
            try:
                z = cap(here[0], here[1], BACK_REACH_M)
            except Exception:
                log.exception("跟人 %s:限速区查不出来,按最慢退", self.task_id)
                z = 0.0
            if z is not None:
                v = min(v, float(z))
        return v

    async def _battery_low(self) -> str:
        """电量低于导航段用的停止线(报警级 ``ALARM_FLOOR_PCT``,别的按任务默认):回原因;
        不低回 ``""``。"""
        if self._hal is None:
            return ""
        line = ALARM_FLOOR_PCT if self.priority >= ALARM_PRIORITY else Policy().battery_abort_pct
        try:
            pct = getattr(await self._hal.battery(), "percent", None)
        except Exception:
            log.exception("跟人 %s:读电量失败", self.task_id)
            return ""
        if isinstance(pct, (int, float)) and pct < line:
            return f"电量 {pct:.0f}% 低于停止线 {line:.0f}%"
        return ""

    async def _halt_pending(self) -> None:
        """发停车,记一笔「待停稳」(停车出错也记着,外审 W77-1 #3)。"""
        if self._stop_wait is None:
            self._stop_wait = 0.0
        try:
            await self._hal.stop()
        except Exception:
            log.exception("跟人 %s:停车失败", self.task_id)

    async def _stop_backing(self) -> None:
        if self._backing == "retreat":
            await self._halt_pending()
        self._backing = ""

    async def _stop_confirmed(self, dt_s: float) -> bool:
        """退过以后停稳了没有(最多等 :data:`STOP_CONFIRM_TIMEOUT_S`);不用等回 True。"""
        if self._stop_wait is None:
            return True
        try:
            stopped = bool(await self._hal.stopped())
        except Exception:
            log.exception("跟人 %s:问停没停失败", self.task_id)
            stopped = False
        if stopped:
            self._stop_wait = None
            return True
        self._stop_wait += dt_s
        if self._stop_wait >= STOP_CONFIRM_TIMEOUT_S:
            self._stop_wait = 0.0
            if not self._stop_alarmed:
                self._stop_alarmed = True
                log.error("跟人 %s:%.0f 秒没确认停稳,重发停车,不起导航段、不交接", self.task_id,
                          STOP_CONFIRM_TIMEOUT_S)
                self._events.emit("follow_stop_unconfirmed", {"task_id": self.task_id})
            try:
                await self._hal.stop()
            except Exception:
                log.exception("跟人 %s:重发停车失败", self.task_id)
        return False

    async def _settled(self, dt_s: float) -> bool:
        """要收尾了:在退就先停车;退过的都要停稳(最多 :data:`STOP_CONFIRM_TIMEOUT_S`)。"""
        await self._stop_backing()
        return await self._stop_confirmed(dt_s)

    def _heading(self) -> float | None:
        """人往哪走(弧度):最近 :data:`HEADING_SPAN_S` 秒的头尾连线;走得太近算不出。"""
        if len(self._track) < 2:
            return None
        end = self._track[-1]
        start = next((t for t in self._track if end[0] - t[0] <= HEADING_SPAN_S * 1000),
                     self._track[0])
        if start is end or math.dist(start[1:3], end[1:3]) < HEADING_MIN_M:
            start = self._track[0]
        if math.dist(start[1:3], end[1:3]) < HEADING_MIN_M:
            return None
        return math.atan2(end[2] - start[2], end[1] - start[1])

    # ------------------------------------------------------------ 怎么跟

    async def _follow(self, now: int, here: tuple[float, float, float] | None) -> None:
        if self._person is None or here is None or now - self._seen_ms > SWITCH_S * 1000:
            return                                       # 不知道人在哪 / 自己在哪:不动
        px, py = self._person
        d = math.dist((px, py), here[:2])
        yaw = math.atan2(py - here[1], px - here[0])
        k = max(0.0, d - self.req.keep_m) / d if d > 1e-6 else 0.0
        goal = (here[0] + (px - here[0]) * k, here[1] + (py - here[1]) * k)
        if self._leg is None:
            if d < self.req.keep_m + START_EXTRA_M:
                return
            await self._start_leg(goal, yaw)
            return
        if self._leg_goal is not None and math.dist(goal, self._leg_goal) >= RETARGET_M \
                and now - self._retarget_at >= RETARGET_EVERY_S * 1000:
            from nexwar_patrol.protocol.nav_types import Pose
            self._retarget_at = now
            self._leg_goal = goal
            await self._parts.engine.retarget(Pose.from_xy_yaw(goal[0], goal[1], yaw))

    async def _start_leg(self, goal: tuple[float, float], yaw: float) -> None:
        self._leg_n += 1
        leg = EngineGotoTask(task_id=self.task_id,
                             target=MapPose(map_id=self._map[0], map_version=self._map[1],
                                            frame_id="map",
                                            x=goal[0], y=goal[1], yaw=yaw),
                             max_speed_mps=self.req.max_speed_mps, parts=self._parts,
                             events=self._events, now_ms=self._wall, priority=self.priority)
        await leg.start()
        if leg.done:
            log.warning("跟人 %s:这一段起不来(%s)", self.task_id, leg.detail.get("reason"))
            if self.phase == "back":
                self._final = (TaskState.DONE, {"result": self._result,
                                                "reason": str(leg.detail.get("reason", ""))[:200],
                                                **self._report()})
            else:
                self._lose("lost")
            return
        self._leg, self._leg_goal = leg, goal
        self._retarget_at = self._mono()

    def _lose(self, result: str) -> None:
        """跟丢:停下这一段,回最后看见人的地方、朝人离开的方向。到上限(外审 W77-1 #4):不再往前追,
        原地守着(人靠近照样退),人看不到 ``lost_s`` 秒才收尾。"""
        if result == "limit":
            self.phase, self._result = "keep", result
            log.info("跟人 %s:到上限了,不再追,原地守着", self.task_id)
            self._events.emit("follow_lost", {"task_id": self.task_id, "result": result,
                                              **self._last()})
            return
        self.phase, self._result = "back", result
        log.info("跟人 %s:%s,回最后看见人的地方", self.task_id,
                 "跟丢了" if result == "lost" else "到上限了")
        self._events.emit("follow_lost", {"task_id": self.task_id, "result": result,
                                          **self._last()})
        if self._person is None:
            self._final = (TaskState.DONE, {"result": result, **self._report()})
            return
        self._pending_back = True

    async def _go_back(self) -> None:
        """跟丢:去最后看见人的那个点,朝人离开的方向;算不出方向就朝那个点。"""
        here = self._here()
        px, py = self._person  # type: ignore[misc]
        h = self._heading()
        if h is None:
            h = math.atan2(py - here[1], px - here[0]) if here is not None else 0.0
        await self._start_leg((px, py), h)

    # ------------------------------------------------------------ 报告

    def _last(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if self._person is not None and self._track:
            out["last"] = {"x": round(self._person[0], 2), "y": round(self._person[1], 2),
                           "at_ms": self._track[-1][3]}
        h = self._heading()
        if h is not None:
            out["heading_deg"] = round(math.degrees(h), 1)
        return out

    def _report(self) -> dict[str, Any]:
        return {**self._last(), "dist_m": round(self._dist_m, 1),
                "secs": round((self._mono() - self._t0) / 1000),
                "track": [{"x": round(x, 2), "y": round(y, 2), "at_ms": w}
                          for _, x, y, w in self._track]}

    def _send_track(self, now: int) -> None:
        if not self._unsent or now - self._sent_at < TRACK_EVERY_S * 1000:
            return
        self._sent_at = now
        pts, self._unsent = self._unsent, []
        self._events.emit("follow_track", {"task_id": self.task_id, "phase": self.phase,
                                           "points": pts, **self._last()})
