// 布防时间页(W44 第二期,设计 §5.1「布防时间」):一周七行、0–24 点,色块 = 布防,拖着画、点了删、拖两边改;
// 全部防区一样,或者每个防区单独设;例外日期(节假日、出远门);交班时间、多久没巡过;一个「保存」存整份。
// 星期、日子、时区都由站点算(站点时区),网页只画站点回来的。
import { useEffect, useRef, useState } from "preact/hooks";
import { canArm, canDisarm, canSchedule, isOwnerLike } from "./model";
import { GuardPanel } from "./armguard";
import { DevicesPanel } from "./devicespanel";
import { PatrolSchedules } from "./routepage";
import { api, ApiError, enc } from "./api";
import { addBlock, armedAt, copyDay, fromWire, minutesText, moveEdge, removeBlock, toWire, type Slot, type WireSlot } from "./armgrid";
import { hm, type DutySettings } from "./data";
import { t, type Key } from "./i18n";
import { pageAllowed } from "./shell";
import { Confirm } from "./dialogs";
import { useUnsaved } from "./unsaved";
import { dateInput } from "./recordings";

type Say = (s: string) => void;
interface Exception { id: number; first_day: string; last_day: string; state: "armed" | "disarmed"; note: string }
interface Schedule { enabled: boolean; slots: WireSlot[]; exceptions: Exception[] }
interface ModeView { mode: string; label?: string; state?: string; source?: "schedule" | "manual"; next_change_ms?: number | null; manual_until_ms?: number | null; zones?: { zone: string }[] }

const DAY_KEYS: Key[] = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"];
const HOURS = Array.from({ length: 24 }, (_, i) => i);

function errText(e: unknown): string {
  return t("failed", { why: e instanceof ApiError ? e.message : String(e) });
}

/** 模式给人看的名字(网页自己翻,站点的 label 只有中文):按时间表:布防 / 部分布防 / 撤防;手动的:布防 / 留守 / 临时撤防。 */
export function modeLabel(m: { mode: string; source?: string; state?: string }): string {
  if (m.source === "schedule") {
    return t("armSched", { s: t(m.state === "armed" ? "armStArmed" : m.state === "disarmed" ? "armStDisarmed" : "armStPartial") });
  }
  return t(m.mode === "armed" ? "modeArmed" : m.mode === "home" ? "modeHome" : "modeVisitor");
}

/** 现在谁说了算:按时间表 / 手动到几点回时间表 / 时间表没开。 */
export function whoText(m: ModeView | null, enabled: boolean): string {
  if (!m) return "";
  const s = modeLabel(m);
  if (m.source === "schedule") {
    return m.next_change_ms ? t("armWhoSchedule", { s, t: hm(m.next_change_ms) }) : t("armWhoScheduleNoNext", { s });
  }
  if (enabled && m.manual_until_ms) return t("armWhoManual", { s, t: hm(m.manual_until_ms) });
  return t("armWhoOff", { s });
}

export function ArmingPage({ say, now, role = "admin" }: { say: Say; now: number; role?: string }) {
  // W53:经理能排布防时间,值班设置(交班钟点等)还是管理员的事 —— 经理那一块不显示、不提交(外审 W53-1 #10)
  const canDuty = isOwnerLike(role);
  const [loaded, setLoaded] = useState<{ enabled: boolean; slots: Slot[]; duty: DutySettings } | null>(null);
  const [enabled, setEnabled] = useState(false);
  const [slots, setSlots] = useState<Slot[]>([]);
  const [duty, setDuty] = useState<DutySettings>({ shift_hours: [7, 19], stale_hours: 2 });
  const [exceptions, setExceptions] = useState<Exception[]>([]);
  const [mode, setMode] = useState<ModeView | null>(null);
  const [perZone, setPerZone] = useState(false);
  const [zone, setZone] = useState("");
  const [sel, setSel] = useState<{ day: number; start: number } | null>(null);
  const [gridHint, setGridHint] = useState<string | null>(null);
  const [sec, setSec] = useState<"times" | "patrols" | "guard" | "devices">("times");
  const [copyFrom, setCopyFrom] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [switching, setSwitching] = useState<"armed" | "home" | null>(null);

  const loadMode = () => api<ModeView>("GET", "/api/mode").then(setMode).catch(() => setMode(null));
  useEffect(() => {
    Promise.all([api<Schedule>("GET", "/api/arming/schedule"), api<DutySettings>("GET", "/api/duty-settings").catch(() => duty)])
      .then(([s, d]) => {
        const sl = fromWire(s.slots ?? []);
        setEnabled(!!s.enabled);
        setSlots(sl);
        setExceptions(s.exceptions ?? []);
        setDuty(d);
        setLoaded({ enabled: !!s.enabled, slots: sl, duty: d });
        setPerZone(sl.some((x) => x.zone !== ""));
      })
      .catch((e) => say(errText(e)));
    void loadMode();
  }, []);
  // 第 3 轮 config N5:「此刻」一栏每分钟刷新一次(原来只在打开页面、保存、手动切换时刷新)
  const minute = Math.floor(now / 60_000);
  useEffect(() => { void loadMode(); }, [minute]);

  const dirty = loaded != null && (loaded.enabled !== enabled || JSON.stringify(loaded.slots) !== JSON.stringify(slots)
    || JSON.stringify(loaded.duty) !== JSON.stringify(duty));
  useUnsaved("arming", dirty);

  const zones = Array.from(new Set([...(mode?.zones ?? []).map((z) => z.zone), ...slots.filter((x) => x.zone).map((x) => x.zone)])).sort();
  const editing = perZone ? zone : "";
  const ownSlots = slots.some((x) => x.zone === editing);
  const followsAll = perZone && zone !== "" && !ownSlots;

  // P0-08:存下去立刻生效 —— 跟现在的布防状态不一样就先确认(原来只画一段、一存全站就撤防了,没有任何提示)
  const [askSave, setAskSave] = useState<string | null>(null);
  function effectNow(): string | null {
    if (!mode) return null;
    const wasOn = !!loaded?.enabled;
    // 第 3 轮 config N1:停用日程时站点照此刻的状态改成手动(此刻撤防 → 留守),确认框写清变成什么
    if (!enabled && wasOn) {
      return mode.source === "schedule"
        ? t("armSaveOffTo", { to: t(mode.state === "disarmed" ? "modeHome" : "modeArmed") }) : t("armSaveOff");
    }
    // 第 3 轮 config N4:手动期里删光时段也要说「整周撤防」(原来手动期里一律不问)
    if (enabled && slots.length === 0) return t("armSaveEmpty");
    // 第 3 轮 config N3:临时撤防进行中打开日程,临时撤防马上结束
    if (enabled && !wasOn && mode.mode === "visitor") {
      return t("armSaveEndsVisitor", { state: t(armedAt(slots, "", new Date(now)) ? "armStateArmed" : "armStateDisarmed") });
    }
    // 第 2 轮 N1:日程开着时手动切换管到下一个变化点(manual_until_ms),这期间存日程此刻不变;
    // 日程原来关着,手动状态没有期限 —— 一打开日程保存,站点马上按日程走,跟按日程时一样要先确认
    if (mode.source === "manual" && mode.manual_until_ms && wasOn && enabled) return null;
    // 第 3 轮 config N2:留守时外围防区是布防的,也算「此刻布防」(原来把留守当撤防,打开日程撤防不问)
    const nowArmed = mode.state !== "disarmed";
    const willArm = enabled && armedAt(slots, "", new Date(now));
    if (enabled && nowArmed && !willArm) return t("armSaveDisarm");
    if (enabled && !nowArmed && willArm) return t("armSaveArm");
    return null;
  }
  function trySave() {
    const e = effectNow();
    if (e) setAskSave(e);
    else void save();
  }

  async function save() {
    setAskSave(null);
    setBusy(true);
    try {
      await api("POST", "/api/arming/schedule", { enabled, slots: toWire(slots) });
      if (canDuty) await api("POST", "/api/duty-settings", duty);
      setLoaded({ enabled, slots, duty });
      say(t("saved"));
      void loadMode();
    } catch (e) {
      say(errText(e));
    } finally {
      setBusy(false);
    }
  }

  // P1-57:一页三块,分标签:布防时间(顶上「保存」管这块)、守卫值勤(自己存)、报警设备(马上存)
  const tabs = (
    <div class="ly-tabs arm-tabs" role="tablist">
      {(["times", "patrols", "guard", "devices"] as const).map((x) => (
        <button key={x} type="button" role="tab" aria-selected={sec === x} data-arm-tab={x}
          onClick={() => setSec(x)}>{t(x === "times" ? "armTabTimes" : x === "patrols" ? "armTabPatrols" : x === "guard" ? "armTabGuard" : "armTabDevices")}</button>
      ))}
    </div>
  );
  if (sec !== "times") {
    return (
      <section class="arming">
        <div class="panel-head"><h1>{t("tabArming")}</h1></div>
        {tabs}
        {dirty && <p class="arm-dirty" role="status">{t("armDirtyOther")}</p>}
        {sec === "patrols" ? <PatrolSchedules say={say} canEdit={canSchedule(role)} />
          : sec === "guard" ? <GuardPanel say={say} now={now} canEdit={canSchedule(role)} /> : <DevicesPanel say={say} canEdit={isOwnerLike(role)} />}
      </section>
    );
  }
  return (
    <section class="arming">
      <div class="panel-head">
        <h1>{t("tabArming")}</h1>
        {dirty && <span class="ly-dirty small" role="status">{t("armDirty")}</span>}
        <button type="button" class="btn primary push arm-save" disabled={busy || !dirty} onClick={trySave}>{t("save")}</button>
      </div>
      {tabs}
      <p class="muted lead">{t("armLead")}</p>
      {/* W72(用户 11-03):在网页上要能直接布防 / 撤防,不用翻到「系统状态」页去找 */}
      <section class="panel arm-now">
        <div class="arm-now-text">
          <h2>{t("armNow")}</h2>
          <p class="arm-who">{whoText(mode, loaded?.enabled ?? enabled)}</p>
        </div>
        {mode && (
          <div class="arm-now-btns">
            <div class="seg" role="group" aria-label={t("homeSwitch")}>
              {(["armed", "home"] as const).map((m) => (
                <button key={m} type="button" aria-pressed={mode.source !== "schedule" && mode.mode === m}
                  disabled={m === "armed" ? !canArm(role) : !canDisarm(role)}
                  title={m !== "armed" && !canDisarm(role) ? t("armNoDisarm") : undefined}
                  onClick={() => setSwitching(m)}>{t(m === "armed" ? "modeArmed" : "modeHome")}</button>
              ))}
            </div>
            {/* 第 2 轮 config N4:打不开「临时撤防」页的账号(经理)不给这个入口,写一句谁能做 */}
            {pageAllowed("admin/access", role)
              ? <a class="btn sm" href="#/admin/access">{t("armNowVisitor")}</a>
              : <span class="muted small" data-no-visitor="1">{t("armVisitorAdminOnly")}</span>}
          </div>
        )}
      </section>
      {askSave && <Confirm text={askSave} yes={t("save")} onNo={() => setAskSave(null)} onYes={() => void save()} />}
      {switching && (
        <Confirm text={t(switching === "armed" ? "modeArmConfirm" : "modeHomeConfirm")}
          yes={t(switching === "armed" ? "modeArmed" : "modeHome")} onNo={() => setSwitching(null)}
          onYes={() => {
            const m = switching;
            setSwitching(null);
            api("POST", "/api/mode", { mode: m }).then(() => say(t(m === "armed" ? "modeNowArmed" : "modeNowHome"))).catch((e) => say(errText(e))).finally(() => void loadMode());
          }} />
      )}

      {/* P2-20:大一点的开关;打开了却一个时段都没有(= 全天撤防)当场说(存的时候还会再确认) */}
      <label class="switch arm-enabled">
        <input id="arm-enabled" type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.currentTarget.checked)} />
        {t("armEnabled")}
      </label>
      {enabled && slots.length === 0 && <p class="arm-dirty" role="status" data-arm-noslots="1">{t("armEnableNeedSlots")}</p>}

      <div class="seg arm-scope" role="group" aria-label={t("armScope")}>
        <button type="button" aria-pressed={!perZone} onClick={() => { setPerZone(false); setZone(""); setSel(null); }}>{t("armAllSame")}</button>
        <button type="button" aria-pressed={perZone} onClick={() => { setPerZone(true); setSel(null); }}>{t("armPerZone")}</button>
      </div>
      {perZone && (
        <div class="arm-zones chips">
          {/* P2-43:没有防区只说一句,给去画的入口 */}
          {zones.length === 0 && <span class="muted small">{t("armNoZones")} <a href="#/admin/layout?tab=zones">{t("armGoDrawZones")}</a></span>}
          {zones.map((z) => (
            <button key={z} type="button" class="chip" aria-pressed={zone === z} onClick={() => { setZone(z); setSel(null); }}>{z}</button>
          ))}
        </div>
      )}
      {followsAll ? (
        <div class="arm-follow">
          <p>{t("armFollowsAll", { z: zone })}</p>
          <button type="button" class="btn" onClick={() => setSlots(copyZone(slots, "", zone))}>{t("armOwnZone")}</button>
        </div>
      ) : (perZone && zone === "") ? (zones.length > 0 ? <p class="muted">{t("armPickZone")}</p> : null) : (
        <>
          <WeekGrid slots={slots.filter((x) => x.zone === editing)} sel={sel}
            onAdd={(day, a, b) => {
              // P1-59:单击(拖得太短)没加上 → 说要按住拖;跟已有的连上了 → 说合并了
              const n = addBlock(slots, editing, day, a, b);
              if (n === slots) { setGridHint(t("armDragHint")); return; }
              setGridHint(n.length < slots.length + 1 ? t("armMerged") : null);
              setSlots(n);
            }}
            onPick={(day, start) => setSel({ day, start })}
            onEdge={(day, start, edge, to) => { const n = moveEdge(slots, editing, day, start, edge, to); setSlots(n); }}
            onCopy={(day) => setCopyFrom(day)} />
          <p class="arm-legend small muted" data-arm-legend="1">
            <i class="arm-sw" aria-hidden="true" /> {t("armLegendArmed")} · {t("armLegendHow")}
          </p>
          {gridHint && <p class="small warn" role="status" data-arm-hint="1">{gridHint}</p>}
          {sel && (
            <div class="arm-selected row">
              <span>{t(DAY_KEYS[sel.day])} {minutesText(sel.start)}–{minutesText(slots.find((x) => x.zone === editing && x.day === sel.day && x.start === sel.start)?.end ?? sel.start)}</span>
              <button type="button" class="btn sm" onClick={() => { setSlots(removeBlock(slots, editing, sel.day, sel.start)); setSel(null); }}>{t("armDeleteBlock")}</button>
              {perZone && zone && ownSlots && (
                <button type="button" class="btn sm" onClick={() => setSlots(slots.filter((x) => x.zone !== zone))}>{t("armBackToAll")}</button>
              )}
            </div>
          )}
          {copyFrom != null && (
            <CopyTo from={copyFrom} onClose={() => setCopyFrom(null)}
              onCopy={(days) => { setSlots(copyDay(slots, editing, copyFrom, days)); setCopyFrom(null); }} />
          )}
        </>
      )}

      <Exceptions list={exceptions} say={say} onChange={(l) => { setExceptions(l); void loadMode(); }} on={!!loaded?.enabled} mode={mode} />
      {role === "owner" && <p class="muted small">{t("armOwnerNote")}</p>}


      {canDuty && <section class="panel arm-duty">
        <h2>{t("armDutyTitle")}</h2>
        <div class="row wrap">
          <label class="field">{t("armShiftA")}
            <select name="shiftA" value={String(duty.shift_hours[0])} onChange={(e) => setDuty({ ...duty, shift_hours: [Number(e.currentTarget.value), duty.shift_hours[1]] })}>
              {HOURS.map((h) => <option key={h} value={String(h)}>{`${String(h).padStart(2, "0")}:00`}</option>)}
            </select>
          </label>
          <label class="field">{t("armShiftB")}
            <select name="shiftB" value={String(duty.shift_hours[1])} onChange={(e) => setDuty({ ...duty, shift_hours: [duty.shift_hours[0], Number(e.currentTarget.value)] })}>
              {HOURS.map((h) => <option key={h} value={String(h)}>{`${String(h).padStart(2, "0")}:00`}</option>)}
            </select>
          </label>
          <label class="field">{t("armStale")}
            <input name="stale" type="number" min={1} max={48} value={duty.stale_hours}
              onInput={(e) => setDuty({ ...duty, stale_hours: Number(e.currentTarget.value) })} />
          </label>
        </div>
        <label class="row">
          <input name="siren" type="checkbox" checked={duty.self_protect_siren !== false}
            onChange={(e) => setDuty({ ...duty, self_protect_siren: e.currentTarget.checked })} />
          {t("armSelfSiren")}
        </label>
        <p class="muted small">{t("armDutyHint")}</p>
      </section>}
    </section>
  );
}

function copyZone(slots: Slot[], from: string, to: string): Slot[] {
  return [...slots.filter((x) => x.zone !== to), ...slots.filter((x) => x.zone === from).map((x) => ({ ...x, zone: to }))];
}

function WeekGrid(props: {
  slots: Slot[];
  sel: { day: number; start: number } | null;
  onAdd: (day: number, a: number, b: number) => void;
  onPick: (day: number, start: number) => void;
  onEdge: (day: number, start: number, edge: "start" | "end", to: number) => void;
  onCopy: (day: number) => void;
}) {
  const drag = useRef<{ day: number; from: number; edge?: "start" | "end"; start?: number } | null>(null);
  const [ghost, setGhost] = useState<{ day: number; a: number; b: number } | null>(null);
  const minuteAt = (el: Element, x: number) => {
    const r = el.getBoundingClientRect();
    return r.width > 0 ? Math.max(0, Math.min(1440, ((x - r.left) / r.width) * 1440)) : 0;
  };
  const pct = (m: number) => `${(m / 1440) * 100}%`;
  return (
    <div class="armgrid" role="grid" aria-label={t("tabArming")}>
      <div class="armhours" aria-hidden="true">
        {[0, 6, 12, 18, 24].map((h) => <span key={h} style={{ left: pct(h * 60) }}>{`${h}:00`}</span>)}
      </div>
      {DAY_KEYS.map((k, day) => (
        <div key={k} class="armrow" data-day={day} role="row">
          <span class="armday">{t(k)}</span>
          <div class="armtrack" role="gridcell"
            onPointerDown={(e) => {
              const el = e.currentTarget as HTMLElement;
              const tgt = e.target as HTMLElement;
              if (tgt.classList.contains("armedge")) {
                drag.current = { day, from: 0, edge: tgt.dataset.edge as "start" | "end", start: Number(tgt.dataset.start) };
              } else if (tgt.classList.contains("armblock")) {
                return;
              } else {
                const m = minuteAt(el, e.clientX);
                drag.current = { day, from: m };
                setGhost({ day, a: m, b: m });
              }
              try { el.setPointerCapture?.(e.pointerId); } catch { /* 测试环境没有 */ }
            }}
            onPointerMove={(e) => {
              const d = drag.current;
              if (!d || d.day !== day) return;
              const m = minuteAt(e.currentTarget as HTMLElement, e.clientX);
              if (d.edge && d.start != null) {
                props.onEdge(day, d.start, d.edge, m);
                if (d.edge === "start") d.start = Math.min(Math.round(m / 30) * 30, d.start);
              } else setGhost({ day, a: d.from, b: m });
            }}
            onPointerUp={(e) => {
              const d = drag.current;
              drag.current = null;
              setGhost(null);
              if (!d || d.day !== day || d.edge) return;
              props.onAdd(day, d.from, minuteAt(e.currentTarget as HTMLElement, e.clientX));
            }}>
            {props.slots.filter((s) => s.day === day).map((s) => (
              <div key={s.start} class={props.sel && props.sel.day === day && props.sel.start === s.start ? "armblock on" : "armblock"}
                style={{ left: pct(s.start), width: pct(s.end - s.start) }}
                title={`${minutesText(s.start)}–${minutesText(s.end)}`}
                onClick={() => props.onPick(day, s.start)}>
                <i class="armedge" data-edge="start" data-start={s.start} />
                <span class="armlabel">{minutesText(s.start)}–{minutesText(s.end)}</span>
                <i class="armedge end" data-edge="end" data-start={s.start} />
              </div>
            ))}
            {ghost && ghost.day === day && (
              <div class="armblock ghost" style={{ left: pct(Math.min(ghost.a, ghost.b)), width: pct(Math.abs(ghost.b - ghost.a)) }} />
            )}
          </div>
          <button type="button" class="btn sm arm-copy" onClick={() => props.onCopy(day)}>{t("armCopyTo")}</button>
        </div>
      ))}
    </div>
  );
}

function CopyTo({ from, onCopy, onClose }: { from: number; onCopy: (days: number[]) => void; onClose: () => void }) {
  const [days, setDays] = useState<number[]>([]);
  // 第 2 轮 config N7:面板一打开就滚到看得见的地方(原来在屏幕下面,看着像没反应);焦点给第一个勾选框
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = box.current;
    if (!el) return;
    if (typeof el.scrollIntoView === "function") el.scrollIntoView({ block: "nearest", behavior: "smooth" });
    el.querySelector<HTMLElement>("input, button")?.focus({ preventScroll: true });
  }, [from]);
  return (
    <div class="arm-copyto panel" ref={box}>
      <p>{t("armCopyFrom", { d: t(DAY_KEYS[from]) })}</p>
      {/* P2-20:一下勾上工作日 / 周末 / 其余全部 */}
      <div class="row wrap arm-copy-quick">
        {([["armCopyWeekdays", [0, 1, 2, 3, 4]], ["armCopyWeekend", [5, 6]], ["armCopyAll", [0, 1, 2, 3, 4, 5, 6]]] as [Key, number[]][]).map(([k, ds]) => (
          <button key={k} type="button" class="btn sm" data-copy-quick={k}
            onClick={() => setDays([...new Set([...days, ...ds.filter((d) => d !== from)])])}>{t(k)}</button>
        ))}
      </div>
      <div class="row wrap">
        {DAY_KEYS.map((k, i) => i === from ? null : (
          <label key={k}><input type="checkbox" value={String(i)} checked={days.includes(i)}
            onChange={() => setDays(days.includes(i) ? days.filter((x) => x !== i) : [...days, i])} /> {t(k)}</label>
        ))}
      </div>
      <div class="row end">
        <button type="button" class="btn" onClick={onClose}>{t("cancel")}</button>
        <button type="button" class="btn primary" disabled={days.length === 0} onClick={() => onCopy(days)}>{t("armCopy")}</button>
      </div>
    </div>
  );
}

function Exceptions({ list, say, onChange, on, mode }: { list: Exception[]; say: Say; onChange: (l: Exception[]) => void; on: boolean; mode: ModeView | null }) {
  const [asking, setAsking] = useState<string | null>(null);
  const [first, setFirst] = useState("");
  const [last, setLast] = useState("");
  const [state, setState] = useState<"armed" | "disarmed">("armed");
  const [note, setNote] = useState("");
  // 第 2 轮 P1-58 / P1-05:例外跟上面的时间表不一样,加、删马上生效 —— 删先确认,加删都说一声
  const [removing, setRemoving] = useState<Exception | null>(null);
  // P1-60:当场查 —— 不能早于今天、结束不能早于开始;错就写在这一行下面,不弹框
  const today = dateInput(Date.now());
  const exErr = first && first < today ? t("armExPast") : first && last && last < first ? t("armExOrder") : "";
  // 第 3 轮 config N5:今天的例外会马上改变此刻的状态(日程开着、此刻按日程走)→ 跟保存日程一样先确认
  function tryAdd() {
    if (exErr) return;
    const end = last || first;
    const hitsNow = on && mode?.source === "schedule" && first <= today && today <= end
      && (state === "disarmed") === (mode.state !== "disarmed");
    if (hitsNow) setAsking(t(state === "disarmed" ? "armExNowDisarm" : "armExNowArm"));
    else void add();
  }
  async function add() {
    setAsking(null);
    if (exErr) return;
    try {
      const d = await api<Schedule>("POST", "/api/arming/exceptions", { first_day: first, last_day: last || first, state, note });
      onChange(d.exceptions ?? []);
      setFirst(""); setLast(""); setNote("");
      say(t(on ? "armExAdded" : "armExAddedOff"));
    } catch (e) {
      say(errText(e));
    }
  }
  async function remove(id: number) {
    try {
      const d = await api<Schedule>("POST", `/api/arming/exceptions/${enc(String(id))}/remove`, {});
      onChange(d.exceptions ?? []);
      say(t("armExRemoved"));
    } catch (e) {
      say(errText(e));
    }
  }
  return (
    <section class="panel arm-ex">
      <h2>{t("armExTitle")}</h2>
      <p class="muted small">{t("armExHint")} {t(on ? "armExNow" : "armExNowOff")}</p>
      {list.length > 0 && (
        <ul class="plain">
          {list.map((x) => (
            <li key={x.id} class="row">
              <span class="mono">{x.first_day === x.last_day ? x.first_day : `${x.first_day} – ${x.last_day}`}</span>
              <b>{t(x.state === "armed" ? "armExArmed" : "armExDisarmed")}</b>
              {x.note && <span class="muted">{x.note}</span>}
              <button type="button" class="btn sm push" onClick={() => setRemoving(x)}>{t("remove")}</button>
            </li>
          ))}
        </ul>
      )}
      <div class="row wrap">
        <label class="field">{t("from")}<input name="first" type="date" min={today} value={first} onInput={(e) => setFirst(e.currentTarget.value)} /></label>
        <label class="field">{t("to")}<input name="last" type="date" min={first || today} value={last} onInput={(e) => setLast(e.currentTarget.value)} /></label>
        <label class="field">{t("armExState")}
          <select name="state" value={state} onChange={(e) => setState(e.currentTarget.value as "armed" | "disarmed")}>
            <option value="armed">{t("armExArmed")}</option>
            <option value="disarmed">{t("armExDisarmed")}</option>
          </select>
        </label>
        <label class="field">{t("note")}<input name="note" maxLength={200} value={note} onInput={(e) => setNote(e.currentTarget.value)} /></label>
        <button type="button" class="btn" disabled={!first || !!exErr} onClick={tryAdd}>{t("armExAdd")}</button>
      </div>
      {exErr && <p class="error small" role="alert">{exErr}</p>}
      {asking && <Confirm text={asking} yes={t("armExAdd")} danger onNo={() => setAsking(null)} onYes={() => void add()} />}
      {removing && (
        <Confirm text={t("armExRemoveAsk", { d: removing.first_day === removing.last_day ? removing.first_day : `${removing.first_day} – ${removing.last_day}` })}
          yes={t("remove")} danger onNo={() => setRemoving(null)} onYes={() => { const id = removing.id; setRemoving(null); void remove(id); }} />
      )}
    </section>
  );
}
