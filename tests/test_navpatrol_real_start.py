"""整趟巡逻仿真用例(tools/navpatrol_real.py):人不许一开始就生成在机器人身上(台式机 11-18:
K1 大堂 35、53 号人生在车身里、站着不动,机器人一退就记成撞人)。故意在车头前起步的不动。"""

from __future__ import annotations

import importlib.util
import math
import random
from pathlib import Path

_P = Path(__file__).resolve().parents[1] / "tools" / "navpatrol_real.py"
_spec = importlib.util.spec_from_file_location("navpatrol_real", _P)
npr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(npr)


def _gap(start, p) -> float:
    """人(中心 p,半边 0.225)离机器人起点车身(半长 0.465、半宽 0.24)的净距。"""
    c, s = math.cos(start[2]), math.sin(start[2])
    dx, dy = p[0] - start[0], p[1] - start[1]
    lx, ly = c * dx + s * dy, -s * dx + c * dy
    return math.hypot(max(0.0, abs(lx) - 0.465), max(0.0, abs(ly) - 0.24)) - 0.225


def _case(fam, seed):
    rng = random.Random(f"{fam.__name__}/{seed}")
    for _ in range(100):
        try:
            return fam(rng, seed)
        except ValueError:
            continue
    raise AssertionError("出不来")


def test_大堂35_53_人起步不叠在车身上():
    for seed in (35, 53):
        c = _case(npr.lobby, seed)
        st = c["start"]
        for a in c["actors"]:
            assert _gap(st, a["path"][0]) >= npr.START_ACTOR_CLEAR_M - 1e-9, (seed, a["name"])


def test_十类环境前20个种子_人起步都不叠在车身上():
    for fam in npr.FAMILIES:
        for seed in range(20):
            c = _case(fam, seed)
            for a in c["actors"]:
                assert _gap(c["start"], a["path"][0]) >= npr.START_ACTOR_CLEAR_M - 1e-9, \
                    (fam.__name__, seed, a["name"])


def test_医院护士故意在车头前1米起步_不动她():
    c = _case(npr.hospital, 0)
    nurse = next(a for a in c["actors"] if a["name"] == "nurse1")
    assert nurse["path"][0] == [-15.489864970699283, -9.0]
