"""Super-LIO 建图前端(工单 21):Super-LIO 的轨迹 + 录包里的原始点云 → 我们原来的出图流程。

为什么:2026-11-02 商场两版图 MOLA 都跟丢(机器人上首尾差 56 m / 12.5 m);同一商场
Super-LIO 在机器人上实时跑首尾 5 cm,台式机离线跑同一个包 0.14 m
(``docs/Super-LIO现场验证-2026-11-02.md``)。MOLA 留着:建图前端可以切回去(``--front mola``),
定位器照旧用 MOLA。

Super-LIO 只用前雷达 + 它自带的 IMU(跟竞品一样)。它是 GPL-3.0,**只作为单独进程跑**
(``super_lio_node``),我们只读它发的位姿(``nav_msgs/Odometry``,IMU 在世界系里;世界系 z 朝上)。

出图要的中间文件(跟 MOLA 出的同名,:func:`nexwar_localizer.build.package` 原样收):

- ``traj.tum``:每帧扫描时刻的**雷达**位姿(IMU 位姿 × 雷达 → IMU 外参,按扫描中间时刻插值);
- ``map.simplemap``:隔 :data:`KF_DIST_M` / :data:`KF_TURN_DEG` 取的关键帧,原始整帧点云
  (``kf2sm`` 写);
- ``raw_prior.mm``:``sm2mm`` 按定位先验的流水线从 simplemap 出(同回环那条路)。

位姿从哪来:边走边建时 Super-LIO 在机器人上实时跑,它的位姿跟原始数据录进**同一个包**
(:data:`LIVE_TOPIC`);从录包重建时在本机隔离域里回放给 Super-LIO 重算(:func:`run_offline`)。
"""

from __future__ import annotations

import json
import math
import os
import shlex
import shutil
import signal
import subprocess
import time
from collections.abc import Callable, Iterable, Iterator, Sequence
from pathlib import Path
from typing import Any

#: 装在哪(``deploy/nexwar_superlio_build`` 编出来的;``current`` 指当前版本)。
ROOT = Path(os.environ.get("NEXWAR_SUPERLIO_ROOT", "/opt/nexwar/superlio/current"))
#: 参数文件:机器人上的(现场调参)优先,没有用随版本带的。
SITE_CONFIG = Path("/etc/nexwar/superlio.yaml")
DEFAULT_CONFIG = Path(__file__).resolve().parents[4] / "deploy/superlio/nexwar.yaml"
LIDAR_TOPIC = "/front_lidar"
IMU_TOPIC = "/front_lidar/imu"
#: 边走边建时 Super-LIO 的位姿改名到建图的命名空间下(跟定位器、竞品的 ``/lio/*`` 都不串),录进包里。
NS = "/nexwar_mapping"
LIVE_TOPIC = f"{NS}/lio/odom"
#: Super-LIO 发的话题(都是绝对名,``__ns`` 管不到,一个个改名)。
PUBLISHED = ("/lio/odom", "/lio/imu/odom", "/lio/robo/odom", "/lio/path", "/lio/cloud_world",
             "/mavros/vision_pose/pose", "/lio/robo/cloud_world", "/lio/body/cloud_pose",
             "/lio/world/cloud_pose", "/lio/processing_time", "/lio/global_map")
#: 关键帧间隔:走这么远或转这么多取一帧(MOLA 建图的关键帧也是这个量级)。
KF_DIST_M = 0.3
KF_TURN_DEG = 10.0
#: 边走边存的关键帧按这么大的体素降采样(W75:出图的点云也是 5 cm,省一半多的盘、上传和回环的内存)。
KF_VOXEL_M = 0.05
#: 边走边存收尾时写的汇总(``livemap.write_live``):有它才算这一趟的关键帧齐了。
LIVE_FILE = "live.json"
#: W75 边走边存时另记的 IMU 比力(``t ax ay az`` 一行一条,最多每秒 :data:`IMU_LOG_HZ` 条):站点上从
#: 关键帧打包时按它摆平(:func:`level`;11-18 前这条路不摆平,客户自己建 Top Glove 那种场地还是歪的)。
IMU_FILE = "imu.txt"
#: 后雷达(11-18,Top Glove):每存一个前雷达关键帧,顺手存一帧时刻最近的后雷达(雷达系点云,文件名
#: ``r00000.bin``,跟前雷达的放在同一个 ``kf/`` 里、另记索引 ``kf/rear.txt``:旧站点收件只认
#: ``kf/<文件名>``,这样照收、只是不用)。外参抄一份 :data:`REAR_LIDARS` 在关键帧目录顶上
#: (标定过的才抄)。
REAR_INDEX = "rear.txt"
REAR_LIDARS = "lidars.json"
#: 后雷达跟前雷达关键帧最多差这么多秒才配(两台 10 帧/秒,半帧多一点)。
REAR_MATCH_S = 0.06
#: 后雷达关键帧的降采样(米)。后雷达只拿去打栅格射线清空地(不进点云、路沿、底图),10 cm 够用;
#: 跟前雷达一样 5 cm 时 Top Glove 一趟往站点传 414 MB,10 cm 约 270 MB(用户 11-21 定做)。
REAR_KF_VOXEL_M = 0.10
IMU_LOG_HZ = 100.0
#: 关键帧点云按离雷达的距离裁(太近是机身、太远是噪点)。
RANGE_MIN_M, RANGE_MAX_M = 0.6, 80.0
#: 位姿取在扫描的哪个时刻(Airy 一帧 0.1 s,报文头是起点):取中间。
SCAN_MID_S = 0.05
#: 两个位姿之间断了这么久,中间的扫描不用(插值不可信)。
MAX_GAP_S = 0.5
#: 从录包重建时回放的倍速:慢一点保证 Super-LIO 每帧都算得完(它是实时算法,来不及就发散)。
OFFLINE_RATE = 0.5
#: 一帧扫描最少多少点才当关键帧。
MIN_KF_POINTS = 500
#: 离线回放默认的隔离域(调用方环境里没设 ROS_DOMAIN_ID 时用)。
OFFLINE_ENV = {"ROS_DOMAIN_ID": "93", "RMW_IMPLEMENTATION": "rmw_fastrtps_cpp",
               "ROS_LOCALHOST_ONLY": "1"}
#: 位姿要盖住几成的扫描、两头最多差几秒(Super-LIO 中途退了、录位姿断了,不出残缺的图;外审 W67-1)。
MIN_POSE_COVERAGE = 0.8
MAX_EDGE_GAP_S = 5.0
# 按重力摆平(Top Glove 11-17:Super-LIO 俯仰 / 横滚走了 10 分钟漂了约 4°,轨迹东头「高 1.2 m」是假的)
LEVEL_WINDOW_S = 20.0       # 每这么长拿 IMU 比力的平均当「上」(走路的加速度平均掉)
LEVEL_MIN_DEG = 1.0         # 偏得比这小不改(IMU 零偏、噪声也有这么多)
LEVEL_MAX_DEG = 10.0        # 偏得比这大是 IMU / 轴向有问题,不改,写明
LEVEL_MIN_SAMPLES = 200     # 一段里 IMU 少于这么多不算那段
# 加速度计水平零偏(笔记本核 v11:约 0.84° 没扣,去程回程朝向相反被纠成相反方向,同一处高低差 0.3–0.5 m)
LEVEL_BIAS_MIN_WINDOWS = 6  # 估零偏至少要这么多段
LEVEL_BIAS_MAX_DEG = 3.0    # 估出来比这大不信(不扣)
LEVEL_BIAS_KEEP_DEG = 0.8   # 估零偏时离拟合超过这么多的段当在漂,不参与(v11 不漂的段 0.04–0.8°)
LEVEL_BIAS_FINE_DEG = 0.3   # 精解时离拟合超过 max(这么多, 3 倍中位)的段也不要(漂刚开始的那几段)
LEVEL_BIAS_TRIES = 3000     # RANSAC 最多试这么多组(段少时全试)
LEVEL_CONST_DEG = 1.3       # 扣零偏后离常量重力不到这么多的段都用常量纠(固定,不按段间噪声往下压)。
                            # 台式机 11-18 回归台:没漂的段 Top Glove 到 0.96°、商场 Super-LIO
                            # 每回放一遍 0.71–0.83°;真漂的 Top Glove 2.04° 以上。原来「3 倍中位、
                            # 不低于 0.5°/0.8°、最多 1°」紧贴没漂的那边。合成慢漂 1.0–1.3° 一样,
                            # 1.5° 就纠不动
#: 建完把关:相邻两个位姿水平挪的比「最快速度 × 间隔 + 余量」还多,就是跟丢了,不出图(跟定位器
#: 判跳一个做法)。不只看距离:录位姿会丢帧(台式机实测 1.8 s 断档里走了 1.58 m,是正常走);
#: 不只看速度:两个位姿可能只隔 5 ms(差 1.5 cm 算出来 3 m/s)。
MAX_SPEED_MPS = 3.0
JUMP_MARGIN_M = 0.3

Pose = tuple[float, tuple[float, float, float], tuple[float, float, float, float]]


class SuperLioError(RuntimeError):
    """Super-LIO 这条路走不通(说人话的原因)。"""


# ---------------------------------------------------------------- 装没装、参数
def installed(root: Path | None = None) -> bool:
    root = ROOT if root is None else root
    return (root / ".ok").is_file() and (root / "install/setup.bash").is_file() \
        and (root / "bin/kf2sm").is_file()


def config_path() -> Path:
    return SITE_CONFIG if SITE_CONFIG.is_file() else DEFAULT_CONFIG


def extrinsic(cfg: Path) -> tuple[list[list[float]], list[float]]:
    """参数文件里的 ``lio.extrinsic.lidar_imu``:``(R, t)``,雷达系 → IMU 系(t 3 个 + R 9 个)。

    R 的 9 个数**按列**读:Super-LIO 是 ``M3 __R(r_data.data())``,Eigen 默认列优先。按行读差一个
    转置,算出来的雷达位姿跟 Super-LIO 自己用的不一致,图是镜像的(11-02 商场 v2 包实跑发现)。"""
    txt = Path(cfg).read_text(encoding="utf-8")
    key = "lio.extrinsic.lidar_imu:"
    i = txt.find(key)
    if i < 0:
        raise SuperLioError(f"{cfg} 里没有 {key}")
    j, k = txt.index("[", i), txt.index("]", i)
    try:
        v = [float(s) for s in txt[j + 1:k].replace("\n", " ").split(",") if s.strip()]
    except ValueError as exc:
        raise SuperLioError(f"{cfg} 的 {key} 不是 12 个数") from exc
    if len(v) != 12:
        raise SuperLioError(f"{cfg} 的 {key} 要 12 个数,给了 {len(v)} 个")
    if not all(math.isfinite(x) for x in v):
        raise SuperLioError(f"{cfg} 的 {key} 有非有限值")
    R = [[v[3 + r + 3 * c] for c in range(3)] for r in range(3)]
    RtR = _mul(_T(R), R)
    if any(abs(RtR[i][j] - (i == j)) > 0.02 for i in range(3) for j in range(3)):
        raise SuperLioError(f"{cfg} 的 {key} 旋转部分不是旋转矩阵(不正交,带缩放或剪切)")
    det = (R[0][0] * (R[1][1] * R[2][2] - R[1][2] * R[2][1])
           - R[0][1] * (R[1][0] * R[2][2] - R[1][2] * R[2][0])
           + R[0][2] * (R[1][0] * R[2][1] - R[1][1] * R[2][0]))
    if abs(det - 1.0) > 0.05:
        raise SuperLioError(f"{cfg} 的 {key} 旋转部分不是旋转矩阵(行列式 {det:.3f})")
    return R, v[0:3]


def node_args(cfg: Path, *, ns_remap: bool) -> list[str]:
    """``super_lio_node`` 的 ROS 参数:参数文件、输入话题;``ns_remap`` 把发的话题全改到
    :data:`NS` 下。"""
    args = ["--ros-args", "--params-file", str(cfg),
            "-p", f"lio.ros.lidar_topic:={LIDAR_TOPIC}", "-p", f"lio.ros.imu_topic:={IMU_TOPIC}",
            "-p", "lio.map.save_map:=false"]
    if ns_remap:
        for t in PUBLISHED:
            args += ["-r", f"{t}:={NS}{t}"]
    return args


# ---------------------------------------------------------------- 小数学(四元数 x, y, z, w)
def quat_to_mat(q: Sequence[float]) -> list[list[float]]:
    x, y, z, w = q
    return [[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]]


def mat_to_quat(R: Sequence[Sequence[float]]) -> tuple[float, float, float, float]:
    tr = R[0][0] + R[1][1] + R[2][2]
    if tr > 0:
        s = math.sqrt(tr + 1.0) * 2
        q = ((R[2][1] - R[1][2]) / s, (R[0][2] - R[2][0]) / s, (R[1][0] - R[0][1]) / s, 0.25 * s)
    elif R[0][0] > R[1][1] and R[0][0] > R[2][2]:
        s = math.sqrt(1.0 + R[0][0] - R[1][1] - R[2][2]) * 2
        q = (0.25 * s, (R[0][1] + R[1][0]) / s, (R[0][2] + R[2][0]) / s, (R[2][1] - R[1][2]) / s)
    elif R[1][1] > R[2][2]:
        s = math.sqrt(1.0 + R[1][1] - R[0][0] - R[2][2]) * 2
        q = ((R[0][1] + R[1][0]) / s, 0.25 * s, (R[1][2] + R[2][1]) / s, (R[0][2] - R[2][0]) / s)
    else:
        s = math.sqrt(1.0 + R[2][2] - R[0][0] - R[1][1]) * 2
        q = ((R[0][2] + R[2][0]) / s, (R[1][2] + R[2][1]) / s, 0.25 * s, (R[1][0] - R[0][1]) / s)
    n = math.sqrt(sum(c * c for c in q))
    return (q[0] / n, q[1] / n, q[2] / n, q[3] / n)


def _mul(A: Sequence[Sequence[float]], B: Sequence[Sequence[float]]) -> list[list[float]]:
    return [[sum(A[i][k] * B[k][j] for k in range(3)) for j in range(3)] for i in range(3)]


def _apply(A: Sequence[Sequence[float]], v: Sequence[float]) -> list[float]:
    return [sum(A[i][k] * v[k] for k in range(3)) for i in range(3)]


def _T(A: Sequence[Sequence[float]]) -> list[list[float]]:
    return [[A[j][i] for j in range(3)] for i in range(3)]


def slerp(q0: Sequence[float], q1: Sequence[float], s: float) -> tuple[float, ...]:
    d = sum(a * b for a, b in zip(q0, q1, strict=True))
    if d < 0:
        q1, d = tuple(-c for c in q1), -d
    if d > 0.9995:
        q = [a + s * (b - a) for a, b in zip(q0, q1, strict=True)]
    else:
        th = math.acos(d)
        q = [(math.sin((1 - s) * th) * a + math.sin(s * th) * b) / math.sin(th)
             for a, b in zip(q0, q1, strict=True)]
    n = math.sqrt(sum(c * c for c in q))
    return tuple(c / n for c in q)


def rot_angle(R: Sequence[Sequence[float]]) -> float:
    return math.acos(max(-1.0, min(1.0, (R[0][0] + R[1][1] + R[2][2] - 1) / 2)))


def _log(R: Sequence[Sequence[float]]) -> list[float]:
    th = rot_angle(R)
    if th < 1e-9:
        return [0.0, 0.0, 0.0]
    k = th / (2 * math.sin(th))
    return [(R[2][1] - R[1][2]) * k, (R[0][2] - R[2][0]) * k, (R[1][0] - R[0][1]) * k]


# ---------------------------------------------------------------- 位姿
def clean(poses: Iterable[Pose]) -> list[Pose]:
    """按时间排好;丢掉非有限值、离谱的(Super-LIO 退出时会吐几帧乱值)、时间倒退或重复的。"""
    out: list[Pose] = []
    for t, p, q in sorted(poses, key=lambda r: r[0]):
        v = (t, *p, *q)
        if not all(math.isfinite(c) for c in v) or max(abs(c) for c in p) > 1e4:
            continue
        n = math.sqrt(sum(c * c for c in q))
        if n < 1e-6 or (out and t <= out[-1][0]):
            continue
        out.append((t, p, (q[0] / n, q[1] / n, q[2] / n, q[3] / n)))
    return out


def pose_at(poses: Sequence[Pose], t: float, times: Sequence[float] | None = None
            ) -> tuple[tuple[float, ...], tuple[float, ...]] | None:
    """``t`` 时刻的位姿(前后两个之间插值);在范围外、两头断了 :data:`MAX_GAP_S` 以上是 None。"""
    import bisect
    ts = times if times is not None else [r[0] for r in poses]
    if not ts or t < ts[0] or t > ts[-1]:
        return None
    i = min(max(bisect.bisect_left(ts, t), 1), len(ts) - 1)
    (t0, p0, q0), (t1, p1, q1) = poses[i - 1], poses[i]
    if t1 - t0 > MAX_GAP_S:
        return None
    s = 0.0 if t1 == t0 else (t - t0) / (t1 - t0)
    return (tuple(a + s * (b - a) for a, b in zip(p0, p1, strict=True)), slerp(q0, q1, s))


def level(poses: Sequence[Pose], imu: Sequence[tuple[float, float, float, float]]
          ) -> tuple[list[Pose], dict[str, Any]]:
    """按 IMU 测的重力把 Super-LIO 的轨迹逐段摆平(Top Glove 11-17)。

    ``poses``:IMU 在世界系的位姿(Super-LIO 的 odom);``imu``:``(t, ax, ay, az)``
    IMU 系的比力(静止时朝上,单位不管,只用方向)。每 :data:`LEVEL_WINDOW_S` 一段:比力按那一刻
    的姿态转到世界系取平均 = 那段的「上」;转到 +Z 的最小旋转(不动航向)= 那段的纠正,段中心
    之间线性插,两头取最近的一段。姿态左乘
    纠正,位移逐步按纠正转(高低跟着回平)。偏得不到 :data:`LEVEL_MIN_DEG`、超过
    :data:`LEVEL_MAX_DEG`、IMU 不够:原样回,``info["why"]`` 写明。回(位姿, 摘要)。"""
    import bisect
    poses = list(poses)
    info: dict[str, Any] = {"applied": False, "max_deg": 0.0, "window_s": LEVEL_WINDOW_S}
    if len(poses) < 2:
        info["why"] = "位姿太少"
        return poses, info
    import numpy as np
    times = [r[0] for r in poses]
    t0 = times[0]
    n_win = max(1, int(math.ceil((times[-1] - t0) / LEVEL_WINDOW_S)))
    su = np.zeros((n_win, 3))            # 每段:比力(单位向量)转到世界系的和
    sR = np.zeros((n_win, 3, 3))         # 每段:姿态的和(零偏转到世界系用)
    cnt = np.zeros(n_win, int)
    raw = np.zeros(3)                    # IMU 系里比力的和(哪根轴朝上)
    for t, ax, ay, az in imu:
        at = pose_at(poses, t, times)
        n = math.sqrt(ax * ax + ay * ay + az * az)
        if at is None or n < 1e-6:
            continue
        k = min(int((t - t0) / LEVEL_WINDOW_S), n_win - 1)
        R = np.array(quat_to_mat(at[1]))
        f = np.array((ax / n, ay / n, az / n))
        su[k] += R @ f
        sR[k] += R
        cnt[k] += 1
        raw += f
    ok = np.nonzero(cnt >= LEVEL_MIN_SAMPLES)[0]
    U = su[ok] / cnt[ok, None]
    M = sR[ok] / cnt[ok, None, None]
    up_axis = int(np.argmax(np.abs(raw)))
    flat = [i for i in range(3) if i != up_axis]
    C, b, why_b, const = _window_ups(U, M[:, :, flat])
    info["bias_deg"] = round(math.degrees(float(np.linalg.norm(b))), 2)
    info["bias_used"] = not why_b
    info["const_windows"] = int(const.sum())
    if why_b:
        info["bias_why"] = why_b
    centers, fixes, degs = [], [], []
    for k, (x, y, z) in zip(ok, C, strict=True):
        n = math.sqrt(x * x + y * y + z * z)
        ux, uy, uz = x / n, y / n, z / n
        ang = math.acos(max(-1.0, min(1.0, uz)))
        h = math.hypot(ux, uy)
        if h < 1e-9:
            q = (0.0, 0.0, 0.0, 1.0)
        else:                            # 绕 u × z(水平轴)转 ang
            ex, ey = uy / h, -ux / h
            q = (ex * math.sin(ang / 2), ey * math.sin(ang / 2), 0.0, math.cos(ang / 2))
        centers.append(t0 + (int(k) + 0.5) * LEVEL_WINDOW_S)
        fixes.append(q)
        degs.append(math.degrees(ang))
    if not fixes:
        info["why"] = (f"IMU 不够(每 {LEVEL_WINDOW_S:g} s 要 {LEVEL_MIN_SAMPLES} 个,"
                       "录包里有 IMU 吗?)")
        return poses, info
    info["max_deg"] = round(max(degs), 2)
    info["first_deg"], info["last_deg"] = round(degs[0], 2), round(degs[-1], 2)
    if max(degs) > LEVEL_MAX_DEG:
        info["why"] = f"偏了 {max(degs):.1f}° 超过 {LEVEL_MAX_DEG:g}°(IMU 或轴向不对?),不摆平"
        return poses, info
    if max(degs) < LEVEL_MIN_DEG:
        info["why"] = f"偏得不到 {LEVEL_MIN_DEG:g}°,不改"
        return poses, info

    def fix_at(t: float) -> tuple[float, ...]:
        i = bisect.bisect_left(centers, t)
        if i <= 0:
            return fixes[0]
        if i >= len(centers):
            return fixes[-1]
        s = (t - centers[i - 1]) / (centers[i] - centers[i - 1])
        return slerp(fixes[i - 1], fixes[i], s)

    out: list[Pose] = []
    prev_p, prev_new = None, None
    for t, p, q in poses:
        C = quat_to_mat(fix_at(t))
        new_q = mat_to_quat(_mul(C, quat_to_mat(q)))
        if prev_p is None:
            new_p = tuple(p)
        else:
            d = _apply(C, [a - b for a, b in zip(p, prev_p, strict=True)])
            new_p = tuple(a + b for a, b in zip(prev_new, d, strict=True))
        out.append((t, new_p, new_q))
        prev_p, prev_new = p, new_p
    info["applied"] = True
    info["why"] = (f"按 IMU 重力摆平:开头偏 {degs[0]:.1f}°、最多 {max(degs):.1f}°、"
                   f"最后 {degs[-1]:.1f}°;加速度计零偏 {info['bias_deg']:.2f}°"
                   + ("已扣" if info["bias_used"] else f"没扣({info.get('bias_why', '段不够')})"))
    return out, info


def _window_ups(U: Any, M: Any) -> tuple[Any, Any, str, Any]:
    """每段的「上」``U``(k×3)、平均姿态里水平两根轴 ``M``(k×3×2)→(纠正用的「上」k×3、零偏、
    没扣零偏的原因、哪些段用常量)。扣掉零偏(:func:`_imu_bias`)后,离常量重力不到
    :data:`LEVEL_CONST_DEG` 的段都用那个常量(不把段间 0.2–0.5° 的噪声
    纠进去),只有漂了的段逐段纠;不平滑(笔记本核 v13:前后各一段平均让
    纠正滞后、摊开,去程回程差 0.12–0.27 m)。
    零偏估不了:不扣、逐段纠。"""
    import numpy as np
    U = np.asarray(U, float)
    k = len(U)
    const = np.zeros(k, bool)
    if k < LEVEL_BIAS_MIN_WINDOWS:
        return U.copy(), np.zeros(2), f"段不够(要 {LEVEL_BIAS_MIN_WINDOWS} 段)", const
    x, why = _bias_fit(U, M)
    if why:
        return U.copy(), np.zeros(2), why, const
    b, g = x[3:], x[:3]
    C = U - np.einsum("kij,j->ki", M, b)
    cos = (C @ g) / (np.linalg.norm(C, axis=1) * np.linalg.norm(g))
    dev = np.degrees(np.arccos(np.clip(cos, -1.0, 1.0)))
    # 门槛固定(:data:`LEVEL_CONST_DEG`)。挨着漂的段不另算(笔记本核 v14:Top Glove 第 16 段
    # 偏 0.85–0.96°、看高度不是漂,逐段纠了西头反而压低 0.27 m)
    const = dev < LEVEL_CONST_DEG
    C[const] = g
    return C, b, "", const


def _imu_bias(U: Any, M: Any) -> tuple[Any, str]:
    """:func:`_bias_fit` 的零偏部分:回(零偏 2 个分量, 不扣的原因)。"""
    import numpy as np
    x, why = _bias_fit(U, M)
    return (np.zeros(2) if x is None else x[3:]), why


def _bias_fit(U: Any, M: Any) -> tuple[Any, str]:
    """各段的「上」``U``(k×3)、平均姿态里水平两根轴 ``M``(k×3×2)→ 加速度计水平零偏
    (2 个分量,单位 g):解「U = 常量 g + M·b」。先找一致的大多数(RANSAC / MSAC:每次取 3 段解,
    离拟合 :data:`LEVEL_BIAS_KEEP_DEG` 以外的封顶算,误差总和最小的那组),再用那些段收紧了精解
    —— 笔记本核 v12:先全量最小二乘,漂的几段朝向别处没有,零偏把漂移「解释」掉了。
    朝向不够多、一致的段不够、估出来太大:回 (零, 原因)。"""
    import itertools

    import numpy as np
    k = len(U)
    A = np.zeros((3 * k, 5))
    A[:, :3] = np.tile(np.eye(3), (k, 1))
    A[:, 3:] = M.reshape(3 * k, 2)
    y = U.reshape(3 * k)
    thr = math.radians(LEVEL_BIAS_KEEP_DEG)

    def fit(keep: Any) -> Any:
        rows = np.repeat(keep, 3)
        sv = np.linalg.svd(A[rows], compute_uv=False)
        if sv[-1] < 0.05 * sv[0]:
            return None
        return np.linalg.lstsq(A[rows], y[rows], rcond=None)[0]

    def residual(x: Any) -> Any:
        return np.linalg.norm((A @ x - y).reshape(k, 3), axis=1)

    combos = list(itertools.combinations(range(k), 3))
    if len(combos) > LEVEL_BIAS_TRIES:
        pick = np.random.default_rng(0).choice(len(combos), LEVEL_BIAS_TRIES, replace=False)
        combos = [combos[i] for i in pick]
    best, best_cost = None, math.inf
    for c in combos:
        keep = np.zeros(k, bool)
        keep[list(c)] = True
        x = fit(keep)
        if x is None:
            continue
        res = residual(x)
        cost = float((np.minimum(res, thr) ** 2).sum())     # MSAC:离得远的封顶,一致的越贴越好
        if cost < best_cost:
            best, best_cost = res <= thr, cost
    if best is None:
        return None, "朝向不够多,零偏跟重力分不开,不扣"
    if best.sum() < LEVEL_BIAS_MIN_WINDOWS:
        return None, f"一致的段只有 {int(best.sum())} 段,不扣"
    for _ in range(3):                                   # 用一致的那些段精解,再按新解收紧了认一遍
        x = fit(best)
        if x is None:
            return None, "朝向不够多,零偏跟重力分不开,不扣"
        res = residual(x)
        fine = min(thr, max(math.radians(LEVEL_BIAS_FINE_DEG), 3 * float(np.median(res[best]))))
        new = res <= fine
        if new.sum() < LEVEL_BIAS_MIN_WINDOWS or (new == best).all():
            break
        best = new
    b = x[3:]
    if math.degrees(float(np.linalg.norm(b))) > LEVEL_BIAS_MAX_DEG:
        return x, f"零偏估出来 {math.degrees(float(np.linalg.norm(b))):.1f}° 太大,不扣"
    return x, ""


def bag_imu(bag: Path, topic: str = IMU_TOPIC) -> list[tuple[float, float, float, float]]:
    """录包里 ``topic`` 的 ``sensor_msgs/Imu`` → ``(报文头时刻, ax, ay, az)``。没有这个话题回空。"""
    import rosbag2_py
    from rclpy.serialization import deserialize_message
    from sensor_msgs.msg import Imu

    storage = "mcap" if any(Path(bag).glob("*.mcap")) else "sqlite3"
    r = rosbag2_py.SequentialReader()
    r.open(rosbag2_py.StorageOptions(uri=str(bag), storage_id=storage),
           rosbag2_py.ConverterOptions("cdr", "cdr"))
    if topic not in {x.name for x in r.get_all_topics_and_types()}:
        return []
    r.set_filter(rosbag2_py.StorageFilter(topics=[topic]))
    out = []
    while r.has_next():
        _, raw, _ = r.read_next()
        m = deserialize_message(raw, Imu)
        a = m.linear_acceleration
        out.append((m.header.stamp.sec + m.header.stamp.nanosec * 1e-9, a.x, a.y, a.z))
    return out


def lidar_pose(p_imu: Sequence[float], q_imu: Sequence[float], R_il: Sequence[Sequence[float]],
               t_il: Sequence[float]) -> tuple[list[float], list[list[float]]]:
    """IMU 在世界系的位姿 → 雷达在世界系的位姿:``T_wl = T_wi · T_il``。"""
    R_wi = quat_to_mat(q_imu)
    R_wl = _mul(R_wi, R_il)
    p_wl = [a + b for a, b in zip(_apply(R_wi, t_il), p_imu, strict=True)]
    return p_wl, R_wl


# ---------------------------------------------------------------- 读录包
def read_odom(bag: Path, topic: str) -> list[Pose]:
    """录包里 ``topic`` 的 ``nav_msgs/Odometry`` → 位姿(报文头时刻)。要 ROS 的系统 Python。"""
    import rosbag2_py
    from nav_msgs.msg import Odometry
    from rclpy.serialization import deserialize_message

    storage = "mcap" if any(Path(bag).glob("*.mcap")) else "sqlite3"
    r = rosbag2_py.SequentialReader()
    r.open(rosbag2_py.StorageOptions(uri=str(bag), storage_id=storage),
           rosbag2_py.ConverterOptions("cdr", "cdr"))
    have = {x.name: x.type for x in r.get_all_topics_and_types()}
    if have.get(topic) != "nav_msgs/msg/Odometry":
        raise SuperLioError(f"录包里没有 Super-LIO 的位姿 {topic}(nav_msgs/Odometry)")
    r.set_filter(rosbag2_py.StorageFilter(topics=[topic]))
    out: list[Pose] = []
    while r.has_next():
        _, raw, _ = r.read_next()
        m = deserialize_message(raw, Odometry)
        p, o = m.pose.pose.position, m.pose.pose.orientation
        out.append((m.header.stamp.sec + m.header.stamp.nanosec * 1e-9, (p.x, p.y, p.z),
                    (o.x, o.y, o.z, o.w)))
    return out


def bag_clouds(bag: Path, topic: str = LIDAR_TOPIC) -> Iterator[tuple[float, Any]]:
    """录包里的点云,逐帧 ``(报文头时刻, 原始消息)``(点在 :func:`make_keyframes` 里按需解)。"""
    import rosbag2_py
    from rclpy.serialization import deserialize_message
    from sensor_msgs.msg import PointCloud2

    storage = "mcap" if any(Path(bag).glob("*.mcap")) else "sqlite3"
    r = rosbag2_py.SequentialReader()
    r.open(rosbag2_py.StorageOptions(uri=str(bag), storage_id=storage),
           rosbag2_py.ConverterOptions("cdr", "cdr"))
    r.set_filter(rosbag2_py.StorageFilter(topics=[topic]))
    while r.has_next():
        _, raw, _ = r.read_next()
        m = deserialize_message(raw, PointCloud2)
        yield m.header.stamp.sec + m.header.stamp.nanosec * 1e-9, m


# ---------------------------------------------------------------- 轨迹、关键帧
def make_keyframes(poses: Sequence[Pose], clouds: Iterable[tuple[float, Any]], work: Path,
                   R_il: Sequence[Sequence[float]], t_il: Sequence[float],
                   xyz_of: Callable[[Any], Any], *, voxel: float | None = None) -> dict[str, int]:
    """写 ``work/traj.tum``(每帧扫描的雷达位姿)和 ``work/kf/``
    (关键帧:``index.txt`` + 点云 float32)。``voxel``:关键帧点云按这么大的体素降采样(W75)。
    回 ``{"scans", "traj", "keyframes", "first_scan", "last_scan"}``。"""
    times = [r[0] for r in poses]
    k = Keyframer(work, R_il, t_il, xyz_of, voxel=voxel)
    for t, msg in clouds:
        k.scan(t, msg, pose_at(poses, t + SCAN_MID_S, times))
    return k.close()


class Keyframer:
    """取关键帧(:func:`make_keyframes` 和边走边存 :class:`LiveKeyframes` 共用一套规则):一帧一帧喂
    扫描和它中间时刻的 IMU 位姿。每存一个关键帧就落盘(先写点开头的临时名再改名,上传器不收半个文件),
    索引、轨迹逐行追加 —— 进程半路没了,存下的照样能用。"""

    def __init__(self, work: Path, R_il: Sequence[Sequence[float]], t_il: Sequence[float],
                 xyz_of: Callable[[Any], Any], *, voxel: float | None = None) -> None:
        self.work, self.R_il, self.t_il, self.xyz_of, self.voxel = work, R_il, t_il, xyz_of, voxel
        self.kf = work / "kf"
        shutil.rmtree(self.kf, ignore_errors=True)
        self.kf.mkdir(parents=True)
        self._index = open(self.kf / "index.txt", "w", encoding="utf-8")
        self._traj = open(work / "traj.tum", "w", encoding="utf-8")
        self.scans = self.traj = self.keyframes = 0
        self.first: float | None = None
        self.last: float | None = None
        self._last_kf: tuple[list[float], list[list[float]]] | None = None
        self._prev: tuple[float, list[float], list[list[float]]] | None = None
        self._rear_index: Any = None
        self.rear_keyframes = 0
        import collections
        self._rear: collections.deque[tuple[float, Any]] = collections.deque(maxlen=20)

    def rear(self, t: float, msg: Any) -> None:
        """后雷达来了一帧(原始报文先攒着,配上关键帧才解)。最近 2 秒左右的留着:前雷达那帧要等位姿,
        交给 :meth:`scan` 时比后雷达晚。"""
        self._rear.append((t, msg))

    def _save_rear(self, t: float) -> None:
        import numpy as np

        if not self._rear:
            return
        rt, msg = min(self._rear, key=lambda r: abs(r[0] - t))
        if abs(rt - t) > REAR_MATCH_S:
            return
        xyz = _clip(np.asarray(self.xyz_of(msg), float))
        if len(xyz) < MIN_KF_POINTS:
            return
        if self.voxel:
            from nexwar_localizer.slioloc import voxel_down
            xyz = voxel_down(xyz, max(self.voxel, REAR_KF_VOXEL_M))
        name = f"r{self.rear_keyframes:05d}.bin"
        tmp = self.kf / f".{name}.tmp"
        xyz.astype("<f4").tofile(tmp)
        os.replace(tmp, self.kf / name)
        if self._rear_index is None:
            self._rear_index = open(self.kf / REAR_INDEX, "w", encoding="utf-8")
        self._rear_index.write(f"{rt:.6f} {name}\n")
        self._rear_index.flush()
        self.rear_keyframes += 1

    def scan(self, t: float, msg: Any,
             pose: tuple[Sequence[float], Sequence[float]] | None) -> None:
        import numpy as np

        self.scans += 1
        self.first = t if self.first is None else self.first
        self.last = t
        if pose is None:
            return
        p, R = lidar_pose(pose[0], pose[1], self.R_il, self.t_il)
        q = mat_to_quat(R)
        self._traj.write(f"{t:.6f} " + " ".join(f"{c:.6f}" for c in (*p, *q)) + "\n")
        self._traj.flush()
        self.traj += 1
        v = w = [0.0, 0.0, 0.0]
        prev = self._prev
        if prev is not None and t > prev[0]:
            dt = t - prev[0]
            v = [c / dt for c in _apply(_T(R), [a - b for a, b in zip(p, prev[1], strict=True)])]
            w = [c / dt for c in _log(_mul(_T(prev[2]), R))]
        self._prev = (t, p, R)
        if self._last_kf is not None:
            moved = math.dist(p, self._last_kf[0])
            turned = math.degrees(rot_angle(_mul(_T(self._last_kf[1]), R)))
            if moved < KF_DIST_M and turned < KF_TURN_DEG:
                return
        xyz = _clip(np.asarray(self.xyz_of(msg), float))
        if len(xyz) < MIN_KF_POINTS:
            return
        if self.voxel:
            from nexwar_localizer.slioloc import voxel_down
            xyz = voxel_down(xyz, self.voxel)
        name = f"{self.keyframes:05d}.bin"
        tmp = self.kf / f".{name}.tmp"
        xyz.astype("<f4").tofile(tmp)
        os.replace(tmp, self.kf / name)
        self._index.write(f"{t:.6f} " + " ".join(f"{c:.6f}" for c in (*p, *q, *v, *w))
                          + f" {name}\n")
        self._index.flush()
        self.keyframes += 1
        self._last_kf = (p, R)
        self._save_rear(t)

    def close(self) -> dict[str, Any]:
        self._index.close()
        self._traj.close()
        if self._rear_index is not None:
            self._rear_index.close()
        out = {"scans": self.scans, "traj": self.traj, "keyframes": self.keyframes,
               "first_scan": self.first, "last_scan": self.last}
        if self.rear_keyframes:
            out["rear_keyframes"] = self.rear_keyframes
        return out


def _clip(xyz: Any) -> Any:
    """量程外的点不要(:data:`RANGE_MIN_M`–:data:`RANGE_MAX_M`)。"""
    import numpy as np

    if len(xyz):
        rng = np.linalg.norm(xyz, axis=1)
        xyz = xyz[(rng > RANGE_MIN_M) & (rng < RANGE_MAX_M)]
    return xyz


class LiveKeyframes:
    """边走边存关键帧(W75):点云、位姿各自来(Super-LIO 算完一帧才发位姿,比点云晚)。点云先攒着原始
    报文,等到盖住它中间时刻的位姿再交给 :class:`Keyframer` —— 跟录完再取(:func:`make_keyframes`)
    一样的插值、一样的结果;只有取成关键帧的那几帧才解点云。位姿等了 ``wait_s`` 还没来,这帧按
    没位姿算。位姿照 :func:`clean` 的规矩丢坏的。"""

    def __init__(self, keyframer: Keyframer, *, wait_s: float = 1.0, keep_poses: int = 200,
                 log: Path | None = None, imu_log: Path | None = None) -> None:
        """``log``:收下的位姿(IMU)逐行另记一份 TUM(建完把关 :func:`quality` 用);``imu_log``:
        IMU 比力另记一份(:data:`IMU_FILE`,打包时摆平用)。"""
        import collections
        self.k = keyframer
        self._log = None if log is None else open(log, "w", encoding="utf-8")
        self._imu = None if imu_log is None else open(imu_log, "w", encoding="utf-8")
        self._imu_last = -math.inf
        self.wait_s = wait_s
        self.poses: collections.deque[Pose] = collections.deque(maxlen=keep_poses)
        self.pending: collections.deque[tuple[float, Any]] = collections.deque()
        self._newest = -math.inf

    def on_scan(self, t: float, msg: Any) -> None:
        self.pending.append((t, msg))
        self._newest = max(self._newest, t)
        self._drain()

    def on_rear(self, t: float, msg: Any) -> None:
        """后雷达一帧(:data:`REAR_INDEX`)。"""
        self.k.rear(t, msg)

    def on_imu(self, t: float, ax: float, ay: float, az: float) -> None:
        if self._imu is None or t - self._imu_last < 1.0 / IMU_LOG_HZ - 1e-6:
            return
        v = (float(t), float(ax), float(ay), float(az))
        if not all(map(math.isfinite, v)):
            return
        self._imu_last = v[0]
        self._imu.write(" ".join(repr(c) for c in v) + "\n")

    def on_pose(self, t: float, p: Sequence[float], q: Sequence[float]) -> None:
        got = clean([(t, tuple(p), tuple(q))])
        if not got or (self.poses and got[0][0] <= self.poses[-1][0]):
            return
        self.poses.append(got[0])
        if self._log is not None:
            t0, p0, q0 = got[0]
            self._log.write(" ".join(repr(float(c)) for c in (t0, *p0, *q0)) + "\n")
            self._log.flush()
        self._newest = max(self._newest, t)
        self._drain()

    def _drain(self, final: bool = False) -> None:
        while self.pending:
            t, msg = self.pending[0]
            mid = t + SCAN_MID_S
            if self.poses and self.poses[-1][0] >= mid or final:
                pose = pose_at(list(self.poses), mid) if self.poses else None
            elif self._newest - t > self.wait_s:
                pose = None
            else:
                return
            self.pending.popleft()
            self.k.scan(t, msg, pose)

    def close(self) -> dict[str, Any]:
        self._drain(final=True)
        if self._log is not None:
            self._log.close()
        if self._imu is not None:
            self._imu.close()
        return self.k.close()


def live_from_bag(poses: Sequence[Pose], clouds: Iterable[tuple[float, Any]],
                  imu: Iterable[tuple[float, float, float, float]], kd: Path, *, cfg: Path,
                  xyz_of: Callable[[Any], Any] | None = None,
                  rear: Iterable[tuple[float, Any]] = (),
                  rear_lidars: Path | None = None) -> dict[str, Any]:
    """回归台用(11-18):录包里的点云 + Super-LIO 位姿 + IMU → 跟机器人边走边存(``livemap
    --keyframes``)一样的关键帧目录(位姿没摆平、关键帧按 :data:`KF_VOXEL_M` 降采样、IMU 另记、
    ``live.json`` 收尾),站点那条打包路(:func:`prepare_live`)就能拿录包验。回关键帧汇总。
    ``rear`` + ``rear_lidars``:后雷达的帧和外参,跟机器人上一样存(:data:`REAR_INDEX`)。"""
    if xyz_of is None:
        from nexwar_localizer.build import cloud_xyz as xyz_of
    R_il, t_il = extrinsic(cfg)
    kd.mkdir(parents=True, exist_ok=True)
    (kd / LIVE_FILE).unlink(missing_ok=True)
    live = LiveKeyframes(Keyframer(kd, R_il, t_il, xyz_of, voxel=KF_VOXEL_M),
                         log=kd / "lio.tum", imu_log=kd / IMU_FILE)
    poses = clean(poses)
    imu = sorted(imu)
    pi = ii = 0
    if rear_lidars is not None:
        shutil.copyfile(rear_lidars, kd / REAR_LIDARS)
    rear_it = iter(rear)
    nxt = next(rear_it, None)
    # 按机器人上到的顺序喂:位姿、IMU 到了这一帧的时刻再给点云;后雷达按时刻插在前雷达之间
    for t, msg in clouds:
        while nxt is not None and nxt[0] <= t + REAR_MATCH_S:   # 机器人上后雷达实时到,不缺这几帧
            live.on_rear(*nxt)
            nxt = next(rear_it, None)
        while pi < len(poses) and poses[pi][0] <= t + SCAN_MID_S:
            while ii < len(imu) and imu[ii][0] <= poses[pi][0]:
                live.on_imu(*imu[ii])
                ii += 1
            live.on_pose(*poses[pi])
            pi += 1
        live.on_scan(t, msg)
    while nxt is not None:
        live.on_rear(*nxt)
        nxt = next(rear_it, None)
    for p in poses[pi:]:
        while ii < len(imu) and imu[ii][0] <= p[0]:
            live.on_imu(*imu[ii])
            ii += 1
        live.on_pose(*p)
    n = live.close()
    tmp = kd / f".{LIVE_FILE}.tmp"
    tmp.write_text(json.dumps({**n, "clock_offset_s": None, "odom": [], "clean": True}),
                   encoding="utf-8")
    os.replace(tmp, kd / LIVE_FILE)
    return n


def read_imu(path: Path) -> list[tuple[float, float, float, float]]:
    """:class:`LiveKeyframes` 记的 IMU 比力(:data:`IMU_FILE`)。坏行跳过;没有这个文件回空。"""
    out: list[tuple[float, float, float, float]] = []
    try:
        text = Path(path).read_text(encoding="utf-8")
    except FileNotFoundError:
        return out
    for line in text.splitlines():
        try:
            v = [float(c) for c in line.split()]
        except ValueError:
            continue
        if len(v) == 4 and all(map(math.isfinite, v)):
            out.append((v[0], v[1], v[2], v[3]))
    return out


def _relevel_keyframes(kd: Path, work: Path, poses: Sequence[Pose], cfg: Path) -> Path:
    """摆平后的 IMU 位姿 → 重写关键帧索引、``traj.tum`` 的雷达位姿(跟 :class:`Keyframer` 一样:扫描
    中间时刻插值、乘外参),写到 ``work``;点云不动(雷达系),链接原文件。回新的关键帧目录。"""
    R_il, t_il = extrinsic(cfg)
    times = [r[0] for r in poses]

    def pose_line(t: float) -> str | None:
        at = pose_at(poses, t + SCAN_MID_S, times)
        if at is None:
            return None
        p, R = lidar_pose(at[0], at[1], R_il, t_il)
        return " ".join(f"{c:.6f}" for c in (*p, *mat_to_quat(R)))

    out = work / "kf"
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    rows = []
    for ln in (kd / "kf" / "index.txt").read_text(encoding="utf-8").splitlines():
        c = ln.split()
        new = pose_line(float(c[0])) if len(c) == 15 else None
        if new is None:
            raise SuperLioError(f"关键帧索引对不上摆平后的位姿:{ln[:80]}")
        rows.append(f"{c[0]} {new} {' '.join(c[8:14])} {c[14]}")
        (out / c[14]).symlink_to((kd / "kf" / c[14]).resolve())
    (out / "index.txt").write_text("".join(r + "\n" for r in rows), encoding="utf-8")
    traj = []
    for ln in (kd / "traj.tum").read_text(encoding="utf-8").splitlines():
        c = ln.split()
        new = pose_line(float(c[0])) if len(c) == 8 else None
        if new is not None:
            traj.append(f"{c[0]} {new}\n")
    (work / "traj.tum").write_text("".join(traj), encoding="utf-8")
    return out


def read_tum_poses(path: Path) -> list[Pose]:
    """:class:`LiveKeyframes` 记的位姿(TUM:时刻 x y z qx qy qz qw)。坏行跳过。"""
    out: list[Pose] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        try:
            v = [float(c) for c in line.split()]
        except ValueError:
            continue
        if len(v) == 8:
            out.append((v[0], (v[1], v[2], v[3]), (v[4], v[5], v[6], v[7])))
    return out


#: 「同一处」:水平这么近、时间隔这么久以上两次经过(:func:`_same_place_dz`)。
SAME_PLACE_R_M = 0.5
SAME_PLACE_DT_S = 30.0


def _same_place_dz(keep: Sequence[Pose]) -> float:
    """同一处两次经过的高度差(每个点取跟它差得最多的那次)的 95 分位;没经过两次是 0。
    上下歪了(俯仰漂、摆平没摆对)就对不上(11-18 出图自动检查)。"""
    import numpy as np
    if len(keep) < 2:
        return 0.0
    t = np.array([r[0] for r in keep])
    p = np.array([r[1] for r in keep], float)
    worst = []
    for i in range(len(p)):
        j = (np.hypot(*(p[:, :2] - p[i, :2]).T) < SAME_PLACE_R_M) & \
            (np.abs(t - t[i]) > SAME_PLACE_DT_S)
        if j.any():
            worst.append(float(np.abs(p[j, 2] - p[i, 2]).max()))
    return round(float(np.percentile(worst, 95)), 3) if worst else 0.0


def quality(poses: Sequence[Pose]) -> dict[str, float]:
    """路程(每秒取一个点)、首尾相距、最大单步:扫图时回到起点的话,首尾相距就是误差;同一处
    两次经过的高度差(:func:`_same_place_dz`)。"""
    keep: list[Pose] = []
    for r in poses:
        if not keep or r[0] - keep[-1][0] >= 1.0:
            keep.append(r)
    if poses and keep[-1] is not poses[-1]:
        keep.append(poses[-1])
    path = sum(math.dist(a[1][:2], b[1][:2]) for a, b in zip(keep, keep[1:], strict=False))
    steps = [math.dist(a[1][:2], b[1][:2]) for a, b in zip(poses, poses[1:], strict=False)]
    # 判跳用三维位移(竖直方向跳了一样是跟丢,坏位姿会进三维先验;外审 W67-1)
    over = [math.dist(a[1], b[1]) - MAX_SPEED_MPS * (b[0] - a[0])
            for a, b in zip(poses, poses[1:], strict=False)]
    gaps = sum(1 for a, b in zip(poses, poses[1:], strict=False) if b[0] - a[0] > MAX_GAP_S)
    return {"same_place_dz_p95": _same_place_dz(keep),
            "duration_s": round(poses[-1][0] - poses[0][0], 1) if poses else 0.0,
            "path_m": round(path, 1),
            "start_end_m": round(math.dist(poses[0][1][:2], poses[-1][1][:2]), 2) if poses else 0.0,
            "max_step_m": round(max(steps), 2) if steps else 0.0,
            "max_jump_m": round(max(0.0, *over), 3) if over else 0.0, "gaps": gaps}


def check(q: dict[str, float]) -> None:
    """建完把关(:func:`quality` 的结果):跟丢了就抛 :class:`SuperLioError`,这一趟不出图。"""
    if q["max_jump_m"] > JUMP_MARGIN_M:
        raise SuperLioError(f"Super-LIO 的轨迹有突跳(比最快走得还远 {q['max_jump_m']} m):"
                            "跟丢了,这一趟不出图。慢一点重走,开始、结束各静止 10 秒")


# ---------------------------------------------------------------- 出中间文件
Runner = Callable[..., Any]


def _run(run: Runner, cmd: list[str], log: Path, what: str, env: dict[str, str] | None = None
         ) -> None:
    with open(log, "w", encoding="utf-8") as fh:
        rc = run(cmd, stdout=fh, stderr=subprocess.STDOUT, env=env).returncode
    if rc != 0:
        raise SuperLioError(f"{what}失败(退出码 {rc}),日志见 {log}")


def _checked(poses: Iterable[Pose]) -> tuple[list[Pose], dict[str, float]]:
    poses = clean(poses)
    if len(poses) < 20:
        raise SuperLioError(f"Super-LIO 只给了 {len(poses)} 个位姿(没跑起来?)")
    q = quality(poses)
    check(q)
    return poses, q


def prepare(work: Path, bag: Path, poses: Sequence[Pose], *, cfg: Path, root: Path = ROOT,
            prior_pipeline: Path, plugin: Sequence[str] = (), run: Runner = subprocess.run,
            clouds: Iterable[tuple[float, Any]] | None = None,
            xyz_of: Callable[[Any], Any] | None = None, source: str = "",
            level: dict[str, Any] | None = None) -> dict[str, Any]:
    """位姿 → ``work`` 里出图要的三样(``traj.tum``、``map.simplemap``、``raw_prior.mm``)
    + ``mola.json``
    (``build.json`` 抄它:这次用的哪个前端、参数、质量)。回汇总。"""
    poses, q = _checked(poses)
    if xyz_of is None:
        from nexwar_localizer.build import cloud_xyz as xyz_of
    R_il, t_il = extrinsic(cfg)
    work.mkdir(parents=True, exist_ok=True)
    t0 = time.monotonic()
    n = make_keyframes(poses, bag_clouds(bag) if clouds is None else clouds, work, R_il, t_il,
                       xyz_of)
    if level is not None:                                 # 按重力摆平的摘要(:func:`level`)
        n["level"] = level
    info = _finish(work, work / "kf", n, poses, q, cfg=cfg, root=root,
                   prior_pipeline=prior_pipeline, plugin=plugin, run=run, source=source, t0=t0)
    shutil.rmtree(work / "kf", ignore_errors=True)        # 几百 MB,simplemap 里都有了
    return info


def prepare_live(work: Path, kf_dir: Path, *, cfg: Path, root: Path = ROOT,
                 prior_pipeline: Path, plugin: Sequence[str] = (), run: Runner = subprocess.run
                 ) -> dict[str, Any]:
    """边走边存的关键帧(W75,``livemap --keyframes``)→ ``work`` 里出图要的三样 + ``mola.json``,跟
    :func:`prepare` 一样的把关,只是不读录包。``kf_dir`` 原样留着(站点打包也用它)。"""
    try:
        n = json.loads((kf_dir / LIVE_FILE).read_text(encoding="utf-8"))
        n = {k: n[k] for k in ("scans", "traj", "keyframes", "first_scan", "last_scan")}
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise SuperLioError(f"边走边存的关键帧没收尾(没有 {LIVE_FILE}:预览进程没正常停?)"
                            ",从录包建") from exc
    t0 = time.monotonic()
    try:
        raw = clean(read_tum_poses(kf_dir / "lio.tum"))
    except OSError as exc:
        raise SuperLioError("边走边存的关键帧缺位姿(lio.tum)") from exc
    imu = read_imu(kf_dir / IMU_FILE)
    if imu:
        lv_poses, lv = level(raw, imu)
    else:
        lv_poses, lv = raw, {"applied": False, "why": "没记 IMU(机器人上的建图预览是老版本),没摆平"}
    poses, q = _checked(lv_poses)
    work.mkdir(parents=True, exist_ok=True)
    n = {**n, "level": lv}
    if lv.get("applied"):
        kf = _relevel_keyframes(kf_dir, work, poses, cfg)
    else:
        kf = kf_dir / "kf"
        shutil.copyfile(kf_dir / "traj.tum", work / "traj.tum")
    return _finish(work, kf, n, poses, q, cfg=cfg, root=root,
                   prior_pipeline=prior_pipeline, plugin=plugin, run=run, source="live-kf",
                   t0=t0)


def _finish(work: Path, kf: Path, n: dict[str, Any], poses: Sequence[Pose], q: dict[str, float],
            *, cfg: Path, root: Path, prior_pipeline: Path, plugin: Sequence[str], run: Runner,
            source: str, t0: float) -> dict[str, Any]:
    """关键帧取完之后:盖住了多少、够不够,kf2sm 出 simplemap,sm2mm 出先验,写 ``mola.json``。"""
    if n["scans"] and n["traj"] < MIN_POSE_COVERAGE * n["scans"]:
        raise SuperLioError(f"位姿只覆盖了 {n['traj']}/{n['scans']} 帧扫描"
                            "(Super-LIO 中途停了?录位姿断了?),不出残缺的图")
    first, last = n.get("first_scan"), n.get("last_scan")
    if first is not None and (poses[0][0] - first > MAX_EDGE_GAP_S
                              or last - poses[-1][0] > MAX_EDGE_GAP_S):
        raise SuperLioError(f"位姿只覆盖了录包中间一段({poses[0][0] - first:.0f} s 后开始、"
                            f"{last - poses[-1][0]:.0f} s 前结束),不出残缺的图")
    if n["keyframes"] < 3:
        raise SuperLioError(f"关键帧只有 {n['keyframes']} 个(走得太短,或位姿跟点云时间对不上)")
    _run(run, [str(root / "bin/kf2sm"), str(kf), str(work / "map.simplemap")],
         work / "kf2sm.log", "关键帧转 simplemap")
    _run(run, ["sm2mm", *plugin, "-i", str(work / "map.simplemap"), "-o",
               str(work / "raw_prior.mm"), "-p", str(prior_pipeline), "--no-progress-bar"],
         work / "prior.log", "从关键帧出定位先验")
    info = {"builder": "super-lio", "source": source, "config": str(cfg),
            "version": _version(root), "lidar_topic": LIDAR_TOPIC, "imu_topic": IMU_TOPIC,
            "keyframe": {"dist_m": KF_DIST_M, "turn_deg": KF_TURN_DEG}, "quality": q,
            **n, "prepare_s": round(time.monotonic() - t0, 1)}
    (work / "mola.json").write_text(json.dumps(info, ensure_ascii=False, indent=2) + "\n",
                                    encoding="utf-8")
    return info


def _version(root: Path) -> str:
    try:
        return Path(os.path.realpath(root)).name
    except OSError:
        return "?"


# ---------------------------------------------------------------- 从录包重算
def run_offline(bag: Path, work: Path, *, cfg: Path, root: Path = ROOT, rate: float = OFFLINE_RATE,
                env: dict[str, str] | None = None, node: str = "super_lio_node") -> Path:
    """在本机隔离域里起 Super-LIO、回放录包的前雷达 + IMU、把它的位姿录成一个小包。回那个包的目录。

    ``env``:额外的环境变量。隔离域由调用方给(建图编排起建图脚本时已经设好,这里不覆盖;外审
    W67-1);环境里没有 ROS_DOMAIN_ID 才用 :data:`OFFLINE_ENV`。``node``:建图 ``super_lio_node``,
    定位回放 ``relocation_node``(W68)。
    收到 SIGTERM(建图被停)也照样把起的进程组收掉。"""
    out = work / "lio_bag"
    shutil.rmtree(out, ignore_errors=True)
    work.mkdir(parents=True, exist_ok=True)
    e = dict(os.environ)
    if "ROS_DOMAIN_ID" not in e:           # 手动跑、没给域:用隔离域,别把点云放进机器人那个域
        e.update(OFFLINE_ENV)
    e.update(env or {})
    q = shlex.quote
    src = (f"set +u; . /opt/ros/humble/setup.bash; . {q(str(root))}/install/setup.bash; "
           "set -u; exec ")
    qos = work / "qos.yaml"
    # 回放要显式给 QoS:这些包里存的 QoS 在别的机器上读不出来时,ros2 bag play 一个话题都不发(11-02)
    qos.write_text("".join(f"{t}:\n  reliability: reliable\n  durability: volatile\n"
                           f"  history: keep_last\n  depth: {d}\n"
                           for t, d in ((LIDAR_TOPIC, 50), (IMU_TOPIC, 500))), encoding="utf-8")
    node_cmd = f"ros2 run super_lio {node} " + shlex.join(node_args(cfg, ns_remap=False))
    rec_cmd = f"ros2 bag record -s mcap -o {q(str(out))} /lio/odom"
    play_cmd = (f"ros2 bag play {q(str(bag))} --rate {rate} --topics {LIDAR_TOPIC} {IMU_TOPIC} "
                f"--qos-profile-overrides-path {q(str(qos))}")
    logs = {k: work / f"{k}.log" for k in ("superlio", "record", "play")}
    procs: list[tuple[str, subprocess.Popen[bytes], Path]] = []

    def _term(*_: Any) -> None:
        raise SystemExit(143)              # 让 finally 跑:按进程组收掉起的进程

    old = signal.signal(signal.SIGTERM, _term)
    try:
        for name, cmd, log in (("Super-LIO", node_cmd, logs["superlio"]),
                               ("录位姿", rec_cmd, logs["record"])):
            procs.append((name, subprocess.Popen(["bash", "-c", src + cmd], env=e,
                                                 stdout=open(log, "wb"),
                                                 stderr=subprocess.STDOUT,
                                                 start_new_session=True), log))
            time.sleep(3)
            _check_alive(procs)
        play = subprocess.Popen(["bash", "-c", src + play_cmd], env=e,
                                stdout=open(logs["play"], "wb"), stderr=subprocess.STDOUT,
                                start_new_session=True)
        procs.append(("回放", play, logs["play"]))
        while play.poll() is None:
            time.sleep(1)
            _check_alive(procs[:-1])       # 回放途中 Super-LIO、录位姿退了:不等放完,直接报
        time.sleep(3)
        _check_alive(procs[:-1])
        if play.returncode != 0:
            raise SuperLioError(f"回放录包失败,日志见 {logs['play']}")
    finally:
        for _, p, _ in reversed(procs):    # 先停录(把位姿写完),再停 Super-LIO;按进程组停
            _stop(p)
        signal.signal(signal.SIGTERM, old)
    if not out.is_dir():
        raise SuperLioError(f"Super-LIO 的位姿没录下来,日志见 {logs['record']}")
    return out


def _check_alive(procs: Sequence[tuple[str, subprocess.Popen[bytes], Path]]) -> None:
    for name, p, log in procs:
        if p.poll() is not None:
            raise SuperLioError(f"{name} 提前退出(退出码 {p.returncode}),日志见 {log}")


def _stop(p: subprocess.Popen[bytes], grace_s: float = 60.0) -> None:
    """按进程组停:先 SIGINT 等组长退,再把组里剩下的(组长退了、子进程还在)SIGKILL 掉。"""
    if p.poll() is None:
        try:
            os.killpg(p.pid, signal.SIGINT)
            p.wait(timeout=grace_s)
        except ProcessLookupError:
            pass
        except subprocess.TimeoutExpired:
            pass
    try:
        os.killpg(p.pid, signal.SIGKILL)   # 组里还有谁(或组长没退)一并收掉;组空了会抛
    except ProcessLookupError:
        pass
    try:
        p.wait(timeout=10)
    except subprocess.TimeoutExpired:
        pass


# ---------------------------------------------------------------- 机器人上边走边建
def node_exe(root: Path | None = None) -> Path:
    return (ROOT if root is None else root) / "install/super_lio/lib/super_lio/super_lio_node"


def main(argv: Sequence[str] | None = None) -> int:
    """``live``:换成 ``super_lio_node`` 进程(``deploy/nexwar_superlio_live`` 先 source 好 ROS 和
    Super-LIO 的工作区)。发的话题全改到 :data:`NS` 下,跟定位器、竞品的 ``/lio/*`` 不串。"""
    import argparse
    ap = argparse.ArgumentParser(prog="nexwar_superlio")
    ap.add_argument("cmd", choices=["live"])
    ap.parse_args(argv)
    exe = node_exe()
    if not installed() or not exe.is_file():
        print(f"Super-LIO 未装({ROOT}):先跑 deploy/nexwar_superlio_build", flush=True)
        return 2
    cfg = config_path()
    print(f"Super-LIO 建图:参数 {cfg},位姿发到 {LIVE_TOPIC}", flush=True)
    os.execv(str(exe), [str(exe), *node_args(cfg, ns_remap=True)])
    return 0  # pragma: no cover


if __name__ == "__main__":
    raise SystemExit(main())
