"""建图回归台:几个录包各自完整建图 + 回放定位,出一张表;跟基准比,标出变差的(用户 11-18)。

为什么:建图代码每次只拿一个包核(Top Glove 11-17 摆平按它一个包调,合进去才发现商场平地被纠坏)。
**规矩(用户 11-18):改建图代码的 PR(摆平、出图、去噪、栅格、Super-LIO 配置),四个包都要跑、
跟 master 基准比、只许变好或持平,``compare`` 的结果贴进 PR。** 建图代码交付后冻结,不为单个现场调。

    # 换一份代码跑(PR 的工作目录);复用基准那份 Super-LIO 位姿(两份代码比,别让 Super-LIO 每遍
    # 不一样混进来;四个包约 1 小时,大半是回放定位)
    python3 tools/map_regress.py run --bags $E/bags.json --out $E/regress/prNNN --code ../wt-N \\
        --lio-from $E/regress/master-<rev>
    # 改的是 Super-LIO 本身 / 配置:不加 --lio-from,重算(一个一个包跑,约 1.5 小时)
    python3 tools/map_regress.py compare $E/regress/master-<rev> $E/regress/prNNN
    # 站点那条路(客户自己在 App 上建图:机器人边走边存关键帧、站点主机打包):录包 + 基准那份
    # Super-LIO 位姿 → 跟机器人上逐字节一样的关键帧目录 → build --from-keyframes。改了站点打包
    # (prepare_live、摆平、栅格)两条路都跑;站点的跟站点的基准比
    python3 tools/map_regress.py run --site --bags $E/bags.json --out $E/regress/prNNN-site \
        --code ../wt-N --lio-from $E/regress/master-<rev>
    python3 tools/map_regress.py compare $E/regress/site-<rev> $E/regress/prNNN-site

台式机上 ``E=/media/liang/E/bags-level``:四个包(商场 mall3、办公室 office1、广场 plaza、
Top Glove)、``bags.json``、基准 ``regress/master-9fa18be7``(站点那条路 ``regress/site-<rev>``)。
``bags.json`` 按机器写,不进仓库::

    {"superlio_root": "/home/liang/d1max-superlio/current",
     "bags": [{"name": "mall3", "bag": "/media/liang/E/bags-level/superlio-mall3/raw-bag"},
              {"name": "topglove", "bag": "...", "rear_lidars": ".../lidars.json"}]}

每个包:``tools build --front superlio --replay``(录包里的位姿不用,半速回放重算;站点上是边走边存的
关键帧直接打包,不重算)、``tools replay --engine superlio``(初值 = 建图轨迹第一帧,参考 = 建图
轨迹),再从产物算指标(:func:`bag_metrics`)。回放每秒不到 :data:`MIN_RATE_HZ` 帧的定位结果作废
(机器忙、Super-LIO 跟不上,不算代码变差)。跑的时候别同时跑别的重活(仿真、另一份回归)。
要 ROS 的系统 Python(``source /opt/ros/humble/setup.bash``)。现场碰到四种以外的新问题,把那个
录包加进来、更新基准。
"""

from __future__ import annotations

import argparse
import json
import math
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
DOMAIN0 = 70                 # 第 i 个包用 ROS_DOMAIN_ID = DOMAIN0 + i(别跟机器人、仿真撞)
TILE_M = 10.0                # 地面倾角:按这么大一块拟合
SAME_R_M = 0.5               # 同一处:水平这么近
SAME_DT_S = 30.0             # 而且时间隔这么久(去程 / 回程)
MIN_RATE_HZ = 8.0            # 回放定位每秒处理不到这么多帧 = 被抢了,结果作废(雷达 10 帧/秒)
GROUND_R_M = 2.5             # 地面:离轨迹水平这么近
GROUND_DZ = (-0.85, -0.3)    # 而且比轨迹(雷达)低这么多(笔记本 groundtilt.py 的口径)

# 变差多少算变差(基准 → 新):(指标路径, 方向 +1 = 越大越差, 容差)
CHECKS: list[tuple[str, int, float]] = [
    ("traj.start_end_m", +1, 0.05),
    ("traj.same_place_dz.p50", +1, 0.015),
    ("traj.same_place_dz.max", +1, 0.03),
    ("ground.tilt_deg.p90", +1, 0.3),
    ("replay.trusted", -1, 0.02),
    ("replay.error.p95", +1, 0.03),
    ("replay.jumps", +1, 3),
    ("grid.free_rel", -1, 0.02),
    ("grid.curb_rel", +1, 0.20),
]


# ---------------------------------------------------------------- 指标(纯函数)

def read_tum(path: Path) -> np.ndarray:
    """TUM 轨迹 → N×8(t x y z qx qy qz qw)。"""
    rows = [list(map(float, ln.split()[:8])) for ln in path.read_text().splitlines()
            if ln.strip() and not ln.startswith("#")]
    return np.array(rows, float).reshape(-1, 8)


def same_place_dz(t: np.ndarray, xyz: np.ndarray, *, r: float = SAME_R_M, dt: float = SAME_DT_S,
                  n_max: int = 3000) -> dict[str, float]:
    """同一处(水平 ``r`` 内、时间隔 ``dt`` 以上)两次经过的高度差:每个点取跟它最远的那次,
    回分位数。没有经过两次的:都是 0、``n`` = 0。"""
    sub = np.arange(0, len(t), max(1, len(t) // n_max))
    q, qt = xyz[sub], t[sub]
    out = []
    for i in range(len(q)):
        near = np.linalg.norm(q[:, :2] - q[i, :2], axis=1) < r
        j = np.nonzero(near & (np.abs(qt - qt[i]) > dt))[0]
        if len(j):
            out.append(float(np.abs(q[j, 2] - q[i, 2]).max()))
    if not out:
        return {"n": 0, "p50": 0.0, "p95": 0.0, "max": 0.0}
    a = np.array(out)
    return {"n": len(a), "p50": round(float(np.median(a)), 3),
            "p95": round(float(np.percentile(a, 95)), 3), "max": round(float(a.max()), 3)}


def tile_tilts(pts: np.ndarray, traj: np.ndarray, *, tile: float = TILE_M,
               min_pts: int = 200) -> list[float]:
    """3D 点 + 轨迹(N×3)→ 每 ``tile`` 米一块的地面倾角(度)。口径跟笔记本 groundtilt.py 一样:
    离轨迹水平 :data:`GROUND_R_M` 以内、比最近的轨迹点低 :data:`GROUND_DZ` 的点当地面,
    拟合 z = ax + by + c、去掉离得远的再拟两遍。点不够的块不算。"""
    if len(pts) == 0 or len(traj) == 0:
        return []
    tr = traj[:: max(1, len(traj) // 4000)]
    keep = np.zeros(len(pts), bool)
    for i in range(0, len(pts), 20000):                  # 分块找最近的轨迹点(不要 scipy)
        q = pts[i:i + 20000]
        d2 = ((q[:, None, :2] - tr[None, :, :2]) ** 2).sum(-1)
        j = d2.argmin(1)
        rel = q[:, 2] - tr[j, 2]
        keep[i:i + 20000] = ((d2[np.arange(len(q)), j] < GROUND_R_M ** 2)
                             & (rel > GROUND_DZ[0]) & (rel < GROUND_DZ[1]))
    g_all = pts[keep]
    ij = np.floor(g_all[:, :2] / tile).astype(int)
    keys, inv = np.unique(ij, axis=0, return_inverse=True)
    out = []
    for k in range(len(keys)):
        g = g_all[inv.ravel() == k]
        if len(g) < min_pts:
            continue
        A = np.c_[g[:, 0], g[:, 1], np.ones(len(g))]
        z = g[:, 2]
        for _ in range(3):
            c, *_ = np.linalg.lstsq(A, z, rcond=None)
            res = np.abs(z - A @ c)
            ok = res < max(0.03, 2.5 * float(np.median(res)))
            A, z = A[ok], z[ok]
        out.append(round(math.degrees(math.atan(math.hypot(c[0], c[1]))), 2))
    return out


def read_pgm(path: Path) -> np.ndarray:
    """P5 / P4 位图 → 数组(P4 的 1 = 黑)。"""
    data = path.read_bytes()
    parts: list[bytes] = []
    pos = 0
    while len(parts) < (3 if data[:2] == b"P4" else 4):
        while data[pos:pos + 1].isspace():
            pos += 1
        if data[pos:pos + 1] == b"#":
            pos = data.index(b"\n", pos) + 1
            continue
        end = pos
        while not data[end:end + 1].isspace():
            end += 1
        parts.append(data[pos:end])
        pos = end
    pos += 1
    w, h = int(parts[1]), int(parts[2])
    if parts[0] == b"P4":
        bits = np.unpackbits(np.frombuffer(data[pos:], np.uint8))
        return bits.reshape(h, -1)[:, :w]
    return np.frombuffer(data[pos:pos + w * h], np.uint8).reshape(h, w)


def grid_counts(floor: np.ndarray, curb: np.ndarray | None) -> dict[str, int]:
    """平面图(trinary:254 空地、0 障碍、其余未知)+ 路沿位图 → 格子数。"""
    return {"free": int((floor == 254).sum()), "occupied": int((floor == 0).sum()),
            "unknown": int(((floor != 254) & (floor != 0)).sum()),
            "curb": int(curb.sum()) if curb is not None else 0}


def read_pcd_xyz(path: Path) -> np.ndarray:
    """PCD(ascii 或 binary,float x y z 在前)→ N×3。"""
    data = path.read_bytes()
    head_end = data.index(b"DATA")
    head = data[:head_end].decode(errors="replace").split("\n")
    kv = {ln.split()[0]: ln.split()[1:] for ln in head if ln.strip() and not ln.startswith("#")}
    fields, sizes = kv["FIELDS"], list(map(int, kv["SIZE"]))
    counts = list(map(int, kv.get("COUNT", ["1"] * len(fields))))
    n = int(kv["POINTS"][0])
    line_end = data.index(b"\n", head_end) + 1
    kind = data[head_end:line_end].split()[1].decode()
    idx = [fields.index(c) for c in ("x", "y", "z")]
    if kind == "ascii":
        rows = np.loadtxt(data[line_end:].decode().splitlines(), ndmin=2)
        return rows[:, idx].astype(float)
    if kind != "binary":
        raise ValueError(f"不认识的 PCD DATA {kind}")
    step = sum(s * c for s, c in zip(sizes, counts, strict=True))
    raw = np.frombuffer(data[line_end:line_end + n * step], np.uint8).reshape(n, step)
    offs = np.cumsum([0] + [s * c for s, c in zip(sizes, counts, strict=True)])[:-1]
    return np.stack([raw[:, offs[i]:offs[i] + 4].copy().view(np.float32).ravel() for i in idx],
                    axis=1).astype(float)


def bag_metrics(map_dir: Path, work: Path, replay_dir: Path | None) -> dict[str, Any]:
    """一个包的产物 → 指标。"""
    b = json.loads((map_dir / "build.json").read_text())
    front = b.get("mola", {})
    tr = read_tum(work / "traj.tum")
    xyz = tr[:, 1:4]
    m: dict[str, Any] = {
        "traj": {"path_m": front.get("quality", {}).get("path_m"),
                 "start_end_m": round(float(np.linalg.norm(xyz[-1] - xyz[0])), 3),
                 "z_span_m": round(float(np.ptp(xyz[:, 2])), 3),
                 "same_place_dz": same_place_dz(tr[:, 0], xyz)},
        "level": {k: front.get("level", {}).get(k) for k in
                  ("applied", "max_deg", "bias_deg", "const_windows", "why")},
    }
    pcd = map_dir / "superlio_map.pcd"
    if pcd.exists():
        tl = tile_tilts(read_pcd_xyz(pcd), xyz)
        m["ground"] = {"tiles": len(tl), "tilt_deg": {
            "p50": round(float(np.median(tl)), 2) if tl else None,
            "p90": round(float(np.percentile(tl, 90)), 2) if tl else None,
            "max": max(tl) if tl else None}}
    floor = read_pgm(map_dir / "floor.pgm")
    curb_p = map_dir / "curb.pbm"
    g = grid_counts(floor, read_pgm(curb_p) if curb_p.exists() else None)
    known = max(1, g["free"] + g["occupied"])
    g["free_rel"] = round(g["free"] / known, 4)
    g["curb_rel"] = round(g["curb"] / max(1, g["occupied"]), 4)
    m["grid"] = g
    if replay_dir is not None and (replay_dir / "metrics.json").exists():
        r = json.loads((replay_dir / "metrics.json").read_text())
        err = r.get("error_m", {}).get("trusted", {}) or {}
        m["replay"] = {"frames": r.get("frames"), "rate_hz": r.get("rate_hz"),
                       "trusted": r.get("agent_trusted_share"),
                       "jumps": r.get("jumps"), "states": r.get("localizer_states"),
                       "error": {"p50": err.get("p50"), "p95": err.get("p95"),
                                 "max": err.get("max")}}
        if (r.get("rate_hz") or 0) < MIN_RATE_HZ:         # 算不过来:不是代码的事,不拿来比
            m["replay"] = {"invalid": f"回放只跑到 {r.get('rate_hz')} 帧/秒(CPU 或磁盘被抢),作废",
                           "rate_hz": r.get("rate_hz")}
    return m


def get(d: dict[str, Any], path: str) -> Any:
    for k in path.split("."):
        if not isinstance(d, dict) or k not in d:
            return None
        d = d[k]
    return d


def compare(base: dict[str, Any], new: dict[str, Any]) -> list[dict[str, Any]]:
    """两次的结果(包名 → 指标)→ 每包每项:基准、新、变差没有。缺的不判。"""
    rows = []
    for name in sorted(set(base) | set(new)):
        for path, sign, tol in CHECKS:
            a, b = get(base.get(name, {}), path), get(new.get(name, {}), path)
            worse = (a is not None and b is not None and sign * (b - a) > tol)
            rows.append({"bag": name, "metric": path, "base": a, "new": b, "worse": worse})
    return rows


def report_md(results: dict[str, Any]) -> str:
    cols = [("回到起点 m", "traj.start_end_m"), ("同处高度差 中位/最大 m", "traj.same_place_dz"),
            ("高度起伏 m", "traj.z_span_m"), ("地面倾角 中位/p90°", "ground.tilt_deg"),
            ("摆平", "level"), ("空地/障碍/未知/路沿", "grid"), ("定位可信", "replay.trusted"),
            ("定位误差 p50/p95 m", "replay.error"), ("跳变", "replay.jumps")]
    lines = ["| 包 | " + " | ".join(c for c, _ in cols) + " |", "|---" * (len(cols) + 1) + "|"]
    for name, m in sorted(results.items()):
        if "error" in m:
            lines.append(f"| {name} | 失败:{m['error']} |")
            continue
        cells = []
        for _, p in cols:
            v = get(m, p)
            if p == "traj.same_place_dz" and v:
                v = f"{v['p50']} / {v['max']}"
            elif p == "ground.tilt_deg" and v:
                v = f"{v['p50']} / {v['p90']}"
            elif p == "level" and v:
                v = (f"{v.get('max_deg')}°、常量 {v.get('const_windows')} 段"
                     if v.get("applied") else "不改")
            elif p == "grid" and v:
                v = f"{v['free']} / {v['occupied']} / {v['unknown']} / {v['curb']}"
            elif p == "replay.error" and v:
                v = f"{v['p50']} / {v['p95']}"
            elif p == "replay.trusted" and v is not None:
                v = f"{v:.0%}"
            elif p.startswith("replay.") and get(m, "replay.invalid"):
                v = "作废"
            cells.append("—" if v is None else str(v))
        lines.append(f"| {name} | " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def compare_md(rows: list[dict[str, Any]]) -> str:
    bad = [r for r in rows if r["worse"]]
    out = [f"变差 {len(bad)} 项" + ("" if bad else "(全部持平或变好)"), "",
           "| 包 | 指标 | 基准 | 新 | |", "|---|---|---|---|---|"]
    for r in rows:
        if r["base"] is None and r["new"] is None:
            continue
        out.append(f"| {r['bag']} | {r['metric']} | {r['base']} | {r['new']} | "
                   f"{'⚠ 变差' if r['worse'] else ''} |")
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------- 跑

def _pythonpath(code: Path) -> str:
    return ":".join([*map(str, sorted((code / "packages").glob("*/src"))), str(code / "src")])


def _first_pose_2d(map_dir: Path, work: Path, code: Path) -> tuple[float, float, float]:
    """建图轨迹第一帧 → 地图平面上的 x, y, yaw(用那份代码的 frames.json 换算)。"""
    sys.path[:0] = _pythonpath(code).split(":")
    from nexwar_localizer.frames import Frames
    tr = read_tum(work / "traj.tum")
    f = Frames.load(map_dir / "frames.json")
    return f.to_map2d(tr[0, 1:4].tolist(), tr[0, 4:8].tolist())


#: ``--lio-from``:Super-LIO 不回放,直接用另一次跑出来的位姿包(笔记本 v6–v15 的做法)。两份代码吃
#: 同一份轨迹,比出来的差别只来自代码(Super-LIO 每回放一遍姿态差零点几度,台式机 11-18 商场)。
_REUSE_LIO = ("import sys; from pathlib import Path; "
              "from nexwar_localizer import superlio as S, tools; "
              "L = Path(sys.argv[1]); S.run_offline = lambda bag, work, **kw: L; "
              "sys.exit(tools.main(sys.argv[2:]))")


def _job(i: int, spec: dict[str, Any], out: Path, code: Path, cores: str, sroot: str,
         py: str, lio_from: Path | None = None, site: bool = False) -> subprocess.Popen[bytes]:
    d = out / spec["name"]
    d.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "PYTHONPATH": _pythonpath(code) + ":" + os.environ.get("PYTHONPATH", ""),
           "ROS_DOMAIN_ID": str(DOMAIN0 + i + int(cores.replace(",", "-").split("-")[0])),
           "NEXWAR_SUPERLIO_ROOT": sroot, "PYTHONDONTWRITEBYTECODE": "1"}
    head = ["-m", "nexwar_localizer.tools"]
    if site:
        return _site_job(spec, d, env, cores, py, lio_from)
    if lio_from is not None:
        lio = lio_from / spec["name"] / "map.work" / "lio_bag"
        if not (lio / "metadata.yaml").exists():
            raise SystemExit(f"--lio-from 里没有 {lio}")
        head = ["-c", _REUSE_LIO, str(lio.resolve())]
    cmd = ["taskset", "-c", cores, py, *head, "build",
           "--bag", spec["bag"], "--out", str(d / "map"), "--work", str(d / "map.work"),
           "--front", "superlio", "--replay", *spec.get("build_args", [])]
    if spec.get("rear_lidars"):
        cmd += ["--rear-lidars", spec["rear_lidars"]]
    log = (d / "build.log").open("wb")
    return subprocess.Popen(cmd, env=env, stdout=log, stderr=subprocess.STDOUT, cwd=d)


def site_cmds(spec: dict[str, Any], d: Path, py: str, lio: Path) -> list[list[str]]:
    """站点那条路的两步:录包 + Super-LIO 位姿 → 关键帧目录(``d/live``)→ 站点打包(``d/map``)。
    后雷达不用(机器人边走边存的只有前雷达)。"""
    tools = [py, "-m", "nexwar_localizer.tools"]
    return [[*tools, "live-from-bag", "--bag", spec["bag"], "--lio", str(lio),
             "--out", str(d / "live")],
            [*tools, "build", "--from-keyframes", str(d / "live"), "--out", str(d / "map"),
             "--work", str(d / "map.work")]]


def _site_job(spec: dict[str, Any], d: Path, env: dict[str, str], cores: str, py: str,
              lio_from: Path | None) -> subprocess.Popen[bytes]:
    if lio_from is None:
        raise SystemExit("--site 要 --lio-from(用哪次的 Super-LIO 位姿模拟机器人边走边存)")
    lio = lio_from / spec["name"] / "map.work" / "lio_bag"
    if not (lio / "metadata.yaml").exists():
        raise SystemExit(f"--lio-from 里没有 {lio}")
    script = " && ".join(shlex.join(["taskset", "-c", cores, *c])
                         for c in site_cmds(spec, d, py, lio.resolve()))
    log = (d / "build.log").open("wb")
    return subprocess.Popen(["bash", "-c", script], env=env, stdout=log,
                            stderr=subprocess.STDOUT, cwd=d)


def fast_cpus(max_khz: dict[int, int] | None = None) -> list[int]:
    """最快那一档的核(大小核的机器只要大核;台式机 i7-14700:0–15 是 5.3 GHz 大核、16–27 是 4.2 GHz
    小核,广场的包回放绑到小核上 Super-LIO 只跑到 4.3 帧/秒、定位丢了,11-18)。读不到频率就全用。"""
    if max_khz is None:
        max_khz = {}
        for f in Path("/sys/devices/system/cpu").glob("cpu[0-9]*/cpufreq/cpuinfo_max_freq"):
            try:
                max_khz[int(f.parent.parent.name[3:])] = int(f.read_text())
            except (OSError, ValueError):
                pass
    if not max_khz:
        return list(range(os.cpu_count() or 1))
    top = max(max_khz.values())
    return sorted(c for c, k in max_khz.items() if k >= 0.9 * top)


def _replay_job(i: int, spec: dict[str, Any], out: Path, code: Path, cores: str, sroot: str,
                py: str) -> subprocess.Popen[bytes]:
    d = out / spec["name"]
    x, y, yaw = _first_pose_2d(d / "map", d / "map.work", code)
    env = {**os.environ, "PYTHONPATH": _pythonpath(code) + ":" + os.environ.get("PYTHONPATH", ""),
           "ROS_DOMAIN_ID": str(DOMAIN0 + i + int(cores.replace(",", "-").split("-")[0])),
           "NEXWAR_SUPERLIO_ROOT": sroot, "PYTHONDONTWRITEBYTECODE": "1"}
    cmd = ["taskset", "-c", cores, py, "-m", "nexwar_localizer.tools", "replay",
           "--bag", spec["bag"], "--prior", str(d / "map"), f"--init={x},{y},{yaw}",
           "--out", str(d / "replay"), "--engine", "superlio", "--superlio-root", sroot,
           "--reference", str(d / "map.work" / "traj.tum")]
    log = (d / "replay.log").open("wb")
    return subprocess.Popen(cmd, env=env, stdout=log, stderr=subprocess.STDOUT, cwd=d)


def _run(a: argparse.Namespace) -> int:
    cfg = json.loads(a.bags.read_text())
    bags = [b for b in cfg["bags"] if not a.only or b["name"] in a.only.split(",")]
    sroot = cfg.get("superlio_root") or os.environ.get("NEXWAR_SUPERLIO_ROOT", "")
    code = a.code.resolve()
    a.out.mkdir(parents=True, exist_ok=True)
    rev = subprocess.run(["git", "-C", str(code), "rev-parse", "--short", "HEAD"],
                         capture_output=True, text=True).stdout.strip()
    n = os.cpu_count() or 8
    per = max(2, min(a.cores, n // max(1, len(bags))))
    o = a.core_offset
    cores = [f"{o + i * per}-{o + i * per + per - 1}" for i in range(len(bags))]
    t0 = time.monotonic()
    old = a.out / "results.json"                 # 同一份代码分几次跑(--only):结果并进一张表
    prev = json.loads(old.read_text()) if old.exists() else {}
    if prev and prev.get("rev") != rev:
        raise SystemExit(f"{old} 是 {prev.get('rev')} 跑的,这次是 {rev}:换个 --out")
    results: dict[str, Any] = dict(prev.get("bags", {}))
    for b in bags:
        results.pop(b["name"], None)
    # 重算 Super-LIO 的建图一个一个跑(台式机 11-18:广场跟 Top Glove 同时回放,Super-LIO 掉了 36%
    # 的位姿);复用位姿(--lio-from)只剩打栅格,一起跑。回放定位按实时、怕抢(办公室回放跟商场建图
    # 同时跑,Super-LIO 只跑到 3.65 帧/秒、飞了几千米),等建图全完再一个一个跑
    failed: dict[str, str] = {}
    replay_cores = ",".join(map(str, fast_cpus()))
    if not a.replay_only:
        def build(i: int, b: dict[str, Any]) -> subprocess.Popen[bytes]:
            return _job(i, b, a.out, code, cores[i], sroot, a.python, a.lio_from, a.site)
        if a.lio_from:
            procs = {b["name"]: build(i, b) for i, b in enumerate(bags)}
            rcs = {name: p.wait() for name, p in procs.items()}
        else:
            rcs = {b["name"]: build(i, b).wait() for i, b in enumerate(bags)}
        for name, rc in rcs.items():
            if rc != 0:
                failed[name] = f"build 退出码 {rc}(见 {a.out / name / 'build.log'})"
    for i, b in enumerate(bags):
        name = b["name"]
        if name in failed or a.no_replay:
            continue
        # 回放一个一个跑、按实时:全给大核(按包分的核可能落在小核上)
        p = _replay_job(i, b, a.out, code, replay_cores, sroot, a.python)
        if p.wait() != 0:
            failed[name] = f"replay 退出码 {p.returncode}(见 {a.out / name / 'replay.log'})"
    for b in bags:
        name = b["name"]
        d = a.out / name
        results[name] = ({"error": failed[name]} if name in failed else
                         bag_metrics(d / "map", d / "map.work",
                                     None if a.no_replay else d / "replay"))
    if old.exists():                             # 别的 --only 同时在跑:写之前再并一次
        results = {**json.loads(old.read_text()).get("bags", {}), **results}
    summary = {"code": str(code), "rev": rev, "wall_s": round(time.monotonic() - t0),
               "lio_from": str(a.lio_from) if a.lio_from else None, "site": a.site,
               "bags": results}
    (a.out / "results.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    path = "站点打包" if a.site else "录包建图"
    md = f"# 建图回归 {rev} {path}({summary['wall_s']} s)\n\n" + report_md(results)
    (a.out / "report.md").write_text(md)
    print(md)
    return 1 if any("error" in m for m in results.values()) else 0


def _compare(a: argparse.Namespace) -> int:
    bj, nj = (json.loads((x / "results.json").read_text()) for x in (a.base, a.new))
    if bool(bj.get("site")) != bool(nj.get("site")):
        raise SystemExit("一个是站点打包、一个是录包建图:跟同一条路的基准比")
    base, new = bj["bags"], nj["bags"]
    rows = compare(base, new)
    md = compare_md(rows)
    print(md)
    return 1 if any(r["worse"] for r in rows) else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--bags", type=Path, required=True)
    r.add_argument("--out", type=Path, required=True)
    r.add_argument("--code", type=Path, default=ROOT, help="用哪份代码建图(仓库根)")
    r.add_argument("--only", default="", help="只跑这几个包(逗号分开)")
    r.add_argument("--cores", type=int, default=6, help="每个包最多几个核")
    r.add_argument("--core-offset", type=int, default=0, help="从第几个核开始分(两次同时跑时错开)")
    r.add_argument("--no-replay", action="store_true", help="只建图,不回放定位")
    r.add_argument("--replay-only", action="store_true", help="图已经建好了,只重跑回放定位")
    r.add_argument("--lio-from", type=Path, default=None,
                   help="Super-LIO 不回放,用这次跑的结果目录里的位姿包(比代码改动时用)")
    r.add_argument("--site", action="store_true",
                   help="走站点那条路(关键帧 → build --from-keyframes);要 --lio-from")
    r.add_argument("--python", default="/usr/bin/python3", help="ROS 的系统 Python")
    c = sub.add_parser("compare")
    c.add_argument("base", type=Path)
    c.add_argument("new", type=Path)
    a = ap.parse_args(argv)
    return _run(a) if a.cmd == "run" else _compare(a)


if __name__ == "__main__":
    raise SystemExit(main())
