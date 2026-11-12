"""回环参数文件(``pipelines/loop-closure.yaml``)的几条硬规矩。"""

from __future__ import annotations

import re

import yaml
from nexwar_localizer.build import LC_PIPELINE


def _default(v) -> float:
    """``"${ENV|100}"`` → 100;普通数字原样。"""
    m = re.fullmatch(r"\$\{[A-Z_]+\|([0-9.]+)\}", str(v).strip())
    return float(m.group(1) if m else v)


def test_W75_ICP提前放弃的检查点在迭代上限之内_不然没希望的候选也跑满():
    """11-13 台式机整圈 1071 关键帧:检查点原来写在第 150 次,上限 100 次,从来不生效 —— 0% 匹配的
    候选照样跑到几十上百次。挪到第 10 次:回环 125 s → 96 s,回环数一样(44),轨迹差 ≤ 0.2 cm。"""
    p = yaml.safe_load(LC_PIPELINE.read_text())["icp_settings"]["params"]
    top = _default(p["maxIterations"])
    cps = p["quality_checkpoints"]
    assert cps and all(int(c["iteration"]) < top for c in cps), (cps, top)
    assert min(int(c["iteration"]) for c in cps) <= 10


def test_W75_子图配准用的点降到两万():
    """11-13 广场整圈:5 万 → 2 万,回环 96 s → 64 s;走过两次的地方清晰度不变
    (中位 3.48 → 3.42 cm)。"""
    y = yaml.safe_load(LC_PIPELINE.read_text())
    got = [f["params"] for f in y["submap_final_filter"]
           if f["class_name"] == "mp2p_icp_filters::FilterDecimateAdaptive"]
    assert got and _default(got[0]["desired_output_point_count"]) == 20000
