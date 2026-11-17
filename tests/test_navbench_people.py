"""外审 11-17 I5:仿真里会让路的人不能「一看见就瞬间站住、永远不往机器人身上走」(成功率虚高)。
像真人:看见了过一会儿才反应(:data:`PERSON_REACT_S`),按有限的减速度刹住、按有限的加速度起步;
不再按真值拦着不让人走进机器人。另有不让路的对照(``NAVPATROL_NO_YIELD``)。"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_P = Path(__file__).resolve().parents[1] / "tools" / "navbench_patrol.py"
_spec = importlib.util.spec_from_file_location("navbench_patrol", _P)
nb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(nb)

T = 0.05


def _run(f, seen, sees, v, secs):
    for _ in range(round(secs / T)):
        f, seen = nb._person_pace(f, seen, sees, v, T)
    return f, seen


def test_外审1117_I5_看见了反应之前照常走():
    f, seen = _run(1.0, 0.0, True, 1.2, nb.PERSON_REACT_S - 2 * T)
    assert f == 1.0


def test_外审1117_I5_反应过来以后按有限减速度刹_不是瞬间站住():
    f, seen = _run(1.0, 0.0, True, 1.2, nb.PERSON_REACT_S + 2 * T)
    assert 0.0 < f < 1.0, "刚开始刹,还没停"
    stop_s = 1.2 / nb.PERSON_DECEL_MPS2
    f, _ = _run(f, seen, True, 1.2, stop_s)
    assert f == 0.0


def test_外审1117_I5_走开了按有限加速度起步_反应计时清零():
    f, seen = _run(0.0, 3.0, False, 1.2, 2 * T)
    assert seen == 0.0 and 0.0 < f < 0.2
    f, _ = _run(f, seen, False, 1.2, 1.2 / nb.PERSON_ACCEL_MPS2)
    assert f == 1.0


def test_外审1117_I5_看得比刹车距离远():
    """反应时间里走的 + 刹车距离,在看得见的范围以内(不然看见了也停不住)。"""
    v = 1.4
    assert v * nb.PERSON_REACT_S + v * v / (2 * nb.PERSON_DECEL_MPS2) < nb.PERSON_LOOK_M


@pytest.mark.parametrize("val,want", [("", True), ("1", False)])
def test_外审1117_I5_不让路的对照开关(monkeypatch, val, want):
    monkeypatch.setenv("NAVPATROL_NO_YIELD", val)
    assert nb._yields({"yields": True}) is want
    assert nb._yields({}) is False
