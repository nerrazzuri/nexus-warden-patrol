// 报警记录页(W44 第一期,设计 §4.5)。上面:本班出的事、还没处理、有人闯入三个数,上一班留的话(谁、几点),
// 下班前可以给下一班留话。筛选:本班 / 今天 / 选日期 × 全部 / 有人闯入 / 机器人需要帮忙 / 机器人掉线 × 只看没处理的。
// 每行:抓拍(录像那一刻的一帧)、时间、什么事、结论和谁处理的、看录像 / 去处理。技术类(给管理员的)不列。
import { siteStr, byText } from "./sitetext";
import { useEffect, useState } from "preact/hooks";
import { useStored } from "./stored";
import { AlertDetail, type ToastAction } from "./alertdetail";
import { alertHeadline, canHandleAlerts } from "./alertinfo";
import { AlertTestBar } from "./alerttest";
import { api, ApiError } from "./api";
import { hm, useDutySettings } from "./data";
import { t, type Key } from "./i18n";
import { shiftStart } from "./maplayers";
import { verdictText } from "./mappage";
import { forGuard, type Alert } from "./model";
import { dateInput, dayRange, recordingLink } from "./recordings";

const LIMIT = 500;
type Scope = "shift" | "today" | "date";
type Kind = "all" | "intrusion" | "help" | "offline";
const KINDS: Kind[] = ["intrusion", "help", "offline"];
interface Note { id: number; at_ms: number; author: string; text: string }

/** 能留话的(站点 HANDLE_ALERTS):管理员、保安、经理。 */
function canNote(role: string): boolean {
  return role === "admin" || role === "engineer" || role === "guard" || role === "owner";
}

export function AlarmLogPage(props: { now: number; role: string; me?: string }) {
  const [alerts, setAlerts] = useState<Alert[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [truncated, setTruncated] = useState(false);
  const [note, setNote] = useState<Note | null>(null);
  const [draft, setDraft] = useState("");
  const [err, setErr] = useState("");
  // P2-10:筛选条件记在这台浏览器上;种类能多选(一个都不选 = 全部)
  const [scope, setScope] = useStored<Scope>("nexwar.alarms.scope", "shift", (v): v is Scope => v === "shift" || v === "today" || v === "date");
  const [date, setDate] = useState(dateInput(props.now));
  const [kindList, setKinds] = useStored<Kind[]>("nexwar.alarms.kinds", [], (v): v is Kind[] => Array.isArray(v) && v.every((x) => KINDS.includes(x as Kind)));
  const kindSet = new Set(kindList);
  const [openOnly, setOpenOnly] = useStored<boolean>("nexwar.alarms.open", false, (v): v is boolean => typeof v === "boolean");
  const [detail, setDetail] = useState<string | null>(null);
  const [said, setSaidRaw] = useState("");
  // 第 2 轮 duty N8 残留(第 3 轮):在报警记录页关掉也给「撤销」按钮(原来只在页底一行字)
  const [sayAct, setSayAct] = useState<ToastAction | null>(null);
  const setSaid = (s: string, act?: ToastAction) => { setSaidRaw(s); setSayAct(act ?? null); };

  const pull = () => api<{ alerts: Alert[]; truncated?: boolean }>("GET", `/api/alerts?all=1&limit=${LIMIT}`)
    .then((d) => { setAlerts(d.alerts ?? []); setTruncated(!!d.truncated); setFailed(false); })
    // 第 4 轮 layout r3-N3 / N6:读不到不当成「没有报警」(计数写「–」,列表写正在重试)
    .catch(() => setFailed(true));
  // liang-d5 第 5 轮前:「今天」「选日期」按那天去站点查(原来只拿最近 500 条在这里筛,一个月前的那天是空的),
  // 一天超过 500 条能翻页
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
  const pullNote = () => api<{ latest: Note | null }>("GET", "/api/shift-notes").then((d) => setNote(d.latest ?? null)).catch(() => {});
  useEffect(() => { void pullNote(); }, []);

  const guardSees = (a: Alert) => forGuard(a) && a.level !== "P3" || a.kind === "authorized_person";
  const mine = (alerts ?? []).filter(guardSees);
  const dayRows = day && day.key === dayKey ? day.alerts : null;
  const source = scope === "shift" ? alerts : dayRows;
  const inScope = scope === "shift" ? mine.filter((a) => a.first_ms >= since && a.first_ms < until) : (dayRows ?? []).filter(guardSees);
  const shown = inScope
    .filter((a) => kindSet.size === 0 || [...kindSet].some((k) => (k === "intrusion" ? a.audience === "intrusion" || a.audience === "fire" : a.audience === k)))
    .filter((a) => !openOnly || a.resolved_ms == null)
    .sort((a, b) => b.first_ms - a.first_ms);
  const inShift = mine.filter((a) => a.first_ms >= shift);

  async function leave() {
    setErr("");
    try {
      await api("POST", "/api/shift-notes", { text: draft });
      setDraft("");
      await pullNote();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : String(e));
    }
  }

  const scopes: { v: Scope; key: Key }[] = [{ v: "shift", key: "alShift" }, { v: "today", key: "alToday" }, { v: "date", key: "alPickDate" }];
  const kinds: { v: Kind; key: Key }[] = [{ v: "all", key: "alAll" }, { v: "intrusion", key: "alIntrusion" }, { v: "help", key: "alHelp" }, { v: "offline", key: "alOffline" }];
  return (
    <div class="alarmlog">
      <AlertTestBar role={props.role} onCleared={() => setAlerts((a) => (a ?? []).filter((x) => !x.title.startsWith("测试：")))} />
      <div class="sum">
        <div class="box"><b>{alerts == null ? "–" : inShift.length}</b><span>{t("alSumShift", { t: hm(shift) })}</span></div>
        <div class="box o"><b>{alerts == null ? "–" : inShift.filter((a) => a.resolved_ms == null).length}</b><span>{t("alSumOpen")}</span></div>
        <div class="box r"><b>{alerts == null ? "–" : inShift.filter((a) => a.audience === "intrusion").length}</b><span>{t("alSumIntrusion")}</span></div>
        <div class="note">
          {/* P1-20:自己刚写的不叫「上一班留言」;能改(再发一条顶替,先把原文放进框里) */}
          <h4>{note ? t(note.author === props.me ? "alNoteMine" : "alNoteFrom", { who: note.author, t: hm(note.at_ms) }) : t("alNoteNone")}</h4>
          {note && <p>{note.text}</p>}
          {note && note.author === props.me && canNote(props.role) && !draft && (
            <button type="button" class="btn sm" onClick={() => setDraft(note.text)}>{t("alNoteEdit")}</button>
          )}
          {canNote(props.role) && (
            <div class="note-write">
              <textarea rows={2} maxLength={500} placeholder={t("alNoteHint")} value={draft}
                onInput={(e) => setDraft((e.target as HTMLTextAreaElement).value)} />
              <button type="button" class="btn sm" disabled={!draft.trim()} onClick={leave}>{t("alNoteSave")}</button>
            </div>
          )}
          {err && <p class="error">{err}</p>}
        </div>
      </div>
      <div class="filters">
        {scopes.map((s) => (
          <button key={s.v} type="button" class={scope === s.v ? "chip on" : "chip"} aria-pressed={scope === s.v} onClick={() => setScope(s.v)}>{t(s.key)}</button>
        ))}
        {scope === "date" && <input type="date" value={date} max={dateInput(props.now)} onChange={(e) => setDate((e.target as HTMLInputElement).value)} />}
        <span class="sep" />
        {kinds.map((k) => {
          const on = k.v === "all" ? kindSet.size === 0 : kindSet.has(k.v);
          return <button key={k.v} type="button" class={on ? "chip on" : "chip"} aria-pressed={on} data-kind={k.v}
            onClick={() => setKinds(k.v === "all" ? [] : on ? kindList.filter((x) => x !== k.v) : [...kindList, k.v])}>{t(k.key)}</button>;
        })}
        <span class="sep" />
        <button type="button" class={openOnly ? "chip on" : "chip"} aria-pressed={openOnly} onClick={() => setOpenOnly(!openOnly)}>{t("alOpenOnly")}</button>
      </div>
      {scope === "shift" && truncated && <p class="muted small">{t("alTruncated", { n: LIMIT })}</p>}
      {scope !== "shift" && day && day.key === dayKey && day.total > LIMIT && (
        <p class="row small al-pages" data-al-pages="1">
          <span class="muted">{t("alPageOf", { a: page * LIMIT + 1, b: Math.min((page + 1) * LIMIT, day.total), n: day.total })}</span>
          <button type="button" class="btn sm" disabled={page === 0} onClick={() => setPage(page - 1)}>{t("alPagePrev")}</button>
          <button type="button" class="btn sm" disabled={(page + 1) * LIMIT >= day.total} onClick={() => setPage(page + 1)}>{t("alPageNext")}</button>
        </p>
      )}
      <div class="list">
        {source == null && <p class={(scope === "shift" ? failed : dayFailed) ? "empty warn" : "empty"} data-load-failed={(scope === "shift" ? failed : dayFailed) ? "1" : undefined}>{t((scope === "shift" ? failed : dayFailed) ? "loadRetry" : "loading")}</p>}
        {source != null && shown.length === 0 && <p class="empty">{t("alNone")}</p>}
        {shown.map((a) => <Row key={a.key} a={a} canHandle={canHandleAlerts(props.role)} onOpen={() => setDetail(a.key)} />)}
      </div>
      {said && <p class="muted small" role="status">{said}
        {sayAct && <> <button type="button" class="btn sm" data-undo="1" onClick={() => { const r = sayAct.run; setSayAct(null); r(); }}>{sayAct.label}</button></>}</p>}
      {detail && alerts?.find((a) => a.key === detail) && (
        <AlertDetail a={alerts.find((a) => a.key === detail)!} role={props.role} now={props.now} units={[]}
          onClose={() => setDetail(null)} refresh={pull} say={setSaid} />
      )}
    </div>
  );
}

function Row({ a, onOpen, canHandle }: { a: Alert; onOpen: () => void; canHandle: boolean }) {
  const [bad, setBad] = useState(false);
  const open = a.resolved_ms == null;
  const site = a.robot === "site" || a.robot.includes(":");
  const tone = a.audience === "intrusion" || a.audience === "fire" ? "r" : a.audience === "offline" ? "g" : "o";
  return (
    <div class={open ? "it open" : "it"}>
      {site || bad ? <span class="shot none" /> : (
        <img class="shot" alt="" loading="lazy" src={`/api/recordings/frame?robot=${encodeURIComponent(a.robot)}&camera=front&t=${a.first_ms}`}
          onError={() => setBad(true)} />
      )}
      <time class="mono">{hm(a.first_ms)}</time>
      <div class="what">
        <h5 class={tone}><button type="button" class="linkish" onClick={onOpen}>{alertHeadline(a)}</button></h5>
        {(a.detail || a.context?.where) && <p>{[a.context?.where && !a.context?.zone ? t("atWhere", { w: a.context.where }) : "", a.detail ? siteStr(a.detail) : ""].filter(Boolean).join(" · ")}</p>}
      </div>
      <div class="res">
        {/* 第 3 轮 duty N8:有人接手了写谁在处理;处理完带上写的备注 */}
        {open ? (a.acked_by ? t("dutyTakenBy", { who: byText(a.acked_by) }) : t("evOpen")) : verdictText(a)}
        {!open && <small>{[byText(a.resolved_by), a.resolved_ms ? hm(a.resolved_ms) : ""].filter(Boolean).join(" · ")}</small>}
        {!open && (a.context as { note?: string } | undefined)?.note && <small class="al-note" data-note="1">{(a.context as { note?: string }).note}</small>}
      </div>
      <div>
        {/* 第 2 轮 P0-20:只读账号处理不了,按钮就叫「详情」、不用蓝色主按钮 */}
        {open ? <button type="button" class={canHandle ? "btn sm primary" : "btn sm"} onClick={onOpen}>{t(canHandle ? "alGoHandle" : "alDetails")}</button>
          // 第 4 轮 r3-duty-N7:摄像头掉线、站点自己的报警没有机器人录像,不给「看录像」
          : hasRecording(a) ? <a class="btn sm" href={recordingLink(a)}>{t("alSeeRec")}</a> : null}
      </div>
    </div>
  );
}

/** 这条报警有没有机器人录像可看(摄像头、站点自己的报警没有)。 */
export function hasRecording(a: { robot: string; kind: string }): boolean {
  return a.robot !== "site" && !a.robot.startsWith("cctv:") && a.kind !== "cctv_offline";
}
