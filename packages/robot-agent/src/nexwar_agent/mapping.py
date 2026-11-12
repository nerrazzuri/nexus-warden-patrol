"""录包与重建经站点(W00c5d 第二部分,决策 8)。

站点下命令 ``mapping``(开始 / 停止录包,人经站点遥控开着狗走)、``map_build``(拿录好的包在狗上
离线重建一张图)。这里只是把现成的建图编排(``nexwar_patrol.app.mapping.MappingOrchestrator``,
录 mcap 包 → MOLA 离线建一个地图版本,W09c1)接到发件箱上:

- **包**写进发件箱 ``bags/<包名>-<UTC 时刻>/``(带时刻:同名的包不会在站点上覆盖上一个);停录时打
  一个 ``.done``。**重建成功之后(``.built``)或录完满 ``BAG_KEEP_DAYS`` 天**,传完、站点确认才删 ——
  包是在狗上重建的原料,传完就删的话「拿这个包重建」几乎永远做不成(内部评审)。正在拿它重建的包不删。
- **重建出来的图**(``GEOMETRY_FILES`` 那几样,缺一样都不算建成)挪进发件箱 ``maps/<地图号>/<版本>/``
  (挪、不拷:先验几百 MB),文件都就位之后**最后写** ``map.json``(每个文件的大小与 sha256):站点
  收齐这一份、核对全部文件才登记;狗上传完就删。
- 包传完删了再想重建:这一张不做(在站点上重建要站点主机有 ROS,列进后续)。
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import logging
import os
import shutil
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from nexwar_contract.maps import GEOMETRY_FILES, MANIFEST, OPTIONAL_FILES, MapFile, MapRef

log = logging.getLogger(__name__)

#: 包停录后打的标记;拿它重建成功后打的标记。
DONE = ".done"
BUILT = ".built"
#: 边走边建的包(W09c2):开录时记下建哪一版(``{"map_id", "version"}``),收尾完了删。代理重启时按它
#: 接着收尾(内审应修 1:待打包原来只在内存里,重启就丢,站点一直当它「在建」)。
LIVE = ".live"
#: 没重建过的包,录完之后在狗上最多留几天(传完、站点确认之后才删)。
BAG_KEEP_DAYS = 7
#: **盘紧了就不留**(W00c5d 第三部分内部评审:留着的包把发件箱撑满,巡检就被拒 storage_full):
#: 发件箱过了上限的这一份、或者盘用到这条线,传完了的包一律可以删 —— 站点上有一份。
RETAIN_CAP_SHARE = 0.5
RETAIN_DISK_RATIO = 0.8
#: 建图预览(W09f):预览进程写的快照(``nexwar_localizer.livemap.SNAPSHOT``)、原样转给手机的几项;
#: base64 的 PNG 超过这么大不带(再加说明、轨迹还在回执的 240 KiB 以内;正常一层楼 20 KB 上下)。
PREVIEW_FILE = "preview.json"
PREVIEW_FIELDS = ("run", "res", "origin", "width", "height", "pose", "trail", "frames", "dropped")
PREVIEW_PNG_MAX_B64 = 200 * 1024
#: 整条预览数据编码后的预算(回执上限 240 KiB 再留出命令号、主题):超了去掉 PNG、标 ``too_big``,
#: 说明与轨迹照给(内审小 5:原来超了整条数据被出口兜底去掉,站点 502、手机只说连不上)
PREVIEW_MAX_BYTES = 230 * 1024


#: W75 方案 1(站点打包):边走边存的关键帧放进发件箱的这一块(``mapkf/<地图号>/<版本>/``),存一个传一个;
#: 走完写清单 ``kf.json``(最后传),站点收齐核对完在站点主机上出图。``live.json`` 是预览进程收尾写的。
KF_SUB = "mapkf"
KF_MANIFEST = "kf.json"
KF_LIVE = "live.json"
#: 预览进程最后收到雷达的时刻离停录(录包的完成标记)最多这么远(秒),才算关键帧存到了最后(外审 W75-1
#: #1:预览半路没了、关键帧只存了前 10 秒,原来照样交给站点、出一张缺一大块的图)。
KF_COVER_S = 10.0


def kf_classify(rel: str) -> int | None:
    """关键帧都传,清单最后走;点开头的(写到一半的临时文件)不传。"""
    if rel.split("/")[-1].startswith("."):
        return None
    return 5 if rel == KF_MANIFEST else 4


def kf_settled(run: Path) -> bool:
    """有清单才算这一趟写完(传完、站点确认才删)。"""
    return (run / KF_MANIFEST).is_file()


def _check_live(live: Path, done: Path) -> None:
    """关键帧齐不齐(外审 W75-1 #1):预览进程收到停止信号正常收尾、写关键帧没出过错、最后收到的雷达
    离停录不超过 :data:`KF_COVER_S`。不齐抛 :class:`MappingError`(退回在机器人上从录包打包)。"""
    try:
        d = json.loads(live.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise MappingError(f"关键帧收尾文件读不了:{exc}") from exc
    if not isinstance(d, dict) or d.get("clean") is not True:
        raise MappingError("边走边存的关键帧没收尾(预览进程没正常停)")
    errs = d.get("kf_errors")
    if not isinstance(errs, int) or isinstance(errs, bool) or errs:
        raise MappingError(f"边走边存的关键帧写盘出过错({errs} 次)")
    last = d.get("last_rx")
    if not isinstance(last, (int, float)) or isinstance(last, bool):
        raise MappingError("边走边存的关键帧没记最后收到雷达的时刻")
    try:
        stopped = done.stat().st_mtime
    except OSError as exc:
        raise MappingError(f"录包没有完成标记:{exc}") from exc
    if stopped - float(last) > KF_COVER_S:
        raise MappingError(f"边走边存的关键帧只存到停录前 {stopped - float(last):.0f} 秒"
                           "(预览进程中途停了?)")


def storage_pressure(facts: Any) -> bool:
    """盘况(``StorageFacts``)说盘紧了:留着备重建的包该让位了。"""
    if facts is None:
        return False
    return (facts.outbox_bytes > facts.outbox_cap_bytes * RETAIN_CAP_SHARE
            or facts.disk_used_ratio >= RETAIN_DISK_RATIO)


class MappingError(RuntimeError):
    """录包、重建做不了。消息给站点看。"""


def bag_classify(rel: str) -> int | None:
    """包里的文件都传,优先级最低(照片、事件先走);点开头的标记不传。"""
    return None if rel.split("/")[-1].startswith(".") else 5


def map_classify(rel: str) -> int | None:
    """图的文件先走,``map.json`` 最后走(站点收齐它才登记)。"""
    if rel.split("/")[-1].startswith("."):
        return None
    return 5 if rel == MANIFEST else 4


def map_settled(run: Path) -> bool:
    return (run / MANIFEST).is_file()


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class MappingService:
    def __init__(self, orchestrator: Any, *, bags_root: Path, maps_out: Path,
                 kf_root: Path | None = None) -> None:
        """``kf_root``(W75):发件箱里放边走边存关键帧的那一块;没有就不能站点打包。"""
        self.orch = orchestrator
        self.kf_root = None if kf_root is None else Path(kf_root)
        #: 正在边走边建的、待打包的这一趟在哪打包(``robot`` / ``site``,W75)。
        self.live_pack = "robot"
        self.pending_pack = "robot"
        self.bags_root = Path(bags_root)
        self.maps_out = Path(maps_out)
        self.recording = False
        self.last_bag = ""
        #: 正在拿来重建的包:不许删。跟发件箱删包用同一把锁(判「能不能删」和删在锁里一起做)。
        self.held: set[str] = set()
        self.lock = threading.Lock()
        #: 盘紧不紧(主程序接到发件箱的盘况上):紧了传完的包不再留着备重建。
        self.pressure: Callable[[], bool] = lambda: False
        #: 本地地图库(``MapKeeper``,主程序接上):建好的版本放进去,激活时不用从站点下回来。
        self.keeper: Any = None
        #: 上一次建图的栅格用的哪种射线(``build.json`` 的 ``grid.rays``;``synthetic:…`` 是退回了)。
        self.last_rays = ""
        #: 正在边走边建的(地图号, 版本);停录之后待打包的(包, 地图号, 版本);上一次在线那份
        #: 打不成、退回从录包建的原因(W09c2)。
        self.live: tuple[str, str] | None = None
        self.pending: tuple[str, str, str] | None = None
        #: 开录那条命令的号(正在录的、待打包的):建好、没建成的事件带它(外审阻断 3)。
        self.live_task = ""
        self.pending_task = ""
        self.last_fallback = ""
        #: 起来时找到的、没法接着收尾的边走边建(包, 地图号, 版本, 命令号):调用方报「没建成」。
        self.lost: list[tuple[str, str, str, str]] = []
        self._cleanup()

    @property
    def log_dir(self) -> Path | None:
        """录包、重建子进程的日志目录(W00c6g:站点经 ``proc_log`` 看尾巴);编排没有就是 None。"""
        d = getattr(self.orch, "log_dir", None)
        return None if d is None else Path(d)

    def _cleanup(self) -> None:
        """起来时收拾:攒到一半的图(``.building``)扔掉;没打 ``.done`` 的包是上次录到一半进程没了,
        补上 ``.done``(它已经录不下去了,该传的照传)。"""
        shutil.rmtree(self.maps_out / ".building", ignore_errors=True)
        if self.bags_root.is_dir():
            for b in sorted(self.bags_root.iterdir()):
                if b.is_dir() and not (b / DONE).exists():
                    (b / DONE).touch()
                # 边走边建的没收尾完(代理重启了):接着收尾。同一时刻只会有一趟;真有几个,前面的
                # 交给调用方报「没建成」(``lost``)。
                try:
                    t = json.loads((b / LIVE).read_text("utf-8"))
                    got = (b.name, str(t["map_id"]), str(t["version"]))
                    task = str(t.get("task_id", ""))
                    pack = "site" if t.get("pack") == "site" else "robot"
                except (OSError, ValueError, KeyError, TypeError, AttributeError):
                    continue
                if self.pending is not None:
                    self.lost.append((*self.pending, self.pending_task))
                    (self.bags_root / self.pending[0] / LIVE).unlink(missing_ok=True)
                    self.held.discard(self.pending[0])
                self.pending, self.pending_task, self.pending_pack = got, task, pack
                self.held.add(b.name)

    def bag_settled(self, run: Path) -> bool:
        if not (run / DONE).is_file() or run.name in self.held:
            return False
        if (run / BUILT).is_file() or self.pressure():
            return True
        age_days = (time.time() - (run / DONE).stat().st_mtime) / 86400
        return age_days >= BAG_KEEP_DAYS

    async def start(self, name: str, target: tuple[str, str] | None = None,
                    task_id: str = "", pack: str = "robot") -> None:
        """开录。给了 ``target``(地图号, 版本)就同时在线建这一版(W09c2 边走边建);``task_id`` 是开录
        那条命令的号 —— 这一版建好、没建成的事件都带它(站点按它认是哪一次,外审阻断 3)。
        ``pack="site"``(W75):关键帧边走边存进发件箱传给站点,走完在站点主机上打包。"""
        if pack == "site" and (target is None or self.kf_root is None):
            pack = "robot"
        if self.recording:
            raise MappingError(f"正在录 {self.last_bag},先停")
        if self.pending is not None:
            raise MappingError(f"上一趟边走边建的 {self.pending[1]}:{self.pending[2]} 还在打包")
        full = f"{name}-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}"
        if (self.bags_root / full).exists():
            raise MappingError(f"{full} 此包已存在,过一秒再来")
        if target is not None:
            if (self.maps_out / target[0] / target[1]).exists():
                raise MappingError(f"{target[0]}:{target[1]} 机器人上已有一份在传了,换个版本号")
            if pack == "site":
                kd = self._kf_dir(*target)
                shutil.rmtree(kd, ignore_errors=True)
                bag = Path(await self.orch.start_record(full, live_map_id=target[0],
                                                        keyframes_dir=kd))
            else:
                bag = Path(await self.orch.start_record(full, live_map_id=target[0]))
            try:
                mark = {"map_id": target[0], "version": target[1], "task_id": task_id}
                (bag / LIVE).write_text(json.dumps(mark | ({"pack": "site"} if pack == "site"
                                                           else {})), encoding="utf-8")
            except BaseException:
                # 记不下恢复标记(盘满、只读重挂):已经起了的录包、在线建图收掉再报(外审阻断 1)
                try:
                    await self.orch.stop_record()
                except Exception:
                    log.exception("记不下恢复标记之后停录也没成")
                raise
        else:
            await self.orch.start_record(full)
        self.recording = True
        self.last_bag = full
        self.live = target
        self.live_task = task_id
        self.live_pack = pack

    async def stop(self) -> None:
        """停录。边走边建的:记下待打包(:meth:`finish`,调用方丢到后台),包先占住(打包要读它)。"""
        if not self.recording:
            raise MappingError("现在未在录包")
        # 编排停录**先回闲着再报**其中一个停止的错(录包、在线建图都停过了):这边不管报不报错都按
        # 「停了」收 —— 不然上层「在录」、下层「闲着」,之后停不了也开不了(外审复查阻断)。边走边建的
        # 照样记待打包,错再往外报。
        err: BaseException | None = None
        try:
            bag = Path(await self.orch.stop_record())
        except Exception as exc:  # noqa: BLE001 - 什么错都先按「停了」收,再原样往外报
            err = exc
            bag = self.bags_root / self.last_bag
        self.recording = False
        live, self.live = self.live, None
        if err is not None and not bag.is_dir():
            raise err
        (bag / DONE).touch()                      # 录完了:之后才算安定,传完即删
        # 先打完成标记再记待打包(内审应修 3:打标记炸了,待打包就永远挂着、之后每次开录都拒)
        if live is not None:
            with self.lock:
                self.held.add(bag.name)
            self.pending = (bag.name, *live)
            self.pending_task = self.live_task
            self.pending_pack = self.live_pack
        if err is not None:
            raise err

    def preview(self, since: int) -> dict[str, Any]:
        """建图预览(W09f,在线程里调):正在边走边建、或停了还没打包完的这一版的最新快照。没在边走边建
        回 ``{"live": False}``(手机退回录包轨迹);还没第一张 ``seq`` 是 0;``seq`` 比 ``since`` 新才带
        PNG(base64),说明(位姿、轨迹……)每次都给。``age_s`` 是快照多久没更新了(狗自己的钟比)。"""
        # 在线程里跑:事件循环那边随时可能停录、清掉这几个 —— 先各取一份再判(内审应修 6)
        recording, live, pending = self.recording, self.live, self.pending
        if recording and live is not None:
            map_id, version = live
        elif pending is not None:
            _, map_id, version = pending
        else:
            return {"live": False}
        out: dict[str, Any] = {"live": True, "map_id": map_id, "version": version, "seq": 0,
                               "recording": recording,
                               "preview_error": str(getattr(self.orch, "preview_error", ""))}
        try:
            doc = json.loads((Path(self.orch.preview_dir(map_id)) / PREVIEW_FILE)
                             .read_text("utf-8"))
        except (OSError, ValueError):
            return out
        seq = doc.get("seq") if isinstance(doc, dict) else None
        if isinstance(seq, bool) or not isinstance(seq, int):
            return out
        out |= {k: doc.get(k) for k in PREVIEW_FIELDS} | {"seq": seq}
        with contextlib.suppress(KeyError, TypeError, ValueError):
            out["age_s"] = round(max(0.0, time.time() - float(doc["written_at"])), 1)
        png = doc.get("png")
        if seq > since and isinstance(png, str):
            if len(png) > PREVIEW_PNG_MAX_B64:
                out["too_big"] = True
            else:
                out["png"] = png
                if len(json.dumps(out, ensure_ascii=False)) > PREVIEW_MAX_BYTES:
                    del out["png"]
                    out["too_big"] = True
        return out

    def preview_alive(self) -> bool:
        """正在边走边建时预览进程还在不在(**在事件循环里调**:进程表只在那边动)。"""
        f = getattr(self.orch, "preview_running", None)
        return bool(f()) if callable(f) else True

    async def shutdown(self) -> None:
        """代理收尾:正在录就好好停下(录包写完索引、在线建图 SIGINT 存盘),待打包的重启后接着做。"""
        if self.recording:
            await self.stop()

    def _kf_dir(self, map_id: str, version: str) -> Path:
        assert self.kf_root is not None
        return self.kf_root / map_id / version

    async def finish(self) -> tuple[MapRef | None, str]:
        """把边走边建的这一版收尾:先打包在线建好的(``live``);不成(MOLA 半路没了、存下的不齐……)
        就退回在录包上从头建(``bag``)。回(图, 哪种)。站点打包的(W75)写好关键帧清单交给站点,
        回 ``(None, "site")``;关键帧不全就退回在机器人上打包。"""
        assert self.pending is not None
        bag, map_id, version = self.pending
        src = self.bags_root / bag
        out = self.maps_out / map_id / version
        site = self.pending_pack == "site" and self.kf_root is not None
        self.last_fallback = ""
        try:
            if site:
                kd = self._kf_dir(map_id, version)
                try:
                    await asyncio.to_thread(self._handoff, kd, src, map_id, version)
                    return None, "site"
                except MappingError as exc:
                    self.last_fallback = str(exc)[:300]
                    log.warning("%s:%s 交不了站点打包(%s),在机器人上打包", map_id, version, exc)
                    await asyncio.to_thread(self._abandon_kf, kd, map_id, version,
                                            self.last_fallback)
            if out.exists():
                raise MappingError(f"{map_id}:{version} 机器人上已有一份在传了,换个版本号")
            try:
                if site:
                    # 外审 W75-1 #1:交不了站点 = 边走边存的关键帧不齐;拿它打包照样缺一块 ——
                    # 直接从录包重建
                    raise MappingError(self.last_fallback or "关键帧不齐")
                made = Path(await self.orch.package(src, map_id))
                mode = "live"
            except Exception as exc:  # noqa: BLE001 - 在线那份打不成:退回从录包建,原因记着
                self.last_fallback = "; ".join(x for x in (
                    self.last_fallback, f"{type(exc).__name__}: {exc}") if x)[:300]
                log.warning("边走边建的 %s:%s 打包没成(%s),退回从录包建", map_id, version,
                            self.last_fallback)
                made, mode = Path(await self.orch.rebuild(src, map_id)), "bag"
            ref = await asyncio.to_thread(self._settle, made, map_id, version, out)
            (src / BUILT).touch()
            return ref, mode
        finally:
            self.pending = None
            self.pending_task = ""
            self.pending_pack = "robot"
            (src / LIVE).unlink(missing_ok=True)
            with self.lock:
                self.held.discard(bag)

    def _handoff(self, kd: Path, bag: Path, map_id: str, version: str) -> None:
        """站点打包(W75):预览进程收尾了(有 ``live.json``)才交;录包里的 RTK 解一起带上;最后写清单
        (每个文件的大小、sha256)—— 发件箱最后传它,站点收齐核对完出图。"""
        if not (kd / KF_LIVE).is_file():
            raise MappingError("边走边存的关键帧没收尾(预览进程没正常停?)")
        _check_live(kd / KF_LIVE, bag / DONE)
        rtk = bag / "rtk.jsonl"
        if rtk.is_file():
            shutil.copyfile(rtk, kd / ".rtk.jsonl.tmp")
            os.replace(kd / ".rtk.jsonl.tmp", kd / "rtk.jsonl")
        files = []
        for p in sorted(kd.rglob("*")):
            rel = p.relative_to(kd).as_posix()
            if p.is_file() and rel != KF_MANIFEST and kf_classify(rel) is not None:
                files.append({"name": rel, "size": p.stat().st_size, "sha256": _sha256(p)})
        tmp = kd / f".{KF_MANIFEST}.tmp"
        tmp.write_text(json.dumps({"map_id": map_id, "version": version, "files": files},
                                  ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, kd / KF_MANIFEST)
        log.info("%s:%s 的关键帧交给站点打包(%d 个文件)", map_id, version, len(files))

    @staticmethod
    def _abandon_kf(kd: Path, map_id: str, version: str, reason: str) -> None:
        """外审 W75-1 #4:交不了站点的关键帧作废 —— 删掉不再传,只留一份作废清单:有清单这一趟就算写完,
        传上去、站点确认后发件箱删掉;站点收到作废清单把收了一半的删掉。"""
        try:
            for p in sorted(kd.iterdir()):
                if p.name != KF_MANIFEST:
                    shutil.rmtree(p) if p.is_dir() else p.unlink()
            tmp = kd / f".{KF_MANIFEST}.tmp"
            tmp.write_text(json.dumps({"map_id": map_id, "version": version, "files": [],
                                       "abandoned": True, "reason": reason[:300]},
                                      ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, kd / KF_MANIFEST)
        except OSError:
            log.exception("%s:%s 作废关键帧没办成", map_id, version)

    def _settle(self, made: Path, map_id: str, version: str, out: Path) -> MapRef:
        """建出来的文件挪进发件箱、放进本地库(出错只记一笔,激活时从站点下)、最后写清单。"""
        missing = [n for n in GEOMETRY_FILES if not (made / n).is_file()]
        if missing:
            raise MappingError(f"重建已完成,缺 {', '.join(missing)}")
        # 先在点开头的目录里攒齐(上传器不看点开头的路径),再整个挪过去。
        tmp = self.maps_out / ".building" / f"{map_id}@{version}"
        shutil.rmtree(tmp, ignore_errors=True)
        tmp.mkdir(parents=True)
        files = []
        optional = [n for n in OPTIONAL_FILES if (made / n).is_file()]   # W09e:geo.json 有才收
        for n in (*GEOMETRY_FILES, *optional):
            shutil.move(made / n, tmp / n)                # 同一块盘上就是改名
            files.append(MapFile(name=n, size=(tmp / n).stat().st_size,
                                 sha256=_sha256(tmp / n)))
        ref = MapRef(map_id=map_id, version=version, files=tuple(files))
        try:
            self.last_rays = str(json.loads((tmp / "build.json").read_text("utf-8"))
                                 ["grid"]["rays"])[:200]
        except (OSError, ValueError, KeyError, TypeError):
            self.last_rays = ""
        out.parent.mkdir(parents=True, exist_ok=True)
        os.replace(tmp, out)
        # 在写清单**之前**放进本地库:有了清单发件箱就会传、传完就删。
        if self.keeper is not None:
            try:
                self.keeper.adopt(out, ref)
            except Exception:
                log.warning("建好的 %s:%s 放不进本地库(激活时从站点下)", map_id, version,
                            exc_info=True)
        # 文件都就位了才写清单:站点(和发件箱)见到清单才算这张图完整。
        m = out / (MANIFEST + ".tmp")
        m.write_text(json.dumps(ref.to_wire(), ensure_ascii=False), encoding="utf-8")
        os.replace(m, out / MANIFEST)
        return ref

    async def build(self, bag: str, map_id: str, version: str) -> MapRef:
        src = self.bags_root / bag
        with self.lock:                                   # 先占住,再查在不在:发件箱删包也拿这把锁
            if not (src / DONE).is_file():
                raise MappingError(f"包 {bag} 不在机器人上了(传完、放够天数就删了)或尚未录完")
            self.held.add(bag)
        out = self.maps_out / map_id / version
        try:
            if out.exists():
                raise MappingError(f"{map_id}:{version} 机器人上已有一份在传了,换个版本号")
            made = Path(await self.orch.rebuild(src, map_id))   # 编排起建图前清掉上一次的产物
            # 挪文件、算几百 MB 的哈希放线程里:不卡住代理(心跳、命令)。
            ref = await asyncio.to_thread(self._settle, made, map_id, version, out)
            (src / BUILT).touch()                         # 重建过了:这个包传完就可以删
            return ref
        finally:
            with self.lock:
                self.held.discard(bag)
