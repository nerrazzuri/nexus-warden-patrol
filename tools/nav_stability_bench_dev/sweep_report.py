#!/usr/bin/env python3
"""汇总 run_sweep 的结果 → REPORT.md + summary.json(+ 可选:失败的俯视视频)。

    python3 sweep_report.py runs/nav-sweep-p0 [--videos 3]

报告里有:
- 每个配置的总表:趟数、通过率、碰撞、车身最小净距(P1 / 中位)、最小 TTC、平均脱困动作次数;
- 宽度曲线:每类窄路 × 每档宽度的通过率(必须过的档 / 必须停的档分开看);
- 失败原因分布(超时 / Nav2 放弃 / 碰撞 / 该停没停)和 Nav2 典型报错次数;
- 每类最差的几次(给视频)。
"""
from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent


def pct(xs, q):
    xs = sorted(x for x in xs if x is not None and math.isfinite(x))
    if not xs:
        return None
    k = (len(xs) - 1) * q
    lo, hi = math.floor(k), math.ceil(k)
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


def safety(r, run_dir):
    """按 REPORT_SPEC.md 的口径取安全指标:真实车身(0.93 × 0.48)精确距离,墙 / 人车分开。
    来源优先级:result.json 的 "safety"(goal_driver 当场算)> safety.json(safety_from_bag.py 从录包补)>
    推断(没录包的趟都是成功的:外扩 5 cm 的框从没碰上 → 没有真实碰撞、没有 < 5 cm;< 10 cm 不知道)。"""
    if r.get("safety"):
        return r["safety"]
    f = run_dir / "safety.json"
    if f.exists():
        d = json.loads(f.read_text())
        if "error" not in d:
            return d
    if r.get("collision"):
        return None                               # 碰了又没包:不知道,单独报
    return {"static_physical": False, "dynamic_physical": False, "static_under_5cm_s": 0.0,
            "dynamic_under_5cm_s": 0.0, "static_under_10cm_s": None, "dynamic_under_10cm_s": None,
            "static_min_m": None, "dynamic_min_moving_m": None, "inferred": True}


def why(r):
    if r.get("success"):
        return "通过"
    sf = r.get("_safety") or {}
    if sf.get("dynamic_physical"):
        return f"真撞 {sf.get('dynamic_physical_actor') or '人/车'}"
    if sf.get("static_physical"):
        return "真撞墙"
    if r.get("collision"):
        return "进了 5 cm 圈被判停" + (f"({r['actor_hit']})" if r.get("actor_hit") else "(墙)")
    if r.get("expect") == "blocked":
        return "该停没停(钻过去了)"
    gr = r.get("goal_results") or []
    if not gr:
        return r.get("reason", "没结果")
    last = gr[-1]
    if last.get("reason") == "timeout":
        return f"目标{last['goal'] + 1} 超时"
    if last.get("status") == 6:
        return f"目标{last['goal'] + 1} Nav2 放弃"
    return f"目标{last['goal'] + 1} {last.get('reason') or last.get('status')}"


def cmdtxt(c):
    if not c:
        return "—"
    return "停(0)" if not any(c) else f"前进 {c[0]:.2f}"


def fmt(v, nd=2, unit=""):
    return "—" if v is None else f"{v:.{nd}f}{unit}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("out", type=Path)
    ap.add_argument("--videos", type=int, default=0, help="每类出几段失败视频")
    ap.add_argument("--main-seeds", type=int, default=10, help="主表只用种子 < N(每个配置都有的)")
    args = ap.parse_args()
    allrows = [json.loads(p.read_text()) for p in sorted(args.out.glob("*/*/s*/result.json"))]
    # 生成失败 = 随机扰动把起点/目标放进了墙里,场景本身不成立:不算这次,单独报数
    invalid = [r for r in allrows if r.get("reason") == "generate failed"]
    rows = [r for r in allrows if r.get("reason") != "generate failed"]
    for r in rows:
        r["_safety"] = safety(r, args.out / r["config"] / r["scenario"] / f"s{r['seed']:03d}")
    for r in rows:
        if r.get("width_m") is None and "_w" in r["scenario"] and r["scenario"].rsplit("_w", 1)[1].isdigit():
            fam, w = r["scenario"].rsplit("_w", 1)
            r["family"], r["width_m"] = fam, int(w) / 100
    # 公平比较:主表只用每个配置都跑了的种子(0–9);加跑的种子(安全场景 40 次)单独一节
    extra = [r for r in rows if r["seed"] >= args.main_seeds]
    rows = [r for r in rows if r["seed"] < args.main_seeds]
    any_cut = any(r.get("collision") and r.get("stop_rule") != "physical" for r in rows)
    by_cfg = defaultdict(list)
    for r in rows:
        by_cfg[r["config"]].append(r)
    L = [f"# 极限场景扫描报告:{args.out.name}", "",
         f"共 {len(rows)} 趟有效(另有 {len(invalid)} 趟随机扰动把点放进墙里、场景不成立,不计)。标准:每边余量 ≥ 0.2 m(宽 ≥ 0.98 m)必须过;更窄的必须停住、不撞。", ""]
    summary = {}

    def must_pass(r):
        return r.get("expect", "arrive") != "blocked" and not (r.get("width_m") is not None and r["width_m"] < 0.98)

    def phys(r, k):
        return bool((r.get("_safety") or {}).get(k))

    L += ["## 四个关键数(规范见 tools/nav_stability_bench_dev/REPORT_SPEC.md)", "",
          "| 配置 | 必须通过 | 人/车真实碰撞 | 墙真实碰撞 | 太窄没钻过去 | 安全数据缺的趟 |", "|---|---:|---:|---:|---:|---:|"]
    for cfg, rs in sorted(by_cfg.items()):
        mp = [r for r in rs if must_pass(r)]
        tn = [r for r in rs if not must_pass(r)]
        L.append(f"| {cfg} | {sum(1 for r in mp if r.get('success'))}/{len(mp)} "
                 f"({sum(1 for r in mp if r.get('success')) / max(1, len(mp)):.0%}) | "
                 f"{sum(phys(r, 'dynamic_physical') for r in rs)} | {sum(phys(r, 'static_physical') for r in rs)} | "
                 f"{sum(1 for r in tn if r.get('success'))}/{len(tn)} | {sum(1 for r in rs if r.get('_safety') is None)} |")
    L += ["", "- 「太窄没钻过去」现在只是守卫/Nav2 过不去,还不是主动拒绝(出发前几何检查还没做)。"]
    if any_cut:
        L += ["- **墙真实碰撞 = 0 不能当结论**:这批是旧判停口径,外扩 5 cm 的框一碰上这趟就判失败、停车,"
              "车身没机会再往墙上贴。所以墙这一侧只能看「< 5 cm」那列。人/车不受影响(人会继续走过来)。"]
    L += [""]
    L += ["## 碰撞拆开看", "",
          "真实碰撞 = 真实车身(0.93 × 0.48)和障碍重叠;余量侵入 = 没碰上但车身离障碍 < 5 cm / < 10 cm(趟数)。"
          "人/车只算机器人在动时;停着被人走上来碰到另列。< 10 cm 只统计有录包或当场算过的趟(括号里是有数据的趟数)。", "",
          "| 配置 | 真撞墙 | 真撞人/车 | 墙 < 5 cm | 墙 < 10 cm | 人车 < 5 cm | 人车 < 10 cm | 墙最近 | 人车最近 | 停着被碰 |",
          "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for cfg, rs in sorted(by_cfg.items()):
        sf = [r["_safety"] for r in rs if r.get("_safety")]
        def cnt(k):
            return sum(1 for x in sf if (x.get(k) or 0) > 0)
        known10 = [x for x in sf if x.get("static_under_10cm_s") is not None]
        def mn(k):
            v = [x[k] for x in sf if x.get(k) is not None]
            return fmt(min(v), 3, " m") if v else "—"
        L.append(f"| {cfg} | {cnt('static_physical')} | {cnt('dynamic_physical')} | {cnt('static_under_5cm_s')} | "
                 f"{sum(1 for x in known10 if x['static_under_10cm_s'] > 0)} ({len(known10)}) | "
                 f"{cnt('dynamic_under_5cm_s')} | {sum(1 for x in known10 if (x.get('dynamic_under_10cm_s') or 0) > 0)} ({len(known10)}) | "
                 f"{mn('static_min_m')} | {mn('dynamic_min_moving_m')} | {cnt('dyn_bumped_while_stopped')} |")
    L.append("")
    hits = [r for r in rows + [x for x in extra] if (r.get("_safety") or {}).get("dynamic_physical")]
    if hits:
        L += ["### 撞上人/车的每一趟", "",
              "速度 = 平移 + 原地转的角点线速度。命令 = /cmd_vel(守卫之后、发给机器人的)。「进 5 cm 时命令还在前进」= 那一刻守卫还没看见;"
              "碰上时命令已是 0 = 在刹车(守卫叫停,或 5 cm 判停后 Nav2 取消目标)。", "", "| 配置 | 场景 | 种子 | 撞到 | 进 5 cm 时速度 / 命令 | 碰上时速度 / 命令 | 从进 5 cm 到碰上 |",
              "|---|---|---:|---|---|---|---:|"]
        for r in sorted(hits, key=lambda r: (r["config"], r["scenario"], r["seed"])):
            sf = r["_safety"]
            L.append(f"| {r['config']} | {r['scenario']} | {r['seed']} | {sf.get('dynamic_physical_actor')} | "
                     f"{fmt(sf.get('dynamic_5cm_speed'), 2, ' m/s')} / {cmdtxt(sf.get('dynamic_5cm_cmd'))} | "
                     f"{fmt(sf.get('dynamic_contact_speed'), 2, ' m/s')} / {cmdtxt(sf.get('dynamic_contact_cmd'))} | "
                     f"{fmt(sf.get('dynamic_contact_after_5cm_s'), 2, ' s')} |")
        L.append("")
    if extra:
        L += [f"## 安全场景加跑(种子 {args.main_seeds} 以上,只有部分配置跑了;跟上面合起来看每组 40 次)", "",
              "| 配置 | 场景 | 通过 | 人/车真实碰撞 | 人车 < 5 cm | 人车最近 |", "|---|---|---:|---:|---:|---:|"]
        allr = rows + extra
        ex_cfg = sorted({r["config"] for r in extra})
        ex_sc = sorted({r["scenario"] for r in extra})
        for cfg in ex_cfg:
            for sid in ex_sc:
                xs = [r for r in allr if r["config"] == cfg and r["scenario"] == sid]
                sf = [r.get("_safety") or {} for r in xs]
                dm = [x.get("dynamic_min_moving_m") for x in sf if x.get("dynamic_min_moving_m") is not None]
                L.append(f"| {cfg} | {sid} | {sum(1 for r in xs if r.get('success'))}/{len(xs)} | "
                         f"{sum(1 for x in sf if x.get('dynamic_physical'))} | {sum(1 for x in sf if (x.get('dynamic_under_5cm_s') or 0) > 0)} | "
                         f"{fmt(min(dm), 3, ' m') if dm else '—'} |")
            L.append(f"| **{cfg} 合计** | | {sum(1 for r in allr if r['config'] == cfg and r['scenario'] in ex_sc and r.get('success'))}/"
                     f"{sum(1 for r in allr if r['config'] == cfg and r['scenario'] in ex_sc)} | "
                     f"{sum(1 for r in allr if r['config'] == cfg and r['scenario'] in ex_sc and (r.get('_safety') or {}).get('dynamic_physical'))} | | |")
        L.append("")
    L += ["## 总表", "", "| 配置 | 趟数 | 通过率 | 进 5 cm 圈被判停 | 外扩 5 cm 框最小净距 P1 / 中位 | 最小 TTC P1 | 每趟脱困动作 | 每趟守卫拦截拍数 |",
          "|---|---:|---:|---:|---|---:|---:|---:|"]
    for cfg, rs in sorted(by_cfg.items()):
        n = len(rs)
        ok = sum(1 for r in rs if r.get("success"))
        col = sum(1 for r in rs if r.get("collision"))
        clr = [r.get("min_body_clearance_moving_m") for r in rs]
        ttc = [r.get("min_ttc_s") for r in rs]
        rec = [sum(v for k, v in (r.get("log") or {}).items() if k.startswith("rec_")) for r in rs]
        blk = [(r.get("guard") or {}).get("blocked_ticks", 0) for r in rs]
        summary[cfg] = {"runs": n, "passed": ok, "collisions": col, "clearance_p1": pct(clr, 0.01),
                        "clearance_p50": pct(clr, 0.5), "ttc_p1": pct(ttc, 0.01),
                        "recoveries_per_run": sum(rec) / n if n else None}
        L.append(f"| {cfg} | {n} | {ok / n:.1%} | {col} | {fmt(pct(clr, 0.01))} / {fmt(pct(clr, 0.5))} m | "
                 f"{fmt(pct(ttc, 0.01), 1, ' s')} | {sum(rec) / n:.1f} | {sum(blk) / n:.0f} |")
    L.append("")
    # 宽度曲线
    fams = sorted({r["family"] for r in rows if r.get("width_m") is not None})
    widths = sorted({r["width_m"] for r in rows if r.get("width_m") is not None})
    if fams:
        L += ["## 宽度曲线(通过率;**粗体** = 必须过的档,其余 = 必须停的档)", ""]
        for cfg, rs in sorted(by_cfg.items()):
            L += [f"### {cfg}", "", "| 场景类 | " + " | ".join(
                (f"**{w:.2f}**" if w >= 0.98 else f"{w:.2f}") for w in widths) + " |",
                "|---|" + "---:|" * len(widths)]
            for fam in fams:
                cells = []
                for w in widths:
                    xs = [r for r in rs if r.get("family") == fam and r.get("width_m") == w]
                    if not xs:
                        cells.append("—")
                        continue
                    k = sum(1 for r in xs if r.get("success"))
                    c = sum(1 for r in xs if phys(r, "static_physical") or phys(r, "dynamic_physical"))
                    m = sum(1 for r in xs if (r.get("collision") or r.get("margin_touch"))
                            and not (phys(r, "static_physical") or phys(r, "dynamic_physical")))
                    cells.append(f"{k}/{len(xs)}" + (f" ⚠真撞{c}" if c else "") + (f" ·进圈{m}" if m > 0 else ""))
                L.append(f"| {fam} | " + " | ".join(cells) + " |")
            L.append("")
    # 必须过的档:失败原因
    if fams:
        L += ["## 必须过的档(≥ 0.98 m)为什么没过", "", "| 配置 | 场景类 | 没过 | 原因 |", "|---|---|---:|---|"]
        for cfg, rs in sorted(by_cfg.items()):
            for fam in fams:
                xs = [r for r in rs if r.get("family") == fam and (r.get("width_m") or 0) >= 0.98 and not r.get("success")]
                if not xs:
                    continue
                c = defaultdict(int)
                for r in xs:
                    c[why(r)] += 1
                L.append(f"| {cfg} | {fam} | {len(xs)} | " + "、".join(
                    f"{k} ×{v}" for k, v in sorted(c.items(), key=lambda kv: -kv[1])) + " |")
        L.append("")
    # 其他场景
    L += ["## 不按宽度扫的场景", "", "| 配置 | 场景 | 通过 | 真撞 / 进圈 | 外扩框最小净距 | 主要失败 |", "|---|---|---:|---:|---:|---|"]
    for cfg, rs in sorted(by_cfg.items()):
        for sid in sorted({r["scenario"] for r in rs if r.get("width_m") is None}):
            xs = [r for r in rs if r["scenario"] == sid]
            fails = defaultdict(int)
            for r in xs:
                if not r.get("success"):
                    fails[why(r)] += 1
            top = "、".join(f"{k} ×{v}" for k, v in sorted(fails.items(), key=lambda kv: -kv[1])[:2]) or "—"
            L.append(f"| {cfg} | {sid} | {sum(1 for r in xs if r.get('success'))}/{len(xs)} | "
                     f"{sum(1 for r in xs if phys(r, 'static_physical') or phys(r, 'dynamic_physical'))} / "
                     f"{sum(1 for r in xs if r.get('collision'))} | "
                     f"{fmt(pct([r.get('min_body_clearance_moving_m') for r in xs], 0.0))} m | {top} |")
    L.append("")
    # 失败原因 + Nav2 报错
    # 导航 V1 第 2 节验收:Route Validator 对照几何判定器(只算两边都有结论的趟)
    gated = [r for r in rows if isinstance(r.get("oracle"), dict) and "feasible" in r["oracle"]
             and r.get("route_checks") is not None]
    if gated:
        L += ["## Route Validator 对照几何判定器", "",
              "判定器 = 按地图墙、有效车身 + 每边 0.2 m 搜遍位置和朝向的标准答案;"
              "验收:判定器可行的误拒 < 2%,判定器不可行的正确拒绝 > 50/60(按比例看)。", "",
              "| 配置 | 判定器可行:趟数 | 误拒 | 误拒率 | 可行里自动完成 | 判定器不可行:趟数 | 正确拒绝 | 漏拒 | 漏拒里真撞 | 没查成 |",
              "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
        for cfg in sorted({r["config"] for r in gated}):
            rs = [r for r in gated if r["config"] == cfg]
            fe = [r for r in rs if r["oracle"]["feasible"]]
            inf = [r for r in rs if not r["oracle"]["feasible"]]
            mis = [r for r in fe if r.get("route_refused")]
            done = [r for r in fe if r.get("success")]
            ok_rej = [r for r in inf if r.get("route_refused")]
            miss = [r for r in inf if not r.get("route_refused")]
            hit = [r for r in miss if phys(r, "static_physical") or phys(r, "dynamic_physical")]
            unchecked = sum(1 for r in rs for c in r.get("route_checks") or [] if not c.get("checked"))
            rate = f"{100 * len(mis) / len(fe):.1f}%" if fe else "—"
            L.append(f"| {cfg} | {len(fe)} | {len(mis)} | {rate} | {len(done)}/{len(fe)} | {len(inf)} | "
                     f"{len(ok_rej)} | {len(miss)} | {len(hit)} | {unchecked} |")
            summary.setdefault(cfg, {})["route_validator"] = {
                "feasible": len(fe), "misreject": len(mis), "feasible_done": len(done),
                "infeasible": len(inf), "correct_reject": len(ok_rej), "missed": len(miss),
                "missed_collided": len(hit), "unchecked": unchecked}
        L.append("")
        L += ["误拒、漏拒明细(场景 / 种子 / 判定器怎么说 / Validator 怎么说):", ""]
        for r in gated:
            fe, rej = r["oracle"]["feasible"], bool(r.get("route_refused"))
            if fe == rej:
                why_v = next((c for c in r.get("route_checks") or [] if c.get("checked") and not c.get("ok")), {})
                legs = r["oracle"].get("legs") or []
                o = "可行" if fe else f"不可行(第 {r['oracle'].get('first_bad')} 段 " \
                    f"{legs[r['oracle']['first_bad']]['reason'] if legs else ''})"
                v = f"拒 {why_v.get('code')} 余量 {why_v.get('margin')} 在 {why_v.get('at')}" if rej else "放行"
                L.append(f"- {r['config']} {r['scenario']} s{r['seed']}:判定器{o};Validator {v}")
        L.append("")

    L += ["## 失败原因", ""]
    for cfg, rs in sorted(by_cfg.items()):
        fails = defaultdict(int)
        for r in rs:
            if not r.get("success"):
                fails[why(r).split(" ", 1)[-1] if why(r).startswith("目标") else why(r)] += 1
        errs = defaultdict(int)
        for r in rs:
            for k, v in (r.get("log") or {}).items():
                if k.startswith("err_"):
                    errs[k] += v
        L.append(f"- **{cfg}**:" + ("、".join(f"{k} {v}" for k, v in sorted(fails.items(), key=lambda kv: -kv[1]))
                                     or "无失败"))
        L.append(f"  - Nav2 报错累计:" + "、".join(f"{k[4:]} {v}" for k, v in sorted(errs.items())))
    L.append("")
    (args.out / "REPORT.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    (args.out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1))
    print("\n".join(L))
    if args.videos:
        vids = args.out / "videos"
        vids.mkdir(exist_ok=True)
        picked = defaultdict(int)
        for r in rows:
            if r.get("success"):
                continue
            key = (r["config"], r.get("family") or r["scenario"])
            if picked[key] >= args.videos:
                continue
            d = args.out / r["config"] / r["scenario"] / f"s{r['seed']:03d}"
            if not (d / "bag").exists():
                continue
            picked[key] += 1
            name = f"{r['config']}-{r['scenario']}-s{r['seed']}-{why(r)}.mp4".replace("/", "_").replace(" ", "")
            subprocess.run([sys.executable, str(HERE / "render_topdown.py"), str(d), str(vids / name),
                            f"{r['config']} {r['scenario']} 种子{r['seed']}:{why(r)}"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
