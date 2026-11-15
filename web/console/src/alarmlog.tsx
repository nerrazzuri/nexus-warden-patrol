// 报警记录(redesign 第五期 G-records;W44 第一期起的老页换样子):记录与录像的「报警」标签。
// 左 筛选(时间:本班 / 今天 / 选日期;类型多选带数;状态 全部 / 未关闭 / 已关闭;机器人 / 摄像头;清除)+ 本班三个数;
// 中 「本班 N 条报警」+ 导出表格 + 一张表(画面、时间、事件、位置、负责人、结果);右 选中那条(录像、经过、重新打开)。
// 没关的「去处理」跳值班页那件事(处理在值班页做,不弹窗)。交班留言在旁边的「交班留言」标签。技术类不列。
import { useEffect, useState } from "preact/hooks";
import { EventPanel, hasRecording, placeOf, type ToastAction } from "./alertdetail";
import { alertHeadline, canHandleAlerts } from "./alertinfo";
import { AlertTestBar } from "./alerttest";
import { api } from "./api";
import { hm, nameOf, useDutySettings } from "./data";
import { t, type Key } from "./i18n";
import { shiftStart } from "./maplayers";
import { verdictText } from "./mappage";
import { autoResolved, forGuard, type Alert } from "./model";
import { dateInput, dayRange } from "./recordings";
import { DateBox } from "./recpage";
import { SubTabs } from "./shell";
import { Sign } from "./signs";
import { byText, siteText } from "./sitetext";
import { useStored } from "./stored";

export { hasRecording } from "./alertdetail";

const LIMIT = 500;
type Scope = "shift" | "today" | "date";
type Kind = "intrusion" | "help" | "offline";
type Status = "all" | "open" | "closed";
const KINDS: Kind[] = ["intrusion", "help", "offline"];
const KIND_KEY: Record<Kind, Key> = { intrusion: "evIntrusionFire", help: "alHelp", offline: "alOffline" };

/** 读不到报警时多久再试一次。 */
export const RETRY_MS = 3_000;

const kindOf = (a: Alert): Kind | null =>
  a.audience === "intrusion" || a.audience === "fire" ? "intrusion" : a.audience === "help" ? "help" : a.audience === "offline" ? "offline" : null;
const sourceName = (r: string) => (r === "site" ? t("evSite") : r.startsWith("cctv:") ? r.slice(5) : nameOf(r));

/** 负责人一栏:没关的写谁接手(没人 = 「无人」),关了的写谁关的(站点自己关的写「系统」)。 */
export function ownerOf(a: Alert): string | null {
  if (a.resolved_ms == null) return a.acked_by ? byText(a.acked_by) : null;
  if (autoResolved(a)) return t("evSystem");
  return byText(a.resolved_by || a.acked_by) || "—";
}
/** 结果一栏的字(「去处理」按钮另外放)。 */
export function outcomeOf(a: Alert): string {
  if (a.resolved_ms == null) return a.acked_by ? t("evInProgress") : t("evOpen");
  return autoResolved(a) ? t("evAutoRecovered") : verdictText(a) || t("monResolved");
}

/** 导出表格(CSV,Excel 能开):筛完的这些行。 */
export function alarmsCsv(rows: Alert[]): string {
  const q = (s: string) => (/[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s);
  const head = [t("evColTime"), t("evColEvent"), t("evColWhere"), t("evColOwner"), t("evColOutcome"), t("incNote")];
  const lines = rows.map((a) => {
    const d = new Date(a.first_ms);
    const note = (a.context as { note?: string } | undefined)?.note;
    return [`${dateInput(a.first_ms)} ${d.toTimeString().slice(0, 8)}`, alertHeadline(a), placeOf(a), ownerOf(a) ?? t("evNone"), outcomeOf(a), note ? siteText(note).text : ""].map(q).join(",");
  });
  return "﻿" + [head.map(q).join(","), ...lines].join("\r\n");
}

export function AlarmLogPage(props: { now: number; role: string; me?: string }) {
  const [alerts, setAlerts] = useState<Alert[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [truncated, setTruncated] = useState(false);
  // P2-10:筛选条件记在这台浏览器上;种类能多选(一个都不选 = 全部)
  const [scope, setScope] = useStored<Scope>("nexwar.alarms.scope", "shift", (v): v is Scope => v === "shift" || v === "today" || v === "date");
  const [date, setDate] = useState(dateInput(props.now));
  const [kindList, setKinds] = useStored<Kind[]>("nexwar.alarms.kinds", [], (v): v is Kind[] => Array.isArray(v) && v.every((x) => KINDS.includes(x as Kind)));
  const kindSet = new Set(kindList);
  const [status, setStatus] = useStored<Status>("nexwar.alarms.status", "all", (v): v is Status => v === "all" || v === "open" || v === "closed");
  const [source, setSource] = useState("");
  const [sel, setSel] = useState<string | null>(null);
  const [said, setSaidRaw] = useState("");
  const [sayAct, setSayAct] = useState<ToastAction | null>(null);
  const setSaid = (s: string, act?: ToastAction) => { setSaidRaw(s); setSayAct(act ?? null); };

  const pull = () => api<{ alerts: Alert[]; truncated?: boolean }>("GET", `/api/alerts?all=1&limit=${LIMIT}`)
    .then((d) => { setAlerts(d.alerts ?? []); setTruncated(!!d.truncated); setFailed(false); })
    // 第 4 轮 layout r3-N3 / N6:读不到不当成「没有报警」(计数写「–」,列表写正在重试)
    .catch(() => setFailed(true));
  // liang-d5 第 5 轮前:「今天」「选日期」按那天去站点查,一天超过 500 条能翻页
  const [page, setPage] = useState(0);
  const [day, setDay] = useState<{ key: string; alerts: Alert[]; total: number } | null>(null);
  const [dayFailed, setDayFailed] = useState(false);
  const duty = useDutySettings();
  const shift = shiftStart(props.now, duty.shift_hours);
  const today = dayRange(dateInput(props.now))!;
  const picked = dayRange(date);
  const [since, until] = scope === "shift" ? [shift, Infinity] : scope === "today" ? [today.since, today.until]
    : picked ? [picked.since, picked.until] : [today.since, today.until];
  const dayKey = scope === "shift" ? "" : `${since}-${until}-${page}`;
  const pullDay = () => {
    if (!dayKey) return Promise.resolve();
    return api<{ alerts: Alert[]; total: number }>("GET", `/api/alerts?since=${since}&until=${until}&limit=${LIMIT}&offset=${page * LIMIT}`)
      .then((d) => { setDay({ key: dayKey, alerts: d.alerts ?? [], total: d.total ?? 0 }); setDayFailed(false); })
      .catch(() => setDayFailed(true));
  };
  useEffect(() => { setPage(0); }, [scope, date]);
  useEffect(() => { void pullDay(); }, [dayKey]);
  useEffect(() => {
    void pull();
    const id = window.setInterval(() => { void pull(); void pullDay(); }, 30_000);
    return () => window.clearInterval(id);
  }, [dayKey]);
  // minor #30(r5-layout-N1):读不到的时候 3 秒再试一次,网一通马上回来
  useEffect(() => {
    if (!failed && !dayFailed) return;
    const id = window.setInterval(() => { if (failed) void pull(); if (dayFailed) void pullDay(); }, RETRY_MS);
    return () => window.clearInterval(id);
  }, [failed, dayFailed, dayKey]);

  const guardSees = (a: Alert) => forGuard(a) && a.level !== "P3" || a.kind === "authorized_person";
  const mine = (alerts ?? []).filter(guardSees);
  const dayRows = day && day.key === dayKey ? day.alerts : null;
  const loaded = scope === "shift" ? alerts : dayRows;
  const loadFailed = scope === "shift" ? failed : dayFailed;
  const inScope = scope === "shift" ? mine.filter((a) => a.first_ms >= since && a.first_ms < until) : (dayRows ?? []).filter(guardSees);
  const sources = [...new Set(inScope.map((a) => a.robot))].sort();
  const shown = inScope
    .filter((a) => kindSet.size === 0 || (kindOf(a) != null && kindSet.has(kindOf(a)!)))
    .filter((a) => status === "all" || (status === "open") === (a.resolved_ms == null))
    .filter((a) => !source || a.robot === source)
    .sort((a, b) => b.first_ms - a.first_ms);
  const inShift = mine.filter((a) => a.first_ms >= shift);
  // UIUX-E003:顶栏写「报警 3」、本班却是 0 条 —— 说清还有本班之前没处理的
  const olderOpen = mine.filter((a) => a.first_ms < shift && a.resolved_ms == null);
  const focus = shown.find((a) => a.key === sel) ?? shown[0] ?? null;
  const filtered = kindSet.size > 0 || status !== "all" || !!source;

  const exportCsv = () => {
    const blob = new Blob([alarmsCsv(shown)], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `alarms-${scope === "date" ? date : dateInput(props.now)}.csv`;
    link.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  const one = shown.length === 1;
  const title = scope === "shift" ? t(one ? "evTitleShift1" : "evTitleShift", { n: shown.length })
    : scope === "today" ? t(one ? "evTitleToday1" : "evTitleToday", { n: shown.length })
      : t(one ? "evTitleDate1" : "evTitleDate", { n: shown.length, d: date });
  const range = scope === "shift" ? t("evRangeNow", { a: `${dateInput(shift)} ${hm(shift)}` })
    : scope === "today" ? t("evRangeNow", { a: `${dateInput(props.now)} 00:00` }) : t("evRangeDay", { d: date });
  const can = canHandleAlerts(props.role);
  return (
    <div class="ev alarmlog">
      <aside class="ev-left" aria-label={t("evTime")}>
        <SubTabs page="alarms" role={props.role} rail />
        <label class="ev-f">{t("evTime")}
          <select value={scope} data-scope="1" onChange={(e) => setScope(e.currentTarget.value as Scope)}>
            <option value="shift">{t("evShiftSince", { t: hm(shift) })}</option>
            <option value="today">{t("alToday")}</option>
            <option value="date">{t("alPickDate")}</option>
          </select>
        </label>
        {scope === "date" && <DateBox value={date} max={dateInput(props.now)} onChange={setDate} />}
        <p class="ev-range mono">{range}</p>
        <fieldset class="ev-f">
          <legend>{t("evType")}</legend>
          {KINDS.map((k) => (
            <label key={k} class="ev-check"><input type="checkbox" data-kind={k} checked={kindSet.has(k)}
              onChange={() => setKinds(kindSet.has(k) ? kindList.filter((x) => x !== k) : [...kindList, k])} />
              {t(KIND_KEY[k])} · {inScope.filter((a) => kindOf(a) === k).length}</label>
          ))}
        </fieldset>
        <fieldset class="ev-f">
          <legend>{t("evStatus")}</legend>
          {(["all", "open", "closed"] as const).map((s) => (
            <label key={s} class="ev-check"><input type="radio" name="ev-status" data-status={s} checked={status === s} onChange={() => setStatus(s)} />
              {t(s === "all" ? "evAll" : s === "open" ? "evOpenS" : "evClosedS")}</label>
          ))}
        </fieldset>
        <label class="ev-f">{t("evSource")}
          <select value={source} data-source="1" onChange={(e) => setSource(e.currentTarget.value)}>
            <option value="">{t("evAll")}</option>
            {sources.map((r) => <option key={r} value={r}>{sourceName(r)}</option>)}
          </select>
        </label>
        <button type="button" class="btn ev-clear" disabled={!filtered}
          onClick={() => { setKinds([]); setStatus("all"); setSource(""); }}>{t("evClear")}</button>
        <div class="ev-sum" aria-label={t("evThisShift")}>
          <h3>{t("evThisShift")}</h3>
          <div><b>{alerts == null ? "–" : inShift.length}</b><span>{t("evSumAlarms")}</span></div>
          <div class={inShift.some((a) => a.resolved_ms == null) ? "has" : ""}><b>{alerts == null ? "–" : inShift.filter((a) => a.resolved_ms == null).length}</b><span>{t("evSumOpen")}</span></div>
          <div><b>{alerts == null ? "–" : inShift.filter((a) => a.verdict === "false_alarm").length}</b><span>{t("evSumFalse")}</span></div>
        </div>
      </aside>

      <section class="ev-main">
        <AlertTestBar role={props.role} onCleared={() => setAlerts((a) => (a ?? []).filter((x) => !x.title.startsWith("测试：")))} />
        <header class="ev-head">
          <h1>{loaded == null ? t("loading") : title}</h1>
          <button type="button" class="btn" disabled={!shown.length} onClick={exportCsv} data-export="1">{t("evExport")}</button>
        </header>
        {scope === "shift" && truncated && <p class="muted small ev-note">{t("alTruncated", { n: LIMIT })}</p>}
        {scope === "shift" && olderOpen.length > 0 && (
          <p class="row small al-older ev-note" data-al-older="1">
            <span>{t("alOlderOpen", { n: olderOpen.length })}</span>
            <button type="button" class="btn sm" onClick={() => {
              const first = Math.min(...olderOpen.map((a) => a.first_ms));
              setStatus("open");
              if (first >= today.since) setScope("today"); else { setDate(dateInput(first)); setScope("date"); }
            }}>{t("alOlderShow")}</button>
          </p>
        )}
        {scope !== "shift" && day && day.key === dayKey && day.total > LIMIT && (
          <p class="row small al-pages ev-note" data-al-pages="1">
            <span class="muted">{t("alPageOf", { a: page * LIMIT + 1, b: Math.min((page + 1) * LIMIT, day.total), n: day.total })}</span>
            <button type="button" class="btn sm" disabled={page === 0} onClick={() => setPage(page - 1)}>{t("alPagePrev")}</button>
            <button type="button" class="btn sm" disabled={(page + 1) * LIMIT >= day.total} onClick={() => setPage(page + 1)}>{t("alPageNext")}</button>
          </p>
        )}
        {loaded == null && <p class={loadFailed ? "empty warn" : "empty"} data-load-failed={loadFailed ? "1" : undefined}>{t(loadFailed ? "loadRetry" : "loading")}</p>}
        {loaded != null && shown.length === 0 && <p class="empty">{t("alNone")}</p>}
        {shown.length > 0 && (
          <table class="ev-table">
            <thead><tr>
              <th>{t("evColVideo")}</th><th>{t("evColTime")}</th><th>{t("evColEvent")}</th><th>{t("evColWhere")}</th><th>{t("evColOwner")}</th><th>{t("evColOutcome")}</th>
            </tr></thead>
            <tbody>
              {shown.map((a) => <Row key={a.key} a={a} on={focus?.key === a.key} can={can} onPick={() => setSel(a.key)} />)}
            </tbody>
          </table>
        )}
        {said && <p class="muted small" role="status">{said}
          {sayAct && <> <button type="button" class="btn sm" data-undo="1" onClick={() => { const r = sayAct.run; setSayAct(null); r(); }}>{sayAct.label}</button></>}</p>}
      </section>

      <aside class="ev-side">
        {focus ? <EventPanel a={focus} role={props.role} now={props.now} refresh={pull} say={setSaid} />
          : <p class="empty muted">{t("evPick")}</p>}
      </aside>
    </div>
  );
}

function Row({ a, on, can, onPick }: { a: Alert; on: boolean; can: boolean; onPick: () => void }) {
  const [bad, setBad] = useState(false);
  const open = a.resolved_ms == null;
  const owner = ownerOf(a);
  const sign = a.level === "P1" ? "bad" : a.level === "P2" && open ? "warn" : null;
  return (
    <tr class={`it${open ? " open" : ""}${open && !a.acked_by ? " unowned" : ""}${on ? " on" : ""}`} data-key={a.key} aria-selected={on} onClick={onPick}>
      <td class="ev-shot">
        {!hasRecording(a) || bad ? <span class="shot none" /> : (
          <img class="shot" alt="" loading="lazy" src={`/api/recordings/frame?robot=${encodeURIComponent(a.robot)}&camera=front&t=${a.first_ms}`}
            onError={() => setBad(true)} />
        )}
      </td>
      <td class="mono">{hm(a.first_ms)}</td>
      <td class="ev-what">
        <button type="button" class="linkish" onClick={(e) => { e.stopPropagation(); onPick(); }}>
          {open && sign && <Sign kind={sign} />}<span class={open ? "strong" : ""}>{alertHeadline(a)}</span>
        </button>
      </td>
      <td>{placeOf(a) || (a.robot !== "site" && !a.robot.includes(":") ? nameOf(a.robot) : "—")}</td>
      <td class={owner == null ? "ev-none" : ""}>{owner ?? t("evNone")}</td>
      <td class="res">
        {open && !a.acked_by && can
          ? <a href={`#/duty?alarm=${encodeURIComponent(a.key)}`} class="ev-respond" onClick={(e) => e.stopPropagation()}>{t("evRespond")}</a>
          : outcomeOf(a)}
      </td>
    </tr>
  );
}
