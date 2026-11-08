#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path


def summarize(rows: list[dict]) -> dict:
    by = defaultdict(list)
    for row in rows:
        by[row["scenario"]].append(row)

    def one(items: list[dict]) -> dict:
        n = len(items)
        ok = sum(bool(x.get("success")) and not bool(x.get("clearance_violation")) for x in items)
        stalls = [float(x.get("max_stall_s", 0) or 0) for x in items]
        elapsed = [float(x.get("elapsed_s", 0) or 0) for x in items]
        clear = [float(x["min_clearance_m"]) for x in items if x.get("min_clearance_m") is not None]
        return {
            "runs": n,
            "passed": ok,
            "success_rate": round(ok / n, 5) if n else 0,
            "max_stall_s": round(max(stalls, default=0), 3),
            "mean_elapsed_s": round(sum(elapsed) / len(elapsed), 3) if elapsed else None,
            "min_clearance_m": round(min(clear), 4) if clear else None,
            "progress_failures": sum(int(x.get("progress_failures", 0)) for x in items),
            "planner_failures": sum(int(x.get("planner_failures", 0)) for x in items),
            "controller_failures": sum(int(x.get("controller_failures", 0)) for x in items),
            "localization_resets": sum(int(x.get("localization_resets", 0)) for x in items),
            "safety_rejections": sum(int(x.get("safety_rejections", 0)) for x in items),
        }

    overall = one(rows)
    overall["scenarios"] = {name: one(items) for name, items in sorted(by.items())}
    overall["gate"] = {
        "target_success_rate": 0.99,
        "pass": overall["success_rate"] >= 0.99 and overall["passed"] == overall["runs"],
        "note": "For POC gating, treat any clearance violation as a failed run.",
    }
    return overall


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    rows = [json.loads(line) for line in args.input.read_text(encoding="utf-8").splitlines() if line.strip()]
    result = summarize(rows)
    args.out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if result["gate"]["pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
