"""外审 11-14:车身尺寸只在 ``nexwar_contract.footprint`` 定义一次。守卫、感知、仿真、Nav2 配置
各抄一份数字的话,改一处漏一处,仿真和交付就不是同一台车(发布门槛 3)。"""
from __future__ import annotations

import ast
import io
import re
import tokenize
from pathlib import Path

import pytest

from nexwar_contract.footprint import BASE_HALF_LEN, BASE_HALF_WID, BODY_LEN, BODY_WID

ROOT = Path(__file__).resolve().parents[3]
SCAN = ["packages/robot-agent/src", "packages/localizer/src", "packages/contract/src",
        "packages/site-node/src", "src", "tools/nav_stability_bench_dev"]
#: 车身长、宽、半长、半宽、加基础余量的半长、半宽
SIZES = {BODY_LEN, BODY_WID, BODY_LEN / 2, BODY_WID / 2, round(BASE_HALF_LEN, 6),
         round(BASE_HALF_WID, 6)}


def _hits(p: Path) -> list[str]:
    out = []
    src = p.read_text(encoding="utf-8")
    for t in tokenize.generate_tokens(io.StringIO(src).readline):
        if t.type != tokenize.NUMBER:
            continue
        try:
            v = round(float(t.string), 6)
        except ValueError:
            continue
        if v in SIZES:
            out.append(f"{p.relative_to(ROOT)}:{t.start[0]}: {t.line.strip()[:80]}")
    return out


def test_车身尺寸只在footprint里写数字():
    hits = []
    for d in SCAN:
        for p in sorted((ROOT / d).rglob("*.py")):
            if p.name != "footprint.py":
                hits += _hits(p)
    assert not hits, "车身尺寸要从 nexwar_contract.footprint 取:\n" + "\n".join(hits)


@pytest.mark.parametrize("path", sorted(str(p.relative_to(ROOT)) for p in
                                        [*ROOT.glob("deploy/nav2/*.yaml"),
                                         *ROOT.glob("tools/nav_stability_bench_dev/params/*.yaml")]))
def test_Nav2配置的footprint_等于车身加基础余量(path):
    text = (ROOT / path).read_text(encoding="utf-8")
    polys = re.findall(r"^\s*footprint:\s*'(.+)'", text, flags=re.M)
    for poly in polys:
        pts = ast.literal_eval(poly)
        assert sorted({abs(x) for x, _ in pts}) == [pytest.approx(BASE_HALF_LEN)], (path, pts)
        assert sorted({abs(y) for _, y in pts}) == [pytest.approx(BASE_HALF_WID)], (path, pts)
