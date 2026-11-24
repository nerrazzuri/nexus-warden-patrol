"""W80:``--robot-model d1edu``(同一套旁路协议接 D1 Edu)、``--mapping-orchestrator``
(外部建图编排)。"""

from __future__ import annotations

import asyncio
import sys
import types

import pytest

from nexwar_adapter_d1max.hal import ADAPTER_ID, D1MaxHal
from nexwar_agent import main as agent_main
from nexwar_contract.hal import HalUnsupported
from nexwar_contract.registration import Registration

REG = Registration(site_id="penang-1", robot_id="NEXWAR-SIM", credential_fingerprint="sha256:x",
                   issued_at=0, expires_at=10**13)


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


def test_d1edu_没有机身灯_报给站点的适配器号认得出():
    assert agent_main.model_hal_kwargs("d1max") == {}
    edu = D1MaxHal("127.0.0.1", 1, **agent_main.model_hal_kwargs("d1edu"))
    caps = edu.hal_capabilities()
    assert caps.actuators["light"] is False
    assert edu.adapter_id == "nexwar-d1edu/0.1.0"
    with pytest.raises(HalUnsupported):
        asyncio.run(edu.light("both", True))
    mx = D1MaxHal("127.0.0.1", 1)
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
