"""代理这一侧的障碍(W11 设计稿 §3–5,W08 决定 8):感知给的局部栅格 → 滚动记忆 → 守卫。

- :class:`ObstacleView`:收感知的栅格(``on_grid``,记下**采集时刻**,代理单调钟上的)与每拍的里程
  (``note_odom``);留最近 :data:`MEMORY_S` 秒的栅格,查一个点(此刻狗身系)时按里程换到每一帧当时的
  狗身系,**从新到旧**找第一个「看见过」它的帧:那一帧说挡就挡、说空就空;都没看见过 = 未知(当挡)。
  转身时身后、身侧刚看过的格子靠这个;狗自己刚站过的地方算空。
- :class:`ObstacleGuard`:一条速度命令发出去之前,按这条命令把机身矩形(+ 余量)往前推「链路延迟 +
  刹停距离 + 余量」那么远(刹停按**里程实测速度**,W08 决定 8),原地转是外接圆;扫过的格子有挡或
  未知 → 不发。机身此刻占着的那块不查。往后退(狗尾为前,W09i)一样,往后推。
- 采集时刻(外审 11-14):帧头时刻是感知的钟,不跟单调钟直接减;按「收到 − 帧头」比参考值多出来的
  算这一帧多等了多久(:data:`CLOCK_DRIFT`);重复、乱序、积压超过 :data:`LOST_S` 的丢;seq 从头来、
  帧头倒退 → 重新估钟。里程位姿按采集时刻插。
- 新鲜度:最新一帧采集以后 ≤ 固定延迟 + :data:`FRESH_S` 算新鲜(正常收到以后有 FRESH_S 的余量);
  没新鲜的 → 守卫当挡(原地等);超过固定延迟 + :data:`LOST_S` → 「雷达掉线」(后端发 13331,引擎中止)。
"""

from __future__ import annotations

import logging
import math
import time
from collections import deque
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from nexwar_contract.obsbridge import Grid

#: 记忆多久(秒)。前后两台半球雷达都看不见机身两侧那条带,转身、急转时扫过它全靠往前走时看过的记忆;
#: 被挡等了几秒再绕,5 s 不够(仿真里绕障转身就卡住)。取 10 s,真机调(人 10 s 内横着走进那条带的风险
#: 写进已知限制)。
MEMORY_S = 10.0
#: 工单 21(2026-10-28 C40221 下午):狗站着没挪窝(离那一帧的位置不到 :data:`MEMORY_STILL_M`,原地转
#: 也算没挪)时,那一帧留到这么久;挪了窝照旧 :data:`MEMORY_S`。外审 11-14 起超过 :data:`MEMORY_S` 的
#: 旧帧只认「有东西」、不认「空」(站着的时候人可能从侧面走进盲带)—— 站久了再转身要先挪、看清
#: 再转(守卫按刹停角度多查,小角度转身车角也扫进盲带)。
MEMORY_STILL_S = 60.0
#: 用户 11-14:脱困动作进行中(机器人在动、看得见、有声音)盲带「空」的记忆认这么久 —— 1.3 m 死胡同
#: 掉头(先挪 1.2 m 看清、再原地转 180° 要 8 s 多)按 10 s 会转到一半斜卡在走廊里。平时照旧
#: :data:`MEMORY_S`。走着的时候旧帧也留到这么久(超过 MEMORY_S 的平时只认「有东西」)。
REC_FREE_S = 15.0
MEMORY_STILL_M = 0.15
FRESH_S = 0.3
LOST_S = 2.0
ODOM_KEEP_S = 12.0
#: 感知链路**最快那一路**的延迟(秒,雷达采集 → 代理收到;待真机量,写进 docs/真机验证.md):多等的
#: 按帧头时刻另算(:data:`CLOCK_DRIFT`),采集时刻 = 收到 − 多等的 − 它;里程位姿按采集时刻配
#: (内审应修 4:配收到时刻的位姿,障碍会被往前多算 v·延迟)。
PERCEPTION_LATENCY_S = 0.15
#: 「狗自己刚站过的地方算空」只信这么久(内审再议:人可能跟着走进来)。
SELF_SWEPT_S = 3.0
#: W41 全局重定位:感知攒一份墙那一层用多久(跟感知节点的 ``WALL_EVERY_S`` 一样)、这一段里狗挪了不到
#: 这么远、转了不到这么多才算「没动」(动着攒的点是糊的);一份多久以内算新鲜。
WALL_SPAN_S = 1.2
WALL_STILL_M = 0.05
WALL_STILL_RAD = 0.035
WALL_MAX_AGE_S = 2.5
#: 外审 11-14:帧按**采集时刻**算。帧头 ``stamp_ns`` 是感知那边的钟,跟代理单调钟不能直接减;只看
#: 「收到 − 帧头」的变化:见过最小的当参考(一路最快),这一帧比参考多出来的 = 多等的(积压、卡顿)。
#: 参考往下随时跟;往上每秒最多涨这么多秒(吸收两边钟的漂移,远大于晶振的几十 ppm;持续卡着的
#: 不会过几秒就被当成正常)。
CLOCK_DRIFT = 1e-3
#: 刚开始 / 重新估钟以后,攒够这么多帧才算帧龄可信(``stamp_trusted``)。
CLOCK_MIN_FRAMES = 5
#: seq 退回到这么小当感知重启(重新估钟);别的 seq 不往前的当重复 / 乱序,丢掉。
RESTART_SEQ = 3
#: 多等超过这么久(积压、卡顿)记一条告警,最多每 :data:`DELAY_LOG_S` 秒一条。
DELAY_WARN_S = 0.1
DELAY_LOG_S = 10.0

log = logging.getLogger(__name__)


def _compose(a: tuple[float, float, float], p: tuple[float, float]) -> tuple[float, float]:
    """位姿 ``a``(x, y, yaw)下的局部点 → 外面的坐标。"""
    c, s = math.cos(a[2]), math.sin(a[2])
    return (a[0] + c * p[0] - s * p[1], a[1] + s * p[0] + c * p[1])


def _inv(a: tuple[float, float, float], w: tuple[float, float]) -> tuple[float, float]:
    """外面的点 → 位姿 ``a`` 下的局部坐标。"""
    c, s = math.cos(a[2]), math.sin(a[2])
    dx, dy = w[0] - a[0], w[1] - a[1]
    return (c * dx + s * dy, -s * dx + c * dy)


@dataclass
class _Frame:
    at: float
    pose: tuple[float, float, float]           # 这一帧那一刻狗在里程系里的位姿
    occ: Any                                   # numpy uint8,size × size
    known: Any
    size: int
    res: float
    #: 可疑的格子(W29 复查,决策 42):这一帧可疑 = 挡,旧帧的「空」补不上来。
    suspect: Any = None


@dataclass
class ObstacleView:
    monotonic: Callable[[], float] = time.monotonic
    memory_s: float = MEMORY_S
    frames: deque = field(default_factory=deque)
    odom: deque = field(default_factory=deque)       # (时刻, (x, y, yaw))
    #: 感知自检:none / initializing / ok / extrinsic_bad
    check: str = "none"
    reason: str = ""
    rear: bool = False
    #: 后雷达外参真标过(W09i;感知报的):狗尾为前才许自己走。
    rear_cal: bool = False
    connected: bool = False
    latency_s: float = PERCEPTION_LATENCY_S
    #: W41:感知最新一份墙那一层(狗身系的点)、收到的时刻、攒的时候狗没动。
    wall: Any = None
    wall_at: float = -math.inf
    wall_still: bool = False
    wall_pose: tuple[float, float, float] | None = None
    wall_seq: int = 0
    #: 工单 21:狗最近一次挪窝(离上次站的地方超过 :data:`MEMORY_STILL_M`)的位置和时刻。
    _still_at: tuple[float, float] | None = None
    _still_since: float = -math.inf
    #: 外审 11-14 采集时刻:最近一帧估的「采集 → 收到」(秒)、帧龄可不可信(没有帧头时刻、刚重新估钟
    #: 的不可信:照固定延迟算)。
    delay_s: float = 0.0
    stamp_trusted: bool = False
    _clk_ref: float | None = None          # 「收到 − 帧头」的参考值
    _clk_rx: float = 0.0
    _clk_n: int = 0
    _last_seq: int = 0
    _last_stamp: float = -math.inf
    _delay_logged: float = -math.inf

    # ------------------------------------------------------------ 喂进来

    def note_odom(self, x: float, y: float, yaw: float) -> None:
        now = self.monotonic()
        if self._still_at is None or math.hypot(x - self._still_at[0],
                                                y - self._still_at[1]) > MEMORY_STILL_M:
            self._still_at, self._still_since = (float(x), float(y)), now     # 挪了窝
        self.odom.append((now, (float(x), float(y), float(yaw))))
        while self.odom and now - self.odom[0][0] > ODOM_KEEP_S:
            self.odom.popleft()

    def pose_at(self, t: float) -> tuple[float, float, float] | None:
        """``t`` 时刻狗在里程系里的位姿(前后两拍线性插;超出范围取最近的)。"""
        if not self.odom:
            return None
        prev = None
        for at, p in self.odom:
            if at >= t:
                if prev is None:
                    return p
                (t0, p0) = prev
                f = 0.0 if at == t0 else (t - t0) / (at - t0)
                dyaw = math.remainder(p[2] - p0[2], 2 * math.pi)
                return (p0[0] + f * (p[0] - p0[0]), p0[1] + f * (p[1] - p0[1]), p0[2] + f * dyaw)
            prev = (at, p)
        return self.odom[-1][1]

    def _acquired(self, g: Grid, rx: float) -> float | None:
        """这一帧在代理单调钟上的采集时刻;重复、乱序、积压超过 :data:`LOST_S` 的回 None(丢)。"""
        if g.stamp_ns <= 0:                          # 老感知没帧头时刻:照固定延迟
            self.stamp_trusted, self.delay_s = False, self.latency_s
            return rx - self.latency_s
        st = g.stamp_ns / 1e9
        if g.seq < self._last_seq and g.seq <= RESTART_SEQ:
            self._clk_ref = None                     # 感知重启:重新估
        elif g.seq <= self._last_seq:
            return None                              # 重复 / 乱序
        elif st <= self._last_stamp:
            self._clk_ref = None                     # seq 往前、帧头倒退:对方换了钟
        self._last_seq, self._last_stamp = g.seq, st
        d = rx - st
        if self._clk_ref is None:
            self._clk_ref, self._clk_n = d, 0
        else:
            self._clk_ref = min(d, self._clk_ref + CLOCK_DRIFT * max(0.0, rx - self._clk_rx))
        self._clk_rx = rx
        self._clk_n += 1
        self.stamp_trusted = self._clk_n >= CLOCK_MIN_FRAMES
        extra = d - self._clk_ref
        self.delay_s = extra + self.latency_s
        if extra > DELAY_WARN_S and rx - self._delay_logged >= DELAY_LOG_S:
            self._delay_logged = rx
            log.warning("感知帧多等了 %.2f s(采集 → 收到共 %.2f s;积压或卡顿)%s", extra,
                        self.delay_s, ",超过掉线时长,丢掉" if self.delay_s > LOST_S else "")
        if self.delay_s > LOST_S:
            return None                              # 积压太久:里程早配不上了
        return rx - self.delay_s

    def fresh(self) -> bool:
        """最新一帧新鲜(采集以后 ≤ 固定延迟 + :data:`FRESH_S`;正常收到以后有 FRESH_S 的余量)。"""
        return bool(self.frames) and self.age() <= FRESH_S + self.latency_s

    def on_grid(self, g: Grid) -> None:
        now = self.monotonic()
        self.check, self.reason, self.rear, self.rear_cal = g.check, g.reason, g.rear, g.rear_cal
        at = self._acquired(g, now)
        if at is None:
            return
        pose = self.pose_at(at)
        if pose is None or g.check != "ok":
            return                                   # 没有里程配不上;自检没过的不用
        occ, known = g.bits()
        self.frames.appendleft(_Frame(at=at, pose=pose,
                                      occ=np.frombuffer(occ, dtype=np.uint8),
                                      known=np.frombuffer(known, dtype=np.uint8),
                                      size=g.size, res=g.res,
                                      suspect=np.frombuffer(g.suspect_bits(), dtype=np.uint8)))
        while self.frames:
            f, age = self.frames[-1], now - self.frames[-1].at
            if age <= max(self.memory_s, REC_FREE_S) or (age <= MEMORY_STILL_S
                                        and self._still_since <= f.at + self.memory_s):
                break                                   # 工单 21:它过期之前狗就站住了、一直没挪窝
            self.frames.pop()

    def on_wall(self, w: Any) -> None:
        """感知发来一份墙那一层(W41 全局重定位)。"""
        now = self.monotonic()
        a = self.pose_at(now - self.latency_s - WALL_SPAN_S)
        b = self.pose_at(now - self.latency_s)
        still = (a is not None and b is not None and len(self.odom) >= 2
                 and self.odom[0][0] <= now - self.latency_s - WALL_SPAN_S
                 and math.hypot(b[0] - a[0], b[1] - a[1]) <= WALL_STILL_M
                 and abs(math.remainder(b[2] - a[2], 2 * math.pi)) <= WALL_STILL_RAD)
        self.wall, self.wall_at, self.wall_still = w.points(), now, still
        self.wall_seq += 1                               # 复查 N1:匹配结果按它绑定那一份点云
        self.wall_pose = b                               # 外审 R3:攒这份点云时狗在哪(里程)

    def wall_scan(self, *, since: float = -math.inf,
                  max_age: float = WALL_MAX_AGE_S) -> list[tuple[float, float]] | None:
        """最新一份墙那一层:新鲜、攒的时候狗没动、``since`` 之后收到的;不然 None。"""
        if self.wall is None or not self.wall_still or self.wall_at < since \
                or self.monotonic() - self.wall_at > max_age:
            return None
        # 外审 R3:收到以后狗又走了(还在 2.5 s 有效期里)—— 点云对的是刚才那个位置,不能当现在的用
        p, now_pose = self.wall_pose, (self.odom[-1][1] if self.odom else None)
        if p is None or now_pose is None \
                or math.hypot(now_pose[0] - p[0], now_pose[1] - p[1]) > WALL_STILL_M \
                or abs(math.remainder(now_pose[2] - p[2], 2 * math.pi)) > WALL_STILL_RAD:
            return None
        return list(self.wall)

    def on_connect(self) -> None:
        self.connected = True

    def on_disconnect(self) -> None:
        self.connected = False

    # ------------------------------------------------------------ 状态与查询

    def age(self) -> float:
        return math.inf if not self.frames else self.monotonic() - self.frames[0].at

    def state(self) -> str:
        """``ok`` / ``stale``(短暂不新鲜:原地等)/ ``lost``(雷达掉线)/ ``extrinsic_bad`` /
        ``initializing``。"""
        if self.check == "extrinsic_bad":
            return "extrinsic_bad"
        a = self.age() - self.latency_s
        if a <= FRESH_S:
            return "ok"
        if a <= LOST_S:
            return "stale"
        if self.check == "initializing" and self.connected:
            return "initializing"
        return "lost"

    def near_ahead(self, travel: int, half_len: float, half_wid: float) -> float:
        """最新一帧(新鲜的才算)里,行进方向上机身前沿往前、机身两边各宽 ``half_wid`` 的带子里,最近的
        「挡」离前沿多远(米);没有是 inf。只看「挡」:「看不见」守卫管,
        算进来的话侧面盲带会让狗一直慢。
        近障降速用(W12),不管安全 —— 帧是此刻之前 ≤ :data:`FRESH_S` 的,差几厘米无所谓。"""
        if not self.fresh():
            return math.inf
        f = self.frames[0]
        n = f.size
        c = (np.arange(n) - n / 2 + 0.5) * f.res
        occ = f.occ.reshape(n, n).astype(bool)
        x = c[:, None] * (1.0 if travel >= 0 else -1.0)       # 行 → 行进方向上的前后
        y = c[None, :]
        band = occ & (x > half_len) & (np.abs(y) <= half_wid)
        if not band.any():
            return math.inf
        return float((np.broadcast_to(x, band.shape)[band] - half_len).min())

    def lookup(self, pts: list[tuple[float, float]], pose_now: tuple[float, float, float],
               *, max_age: float | None = None,
               free_s: float | None = None) -> tuple[list[int], list[int]]:
        """此刻狗身系的点 → (挡的点的下标, 未知的点的下标)。numpy 一批算(内审应修 7:逐点逐帧
        在狗上一拍要几十毫秒,事件循环上)。``max_age``:只认这么多秒以内的帧(遮挡限速用)。"""
        if not pts:
            return [], []
        P = np.asarray(pts, dtype=float)
        c0, s0 = math.cos(pose_now[2]), math.sin(pose_now[2])
        wx = pose_now[0] + c0 * P[:, 0] - s0 * P[:, 1]
        wy = pose_now[1] + s0 * P[:, 0] + c0 * P[:, 1]
        res = np.full(len(P), -1, dtype=np.int8)          # -1 没看见过、0 空、1 挡
        now = self.monotonic()
        oldest = -math.inf if max_age is None else now - max_age
        for f in list(self.frames):
            if f.at < oldest:
                break
            todo = res < 0
            if not todo.any():
                break
            # 外审 11-14:站着不动留下来的旧帧(超过 memory_s)只能说「那儿有东西」,不能单独证明
            # 「那儿现在是空的」—— 站着的时候人可能从侧面走进盲带
            stale = now - f.at > (self.memory_s if free_s is None else free_s)
            c, s = math.cos(f.pose[2]), math.sin(f.pose[2])
            dx, dy = wx - f.pose[0], wy - f.pose[1]
            lx, ly = c * dx + s * dy, -s * dx + c * dy
            r = np.floor(lx / f.res + f.size / 2).astype(int)
            cc = np.floor(ly / f.res + f.size / 2).astype(int)
            inb = todo & (r >= 0) & (r < f.size) & (cc >= 0) & (cc < f.size)
            k = np.where(inb, r * f.size + cc, 0)
            seen = inb & (f.known[k] == 1)
            if stale:
                seen &= f.occ[k] == 1
            res[seen] = f.occ[k[seen]]
            if f.suspect is not None:
                # 这一帧说这一格可疑(孤立凸起点,可能是细杆子):当挡,不往更旧的帧找(决策 42)
                sus = inb & (f.suspect[k] == 1)
                res[sus] = 1
        if (res < 0).any():
            res[(res < 0) & self._self_swept(wx, wy)] = 0
        return np.nonzero(res == 1)[0].tolist(), np.nonzero(res < 0)[0].tolist()

    #: 机身矩形的一半(查「狗自己刚站过的地方」用;跟守卫的机身尺寸一致)。
    body_hl: float = 0.465
    body_hw: float = 0.24

    def _self_swept(self, wx: Any, wy: Any) -> Any:
        """这些点(里程系)是不是狗自己最近 :data:`SELF_SWEPT_S` 秒里机身占过的地方:雷达看不见机身
        底下和机身两侧,急转时后角甩出去扫到的正是刚站过的地方 —— 狗刚站过,那里是空的。"""
        now = self.monotonic()
        out = np.zeros(len(wx), dtype=bool)
        for at, pose in reversed(self.odom):
            if now - at > SELF_SWEPT_S:
                break
            c, s = math.cos(pose[2]), math.sin(pose[2])
            dx, dy = wx - pose[0], wy - pose[1]
            lx, ly = c * dx + s * dy, -s * dx + c * dy
            out |= (np.abs(lx) <= self.body_hl) & (np.abs(ly) <= self.body_hw)
        return out


#: 守卫结论的原因(外审 11-14:上层按这个决定停不停,不匹配原因文字)。
#: ``unknown`` = 只有前进方向雷达视野里看不见(被挡住后面),降速可走;``blind`` = 看不见的在两侧盲带、
#: 或者后退 / 原地转时扫过区里有看不见的 —— 停(外审 11-14、用户定:按方向、按动作分规则)。
CAUSES = ("clear", "hit", "unknown", "blind", "data", "blocked")
#: 两侧盲带:机身前后沿(各再放这么多)之间,前后雷达都看不见(实测锥形视野 obs-3f4)。
BAND_TOL_M = 0.05


@dataclass(frozen=True)
class Verdict:
    ok: bool
    reason: str = ""
    #: 挡住的点(此刻狗身系)—— 被挡久了后端把它们记进临时障碍层。
    hits: tuple[tuple[float, float], ...] = ()
    unknown: int = 0
    #: :data:`CAUSES` 之一;不填按 ok / hits 推:放行 = ``clear``,有挡点 = ``hit``,
    #: 别的不放行(地图墙、脱困步扫墙、没动……)= ``blocked``(一律当挡)
    kind: str = ""
    #: 看不见的里有几处在两侧盲带(外审 11-14:转身被它拦住时先直着挪、看清再转)。
    band: int = 0

    @property
    def cause(self) -> str:
        """``clear`` 放行;``hit`` 扫过区有挡;``unknown`` 只有前进方向视野里看不见的;``blind``
        看不见的在两侧盲带、或后退 / 原地转时有看不见的;``data`` 障碍数据不新鲜 / 断了 / 自检没过;
        ``blocked`` 别的明确不放行。"""
        if self.kind:
            return self.kind
        return "clear" if self.ok else ("hit" if self.hits else "blocked")

    @property
    def band_only(self) -> bool:
        """只因为两侧盲带看不见才拦(外审 11-14:这种先直着挪看清再转;后面没雷达这类挪了也看不清)。"""
        return self.cause == "blind" and 0 < self.band == self.unknown

    @property
    def stops(self) -> bool:
        """一定要停:有挡、盲带 / 后退 / 原地转看不见、数据不可用、别的明确不放行(只有前进方向
        视野里看不见的另按降速规则)。"""
        return self.cause in ("hit", "blind", "data", "blocked")


@dataclass
class ObstacleGuard:
    body_len: float = 0.93
    body_wid: float = 0.48
    margin: float = 0.05
    latency: float = 0.2                     # 链路延迟(秒,待 W00d 量)
    decel: float = 0.5                       # 刹车减速度(m/s²,待真机量)
    extra: float = 0.3                       # 再留这么多(米)
    step: float = 0.05                       # 扫过区的采样间距(米)
    #: 原地转:按这一拍转过去再刹停的角度查扇形(工单 21:原来不管转多少都查整个外接圆,差 5° 也被
    #: 侧后方看不见的格子拦住)。角减速度、再留的角度待真机量;算出来过半圈就查整圈。
    ang_decel: float = 1.0                   # 弧度/秒²
    extra_rad: float = 0.2
    #: 低于这个的实测 / 上一拍转速当没在转(里程转速的噪声)。
    still_rps: float = 0.05
    #: 低于这个的实测 / 上一拍前进速度当没在走(外审 11-14 查运动过渡时用)。
    still_mps: float = 0.05

    def turn_reach(self, wz: float) -> float:
        w = abs(wz)
        return w * self.latency + w * w / (2.0 * self.ang_decel) + self.extra_rad

    def reach(self, v: float) -> float:
        v = abs(v)
        return v * self.latency + v * v / (2.0 * self.decel) + self.extra

    def turn_span(self, wz: float, w_now: Sequence[float] = ()) -> tuple[float, float]:
        """原地转这一拍机身朝向可能落到的范围(弧度,相对此刻;含 0)。外审 2026-10-29 R1:不光新命令
        ``wz`` 转过去再刹停,**正在转的那股劲**(``w_now``:上一拍发的转速、里程实测转速)在延迟里接着
        转、再刹停也算 —— 原来只查新命令那一侧,反向或减速时漏了还在执行的那一侧。"""
        lo = hi = 0.0
        if abs(wz) > 1e-6:
            a = math.copysign(self.turn_reach(wz), wz)
            lo, hi = min(lo, a), max(hi, a)
        for w in w_now:
            # 复查 N1:里程转速的噪声不算在转(原来 −0.001 也按整份余量查反向,对准被侧后看不见的挡死);
            # 还在转的那股劲只按延迟里接着转、再刹停算,余量只加在新命令上
            if abs(w) >= self.still_rps:
                v = abs(w)
                a = math.copysign(v * self.latency + v * v / (2.0 * self.ang_decel), w)
                lo, hi = min(lo, a), max(hi, a)
        return lo, hi

    def swept(self, vx: float, wz: float, v_meas: float,
              w_now: Sequence[float] = (), *,
              moving: Sequence[tuple[float, float]] = ()) -> list[tuple[float, float]]:
        """这一拍扫过的机身区域里的采样点(此刻狗身系) = **新命令**的扫掠区 ∪ **正在做的运动**的
        扫掠区(外审 11-14:查运动过渡,不是只查新命令)。

        - 新命令:往前走沿这条命令的圆弧推 ``reach(max(实测, 命令))`` 米,每一步一个机身矩形(往后退
          就往后推);原地转(前进 ≈ 0、在转)::meth:`turn_span` 那段扇形,过半圈查外接圆。
        - 正在做的运动 ``moving`` = ``[(vx, wz), …]``(里程实测、上一拍发的命令 —— 实测滞后或没有时
          靠上一拍命令兜):每一份按它自己的方向和弯在延迟里接着走、再刹停(``reach``),也扫一遍;
          还在转的(``w_now`` 和 ``moving`` 里的转速)按延迟里接着转、刹停的扇形也并进来。
          这样前进中收到倒车、倒车中收到前进、走着收到原地转、转向反过来,都查到还没停下来的那一段。"""
        hl, hw = self.body_len / 2 + self.margin, self.body_wid / 2 + self.margin
        pts = self._swept_cmd(vx, wz, v_meas, w_now, hl, hw)
        for mv, mw in moving:
            if abs(mv) >= self.still_mps:
                pts |= self._arc(mv, mw, self.reach(mv), hl, hw)
        spins = [w for w in (*w_now, *(mw for _, mw in moving)) if abs(w) >= self.still_rps]
        if spins:
            lo, hi = self.turn_span(0.0, spins)
            if hi - lo > 1e-6:
                pts |= self._sector(lo, hi, hl, hw)
        return self._outside_body(pts, hl, hw)

    def _sector(self, lo: float, hi: float, hl: float, hw: float) -> set[tuple[float, float]]:
        """原地从朝向 0 转到 lo → hi 的某一刻落在机身矩形里的采样点;过半圈查整个外接圆。"""
        s = self.step
        r = math.hypot(hl, hw)
        n = int(r / s) + 1
        g = (np.arange(-n, n) + 0.5) * s                 # 取格子中间,不压在格边上
        X, Y = np.meshgrid(g, g, indexing="ij")
        X, Y = X.ravel(), Y.ravel()
        keep = X * X + Y * Y <= r * r
        X, Y = X[keep], Y[keep]
        if hi - lo >= math.pi:
            hit = np.ones(len(X), dtype=bool)
        else:
            hit = np.zeros(len(X), dtype=bool)
            # 角步长让外接圆上相邻两刻不超过一格
            k = max(1, int(math.ceil((hi - lo) * r / s)))
            for i in range(k + 1):
                a = lo + (hi - lo) * i / k              # 机身转了 a:把点转回 −a 看在不在矩形里
                c, sn = math.cos(a), math.sin(a)
                lx, ly = c * X + sn * Y, -sn * X + c * Y
                hit |= (np.abs(lx) <= hl) & (np.abs(ly) <= hw)
        return {(round(float(x), 3), round(float(y), 3))
                for x, y in zip(X[hit], Y[hit], strict=True)}

    def _arc(self, vx: float, wz: float, dist: float, hl: float, hw: float
             ) -> set[tuple[float, float]]:
        """按 (vx, wz) 的方向和弯走 ``dist`` 米,每一步机身轮廓线落下的点;弯比机身对角线还急就并上
        外接圆(跟原地转差不多)。"""
        s = self.step
        pts: set[tuple[float, float]] = set()
        corner = math.hypot(hl, hw)
        # 角点走过的弧长只在转弯半径比机身对角线还小时才比中心的长 —— 那种急转下面直接并上外接圆
        # (内审应修 3;突变里「按角点弧长取步数」跟「并外接圆」互相顶替,只留后一条)
        k = max(1, int(dist / s))
        xs = [(i + 0.5) * s for i in range(int(-hl / s) - 1, int(hl / s) + 1)
              if abs((i + 0.5) * s) < hl] + [-hl, hl]
        ys = [(j + 0.5) * s for j in range(int(-hw / s) - 1, int(hw / s) + 1)
              if abs((j + 0.5) * s) < hw] + [-hw, hw]
        edge = [(x, y) for x in xs for y in ys
                if abs(abs(x) - hl) < s or abs(abs(y) - hw) < s]      # 机身轮廓线
        sign = -1.0 if vx < 0 else 1.0
        for t in range(k + 1):
            d = sign * dist * t / k                      # 走过的路(带方向):往后退是负的
            if abs(wz) < 1e-6 or abs(vx) < 1e-6:
                px, py, th = d, 0.0, 0.0
            else:
                rad = vx / wz
                th = d / rad
                px, py = rad * math.sin(th), rad * (1 - math.cos(th))
            c, sn = math.cos(th), math.sin(th)
            # 每一步机身的轮廓线(采样间距不大于一格,轮廓线扫过的就是整个扫掠区;起点那块是狗自己)
            for x, y in edge:
                pts.add((round(px + c * x - sn * y, 3), round(py + sn * x + c * y, 3)))
        if abs(wz) > 1e-6 and abs(vx / wz) < corner:
            pts |= self._sector(0.0, 2 * math.pi, hl, hw)
        return pts

    def _swept_cmd(self, vx: float, wz: float, v_meas: float, w_now: Sequence[float],
                   hl: float, hw: float) -> set[tuple[float, float]]:
        """新命令的扫掠区(见 :meth:`swept`)。"""
        if abs(vx) < 1e-6 and abs(wz) > 1e-6:
            lo, hi = self.turn_span(wz, w_now)
            return self._sector(lo, hi, hl, hw)
        return self._arc(vx, wz, self.reach(max(abs(v_meas), abs(vx))), hl, hw)

    @staticmethod
    def _outside_body(pts: set[tuple[float, float]], hl: float, hw: float
                      ) -> list[tuple[float, float]]:
        """机身此刻占着的那块(含余量)不查:那里只能是狗自己,雷达也看不见机身底下(感知把机身的点
        滤掉了,那些格子永远是「未知」)。**分辨率**:采样间距 5 cm,紧贴这块边上不到 2 cm 的窄条可能
        漏查 —— 落在 5 cm 的余量里(内审应修 3 的复核)。"""
        return sorted(p for p in pts if abs(p[0]) > hl + 1e-9 or abs(p[1]) > hw + 1e-9)

    def check(self, vx: float, wz: float, v_meas: float, view: ObstacleView,
              pose_now: tuple[float, float, float], *, w_now: Sequence[float] = (),
              moving: Sequence[tuple[float, float]] = (),
              free_s: float | None = None) -> Verdict:
        if abs(vx) < 1e-6 and abs(wz) < 1e-6:
            return Verdict(True)                     # 原地等:不动就不会撞
        st = view.state()
        if st != "ok":
            return Verdict(False, f"障碍数据{_STATE_TEXT.get(st, st)}", kind="data")
        pts = self.swept(vx, wz, v_meas, w_now, moving=moving)
        hit, unknown = view.lookup(pts, pose_now, free_s=free_s)
        if not hit and not unknown:
            return Verdict(True)
        hits = tuple(pts[i] for i in hit)
        ups = [pts[i] for i in unknown]
        front = self.body_len / 2 + BAND_TOL_M
        band = sum(1 for x, _ in ups if abs(x) <= front)
        kind = "hit" if hit else self._unknown_kind(vx, ups, view)
        where = {"blind": f"(盲带 {band} 处 / 后退 / 原地转,不降速放行)"}.get(kind, "")
        return Verdict(False, f"扫过区有挡 {len(hit)} 处、看不见 {len(unknown)} 处{where}"
                              f"{_nearest(hits)}",
                       hits=hits, unknown=len(unknown), kind=kind, band=band)

    def _unknown_kind(self, vx: float, ups: Sequence[tuple[float, float]], view: Any) -> str:
        """外审 11-14:只有看不见的时候按方向、按动作分。前进、看不见的全在车头前雷达视野里(机身
        前沿 + :data:`BAND_TOL_M` 之外)→ ``unknown``(降速走,人一进视野就看得见);后退同理,但要
        有后雷达、外参标过。别的 → ``blind``:两侧盲带里转身、急弯车角甩进去看不见人;没后雷达
        往后退是瞎退;原地转降速也不让车角撞人变安全。"""
        front = self.body_len / 2 + BAND_TOL_M
        if vx >= self.still_mps and all(x > front for x, _ in ups):
            return "unknown"
        if vx <= -self.still_mps and all(x < -front for x, _ in ups) \
                and getattr(view, "rear", False) and getattr(view, "rear_cal", False):
            return "unknown"
        return "blind"


def _nearest(hits: tuple[tuple[float, float], ...]) -> str:
    """工单 24:最近那一处挡在机身的哪儿(狗身系:x 朝前、y 朝左),现场分得清是箱子、人还是噪点。"""
    if not hits:
        return ""
    x, y = min(hits, key=lambda p: math.hypot(p[0], p[1]))
    fb = f"前 {x:.1f} m" if x >= 0 else f"后 {-x:.1f} m"
    lr = f"左 {y:.1f} m" if y >= 0 else f"右 {-y:.1f} m"
    return f"(最近一处在机身{fb}、{lr})"


_STATE_TEXT = {"stale": "不新鲜", "lost": "已断开", "extrinsic_bad": "外参自检未通过",
               "initializing": "还在自检", "none": "没有"}


def describe(state: str) -> str:
    return _STATE_TEXT.get(state, state)
