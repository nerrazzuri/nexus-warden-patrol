"""给一趟仿真标「几何上能不能过」(导航 V1 第 2 节验收):用几何判定器(geom_oracle.py)按这一趟的
地图(map.yaml / map.pgm,只有地图墙,跟 Route Validator 看到的一样)判每一段:
起点 → 目标 1 → 目标 2 …;下一段的起点 = 上一段的目标(位置 + 朝向)。

用法:``python3 oracle_label.py <case 目录>…``(每个目录要有 case.json、map.yaml、map.pgm),
打印每个目录的结论;``label(case_dir)`` 给跑批用。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import geom_oracle  # noqa: E402
from route_gate import load_walls  # noqa: E402


def label(case_dir: Path) -> dict:
    """→ ``{"feasible": bool, "legs": [{"feasible", "reason"}…], "first_bad": 段号或 None}``。"""
    case = json.loads((case_dir / "case.json").read_text(encoding="utf-8"))
    walls, res, origin = load_walls(case_dir)
    pts = [case["start"], *case["goals"]]
    legs = []
    for a, b in zip(pts[:-1], pts[1:], strict=True):
        v = geom_oracle.judge(walls, res, origin, (a[0], a[1], a[2]), (b[0], b[1], b[2]))
        legs.append({"feasible": v.feasible, "reason": v.reason})
    bad = next((i for i, g in enumerate(legs) if not g["feasible"]), None)
    return {"feasible": bad is None, "legs": legs, "first_bad": bad}


def main() -> int:
    for d in sys.argv[1:]:
        print(d, json.dumps(label(Path(d)), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
