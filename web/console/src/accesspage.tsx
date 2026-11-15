// 授权和临时撤防页(W44 第二期,设计 §5.1「授权和临时撤防」;原来的「名单」页):授权期间机器人在这些防区看到人不报警,只记一笔。
// 上面:现在生效的授权(谁、在哪、到几点),能提前结束;大按钮「加一个授权」(每周重复,或只这一天);全部授权;
// 临时撤防单独一块(选防区和结束时间,到点自动恢复)。人脸、车牌名单不在这一轮(设计 §2)。
import { useEffect, useState } from "preact/hooks";
import { api, ApiError, enc } from "./api";
import { hm, siteDown } from "./data";
import { Confirm } from "./dialogs";
import { Sign } from "./signs";
import { t, type Key, joinList } from "./i18n";

type Say = (s: string) => void;
export interface Authz {
  id: number; name: string; zones: string[]; days: number; start: string; end: string; until_ms: number | null; note: string;
  created_by: string; active_now?: boolean; on_today?: boolean;
}
interface ModeView { mode: string; label?: string; prev_mode?: string; until_ms?: number | null; visitor_zones?: string[]; zones?: { zone: string }[] }

const DAY_KEYS: Key[] = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"];
const VISITOR_HOURS = [1, 2, 4, 8, 24];

export function daysText(days: number): string {
  if (days === 127) return t("everyDay");
  if (days === 0b0011111) return t("weekdays");
  if (days === 0b1100000) return t("weekends");
  return DAY_KEYS.filter((_, i) => days >> i & 1).map((k) => t(k)).join(", ");
}

function errText(e: unknown): string {
  return t("failed", { why: e instanceof ApiError ? e.message : String(e) });
}

const where = (a: Authz) => (a.zones.length ? joinList(a.zones) : t("wholeSite"));

export function AccessPage({ say, now }: { say: Say; now: number }) {
  const [rows, setRows] = useState<Authz[]>([]);
  const [mode, setMode] = useState<ModeView | null>(null);
  const [showTemp, setShowTemp] = useState(false);
  const [ending, setEnding] = useState<Authz | null>(null);
  const [removing, setRemoving] = useState<Authz | null>(null);
  void now;
  const load = () => api<{ authorizations: Authz[] }>("GET", "/api/lists/authorizations").then((d) => setRows(d.authorizations ?? [])).catch((e) => say(errText(e)));
  const loadMode = () => api<ModeView>("GET", "/api/mode").then(setMode).catch(() => setMode(null));
  useEffect(() => { void load(); void loadMode(); }, []);
  const zones = (mode?.zones ?? []).map((z) => z.zone);
  const live = rows.filter((r) => r.active_now);
  const visitorOn = mode?.mode === "visitor";

  async function post(path: string, body: unknown) {
    try {
      const d = await api<{ authorizations?: Authz[] }>("POST", path, body);
      if (d.authorizations) setRows(d.authorizations);
      else void load();
    } catch (e) {
      say(errText(e));
    }
  }
  const status = [live.length === 0 ? t("acStNone") : live.length === 1 ? t("acStActive1", { who: live[0].name, t: live[0].end }) : t("acStActiveN", { n: live.length }),
    visitorOn && mode?.until_ms ? t("acStVisitor", { t: hm(mode.until_ms) }) : ""].filter(Boolean).join(" ");
  const today = (new Date().getDay() + 6) % 7;
  const ask = (x: Authz | null, text: string, yes: string, go: () => void, danger = false) => x && (
    <div class="rb-ask ac-ask" role="group">
      <p>{text}</p>
      <span class="rb-row">
        <button type="button" class={danger ? "btn danger" : "btn primary"} onClick={go}>{yes}</button>
        <button type="button" class="btn" onClick={() => { setEnding(null); setRemoving(null); }}>{t("cancel")}</button>
      </span>
    </div>
  );

  return (
    <section class="sp access ac">
      <header class="sp-head">
        <h1>{t("tabAccess")}</h1>
        <p class="sp-status"><Sign kind={live.length || visitorOn ? "info" : "ok"} /><span>{status}</span></p>
        {mode && <button type="button" class="btn" aria-expanded={showTemp || visitorOn} onClick={() => setShowTemp(!showTemp)}>{t("acTempBtn")}</button>}
      </header>
      <div class="sp-body ac-body">
        <div class="sp-main">
          <section class="sp-sec acc-now">
            <h2 class="sp-h"><span>{t("accNow")}</span></h2>
            <dl class="ac-now">
              <dt>{t("acRowAccess")}</dt>
              <dd>
                {live.length === 0 ? <span class="muted">{t("accNowNone")}</span> : (
                  <ul class="plain">
                    {live.map((a) => (
                      <li key={a.id} class="ac-live">
                        <span><b>{a.name}</b> · {where(a)} · <span class="mono">{a.start} → {a.end}</span><br /><small class="muted">{t("acRowAccessSub")}</small></span>
                        <button type="button" class="btn" onClick={() => { setRemoving(null); setEnding(a); }}>{t("accEndNow")}</button>
                      </li>
                    ))}
                  </ul>
                )}
                {ask(ending, t("accEndConfirm", { name: ending?.name ?? "" }), t("accEndYes"), () => { const a = ending!; setEnding(null); void post(`/api/lists/authorizations/${enc(String(a.id))}/end`, {}); })}
              </dd>
              <dt>{t("acRowTemp")}</dt>
              <dd>{visitorOn ? <b>{t("accVisitorOn", { t: mode?.until_ms ? hm(mode.until_ms) : "—" })}</b> : <span class="muted">{t("acTempNone")}</span>}</dd>
            </dl>
          </section>
          {(showTemp || visitorOn) && <Visitor mode={mode} zones={zones} say={say} onDone={loadMode} />}
          <section class="sp-sec acc-all">
            <h2 class="sp-h"><span>{t("acAllN", { n: rows.length })}</span><small>{t("acAllHint")}</small></h2>
            <table class="sp-table ac-table">
              <thead><tr><th>{t("acColWho")}</th><th>{t("acColScope")}</th><th>{t("acColDays")}</th><th>{t("acColUntil")}</th><th /></tr></thead>
              <tbody>
                {rows.length === 0 && <tr><td colSpan={5} class="muted">{t(siteDown.value ? "loadRetry" : "noAuthorizations")}</td></tr>}
                {rows.map((r) => (
                  <tr key={r.id}>
                    <td><b>{r.name}</b>{r.note ? <><br /><span class="muted small">{r.note}</span></> : null}</td>
                    <td>{where(r)}</td>
                    <td>
                      <span class="ac-days">{DAY_KEYS.map((k, i) => <i key={k} class={[(r.days >> i) & 1 ? "on" : "", i === today ? "today" : ""].filter(Boolean).join(" ") || undefined}>{t(k)}</i>)}</span>
                      <span class="muted small">{daysText(r.days)} <span class="mono">{r.start}–{r.end}</span></span>
                    </td>
                    <td class="mono">{r.until_ms ? new Date(r.until_ms).toLocaleDateString("sv-SE") : t("acNoExpiry")}</td>
                    <td class="ac-del">
                      {removing?.id === r.id ? ask(removing, t("removeAuthzConfirm", { name: r.name }), t("remove"), () => { setRemoving(null); void post(`/api/lists/authorizations/${enc(String(r.id))}/remove`, {}); }, true)
                        : <button type="button" class="btn" onClick={() => { setEnding(null); setRemoving(r); }}>{t("acDelete")}</button>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        </div>
        <aside class="sp-side ac-side">
          <AddAuthz key={zones.join("|")} zones={zones} say={say} onDone={() => { void load(); say(t("authzAddedMsg")); }} />
        </aside>
      </div>
    </section>
  );
}

function Visitor({ mode, zones, say, onDone }: { mode: ModeView | null; zones: string[]; say: Say; onDone: () => void }) {
  const [picked, setPicked] = useState<string[]>([]);
  const [hours, setHours] = useState(4);
  // 网页易用性第 1 轮 P0-09:原来没有防区也能一键临时撤防 4 小时,不确认
  const [ask, setAsk] = useState(false);
  if (!mode) return null;
  const on = mode.mode === "visitor";
  async function set(body: Record<string, unknown>, done: string) {
    try {
      await api("POST", "/api/mode", body);
      say(done);           // 第 2 轮 config N8:说清做了什么,不只「已保存」
      onDone();
    } catch (e) {
      say(errText(e));
    }
  }
  return (
    <section class="sp-sec acc-visitor">
      {/* UIUX-035:这一块是按防区的,跟顶栏「全站临时撤防 4 小时」分开叫 */}
      <h2 class="sp-h"><span>{t("accVisitorTitle")}</span><small>{t("accVisitorHint")}</small></h2>
      {on ? (
        <div class="row">
          <b>{t("accVisitorOn", { t: mode.until_ms ? hm(mode.until_ms) : "—" })}</b>
          {(mode.visitor_zones ?? []).length > 0 && <span class="muted">{joinList((mode.visitor_zones ?? []))}</span>}
          <button type="button" class="btn push" onClick={() => void set({ mode: mode.prev_mode || "armed" }, t("accVisitorEnded"))}>{t("accVisitorEnd")}</button>
        </div>
      ) : (
        <>
          <fieldset class="checks row-wrap">
            <legend>{t("accVisitorZones")}</legend>
            {zones.length === 0 && <span class="muted small">{t("armNoZones")}</span>}
            {zones.map((z) => (
              <label key={z}><input type="checkbox" value={z} checked={picked.includes(z)}
                onChange={() => setPicked(picked.includes(z) ? picked.filter((x) => x !== z) : [...picked, z])} /> {z}</label>
            ))}
          </fieldset>
          <div class="row">
            <label class="field">{t("accVisitorFor")}
              <select name="hours" value={String(hours)} onChange={(e) => setHours(Number(e.currentTarget.value))}>
                {VISITOR_HOURS.map((h) => <option key={h} value={String(h)}>{t("accHours", { n: h })}</option>)}
              </select>
            </label>
            <button type="button" class="btn primary" disabled={picked.length === 0} onClick={() => setAsk(true)}>{t("accVisitorStart")}</button>
          </div>
          {zones.length === 0 ? <p class="muted small">{t("accVisitorNoZones")} <a href="#/admin/layout">{t("accVisitorAddZones")}</a></p>
            : picked.length === 0 && <p class="muted small">{t("accVisitorPick")}</p>}
        </>
      )}
      {ask && (
        <Confirm text={t("accVisitorAsk", { z: joinList(picked), n: hours, t: hm(Date.now() + hours * 3_600_000) })} yes={t("accVisitorStart")}
          onNo={() => setAsk(false)} onYes={() => { setAsk(false); void set({ mode: "visitor", zones: picked, minutes: hours * 60 },
            t("accVisitorStarted", { z: joinList(picked), t: hm(Date.now() + hours * 3_600_000) })); }} />
      )}
    </section>
  );
}

/** P1-03:授权日期不能选过去的。 */
const todayYmd = () => new Date().toLocaleDateString("sv-SE");

/** P1-62:时间用 24 小时制,半小时一档(浏览器的时间框按系统设置可能显示成上午/下午)。 */
const HALF_HOURS = Array.from({ length: 48 }, (_, i) => `${String(Math.floor(i / 2)).padStart(2, "0")}:${i % 2 ? "30" : "00"}`);

function AddAuthz({ zones, onDone, say }: { zones: string[]; onDone: () => void; say: Say }) {
  const blank = () => ({ name: "", site: (zones.length === 0 ? true : null) as boolean | null, picked: [] as string[], repeat: true, days: 0b0011111, date: "", start: "09:00", end: "18:00", until: "", note: "" });
  const [f, setF] = useState(blank);
  const put = (p: Partial<ReturnType<typeof blank>>) => setF((o) => ({ ...o, ...p }));
  const { name, site, picked, repeat, days, date, start, end, until, note } = f;
  // P1-62:有防区时不默认「全站」(全站授权期间全站有人报警降级),要人自己选;没防区时只有全站,写明为什么
  async function submit(e: Event) {
    e.preventDefault();
    if (site === null || (site === false && picked.length === 0)) return;     // 回车提交也一样:没选范围不发
    let d = days;
    let untilMs: number | null = until ? new Date(`${until}T23:59:59`).getTime() : null;
    if (!repeat) {
      if (!date) return;
      const at = new Date(`${date}T00:00:00`);
      d = 1 << ((at.getDay() + 6) % 7);                  // 星期一 = 位 0(站点同一个规矩)
      untilMs = new Date(`${date}T23:59:59`).getTime();
    }
    try {
      await api("POST", "/api/lists/authorizations", { name, zones: site ? [] : picked, days: d, start, end, note, until_ms: untilMs });
      setF(blank());
      onDone();
    } catch (x) {
      say(errText(x));
    }
  }
  const seg = (on: boolean, label: string, go: () => void, extra?: Record<string, unknown>) =>
    <button type="button" aria-pressed={on} onClick={go} {...extra}>{label}</button>;
  return (
    <form class="form acc-add sp-sec" onSubmit={submit}>
      <h2 class="sp-h"><span>{t("acAddH")}</span><small>{t("acAddHint")}</small></h2>
      <div class="ac-form">
        <label class="lbl" for="ac-who">{t("who")}</label>
        <input id="ac-who" name="who" value={name} maxLength={64} required placeholder={t("whoPlaceholder")} onInput={(e) => put({ name: e.currentTarget.value })} />
        <span class="lbl">{t("acScope")}</span>
        <div class="seg ac-seg2" role="group" aria-label={t("acScope")}>
          {seg(site === true, t("wholeSite"), () => put({ site: true }), { name: "scope", "data-scope": "site" })}
          {seg(site === false, t("acSelected"), () => put({ site: false }), { name: "scope", "data-scope": "zones", disabled: zones.length === 0 })}
        </div>
        {site === true && <p class="muted small">{t("wholeSiteWarn")}</p>}
        {zones.length === 0 && <p class="muted small">{t("noZonesYet")}</p>}
        {site === false && (
          <div class="ac-zones">
            {zones.map((z) => <button key={z} type="button" aria-pressed={picked.includes(z)} data-zone={z}
              onClick={() => put({ picked: picked.includes(z) ? picked.filter((x) => x !== z) : [...picked, z] })}>{z}</button>)}
          </div>
        )}
        <span class="lbl">{t("acWhen")}</span>
        <div class="seg ac-seg2" role="group" aria-label={t("acWhen")}>
          {seg(!repeat, t("acSingle"), () => put({ repeat: false }), { name: "repeat", "data-repeat": "0" })}
          {seg(repeat, t("acWeekly"), () => put({ repeat: true }), { name: "repeat", "data-repeat": "1" })}
        </div>
        {repeat ? (
          <>
            <div class="ac-days-pick">
              {DAY_KEYS.map((k, i) => <button key={k} type="button" name={`day${i}`} aria-pressed={!!(days >> i & 1)} onClick={() => put({ days: days ^ (1 << i) })}>{t(k)}</button>)}
            </div>
            <div class="ac-days-quick">
              <button type="button" class="btn" onClick={() => put({ days: 0b1111111 })}>{t("acDaily")}</button>
              <button type="button" class="btn" onClick={() => put({ days: 0b0011111 })}>{t("acWeekdays")}</button>
              <button type="button" class="btn" onClick={() => put({ days: 0b1100000 })}>{t("acWeekend")}</button>
            </div>
          </>
        ) : (
          <><label class="lbl" for="ac-date">{t("accOnDay")}</label><input id="ac-date" name="date" type="date" value={date} min={todayYmd()} required onInput={(e) => put({ date: e.currentTarget.value })} /></>
        )}
        <div class="ac-two">
          <label class="lbl" for="ac-start">{t("from")}</label><label class="lbl" for="ac-end">{t("to")}</label>
          <select id="ac-start" name="start" value={start} onChange={(e) => put({ start: e.currentTarget.value })}>{HALF_HOURS.map((h) => <option key={h} value={h}>{h}</option>)}</select>
          <select id="ac-end" name="end" value={end} onChange={(e) => put({ end: e.currentTarget.value })}>{HALF_HOURS.map((h) => <option key={h} value={h}>{h}</option>)}</select>
        </div>
        <p class="muted small">{t("overnightHint")}</p>
        <div class="ac-two">
          {repeat ? <label class="lbl" for="ac-until">{t("validUntil")} · {t("optional")}</label> : <span />}
          <label class="lbl" for="ac-note">{t("note")} · {t("optional")}</label>
          {repeat ? <input id="ac-until" type="date" value={until} min={todayYmd()} onInput={(e) => put({ until: e.currentTarget.value })} /> : <span />}
          <input id="ac-note" value={note} maxLength={200} onInput={(e) => put({ note: e.currentTarget.value })} />
        </div>
      </div>
      <div class="ac-submit">
        <button type="submit" class="btn primary" disabled={!name.trim() || (repeat && days === 0) || (!repeat && !date) || site === null || (site === false && picked.length === 0)}>{t("acAddBtn")}</button>
        <button type="button" class="btn" onClick={() => setF(blank())}>{t("acClear")}</button>
      </div>
    </form>
  );
}
