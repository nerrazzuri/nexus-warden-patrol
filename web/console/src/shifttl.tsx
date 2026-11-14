// 整班时间轴(redesign 第二轮 V4 稿底部):一台机器人一行,巡逻蓝条、离线红竖纹;下面一行标事件(安全事件红圈、
// 设备异常黄三角);一条「现在」竖线。点任一处去看那一刻的录像(点哪一行就是哪台的,点事件那一行是事件那台的)。
// 充电的灰条要站点记充电时段(还没有,见 design/console-v2/BUILD.md 第 8 期)。
import { hm, nameOf } from "./data";
import { t } from "./i18n";
import { forGuard, type Alert } from "./model";
import type { TodayItem } from "./todaypatrols";

/** 机器人掉线(站点 alert_audience._OFFLINE;固定摄像头掉线不画在机器人那一行)。 */
const ROBOT_OFFLINE = new Set(["robot_offline", "robot_offline_idle"]);
const RUNNING = new Set(["running", "done", "failed", "aborted", "handed_over"]);

/** 安全事件:有人闯入、火情(站点 alert_audience);上装的求助按钮也算。其余给保安的(机器人要帮忙、掉线)是设备与运营。 */
export const isSecurity = (a: { audience?: string; kind: string }) => a.audience === "intrusion" || a.audience === "fire" || a.kind === "payload_sos";

export interface Span { robot: string; from: number; to: number; kind: "patrol" | "offline" }
export interface Mark { key: string; robot: string; at: number; kind: "security" | "equipment"; title: string }

/** 时间轴上画什么:巡逻(今天的巡逻里跑过、在跑的)、离线(离线告警的起止)、事件。只取 [from, to) 里的。 */
export function shiftSpans(robots: string[], patrols: TodayItem[], alerts: Alert[], from: number, to: number, now: number): { spans: Span[]; marks: Mark[] } {
  const clip = (a: number, b: number) => [Math.max(a, from), Math.min(b, to)] as const;
  const spans: Span[] = [];
  for (const p of patrols) {
    if (!robots.includes(p.robot) || !RUNNING.has(p.state)) continue;
    const [a, b] = clip(p.at_ms, p.end_ms ?? now);
    if (b > a) spans.push({ robot: p.robot, from: a, to: b, kind: "patrol" });
  }
  for (const al of alerts) {
    if (!ROBOT_OFFLINE.has(al.kind) || !robots.includes(al.robot)) continue;
    const [a, b] = clip(al.first_ms, al.resolved_ms ?? now);
    if (b > a) spans.push({ robot: al.robot, from: a, to: b, kind: "offline" });
  }
  const marks: Mark[] = alerts
    .filter((a) => a.level !== "P3" && !ROBOT_OFFLINE.has(a.kind) && forGuard(a) && a.first_ms >= from && a.first_ms < to)
    .map((a) => ({ key: a.key, robot: a.robot, at: a.first_ms, kind: isSecurity(a) ? "security" as const : "equipment" as const, title: a.title }));
  return { spans, marks };
}

export function ShiftTimeline(props: {
  robots: string[];
  patrols: TodayItem[];
  alerts: Alert[];
  from: number;
  to: number;
  now: number;
  /** 这一刻看哪台的录像(点空白行是那一行的机器人;事件行是第一台)。 */
  onPick: (robot: string, at: number) => void;
}) {
  const { from, to } = props;
  const span = Math.max(1, to - from);
  const pct = (ms: number) => `${(100 * (Math.min(Math.max(ms, from), to) - from)) / span}%`;
  const { spans, marks } = shiftSpans(props.robots, props.patrols, props.alerts, from, to, props.now);
  const ticks: number[] = [];
  for (let h = from; h <= to; h += 7_200_000) ticks.push(h);   // 从班头起每 2 小时(19:00、21:00 …)
  const at = (e: MouseEvent, el: HTMLElement) => {
    const r = el.getBoundingClientRect();
    const f = r.width > 0 ? Math.min(1, Math.max(0, (e.clientX - r.left) / r.width)) : 0;
    return Math.min(props.now, from + f * span);
  };
  return (
    <section class="shifttl" aria-label={t("tlTitle")}>
      <div class="shifttl-head">
        <b>{t("tlShift", { a: hm(from), b: hm(to) })}</b>
        <span class="tl-key patrol">{t("tlPatrol")}</span>
        <span class="tl-key offline">{t("tlOffline")}</span>
        <span class="tl-key security">{t("tlSecurity")}</span>
        <span class="tl-key equipment">{t("tlEquipment")}</span>
        <span class="push muted">{t("tlHint")}</span>
      </div>
      <div class="shifttl-rows">
        {props.robots.map((id) => (
          <div key={id} class="tl-row">
            <span class="tl-name">{nameOf(id)}</span>
            <div class="tl-lane" data-tl-robot={id} onClick={(e) => props.onPick(id, at(e, e.currentTarget as HTMLElement))}>
              {spans.filter((s) => s.robot === id).map((s, i) => (
                <i key={i} class={`tl-span ${s.kind}`} style={{ left: pct(s.from), width: `calc(${pct(s.to)} - ${pct(s.from)})` }} />
              ))}
              <i class="tl-now" style={{ left: pct(props.now) }} />
            </div>
          </div>
        ))}
        <div class="tl-row tl-axis">
          <span class="tl-name" />
          <div class="tl-lane">
            {ticks.map((h) => <span key={h} class="tl-tick mono" style={{ left: pct(h) }}>{hm(h)}</span>)}
            {marks.map((m) => (
              <button key={m.key} type="button" class={`tl-mark ${m.kind}`} style={{ left: pct(m.at) }} title={`${hm(m.at)} ${m.title}`}
                aria-label={`${hm(m.at)} ${m.title}`} onClick={() => props.onPick(m.robot, m.at)} />
            ))}
            <span class="tl-nowlabel mono" style={{ left: pct(props.now) }}>{t("tlNow", { t: hm(props.now) })}</span>
          </div>
        </div>
      </div>
    </section>
  );
}
