"""错误码总表(日志设计 第 7 条,用户 11-10:十六进制 0xMMRR)。"""

from __future__ import annotations

import re

from nexwar_contract import errcodes as ec
from nexwar_contract.navcodes import FAIL_CODES


def test_码不重复_名字跟模块前缀对得上_每样都写全():
    nums = [t[0] for t in ec._T]
    assert len(nums) == len(set(nums)), "码重复了"
    names = [t[1] for t in ec._T]
    assert len(names) == len(set(names)), "英文名重复了"
    for c in ec.CODES.values():
        assert 0x0100 <= c.num <= 0xFFFF and c.num & 0xFF, c
        assert c.module in ec.MODULES, c
        assert c.name.split(".")[0] == ec.MODULES[c.module][0], c
        assert re.fullmatch(r"[a-z]+\.[a-z0-9_]+", c.name), c
        assert c.level in ec.LEVELS and c.who in ec.WHO, c
        assert c.zh and c.en, c
        assert bool(c.do_zh) == bool(c.do_en), f"{c.name}:该做什么中英文要都有或都没有"
        assert "狗" not in c.zh + c.do_zh and "dog" not in (c.en + c.do_en).lower(), c


def test_十六进制写法_按名字和码都认得():
    c = ec.get("dispatch.offline")
    assert c is not None and c.hex == "0x0201"
    assert ec.get("0x0201") is c and ec.get(0x0201) is c and ec.get("0X0201") is c
    assert ec.get("nope") is None and ec.get("0xzz") is None and ec.get(None) is None
    assert ec.tag("dispatch.offline") == "0x0201 dispatch.offline"
    assert ec.tag("") == "-" and ec.tag("x.y") == "?x.y"
    assert ec.wire("sched.missed") == {"err": "0x0302", "err_name": "sched.missed"}


def test_告警种类_拒绝代号_日程结果_导航失败码_都有对应的码():
    for table in (ec.ALERT, ec.REFUSAL, ec.SCHEDULE):
        for k, v in table.items():
            assert v in ec.CODES, (k, v)
    for k in FAIL_CODES:
        assert ec.nav(k) in ec.CODES, k
