#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path

import yaml


def percentile(values, p):
    if not values: return 0.0
    v=sorted(values); pos=(len(v)-1)*p; lo=math.floor(pos); hi=math.ceil(pos)
    if lo==hi: return v[lo]
    return v[lo]+(v[hi]-v[lo])*(pos-lo)


def evaluate(rows, gate):
    by=defaultdict(list)
    for r in rows: by[(r.get("fault","nominal"),r["scenario"])].append(r)
    passed=lambda r: bool(r.get("success")) and not r.get("collision") and not r.get("clearance_violation")
    n=len(rows); ok=sum(passed(r) for r in rows)
    rates={f"{f}/{s}": sum(passed(r) for r in rs)/len(rs) for (f,s),rs in by.items()}
    stalls=[float(r.get("max_stall_s") or 0) for r in rows]
    collisions=sum(bool(r.get("collision")) for r in rows)
    clear=sum(bool(r.get("clearance_violation")) for r in rows)
    progress=sum(int(r.get("progress_failures",0)) for r in rows)
    metrics={
      "runs":n,"passed":ok,"aggregate_success_rate":ok/n if n else 0,
      "min_per_scenario_success_rate":min(rates.values(), default=0),
      "collisions":collisions,"clearance_violations":clear,
      "p95_stall_s":round(percentile(stalls,0.95),3),
      "progress_failures_per_100_runs":100*progress/n if n else 0,
      "per_case_rates":dict(sorted(rates.items())),
    }
    checks={
      "min_runs": n >= gate.get("min_runs",0),
      "aggregate_success_rate": metrics["aggregate_success_rate"] >= gate.get("aggregate_success_rate",0),
      "min_per_scenario_success_rate": metrics["min_per_scenario_success_rate"] >= gate.get("min_per_scenario_success_rate",0),
      "max_collisions": collisions <= gate.get("max_collisions",0),
      "max_clearance_violations": clear <= gate.get("max_clearance_violations",0),
      "max_p95_stall_s": metrics["p95_stall_s"] <= gate.get("max_p95_stall_s",float("inf")),
    }
    if "max_progress_failures_per_100_runs" in gate:
        checks["max_progress_failures_per_100_runs"] = metrics["progress_failures_per_100_runs"] <= gate["max_progress_failures_per_100_runs"]
    return metrics, checks, all(checks.values())


def markdown(metrics, checks, passed, rows=None):
    lines=["# Nexus Warden Navigation Product Gate", "", f"**Result: {'PASS' if passed else 'FAIL'}**", "",
           f"Runs: {metrics['runs']}  ", f"Aggregate success: {metrics['aggregate_success_rate']:.3%}  ",
           f"Worst case success: {metrics['min_per_scenario_success_rate']:.3%}  ",
           f"Collisions: {metrics['collisions']}  ", f"Clearance violations: {metrics['clearance_violations']}  ",
           f"P95 stall: {metrics['p95_stall_s']:.2f}s  ", "", "## Gate checks", ""]
    for k,v in checks.items(): lines.append(f"- {'PASS' if v else 'FAIL'} — {k}")
    lines += ["", "## Per scenario / fault", "", "| Case | Success |", "|---|---:|"]
    for k,v in metrics["per_case_rates"].items(): lines.append(f"| {k} | {v:.2%} |")
    evidence = [r for r in (rows or []) if r.get("evidence_retained")]
    if evidence:
        lines += ["", "## Retained evidence", "", "| Case | Result | Evidence |", "|---|---|---|"]
        for r in evidence:
            case=f"{r.get('fault','nominal')}/{r['scenario']}/seed-{int(r['seed']):04d}"
            result="FAIL" if (not r.get("success") or r.get("collision") or r.get("clearance_violation")) else "PASS sample"
            lines.append(f"| {case} | {result} | `{r.get('evidence_path')}` |")
    lines += ["", "> Passing this simulation gate is a regression prerequisite, not proof of field reliability. Real-robot acceptance remains mandatory."]
    return "\n".join(lines)+"\n"


def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--input",type=Path,required=True); ap.add_argument("--gates",type=Path,required=True); ap.add_argument("--gate",required=True); ap.add_argument("--out",type=Path,required=True); a=ap.parse_args()
    rows=[json.loads(x) for x in a.input.read_text().splitlines() if x.strip()]
    gate=yaml.safe_load(a.gates.read_text())["gates"][a.gate]
    metrics,checks,passed=evaluate(rows,gate)
    result={"gate":a.gate,"pass":passed,"criteria":gate,"checks":checks,"metrics":metrics}
    a.out.mkdir(parents=True,exist_ok=True)
    (a.out/"product_gate.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    (a.out/"PRODUCT_GATE.md").write_text(markdown(metrics,checks,passed,rows),encoding="utf-8")
    print(json.dumps(result,indent=2))
    return 0 if passed else 2

if __name__=="__main__": raise SystemExit(main())
