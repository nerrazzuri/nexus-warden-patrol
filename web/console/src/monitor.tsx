// 值班(redesign 第二轮 V4 稿,design/console-v2/png-en/V4-normal.png):
// 左 事件队列(安全事件 / 设备与运营 / 本班已关闭)+ 交班留言;中 状态头 + 地图(全部/巡逻路线/防区/摄像头)+ 画面
// (单/双/四画面/监控墙);右 机器人 + 今晚巡逻 + 最近活动;底 整班时间轴(点任一处看那时的录像)。
// 原来的「实时画面」页 = 监控墙,「地图」页 = 中间的地图(派去看一眼、临时路线在页头)。
import { useEffect, useMemo, useRef, useState } from "preact/hooks";
import { api, ApiError, enc } from "./api";
import { alertHeadline, canHandleAlerts } from "./alertinfo";
import { modeLabel } from "./armingpage";
import { CameraWell, camLabel } from "./camera";
import { hm, nameOf, useDutySettings } from "./data";
import { guardAlarms, pickSlots, rankUnits, type SlotPick } from "./dutyrank";
import { alertTitle, andList, joinList, lang, t, type Key } from "./i18n";
import { locText, type UnitInfo } from "./live";
import { LiveWall } from "./livewall";
import { shiftStart } from "./maplayers";
import type { CanvasArea } from "./mapcanvas";
import { MapPage, verdictText, type MapPreset, type MapTool } from "./mappage";
import { pointInPolygon } from "./mapview";
import { autoResolved, canDispatch, forGuard, robotCams, type Alert, type Mode, canPatrol } from "./model";
import { pageAllowed } from "./shell";
import { byText } from "./sitetext";
import { VideoSlot, type Scene } from "./slot";
import { fitLayout, Sign, stateSign, videoLayoutsFor, type VideoLayout } from "./signs";
import { awayText, followText, IncidentView, seenByText, responder, type FixedCam } from "./incident";
import { type ChargeSpan, isSecurity, recentActivity, ShiftTimeline } from "./shifttl";
import { TodayPatrols, type TodayItem } from "./todaypatrols";
import { RobotControl } from "./robotctl";
import { MultiView } from "./multi";
import { PlaybackView, playRobot, type Playback } from "./playback";
import { hms, incidentLog, REOPEN_MS } from "./alertdetail";

/** 迷路了的两种(站点 alerts.LEVEL_OF):多一个「帮它找位置」。 */
const LOST = new Set(["loc_lost_paused", "loc_lost_idle"]);
/** W74:要保安先到场才能关的告警(站点 alert_store.ARRIVAL_KINDS)。 */
const ARRIVE = new Set(["dog_sees_person"]);

const LAYOUT_KEY = "nexwar.monvideo";
const PRESET_KEY = "nexwar.mappreset";
const PINS_KEY = "nexwar.dutyPins";

interface Note { id: number; at_ms: number; author: string; text: string }

function load<T extends string>(key: string, ok: readonly T[], dflt: T): T {
  try { const v = localStorage.getItem(key); return ok.includes(v as T) ? v as T : dflt; } catch { return dflt; }
}
function keep(key: string, v: string): void {
  try { localStorage.setItem(key, v); } catch { /* 隐私模式:不记 */ }
}

export { recentActivity } from "./shifttl";

export function MonitorPage(props: {
  units: UnitInfo[];
  alerts: Alert[];
  now: number;
  role: string;
  me?: string;
  say: (s: string) => void;
  refresh: () => Promise<void>;
  onZoom: (robot: string) => void;
  mode?: Mode | null;
  stale?: boolean;
  /** 报警记录页「去处理」带过来的那一件(#/duty?alarm=)。 */
  openKey?: string | null;
}) {
  const duty = useDutySettings();
  const since = shiftStart(props.now, duty.shift_hours);
  const until = since + 12 * 3_600_000;
  const [preset, setPreset] = useState<MapPreset>(() => load(PRESET_KEY, ["all", "route", "zones", "cameras"] as const, "all"));
  const [layoutRaw, setLayout] = useState<VideoLayout>(() => load(LAYOUT_KEY, ["single", "dual", "multi", "wall"] as const, "dual"));
  const layout = fitLayout(layoutRaw, props.units.length);
  const [tool, setToolRaw] = useState<MapTool>(null);
  const [lookRobot, setLookRobot] = useState<string | null>(null);
  // 第 8 期:充电时段(站点 charge_log),画在时间轴上;每分钟刷一次
  const [charging, setCharging] = useState<ChargeSpan[]>([]);
  useEffect(() => {
    let live = true;
    const load = () => api<{ spans: ChargeSpan[] }>("GET", `/api/robots/charging?since=${since}&until=${until}`)
      .then((d) => live && setCharging(d.spans ?? [])).catch(() => {});
    void load();
    const h = window.setInterval(load, 60_000);
    return () => { live = false; window.clearInterval(h); };
  }, [since, until]);
  const setTool = (x: MapTool) => { setToolRaw(x); if (x !== "look") setLookRobot(null); };
  const [thermal, setThermal] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<string | null>(null);
  const [finding, setFinding] = useState<string | null>(null);
  const [areas, setAreas] = useState<CanvasArea[]>([]);
  const [cams, setCams] = useState<FixedCam[]>([]);
  const [recent, setRecent] = useState<Alert[]>([]);
  const [patrols, setPatrols] = useState<TodayItem[]>([]);
  const [pins, setPinsRaw] = useState<[string | null, string | null]>(() => {
    try { const v = JSON.parse(localStorage.getItem(PINS_KEY) ?? "null"); return Array.isArray(v) && v.length === 2 ? v as [string | null, string | null] : [null, null]; } catch { return [null, null]; }
  });
  const setPins = (f: (p: [string | null, string | null]) => [string | null, string | null]) => setPinsRaw((p) => { const n = f(p); keep(PINS_KEY, JSON.stringify(n)); return n; });

  useEffect(() => {
    let live = true;
    api<{ cameras: FixedCam[] }>("GET", "/api/cameras").then((d) => live && setCams(d.cameras ?? [])).catch(() => {});
    return () => { live = false; };
  }, []);
  // 本班出的事(含已关的):30 秒一拉;顶栏的报警一变马上再拉
  const alertKey = props.alerts.map((a) => `${a.key}:${a.count ?? 1}:${a.acked_ms ?? ""}:${a.resolved_ms ?? ""}`).join(",");
  useEffect(() => {
    let live = true;
    const pull = () => api<{ alerts: Alert[] }>("GET", "/api/alerts?all=1&limit=200").then((d) => live && setRecent(d.alerts ?? [])).catch(() => {});
    void pull();
    const id = window.setInterval(pull, 30_000);
    return () => { live = false; window.clearInterval(id); };
  }, [alertKey]);

  const alarms = useMemo(() => guardAlarms(props.alerts), [props.alerts]);
  const ranked = useMemo(() => rankUnits(props.units, props.alerts), [props.units, props.alerts]);
  const open = props.alerts.filter((a) => a.resolved_ms == null && a.level !== "P3");
  // 设备与运营:给保安的那些(站点磁盘、证书这类技术提醒在「现场设置 → 概况」)
  const security = open.filter((a) => isSecurity(a)).sort((a, b) => (a.level === b.level ? b.last_ms - a.last_ms : a.level === "P1" ? -1 : 1));
  const equipment = open.filter((a) => !isSecurity(a) && forGuard(a)).sort((a, b) => (a.level === b.level ? b.last_ms - a.last_ms : a.level === "P1" ? -1 : 1));
  const closed = recent.filter((a) => a.resolved_ms != null && a.resolved_ms >= since && a.level !== "P3" && a.first_ms >= since - 86_400_000)
    .sort((a, b) => (b.resolved_ms ?? 0) - (a.resolved_ms ?? 0));
  const hot = new Set(alarms.map((a) => a.context?.zone).filter((z): z is string => !!z));
  const unitOf = (id: string) => props.units.find((u) => u.robot.robot_id === id);
  const can = canHandleAlerts(props.role);
  const top = alarms[0];
  // 有告警时中间是「这件事」(第 3 期):点左栏哪一条看哪一条;没点过看最要紧的那条;点「全场地图」回平时的样子,
  // 直到来了新的一条
  const [siteView, setSiteView] = useState(false);
  const [seenTop, setSeenTop] = useState<string | null>(null);
  // 单台机器人控制(第 4 期 G-robot):右栏「Details」打开;来了新的告警切回告警
  const [ctl, setCtl] = useState<string | null>(null);
  // G-compact(≤1439 宽):右栏收成窄栏,巡逻 / 活动点开在原地盖一层
  const [rail, setRail] = useState<"patrol" | "activity" | null>(null);
  // 回放(第五期 G-playback):点「本班已关闭」的一件或时间轴某一刻;来了新的告警回到实时
  const [play, setPlay] = useState<Playback | null>(null);
  const [playHead, setPlayHead] = useState<number | null>(null);
  // 外审 1 #1 / 外审 2 #1:只有**新来的**一条(这个标签页里第一次见到的键)顶到最上面,之前点开的那件才让开;
  // 确认、关闭、现场更新引起的重排不动人家正在处理的那件(不然接手一条,中央就跳到另一条)
  const seenKeys = useRef<Set<string>>(new Set());
  const topIsNew = !!top && !seenKeys.current.has(top.key);
  if ((top?.key ?? null) !== seenTop) {
    setSeenTop(top?.key ?? null);
    if (top && top.key !== seenTop && topIsNew) { setSiteView(false); setCtl(null); setPlay(null); setDetail(null); }
  }
  for (const a of alarms) seenKeys.current.add(a.key);
  const picked = detail ? props.alerts.find((a) => a.key === detail) ?? recent.find((a) => a.key === detail) ?? null : null;
  const focus = picked ?? (!siteView ? top ?? null : null);
  const openAlarm = (a: Alert) => { setSelected(a.robot); setDetail(a.key); setSiteView(false); setCtl(null); setPlay(null); };
  useEffect(() => { if (props.openKey) { setDetail(props.openKey); setSiteView(false); setCtl(null); setPlay(null); } }, [props.openKey]);
  const robotIds = props.units.map((u) => u.robot.robot_id);
  const replay = (a: Alert) => { setCtl(null); setPlay({ key: a.key, robot: playRobot(a, robotIds), at: a.first_ms }); setPlayHead(a.first_ms); };
  const playAlert = play?.key ? recent.find((a) => a.key === play.key) ?? props.alerts.find((a) => a.key === play.key) ?? null : null;
  const held = props.units.filter((u) => u.robot.held != null);
  const noHome = props.units.filter((u) => u.state !== "offline" && u.robot.home_set === false);
  const fixHome = pageAllowed("admin/localization", props.role);
  const [askResume, setAskResume] = useState(false);

  async function post(path: string) {
    try {
      await api("POST", path, {});
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) props.say(t("dutyGone"));
      else props.say(t("failed", { why: e instanceof ApiError ? e.message : String(e) }));
    }
    await props.refresh();
  }
  async function resumeAll() {
    setAskResume(false);
    const res = await Promise.allSettled(held.map((u) => api("POST", `/api/robots/${enc(u.robot.robot_id)}/resume`, {})));
    const bad = res.filter((r) => r.status === "rejected").length;
    props.say(bad ? t("failed", { why: `${bad}/${held.length}` }) : t("dutyResumed", { n: held.length }));
    await props.refresh();
  }

  const zoneOf = (u: UnitInfo): string => {
    const p = u.robot.loc?.pose;
    if (!p) return "";
    return areas.find((a) => pointInPolygon([p.x, p.y], a.pts))?.name ?? "";
  };
  function sceneOf(a: Alert | undefined): Scene | undefined {
    if (!a || a.audience !== "intrusion" || !a.context?.zone) return undefined;
    const c = cams.find((x) => x.zone === a.context?.zone);
    return c ? { label: c.name, src: `/api/cameras/${enc(c.name)}/live`, health: `/api/cameras/${enc(c.name)}/health` } : undefined;
  }

  // ---- 状态头 ----
  const mustArrive = (a: Alert) => ARRIVE.has(a.kind) && a.context?.arrived_ms == null;
  let head: { sign: "ok" | "warn" | "bad" | "info"; title: string; sub: string; acts?: preact.ComponentChildren };
  if (top) {
    head = {
      sign: top.level === "P1" ? "bad" : "warn",
      title: alertHeadline(top),
      sub: [top.level, top.context?.zone ?? top.context?.where ?? "", nameOf(top.robot), hm(top.first_ms),
        followText(top.context), seenByText(top.context),
        top.context?.arrived_by ? t("dutyArrived", { who: top.context.arrived_by }) : mustArrive(top) ? t("dutyArriveFirst")
          : top.acked_ms != null && top.acked_by ? t("dutyTakenBy", { who: byText(top.acked_by) }) : "",
        alarms.length > 1 ? t("dutyMore", { n: alarms.length - 1 }) : ""].filter(Boolean).join(" · "),
      acts: (
        <>
          {can && top.acked_ms == null && <button type="button" class="btn primary" onClick={() => void post(`/api/alerts/${enc(top.key)}/ack`)}>{t("dutyTake")}</button>}
          {can && mustArrive(top) && <button type="button" class="btn" onClick={() => void post(`/api/alerts/${enc(top.key)}/arrive`)}>{t("dutyArrive")}</button>}
          {can && LOST.has(top.kind) && <button type="button" class="btn" onClick={() => { setFinding(top.robot); setSelected(top.robot); }}>{t("dutyFindPose")}</button>}
          <button type="button" class="btn" onClick={() => openAlarm(top)}>{t("monOpenIncident")}</button>
        </>
      ),
    };
  } else if (props.stale) {
    head = { sign: "warn", title: t("dutyUnknown"), sub: t("dutyUnknownSub") };
  } else if (held.length > 0) {
    // G-estop:谁几点按的(取最早那一次);恢复在页头原地确认
    const first = held.map((u) => u.robot.held as { by?: string; at_ms?: number } | null).filter((h) => h?.at_ms != null)
      .sort((a, b) => (a!.at_ms ?? 0) - (b!.at_ms ?? 0))[0];
    head = {
      sign: "bad", title: t("monHeld", { n: held.length }),
      sub: first?.by ? t("monHeldSub", { by: byText(first.by), t: hm(first.at_ms ?? 0) }) : `${joinList(held.map((u) => nameOf(u.robot.robot_id)))} · ${t("dutyHeldSub")}`,
      acts: canDispatch(props.role) && !askResume && <button type="button" class="btn primary" onClick={() => setAskResume(true)}>{t("monResetAll")}</button>,
    };
  } else if (noHome.length > 0) {
    head = {
      sign: "warn", title: t("dutyNoHome", { ids: andList(noHome.map((u) => nameOf(u.robot.robot_id))) }), sub: fixHome ? "" : t("dutyNoHomeGuard"),
      acts: fixHome && <a class="btn" href="#/admin/localization">{t("dutyNoHomeGo")}</a>,
    };
  } else {
    const busy = ranked.filter((u) => u.state !== "offline" && u.task).map((u) => `${nameOf(u.robot.robot_id)} ${u.taskShort || u.task}`);
    head = { sign: "ok", title: t("monAllNormal"), sub: [props.mode ? modeLabel(props.mode) : "", ...busy].filter(Boolean).join(" · ") };
  }

  // ---- 画面 ----
  const slots = pickSlots(ranked, pins, alarms);
  const slot = (s: SlotPick | null, i: 0 | 1) => {
    const u = s ? unitOf(s.robot) : undefined;
    if (!s || !u) return <div key={`e${i}`} class="slot empty-slot" />;
    return (
      <VideoSlot key={`${i}:${s.robot}:${s.alert?.key ?? ""}`} u={u} now={props.now} pinned={pins[i] === s.robot} thermal={thermal}
        onPin={() => setPins((p) => { const n: [string | null, string | null] = [p[0], p[1]]; n[i] = n[i] === s.robot ? null : s.robot; return n; })}
        onZoom={() => props.onZoom(s.robot)} forceLive={!!s.alert} scene={sceneOf(s.alert)} alarm={!!s.alert} />
    );
  };
  const put = (robot: string) => setPins((p) => (p[0] == null || p[1] != null && p[0] !== robot ? [robot, p[1]] : [p[0], robot]));
  const anyThermal = props.units.some((u) => robotCams(u.robot).includes("thermal"));
  const LAYOUT_KEYS: Record<VideoLayout, Key> = { single: "monSingle", dual: "monDual", multi: "monMulti", wall: "monWall" };
  const layouts: { v: VideoLayout; key: Key }[] = videoLayoutsFor(props.units.length).map((v) => ({ v, key: LAYOUT_KEYS[v] }));
  // 单:只有一台 —— 前、后两路分开放(有热像、点了「全部热像」时前面那格换热像)
  const one = ranked[0];
  const oneAlarm = !!slots[0]?.alert;
  const singleTiles = one ? (["front", "back"] as const).map((cam) => {
    const id = one.robot.robot_id;
    const c = cam === "front" && thermal && robotCams(one.robot).includes("thermal") ? "thermal" : cam;
    return { key: `${id}:${c}`, label: camLabel(id, c),
      el: one.state === "offline" ? <div class="slot-off">{t("st_offline")}</div>
        : <CameraWell robot={id} cam={c} now={props.now} variant="main" forceLive={oneAlarm} onOpen={() => props.onZoom(id)} /> };
  }) : [];
  const presets: { v: MapPreset; key: Key }[] = [{ v: "all", key: "monPAll" }, { v: "route", key: "monPRoutes" }, { v: "zones", key: "monPZones" }, { v: "cameras", key: "monPCams" }];
  const byIncident = focus && focus.resolved_ms == null ? [...ranked].sort((x, y) => near(x) - near(y)) : ranked;
  function near(u: typeof ranked[number]): number {
    if (!focus) return 0;
    if (u.robot.robot_id === focus.robot) return -1;
    const d = responder({ ...focus, robot: "" }, [u]);
    return d?.dist ?? Number.POSITIVE_INFINITY;
  }
  const activity = recentActivity(recent.filter(forGuard), patrols, since, props.now).slice(0, 6);
  const ctlUnit = ctl ? unitOf(ctl) : undefined;
  // G-multi:两件以上安全事件开着、没点进哪一件:先看全局
  const multi = !picked && !siteView && security.length >= 2;

  return (
    <div class={`mon${layout === "wall" ? " wall" : ""}`} data-head={head.sign}>
      <aside class="mon-left" aria-label={t("monQueue")}>
        <section class="mon-sec">
          <h2 class="mon-h"><span>{t("monSecurity")}{security.length > 0 && ` ${security.length}`}</span><small>{t("monSecurityHint")}</small></h2>
          {security.length === 0 ? <p class="mon-none"><Sign kind={props.stale ? "warn" : "ok"} />{t(props.stale ? "dutyStaleAlarms" : "monNoneOpen")}</p> : (
            <ul class="mon-q">{security.map((a) => <QueueRow key={a.key} a={a} on={focus?.key === a.key} onOpen={() => openAlarm(a)} />)}</ul>
          )}
        </section>
        <section class="mon-sec">
          <h2 class="mon-h"><span>{t("monEquipment")}{equipment.length > 0 && ` ${equipment.length}`}</span><small>{t("monEquipmentHint")}</small></h2>
          {equipment.length === 0 ? <p class="mon-none"><Sign kind={props.stale ? "warn" : "ok"} />{t(props.stale ? "dutyStaleAlarms" : "monNoneOpen")}</p> : (
            <ul class="mon-q">{equipment.map((a) => <QueueRow key={a.key} a={a} on={focus?.key === a.key} onOpen={() => openAlarm(a)} />)}</ul>
          )}
        </section>
        <section class="mon-sec mon-closed">
          <h2 class="mon-h"><span>{t("monClosed", { n: closed.length })}</span></h2>
          <ul class="mon-closedlist">
            {closed.slice(0, 12).map((a) => (
              <li key={a.key} class={play?.key === a.key ? "on" : ""}><button type="button" onClick={() => replay(a)}>
                <time class="mono">{hm(a.resolved_ms ?? a.first_ms)}</time>
                <span>{alertTitle(lang.value, a.kind, a.title)}</span>
                <span class="muted">{autoResolved(a) ? t("monAuto") : verdictText(a) || t("monResolved")}</span>
              </button></li>
            ))}
          </ul>
        </section>
        <Handover role={props.role} me={props.me ?? ""} />
      </aside>

      <section class="mon-center" aria-label={t("secMonitor")}>
        {play ? (
          <PlaybackView play={play} alert={playAlert} robots={robotIds} role={props.role} now={props.now} say={props.say}
            onHead={setPlayHead} onLive={() => { setPlay(null); setPlayHead(null); }} />
        ) : ctlUnit ? (
          <RobotControl u={ctlUnit} role={props.role} now={props.now} alerts={recent} patrols={patrols} since={since} say={props.say} refresh={props.refresh}
            onBack={() => setCtl(null)}
            onLook={(id) => { setCtl(null); setDetail(null); setSiteView(true); setSelected(id); setLookRobot(id); setTool("look"); }}
            onFind={(id) => { setCtl(null); setDetail(null); setSiteView(true); setSelected(id); setFinding(id); }} />
        ) : multi ? (
          <MultiView events={security} units={props.units} cams={cams} canTake={can} onOpen={openAlarm}
            onTake={(a) => void post(`/api/alerts/${enc(a.key)}/ack`)} map={(
              <div class="mon-map">
                <MapPage units={props.units} p1={alarms.filter((a) => a.level === "P1")} now={props.now} role={props.role} stale={props.stale}
                  selected={selected} onSelect={setSelected} mode={props.mode ?? null} say={props.say} preset="all" recent={recent} hot={hot}
                  onAreas={(a) => setAreas((old) => (old.length === a.length && old.every((x, i) => x.name === a[i].name) ? old : a))} />
              </div>
            )} />
        ) : focus ? (
          <IncidentView a={focus} units={props.units} alerts={props.alerts} now={props.now} role={props.role} mode={props.mode ?? null} stale={props.stale}
            cams={cams} layout={layout} onLayout={(l) => { setLayout(l); keep(LAYOUT_KEY, l); }} say={props.say} refresh={props.refresh}
            onSite={() => { setDetail(null); setSiteView(true); }} onZoom={props.onZoom}
            onFindPose={(r) => { setFinding(r); setSelected(r); setDetail(null); setSiteView(true); }}
            onAreas={(a) => setAreas((old) => (old.length === a.length && old.every((x, i) => x.name === a[i].name) ? old : a))} />
        ) : (<>
        <header class="mon-head" data-sign={head.sign}>
          <Sign kind={head.sign} />
          <div class="mon-head-text">
            <h1 title={head.title}>{head.title}</h1>
            {head.sub && <p title={head.sub}>{head.sub}</p>}
          </div>
          <div class="mon-head-acts">
            {head.acts}
            {/* 外审 1 #8:临时路线按 canPatrol(经理也能派巡逻),派去看一眼按 canDispatch */}
            {!top && canDispatch(props.role) && (
              <button type="button" class="btn" aria-pressed={tool === "look"} onClick={() => setTool(tool === "look" ? null : "look")}>{t("monLook")}</button>
            )}
            {!top && canPatrol(props.role) && (
              <button type="button" class="btn" aria-pressed={tool === "route"} onClick={() => setTool(tool === "route" ? null : "route")}>{t("monRoute")}</button>
            )}
          </div>
          {askResume && held.length > 0 && (
            <div class="mon-ask" role="group">
              <p>{t("dutyResumeAsk", { n: held.length })}</p>
              <button type="button" class="btn primary" onClick={() => void resumeAll()}>{t("dutyResumeAll")}</button>
              <button type="button" class="btn" onClick={() => setAskResume(false)}>{t("cancel")}</button>
            </div>
          )}
          {layout !== "wall" && (
            <div class="seg" role="tablist" aria-label={t("tabMap")}>
              {presets.map((p) => <button key={p.v} type="button" role="tab" aria-selected={preset === p.v} class={preset === p.v ? "on" : ""}
                onClick={() => { setPreset(p.v); keep(PRESET_KEY, p.v); }}>{t(p.key)}</button>)}
            </div>
          )}
        </header>
        {layout !== "wall" && (
          <div class="mon-map">
            <MapPage units={props.units} p1={alarms.filter((a) => a.level === "P1")} now={props.now} role={props.role} stale={props.stale}
              selected={finding ?? selected ?? slots[0]?.robot ?? null} onSelect={setSelected} mode={props.mode ?? null} say={props.say}
              preset={preset} tool={tool} onTool={setTool} recent={recent} hot={hot} finding={finding} lookRobot={lookRobot}
              onLocated={(id) => { setFinding(null); props.say(t("locDoneMsg", { id: nameOf(id) })); }}
              onAreas={(a) => setAreas((old) => (old.length === a.length && old.every((x, i) => x.name === a[i].name) ? old : a))} />
          </div>
        )}
        {/* I3 11-17:选点时视频收起,地图占满(原来地图只剩 296 px 高、卡片还盖住一块) */}
        {!(tool === "look" || tool === "route") && <section class="mon-video" aria-label={t("monVideo")}>
          <div class="mon-video-h">
            <h2>{t("monVideo")}</h2>
            <span class="push" />
            <div class="seg" role="tablist" aria-label={t("monVideo")}>
              {layouts.map((l) => <button key={l.v} type="button" role="tab" aria-selected={layout === l.v} class={layout === l.v ? "on" : ""}
                onClick={() => { setLayout(l.v); keep(LAYOUT_KEY, l.v); }}>{t(l.key)}</button>)}
            </div>
            {anyThermal && layout !== "wall" && <button type="button" class="btn" aria-pressed={thermal} onClick={() => setThermal(!thermal)}>{t("monAllThermal")}</button>}
          </div>
          {layout === "wall" ? <LiveWall units={props.units} alerts={props.alerts} now={props.now} onZoom={props.onZoom} />
            : layout === "single" ? (
              <div class="mon-tiles single">
                {singleTiles.length === 0 && <p class="muted">{t("dutyNoRobots")}</p>}
                {singleTiles.map((q) => <figure key={q.key} class="mon-tile"><figcaption>{q.label}</figcaption>{q.el}</figure>)}
              </div>
            ) : layout === "multi" ? (
              // 多:每台一格(大画面 + 小画面,跟双一样),两列,超出的滚
              <div class="mon-tiles many">
                {ranked.map((u) => {
                  const al = alarms.find((a) => a.robot === u.robot.robot_id);
                  return <VideoSlot key={`m:${u.robot.robot_id}`} u={u} now={props.now} pinned={false} thermal={thermal}
                    onZoom={() => props.onZoom(u.robot.robot_id)} forceLive={!!al} alarm={!!al} />;
                })}
              </div>
            ) : (
              <div class={`mon-tiles ${layout}`}>
                {slot(slots[0], 0)}
                {layout === "dual" && slot(slots[1], 1)}
              </div>
            )}
        </section>}
        </>)}
      </section>

      <aside class="mon-right" aria-label={t("monRobots")} data-rail={rail ?? undefined}>
        <section class="mon-sec mon-robots-sec">
          <h2 class="mon-h"><span>{t(play ? "pbRobotsLive" : focus && focus.resolved_ms == null && !ctlUnit && !multi ? "monRobotsNearest" : "monRobots")}</span>
            {play && <small>{t("pbRobotsLiveSub")}</small>}</h2>
          {ranked.length === 0 && <p class={props.stale ? "warn mon-pad" : "muted mon-pad"}>{t(props.stale ? "dutyStaleRobots" : "dutyNoRobots")}</p>}
          <ul class="mon-robots">
            {byIncident.map((u) => {
              const id = u.robot.robot_id;
              const sign = u.stale ? "warn" : u.robot.held != null ? "bad" : stateSign(u.state);
              const loc = locText(u);
              const dist = focus && focus.resolved_ms == null ? responder({ ...focus, robot: "" }, [u])?.dist ?? null : null;
              const sub = [awayText(dist, focus?.context?.zone ?? focus?.context?.where ?? ""), zoneOf(u), u.task, loc ? t(loc) : "", u.state !== "offline" && u.robot.home_set === false ? t("dutyRowNoHome") : ""].filter(Boolean).join(" · ");
              return (
                <li key={id} class={selected === id ? "mon-robot on" : "mon-robot"} data-robot={id}>
                  <div class="mon-robot-top">
                    <b class="mon-robot-id">{nameOf(id)}</b>
                    <span class={`mon-state ${sign}`}><Sign kind={sign} />{u.stale ? t("stUnknown") : u.robot.held != null ? t("st_estop") : t(`st_${u.state}` as Key)}</span>
                    {u.battery != null && <b class={u.battery < 30 ? "mon-batt low" : "mon-batt"}>{Math.round(u.battery)}%</b>}
                  </div>
                  {u.battery != null && <div class={u.battery < 30 ? "mon-bar low" : "mon-bar"}><i style={{ width: `${Math.max(0, Math.min(100, u.battery))}%` }} /></div>}
                  {sub && <p class="mon-robot-sub" title={sub}>{sub}</p>}
                  <div class="mon-robot-acts">
                    <button type="button" class="btn sm" onClick={() => { put(id); setSelected(id); if (layout === "wall") { setLayout("dual"); keep(LAYOUT_KEY, "dual"); } }}>{t("monViewVideo")}</button>
                    <button type="button" class="btn sm" data-robot-more={id} aria-pressed={ctl === id}
                      onClick={() => { setSelected(id); setCtl(ctl === id ? null : id); }}>{t("dutyDetails")}</button>
                  </div>
                </li>
              );
            })}
          </ul>
        </section>
        {playAlert && (
          <section class="mon-sec mon-pbhist" aria-label={t("pbHistory")}>
            <h2 class="mon-h"><span>{t("pbHistory")}</span></h2>
            <ol class="mon-activity">{incidentLog(playAlert).map((x, i) => <li key={i}><time class="mono">{hms(x.at)}</time><span>{x.text}</span></li>)}</ol>
            {can && playAlert.resolved_ms != null && props.now < playAlert.resolved_ms + REOPEN_MS && !autoResolved(playAlert) && (
              <button type="button" class="btn mon-pad" onClick={() => void post(`/api/alerts/${enc(playAlert.key)}/reopen`).then(() => { props.say(t("incReopened")); setPlay(null); openAlarm(playAlert); })}>
                {t("evReopenUntil", { t: hm(playAlert.resolved_ms + REOPEN_MS) })}
              </button>
            )}
          </section>
        )}
        <section class="mon-sec mon-tonight">
          <TodayPatrols canFix={pageAllowed("admin/robots", props.role)} onItems={setPatrols} title={t("monTonight")} guard />
        </section>
        <section class="mon-sec mon-act">
          <h2 class="mon-h"><span>{t("monActivity")}</span></h2>
          {activity.length === 0 ? <p class="muted mon-pad">{t("monNoActivity")}</p> : (
            <ul class="mon-activity">{activity.map((x, i) => <li key={i}><time class="mono">{hm(x.at)}</time><span>{x.text}</span></li>)}</ul>
          )}
        </section>
      </aside>

      <nav class="mon-rail" aria-label={t("monRobots")}>
        {ranked.map((u) => {
          const id = u.robot.robot_id;
          const low = u.battery != null && u.battery < 30;
          return (
            <button key={id} type="button" class={`mon-chip ${u.stale ? "warn" : stateSign(u.state)}${low ? " low" : ""}`} aria-pressed={ctl === id}
              title={u.stale ? t("stUnknown") : t(`st_${u.state}` as Key)} onClick={() => { setSelected(id); setCtl(ctl === id ? null : id); }}>
              <b>{nameOf(id)}</b>{u.battery != null && <small>{Math.round(u.battery)}%</small>}
            </button>
          );
        })}
        <span class="push" />
        <button type="button" class="mon-railbtn" aria-pressed={rail === "patrol"} onClick={() => setRail(rail === "patrol" ? null : "patrol")}>{t("monRailPatrol")}</button>
        <button type="button" class="mon-railbtn" aria-pressed={rail === "activity"} onClick={() => setRail(rail === "activity" ? null : "activity")}>{t("monRailActivity")}</button>
      </nav>

      <ShiftTimeline robots={ranked.map((u) => u.robot.robot_id)} patrols={patrols} alerts={recent} from={since} to={until} now={props.now} charging={charging}
        play={play ? playHead ?? play.at : null}
        onPick={(robot, at) => { setCtl(null); setPlay({ key: null, robot, at }); setPlayHead(at); }} />

    </div>
  );
}

function QueueRow({ a, on, onOpen }: { a: Alert; on: boolean; onOpen: () => void }) {
  const p1 = a.level === "P1";
  const who = a.acked_ms != null && a.acked_by ? t("monHandling", { who: byText(a.acked_by) }) : t("monUnassigned");
  return (
    <li class={`mon-qrow ${p1 ? "p1" : "p2"}${on ? " on" : ""}${a.acked_ms == null ? " fresh" : ""}`}>
      <button type="button" onClick={onOpen}>
        <Sign kind={p1 ? "bad" : "warn"} />
        <b>{alertHeadline(a)}</b>
        <span class={`mon-level ${p1 ? "p1" : "p2"}`}>{a.level}</span>
        <span class="mon-qsub">{[a.context?.zone ?? a.context?.where ?? "", nameOf(a.robot), hm(a.first_ms)].filter(Boolean).join(" · ")}</span>
        {(p1 || a.acked_ms != null) && <span class={a.acked_ms == null ? "mon-qwho none" : "mon-qwho"}>{who}</span>}
      </button>
    </li>
  );
}

/** 交班留言(原来在报警记录页):上一条 + 给下一班留一句。 */
function Handover({ role, me }: { role: string; me: string }) {
  const [note, setNote] = useState<Note | null>(null);
  const [draft, setDraft] = useState("");
  const [err, setErr] = useState("");
  const canNote = canHandleAlerts(role);
  const pull = () => api<{ latest: Note | null }>("GET", "/api/shift-notes").then((d) => setNote(d.latest ?? null)).catch(() => {});
  useEffect(() => { void pull(); }, []);
  async function save() {
    setErr("");
    try {
      await api("POST", "/api/shift-notes", { text: draft });
      setDraft("");
      await pull();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : String(e));
    }
  }
  return (
    <section class="mon-note" aria-label={t("monNoteTitle")}>
      <h3 class="lbl">{note ? t(note.author === me ? "alNoteMine" : "alNoteFrom", { who: note.author, t: hm(note.at_ms) }) : t("alNoteNone")}</h3>
      {note && <p>{note.text}</p>}
      {canNote && (
        <>
          <label class="lbl" for="mon-note-text">{t("alNoteLabel")}</label>
          <textarea id="mon-note-text" rows={2} maxLength={500} placeholder={t("alNoteHint")} value={draft}
            onInput={(e) => setDraft((e.target as HTMLTextAreaElement).value)} />
          {draft.trim() && <button type="button" class="btn sm" onClick={save}>{t("alNoteSave")}</button>}
          {err && <p class="error">{err}</p>}
        </>
      )}
    </section>
  );
}
