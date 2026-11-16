"""整趟巡逻仿真(用户 11-16):把**真机代理**的巡逻引擎、导航后端、守卫和**真的 Nav2**接在一起跑一整趟巡逻。

跟 Gazebo 那套(``tools/nav_stability_bench_dev``)的区别:那边的 goal_driver 是照真机规矩另写的一份;
这里跑的就是交付的代码 ——

- 巡逻引擎 ``MissionEngine``:每个点重试一次、再不行跳过接着走、一圈走完回头补没到的点;
- 导航后端 ``Nav2NavBackend``:出发前路线检查(+ 局部搜索,``--search``)、卡在一处标成绕开重查、
  半路重查过不去沿来路退出来再查、恢复链(重新规划 → 沿原路倒退 + 绕开卡住处 → 自己前后挪 / K 字掉头)、
  台阶脱困(Nav2 让往前、走不动、机身横滚)、MPPI 走不动换 RPP、照查过的路走(FollowPath / FollowTight);
- 守卫 ``ObstacleGuard``(严格盲带,交付缺省)、禁行区;
- Nav2 用狗上同一个启动文件(``deploy/nav2/nexwar_nav2.launch.py``)+ 转接节点。

世界是 ``packages/robot-agent/tests/obs_world.py`` 的栅格世界:真值墙、照 C40221 实测的雷达视野
(前后半球、两侧盲带)、感知晚到、链路延迟、起步切步态、刹车上限。场景直接读 Gazebo 扫描生成的
``case.json``(同一个场景、同一个种子,能跟 Gazebo 结果逐个对),外加两类这里才有的:

- ``curbs``:台阶边(线段)。雷达看不见、地图里也没有;机身前沿斜着(跟台阶线夹角小于
  :data:`CURB_STUCK_DEG`)顶上去就卡住、机身横滚(一边的腿在台阶下面,W71 商场那种),够正就上得去;
- ``zones``:禁行区(多边形,交给导航后端,跟站点下发的一样)。

定位:按 case 的 ``sim.loc_noise_m / loc_noise_deg`` 给一个固定偏差 + 小抖动;``fault_trigger`` 那类
(机器人到某处后定位横跳 ``lateral_m``、持续 ``fault_duration_s``)照做。没做的:Gazebo 的执行噪声
(``exec_noise``)、真实的腿部动力学 —— 台阶是按上面的规则卡住 / 放行的模型,不是物理。

用法(仓库根目录,PYTHONPATH 同 pt.sh)::

    python tools/navbench_patrol.py --cases runs/nav-d-1116/D --out runs/navpatrol/G2 --search
    python tools/navbench_patrol.py --cases ... --out ... --no-search --shard 3/12   # 并行:第 3 份(共 12 份)

每个用例写 ``<out>/<场景>/<种子>/result.json``;已经有的跳过(断了接着跑)。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import random
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages" / "robot-agent" / "tests"))
sys.path.insert(0, str(ROOT / "tools" / "nav_stability_bench_dev"))

#: 仿真狗(照真机量过的、保守的;同 tools/navbench.py)。
ROBOT = {"latency_s": 0.1, "gait_start_s": 0.3, "max_decel": 1.5, "require_clearance": True,
         "max_vx": 1.0}
#: 机身(不带余量,REPORT_SPEC 的 0.93 × 0.48)。
BODY_HL, BODY_HW = 0.465, 0.24
#: 台阶:机身朝向跟台阶线夹角小于这个(度)就顶不上去、卡住横滚;够正的上得去。
CURB_STUCK_DEG = 40.0
CURB_ROLL_RAD = math.radians(6.0)
TICK = 0.1


# ------------------------------------------------------------------ 几何

def _corners(x: float, y: float, yaw: float, hl: float = BODY_HL, hw: float = BODY_HW):
    c, s = math.cos(yaw), math.sin(yaw)
    return [(x + c * u - s * v, y + s * u + c * v) for u, v in ((hl, hw), (hl, -hw), (-hl, -hw),
                                                                  (-hl, hw))]


def _proj(poly, ax):
    v = [p[0] * ax[0] + p[1] * ax[1] for p in poly]
    return min(v), max(v)


def _poly_hits_rect(poly, r) -> bool:
    x0, y0, x1, y1 = r
    box = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    axes = [(1.0, 0.0), (0.0, 1.0)]
    for i in range(len(poly)):
        (ax, ay), (bx, by) = poly[i], poly[(i + 1) % len(poly)]
        n = math.hypot(bx - ax, by - ay) or 1.0
        axes.append((-(by - ay) / n, (bx - ax) / n))
    for a in axes:
        p, q = _proj(poly, a), _proj(box, a)
        if min(p[1], q[1]) < max(p[0], q[0]):
            return False
    return True


def _perimeter(x: float, y: float, yaw: float, step: float = 0.08):
    pts = []
    poly = _corners(x, y, yaw)
    for i in range(4):
        (ax, ay), (bx, by) = poly[i], poly[(i + 1) % 4]
        n = max(2, int(math.hypot(bx - ax, by - ay) / step))
        pts += [(ax + (bx - ax) * k / n, ay + (by - ay) * k / n) for k in range(n)]
    return pts


def _rect_dist(px: float, py: float, r) -> float:
    x0, y0, x1, y1 = r
    dx = max(x0 - px, 0.0, px - x1)
    dy = max(y0 - py, 0.0, py - y1)
    return math.hypot(dx, dy)


def _in_poly(x: float, y: float, poly) -> bool:
    inside = False
    for i in range(len(poly)):
        (ax, ay), (bx, by) = poly[i], poly[(i + 1) % len(poly)]
        if (ay > y) != (by > y) and x < ax + (y - ay) * (bx - ax) / (by - ay):
            inside = not inside
    return inside


# ------------------------------------------------------------------ 仿真狗:定位偏差 / 横跳

def _robot_cls():
    from dataclasses import replace

    from nexwar_adapter_sim.robot import SimRobot

    class FieldRobot(SimRobot):
        """定位 = 真值 + 固定偏差 + 小抖动;横跳故障期间再叠一个侧向偏移。"""

        loc_off = (0.0, 0.0, 0.0)
        jitter_m = 0.0
        jump: tuple[float, float] | None = None       # 这一刻的横跳偏移(世界系)
        rng = random.Random(0)

        async def odometry(self):
            o = await super().odometry()
            bx, by, byaw = self.loc_off
            jx = self.rng.gauss(0.0, self.jitter_m) if self.jitter_m else 0.0
            jy = self.rng.gauss(0.0, self.jitter_m) if self.jitter_m else 0.0
            if self.jump is not None:
                bx, by = bx + self.jump[0], by + self.jump[1]
            return replace(o, x=o.x + bx + jx, y=o.y + by + jy, yaw=o.yaw + byaw)

    return FieldRobot


# ------------------------------------------------------------------ Nav2(每个进程一套)

_NAV2: dict[str, Any] = {}


async def _nav2_up() -> Any:
    if "link" in _NAV2:
        return _NAV2["link"]
    import subprocess

    from nexwar_agent.navbridge import NavBridgeServer
    d = Path(tempfile.mkdtemp(prefix="navpatrol-"))
    sock = d / "nav2.sock"
    link = NavBridgeServer(sock)
    await link.start()
    env = {k: v for k, v in os.environ.items()
           if k not in ("PYTHONPATH", "VIRTUAL_ENV", "AMENT_PREFIX_PATH", "COLCON_PREFIX_PATH")}
    env |= {"ROS_DOMAIN_ID": os.environ.get("NAVBENCH_DOMAIN", "77"), "ROS_LOCALHOST_ONLY": "1",
            "PATH": "/usr/bin:/bin"}
    params = ROOT / "deploy" / "nav2" / "params.yaml"
    logdir = Path(os.environ.get("NAVPATROL_LOGS", str(ROOT / "runs" / "navpatrol")))
    logdir.mkdir(parents=True, exist_ok=True)
    pypath = f"{ROOT}/packages/localizer/src:{ROOT}/packages/contract/src"
    nav2 = subprocess.Popen(
        ["bash", "-c", "source /opt/ros/humble/setup.bash && exec ros2 launch "
                       f"{ROOT}/deploy/nav2/nexwar_nav2.launch.py params_file:={params} "
                       f"socket:={sock} pythonpath:={pypath}"],
        env=env, stdout=open(logdir / f"nav2-{env['ROS_DOMAIN_ID']}.log", "w"),
        stderr=subprocess.STDOUT, start_new_session=True)
    _NAV2.update(link=link, procs=[nav2], t_ms=1_700_000_000_000)
    for _ in range(600):
        if link.connected:
            break
        await asyncio.sleep(0.1)
    if not link.connected:
        raise RuntimeError("Nav2 转接节点 60 s 没连上")
    return link


def _nav2_down() -> None:
    import signal
    for p in _NAV2.get("procs", []):
        try:
            os.killpg(p.pid, signal.SIGINT)
        except ProcessLookupError:
            pass
    for p in _NAV2.get("procs", []):
        try:
            p.wait(15)
        except Exception:                             # noqa: BLE001
            os.killpg(p.pid, signal.SIGKILL)


# ------------------------------------------------------------------ 一个用例

class Clock:
    def __init__(self, ms: int) -> None:
        self.ms = ms
        self.mono = 100.0

    def __call__(self) -> int:
        return self.ms

    def s(self) -> float:
        return self.ms / 1000.0

    def advance(self, dt: float) -> None:
        self.ms += int(round(dt * 1000))
        self.mono += dt


async def run_case(case: dict[str, Any], *, sim_cap_s: float) -> dict[str, Any]:
    from actor_driver import Timeline
    from obs_world import 世界, 假感知

    from nexwar_agent.assembly import build_engine
    from nexwar_agent.engine.machine import FINAL_STATES
    from nexwar_agent.obstacles import ObstacleGuard, ObstacleView
    from nexwar_agent.planning.planner import Planner
    from nexwar_contract.mission import Mission, MissionWaypoint, Policy
    from nexwar_contract.zones import ZoneSet
    from nexwar_patrol.protocol.nav_types import Pose

    rng = random.Random(f"{case['scenario']}/{case['seed']}")
    bx0, bx1, by0, by1 = case.get("map_bounds") or [-9.0, 9.0, -9.0, 9.0]
    ox, oy = -bx0, -by0                                  # 世界坐标 = case 坐标 + (ox, oy)

    def rect(b):
        return (b["x"] - b["sx"] / 2 + ox, b["y"] - b["sy"] / 2 + oy,
                b["x"] + b["sx"] / 2 + ox, b["y"] + b["sy"] / 2 + oy)

    mapped = case.get("obstacles", [])
    phys = case.get("collision_obstacles", mapped)
    unmapped = [b for b in phys if b not in mapped]
    walls = [rect(b) for b in mapped]
    link = await _nav2_up()
    sim = case.get("sim") or {}
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        world = 世界(bx1 - bx0, by1 - by0, walls=walls)
        world.地图(d)
        for i, b in enumerate(unmapped):
            world.dyn[f"u{i}"] = rect(b)
        c = Clock(_NAV2["t_ms"] + 60_000)
        Robot = _robot_cls()
        r = Robot(now_ms=c, max_vx=ROBOT["max_vx"], max_wz=1.5, stop_latency_s=0.2,
                  latency_s=ROBOT["latency_s"], gait_start_s=ROBOT["gait_start_s"],
                  max_decel=ROBOT["max_decel"], require_clearance=ROBOT["require_clearance"],
                  imu=True)
        r.rng = rng
        r.loc_off = (rng.gauss(0, float(sim.get("loc_noise_m", 0.0)) / 2),
                     rng.gauss(0, float(sim.get("loc_noise_m", 0.0)) / 2),
                     math.radians(rng.gauss(0, float(sim.get("loc_noise_deg", 0.0)) / 2)))
        r.jitter_m = float(sim.get("loc_noise_m", 0.0)) / 4
        r.inject_head("head")
        await r.connect()
        await r.acquire_control()
        sx, sy, syaw = case["start"]
        start = Pose.from_xy_yaw(sx + ox, sy + oy, syaw)
        parts = build_engine(r, runs_root=d / "runs", now_ms=c, monotonic=lambda: c.mono,
                             map_id="m", home=start, nav_kind="nav2",
                             planner=Planner(in_process=True))
        nav = parts.nav
        nav.link = link
        view = ObstacleView(monotonic=c.s)
        nav.obstacles = view
        nav.guard = ObstacleGuard()
        events: list[tuple[float, str, dict]] = []
        nav.on_event = lambda k, dd: events.append((round(c.mono - 100.0, 1), k, dict(dd)))
        nav.load_grid(d)
        if case.get("zones"):
            await nav.set_zones(ZoneSet.from_wire({
                "map_id": "m", "map_version": "v", "revision": 1,
                "zones": [{"id": z.get("id", f"z{i}"), "kind": z.get("kind", "nogo"),
                           "polygon": [[p[0] + ox, p[1] + oy] for p in z["polygon"]]}
                          for i, z in enumerate(case["zones"])]}))
        await nav.connect()
        r.teleport(start.position.x, start.position.y, syaw)
        per = 假感知(world, rear=True, cone=True)
        delay = 0.15 + float(sim.get("obstacle_delay_ms", 0)) / 1000.0
        q: list = []

        def feed() -> None:
            g = per.grid(r.x, r.y, r.yaw)
            q.append((c.s() + delay, g))
            while q and q[0][0] <= c.s() + 1e-9:
                view.on_grid(q.pop(0)[1])
            from nexwar_localizer.obstacles import MIN_PERMIT_V, PERMIT_MS, Config, permit_vmax
            v = permit_vmax(per.净空(g, "head"), Config())
            if v >= MIN_PERMIT_V:
                r.clear(PERMIT_MS, "head", vmax=v)

        for _ in range(4):
            feed()
            c.advance(TICK)
            await nav.step(TICK)
        for _ in range(300):                              # 等 Nav2 收下这张图、时钟走起来
            await nav.step(TICK)
            r.tick(TICK)
            c.advance(TICK)
            feed()
            if link.ready:
                break
            await asyncio.sleep(0.02)
        wps = tuple(MissionWaypoint(name=f"g{i}", pose=Pose.from_xy_yaw(g[0] + ox, g[1] + oy,
                                                                        g[2]))
                    for i, g in enumerate(case["goals"]))
        mission = Mission(mission=case["scenario"], map_id="m", waypoints=wps, policy=Policy())
        await parts.engine.start(mission, home=parts.home)

        actors = case.get("actors") or []
        lines = [Timeline(a["path"], float(a.get("speed", 1.0)), a.get("mode", "once"))
                 for a in actors]
        began: list[float | None] = [None] * len(actors)
        curbs = [((p[0][0] + ox, p[0][1] + oy), (p[1][0] + ox, p[1][1] + oy))
                 for p in case.get("curbs", [])]
        climbed: set[int] = set()
        zones = [[(p[0] + ox, p[1] + oy) for p in z["polygon"]] for z in case.get("zones", [])
                 if z.get("kind", "nogo") == "nogo"]
        fault = sim.get("fault_trigger")
        fault_at: float | None = None
        out: dict[str, Any] = {"static_hit": None, "unmapped_hit": None, "actor_hit": None,
                               "actor_bumped_stopped": 0, "zone_entered": False,
                               "min_body_clear": math.inf, "min_body_clear_moving": math.inf,
                               "curb_stuck_s": 0.0, "edge_escapes": 0, "maneuvers": 0,
                               "retreats": 0, "jump_applied": False}
        flags = {"edge": False, "man": False, "back": False}
        t_sim, cut = 0.0, False
        prev = (r.x, r.y, r.yaw)
        k = 0
        while True:
            if parts.engine.state in FINAL_STATES:
                break
            if t_sim >= sim_cap_s:
                cut = True
                break
            # 规划在线程里按真实时间算:算完之前不推仿真时钟
            for _ in range(2000):
                busy = nav._planning or (nav._replan is not None and not nav._replan.done())
                if not busy:
                    break
                await asyncio.sleep(0.005)
            await nav.step(TICK)
            await parts.device.step(TICK)
            prev = (r.x, r.y, r.yaw)
            r.tick(TICK)
            # 台阶:前沿越线时朝向跟台阶线夹角太小 → 顶住不动、机身横滚
            on_curb = False
            for ci, (a, b) in enumerate(curbs):
                if ci in climbed:
                    continue
                fx0 = prev[0] + BODY_HL * math.cos(prev[2])
                fy0 = prev[1] + BODY_HL * math.sin(prev[2])
                fx1 = r.x + BODY_HL * math.cos(r.yaw)
                fy1 = r.y + BODY_HL * math.sin(r.yaw)
                ex, ey = b[0] - a[0], b[1] - a[1]
                s0 = ex * (fy0 - a[1]) - ey * (fx0 - a[0])
                s1 = ex * (fy1 - a[1]) - ey * (fx1 - a[0])
                L = math.hypot(ex, ey)
                tpar = ((fx1 - a[0]) * ex + (fy1 - a[1]) * ey) / (L * L)
                if s0 * s1 <= 0 and s0 != s1 and 0.0 <= tpar <= 1.0:
                    ang = abs(math.degrees(math.remainder(r.yaw - math.atan2(ey, ex), math.pi)))
                    if ang < CURB_STUCK_DEG:
                        r.teleport(*prev)
                        on_curb = True
                        side = -1.0 if math.sin(r.yaw - math.atan2(ey, ex)) > 0 else 1.0
                        r.inject_imu(roll=side * CURB_ROLL_RAD)
                    else:
                        climbed.add(ci)
            if not on_curb:
                r.inject_imu(roll=0.0)
            else:
                out["curb_stuck_s"] += TICK
            # 定位横跳(Gazebo loc_jump 那类)
            if fault and fault_at is None and fault.startswith("within:"):
                fx, fy, fr = (float(v) for v in fault.split(":", 1)[1].split(","))
                if math.hypot(r.x - (fx + ox), r.y - (fy + oy)) <= fr:
                    fault_at = t_sim
                    lat = float(sim.get("lateral_m", 0.3))
                    r.jump = (-math.sin(r.yaw) * lat, math.cos(r.yaw) * lat)
                    out["jump_applied"] = True
            if fault_at is not None and r.jump is not None \
                    and t_sim - fault_at > float(sim.get("fault_duration_s", 3.0)):
                r.jump = None
            c.advance(TICK)
            t_sim += TICK
            # 人、车
            for i, a in enumerate(actors):
                st = a.get("start") or {"at_s": 0.0}
                if began[i] is None:
                    if "robot_within" in st:
                        wx, wy, wr = st["robot_within"]
                        if math.hypot(r.x - (wx + ox), r.y - (wy + oy)) <= wr:
                            began[i] = t_sim
                    elif t_sim >= float(st.get("at_s", 0.0)):
                        began[i] = t_sim
                px, py = lines[i].at(0.0 if began[i] is None else t_sim - began[i])
                hx, hy = float(a["sx"]) / 2, float(a["sy"]) / 2
                world.dyn[f"a{i}"] = (px + ox - hx, py + oy - hy, px + ox + hx, py + oy + hy)
            feed()
            for _ in range(3):
                await asyncio.sleep(0)
            # Nav2 在开的时候:等它对这一拍出了速度(墙钟 ≤ 0.3 s)
            if getattr(nav, "_nav2_goal", None) is not None:
                want = nav._t_ms
                for _ in range(60):
                    cmd = link.cmd
                    if cmd is not None and cmd[1] >= want:
                        break
                    await asyncio.sleep(0.005)
            # 恢复动作计数(状态从无到有算一次)
            for key, attr, name in (("edge", "_edge", "edge_escapes"), ("man", "_man", "maneuvers"),
                                    ("back", "_back", "retreats")):
                on = getattr(nav, attr, None) is not None
                if on and not flags[key]:
                    out[name] += 1
                flags[key] = on
            # 碰撞、净空(真值)
            vx, wz = r.speed
            moving = abs(vx) > 0.05 or abs(wz) > 0.1
            poly = _corners(r.x, r.y, r.yaw)
            if out["static_hit"] is None and _hits_walls(world, r.x, r.y, r.yaw):
                out["static_hit"] = [round(t_sim, 1), round(r.x - ox, 2), round(r.y - oy, 2)]
            for nm, rr in world.dyn.items():
                if not _poly_hits_rect(poly, rr):
                    continue
                if nm.startswith("u") and out["unmapped_hit"] is None:
                    out["unmapped_hit"] = [round(t_sim, 1), nm]
                if nm.startswith("a"):
                    if moving and out["actor_hit"] is None:
                        out["actor_hit"] = [round(t_sim, 1), actors[int(nm[1:])]["name"],
                                            round(abs(vx), 2)]
                    elif not moving:
                        out["actor_bumped_stopped"] += 1
            if zones and not out["zone_entered"]:
                if any(_in_poly(px, py, z) for z in zones for px, py in poly):
                    out["zone_entered"] = True
            k += 1
            if k % 5 == 0:
                cl = _clearance(world, r.x, r.y, r.yaw)
                out["min_body_clear"] = min(out["min_body_clear"], cl)
                if moving:
                    out["min_body_clear_moving"] = min(out["min_body_clear_moving"], cl)
            if out["static_hit"] or out["unmapped_hit"] or out["actor_hit"]:
                break                                     # 撞了:停在这儿(跟 Gazebo 判停口径一样)
        _NAV2["t_ms"] = c.ms
        live = parts.engine._live
        res = list(live.results) if live is not None else []
        try:
            await nav.stop()
        except Exception:                                 # noqa: BLE001
            pass
        await parts.engine.aclose()
        kinds: dict[str, int] = {}
        for _t, kd, _d in events:
            kinds[kd] = kinds.get(kd, 0) + 1
        steps = [{"t": t, **dd} for t, kd, dd in events if kd == "recovery_step"]
        samples: dict[str, list] = {}
        for t, kd, dd in events:
            if kd != "recovery_step" and len(samples.setdefault(kd, [])) < 3:
                samples[kd].append({"t": t, **{x: (str(y)[:160] if isinstance(y, str) else y)
                                               for x, y in dd.items()}})
        reached = sum(1 for x in res if x.ok)
        total = len(case["goals"])
        return {
            "scenario": case["scenario"], "family": case.get("family"), "seed": case["seed"],
            "width_m": case.get("width_m"), "expect": case.get("expect", "arrive"),
            "oracle": case.get("oracle"),
            "engine_state": str(parts.engine.state.value if hasattr(parts.engine.state, "value")
                                else parts.engine.state),
            "engine_reason": (parts.engine.snapshot.reason or "")[:300]
            if getattr(parts.engine, "snapshot", None) else "",
            "cut_at_cap": cut, "sim_s": round(t_sim, 1),
            "goals_total": total, "goals_reached": reached,
            "waypoints": [{"name": x.name, "ok": x.ok, "note": x.note[:300], "code": x.code,
                           "elapsed_s": round(x.elapsed_s, 1)} for x in res],
            "revisited": sum(1 for x in res if "回头补" in (x.note or "")),
            "events": kinds, "event_samples": samples, "recovery_steps": steps[:60],
            **{kk: (None if isinstance(v, float) and not math.isfinite(v)
                    else (round(v, 3) if isinstance(v, float) else v)) for kk, v in out.items()},
        }


def _hits_walls(world: Any, x: float, y: float, yaw: float) -> bool:
    """机身矩形(不带余量)压没压上地图里的真值墙(不含人、车、地图外的东西)。"""
    from obs_world import RES
    c, s = math.cos(yaw), math.sin(yaw)
    u = -BODY_HL
    while u <= BODY_HL + 1e-9:
        v = -BODY_HW
        while v <= BODY_HW + 1e-9:
            px, py = x + c * u - s * v, y + s * u + c * v
            row, col = int(py / RES), int(px / RES)
            if 0 <= row < world.h and 0 <= col < world.w and world.occ[row, col]:
                return True
            v += RES / 2
        u += RES / 2
    return False


def _clearance(world: Any, x: float, y: float, yaw: float) -> float:
    """车身外沿到最近真值障碍(墙格 + 动态矩形)的距离(米);1.5 m 以外不管。"""
    import numpy as np
    from obs_world import RES
    pts = _perimeter(x, y, yaw)
    best = 1.5
    r0, r1 = int((y - 1.6) / RES), int((y + 1.6) / RES) + 1
    c0, c1 = int((x - 1.6) / RES), int((x + 1.6) / RES) + 1
    r0, c0 = max(r0, 0), max(c0, 0)
    sub = world.occ[r0:r1, c0:c1]
    ys, xs = np.nonzero(sub)
    if len(xs):
        cx = (xs + c0 + 0.5) * RES
        cy = (ys + r0 + 0.5) * RES
        P = np.array(pts)
        dd = np.sqrt((P[:, 0:1] - cx[None, :]) ** 2 + (P[:, 1:2] - cy[None, :]) ** 2) - RES / 2
        best = min(best, float(dd.min()))
    for rr in world.dyn.values():
        for px, py in pts:
            best = min(best, _rect_dist(px, py, rr))
    return max(best, 0.0)


# ------------------------------------------------------------------ 批量

def _cases(src: Path) -> list[Path]:
    return sorted(src.glob("*/*/case.json"))


async def _batch(paths: list[Path], out: Path, sim_cap_s: float) -> None:
    for p in paths:
        case = json.loads(p.read_text(encoding="utf-8"))
        dst = out / case["scenario"] / f"s{int(case['seed']):03d}" / "result.json"
        if dst.exists():
            continue
        t0 = time.monotonic()
        try:
            res = await run_case(case, sim_cap_s=sim_cap_s)
        except Exception as exc:                          # noqa: BLE001 - 记下来,接着跑下一个
            import traceback
            res = {"scenario": case["scenario"], "seed": case["seed"], "error": repr(exc)[:300],
                   "trace": traceback.format_exc()[-2000:]}
        res["wall_s"] = round(time.monotonic() - t0, 1)
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"{case['scenario']:<32} s{case['seed']:<3} "
              f"{res.get('goals_reached')}/{res.get('goals_total')} {res.get('engine_state')} "
              f"sim={res.get('sim_s')}s wall={res['wall_s']}s {res.get('error', '')}",
              flush=True)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--cases", type=Path, required=True, action="append",
                   help="放 <场景>/<种子>/case.json 的目录(可以给多个)")
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--search", dest="search", action="store_true", default=True)
    p.add_argument("--no-search", dest="search", action="store_false",
                   help="路线检查不做局部搜索(master 现在的样子)")
    p.add_argument("--only", default="", help="只跑名字里含这些的场景(逗号分开)")
    p.add_argument("--seeds", default="", help="只跑这些种子(逗号分开)")
    p.add_argument("--shard", default="1/1", help="第 i 份 / 共 n 份(并行用)")
    p.add_argument("--sim-cap-s", type=float, default=900.0, help="一趟仿真最多多少秒")
    a = p.parse_args(argv)
    import logging
    logging.disable(logging.WARNING)
    if not a.search:
        from nexwar_agent import route_check as _rc
        _rc._searched = lambda *x, **kw: None             # 局部搜索永远找不到 → 窄的照旧拒
    paths = [q for src in a.cases for q in _cases(src)]
    if a.only:
        keys = [s for s in a.only.split(",") if s]
        paths = [q for q in paths if any(s in q.parent.parent.name for s in keys)]
    if a.seeds:
        seeds = {int(s) for s in a.seeds.split(",") if s}
        paths = [q for q in paths if int(q.parent.name.lstrip("s")) in seeds]
    i, n = (int(v) for v in a.shard.split("/"))
    paths = paths[i - 1::n]
    a.out.mkdir(parents=True, exist_ok=True)
    try:
        asyncio.run(_batch(paths, a.out, a.sim_cap_s))
    finally:
        _nav2_down()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
