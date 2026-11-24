"""W80:机型档案(:mod:`nexwar_agent.robot_models`,用户 11-25「解耦,加新机型只要最小改动」)、
``--robot-model``、``--mapping-orchestrator``(外部建图编排)。

D1 Edu 的档案跟着 ``nexwar-d1edu`` 仓库走(装机脚本放进 ``/etc/nexwar/robot-models``);这里用一份
同样内容的拿来测。"""

from __future__ import annotations

import asyncio
import json
import sys
import types

import pytest

from nexwar_adapter_d1max.hal import ADAPTER_ID, D1MaxHal
from nexwar_agent import main as agent_main
from nexwar_agent import robot_models as RM
from nexwar_contract.hal import HalUnsupported
from nexwar_contract.registration import Registration

REG = Registration(site_id="penang-1", robot_id="NEXWAR-SIM", credential_fingerprint="sha256:x",
                   issued_at=0, expires_at=10**13)

#: 跟 nexwar-d1edu/deploy/robot-models/d1edu.json 一样。
D1EDU = {
    "schema": 1, "id": "d1edu", "name": "D1 Edu", "adapter_id": "nexwar-d1edu/0.1.0",
    "driver": "sidecar", "cameras": ["front"], "light": False,
    "units": {"mps_per_unit": 1.0, "radps_per_unit": 1.5, "deadband": 0.05,
              "lateral_mps_per_unit": 1.0},
    "mapping_orchestrator": "nexwar_d1edu.slam2d:orchestrator",
    "services": ["nexwar_d1edu_sidecar", "nexwar_d1edu_lidar", "nexwar_d1edu_tf",
                 "nexwar_d1edu_loc", "nexwar_d1edu_obs", "nexwar_nav2"]}


@pytest.fixture(autouse=True)
def _models(tmp_path, monkeypatch):
    """档案目录换成临时的(不读台式机上的 /etc),放一份 D1 Edu。"""
    d = tmp_path / "robot-models"
    d.mkdir()
    (d / "d1edu.json").write_text(json.dumps(D1EDU), encoding="utf-8")
    monkeypatch.setattr(RM, "MODEL_DIRS", (d,))
    monkeypatch.delenv("NEXWAR_ROBOT_MODELS_DIR", raising=False)
    return d


def _args(tmp_path, *extra, outbox=False):
    reg = tmp_path / "registration.json"
    REG.save(reg)
    where = ["--outbox", str(tmp_path / "outbox")] if outbox else \
        ["--runs-root", str(tmp_path / "runs")]
    return agent_main.parse_args([
        "--transport", "memory://", "--hal", "sim", "--registration", str(reg),
        "--store-dir", str(tmp_path / "store"), *where,
        "--map", "estate-1:7", "--home", "0,0,0", "--period", "0.01", *extra])


def test_机型参数_缺省d1max_d1edu只配真机适配器(tmp_path):
    assert _args(tmp_path).robot_model == "d1max"
    a = _args(tmp_path, "--hal", "d1max", "--robot-model", "d1edu")
    assert a.robot_model == "d1edu"
    with pytest.raises(SystemExit):
        _args(tmp_path, "--robot-model", "d1edu")          # sim 不收
    with pytest.raises(SystemExit):
        _args(tmp_path, "--hal", "d1max", "--robot-model", "x2")


def test_d1edu_没有机身灯_报给站点的适配器号认得出(tmp_path):
    edu = agent_main.make_hal(_args(tmp_path, "--hal", "d1max", "--robot-model", "d1edu"))
    assert isinstance(edu, D1MaxHal)
    caps = edu.hal_capabilities()
    assert caps.actuators["light"] is False
    assert edu.adapter_id == "nexwar-d1edu/0.1.0"
    with pytest.raises(HalUnsupported):
        asyncio.run(edu.light("both", True))
    mx = agent_main.make_hal(_args(tmp_path, "--hal", "d1max"))
    assert mx.hal_capabilities().actuators["light"] is True and mx.adapter_id == ADAPTER_ID
    assert D1MaxHal.adapter_id == ADAPTER_ID, "改实例的,不动类上的"


def test_外部编排_要配mapping_格式要对(tmp_path):
    with pytest.raises(SystemExit):
        _args(tmp_path, "--mapping-orchestrator", "m:f", outbox=True)
    with pytest.raises(SystemExit):
        _args(tmp_path, "--mapping", "--mapping-orchestrator", "no colon", outbox=True)
    a = _args(tmp_path, "--mapping", "--mapping-orchestrator", "pkg.mod:make", outbox=True)
    assert a.mapping_orchestrator == "pkg.mod:make"


def test_外部编排_找不到就不起():
    with pytest.raises(SystemExit, match="找不到"):
        agent_main.load_orchestrator("nexwar_no_such_mod:make")
    with pytest.raises(SystemExit, match="找不到"):
        agent_main.load_orchestrator("os:no_such_fn")


def test_外部编排_装进建图服务(tmp_path, monkeypatch):
    got = {}

    class Orch:
        preview_error = ""

        def __init__(self, **kw):
            got.update(kw)
            self.log_dir = tmp_path / "logs"

    mod = types.ModuleType("w80_fake_orch")
    mod.make = lambda **kw: Orch(**kw)
    monkeypatch.setitem(sys.modules, "w80_fake_orch", mod)
    a = agent_main.build(_args(tmp_path, "--mapping", "--mapping-orchestrator",
                               "w80_fake_orch:make", outbox=True))
    try:
        assert isinstance(a.runtime.mapper.orch, Orch)
        store = tmp_path / "store"
        assert got == {"bags_dir": store / "mapbags", "work": store / "mapwork", "store": store}
    finally:
        a.stop()


def test_d1edu只有前摄像头_d1max照旧前后两路(tmp_path):
    """用户 11-25:D1 Edu 只有一个前摄像头。上报的相机、录像、到点拍照都只有 front。"""
    from nexwar_agent.video_push import rtsp_source, source_cameras
    edu = _args(tmp_path, "--hal", "d1max", "--robot-model", "d1edu", "--record", "auto")
    mx = _args(tmp_path, "--hal", "d1max", "--record", "auto")
    assert agent_main.builtin_cameras(edu) == ("front",)
    assert agent_main.builtin_cameras(mx) == ("front", "back")
    assert agent_main.record_cameras(edu) == ["front"]
    assert agent_main.record_cameras(mx) == ["front", "back"]
    with pytest.raises(SystemExit):
        agent_main.record_cameras(_args(tmp_path, "--hal", "d1max", "--robot-model", "d1edu",
                                        "--record", "back"))
    src = rtsp_source("192.168.168.168", {"front": {"url": "rtsp://192.168.168.168:8554/test",
                                                    "record": True}},
                      agent_main.builtin_cameras(edu))
    assert source_cameras(src) == ("front",)
    assert "rtsp://192.168.168.168:8554/test" in src("front"), "cameras.json 里的地址顶掉缺省的"
    assert source_cameras(rtsp_source("127.0.0.1")) == ("front", "back")


# ---------------------------------------------------------------- 机型档案


def test_内置的d1max_跟拆档案以前写死的一样():
    from nexwar_agent import ops as O
    from nexwar_contract.video import STANDARD_CAMERAS
    m = RM.get("d1max")
    assert m is RM.D1MAX and m.driver == "sidecar" and m.light is True and m.adapter_id is None
    assert m.cameras == tuple(STANDARD_CAMERAS)
    assert dict(m.units) == {k: v for k, v in agent_main.NEXWAR_DEFAULTS.items()
                             if k in RM.UNIT_KEYS}
    assert dict(m.unit_ranges) == agent_main.UNIT_RANGES
    assert m.all_services == O.OUR_UNITS, "站点上的服务名单一个不多一个不少、顺序也一样"
    assert m.robot_radius_m is None and m.mapping_orchestrator is None


def test_d1edu档案_换算缺省值从档案来_命令行给了以命令行为准(tmp_path):
    a = _args(tmp_path, "--hal", "d1max", "--robot-model", "d1edu")
    assert (a.deadband, a.mps_per_unit, a.lateral_mps_per_unit) == (0.05, 1.0, 1.0)
    assert a.max_fraction == agent_main.NEXWAR_DEFAULTS["max_fraction"], "档案没写的用缺省"
    b = _args(tmp_path, "--hal", "d1max", "--robot-model", "d1edu", "--deadband", "0.1")
    assert b.deadband == 0.1
    mx = _args(tmp_path, "--hal", "d1max")
    assert mx.deadband == 0.2


def test_d1edu档案_建图编排缺省从档案来(tmp_path):
    a = _args(tmp_path, "--hal", "d1max", "--robot-model", "d1edu", "--mapping", outbox=True)
    assert a.mapping_orchestrator == "nexwar_d1edu.slam2d:orchestrator"
    b = _args(tmp_path, "--hal", "d1max", "--robot-model", "d1edu", outbox=True)
    assert b.mapping_orchestrator is None, "没开建图不装编排"
    c = _args(tmp_path, "--hal", "d1max", "--mapping", outbox=True)
    assert c.mapping_orchestrator is None, "D1 Max 用自己的建图"


def test_没有的机型_不起_说清楚档案放哪(tmp_path, capsys):
    with pytest.raises(SystemExit):
        _args(tmp_path, "--hal", "d1max", "--robot-model", "go2")
    err = capsys.readouterr().err
    assert "go2" in err and "robot-models" in err and "d1edu" in err


def _doc(**kw):
    return {"schema": 1, "id": "ultra", "name": "D1 Ultra", **kw}


@pytest.mark.parametrize("doc, why", [
    ([], "JSON 对象"),
    (_doc(schema=2), "schema"),
    (_doc(id="Ultra"), "id"),
    (_doc(name=""), "name"),
    (_doc(camras=["front"]), "camras"),
    (_doc(cameras=["front", "top"]), "cameras"),
    (_doc(cameras=[]), "cameras"),
    (_doc(light="no"), "light"),
    (_doc(units={"speed": 1}), "speed"),
    (_doc(units={"mps_per_unit": "1"}), "units.mps_per_unit"),
    (_doc(units={"mps_per_unit": 3.0}), "unit_ranges"),
    (_doc(unit_ranges={"mps_per_unit": [2, 1]}), "下限"),
    (_doc(driver="unitree"), "driver"),
    (_doc(services=["sshd"]), "services"),
    (_doc(robot_radius_m=5), "robot_radius_m"),
    (_doc(mapping_orchestrator="x"), "mapping_orchestrator"),
])
def test_档案写错了_说清楚哪一项(doc, why):
    with pytest.raises(RM.ModelError, match=why):
        RM.parse(doc, "ultra.json")


def test_档案目录_文件名要跟id一样_编号不能重(_models):
    (_models / "x.json").write_text(json.dumps(_doc()), encoding="utf-8")
    with pytest.raises(RM.ModelError, match="文件名"):
        RM.available()
    (_models / "x.json").unlink()
    (_models / "d1max.json").write_text(json.dumps(_doc(id="d1max")), encoding="utf-8")
    with pytest.raises(RM.ModelError, match="已经有了"):
        RM.available()
    (_models / "d1max.json").write_text("{坏", encoding="utf-8")
    with pytest.raises(RM.ModelError, match="读不了"):
        RM.available()


def test_加一个同系列的新机型_只放一份档案(tmp_path, monkeypatch, capsys):
    """用户 11-25:D1 Ultra、D1 Max Pro 这种 = 放一份 JSON,代码不动。"""
    d = tmp_path / "more"
    d.mkdir()
    (d / "ultra.json").write_text(json.dumps(_doc(
        cameras=["front", "back", "thermal"], adapter_id="nexwar-d1ultra/0.1.0",
        units={"mps_per_unit": 1.2}, robot_radius_m=0.45,
        services=["nexwar_localizer", "nexwar_sidecar"])), encoding="utf-8")
    monkeypatch.setenv("NEXWAR_ROBOT_MODELS_DIR", str(d))
    a = _args(tmp_path, "--hal", "d1max", "--robot-model", "ultra", "--record", "auto")
    assert a.mps_per_unit == 1.2 and a.robot_radius == 0.45
    assert agent_main.builtin_cameras(a) == ("front", "back", "thermal")
    assert agent_main.record_cameras(a) == ["front", "back", "thermal"]
    hal = agent_main.make_hal(a)
    assert hal.adapter_id == "nexwar-d1ultra/0.1.0"
    assert agent_main.robot_model(a).all_services == (
        "nexwar_agent", "nexwar_localizer", "nexwar_sidecar", "nexwar_bind")
    capsys.readouterr()
    with pytest.raises(SystemExit):
        _args(tmp_path, "--hal", "d1max", "--robot-model", "ultra", "--mps-per-unit", "1.6")
    assert "D1 Ultra 的速度换算系数不在" in capsys.readouterr().err


def test_别家机器人_品牌包自己的驱动(tmp_path, monkeypatch):
    """driver = 模块:函数:代理调它拿 HAL;旁路协议的换算范围不管它(换算是它自己的事)。"""
    got = {}

    class FakeHal:
        adapter_id = "acme-go/1"

    def make(**kw):
        got.update(kw)
        return FakeHal()
    mod = types.ModuleType("w80_fake_brand")
    mod.make = make
    monkeypatch.setitem(sys.modules, "w80_fake_brand", mod)
    d = tmp_path / "brand"
    d.mkdir()
    (d / "acme.json").write_text(json.dumps({
        "schema": 1, "id": "acme", "name": "Acme Go", "driver": "w80_fake_brand:make",
        "cameras": ["front"], "light": False}), encoding="utf-8")
    monkeypatch.setenv("NEXWAR_ROBOT_MODELS_DIR", str(d))
    a = _args(tmp_path, "--hal", "d1max", "--robot-model", "acme", "--mps-per-unit", "3")
    hal = agent_main.make_hal(a, payload="p")
    assert isinstance(hal, FakeHal)
    assert got["model"].id == "acme" and got["args"] is a and got["payload"] == "p"
    assert callable(got["now_ms"])
    (d / "acme.json").write_text(json.dumps({
        "schema": 1, "id": "acme", "name": "Acme Go", "driver": "w80_no_such_brand:make"}),
        encoding="utf-8")
    with pytest.raises(SystemExit, match="driver"):
        agent_main.make_hal(_args(tmp_path, "--hal", "d1max", "--robot-model", "acme"))


def test_站点上的服务名单跟着机型(tmp_path):
    from nexwar_agent import ops as O
    from nexwar_contract.privops import SimOps
    m = RM.get("d1edu")
    desk = O.OpsDesk(robot_id="E", priv=SimOps(), data_root=tmp_path / "data", busy=lambda: "",
                     run=lambda argv, t: (0, ""), units=m.all_services)
    k = desk.kinds()
    assert k["ops_restart"]["units"] == ["nexwar_agent", "nexwar_d1edu_sidecar",
                                         "nexwar_d1edu_lidar", "nexwar_d1edu_tf",
                                         "nexwar_d1edu_loc", "nexwar_d1edu_obs", "nexwar_nav2",
                                         "nexwar_bind"]
    assert "nexwar_persons" not in k["ops_journal"]["units"], "D1 Edu 没有的不列"
    assert "ssh" in k["ops_journal"]["units"]
    assert [s["unit"] for s in desk.diag()["services"]] == list(m.all_services)
