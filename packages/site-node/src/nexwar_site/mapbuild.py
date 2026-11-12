"""W75 方案 1(用户 11-12):站点主机打包。

机器人边走边建时边存关键帧(5 cm 降采样),存一个传一个上来(发件箱的 ``mapkf``,接收口
``/mapkf``),落在 ``<站点目录>/mapkf-in/<机器人>/<地图号>/<版本>/``。结束建图时机器人最后传
``kf.json``(每个文件的大小和 sha256)。站点收齐、核对完,就在后台起出图命令(``nexwar_loc build
--from-keyframes``,站点主机上装的出图组件),出完登记成这一版地图 —— 回环不占机器人的 CPU 和内存
(广场 8 分钟那趟回环 8–12 GB 内存)。

- 只收站点让这台机器人建的那一版(跟收图一样);路径只许 ``<文件名>`` 或 ``kf/<文件名>``。
- 一次只出一张图(回环吃满 CPU 和内存)。出图命令每到一步打一行 ``@@进度 <这一步>``,
  :func:`progress_pct` 按台式机实测的各步用时折成百分比给手机、网页。
- 出成了:登记(来源是机器人的号,备注「站点打包」),收件那份关键帧删掉;没出成:原因(日志尾巴)记在
  ``.failed`` 里,关键帧留着,可以重试(:meth:`SiteMapBuilder.retry`);站点重启后不自己再跑失败的。
- 站点重启:收齐了、还没出的接着出。
- **默认不回环**(用户 11-13):出图就直接用。出成了关键帧挪到 ``mapkf-keep/`` 留着(最近
  :data:`KEEP_N` 份);漂移大了,工程师在建图向导里点「优化地图」(:meth:`SiteMapBuilder.optimize`),
  站点拿留着的关键帧回环、登记成新的一版(旧版留着:登记了的版本不改,机器人可能已经在用)。
"""

from __future__ import annotations

import collections
import hashlib
import json
import logging
import os
import re
import shutil
import signal
import subprocess
import threading
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from nexwar_contract.errors import ContractError
from nexwar_contract.maps import check_name
from nexwar_site.evidence import ChunkWriter, PathRefused, Stored, safe_join

log = logging.getLogger(__name__)

#: 机器人最后传的清单(``{"map_id", "version", "files": [{"name", "size", "sha256"}]}``)。
KF_MANIFEST = "kf.json"
INCOMING = "mapkf-in"
WORK = "mapkf-work"
#: 出成了的关键帧挪到这里留着,给「优化地图」用(``<机器人>/<地图号>/<版本>/``)。
KEEP = "mapkf-keep"
#: 最多留几份(一份广场那么大约 300 MB):超了删最老的。
KEEP_N = 5
#: 优化请求落在留着的那份关键帧目录里:``.optimize-<新版本>``,内容空 = 排着,``failed: …`` = 没成。
OPT_PREFIX = ".optimize-"
#: 出图命令报进度的行(跟 ``nexwar_localizer.tools.PROGRESS`` 一致)。
PROGRESS = "@@进度"
#: 各步、台式机上广场 8 分钟那趟各用了多少秒(W75 实测;回环 11-13 调参后):按它折百分比。
STAGES: tuple[tuple[str, float], ...] = (
    ("关键帧", 15.0), ("回环", 64.0), ("点云", 7.0), ("栅格", 14.0), ("先验", 1.0),
    ("定位地图", 3.0))
#: 给手机、网页的阶段代号(界面按它翻译;出图命令打的是中文阶段名)。
STAGE_CODES = {"关键帧": "keyframes", "回环": "loop", "点云": "points", "栅格": "grid",
               "先验": "prior", "定位地图": "locmap", "完成": "done"}
DONE_STAGE = "完成"
#: 出图最多跑多久。
TIMEOUT_S = 3600.0
#: 失败原因带日志的最后几行。
TAIL_LINES = 12
FAILED = ".failed"
#: 机器人作废了这一趟关键帧(W75 外审 2 #4):收件目录旁边留这个记号,迟到的旧上传直接丢弃。
ABANDONED = ".abandoned"
_REL = re.compile(r"^(?:kf/)?[A-Za-z0-9][A-Za-z0-9_.-]*$")

Job = tuple[str, str, str]          # (机器人, 地图号, 版本)


def progress_pct(stage: str, elapsed_s: float, *, lc: bool = True) -> int:
    """在 ``stage`` 这一步、已经走了 ``elapsed_s`` 秒:百分之几。一步之内按时间往前挪,最多挪到这一步
    预计用时的 95%(机器慢的话停在那儿等,不越过下一步的起点)。``lc``:这一趟回不回环(不回环不算
    回环那一段)。"""
    if stage == DONE_STAGE:
        return 100
    stages = [(n, d) for n, d in STAGES if lc or n != "回环"]
    total = sum(d for _, d in stages)
    before = 0.0
    for s, d in stages:
        if s == stage:
            return min(99, int(100 * (before + min(max(elapsed_s, 0.0), 0.95 * d)) / total))
        before += d
    return 0


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class SiteMapBuilder:
    def __init__(self, home: Path, maps: Any, *, runner: Sequence[str],
                 on_done: Callable[[dict[str, Any]], None] | None = None,
                 start_thread: bool = True, now: Callable[[], float] = time.monotonic) -> None:
        """``runner``:出图命令(后面接 ``build --from-keyframes … --out … --work …``)。``on_done``:
        出完(成没成都调)``{"robot_id", "map_id", "version", "ok", "reason"}``。"""
        self.root = Path(home) / INCOMING
        self.work_root = Path(home) / WORK
        self.keep_root = Path(home) / KEEP
        self.root.mkdir(parents=True, exist_ok=True)
        self.maps = maps
        self.runner = list(runner)
        self.on_done = on_done
        self.writer = ChunkWriter()
        self._now = now
        self._cv = threading.Condition()
        # 外审 W75-3 #1:清理留着的关键帧、收优化请求排成一个接一个(删之前核的「谁在用」不会过时)
        self._keep_lock = threading.Lock()
        self._queue: collections.deque[Job] = collections.deque()
        #: (地图号, 版本) → 状态(``robot_id``、``state``、``stage``、``since``、``reason``)。
        self._status: dict[tuple[str, str], dict[str, Any]] = {}
        #: 优化(回环)的那几趟:(地图号, 新版本) → (留着的关键帧目录, 从哪一版来)。
        self._opt: dict[tuple[str, str], tuple[Path, str]] = {}
        self._scan()
        if hasattr(maps, "in_flight_hooks"):
            maps.in_flight_hooks.append(self.in_flight)
        if start_thread:
            threading.Thread(target=self._loop, name="site-mapbuild", daemon=True).start()

    # ------------------------------------------------------------ 收

    def put_chunk(self, robot_id: str, run: str, rel: str, *, offset: int, data: bytes,
                  total: int) -> Stored:
        """``run`` = ``<地图号>/<版本>``,``rel`` = ``kf/<文件名>`` 或 ``<文件名>``。"""
        try:
            map_id, version = run.split("/")
            check_name(map_id, "地图号")
            check_name(version, "版本")
        except (ValueError, ContractError) as exc:
            raise PathRefused(f"关键帧的路径错误:{run!r}/{rel!r}") from exc
        if not _REL.match(rel) or ".." in rel:
            raise PathRefused(f"关键帧的路径错误:{run!r}/{rel!r}")
        if not self.maps._build_issued(robot_id, map_id, version):
            raise PathRefused(f"站点未让 {robot_id} 建 {map_id}:{version}")
        if self._abandoned_mark((robot_id, map_id, version)).is_file():
            # 作废过了:迟到的旧上传不重建收件目录,叫机器人当传完(它早清了这一趟)
            return Stored(size=total, sha256="", discarded=True)
        path = safe_join(self.root, robot_id, map_id, version, *rel.split("/"))
        got = self.writer.write(path, offset=offset, data=data, total=total)
        if self._abandoned_mark((robot_id, map_id, version)).is_file():
            # 写的时候作废正好处理完了(这一块在它之后落盘):删掉,照样叫机器人当传完
            shutil.rmtree(self._dir((robot_id, map_id, version)), ignore_errors=True)
            return Stored(size=total, sha256="", discarded=True)
        if got.size >= total:
            self._check((robot_id, map_id, version))
        return got

    def _dir(self, job: Job) -> Path:
        return self.root / job[0] / job[1] / job[2]

    def _abandoned_mark(self, job: Job) -> Path:
        return self.root / job[0] / job[1] / (job[2] + ABANDONED)

    def _check(self, job: Job) -> None:
        """清单到了、文件都齐、大小和哈希都对 → 排进队。没齐什么也不做;对不上抛 :class:`PathRefused`
        (机器人隔离那个文件、站点出「不收」的告警)。"""
        d = self._dir(job)
        key = (job[1], job[2])
        with self._cv:
            if self._status.get(key, {}).get("state") in ("queued", "running", "done"):
                return
        try:
            m = json.loads((d / KF_MANIFEST).read_text(encoding="utf-8"))
            if (m.get("map_id"), m.get("version")) != key:
                raise ValueError(f"清单写的是 {m.get('map_id')}:{m.get('version')}")
            if m.get("abandoned") is True:
                # 外审 W75-1 #4:机器人交不了(关键帧不齐),退回自己从录包建:收了一半的删掉,不出图
                mark = self._abandoned_mark(job)
                mark.write_text(str(m.get("reason", ""))[:200], encoding="utf-8")
                shutil.rmtree(d, ignore_errors=True)
                with self._cv:
                    self._status.pop(key, None)
                log.info("%s 作废了 %s:%s 的关键帧(%s):收了一半的删掉", job[0], *key,
                         str(m.get("reason", ""))[:200])
                return
            files = [(str(f["name"]), int(f["size"]), str(f["sha256"])) for f in m["files"]]
        except FileNotFoundError:
            self._set(job, "uploading")
            return
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise PathRefused(f"{job[0]} 传来的 {key[0]}:{key[1]} 关键帧清单无法读取:{exc}") \
                from exc
        for name, size, _ in files:
            if not _REL.match(name) or ".." in name:
                raise PathRefused(f"关键帧清单里的文件名不对:{name!r}")
            p = d / name
            if not p.is_file() or p.stat().st_size < size:
                self._set(job, "uploading")
                return
        for name, size, sha in files:
            p = d / name
            if p.stat().st_size != size or _sha256(p) != sha:
                raise PathRefused(f"{job[0]} 传来的 {key[0]}:{key[1]} 里 {name} 与清单不匹配")
        with self._cv:
            self._status[key] = {"robot_id": job[0], "state": "queued", "since": self._now()}
            self._queue.append(job)
            self._cv.notify_all()
        log.info("%s 的关键帧收齐了:%s:%s,排队出图", *job)

    def _scan(self) -> None:
        for m in sorted(self.keep_root.glob(f"*/*/*/{OPT_PREFIX}*")):
            kd = m.parent
            robot, map_id, frm = kd.parent.parent.name, kd.parent.name, kd.name
            to = m.name[len(OPT_PREFIX):]
            self._opt[(map_id, to)] = (kd, frm)
            why = m.read_text(encoding="utf-8", errors="replace")
            if why.startswith("failed: "):
                self._set((robot, map_id, to), "failed", reason=why[len("failed: "):], lc=True)
            elif not self._registered(map_id, to):
                self._enqueue((robot, map_id, to))
        for d in sorted(self.root.glob("*/*/*")):
            if not d.is_dir():
                continue
            job: Job = (d.parent.parent.name, d.parent.name, d.name)
            if self._abandoned_mark(job).is_file():   # 作废过,又被迟到的上传建了出来:清掉
                shutil.rmtree(d, ignore_errors=True)
                continue
            f = d / FAILED
            if f.is_file():
                self._set(job, "failed", reason=f.read_text(encoding="utf-8", errors="replace"))
                continue
            try:
                self._check(job)
            except PathRefused as exc:
                log.warning("站点重启后核关键帧:%s", exc)

    def _registered(self, map_id: str, version: str) -> bool:
        try:
            self.maps.get(map_id, version)
            return True
        except Exception:  # noqa: BLE001 - MapError:没有这一版
            return False

    def _enqueue(self, job: Job) -> None:
        with self._cv:
            self._status[(job[1], job[2])] = {"robot_id": job[0], "state": "queued",
                                               "since": self._now(),
                                               "lc": (job[1], job[2]) in self._opt}
            self._queue.append(job)
            self._cv.notify_all()

    def _set(self, job: Job, state: str, **kw: Any) -> None:
        with self._cv:
            self._status[(job[1], job[2])] = {"robot_id": job[0], "state": state,
                                               "since": self._now(), **kw}

    # ------------------------------------------------------------ 查、重试

    def status(self, map_id: str, version: str) -> dict[str, Any] | None:
        """``{"state": uploading|queued|running|done|failed, "stage", "pct", "reason"}``;
        没有是 None。"""
        with self._cv:
            st = dict(self._status.get((map_id, version)) or {})
        if not st:
            return None
        out: dict[str, Any] = {"state": st["state"], "robot_id": st["robot_id"]}
        if st["state"] == "running":
            out["stage"] = st.get("stage", STAGES[0][0])
            since = st.get("stage_since", st["since"])
            out["pct"] = progress_pct(out["stage"], self._now() - since, lc=bool(st.get("lc")))
        elif st["state"] == "done":
            out["pct"] = 100
        elif st["state"] == "failed":
            out["reason"] = str(st.get("reason", ""))[:600]
        return out

    def retry(self, map_id: str, version: str) -> None:
        with self._cv:
            st = self._status.get((map_id, version))
        if st is None or st["state"] != "failed":
            raise ValueError(f"{map_id}:{version} 不是出图失败的")
        job = (st["robot_id"], map_id, version)
        opt = self._opt.get((map_id, version))
        if opt is not None:                               # 优化没成:再回环一次
            (opt[0] / f"{OPT_PREFIX}{version}").write_text("", encoding="utf-8")
            self._enqueue(job)
            return
        (self._dir(job) / FAILED).unlink(missing_ok=True)
        with self._cv:
            del self._status[(map_id, version)]
        self._check(job)

    # ------------------------------------------------------------ 优化地图(回环)

    def _kept(self, robot_id: str, map_id: str, version: str) -> Path:
        return self.keep_root / robot_id / map_id / version

    def in_flight(self, map_id: str, version: str) -> bool:
        """这一版号被「优化地图」占着(排着、出着、失败待重试;还没登记)。"""
        with self._cv:
            if (map_id, version) not in self._opt:
                return False
        return not self._registered(map_id, version)

    def optimizable(self, robot_id: str, map_id: str, version: str) -> bool:
        """这一版能不能「优化地图」:站点出的、关键帧还留着、自己不是优化出来的。"""
        return (map_id, version) not in self._opt \
            and (self._kept(robot_id, map_id, version) / KF_MANIFEST).is_file()

    def optimize(self, robot_id: str, map_id: str, version: str, to_version: str) -> None:
        """拿 ``version`` 留着的关键帧回环,出成 ``to_version``(新的一版;``version`` 不动)。"""
        with self._keep_lock:
            if not self.optimizable(robot_id, map_id, version):
                raise ValueError(f"{map_id}:{version} 的关键帧没留在站点上,不能优化")
            kd = self._kept(robot_id, map_id, version)
            (kd / f"{OPT_PREFIX}{to_version}").write_text("", encoding="utf-8")   # 站点重启接着跑
            with self._cv:
                self._opt[(map_id, to_version)] = (kd, version)
            self._enqueue((robot_id, map_id, to_version))
        log.info("%s:%s 排队优化(回环),出成 %s", map_id, version, to_version)

    def _keep(self, job: Job, kd: Path) -> None:
        """出成了:关键帧挪到 ``mapkf-keep`` 留着;超过 :data:`KEEP_N` 份删最老的。"""
        dst = self._kept(*job)
        with self._keep_lock:
            self._keep_locked(kd, dst)

    def _keep_locked(self, kd: Path, dst: Path) -> None:
        try:
            if kd != dst:
                shutil.rmtree(dst, ignore_errors=True)
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(kd), str(dst))
            with self._cv:                              # 外审 W75-2 #3:优化还要用的不删
                busy = {src.resolve() for (m, v), (src, _) in self._opt.items()
                        if not self._registered(m, v)}
            kept = sorted((d for d in self.keep_root.glob("*/*/*")
                           if d.is_dir() and d.resolve() not in busy),
                          key=lambda d: d.stat().st_mtime)
            for old in kept[:max(0, len(kept) - KEEP_N)]:
                shutil.rmtree(old, ignore_errors=True)
        except OSError:
            log.exception("留关键帧没成(不影响这一版)")

    # ------------------------------------------------------------ 出图

    def _loop(self) -> None:
        while True:
            with self._cv:
                while not self._queue:
                    self._cv.wait()
            self.run_pending()

    def run_pending(self) -> None:
        """把队里的一个个出完(测试直接调;后台线程也调它)。"""
        while True:
            with self._cv:
                if not self._queue:
                    return
                job = self._queue.popleft()
            try:
                self._run(job)
            except Exception as exc:  # 一张出不成不能把后台线程弄死
                # 外审 W75-1 #5:盘满、开不了日志这类意外也记成失败(能重试、告诉人),不能卡在排队
                log.exception("出图 %s:%s 出错", job[1], job[2])
                try:
                    self._failed(job, f"出图出错:{exc}")
                except Exception:
                    log.exception("出图 %s:%s 记不下失败", job[1], job[2])

    def _run(self, job: Job) -> None:
        robot, map_id, version = job
        opt = self._opt.get((map_id, version))
        kd = opt[0] if opt is not None else self._dir(job)
        base = self.work_root / robot / map_id / version
        out, work = base / "out", base / "work"
        shutil.rmtree(base, ignore_errors=True)
        base.mkdir(parents=True)
        t0 = self._now()
        self._set(job, "running", stage=STAGES[0][0], stage_since=t0, lc=opt is not None)
        tail: collections.deque[str] = collections.deque(maxlen=TAIL_LINES)
        # 用户 11-13:默认不回环;「优化地图」那一趟才回环
        cmd = [*self.runner, "build", "--from-keyframes", str(kd), "--out", str(out),
               "--work", str(work), "--loop-closure", "auto" if opt is not None else "off"]
        rc: int | None
        with open(base / "build.log", "w", encoding="utf-8") as logf:
            try:
                p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                     text=True, errors="replace", start_new_session=True)
            except OSError as exc:
                return self._failed(job, f"出图命令起不来:{exc}")
            # 外审 W75-1 #6:超时不能靠读日志行时顺带看(程序不出声卡住就永远读不到下一行)——
            # 另起定时器,到点把整组进程(出图程序和它起的子命令)杀掉
            timed_out = threading.Event()

            def _expire() -> None:
                timed_out.set()
                _kill_group(p)
            watchdog = threading.Timer(TIMEOUT_S, _expire)
            watchdog.daemon = True
            watchdog.start()
            try:
                rc = self._follow(p, logf, tail, map_id, version)
            finally:
                watchdog.cancel()
                if p.poll() is None:            # 读日志时出了意外:别留下没人管的出图程序
                    _kill_group(p)
                    p.wait()
            if timed_out.is_set():
                tail.append(f"出图超过 {TIMEOUT_S:.0f} 秒,停了")
                rc = None
        if rc != 0:
            return self._failed(job, f"出图没成(退出码 {rc}):" + " / ".join(tail))
        note = (f"站点优化(回环,从 {opt[1]})" if opt is not None
                else "站点打包(边走边存的关键帧)")
        try:
            self.maps.import_dir(out, map_id=map_id, version=version, source=robot, note=note)
        except Exception as exc:  # noqa: BLE001 —— MapError、盘满……都按没成说
            return self._failed(job, f"出完了但登记不进地图目录:{exc}")
        shutil.rmtree(base, ignore_errors=True)
        if opt is not None:
            (kd / f"{OPT_PREFIX}{version}").unlink(missing_ok=True)
        else:
            self._keep(job, kd)
        self._set(job, "done", seconds=round(self._now() - t0, 1))
        log.info("站点打包出完了:%s:%s(%s 的关键帧,%.0f 秒)", map_id, version, robot,
                 self._now() - t0)
        self._tell(job, ok=True, reason="")

    def _follow(self, p: subprocess.Popen[str], logf: Any, tail: collections.deque[str],
                map_id: str, version: str) -> int:
        """读出图程序的输出(进度行改阶段,别的记日志、留尾巴),读完等它退出,回退出码。"""
        assert p.stdout is not None
        for line in p.stdout:
            logf.write(line)
            line = line.rstrip("\n")
            if line.startswith(PROGRESS + " "):
                stage = line[len(PROGRESS) + 1:].strip()
                with self._cv:
                    self._status[(map_id, version)].update(stage=stage, stage_since=self._now())
            elif line.strip():
                tail.append(line)
        return p.wait()

    def _failed(self, job: Job, reason: str) -> None:
        reason = reason[:1000]
        opt = self._opt.get((job[1], job[2]))
        try:
            if opt is not None:
                (opt[0] / f"{OPT_PREFIX}{job[2]}").write_text(f"failed: {reason}",
                                                              encoding="utf-8")
            else:
                (self._dir(job) / FAILED).write_text(reason, encoding="utf-8")
        except OSError:
            log.exception("记不下出图失败的原因")
        self._set(job, "failed", reason=reason, lc=opt is not None)
        log.warning("站点打包 %s:%s 没成:%s", job[1], job[2], reason)
        self._tell(job, ok=False, reason=reason)

    def _tell(self, job: Job, *, ok: bool, reason: str) -> None:
        if self.on_done is None:
            return
        try:
            self.on_done({"robot_id": job[0], "map_id": job[1], "version": job[2], "ok": ok,
                          "reason": reason})
        except Exception:
            log.exception("出图结果的回调出错")


def notify(desk: Any, r: dict[str, Any]) -> None:
    """出完了告诉人(W75):成了记一条「地图已建成」(P3,推给管理员、工程师),之前的建图失败解决掉;
    没成报「建图失败」(带原因)。``desk`` 是告警簿(线程里用 ``LoopAlerts``)。"""
    rid, which = r["robot_id"], f"{r['map_id']}:{r['version']}"
    if r["ok"]:
        desk.raise_alert(kind="map_ready", robot=rid, title=f"地图已建成:{which}",
                         detail="在建图向导里看结论、点「用这张图」", merge=False)
        desk.resolve_all(rid, "map_failed", who="site:map_ready")
    else:
        desk.raise_alert(kind="map_failed", robot=rid, title=f"站点出图失败:{which}",
                         detail=f"{r['reason'][-280:]};关键帧留在站点上,可以重试")


#: 出图组件装好的命令(``install-site.sh --with-mapping`` 装;它起 ROS 环境再跑
#: ``nexwar_localizer.tools``)。
DEFAULT_RUNNER = Path("/usr/local/bin/nexwar_site_mapbuild")


def runner_from(cfg: dict[str, Any], *, default: Path = DEFAULT_RUNNER) -> list[str] | None:
    """``site.json`` 的 ``mapbuild``:``{"runner": [...]}`` 用它;``{"enabled": false}`` 关掉;没写就看
    出图组件装没装。回 None = 不在站点上出图(机器人照旧自己打包)。"""
    m = cfg.get("mapbuild") or {}
    if m.get("enabled") is False:
        return None
    if m.get("runner"):
        r = m["runner"]
        return [str(x) for x in r] if isinstance(r, list) else [str(r)]
    return [str(default)] if Path(default).is_file() else None


def _kill_group(p: subprocess.Popen[str]) -> None:
    """杀出图程序整组进程(它起的回环、出点云子命令一起)。"""
    try:
        os.killpg(p.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass
