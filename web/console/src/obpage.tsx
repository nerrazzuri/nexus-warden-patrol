// 1.1-5 电子值班簿(记录与录像的第四个标签):左 写一条(类别、内容、补记时间、哪台机器人);
// 中 一天的值班簿 —— 手写的加上站点自己记的(报警、确认、关闭、机器人巡检、外部报警器、交班留言),按时间排。
// 只追加:写错了点「更正」另写一条;原来那条划掉、写「已由 #n 更正」。「打印 / PDF」开站点出的能打印的那一页。
// 设计 docs/1.1-5-值班簿-设计.md。
import { useEffect, useState } from "preact/hooks";
import { api, ApiError } from "./api";
import { hm } from "./data";
import { lang, t, type Key } from "./i18n";
import { canNote } from "./notes";
import { dateInput } from "./recordings";
import { SubTabs } from "./shell";

export interface ObEntry {
  at_ms: number; source: "manual" | "alarm" | "patrol" | "external" | "handover"; category: string; text: string;
  author: string; robot: string; id?: number; corrects?: number; corrected_by?: number; alert?: string;
}
export const OB_CATEGORIES = ["duty_on", "duty_off", "patrol", "incident", "visitor", "handover", "maintenance", "observation", "other"] as const;
const CAT_KEY: Record<string, Key> = {
  duty_on: "obCatDutyOn", duty_off: "obCatDutyOff", patrol: "obCatPatrol", incident: "obCatIncident", visitor: "obCatVisitor",
  handover: "obCatHandover", maintenance: "obCatMaint", observation: "obCatObs", other: "obCatOther", alarm: "obCatAlarm",
  external: "obCatExternal",
};
type Filter = "all" | "manual" | "auto";

/** 本地那一天的 [0 点, 第二天 0 点)。 */
export function dayRange(day: string): { since: number; until: number } {
  const [y, m, d] = day.split("-").map(Number);
  const a = new Date(y, m - 1, d).getTime();
  return { since: a, until: new Date(y, m - 1, d + 1).getTime() };
}

export function ObPage(props: { role: string; me?: string; now?: number }) {
  const today = dateInput(props.now ?? Date.now());
  const [day, setDay] = useState(today);
  const [rows, setRows] = useState<ObEntry[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [filter, setFilter] = useState<Filter>("all");
  const [cat, setCat] = useState<string>("observation");
  const [text, setText] = useState("");
  const [when, setWhen] = useState("");
  const [fix, setFix] = useState<ObEntry | null>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const r = dayRange(day);
  const q = `since=${r.since}&until=${r.until}&lang=${lang.value === "zh" ? "zh" : "en"}`;
  const pull = () => api<{ entries: ObEntry[] }>("GET", `/api/ob?${q}`)
    .then((d) => { setRows(d.entries ?? []); setFailed(false); })
    .catch(() => setFailed(true));
  useEffect(() => { setRows(null); void pull(); }, [q]);

  async function save() {
    setErr("");
    setBusy(true);
    try {
      const body: Record<string, unknown> = { category: cat, text };
      if (when) body.at_ms = new Date(when).getTime();
      if (fix?.id != null) body.corrects = fix.id;
      if (fix?.alert) body.alert = fix.alert;
      await api("POST", "/api/ob", body);
      setText("");
      setWhen("");
      setFix(null);
      await pull();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }
  const write = canNote(props.role);
  const shown = (rows ?? []).filter((x) => filter === "all" || (filter === "manual" ? x.source === "manual" : x.source !== "manual"));
  return (
    <div class="ev notes ob">
      <aside class="ev-left">
        <SubTabs page="ob" role={props.role} rail />
        {write ? (
          <div class="ev-f notes-write ob-write" data-ob-write="1">
            {fix && <p class="ob-fixing" data-ob-fixing={fix.id}>{t("obFixing", { n: String(fix.id) })}
              <button type="button" class="linkish" onClick={() => setFix(null)}>{t("cancel")}</button></p>}
            <label for="ob-cat">{t("obCategory")}</label>
            <select id="ob-cat" name="category" value={cat} onChange={(e) => setCat(e.currentTarget.value)}>
              {OB_CATEGORIES.map((c) => <option key={c} value={c}>{t(CAT_KEY[c])}</option>)}
            </select>
            <label for="ob-text">{t("obText")}</label>
            <textarea id="ob-text" name="text" rows={5} maxLength={1000} placeholder={t("obTextHint")} value={text}
              onInput={(e) => setText((e.target as HTMLTextAreaElement).value)} />
            <label for="ob-when">{t("obWhen")}</label>
            <input id="ob-when" name="when" type="datetime-local" value={when} onInput={(e) => setWhen(e.currentTarget.value)} />
            <p class="muted small">{t("obWhenHint")}</p>
            <button type="button" class="btn primary" disabled={!text.trim() || busy} onClick={() => void save()}>{t("obSave")}</button>
            {err && <p class="error" role="alert">{err}</p>}
            <p class="muted small">{t("obAppendOnly")}</p>
          </div>
        ) : <p class="muted small">{t("notesReadOnly")}</p>}
      </aside>
      <section class="ev-main notes-main">
        <header class="ev-head ob-head">
          <div>
            <h1>{t("obTitle")}</h1>
            <p class="muted small">{t("obSub")}</p>
          </div>
          <div class="ob-tools">
            <input type="date" name="day" aria-label={t("obDay")} value={day} max={today} onInput={(e) => e.currentTarget.value && setDay(e.currentTarget.value)} />
            <div class="seg" role="group" aria-label={t("obShow")}>
              {(["all", "manual", "auto"] as Filter[]).map((f) => (
                <button key={f} type="button" aria-pressed={filter === f} onClick={() => setFilter(f)}>
                  {t(f === "all" ? "obAll" : f === "manual" ? "obManual" : "obAuto")}</button>
              ))}
            </div>
            <a class="btn" data-ob-print="1" href={`/api/ob/print?${q}`} target="_blank" rel="noopener">{t("obPrint")}</a>
          </div>
        </header>
        {rows == null && <p class={failed ? "empty warn" : "empty"}>{t(failed ? "loadRetry" : "loading")}</p>}
        {rows != null && shown.length === 0 && <p class="empty">{t("obNone")}</p>}
        {rows != null && shown.length > 0 && (
          <table class="ob-table">
            <thead><tr><th>{t("obColTime")}</th><th>{t("obColNo")}</th><th>{t("obCategory")}</th><th>{t("obText")}</th><th>{t("obColRobot")}</th><th>{t("obColBy")}</th><th /></tr></thead>
            <tbody>
              {shown.map((x, i) => (
                <tr key={`${x.source}-${x.id ?? i}-${x.at_ms}`} class={x.corrected_by != null ? "ob-fixed" : x.source === "manual" ? "" : "ob-auto"}
                  data-ob-row={x.id ?? undefined} data-ob-source={x.source}>
                  <td class="mono">{hm(x.at_ms)}</td>
                  <td class="mono">{x.id != null ? `#${x.id}` : ""}</td>
                  <td>{t(CAT_KEY[x.category] ?? "obCatOther")}</td>
                  <td>
                    {x.corrects != null && <b>{t("obCorrectionOf", { n: String(x.corrects) })} </b>}
                    <span class="ob-text">{x.text}</span>
                    {x.corrected_by != null && <small class="muted"> {t("obCorrectedBy", { n: String(x.corrected_by) })}</small>}
                  </td>
                  <td>{x.robot}</td>
                  <td>{x.author}{x.author && x.author === props.me ? ` (${t("notesMine")})` : ""}</td>
                  <td>{write && x.source === "manual" && x.corrected_by == null && (
                    <button type="button" class="linkish" data-ob-fix={x.id} onClick={() => { setFix(x); setCat(x.category); setText(x.text); }}>{t("obFix")}</button>)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}
