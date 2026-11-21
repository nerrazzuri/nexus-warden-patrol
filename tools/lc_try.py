"""回环对照(实验,用户 11-21):同一份关键帧,不回环 / MOLA 回环 / 厂家那种回环,哪个图更准。

为什么:Super-LIO 本身没有回环(上游最新版也没有,作者推荐另接 Voxel-SLAM)。它的体素地图整张留着,
回到老地方直接对旧图配准,等于边建边合环 —— 11-21 四个回归包(商场、办公室、广场、Top Glove)上
两种回环都没让图更准(广场还略差),所以默认不回环。**比这四个包大的场地(11-26 室外 + 室内)没试过**,
漂移大到对不上旧图时回环才有用:拿那次的关键帧跑这个,看要不要开。

厂家那种(智元 ``robot_slam``,LIO-SAM 的做法):每走 :data:`QUERY_STEP` 米,在水平 :data:`SEARCH_R`
米内、隔 :data:`MIN_DT` 秒以上的老关键帧里挑最近的一个当候选;当前帧跟候选前后共 25 帧拼的子图做
ICP(粗到细);对得上(内点够多、均方根够小、改正量不离谱)就加一条回环边;最后整条轨迹做位姿图优化
(open3d 的 LM + line process,认错的回环边自己掉权)。按改过的位姿再找一轮候选。

尺子(:func:`consistency`,不依赖哪种回环):隔 30 s 以上回到 2 m 内的两帧,一帧的点到另一帧墙面
(法向)的距离取中位数,按对汇总(p50 / p90 / 大于 3 cm 的对数)。单帧噪声约 2 cm;墙扫成两层会大。

    # 站点上留着的关键帧(``<站点数据>/mapkf-keep/<机器人>/<图>/<版本>/``,只留最近 5 份 —— 建完拷走)
    /usr/bin/python3 tools/lc_try.py <关键帧目录> --out <输出目录> \\
        --kf2sm /home/liang/d1max-superlio/current/bin/kf2sm
    # 不给 --kf2sm(或没有 mola-sm-lc-cli)就只比「不回环 / 新回环」

要 open3d、scipy(台式机的系统 Python 有);跑 MOLA 那份要 ``source /opt/ros/humble/setup.bash``。
出 ``<输出目录>/report.md`` 和 ``result.json``。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
LC_PIPELINE = ROOT / "packages/localizer/src/nexwar_localizer/pipelines/loop-closure.yaml"

# MOLA 日志里的回环数(跟 build.py 的 _LC_COUNT 同一个口径)
LC_COUNT = re.compile(r"(?:Overall number of accepted loop-closures|Total accepted loop closures)"
                      r":\s*(\d+)")

# 新回环
SEARCH_R = 10.0       # 候选:水平这么近
MIN_DT = 30.0         # 而且隔这么久(LIO-SAM 30 s)
QUERY_STEP = 1.0      # 每走这么远问一次
SUB_K = 12            # 子图:候选前后各 12 帧(共 25 帧,跟厂家一样)
VOX = 0.2             # 配准用的体素(厂家 filter_size 0.2)
RANGE = 30.0          # 只用这么近的点
FIT_RMSE = 0.10       # 接受:内点均方根 ≤ 这么多(米)
FIT_RATIO = 0.5       # 而且这么多点对上
MAX_CORR_M = 3.0      # 改正量超过这么多多半认错
MAX_CORR_DEG = 15.0
ODO_SIG = (0.01, 0.002)   # 里程边:米、弧度
LOOP_SIG = (0.05, 0.01)   # 回环边
ROUNDS = 2

# 尺子
EV_NEAR, EV_DT, EV_STEP, EV_RANGE, EV_VOX, EV_OVER, EV_MIN_PTS = 2.0, 30.0, 1.0, 15.0, 0.1, 0.3, 200


def read_index(kf: Path) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """关键帧目录(``index.txt``:时刻 x y z qx qy qz qw … 文件名)→ (时刻, N×4×4 位姿, 文件名)。"""
    from scipy.spatial.transform import Rotation

    rows = [ln.split() for ln in (kf / "index.txt").read_text().splitlines() if ln.strip()]
    t = np.array([float(r[0]) for r in rows])
    T = np.tile(np.eye(4), (len(rows), 1, 1))
    for i, r in enumerate(rows):
        v = list(map(float, r[1:8]))
        T[i, :3, :3] = Rotation.from_quat(v[3:7]).as_matrix()
        T[i, :3, 3] = v[:3]
    return t, T, [r[-1] for r in rows]


def read_tum_at(path: Path, t_ref: np.ndarray) -> np.ndarray:
    """TUM 位姿按 ``t_ref`` 的时刻取(差 50 ms 以内)。"""
    from scipy.spatial.transform import Rotation

    rows = np.loadtxt(path).reshape(-1, 8)
    T = np.tile(np.eye(4), (len(t_ref), 1, 1))
    for k, t in enumerate(t_ref):
        r = rows[int(np.argmin(abs(rows[:, 0] - t)))]
        if abs(r[0] - t) > 0.05:
            raise SystemExit(f"{path}:{t:.3f} 这一帧没有位姿")
        T[k, :3, :3] = Rotation.from_quat(r[4:8]).as_matrix()
        T[k, :3, 3] = r[1:4]
    return T


def write_tum(path: Path, t: np.ndarray, T: np.ndarray) -> None:
    from scipy.spatial.transform import Rotation

    with path.open("w") as f:
        for k in range(len(t)):
            q = Rotation.from_matrix(T[k, :3, :3]).as_quat()
            f.write(f"{t[k]:.6f} " + " ".join(f"{v:.6f}" for v in (*T[k, :3, 3], *q)) + "\n")


def _cloud(kf: Path, name: str, rng: float, vox: float) -> np.ndarray:
    import open3d as o3d

    xyz = np.fromfile(kf / name, "<f4").reshape(-1, 3).astype(float)
    xyz = xyz[np.linalg.norm(xyz, axis=1) < rng]
    return np.asarray(o3d.geometry.PointCloud(
        o3d.utility.Vector3dVector(xyz)).voxel_down_sample(vox).points)


def _pcd(xyz: np.ndarray) -> Any:
    import open3d as o3d

    p = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(xyz))
    p.estimate_normals(o3d.geometry.KDTreeSearchParamHybrid(radius=0.6, max_nn=20))
    return p


def _info(sig: tuple[float, float]) -> np.ndarray:
    st, sr = sig
    return np.diag([1 / sr**2] * 3 + [1 / st**2] * 3)     # open3d:先转后移


def loop_close_sam(kf: Path) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    """厂家那种回环 → (时刻, 改过的位姿, 汇总)。"""
    import open3d as o3d
    from scipy.spatial import cKDTree
    from scipy.spatial.transform import Rotation

    reg = o3d.pipelines.registration
    o3d.utility.set_verbosity_level(o3d.utility.VerbosityLevel.Error)
    t0 = time.monotonic()
    t, T0, names = read_index(kf)
    clouds = [_cloud(kf, n, RANGE, VOX) for n in names]

    def submap(T: np.ndarray, j: int) -> Any:
        lo, hi = max(0, j - SUB_K), min(len(clouds), j + SUB_K + 1)
        pts = np.vstack([clouds[k] @ T[k, :3, :3].T + T[k, :3, 3] for k in range(lo, hi)])
        return _pcd(np.asarray(o3d.geometry.PointCloud(
            o3d.utility.Vector3dVector(pts)).voxel_down_sample(VOX).points))

    def candidates(T: np.ndarray, done: set[tuple[int, int]]) -> list[tuple[int, int]]:
        xy = T[:, :2, 3]
        tree = cKDTree(xy)
        out, walked = [], 0.0
        for i in range(1, len(t)):
            walked += float(np.linalg.norm(xy[i] - xy[i - 1]))
            if walked < QUERY_STEP:
                continue
            js = [j for j in tree.query_ball_point(xy[i], SEARCH_R) if t[i] - t[j] >= MIN_DT]
            if js:
                j = min(js, key=lambda j: float(np.linalg.norm(xy[i] - xy[j])))
                if (i, j) not in done:
                    out.append((i, j))
                walked = 0.0
        return out

    def optimize(loops: list[tuple[int, int, np.ndarray]]) -> np.ndarray:
        g = reg.PoseGraph()
        for k in range(len(T0)):
            g.nodes.append(reg.PoseGraphNode(T0[k]))
        for k in range(len(T0) - 1):              # open3d 的边:Z = P_target⁻¹ · P_source
            g.edges.append(reg.PoseGraphEdge(k + 1, k, np.linalg.inv(T0[k]) @ T0[k + 1],
                                             _info(ODO_SIG), uncertain=False))
        for i, j, Z in loops:
            g.edges.append(reg.PoseGraphEdge(i, j, Z, _info(LOOP_SIG), uncertain=True))
        reg.global_optimization(
            g, reg.GlobalOptimizationLevenbergMarquardt(),
            reg.GlobalOptimizationConvergenceCriteria(),
            reg.GlobalOptimizationOption(max_correspondence_distance=0.25,
                                         edge_prune_threshold=0.25, reference_node=0))
        return np.array([n.pose for n in g.nodes])

    T, loops, done, rounds = T0.copy(), [], set(), []
    for _ in range(ROUNDS):
        t1 = time.monotonic()
        cand, acc = candidates(T, done), 0
        for i, j in cand:
            done.add((i, j))
            src, tgt, init = _pcd(clouds[i]), submap(T, j), T[i].copy()
            for d in (1.0, 0.5, 0.25):
                init = reg.registration_icp(src, tgt, d, init,
                                            reg.TransformationEstimationPointToPlane(),
                                            reg.ICPConvergenceCriteria(max_iteration=30)
                                            ).transformation
            ev = reg.evaluate_registration(src, tgt, 0.25, init)
            C = init @ np.linalg.inv(T[i])
            turn = float(np.degrees(np.linalg.norm(Rotation.from_matrix(C[:3, :3]).as_rotvec())))
            if (ev.fitness < FIT_RATIO or ev.inlier_rmse > FIT_RMSE
                    or np.linalg.norm(C[:3, 3]) > MAX_CORR_M or turn > MAX_CORR_DEG):
                continue
            loops.append((i, j, np.linalg.inv(T[j]) @ init))
            acc += 1
        t2 = time.monotonic()
        if acc:
            T = optimize(loops)
        rounds.append({"candidates": len(cand), "accepted": acc,
                       "register_s": round(t2 - t1, 1),
                       "optimize_s": round(time.monotonic() - t2, 1)})
        if not acc:
            break
    return t, T, {"loops": len(loops), "rounds": rounds,
                  "seconds": round(time.monotonic() - t0, 1)}


def consistency(kf: Path, t: np.ndarray, names: list[str], sets: dict[str, np.ndarray]
                ) -> dict[str, Any]:
    """尺子:回到同一处的两帧墙面贴得多紧(厘米)。对按第一份位姿挑,每份用同样的对。"""
    import open3d as o3d
    from scipy.spatial import cKDTree

    xy = next(iter(sets.values()))[:, :2, 3]
    tree = cKDTree(xy)
    pairs, walked = [], 0.0
    for i in range(1, len(t)):
        walked += float(np.linalg.norm(xy[i] - xy[i - 1]))
        if walked < EV_STEP:
            continue
        js = [j for j in tree.query_ball_point(xy[i], EV_NEAR) if t[i] - t[j] > EV_DT]
        if js:
            pairs.append((i, min(js, key=lambda j: float(np.linalg.norm(xy[i] - xy[j])))))
            walked = 0.0
    cache: dict[int, tuple[np.ndarray, np.ndarray]] = {}

    def cloud(k: int) -> tuple[np.ndarray, np.ndarray]:
        if k not in cache:
            p = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(
                _cloud(kf, names[k], EV_RANGE, EV_VOX)))
            p.estimate_normals(o3d.geometry.KDTreeSearchParamHybrid(radius=0.4, max_nn=20))
            cache[k] = (np.asarray(p.points), np.asarray(p.normals))
        return cache[k]

    out: dict[str, Any] = {"pairs": len(pairs)}
    for name, T in sets.items():
        meds = []
        for i, j in pairs:
            (pi, _), (pj, nj) = cloud(i), cloud(j)
            wi = pi @ T[i, :3, :3].T + T[i, :3, 3]
            wj = pj @ T[j, :3, :3].T + T[j, :3, 3]
            d, idx = cKDTree(wj).query(wi, distance_upper_bound=EV_OVER)
            ok = np.isfinite(d)
            if ok.sum() < EV_MIN_PTS:            # 反方向走回来,前雷达看的不是同一面
                continue
            nw = nj[idx[ok]] @ T[j, :3, :3].T
            meds.append(float(np.median(np.abs(np.einsum("ij,ij->i", wi[ok] - wj[idx[ok]], nw)))))
        m = np.array(meds) * 100
        out[name] = ({"n": len(m), "p50_cm": round(float(np.median(m)), 2),
                      "p90_cm": round(float(np.percentile(m, 90)), 2),
                      "over_3cm": int((m > 3).sum())} if len(m) else {"n": 0})
    return out


def _moved(T0: np.ndarray, T: np.ndarray) -> dict[str, float]:
    d = np.linalg.norm(T[:, :3, 3] - T0[:, :3, 3], axis=1)
    return {"median_m": round(float(np.median(d)), 3), "max_m": round(float(d.max()), 3)}


def run_mola(kf: Path, out: Path, kf2sm: str, t: np.ndarray) -> tuple[np.ndarray, dict[str, Any]]:
    """MOLA 回环(建图向导「优化地图」那条):kf2sm → mola-sm-lc-cli → 导出关键帧位姿。"""
    d = out / "mola"
    shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True)
    subprocess.run([kf2sm, str(kf), str(d / "in.simplemap")], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    t0 = time.monotonic()
    with (d / "lc.log").open("wb") as log:
        subprocess.run(["mola-sm-lc-cli", "-i", str(d / "in.simplemap"), "-o",
                        str(d / "out.simplemap"), "-p", str(LC_PIPELINE)],
                       check=True, cwd=d, stdout=log, stderr=subprocess.STDOUT)
    secs = round(time.monotonic() - t0, 1)
    subprocess.run(["sm-cli", "export-keyframes", str(d / "out.simplemap"), "--output",
                    str(d / "after.tum")], check=True, stdout=subprocess.DEVNULL,
                   stderr=subprocess.STDOUT)
    n = LC_COUNT.findall((d / "lc.log").read_text(errors="replace"))
    loops = int(n[-1]) if n else None
    return read_tum_at(d / "after.tum", t), {"loops": loops, "seconds": secs}


def report(res: dict[str, Any]) -> str:
    c = res["consistency"]
    lines = [f"# 回环对照:{res['kf_dir']}", "",
             f"关键帧 {res['keyframes']} 个;回到同一处的对 {c['pairs']} 个(能比的见 n)。", "",
             "| | 墙面差 p50 | p90 | 大于 3 cm 的对 | n | 回环数 | 用时 | 关键帧挪动 中位 / 最大 |",
             "|---|---|---|---|---|---|---|---|"]
    for name, label in (("orig", "不回环"), ("mola", "MOLA 回环"), ("sam", "新回环(厂家那种)")):
        if name not in c:
            continue
        m, info = c[name], res.get(name, {})
        mv = info.get("moved", {})
        lines.append(
            f"| {label} | {m.get('p50_cm', '—')} cm | {m.get('p90_cm', '—')} cm | "
            f"{m.get('over_3cm', '—')} | {m['n']} | {info.get('loops', '—')} | "
            f"{info.get('seconds', '—')} s | "
            f"{mv.get('median_m', '—')} / {mv.get('max_m', '—')} m |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("kf", type=Path, help="关键帧目录(有 index.txt;站点留的那份里是 kf/)")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--kf2sm", help="Super-LIO 的 bin/kf2sm(给了才跑 MOLA 那份)")
    a = ap.parse_args(argv)
    kf = a.kf / "kf" if (a.kf / "kf" / "index.txt").is_file() else a.kf
    if not (kf / "index.txt").is_file():
        ap.error(f"{a.kf} 里没有 index.txt")
    a.out.mkdir(parents=True, exist_ok=True)
    t, T0, names = read_index(kf)
    sets = {"orig": T0}
    res: dict[str, Any] = {"kf_dir": str(kf), "keyframes": len(t)}
    if a.kf2sm and shutil.which("mola-sm-lc-cli"):
        T, info = run_mola(kf, a.out, a.kf2sm, t)
        sets["mola"], res["mola"] = T, {**info, "moved": _moved(T0, T)}
        print(f"MOLA 回环:{info}", flush=True)
    elif a.kf2sm:
        print("没有 mola-sm-lc-cli(先 source /opt/ros/humble/setup.bash):只比新回环",
              file=sys.stderr)
    _, T, info = loop_close_sam(kf)
    write_tum(a.out / "sam.tum", t, T)
    sets["sam"], res["sam"] = T, {**info, "moved": _moved(T0, T)}
    print(f"新回环:{info}", flush=True)
    res["consistency"] = consistency(kf, t, names, sets)
    (a.out / "result.json").write_text(json.dumps(res, ensure_ascii=False, indent=2) + "\n")
    (a.out / "report.md").write_text(report(res))
    print(report(res))
    return 0


if __name__ == "__main__":
    os.environ.setdefault("OMP_NUM_THREADS", str(os.cpu_count() or 4))
    sys.exit(main())
