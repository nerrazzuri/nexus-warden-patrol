// 现场设置 → 概况(redesign 第六期 S-home / M-home;W44 第二期的现场概况换样子)。
// 页头:一句话说现在(布防状态、机器人在线、几件待批准 / 几条提醒),右边「查看报告」。
// 左:要你处理的事(蓝圆点 = 去对应页面批准,黄三角 = 提醒:知道了 / 已处理)+ 开站清单 + 今天的安排(布防 / 授权 / 巡逻三行时间条,
//     切换模式、按防区临时撤防)。右:机器人、本周。
// 经理(只读概况,M-home):左边换成过去 24 小时的报警表、今天的安排(去布防与巡逻修改)、在管理员那里的事(只看进度);
//     右边多一条最近的交班留言。
import { PatrolReason } from "./armwizard";
import { alertAdvice, alertHeadline } from "./alertinfo";
import { siteStr, siteText, zhPunct, byText } from "./sitetext";
import type { AdminPage } from "./shell";
import { useEffect, useState } from "preact/hooks";
import { advice } from "./advice";
import { api } from "./api";
import { whoText } from "./armingpage";
import type { Authz } from "./accesspage";
import { hm, nameOf } from "./data";
import { alertTitle, lang, t, type Key, joinList } from "./i18n";
import { DrillNote } from "./alerttest";
import { SetupChecklist } from "./guide";
import { autoResolved, forGuard, type Alert, type Mode } from "./model";
import { verdictText } from "./mappage";
import { reportRange, type Summary } from "./reports";
import type { RobotCard } from "./robotspage";
import { Sign } from "./signs";
import type { TodayItem } from "./todaypatrols";
import { dateInput } from "./recordings";

interface Today { zone: string; windows: [string, string][] }
interface Note { id: number; at_ms: number; author: string; text: string }

/** 「12:30」→ 当天的分钟。 */
const minOf = (s: string) => { const [h, m] = s.split(":").map(Number); return (h || 0) * 60 + (m || 0); };
const dayMin = (ms: number) => { const d = new Date(ms); return d.getHours() * 60 + d.getMinutes(); };

export function HomePage(props: {
  alerts: Alert[];
  mode: Mode | null;
  now: number;
  role?: string;
  onAck: (a: Alert) => void;
  onDone: (a: Alert) => void;
  onMode: (m: Mode["mode"]) => void;
  /** 布防向导(用户 11-13):布防着机器人却不会自己巡逻时,在模式开关下说原因、给入口(管理员)。 */
  onWizard?: () => void;
}) {
  const owner = props.role === "owner";
  const [today, setToday] = useState<{ enabled: boolean; today: Today[] } | null>(null);
  const [authz, setAuthz] = useState<Authz[]>([]);
  const [robots, setRobots] = useState<RobotCard[] | null>(null);
  const [weeks, setWeeks] = useState<[Summary | null, Summary | null]>([null, null]);
  const [patrols, setPatrols] = useState<TodayItem[]>([]);
  const [last24, setLast24] = useState<Alert[] | null>(null);
  const [note, setNote] = useState<Note | null>(null);
  const [modeOpen, setModeOpen] = useState(false);
  void lang.value;

  useEffect(() => {
    api<{ enabled: boolean; today: Today[] }>("GET", "/api/arming/schedule").then(setToday).catch(() => setToday(null));
    api<{ authorizations: Authz[] }>("GET", "/api/lists/authorizations").then((d) => setAuthz(d.authorizations ?? [])).catch(() => setAuthz([]));
    api<{ robots: RobotCard[] }>("GET", "/api/robots/overview").then((d) => setRobots((d.robots ?? []).filter((r) => !r.revoked))).catch(() => setRobots(null));
    api<{ items: TodayItem[] }>("GET", "/api/patrols/today").then((d) => setPatrols(d.items ?? [])).catch(() => setPatrols([]));
    const w = reportRange("week", props.now)!;
    const l = reportRange("lastweek", props.now)!;
    Promise.all([w, l].map((p) => api<Summary>("GET", `/api/reports/summary?since=${p.since}&until=${p.until}`).catch(() => null)))
      .then(([a, b]) => setWeeks([a, b]));
    if (owner) {
      api<{ alerts: Alert[] }>("GET", `/api/alerts?since=${props.now - 86_400_000}&until=${props.now + 60_000}&limit=200`)
        .then((d) => setLast24((d.alerts ?? []).filter((a) => forGuard(a) && a.level !== "P3"))).catch(() => setLast24([]));
      api<{ latest: Note | null }>("GET", "/api/shift-notes").then((d) => setNote(d.latest ?? null)).catch(() => {});
    }
  }, []);

  // 第 2 轮 duty N6 / config N9:P3 是通知(巡逻开始了、派了临时巡逻……),不是要你处理的事,不进这里
  const todo = homeTodo(props.alerts);
  const groups = groupTodo(todo);
  const approvals = groups.filter((g) => !!goOf(g[0])).length;
  const m = props.mode;
  const online = robots?.filter((r) => r.online).length ?? 0;
  const robotLine = robots == null || robots.length === 0 ? "" : online === robots.length ? t("ovAllOnline") : t("ovRobotsOnline", { a: online, n: robots.length });
  const open24 = (last24 ?? []).filter((a) => a.resolved_ms == null).length;
  const tail = owner
    ? (last24 == null ? "" : open24 ? t("ovAlarms24", { n: last24.length, o: open24 }) : t("ovAlarms24Closed", { n: last24.length }))
    : groups.length ? t("ovPending", { a: approvals, b: groups.length - approvals }) : t("ovNothing");
  const headSign = m?.state === "armed" ? "ok" : "info";

  return (
    <section class="homepage sp">
      <header class="sp-head">
        <h1>{t("ovTitle")}</h1>
        <p class="sp-status"><Sign kind={headSign} />
          <span>{m ? whoText(m as Parameters<typeof whoText>[0], today?.enabled ?? false) : ""} {robotLine} <b>{tail}</b></span></p>
        <a class="btn" href="#/admin/reports">{t("ovViewReports")}</a>
      </header>
      <div class="sp-body">
        <div class="sp-main">
          <DrillNote />

          {owner && (
            <section class="sp-sec home-24">
              <h2 class="sp-h"><span>{t("ovAlarms24H", { n: last24?.length ?? "–" })}</span><a href="#/alarms">{t("ovViewEvents")}</a></h2>
              {last24 != null && last24.length === 0 ? <p class="sp-pad muted">{t("ovNoAlarms24")}</p> : (
                <table class="sp-table">
                  <thead><tr><th>{t("ovColTime")}</th><th /><th>{t("ovColEvent")}</th><th>{t("ovColBy")}</th><th>{t("ovColDisp")}</th></tr></thead>
                  <tbody>
                    {(last24 ?? []).slice().sort((a, b) => b.first_ms - a.first_ms).map((a) => (
                      <tr key={a.key}>
                        <td class="mono muted">{dateInput(a.first_ms).slice(5)} {hm(a.first_ms)}</td>
                        <td><Sign kind={a.level === "P1" ? "bad" : "warn"} /></td>
                        <td>{alertHeadline(a)}</td>
                        <td class="muted">{a.resolved_ms == null ? (a.acked_by ? byText(a.acked_by) : "—") : autoResolved(a) ? t("evSystem") : byText(a.resolved_by || a.acked_by) || "—"}</td>
                        <td><b>{a.resolved_ms == null ? t("ovOpenNow") : autoResolved(a) ? t("evAutoRecovered") : verdictText(a) || t("monResolved")}</b></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </section>
          )}

          {!owner && todo.length > 0 && (
            <section class="sp-sec home-todo">
              <h2 class="sp-h"><span>{t("ovAction", { n: groups.length })}</span></h2>
              {/* 第 2 轮 P1-75:「知道了」和「已处理」差在哪儿 */}
              <p class="sp-pad muted small" data-ack-done-hint="1">{t("ovActionHint")} {t("noticeAckDoneHint")}</p>
              <ul class="sp-list">{groups.map((g) => <TodoRow key={g[0].key} g={g} onAck={props.onAck} onDone={props.onDone} />)}</ul>
            </section>
          )}

          <section class="sp-sec home-today">
            <h2 class="sp-h"><span>{t("ovSchedule", { d: new Date(props.now).toLocaleDateString(lang.value === "zh" ? "zh-CN" : "en-GB", { weekday: "short" }) + " " + dateInput(props.now).slice(5) })}</span>
              {owner ? <a href="#/admin/arming">{t("ovEditArming")}</a> : m && (
                <span class="sp-acts">
                  <button type="button" class="btn" aria-expanded={modeOpen} onClick={() => setModeOpen(!modeOpen)}>{t("ovChangeMode")}</button>
                  <a class="btn" href="#/admin/access">{t("ovTempDisarm")}</a>
                </span>
              )}
            </h2>
            {modeOpen && m && !owner && (
              <div class="home-mode sp-pad">
                <p class="arm-who">{whoText(m as Parameters<typeof whoText>[0], today?.enabled ?? false)}</p>
                <div class="seg" role="group" aria-label={t("homeSwitch")}>
                  {([{ m: "armed", key: "modeArmed" }, { m: "home", key: "modeHome" }] as { m: Mode["mode"]; key: Key }[]).map((x) => (
                    <button key={x.m} type="button" aria-pressed={!m.unset && m.source !== "schedule" && m.mode === x.m}
                      onClick={() => props.onMode(x.m)}>{t(x.key)}</button>
                  ))}
                </div>
                {m.state !== "disarmed" && m.mode === "armed" && <PatrolReason onWizard={props.onWizard} />}
              </div>
            )}
            <DayPlan now={props.now} today={today} authz={authz.filter((a) => a.on_today)} patrols={patrols} />
            {m?.mode === "visitor" && m.until_ms != null && <p class="sp-pad"><b>{t("homeVisitorUntil", { t: hm(m.until_ms) })}</b></p>}
          </section>

          {!owner && <SetupChecklist />}

          {owner && todo.length > 0 && (
            <section class="sp-sec home-admin">
              <h2 class="sp-h"><span>{t("ovWithAdmin", { n: groups.length })}</span><small>{t("ovWithAdminHint")}</small></h2>
              <ul class="sp-list">
                {groups.map((g) => {
                  const a = g[0];
                  const adv = advice(a.kind, a.detail);
                  return (
                    <li key={a.key} class="todo" data-kind={a.kind}>
                      <Sign kind={goOf(a) ? "info" : "warn"} />
                      <div class="todo-body"><b>{adv ? t(adv.say) : siteStr(alertTitle(lang.value, a.kind, a.title))}</b></div>
                      <span class="muted">{a.acked_ms != null ? t("ovAckedBy", { who: byText(a.acked_by) || "—", t: dateInput(a.acked_ms).slice(5) }) : t("ovAwaiting")}</span>
                    </li>
                  );
                })}
              </ul>
            </section>
          )}
        </div>

        <aside class="sp-side">
          <section class="sp-sec home-robots">
            <h2 class="sp-h"><span>{t("ovRobotsH")}</span><a href="#/admin/robots">{t("ovGoRobots")}</a></h2>
            {robots == null ? <p class="sp-pad muted">…</p> : robots.length === 0 ? <p class="sp-pad muted">{t("robotsNone")}</p> : (
              <ul class="sp-list">
                {robots.map((r) => {
                  const issues = r.problems.length;
                  return (
                    <li key={r.robot_id}>
                      <a class="home-robot" href={`#/admin/robots?robot=${encodeURIComponent(r.robot_id)}`}>
                        <Sign kind={!r.online ? "bad" : issues ? "warn" : "ok"} />
                        <b>{r.name || nameOf(r.robot_id)}</b>
                        <span class="muted">{[r.online ? (r.task_what?.route ? t("ovRunning", { route: r.task_what.route }) : t("ovPatrolsToday", { n: r.patrols_today })) : t("st_offline"),
                          r.battery_pct == null ? "" : `${r.battery_pct}%`].filter(Boolean).join(" · ")}</span>
                        <span class={issues ? "warn-text" : "muted"}>{issues ? t(issues === 1 ? "ovRobotIssue1" : "ovRobotIssues", { n: issues }) : t("ovRobotNormal")}</span>
                      </a>
                    </li>
                  );
                })}
              </ul>
            )}
          </section>
          <section class="sp-sec home-week">
            <h2 class="sp-h"><span>{t("ovWeekH", { d: weeks[0] ? dateInput(weeks[0].since_ms).slice(5) : "" })}</span><a href="#/admin/reports">{t("ovViewReports")}</a></h2>
            {weeks[0] == null ? <p class="sp-pad muted">…</p> : (
              <dl class="sp-kv">
                <dt>{t("ovEvents")}</dt><dd><b>{weeks[0].totals.incidents}</b><span class="muted">{compare(weeks[0].totals.incidents, weeks[1]?.totals.incidents)}</span></dd>
                <dt>{t("ovFalse")}</dt><dd><b>{weeks[0].totals.false_alarms}</b><span class="muted">{compare(weeks[0].totals.false_alarms, weeks[1]?.totals.false_alarms)}</span></dd>
                {weeks[0].kpis && <><dt>{t("ovPatrolsDone")}</dt><dd><b>{weeks[0].kpis.patrols_done} / {weeks[0].kpis.patrols_sent}</b><span /></dd></>}
              </dl>
            )}
          </section>
          {owner && note && (
            <section class="sp-sec home-note">
              <h3 class="sp-lbl">{t("ovHandover", { who: note.author, t: hm(note.at_ms) })}</h3>
              <p class="sp-pad">{note.text}</p>
            </section>
          )}
        </aside>
      </div>
    </section>
  );
}

/** 这条提醒去哪页处理(有 = 「批准」类,蓝圆点 + 一个去那页的按钮)。 */
function goOf(a: Alert): string | undefined {
  const adv = advice(a.kind, a.detail);
  return adv?.go ?? (a.kind === "preflight_refused" ? preflightPage(a) : undefined);
}

const PAGE_KEY: Record<string, Key> = {
  "admin/users": "setUsers", "admin/robots": "setRobots", "admin/system": "setMaint", "admin/layout": "setLayout",
  "admin/arming": "setArming", "admin/access": "setAccess", "admin/localization": "tabLocalization", "admin/diag": "tabDiag",
  "admin/upgrade": "tabUpgrade", "admin/maps": "tabMapMgmt", "admin/reports": "setReports",
};

function TodoRow({ g, onAck, onDone }: { g: Alert[]; onAck: (a: Alert) => void; onDone: (a: Alert) => void }) {
  const a = g[0];
  const adv = advice(a.kind, a.detail);
  // 第 2 轮 P0-01:出发前检查没过 —— 写是哪一项、管理员自己怎么办、按钮去哪页(不写「请联系工程师」)
  const pf = a.kind === "preflight_refused";
  const go = goOf(a);
  const robots = [...new Set(g.map((x) => x.robot).filter((r) => r && r !== "site"))];
  return (
    <li class={`todo ${a.level}`} data-kind={a.kind} data-n={g.length}>
      <Sign kind={go ? "info" : "warn"} />
      <div class="todo-body">
        <b>{adv ? t(adv.say) : pf ? alertHeadline(a) : siteStr(alertTitle(lang.value, a.kind, a.title))}</b>
        <span class="small muted">{[robots.length > 0 ? t("homeTodoRobots", { r: joinList(robots) }) : "", hm(a.first_ms), pf ? alertAdvice(a) : t(adv ? adv.todo : "advCallEngineer")].filter(Boolean).join(" · ")}</span>
        {/* P2-44:站点原话(带文件路径的技术说明)收起来,要看再点开 */}
        {a.detail && (adv || pf || siteText(a.detail).raw
          ? <details class="todo-detail small"><summary>{t("homeTodoDetail")}</summary>
            {/* UIUX-032:英文界面里这是站点的中文原话,先说一声(跟活动日志一样) */}
            {lang.value !== "zh" && /[一-鿿]/.test(a.detail) && <span data-raw-note="1">{t("homeRawNote")} </span>}
            <span class="muted">{lang.value === "zh" ? zhPunct(a.detail) : a.detail}</span></details>
          : <span class="muted small">{siteStr(a.detail)}</span>)}
      </div>
      <div class="todo-acts">
        {go ? <a class="btn" href={`#/${go}${go === "admin/robots" && robots.length === 1 ? `?robot=${encodeURIComponent(robots[0])}` : ""}`}>
          {PAGE_KEY[go] ? t("ovGoPage", { p: t(PAGE_KEY[go]) }) : t("homeGo")}</a>
          : g.some((x) => x.acked_ms == null) && <button type="button" class="btn" title={t("noticeAckTip")} onClick={() => g.forEach((x) => x.acked_ms == null && onAck(x))}>{t("noticeAck")}</button>}
        <button type="button" class="btn" title={t("noticeDoneTip")} onClick={() => g.forEach((x) => onDone(x))}>{t("noticeDone")}</button>
      </div>
    </li>
  );
}

/** 今天的安排:布防 / 授权 / 巡逻三行,0–24 点,一根「现在」线。 */
function DayPlan(props: { now: number; today: { enabled: boolean; today: Today[] } | null; authz: Authz[]; patrols: TodayItem[] }) {
  const pct = (min: number) => `${(Math.max(0, Math.min(1440, min)) / 1440) * 100}%`;
  const box = (a: number, b: number) => ({ left: pct(a), width: `calc(${pct(b)} - ${pct(a)})` });
  const zones = props.today?.enabled ? props.today.today : [];
  const nowMin = dayMin(props.now);
  const activeAuthz = props.authz.filter((a) => a.active_now);
  const runs = props.patrols.filter((p) => p.at_ms <= props.now && p.state !== "next" && p.state !== "later" && p.state !== "missed" && p.state !== "blocked");
  const running = runs.find((p) => p.state === "running");
  return (
    <div class="dayplan sp-pad">
      <div class="dp-row dp-axis"><span /><div class="dp-lane">{[0, 3, 6, 9, 12, 15, 18, 21, 24].map((h) => <i key={h} style={{ left: pct(h * 60) }}>{String(h).padStart(2, "0")}</i>)}</div><span /></div>
      <div class="dp-row" data-row="armed">
        <b>{t("ovRowArmed")}</b>
        <div class="dp-lane">
          {zones.flatMap((z) => z.windows.flatMap(([a, b]) => {
            const s = minOf(a), e = minOf(b);
            const label = z.zone || t("ovAllZones");
            // 跨午夜的时段分两截画
            const tip = <span class="sr-only"> {a}–{b}</span>;
            return e > s ? [<span key={`${z.zone}${a}`} class="dp-armed" style={box(s, e)}>{label}{tip}</span>]
              : [<span key={`${z.zone}${a}a`} class="dp-armed" style={box(s, 1440)}>{label}{tip}</span>, <span key={`${z.zone}${a}b`} class="dp-armed" style={box(0, e)}>{label}</span>];
          }))}
          <i class="dp-now" style={{ left: pct(nowMin) }} />
        </div>
        <span class="muted">{props.today?.enabled ? t("ovScheduleOn") : t("ovScheduleOff")}</span>
      </div>
      <div class="dp-row" data-row="access">
        <b>{t("ovRowAccess")}</b>
        <div class="dp-lane">
          {props.authz.map((a) => <span key={a.id} class="dp-access" style={box(minOf(a.start), minOf(a.end) > minOf(a.start) ? minOf(a.end) : 1440)} title={`${a.name} ${a.start}–${a.end}`}>{a.name}<span class="sr-only"> {a.zones.length ? joinList(a.zones) : t("wholeSite")} {a.start}–{a.end}</span></span>)}
          <i class="dp-now" style={{ left: pct(nowMin) }} />
        </div>
        <span class="muted">{props.authz.length === 0 ? t("ovAccessNone") : activeAuthz.length ? t("ovAccessN", { n: props.authz.length, name: activeAuthz[0].name }) : t("ovAccessCount", { n: props.authz.length })}</span>
      </div>
      <div class="dp-row" data-row="patrol">
        <b>{t("ovRowPatrol")}</b>
        <div class="dp-lane">
          {runs.map((p, i) => <span key={i} class="dp-patrol" style={box(dayMin(p.at_ms), dayMin(p.end_ms ?? props.now) + 1)}>{nameOf(p.robot)}</span>)}
          <i class="dp-now" style={{ left: pct(nowMin) }} />
        </div>
        <span class="muted">{running ? t("ovPatrolN", { n: runs.length, id: nameOf(running.robot) }) : t("ovPatrolCount", { n: runs.length })}</span>
      </div>
      <div class="dp-row dp-nowrow"><span /><div class="dp-lane"><i class="mono" style={{ left: pct(nowMin) }}>{t("ovNowAt", { t: hm(props.now) })}</i></div><span /></div>
      <p class="muted small">{t("ovLegend")}</p>
    </div>
  );
}

function compare(a: number, b: number | undefined): string {
  if (b == null) return "";
  if (a > b) return t("homeMore", { n: a - b });
  if (a < b) return t("homeLess", { n: b - a });
  return t("homeSame");
}

/** 「需要你处理」那一栏:没处理的、不归值班的、不是 P3 通知。侧栏「概况」的数字也按它数(第 3 轮 config N7)。 */
export function homeTodo(alerts: Alert[]): Alert[] {
  return alerts.filter((a) => a.resolved_ms == null && !forGuard(a) && a.level !== "P3")
    .sort((a, b) => (a.level === b.level ? b.last_ms - a.last_ms : a.level < b.level ? -1 : 1));
}

/** P2-44:同一种提醒(说法一样、只是机器人不同)合成一条;顺序按第一次出现。 */
export function groupTodo(list: Alert[]): Alert[][] {
  const m = new Map<string, Alert[]>();
  for (const a of list) {
    const ad = advice(a.kind, a.detail);
    const k = ad ? `adv:${ad.say}` : `kind:${a.kind}:${a.title}`;
    const g = m.get(k);
    if (g) g.push(a); else m.set(k, [a]);
  }
  return [...m.values()];
}

/** 出发前检查没过,按那一项去哪页处理(第 2 轮 P0-01)。 */
export function preflightPage(a: Alert): AdminPage | undefined {
  const c = (a.context as { check?: string } | undefined)?.check;
  if (c === "home" || c === "localized") return "admin/localization";
  if (c === "nav_ready" || c === "storage" || c === "removable") return "admin/diag";
  return undefined;
}
