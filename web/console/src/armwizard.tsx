// 布防向导(用户 11-13):布防要先画防区 → 防区路线 → 布防时间 → 值守方案,散在三个页面,用户自己配都卡住了
// (存了防区路线没进值守方案,机器人又只许手动派,系统也没说为什么不走)。点「布防」时缺哪样就开这个向导,
// 一步步做完;已经做好的步骤打勾,可以直接往下。画防区、改路线就地嵌布置页的编辑器,不跳页面。
import { useEffect, useState } from "preact/hooks";
import { api, ApiError } from "./api";
import { robotNames } from "./data";
import { Confirm, Modal } from "./dialogs";
import { siteStr } from "./sitetext";
import { lang, type Lang } from "./i18n";
import { LayoutPage } from "./layoutpage";
import { GuardRoutesTab } from "./layoutroutes";
import { ZonesTab } from "./layoutzones";
import { addBlock, toWire, type Slot, type WireSlot } from "./armgrid";
import type { PreviewMeta } from "./mapview";
import type { GuardEntry, Plan, Status } from "./armguard";
import { previewChanges } from "./armingpage";

export type Missing = "zones" | "route" | "plan" | "robot";
export interface ReadyRoute { id: string; title: string; zones: string[]; in_plan: boolean }
export interface ReadyRobot { id: string; code: string; why: string }
export interface Readiness { map_id: string; map_version: string; zones: string[]; routes: ReadyRoute[]; robots: ReadyRobot[]; missing: Missing[] }
interface MapPick { map_id: string; version: string }
interface Sched { enabled: boolean; slots: WireSlot[] }
type Say = (s: string) => void;

const en = {
  title: "Arming wizard",
  lead: "Set up what the robots do while armed. Finished steps are ticked; you can skip ahead.",
  s1: "Zones", s2: "Patrol route", s3: "When to arm", s4: "Who patrols", s5: "Confirm",
  map: "Map: {map} v{ver}",
  zonesHave: "Zones on this map: {list}",
  zonesNone: "This map has no zones yet.",
  zoneWhole: "Use the whole map as one zone",
  zoneWholeName: "Whole site",
  zoneDraw: "Draw zones on the map",
  zoneEdit: "Edit zones on the map",
  hideEditor: "Close the editor",
  routeHave: "Zone routes on this map (pick the one the robots run):",
  routeNone: "No zone route on this map yet.",
  routeVia: "via {zones}",
  routeGen: "Generate from the zones",
  routeGenAgain: "Generate a new one from the zones",
  routeEdit: "Edit routes on the map",
  routeGenTitle: "Zone patrol ({map} v{ver})",
  routeGenNone: "No reachable points in the zones: {why}",
  routeSavedN: "Saved route {name}: {n} points.",
  routeProblems: "The generated route has problems. Fix the red points in the editor below and save.",
  schedKeep: "Keep the current arming times ({n} blocks)",
  schedManual: "No timetable: I arm and disarm by hand",
  schedEvery: "Every day from", schedTo: "to", schedArmed: "",
  schedReplace: "This replaces the current arming times.",
  schedFine: "Fine-tune per weekday or per zone on the Arming times page.",
  who: "Robot",
  whoAny: "Any available robot",
  gap: "Rest between laps",
  gapNone: "None (next lap right away)",
  gapMin: "{n} min",
  robotOk: "can patrol",
  robotFix: "Allow automatic dispatch",
  robotPage: "Open robot page",
  noRobot: "No robot can patrol this map yet.",
  sumMap: "Map", sumZones: "Zones", sumRoute: "Route", sumTime: "Arming times", sumWho: "Who",
  sumManual: "armed and disarmed by hand",
  sumSlots: "{n} blocks a week",
  stillMissing: "Robots will not patrol yet: {why}",
  armNow: "Arm now",
  armOnly: "Arm without robot patrols",
  done: "Done",
  back: "Back", next: "Next",
  armed: "Armed.",
  started: "{robot} has set off on the zone route.",
  runLine: "{robot} is running “{route}”, lap {lap}.",
  restLine: "{robot} is waiting for the next lap of “{route}”.",
  restWhyLine: "{robot} is waiting for the next lap of “{route}”: {why}",
  watchLine: "{robot} finished lap {lap} and is standing at the watch post of “{route}”.",
  pauseLine: "{robot} has paused on “{route}”.",
  pauseWhyLine: "{robot} has paused on “{route}”: {why}",
  waitLine: "“{route}” has not started: {why}",
  sumPlan: "Guard plan",
  waiting: "Not started yet: {why}",
  watching: "Checking whether a robot sets off…",
  noStart: "No robot has set off yet. The guard status on the Arming times page says why.",
  needZones: "this map has no zones",
  needRoute: "there is no zone route",
  needPlan: "no zone route is assigned to a robot",
  needRobot: "no robot can be dispatched",
  openWizard: "Open the arming wizard",
  routeNoZone: "passes through no zone, robots will not run it",
  dropEdits: "The editor has unsaved changes. Discard them?",
  dropPage: "This page has unsaved changes. The arming wizard may change the same settings, so these changes will be discarded.",
  routeIdFull: "Could not find a free route id. Create the route on Setup → Zone routes.",
  dropArming: "This page has unsaved arming-time changes. The wizard may change arming times too, so these changes will be discarded.",
  dropYes: "Discard",
  timeGoOn: "Save these times",
  notPatrolling: "Armed, but robots will not patrol on their own: {why}.",
};
type WKey = keyof typeof en;
const zh: Record<WKey, string> = {
  title: "布防向导",
  lead: "设置布防时机器人做什么。做好的步骤已打勾，可以直接往下。",
  s1: "防区", s2: "巡逻路线", s3: "什么时候布防", s4: "谁去巡逻", s5: "确认",
  map: "地图：{map} 第 {ver} 版",
  zonesHave: "这张图上的防区：{list}",
  zonesNone: "这张图上还没有防区。",
  zoneWhole: "整张图作为一个防区",
  zoneWholeName: "全场",
  zoneDraw: "在地图上画防区",
  zoneEdit: "在地图上修改防区",
  hideEditor: "收起编辑器",
  routeHave: "这张图上的防区路线（选一条让机器人跑）：",
  routeNone: "这张图上还没有防区路线。",
  routeVia: "经过 {zones}",
  routeGen: "按防区自动生成",
  routeGenAgain: "按防区重新生成一条",
  routeEdit: "在地图上修改路线",
  routeGenTitle: "防区巡逻（{map} 第 {ver} 版）",
  routeGenNone: "防区里没有机器人走得到的点：{why}",
  routeSavedN: "已保存路线「{name}」，共 {n} 个点。",
  routeProblems: "生成的路线有问题：请在下面的编辑器里改好红色的点，再保存。",
  schedKeep: "保留现在的布防时间（{n} 段）",
  schedManual: "不按时间，自己手动布防、撤防",
  schedEvery: "每天", schedTo: "到", schedArmed: "布防",
  schedReplace: "会替换现在的布防时间。",
  schedFine: "要按星期、按防区细调，请到「布防时间」页。",
  who: "机器人",
  whoAny: "哪台空就派哪台",
  gap: "每圈之间休息",
  gapNone: "不休息（跑完马上下一圈）",
  gapMin: "{n} 分钟",
  robotOk: "能派",
  robotFix: "改成自动派遣",
  robotPage: "去机器人页",
  noRobot: "还没有能在这张图上巡逻的机器人。",
  sumMap: "地图", sumZones: "防区", sumRoute: "路线", sumTime: "布防时间", sumWho: "谁去",
  sumManual: "手动布防、撤防",
  sumSlots: "每周 {n} 段",
  stillMissing: "机器人还不会巡逻：{why}",
  armNow: "现在布防",
  armOnly: "只布防，不让机器人巡逻",
  done: "完成",
  back: "上一步", next: "下一步",
  armed: "已布防。",
  started: "{robot} 已出发巡逻防区。",
  runLine: "{robot} 正在跑「{route}」，第 {lap} 圈。",
  restLine: "{robot} 在等「{route}」的下一圈。",
  restWhyLine: "{robot} 在等「{route}」的下一圈：{why}",
  watchLine: "{robot} 跑完第 {lap} 圈，在「{route}」的值守点守着。",
  pauseLine: "{robot} 在「{route}」上暂停了。",
  pauseWhyLine: "{robot} 在「{route}」上暂停了：{why}",
  waitLine: "「{route}」还没出发：{why}",
  sumPlan: "值守方案",
  waiting: "还没出发：{why}",
  watching: "正在看有没有机器人出发……",
  noStart: "还没有机器人出发，原因见「布防时间」页的值守状态。",
  needZones: "这张图上没有防区",
  needRoute: "没有防区路线",
  needPlan: "值守方案里没有给机器人分配防区路线",
  needRobot: "没有能派的机器人",
  openWizard: "打开布防向导",
  routeNoZone: "一个防区都不经过，机器人不会去跑",
  dropEdits: "编辑器里有没保存的修改，要丢掉吗？",
  dropPage: "这页还有没保存的修改。布防向导可能改同样的设置，打开向导会丢掉这些修改。",
  routeIdFull: "找不到空着的路线编号，请到「布置 → 防区路线」新建。",
  dropArming: "这页的布防时间还有没保存的修改。布防向导也会改布防时间，打开向导会丢掉这些修改。",
  dropYes: "丢掉",
  timeGoOn: "保存这个时间",
  notPatrolling: "布防着，但机器人不会自己巡逻：{why}。",
};
const DICTS: Record<Lang, Record<WKey, string>> = { en, zh };
export function wt(key: WKey, vars?: Record<string, string | number>): string {
  let s = DICTS[lang.value][key] ?? en[key];
  if (vars) for (const [k, v] of Object.entries(vars)) s = s.split(`{${k}}`).join(String(v));
  return s;
}
const who = (rid: string) => robotNames.value[rid] || rid;
const errText = (e: unknown) => (e instanceof ApiError ? e.message : String(e));
const enc = encodeURIComponent;
const GAPS = [0, 10, 15, 30, 60];

/** 向导用哪张图:站点挑(机器人在用最多的那一版;没有就最新登记的正式版,不挑草稿)—— 跟手机同一张(外审 1 #8)。 */
export async function pickMap(): Promise<MapPick | null> {
  const r = await api<Readiness>("GET", "/api/guard/readiness");
  return r.map_id ? { map_id: r.map_id, version: r.map_version } : null;
}

export async function readiness(map: MapPick): Promise<Readiness> {
  return api<Readiness>("GET", `/api/guard/readiness?map_id=${enc(map.map_id)}&map_version=${enc(map.version)}`);
}

const ROBOT_EN: Record<string, string> = {
  unregistered: "{id} is not registered", offline: "{id} is offline", stale: "{id} has not reported for a while",
  manual_only: "{id} is set to manual dispatch only", supervised: "{id} needs a person beside it and does not go out alone",
  map: "{id} has a different map loaded",
  reserved: "{id} is assigned to another route in the guard plan",
};
/** 这台为什么派不了:中文界面用站点原话,英文界面按原因代号说。 */
export function robotWhy(x: ReadyRobot): string {
  if (lang.value === "zh" || !ROBOT_EN[x.code]) return x.why;
  return ROBOT_EN[x.code].split("{id}").join(who(x.id));
}

/** 布防着机器人为什么不会自己巡逻(一句话);都齐了 → 空串。 */
export function missingText(r: Readiness): string {
  const m = r.missing[0];
  if (!m) return "";
  if (m !== "robot") return wt(m === "zones" ? "needZones" : m === "route" ? "needRoute" : "needPlan");
  const bad = r.robots.filter((x) => x.code);
  return bad.length ? bad.map(robotWhy).join(lang.value === "zh" ? "；" : "; ") : wt("needRobot");
}

/** 点「布防」前查一下:要不要开向导(查不出来 → 不开,照原来的确认框)。 */
export async function needsWizard(): Promise<boolean> {
  try {
    const r = await api<Readiness>("GET", "/api/guard/readiness");
    return !!r.map_id && r.missing.length > 0;
  } catch {
    return false;
  }
}

/** UIUX-036:布防后按值守方案逐条说真话 —— 哪台在跑哪条路线第几圈、哪条在等、为什么。
 *  返回 [这几句, 是不是每条都有了结果]。 */
export function afterLines(entries: GuardEntry[], st: Status, title: (route: string) => string): [string[], boolean] {
  const out: string[] = [];
  let all = entries.length > 0;
  for (const e of entries) {
    const run = e.id == null ? undefined : st.runs.find((x) => x.entry === e.id);
    const raw = e.id == null ? "" : st.waiting[String(e.id)];
    const why = raw ? siteStr(raw) : "";
    const v = { robot: run ? who(run.robot_id) : "", route: title(e.route), lap: run ? Math.max(1, run.lap) : 1, why };
    // 外审:按站点的运行状态说(guard_duty.py):lap 在跑;watch / post 跑完一圈在值守点;
    // wait / resume 等下一圈(可能在补能);held / paused / stopping / standdown 停下了
    if (run?.state === "lap") out.push(wt("runLine", v));
    else if (run && (run.state === "watch" || run.state === "post")) out.push(wt("watchLine", v));
    else if (run && (run.state === "wait" || run.state === "resume")) out.push(wt(why ? "restWhyLine" : "restLine", v));
    else if (run) out.push(wt(why ? "pauseWhyLine" : "pauseLine", v));
    else if (why) out.push(wt("waitLine", v));
    else all = false;
  }
  return [out, all];
}

/** 每天 from–to 布防(跨半夜的拆成两段),全部防区一样。 */
export function dailySlots(from: number, to: number): WireSlot[] {
  let s: Slot[] = [];
  for (let d = 0; d < 7; d++) {
    if (to > from) s = addBlock(s, "", d, from, to);
    else {
      s = addBlock(s, "", d, from, 1440);
      if (to > 0) s = addBlock(s, "", (d + 1) % 7, 0, to);
    }
  }
  return toWire(s);
}
const minutes = (hm: string) => { const [h, m] = hm.split(":").map(Number); return (h || 0) * 60 + (m || 0); };

/** 整张图的外框(地图坐标,米)。 */
export function wholeMap(meta: PreviewMeta): [number, number][] {
  const x0 = meta.left_x, y1 = meta.top_y;
  const x1 = x0 + meta.width * meta.m_per_px, y0 = y1 - meta.height * meta.m_per_px;
  return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]];
}

export function ArmWizard({ say, onClose, arming = false, onChanged }: { say: Say; onClose: () => void; arming?: boolean; onChanged?: () => void }) {
  const [map, setMap] = useState<MapPick | null>(null);
  const [r, setR] = useState<Readiness | null>(null);
  const [plan, setPlan] = useState<Plan | null>(null);
  const [sched, setSched] = useState<Sched | null>(null);
  const [step, setStep] = useState(0);
  const [started, setStarted] = useState(false);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [editor, setEditor] = useState<"zones" | "guard" | null>(null);
  const [route, setRoute] = useState("");
  const [robot, setRobot] = useState("");
  const [gap, setGap] = useState(0);
  const [time, setTime] = useState<"keep" | "manual" | "daily">("daily");
  const [from, setFrom] = useState("21:30");
  const [to, setTo] = useState("06:00");
  const [note, setNote] = useState("");
  const [after, setAfter] = useState("");
  // 外审 1 #6:嵌着的编辑器有没存的改动时,换步、收起、关向导先问
  const [editorDirty, setEditorDirty] = useState(false);
  const [askDrop, setAskDrop] = useState<(() => void) | null>(null);
  const guarded = (go: () => void) => (editor && editorDirty ? setAskDrop(() => go) : go());
  const closeEditor = () => { setEditor(null); setEditorDirty(false); };
  // 外审 1 #2:存下去会马上撤防 / 布防的,先说清楚
  const [askTime, setAskTime] = useState<{ text: string; body: Sched } | null>(null);

  async function load(m: MapPick | null = map, first = false) {
    if (!m) return;
    try {
      const [got, p, s] = await Promise.all([readiness(m), api<Plan>("GET", "/api/guard/plan"),
        api<Sched>("GET", "/api/arming/schedule")]);
      setR(got);
      setPlan(p);
      setSched(s);
      const usable = got.routes.filter((x) => x.zones.length);
      const mine = usable.find((x) => x.in_plan) ?? usable[0];
      setRoute((cur) => (usable.some((x) => x.id === cur) ? cur : mine?.id ?? ""));
      const e = p.entries.find((x) => x.route === mine?.id);
      if (first) {
        if (e) { setRobot(e.robot); setGap(e.gap_min); }
        if (s.enabled && s.slots.length) setTime("keep");
        const order: Missing[] = ["zones", "route", "plan", "robot"];
        const at = order.findIndex((k) => got.missing.includes(k));
        setStep(at < 0 ? 4 : at < 2 ? at : 3);
        setStarted(true);
      }
    } catch (x) {
      setErr(errText(x));
    }
  }
  useEffect(() => {
    pickMap().then((m) => { setMap(m); if (m) void load(m, true); else setErr(wt("zonesNone")); }).catch((x) => setErr(errText(x)));
  }, []);

  const done = [!!r?.zones.length, !!route, !!sched?.enabled && !!sched.slots.length, !!r && !r.missing.includes("plan") && !r.missing.includes("robot"), false];
  const base = map ? `/api/maps/${enc(map.map_id)}/${enc(map.version)}` : "";

  /** 嵌着的编辑器存好了:重新查,也告诉外面。 */
  const changed = () => { onChanged?.(); return load(); };

  async function wholeZone() {
    setBusy(true);
    try {
      const meta = await api<PreviewMeta>("GET", `${base}/preview`);
      await api("POST", `${base}/areas`, { zone: wt("zoneWholeName"), points: wholeMap(meta) });
      await changed();   // 外审 3:背后的页要重读
    } catch (x) { say(errText(x)); } finally { setBusy(false); }
  }

  async function genRoute() {
    if (!map || !r) return;
    setBusy(true);
    setNote("");
    try {
      const g = await api<{ waypoints: unknown[]; problems?: unknown[]; zones: { zone: string; points: number; note?: string }[] }>(
        "POST", "/api/guard-routes/generate", { map_id: map.map_id, map_version: map.version, spacing_m: 6,
          zones: r.zones.map((z) => ({ zone: z, laps: 1, dwell_s: 0, photos: 1 })) });
      if (!g.waypoints.length) {
        setNote(wt("routeGenNone", { why: g.zones.map((z) => z.note).filter(Boolean).join("；") }));
        return;
      }
      const taken = new Set(r.routes.map((x) => x.id));
      const title = wt("routeGenTitle", { map: map.map_id, ver: map.version });
      let saved = "";
      // 外审 2 #5:前缀先截短,给「-2」「-20」留位置(编号最长 64)
      const head = `guard-${map.map_id}-${map.version}`.replace(/[^A-Za-z0-9_.-]/g, "-").slice(0, 60);
      for (let i = 1; i <= 20 && !saved; i++) {
        const id = `${head}${i > 1 ? `-${i}` : ""}`;
        if (taken.has(id)) continue;
        try {
          await api("POST", `/api/routes/${enc(id)}`, { map_id: map.map_id, map_version: map.version, waypoints: g.waypoints,
            policy: {}, base_revision: 0, kind: "guard", title });
          saved = id;
        } catch (x) {
          // 编号用过(删掉过的也算)换下一个;点有问题交给编辑器改
          if (x instanceof ApiError && (x.status === 409 || (x.status === 400 && /用过|已经有|已有/.test(x.message)))) continue;
          const errs = x instanceof ApiError ? (x.data as { errors?: unknown[] } | undefined)?.errors : undefined;
          if (Array.isArray(errs) && errs.length) {
            setNote(wt("routeProblems"));
            setEditor("guard");
            return;
          }
          throw x;
        }
      }
      if (saved) {
        setRoute(saved);
        say(wt("routeSavedN", { name: title, n: g.waypoints.length }));
        onChanged?.();
      } else setNote(wt("routeIdFull"));
      await load();
    } catch (x) { say(errText(x)); } finally { setBusy(false); }
  }

  async function allowAuto(rid: string) {
    setBusy(true);
    try {
      await api("POST", `/api/robots/${enc(rid)}/service`, { manual_only: false });
      await changed();
    } catch (x) { say(errText(x)); } finally { setBusy(false); }
  }

  /** 第 3 步的「下一步」:按选的存布防时间。 */
  async function saveTime(): Promise<boolean> {
    if (!sched || time === "keep") return true;
    if (time === "manual" && !sched.enabled) return true;
    const body: Sched = time === "manual" ? { enabled: false, slots: sched.slots } : { enabled: true, slots: dailySlots(minutes(from), minutes(to)) };
    try {
      const p = await api<{ before: Parameters<typeof previewChanges>[0]; after: Parameters<typeof previewChanges>[1] }>(
        "POST", "/api/arming/schedule/preview", body);
      // 外审 2 #2:预演失败不当成「没变化」,停下说原因(人可以再点一次)
      const warn = previewChanges(p.before, p.after);
      if (warn) { setAskTime({ text: warn, body }); return false; }
      await putTime(body);
      return true;
    } catch (x) { say(errText(x)); return false; }
  }
  async function putTime(body: Sched) {
    await api("POST", "/api/arming/schedule", body);
    onChanged?.();
    await load();
  }

  /** 第 4 步的「下一步」:值守方案里这条路线换成选的机器人(别的路线不动)。 */
  async function savePlan(): Promise<boolean> {
    if (!plan || !route) return false;
    // 外审 1 #1 #9:只换这条路线那一行(别的条目一条不动;同一台机器人指定两条由站点拒绝、写原因),
    // 界面上没有的选项(打乱、每圈回待命点)保留原来的
    const old = plan.entries.find((e) => e.route === route);
    const mine: GuardEntry = { route, robot, gap_min: gap, shuffle: old?.shuffle ?? false, end_standby: old?.end_standby ?? true };
    const entries: GuardEntry[] = old ? plan.entries.map((e) => (e === old ? mine : e)) : [...plan.entries, mine];
    try {
      await api("POST", "/api/guard/plan", { entries: entries.map(({ route, robot, gap_min, shuffle, end_standby }) =>
        ({ route, robot, gap_min, shuffle, end_standby: end_standby !== false })), limits: plan.limits, base_revision: plan.revision });
      onChanged?.();
      await load();
      return true;
    } catch (x) { say(errText(x)); return false; }
  }

  async function next() {
    setBusy(true);
    try {
      if (step === 2 && !(await saveTime())) return;
      if (step === 3 && !(await savePlan())) return;
      closeEditor();
      setNote("");
      setStep((s) => Math.min(4, s + 1));
    } finally { setBusy(false); }
  }

  async function arm(withPatrol: boolean) {
    setBusy(true);
    try {
      await api("POST", "/api/mode", { mode: "armed" });
      say(wt("armed"));
      if (!withPatrol) { onClose(); return; }
      setAfter(wt("watching"));
      // 布防后十几秒内说清楚:谁出发了,或者为什么没出发
      const entries = plan?.entries ?? [];
      for (let i = 0; i < 8; i++) {
        await new Promise((ok) => setTimeout(ok, 2000));
        const st = await api<Status>("GET", "/api/guard/status").catch(() => null);
        if (!st) continue;
        if (entries.length) {
          const [lines, all] = afterLines(entries, st, routeTitle);
          if (lines.length) setAfter(lines.join("\n"));
          if (all) return;
          continue;
        }
        const run = st.runs.find((x) => x.task_id);
        if (run) { setAfter(wt("started", { robot: who(run.robot_id) })); return; }
        const why = Object.values(st.waiting)[0];
        if (why) setAfter(wt("waiting", { why }));
      }
      setAfter((s) => (s === wt("watching") ? wt("noStart") : s));
    } catch (x) { say(errText(x)); } finally { setBusy(false); }
  }

  const steps: WKey[] = ["s1", "s2", "s3", "s4", "s5"];
  const robots = r?.robots ?? [];
  const sel = r?.routes.find((x) => x.id === route);
  const routeTitle = (id: string) => r?.routes.find((x) => x.id === id)?.title || id;
  const canNext = step === 0 ? !!r?.zones.length : step === 1 ? !!route : step === 3 ? !!route && !!plan : true;
  return (
    <Modal label={wt("title")} onClose={() => guarded(onClose)} wide cls="armwiz">
      <p class="muted small">{wt("lead")}</p>
      {map && <p class="small" data-wiz-map="1">{wt("map", { map: map.map_id, ver: map.version })}</p>}
      <ol class="wiz-steps" aria-label={wt("title")}>
        {steps.map((k, i) => (
          <li key={k} aria-current={i === step ? "step" : undefined} class={done[i] ? "done" : ""}>
            <button type="button" class="wiz-step" disabled={!started || busy} onClick={() => guarded(() => { closeEditor(); setNote(""); setStep(i); })}>
              {done[i] ? "✓ " : `${i + 1}. `}{wt(k)}
            </button>
          </li>
        ))}
      </ol>
      {err && <p class="bad" role="alert">{err}</p>}
      {r && step === 0 && (
        <section data-wiz-step="zones">
          <p>{r.zones.length ? wt("zonesHave", { list: r.zones.join("、") }) : wt("zonesNone")}</p>
          <div class="row wrap">
            {!r.zones.length && <button type="button" class="btn primary" disabled={busy} onClick={() => void wholeZone()}>{wt("zoneWhole")}</button>}
            <button type="button" class="btn" onClick={() => (editor === "zones" ? guarded(closeEditor) : setEditor("zones"))}>
              {editor === "zones" ? wt("hideEditor") : wt(r.zones.length ? "zoneEdit" : "zoneDraw")}</button>
          </div>
        </section>
      )}
      {r && step === 1 && (
        <section data-wiz-step="route">
          {r.routes.length ? (
            <fieldset class="wiz-pick">
              <legend>{wt("routeHave")}</legend>
              {r.routes.map((x) => (
                <label key={x.id}><input type="radio" name="wiz-route" checked={route === x.id} disabled={!x.zones.length} onChange={() => setRoute(x.id)} />
                  {" "}{x.title || x.id}{" "}
                  {x.zones.length ? <span class="muted small">{wt("routeVia", { zones: x.zones.join("、") })}</span>
                    : <span class="bad small" data-route-nozone="1">{wt("routeNoZone")}</span>}</label>
              ))}
            </fieldset>
          ) : <p>{wt("routeNone")}</p>}
          <div class="row wrap">
            <button type="button" class={r.routes.length ? "btn" : "btn primary"} disabled={busy || !r.zones.length} onClick={() => void genRoute()}>
              {wt(r.routes.length ? "routeGenAgain" : "routeGen")}</button>
            <button type="button" class="btn" onClick={() => (editor === "guard" ? guarded(closeEditor) : setEditor("guard"))}>
              {editor === "guard" ? wt("hideEditor") : wt("routeEdit")}</button>
          </div>
          {note && <p class="bad small" role="status">{note}</p>}
        </section>
      )}
      {r && sched && step === 2 && (
        <section data-wiz-step="time">
          <fieldset class="wiz-pick">
            {sched.enabled && sched.slots.length > 0 && (
              <label><input type="radio" name="wiz-time" checked={time === "keep"} onChange={() => setTime("keep")} /> {wt("schedKeep", { n: sched.slots.length })}</label>
            )}
            <label><input type="radio" name="wiz-time" checked={time === "daily"} onChange={() => setTime("daily")} />{" "}
              {wt("schedEvery")}{" "}
              <input type="time" step="1800" aria-label={wt("schedEvery")} value={from} onInput={(e) => setFrom(e.currentTarget.value)} />
              {" "}{wt("schedTo")}{" "}
              <input type="time" step="1800" aria-label={wt("schedTo")} value={to} onInput={(e) => setTo(e.currentTarget.value)} />
              {wt("schedArmed") && ` ${wt("schedArmed")}`}</label>
            <label><input type="radio" name="wiz-time" checked={time === "manual"} onChange={() => setTime("manual")} /> {wt("schedManual")}</label>
          </fieldset>
          {time === "daily" && sched.slots.length > 0 && <p class="small warn">{wt("schedReplace")}</p>}
          <p class="muted small">{wt("schedFine")}</p>
        </section>
      )}
      {r && step === 3 && (
        <section data-wiz-step="who">
          <p>{wt("sumRoute")}：{sel ? sel.title || sel.id : "—"}</p>
          <div class="row wrap">
            <label class="field-inline">{wt("who")}
              <select value={robot} onChange={(e) => setRobot(e.currentTarget.value)}>
                <option value="">{wt("whoAny")}</option>
                {robots.map((x) => <option key={x.id} value={x.id}>{who(x.id)}</option>)}
              </select>
            </label>
            <label class="field-inline">{wt("gap")}
              <select value={String(gap)} onChange={(e) => setGap(Number(e.currentTarget.value))}>
                {GAPS.map((g) => <option key={g} value={String(g)}>{g ? wt("gapMin", { n: g }) : wt("gapNone")}</option>)}
              </select>
            </label>
          </div>
          <ul class="wiz-robots">
            {robots.length === 0 && <li class="bad">{wt("noRobot")}</li>}
            {robots.filter((x) => !robot || x.id === robot).map((x) => (
              <li key={x.id} data-wiz-robot={x.id}>
                <b>{who(x.id)}</b>{" "}
                {x.code ? <span class="bad">{robotWhy(x)}</span> : <span class="ok">✓ {wt("robotOk")}</span>}
                {x.code === "manual_only" && <button type="button" class="btn sm" disabled={busy} onClick={() => void allowAuto(x.id)}>{wt("robotFix")}</button>}
                {x.code && x.code !== "manual_only" && <a class="btn sm" href={`#/admin/robots/${enc(x.id)}`} onClick={onClose}>{wt("robotPage")}</a>}
              </li>
            ))}
          </ul>
        </section>
      )}
      {r && sched && step === 4 && (
        <section data-wiz-step="confirm">
          <dl class="wiz-sum">
            <dt>{wt("sumMap")}</dt><dd>{map?.map_id} · v{map?.version}</dd>
            <dt>{wt("sumZones")}</dt><dd>{r.zones.join("、") || "—"}</dd>
            <dt>{wt("sumRoute")}</dt><dd>{sel ? sel.title || sel.id : "—"}</dd>
            <dt>{wt("sumTime")}</dt><dd>{sched.enabled && sched.slots.length ? wt("sumSlots", { n: sched.slots.length }) : wt("sumManual")}</dd>
            <dt>{wt("sumWho")}</dt><dd>{robot ? who(robot) : wt("whoAny")}</dd>
            {/* UIUX-036:值守方案里不止这一条时,全列出来(布防后它们都会跑) */}
            {plan && plan.entries.length > 1 && <><dt>{wt("sumPlan")}</dt><dd data-wiz-plan="1">{plan.entries.map((e) =>
              lang.value === "zh" ? `${routeTitle(e.route)}（${e.robot ? who(e.robot) : wt("whoAny")}）`
                : `${routeTitle(e.route)} (${e.robot ? who(e.robot) : wt("whoAny")})`).join(lang.value === "zh" ? "；" : "; ")}</dd></>}
          </dl>
          {r.missing.length > 0 && <p class="bad" role="status" data-wiz-missing="1">{wt("stillMissing", { why: missingText(r) })}</p>}
          {after && <div role="status" data-wiz-after="1">{after.split("\n").map((x, i) => <p key={i}>{x}</p>)}</div>}
        </section>
      )}
      {editor && map && (
        <div class="wiz-editor">
          <LayoutPage say={say} robots={robots.map((x) => x.id)} tabs={editor === "zones" ? { zones: ZonesTab } : { guard: GuardRoutesTab }}
            embed={{ tab: editor, map, onSaved: () => void changed(), onDirty: setEditorDirty }} />
        </div>
      )}
      {askDrop && <Confirm text={wt("dropEdits")} yes={wt("dropYes")} danger onNo={() => setAskDrop(null)}
        onYes={() => { const go = askDrop; setAskDrop(null); closeEditor(); go(); }} />}
      {askTime && <Confirm text={askTime.text} yes={wt("timeGoOn")} onNo={() => setAskTime(null)}
        onYes={() => {
          const b = askTime.body;
          setAskTime(null);
          setBusy(true);
          putTime(b).then(() => setStep(3)).catch((x) => say(errText(x))).finally(() => setBusy(false));
        }} />}
      <div class="row end wiz-actions">
        {arming && step < 4 && <button type="button" class="btn" disabled={busy} onClick={() => guarded(() => void arm(false))}>{wt("armOnly")}</button>}
        {step > 0 && <button type="button" class="btn" disabled={busy} onClick={() => guarded(() => { closeEditor(); setNote(""); setStep(step - 1); })}>{wt("back")}</button>}
        {step < 4 && <button type="button" class="btn primary" disabled={busy || !canNext || !started} onClick={() => guarded(() => void next())}>{wt("next")}</button>}
        {step === 4 && !after && <button type="button" class="btn primary" disabled={busy} onClick={() => void arm(true)}>{wt("armNow")}</button>}
        {step === 4 && <button type="button" class="btn" onClick={() => guarded(onClose)}>{wt("done")}</button>}
      </div>
    </Modal>
  );
}

/** 布防着却不会自己巡逻时说为什么(用户 11-13:配好了却没走,系统没说原因),带「打开布防向导」。 */
export function PatrolReason({ onWizard }: { onWizard: () => void }) {
  const [why, setWhy] = useState("");
  useEffect(() => {
    let live = true;
    const look = () => void pickMap().then((m) => (m ? readiness(m) : null))
      .then((r) => { if (live) setWhy(r ? missingText(r) : ""); }).catch(() => { if (live) setWhy(""); });
    look();
    const h = setInterval(look, 30_000);
    return () => { live = false; clearInterval(h); };
  }, []);
  if (!why) return null;
  return (
    <p class="note warn small" role="status" data-patrol-reason="1">
      {wt("notPatrolling", { why })}{" "}
      <button type="button" class="btn sm" onClick={onWizard}>{wt("openWizard")}</button>
    </p>
  );
}
