"""机型档案(W80 解耦,用户 11-25):一台机器人「是什么机型」所有跟机型有关的东西都写在一份档案里,
代理按 ``--robot-model <编号>`` 读,别的代码不认机型。

**加一个新机型**(D1 Ultra、D1 Max Pro、别家的机器人……)= 放一份 JSON 到
``/etc/nexwar/robot-models/<编号>.json``(品牌包的装机脚本放),代理、站点、App 都不用改代码。
见 ``docs/接入新机型.md``。

档案里写:

- ``driver``:怎么开这台机器人。``"sidecar"`` = 走我们的旁路协议(协议 9,TCP;D1 系列、D1 Edu 都是这条,
  别家机器人写一个说这套协议的旁路进程就行);``"模块:函数"`` = 品牌包自己的适配器(函数返回 HAL)。
- ``units``:旁路协议的比例换算缺省值(跟 ``--mps-per-unit`` 这些参数同名,命令行给了以命令行为准);
  ``unit_ranges``:换算系数的合理范围(不在范围里不起,W12);没写用 D1 系列 SDK 低速档的范围。
- ``cameras``:自带哪几路相机(``cameras.json`` 只能改地址、加别的,去不掉自带的)。
- ``light``:有没有机身灯。上装(警灯、警笛、喇叭……)不在这里,在 ``payload.json``(W79 两种交付)。
- ``services``:这个机型在机器人上跑的我们的服务(站点上看状态、看日志、重启);``nexwar_agent``、
  ``nexwar_bind`` 每个机型都有,不用写。
- ``robot_radius_m``、``mapping_orchestrator``:缺省的机身半径、建图编排(命令行给了以命令行为准)。
- ``adapter_id``:报给站点的适配器号(站点、手机据此认机型);不写用驱动自己的。

内置的只有 D1 Max(主产品);别的机型的档案跟着各自的品牌包走(D1 Edu 的在 ``nexwar-d1edu`` 仓库)。
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

#: 档案格式版本。
SCHEMA = 1
#: 机型档案放这几个目录(前面的先读);``NEXWAR_ROBOT_MODELS_DIR`` 可以再加一个(冒号隔开几个)。
MODEL_DIRS = (Path("/etc/nexwar/robot-models"),)
#: 每个机型都有的服务(代理、配网)。
COMMON_SERVICES = ("nexwar_agent", "nexwar_bind")
#: 旁路协议的比例换算能写进档案的那几个(跟代理命令行参数同名)。
UNIT_KEYS = ("mps_per_unit", "radps_per_unit", "deadband", "max_fraction", "stopped_eps",
             "fwd_offset", "lateral_mps_per_unit")
#: D1 系列 SDK 低速档的合理范围(W12 外审阻断):档案没写 ``unit_ranges`` 就用它。
SIDECAR_UNIT_RANGES = {"mps_per_unit": (0.7, 1.5), "radps_per_unit": (1.1, 2.0)}

_ID = re.compile(r"[a-z][a-z0-9_-]{1,31}")
_SPEC = re.compile(r"[A-Za-z_][\w.]*:[A-Za-z_]\w*")
_UNIT = re.compile(r"nexwar_[a-z0-9_]{1,40}")
_KEYS = frozenset({"schema", "id", "name", "driver", "adapter_id", "cameras", "light", "units",
                   "unit_ranges", "services", "robot_radius_m", "mapping_orchestrator"})


class ModelError(ValueError):
    """档案写错了(说清楚哪一份、哪一项)。"""


@dataclass(frozen=True)
class RobotModel:
    id: str
    name: str
    driver: str = "sidecar"
    adapter_id: str | None = None
    cameras: tuple[str, ...] = ("front", "back")
    light: bool = True
    units: Mapping[str, float] = field(default_factory=dict)
    unit_ranges: Mapping[str, tuple[float, float]] = field(
        default_factory=lambda: dict(SIDECAR_UNIT_RANGES))
    services: tuple[str, ...] = ()
    robot_radius_m: float | None = None
    mapping_orchestrator: str | None = None
    source: str = "内置"

    @property
    def all_services(self) -> tuple[str, ...]:
        """站点上能看、能重启的我们的服务:代理在最前、配网在最后(跟老名单一个顺序)。"""
        mid = tuple(u for u in self.services if u not in COMMON_SERVICES)
        return (COMMON_SERVICES[0], *mid, *COMMON_SERVICES[1:])


#: 内置:D1 Max。数都跟拆档案以前代码里写死的一样(测试核)。
D1MAX = RobotModel(
    id="d1max", name="D1 Max",
    units={"mps_per_unit": 1.0, "radps_per_unit": 1.5, "deadband": 0.2, "max_fraction": 0.5,
           "stopped_eps": 0.02, "fwd_offset": 0.0, "lateral_mps_per_unit": 1.0},
    services=("nexwar_localizer", "nexwar_obstacles", "nexwar_persons", "nexwar_lidar_merge",
              "nexwar_nav2", "nexwar_sidecar", "nexwar_zenohd"))
BUILTIN: dict[str, RobotModel] = {D1MAX.id: D1MAX}


def _num(v: Any, what: str) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or v != v or v in (float("inf"),
                                                                              float("-inf")):
        raise ModelError(f"{what} 要是数,收到 {v!r}")
    return float(v)


def parse(doc: Any, source: str = "") -> RobotModel:
    """一份档案(JSON 读出来的)→ :class:`RobotModel`。哪里不对抛 :class:`ModelError`。"""
    where = f"机型档案 {source}" if source else "机型档案"

    def bad(msg: str) -> ModelError:
        return ModelError(f"{where}:{msg}")
    if not isinstance(doc, dict):
        raise bad("要是一个 JSON 对象")
    extra = sorted(set(doc) - _KEYS)
    if extra:
        raise bad(f"不认得 {'、'.join(extra)}(写错了?)")
    if doc.get("schema") != SCHEMA:
        raise bad(f"schema 要是 {SCHEMA},收到 {doc.get('schema')!r}")
    mid = doc.get("id")
    if not isinstance(mid, str) or not _ID.fullmatch(mid):
        raise bad(f"id 要是小写字母开头的 2–32 个字母、数字、-、_,收到 {mid!r}")
    name = doc.get("name")
    if not isinstance(name, str) or not name.strip() or len(name) > 64:
        raise bad("name 要写(给人看的机型名,最多 64 个字)")
    driver = doc.get("driver", "sidecar")
    if not isinstance(driver, str) or (driver != "sidecar" and not _SPEC.fullmatch(driver)):
        raise bad(f"driver 要是 \"sidecar\" 或者 \"模块:函数\",收到 {driver!r}")
    adapter = doc.get("adapter_id")
    if adapter is not None and (not isinstance(adapter, str) or not 0 < len(adapter) <= 64):
        raise bad("adapter_id 要是 1–64 个字")
    from nexwar_contract.video import CAMERAS
    cams = doc.get("cameras", ["front", "back"])
    if not isinstance(cams, list) or not cams or any(c not in CAMERAS for c in cams) \
            or len(set(cams)) != len(cams):
        raise bad(f"cameras 要是 {'、'.join(CAMERAS)} 里的几个(不重复、至少一个),收到 {cams!r}")
    light = doc.get("light", True)
    if not isinstance(light, bool):
        raise bad("light 要是 true / false")
    units_raw = doc.get("units", {})
    if not isinstance(units_raw, dict):
        raise bad("units 要是对象")
    units: dict[str, float] = {}
    for k, v in units_raw.items():
        if k not in UNIT_KEYS:
            raise bad(f"units 里不认得 {k}(只认 {'、'.join(UNIT_KEYS)})")
        units[k] = _num(v, f"{where}:units.{k}")
    ranges_raw = doc.get("unit_ranges", {k: list(v) for k, v in SIDECAR_UNIT_RANGES.items()})
    if not isinstance(ranges_raw, dict):
        raise bad("unit_ranges 要是对象")
    ranges: dict[str, tuple[float, float]] = {}
    for k, v in ranges_raw.items():
        if k not in UNIT_KEYS or not isinstance(v, list) or len(v) != 2:
            raise bad(f"unit_ranges.{k} 要写成 [下限, 上限]")
        lo, hi = _num(v[0], f"{where}:unit_ranges.{k}"), _num(v[1], f"{where}:unit_ranges.{k}")
        if not 0 <= lo < hi:
            raise bad(f"unit_ranges.{k} 下限要小于上限、不是负数")
        ranges[k] = (lo, hi)
        if k in units and not lo <= units[k] <= hi:
            raise bad(f"units.{k} {units[k]:g} 不在自己的 unit_ranges [{lo:g}, {hi:g}] 里")
    services = doc.get("services", [])
    if not isinstance(services, list) or any(not isinstance(u, str) or not _UNIT.fullmatch(u)
                                             for u in services):
        raise bad("services 要是服务名的列表(nexwar_ 开头,小写字母、数字、_)")
    radius = doc.get("robot_radius_m")
    if radius is not None:
        radius = _num(radius, f"{where}:robot_radius_m")
        if not 0.1 <= radius <= 2.0:
            raise bad("robot_radius_m 要在 0.1–2.0 米之间")
    orch = doc.get("mapping_orchestrator")
    if orch is not None and (not isinstance(orch, str) or not _SPEC.fullmatch(orch)):
        raise bad("mapping_orchestrator 要写成 模块:函数")
    return RobotModel(id=mid, name=name.strip(), driver=driver, adapter_id=adapter,
                      cameras=tuple(cams), light=light, units=units, unit_ranges=ranges,
                      services=tuple(dict.fromkeys(services)), robot_radius_m=radius,
                      mapping_orchestrator=orch, source=source or "内置")


def model_dirs() -> list[Path]:
    extra = [Path(p) for p in os.environ.get("NEXWAR_ROBOT_MODELS_DIR", "").split(os.pathsep)
             if p]
    return [*MODEL_DIRS, *extra]


def available(dirs: Iterable[Path] | None = None) -> dict[str, RobotModel]:
    """内置的 + 档案目录里的。编号跟别的重了、文件名跟 id 对不上、写错了 —— 都抛,不挑一个凑合用。"""
    out = dict(BUILTIN)
    for d in model_dirs() if dirs is None else dirs:
        if not d.is_dir():
            continue
        for f in sorted(d.glob("*.json")):
            try:
                doc = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                raise ModelError(f"机型档案 {f} 读不了:{exc}") from exc
            m = parse(doc, str(f))
            if f.stem != m.id:
                raise ModelError(f"机型档案 {f}:文件名要跟 id 一样({m.id}.json)")
            if m.id in out:
                raise ModelError(f"机型档案 {f}:{m.id} 已经有了({out[m.id].source})")
            out[m.id] = m
    return out


def get(model_id: str, dirs: Iterable[Path] | None = None) -> RobotModel:
    models = available(dirs)
    if model_id not in models:
        raise ModelError(f"没有机型 {model_id!r}(有的:{'、'.join(sorted(models))};"
                         f"新机型的档案放 {'、'.join(str(d) for d in model_dirs())})")
    return models[model_id]
