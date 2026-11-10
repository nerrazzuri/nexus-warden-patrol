"""错误码总表覆盖站点的告警种类和派单拒绝代号(日志设计 第 7 条)。"""

from __future__ import annotations

from nexwar_contract import errcodes as ec
from nexwar_site.alerts import LEVEL_OF
from nexwar_site.refusals import CODES


def test_每一种告警都有错误码():
    missing = sorted(k for k in LEVEL_OF if k not in ec.ALERT)
    assert not missing, f"这些告警种类没有错误码,在 errcodes.ALERT 里加:{missing}"


def test_每一个拒绝代号都有错误码():
    missing = sorted(code for code, _rx, _en in CODES if code not in ec.REFUSAL)
    assert not missing, missing
