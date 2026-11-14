// 机器人页(W44 第二期,设计 §5.1「机器人」):每台一张卡片 —— 名字、在线、电量、今天巡了几趟、有没有毛病(站点
// /api/robots/overview 一次给全,今天按站点时区算)。点开是详情:改名字、软件版本、证书到期、最近的毛病、只能手动派 / 自动派、
// 重出开通码、解绑(确认 + 再输一次密码;解绑 = 机器人恢复出厂,W42)。
// W42:「添加」= 手机扫机器人贴纸;机器人连上站点后挂在本页顶上「等待批准加入」,核对 6 位核对码、再输密码批准。
// 机器人上有人提了换 WiFi:详情里确认 / 不换(卡片上标出来)。工程师的开通码流程收进「添加」里的一个按钮。
// 照片位这一期放图标;电池健康机器人还不报,不显示。
// W60 卡片分层:第一层名字、状态、在做什么、电量;第二层定位、网络、今天几趟;出了毛病才多一条琥珀色提示
// (正常时安静,不写「正常」)。在做什么、定位从值班的实时数据来(units),概况接口没有。
import { siteKnown, siteStr, zhPunct } from "./sitetext";
import { useCallback, useEffect, useRef, useState } from "preact/hooks";
import { api, ApiError, enc } from "./api";
import { ConfirmPassword } from "./confirmpw";
import { hm, robotNames, siteDown } from "./data";
import { Confirm, Modal } from "./dialogs";
import { alertTitle, lang, refusalText, t, type Key } from "./i18n";
import { autoResolved, canDispatch, canFindPose, canPatrol, canTeleop, isOwnerLike } from "./model";
import { notAccepted, type CommandReply } from "./posepick";
import { siteHm } from "./todaypatrols";
import { Shape } from "./icons";
import { locText, StateText, type UnitInfo } from "./live";
import { lapText, LoopsSelect } from "./loops";

type Say = (s: string) => void;
export interface RobotCard {
  robot_id: string; name: string; revoked: boolean; expires_at: number; online: boolean; battery_pct: number | null; patrols_today: number;
  /** W71 ``nav2``:Nav2 没起来(机器人退回自带规划)。 */
  problems: ({ key: string; kind: string; first_ms: number } | { device: string; state: string } | { nav2: string })[];
  /** W72:``level``、``resolved_by`` 老站点没有。 */
  recent_problems: RecentProblem[];
  agent: string | null; compat: string; manual_only: boolean;
  wifi?: Wifi | null;
  /** W72 详情:老站点没有这些。 */
  /** 第 2 轮 N2:当前地图那一版有没有原点(没报地图 = null)、有没有默认待命点。老站点没有。 */
  home_set?: boolean | null; standby_set?: boolean;
  patrols_7d?: number; aborts_7d?: number; last_patrol_ms?: number | null; last_seen_ms?: number | null; ever_seen?: boolean;
  storage?: { used_ratio: number; backlog_files: number | null; oldest_backlog_s: number | null } | null;
  map?: { id: string; version: string | null; match: boolean | null } | null;
  devices?: { id: string; state: string; detail?: string }[];
  enrolled_at?: number | null; manual_note?: string; held?: { by: string; at_ms: number } | null;
  /** POC:能换哪几种姿态、正在跑的任务(老站点没有)。 */
  postures?: Posture[]; task?: string | null;
  /** 第 9 轮 W9-06:正在跑的任务给人看的说法(不露 adhoc-forever-… 这种编号)。 */
  task_what?: { kind: string; route: string; forever: boolean } | null;
  /** W76:正在跑几圈的巡逻 —— 第几圈、共几圈(0 = 一直巡逻)。一圈的、老站点没有。 */
  lap?: { n: number; of: number } | null;
}
export type Posture = "stand" | "lie" | "crawl";
const POSTURE_KEY: Record<Posture, "rdStand" | "rdLie" | "rdCrawl"> = { stand: "rdStand", lie: "rdLie", crawl: "rdCrawl" };
export interface Wifi {
  ssid: string; link: "wifi" | "4g" | "none";
  change: { id: string; ssid: string; mode: "online" | "trial"; expires_ms: number | null } | null;
}
export interface BindReq {
  id: string; serial: string; check: string; model: string; version: string; source: string; created_ms: number; expires_ms: number;
}
/** 等待批准、卡片多久刷一次(机器人申请过来要尽快看到)。 */
const REFRESH_MS = 10_000;

function errText(e: unknown): string {
  return t("failed", { why: e instanceof ApiError ? e.message : String(e) });
}

function day(ms: number): string {
  const d = new Date(ms);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

const label = (r: RobotCard) => r.name || r.robot_id;

function problemText(p: RobotCard["problems"][number], r?: RobotCard): string {
  if ("nav2" in p) return t("robotNav2Down", { why: p.nav2 });
  if ("kind" in p) return alertTitle(lang.value, p.kind, p.kind);
  // 第 9 轮 W9-09:盘只是快满了,写「存储盘快满(86%)」,不写「disk 异常」
  const used = r?.storage?.used_ratio;
  if (p.device.split(":")[0] === "disk" && used != null && used >= 0.8) return t("robotDiskFull", { n: Math.round(used * 100) });
  return t("robotDeviceBad", { d: devName(p.device), state: t(`dev_${p.state}` as Key) });
}

/** ``readOnly``(W60):经理只看 —— 没有添加、批准加入、改名、改派单方式、开通码、解绑、确认换 WiFi。 */
/** 第 9 轮 W9-06:正在跑的任务说成人话:「一直巡逻（一楼夜巡）」「巡逻（一楼夜巡）」「回待命点」……;
 *  老站点没给说法的写「一个任务」。 */
export function taskWhat(w: { kind: string; route: string; forever: boolean } | null | undefined): string {
  if (!w) return t("twTask");
  const k = w.kind === "patrol" ? (w.forever ? "twForever" : "twPatrol")
    : w.kind === "goto" ? "twGoto" : w.kind === "standby" ? "twStandby" : w.kind === "home" ? "twHome" : "twTask";
  return w.route ? t("twRoute", { what: t(k), route: w.route }) : t(k);
}

export function RobotsPage({ say, now, units = [], readOnly = false, role = "admin", robot = null }: {
  say: Say; now: number; units?: UnitInfo[]; readOnly?: boolean; role?: string; robot?: string | null;
}) {
  const [rows, setRows] = useState<RobotCard[] | null>(null);
  // 第 2 轮 N4:解绑了、消息服务还没重启的编号(常驻提示)
  const [openRevoked, setOpenRevoked] = useState<string[]>([]);
  // P2-08:从总览点「详情」带着 ?robot= 进来,直接打开那一台
  const [open, setOpen] = useState<string | null>(robot);
  const [adding, setAdding] = useState(false);
  const [code, setCode] = useState<{ id: string; code: string; hours: number } | null>(null);
  const [pending, setPending] = useState<BindReq[]>([]);
  const [approving, setApproving] = useState<BindReq | null>(null);
  const [rejecting, setRejecting] = useState<BindReq | null>(null);
  void now;
  const loadPending = useCallback(() => {
    // 没开绑定的站点(没接站点目录)回 404:当没有
    api<{ requests: BindReq[] }>("GET", "/api/admin/bind").then((d) => setPending(d.requests ?? [])).catch(() => setPending([]));
  }, []);
  const load = useCallback(() => {
    api<{ robots: RobotCard[]; open_revoked?: string[] }>("GET", "/api/robots/overview")
      .then((d) => {
        setOpenRevoked(d.open_revoked ?? []);
        const list = (d.robots ?? []).filter((r) => !r.revoked);
        setRows(list);
        robotNames.value = { ...robotNames.value, ...Object.fromEntries(list.filter((r) => r.name).map((r) => [r.robot_id, r.name])) };
      })
      .catch((e) => say(errText(e)));
  }, []);
  useEffect(load, [load]);
  useEffect(() => {
    loadPending();
    const h = window.setInterval(() => { load(); loadPending(); }, REFRESH_MS);
    return () => window.clearInterval(h);
  }, [load, loadPending]);
  const cur = rows?.find((r) => r.robot_id === open) ?? null;
  return (
    <div class="robots">
      <div class="panel-head">
        <h1>{t("robots")}</h1>
        {!readOnly && <button type="button" class="btn primary push" onClick={() => setAdding(true)}>{t("addRobot")}</button>}
      </div>
      {/* P1-30:经理只看,说明不提改名、解绑 */}
      <p class="muted lead">{t(readOnly ? "robotsLeadView" : "robotsLead")}</p>
      {!readOnly && openRevoked.length > 0 && (
        <p class="warn" role="status" data-open-revoked="1">{t("robotsOpenRevoked", { ids: openRevoked.join(", ") })}</p>
      )}
      {!readOnly && pending.length > 0 && (
        <section class="panel bind-pending" aria-label={t("bindPending")}>
          <h2>{t("bindPending")}</h2>
          <p class="muted small">{t("bindPendingHint")}</p>
          <ul class="plain">
            {pending.map((p) => (
              <li key={p.id} class="bind-req row wrap" data-serial={p.serial}>
                <span class="mono">{p.serial}</span>
                <span>{t("bindCheck")} <strong class="mono check-digits">{p.check}</strong></span>
                <span class="muted small">{t("bindFrom", { t: hm(p.created_ms), src: p.source })}</span>
                <span class="push row">
                  <button type="button" class="btn sm primary" onClick={() => setApproving(p)}>{t("bindApprove")}</button>
                  <button type="button" class="btn sm" onClick={() => setRejecting(p)}>{t("bindReject")}</button>
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}
      {rows && rows.length === 0 && <p class="empty">{t("robotsNone")}</p>}
      {/* 第 4 轮 layout r3-N3:读不到时不是一片空 */}
      {rows == null && siteDown.value && <p class="note warn" role="status" data-load-failed="1">{t("loadRetry")}</p>}
      <div class={cur ? "robots-split" : undefined}>
        <div class="robot-cards">
          {(rows ?? []).map((r) => {
            const u = units.find((x) => x.robot.robot_id === r.robot_id);
            const loc = locText(u);
            const warn = r.problems.length > 0 || !!r.wifi?.change;
            return (
              <button key={r.robot_id} type="button" data-robot={r.robot_id}
                class={["robot-card", r.robot_id === open ? "on" : "", warn ? "warn" : ""].filter(Boolean).join(" ")}
                onClick={() => setOpen(r.robot_id === open ? null : r.robot_id)}>
                {/* 第 4 轮 admin N1:起了名字的,名字 + 编号一行(编号不折),状态放第二行 */}
                <span class={r.name ? "fleet-head named" : "fleet-head"}>
                  <span class="robot-name" title={label(r)}>{label(r)}</span>
                  {r.name && <small class="muted mono fleet-id">{r.robot_id}</small>}
                  <span class="fleet-state">
                    {/* P1-23:刚登记、还没连上过的不是故障:灰的「等它连上」,不是红的「离线」 */}
                    {!r.online && r.ever_seen === false ? <span class="state" title={t("fleetNeverSeen")}>{t("fleetNeverSeenShort")}</span>
                      : !r.online ? <span class="state tone-error">{t("st_offline")}</span>
                      : warn ? <span class="state tone-warning"><Shape kind="P2" />{t("fleetAttention")}</span>
                      : <span class="state tone-success">{t("online")}</span>}
                  </span>
                </span>
                {u && r.online && <span class="fleet-doing"><StateText s={u.state} stale={u.stale} />{u.task && <span class="muted">{u.task}</span>}</span>}
                <span class="fleet-batt">
                  <span class="muted">{t("fleetBattery")}</span>
                  <span class="mono fleet-pct">{r.battery_pct == null ? "—" : `${r.battery_pct}%`}</span>
                  <span class="fleet-bar" aria-hidden="true"><i style={{ width: `${Math.max(0, Math.min(100, r.battery_pct ?? 0))}%` }} /></span>
                </span>
                {r.problems.length > 0 && (
                  <span class="fleet-warn"><Shape kind="P2" />{problemText(r.problems[0], r)}{r.problems.length > 1 ? ` · ${t("robotProblems", { n: r.problems.length })}` : ""}</span>
                )}
                {r.wifi?.change && <span class="fleet-warn"><Shape kind="P2" />{t("wifiPending")}</span>}
                <span class="fleet-facts">
                  <span><small>{t("fleetLoc")}</small>{loc ? t(loc) : "—"}</span>
                  <span><small>{t("fleetNet")}</small>{r.wifi ? t(`link_${r.wifi.link}` as Key) : "—"}</span>
                  <span><small>{t("fleetToday")}</small>{patrolsN(r.patrols_today)}</span>
                </span>
              </button>
            );
          })}
        </div>
        {cur && <RobotDetail readOnly={readOnly} r={cur} u={units.find((x) => x.robot.robot_id === cur.robot_id)} now={now} role={role}
          say={say} onChanged={load} onCode={setCode} onClose={() => setOpen(null)} />}
      </div>
      {adding && (
        <AddRobot onClose={() => setAdding(false)} say={say}
          onDone={(id, c, h) => { setAdding(false); setCode({ id, code: c, hours: h }); load(); }} />
      )}
      {code && <CodeDialog {...code} onClose={() => setCode(null)} say={say} />}
      {approving && (
        <BindApprove req={approving} onClose={() => setApproving(null)}
          onDone={() => { say(t("bindApproved", { id: approving.serial })); setApproving(null); loadPending(); load(); }} />
      )}
      {rejecting && (
        <Confirm text={t("bindRejectConfirm", { id: rejecting.serial })} yes={t("bindReject")} danger onNo={() => setRejecting(null)}
          onYes={() => {
            const r = rejecting;
            setRejecting(null);
            api("POST", `/api/admin/bind/${enc(r.id)}/reject`, {})
              .then(() => say(t("bindRejected", { id: r.serial })))
              .catch((e) => say(errText(e)))
              .finally(loadPending);
          }} />
      )}
    </div>
  );
}

type RecentProblem = { key: string; kind: string; level?: string; title?: string; first_ms: number; resolved_ms: number | null; resolved_by?: string };

/** 今天的只写钟点,别的天写月-日 钟点。 */
function when(ms: number, now: number = Date.now()): string {
  const d = new Date(ms);
  const same = day(ms) === day(now);
  return same ? hm(ms) : `${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")} ${hm(ms)}`;
}

/** W72(用户 11-03):详情里的告警分三组放在最下面 —— 要处理(没解决的 P1)、待跟进(没解决的其余,不急)、
 * 记录(已解决的,收起来;自动恢复的标出来)。老站点没报级别的算要处理(宁可多看)。 */
function RecentAlerts({ items }: { items: RecentProblem[] }) {
  const open = items.filter((p) => p.resolved_ms == null);
  const act = open.filter((p) => !p.level || p.level === "P1");
  const later = open.filter((p) => p.level && p.level !== "P1");
  const log = items.filter((p) => p.resolved_ms != null);
  const row = (p: RecentProblem, tag?: { text: string; tone: string }) => {
    const name = alertTitle(lang.value, p.kind, p.title || p.kind);
    // 站点写的具体标题(「断联 20 秒后恢复」)是中文的:中文界面下跟在类型名后面
    // (第 10 轮 W9-10:先换成全角再比,只差标点的不再写一遍半角的原话)
    const raw = p.title ? zhPunct(p.title) : "";
    const more = lang.value === "zh" && raw && raw !== name ? raw : "";
    return (
    <li key={p.key}>
      <time class="mono">{when(p.first_ms)}</time>
      <span class="rd-what">{name}{more && <small>{more}</small>}</span>
      {tag ? <span class={`rd-tag ${tag.tone}`}>{tag.text}</span> : <span />}
    </li>
    );
  };
  const head = (key: Key, n: number) => <h4><span>{t(key)}</span><span class="rd-count">{n}</span></h4>;
  return (
    <section class="robot-alerts rd-sec">
      <h3 class="rd-h">{t("robotRecent")}</h3>
      {items.length === 0 && <p class="muted small">{t("robotRecentNone")}</p>}
      {act.length > 0 && (
        <div class="rd-group act" data-group="act">{head("robotAct", act.length)}
          <ul class="rd-list">{act.map((p) => row(p, { text: t("robotOpen"), tone: "open" }))}</ul></div>
      )}
      {later.length > 0 && (
        <div class="rd-group later" data-group="later">{head("robotLater", later.length)}
          <ul class="rd-list">{later.map((p) => row(p))}</ul></div>
      )}
      {log.length > 0 && (
        <details class="rd-group rd-log" data-group="log">
          <summary>{t("robotLog", { n: log.length })}</summary>
          <ul class="rd-list">{log.map((p) => row(p, autoResolved(p) ? { text: t(p.resolved_by === "site:skipped" ? "vSkipped" : "vAuto"), tone: "auto" } : { text: t("vDone"), tone: "done" }))}</ul>
        </details>
      )}
    </section>
  );
}

/** 多久前(最后联系):一分钟内按秒,一小时内按分钟,再久写钟点。 */
function ago(ms: number, now: number): string {
  const s = Math.max(0, Math.round((now - ms) / 1000));
  if (s < 5) return t("rdJustNow");
  if (s < 60) return t("rdSecAgo", { n: s });
  if (s < 3600) return t("rdMinAgo", { n: Math.floor(s / 60) });
  return when(ms, now);
}

type Act = (fn: () => Promise<unknown>, msg?: string) => Promise<void>;

/** W72(用户 11-03):手机上有的操作网页也要 —— 选路线开始巡逻、回待命点、停止当前任务、自动定位、叫停后恢复。
 * 权限跟手机一样:派巡逻、停止 = 能派单的 + 经理;回待命点、自动定位、恢复 = 能派单的(经理不能让它再动)。 */
function Controls({ r, u, role, say, onChanged }: { r: RobotCard; u?: UnitInfo; role: string; say: Say; onChanged: () => void }) {
  const [routes, setRoutes] = useState<string[] | null>(null);
  const [pick, setPick] = useState("");
  const [loops, setLoops] = useState(1);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [ask, setAsk] = useState<Posture | null>(null);
  const [askHome, setAskHome] = useState(false);
  const [drawn, setDrawn] = useState<Record<string, { id: string; v: string; title?: string }>>({});
  const patrol = canPatrol(role);
  const dispatch = canDispatch(role);
  useEffect(() => {
    if (!patrol) return;
    api<{ missions?: string[] }>("GET", "/api/schedule")
      .then((d) => { const m = d.missions ?? []; setRoutes(m); setPick(m.length === 1 ? m[0] : ""); })
      .catch(() => setRoutes([]));
    // 第 8 轮 W8-02:路线画在哪一版(跟 App 一样,别的版本上的灰掉);读不到就不灰(站点照样会拒)
    api<{ routes?: { id: string; map_id?: string; map_version?: string; title?: string }[] }>("GET", "/api/routes")
      .then((d) => setDrawn(Object.fromEntries((d.routes ?? []).map((x) => [x.id, { id: x.map_id ?? "", v: x.map_version ?? "", title: x.title }]))))
      .catch(() => setDrawn({}));
  }, [r.robot_id, patrol]);
  /** 这条路线画在别的图 / 版本上:回「画在哪一版」;对得上、不知道回 null。 */
  const otherMap = (m: string): string | null => {
    const d = drawn[m];
    if (!d || !d.v || !r.map?.version) return null;
    if (d.id && r.map.id && d.id !== r.map.id) return `${d.id} v${d.v}`;
    return d.v === r.map.version ? null : `v${d.v}`;
  };
  useEffect(() => setErr(null), [r.robot_id]);
  const id = r.name || r.robot_id;
  // UIUX-022:派不了的路线(画在别的地图版本上):不当默认选中,「派巡逻」也不能点
  const cantRoutes = (routes ?? []).map((m) => [m, otherMap(m)] as const).filter((x): x is readonly [string, string] => x[1] !== null);
  const pickOk = !!pick && otherMap(pick) === null;
  const send = async (fn: () => Promise<(CommandReply & { queued?: boolean; start_after_ms?: number; because?: string; utc_offset_min?: number }) | null>,
    ok: string) => {
    setBusy(true);
    setErr(null);
    try {
      const res = await fn();
      if (res === null) return;
      if (res.queued) say(t("trQueued", { id, at: siteHm(res.start_after_ms ?? 0, res.utc_offset_min), why: res.because ?? "" }));
      else {
        const no = res.ack ? notAccepted(res) : null;
        if (no) setErr(t("rdNotAccepted", { why: no }));
        else say(ok);
      }
    } catch (e) {
      setErr(e instanceof ApiError ? refusalText(e.message, e.data) : String(e));
    } finally {
      setBusy(false);
      onChanged();
    }
  };
  const path = (a: string) => `/api/robots/${enc(r.robot_id)}/${a}`;
  const abort = () => send(async () => {
    const v = await api<{ status?: { task?: { task_id?: string } | null } | null }>("GET", `/api/robots/${enc(r.robot_id)}`);
    const tid = v.status?.task?.task_id;
    if (!tid) { say(t("rdNoTask", { id })); return null; }
    const res = await api<CommandReply>("POST", path("abort"), { task_id: tid });
    // 第 9 轮 W9-06:机器人收到叫停到真的停下要一两秒 —— 过一会儿再刷两次,不让页面一直写「一直巡逻 · 第 2 圈」
    for (const ms of [1500, 4000]) setTimeout(onChanged, ms);
    return res;
  }, t("rdSent", { id, what: t("rdAbort") }));
  const off = !r.online;
  // P1-27:点了也做不成的先灰掉、把原因写在按钮下面(不是点了才报红字)
  const findable = u ? canFindPose(u.robot) : true;
  const why = off ? null : r.task ? t("rdHomeBusy") : !findable ? t("rdNoAutoLoc") : null;
  // P1-28:当前姿态(状态里的 ready.motion:站着能走 = true;老站点、没报 = 不写)
  const motion = u?.robot.status?.ready?.motion;
  // 第 2 轮 N2:没原点、没默认待命点的先灰掉,写原因、给去处理的链接(不是点了才报红字)
  const noHome = r.home_set === false;
  const noStandby = r.standby_set === false;
  // UIUX-008:灰着的按钮悬停说为什么(按先后挑第一条成立的)
  const whyOff = (...xs: [boolean, string][]): string | undefined => xs.find((x) => x[0])?.[1];
  const offWhy = t(r.ever_seen === false ? "rdNeverNoCtl" : "rdOfflineNoCtl");
  return (
    <section class="rd-sec rd-control">
      <h3 class="rd-h">{t("rdControl")}</h3>
      {r.held && (
        <div class="note warn rd-held">
          <span>{t("rdHeld", { by: r.held.by, t: when(r.held.at_ms) })}</span>
          {dispatch && <button type="button" class="btn sm" disabled={busy} title={whyOff([busy, t("rdWhySending")])}
            onClick={() => void send(() => api("POST", path("resume"), {}), t("rdSent", { id, what: t("rdResume") }))}>{t("rdResume")}</button>}
        </div>
      )}
      {off && <p class="muted small">{t(r.ever_seen === false ? "rdNeverNoCtl" : "rdOfflineNoCtl")}</p>}
      {patrol && (
        <div class="rd-name">
          <label class="rd-label" for={`rd-route-${r.robot_id}`}>{t("rdRoute")}</label>
          {routes !== null && routes.length === 0 ? <p class="muted small">{t(isOwnerLike(role) ? "rdNoRoutes" : "rdNoRoutesAsk")}</p> : (
            <div class="rd-inline">
              <select id={`rd-route-${r.robot_id}`} name="route" value={pickOk ? pick : ""} onChange={(e) => setPick(e.currentTarget.value)}>
                <option value="">{t("rdPickRoute")}</option>
                {(routes ?? []).map((m) => (
                  // UIUX-022:选项只写路线名(原生下拉放不下整句、也没有省略号);派不了的灰掉,原因写在下拉下面
                  <option key={m} value={m} disabled={otherMap(m) !== null}>{drawn[m]?.title || m}</option>
                ))}
              </select>
              <LoopsSelect value={loops} onChange={setLoops} />
              <button type="button" class="btn sm primary" disabled={busy || off || !pickOk}
                title={whyOff([busy, t("rdWhySending")], [off, offWhy], [!!pick && !pickOk, t("rdRouteOtherMap", { at: otherMap(pick) ?? "", id, v: `v${r.map?.version ?? ""}` })], [!pickOk, t("rdWhyPickRoute")])}
                onClick={() => void send(() => api("POST", path("patrol"), { mission_id: pick, loops }),
                  t("rdPatrolSent", { id, route: drawn[pick]?.title || pick }))}>
                {t("rdStartPatrol")}
              </button>
            </div>
          )}
          {cantRoutes.length > 0 && (
            <ul class="plain small warn" data-route-why="1">
              {cantRoutes.map(([m, o]) => <li key={m}>{drawn[m]?.title || m} {t("rdRouteOtherMap", { at: o, id, v: `v${r.map?.version ?? ""}` })}</li>)}
            </ul>
          )}
        </div>
      )}
      {dispatch && !off && (noHome || noStandby) && (
        <ul class="plain rd-why small muted">
          {noHome && <li>{t("rdNoHome")} {isOwnerLike(role) && <a href="#/admin/localization">{t("rdNoHomeGo")}</a>}</li>}
          {noStandby && <li>{t("rdNoStandby")} {isOwnerLike(role) && <a href="#/admin/layout?tab=standby">{t("rdNoStandbyGo")}</a>}</li>}
        </ul>
      )}
      <div class="rd-actions">
        {dispatch && <button type="button" class="btn sm" disabled={busy || off || noStandby}
          title={whyOff([busy, t("rdWhySending")], [off, offWhy], [noStandby, t("rdNoStandby")])}
          onClick={() => void send(() => api("POST", path("standby/return"), {}), t("rdSent", { id, what: t("rdReturn") }))}>{t("rdReturn")}</button>}
        {dispatch && <button type="button" class="btn sm" disabled={busy || off || !!r.task || noHome}
          title={whyOff([busy, t("rdWhySending")], [off, offWhy], [!!r.task, t("rdHomeBusy")], [noHome, t("rdNoHome")])}
          onClick={() => void send(() => api("POST", path("home/return"), {}), t("rdSent", { id, what: t("rdHome") }))}>{t("rdHome")}</button>}
        {dispatch && r.task && <button type="button" class="btn sm rd-danger" disabled={busy || off}
          title={whyOff([busy, t("rdWhySending")], [off, offWhy])}
          onClick={() => setAskHome(true)}>{t("rdAbortHome")}</button>}
        {dispatch && <button type="button" class="btn sm" disabled={busy || off || !findable}
          title={whyOff([busy, t("rdWhySending")], [off, offWhy], [!findable, t("rdNoAutoLoc")])}
          onClick={() => void send(() => api("POST", path("relocalize"), { global: true }), t("rdSent", { id, what: t("rdAutoLoc") }))}>{t("rdAutoLoc")}</button>}
        {/* P1-28:站点说了它空闲(task 是 null)就灰掉;没带这一项的老站点照旧能点(点了现问) */}
        {patrol && <button type="button" class="btn sm rd-danger" disabled={busy || r.task === null}
          title={whyOff([busy, t("rdWhySending")], [r.task === null, t("rdIdle")])} onClick={() => void abort()}>{t("rdAbort")}</button>}
      </div>
      {dispatch && why && <p class="muted small rd-why">{why}</p>}
      {err && <p class="error small" role="alert">{err}</p>}
      {canTeleop(role) && (r.postures ?? []).length > 0 && (
        <div class="rd-name rd-posture">
          <span class="rd-label">{t("rdPosture")}{motion !== undefined && r.online && <span class="muted small" data-posture-now="1"> · {motion ? t("rdNowStanding") : t("rdNowDown")}</span>}</span>
          <div class="rd-actions">
            {(r.postures ?? []).map((m) => (
              <button key={m} type="button" class="btn sm" disabled={busy || off || !!r.task || !!r.held}
                title={whyOff([busy, t("rdWhySending")], [off, offWhy], [!!r.task, t("rdPostureBusy", { id, what: taskWhat(r.task_what) })], [!!r.held, t("rdPostureHeld")])}
                onClick={() => setAsk(m)}>{t(POSTURE_KEY[m])}</button>
            ))}
          </div>
          {r.task && <p class="muted small">{t("rdPostureBusy", { id, what: taskWhat(r.task_what) })}</p>}
          {!r.task && r.held && <p class="muted small">{t("rdPostureHeld")}</p>}
        </div>
      )}
      {askHome && (
        <Confirm text={t("rdAbortHomeAsk", { id, what: taskWhat(r.task_what) })} yes={t("rdAbortHome")} danger
          onNo={() => setAskHome(false)}
          onYes={() => {
            setAskHome(false);
            void send(() => api("POST", path("home/return"), { abort: true }), t("rdSent", { id, what: t("rdAbortHome") }));
          }} />
      )}
      {ask && (
        <Confirm text={t("rdPostureAsk", { id, what: t(POSTURE_KEY[ask]) })} yes={t(POSTURE_KEY[ask])}
          onNo={() => setAsk(null)}
          onYes={() => {
            const m = ask;
            setAsk(null);
            void send(() => api("POST", path("posture"), { mode: m }), t("rdPostureDone", { id, what: t(POSTURE_KEY[m]) }));
          }} />
      )}
    </section>
  );
}

function RobotDetail({ r, u, now, role, say, onChanged, onCode, onClose, readOnly = false }: {
  readOnly?: boolean; u?: UnitInfo; now: number; role: string;
  r: RobotCard; say: Say; onChanged: () => void; onCode: (c: { id: string; code: string; hours: number }) => void; onClose: () => void;
}) {
  const [name, setName] = useState(r.name);
  const [unbind, setUnbind] = useState<"ask" | "pw" | null>(null);
  const [ask, setAsk] = useState<{ text: string; yes: string; go: () => void } | null>(null);
  useEffect(() => setName(r.name), [r.robot_id, r.name]);
  const act: Act = async (fn, msg) => {
    try {
      await fn();
      if (msg) say(msg);
    } catch (e) {
      say(errText(e));
    }
    onChanged();
  };
  const compat: Key = r.compat === "ok" ? "compat_ok" : (`compat_${r.compat}` as Key);
  const devices = r.problems.filter((p) => "device" in p);
  const loc = locText(u);
  const fact = (k: Key, v: string, mono = false) => <div><dt>{t(k)}</dt><dd class={mono ? "mono" : undefined}>{v}</dd></div>;
  // 第 3 轮 admin N5:换一台时回到顶上(原来留着上一台的滚动位置,从中间开始看,以为还在看上一台)
  const aside = useRef<HTMLElement>(null);
  useEffect(() => {
    const el = aside.current;
    if (!el) return;
    el.scrollTop = 0;
    const top = el.getBoundingClientRect().top;
    if (top < 0 && typeof window !== "undefined") window.scrollBy?.(0, top - 8);
  }, [r.robot_id]);
  return (
    <aside class="panel robot-detail" aria-label={label(r)} ref={aside}>
      <div class="panel-head">
        <h2>{label(r)}</h2>
        {r.name && <small class="muted mono">{r.robot_id}</small>}
        {/* 第 2 轮 P1-23:刚登记、还没连上过的,详情顶上跟卡片一样写「还没连上」,不是红色离线 */}
        {r.online ? <span class="state tone-success">{t("online")}</span>
          : r.ever_seen === false ? <span class="state">{t("fleetNeverSeen")}</span>
          : <span class="state tone-error">{t("st_offline")}</span>}
        <button type="button" class="btn sm push" onClick={onClose}>{t("close")}</button>
      </div>
      <section class="rd-sec">
        <h3 class="rd-h">{t("rdNow")}</h3>
        <dl class="rd-facts">
          <div><dt>{t("rdState")}</dt><dd>{u && r.online ? <><StateText s={u.state} stale={u.stale} />{u.task && <small class="muted"> {u.task}</small>}</>
            : r.online ? t("online") : r.ever_seen === false ? t("fleetNeverSeen") : t("st_offline")}
            {/* 第 10 轮 W10-03:实时状态那一小段已经写了第几圈的,这里不再写一遍 */}
            {r.online && r.lap && !(u && u.task) && <small class="muted" data-lap="1"> · {lapText(r.lap)}</small>}</dd></div>
          {fact("fleetBattery", r.battery_pct == null ? "—" : `${r.battery_pct}%`, true)}
          {fact("fleetLoc", `${loc ? t(loc) : "—"}${u?.robot.loc?.localizer ? ` · ${u.robot.loc.localizer}` : ""}`)}
          {fact("wifiLabel", r.wifi ? `${r.wifi.ssid || "—"} · ${t(`link_${r.wifi.link}` as Key)}` : "—")}
          {fact("rdLastSeen", r.last_seen_ms ? ago(r.last_seen_ms, now) : "—")}
          {/* 第 11 轮 W11-02:不知道待传几个(站点从盘那一行读出的用量)只写用了多少 */}
          {r.storage && fact("rdStorage", r.storage.backlog_files == null ? t("rdStorageUsed", { p: Math.round(r.storage.used_ratio * 100) })
            : t("rdStorageVal", { p: Math.round(r.storage.used_ratio * 100), n: r.storage.backlog_files }))}
        </dl>
        {devices.length > 0 && <p class="note small">{devices.map((p) => problemText(p, r)).join(" · ")}</p>}
      </section>
      {(canPatrol(role) || isOwnerLike(role)) && !r.revoked && <Controls r={r} u={u} role={role} say={say} onChanged={onChanged} />}
      <section class="rd-sec">
        <h3 class="rd-h">{t("rdPatrol")}</h3>
        <dl class="rd-facts">
          {fact("rdToday", patrolsN(r.patrols_today))}
          {r.patrols_7d != null && fact("rd7d", patrolsN(r.patrols_7d))}
          {r.aborts_7d != null && fact("rdAborts", t("rdAbortsN", { n: r.aborts_7d }))}
          {r.last_patrol_ms != null && fact("rdLastPatrol", when(r.last_patrol_ms, now), true)}
        </dl>
      </section>
      {(r.devices?.length ?? 0) > 0 && (
        <section class="rd-sec">
          <h3 class="rd-h">{t("rdDevices")}</h3>
          <ul class="rd-devs">
            {r.devices!.map((x) => (
              <li key={x.id} class={`dev-${x.state}`} title={x.detail ? siteStr(x.detail) : undefined}><span>{devName(x.id)}</span><span>{t(`dev_${x.state}` as Key)}</span></li>
            ))}
          </ul>
        </section>
      )}
      <section class="rd-sec">
        <h3 class="rd-h">{t("rdBasics")}</h3>
        <dl class="rd-facts">
          {fact("robotId", r.robot_id, true)}
          {fact("colVersion", `${r.agent ?? "—"} · ${t(compat)}`)}
          {r.map && <div><dt>{t("rdMap")}</dt><dd><span class="mono">{r.map.id} v{r.map.version ?? "?"}</span>
            {r.map.match === false && <small class="rd-bad"> {t("rdMapBad")}</small>}
            {r.map.match === true && <small class="muted"> {t("rdMapOk")}</small>}</dd></div>}
          {fact("certExpires", r.expires_at ? day(r.expires_at) : "—", true)}
          {r.enrolled_at != null && fact("rdEnrolled", day(r.enrolled_at), true)}
          <div><dt>{t("dispatchMode")}</dt><dd>{r.manual_only ? t("manualOnly") : t("autoDispatch")}
            {r.manual_only && r.manual_note && <small class="muted"> · {siteKnown(r.manual_note)}</small>}</dd></div>
        </dl>
      </section>
      {!readOnly && r.wifi?.change && <section class="rd-sec"><WifiChange id={r.robot_id} ch={r.wifi.change} act={act} /></section>}
      {!readOnly && (
        <section class="rd-sec">
          <h3 class="rd-h">{t("rdManage")}</h3>
          <form class="rd-name" onSubmit={(e) => { e.preventDefault(); void act(() => api("POST", `/api/admin/robots/${enc(r.robot_id)}/name`, { name: name.trim() }),
            name.trim() ? t("saved") : t("robotNameCleared", { id: r.robot_id })); }}>
            <label class="rd-label" for={`rd-name-${r.robot_id}`}>{t("robotName")}</label>
            <div class="rd-inline">
              <input id={`rd-name-${r.robot_id}`} name="name" value={name} maxLength={32} placeholder={r.robot_id}
                onInput={(e) => setName(e.currentTarget.value)} />
              <button type="submit" class="btn sm" disabled={name === r.name} title={name === r.name ? t("rdWhyNameSame") : undefined}>{t("robotNameSave")}</button>
            </div>
            {/* P2-12:写明最多几个字(原来超了悄悄截掉) */}
            <small class={name.length >= 32 ? "warn-text" : "muted"} data-name-count="1">{t("robotNameCount", { n: name.length, max: 32 })}</small>
          </form>
          <div class="rd-actions">
            {/* P1-26 / P1-05:切派遣方式、重出开通码都先确认,说清是什么意思 */}
            <button type="button" class="btn sm" onClick={() => setAsk({
              text: t(r.manual_only ? "setAutoAsk" : "setManualAsk", { id: label(r) }), yes: r.manual_only ? t("setAuto") : t("setManual"),
              go: () => void act(() => api("POST", `/api/robots/${enc(r.robot_id)}/service`, { manual_only: !r.manual_only }),
                t(r.manual_only ? "setAutoDone" : "setManualDone", { id: label(r) })) })}>
              {r.manual_only ? t("setAuto") : t("setManual")}
            </button>
            <button type="button" class="btn sm" onClick={() => setAsk({ text: t("newCodeAsk", { id: label(r) }), yes: t("newCode"),
              go: () => void act(async () => {
                const d = await api<{ code: string; hours: number }>("POST", `/api/admin/robots/${enc(r.robot_id)}/code`, {});
                onCode({ id: r.robot_id, code: d.code, hours: d.hours });
              }) })}>{t("newCode")}</button>
            <button type="button" class="btn sm rd-danger" onClick={() => setUnbind("ask")}>{t("robotUnbind")}</button>
          </div>
        </section>
      )}
      {ask && <Confirm text={ask.text} yes={ask.yes} onNo={() => setAsk(null)} onYes={() => { const g = ask.go; setAsk(null); g(); }} />}
      {unbind === "ask" && (
        // 第 4 轮:解绑要重启消息服务器(吊销名单 broker 重启才读),所有机器人断线几秒 —— 写明会怎样
        <Confirm text={`${t(r.online ? "robotUnbindConfirm" : r.ever_seen === false ? "robotUnbindConfirmNever" : "robotUnbindConfirmOffline", { id: label(r) })} ${t("robotUnbindBroker")}`} yes={t("robotUnbind")} danger onNo={() => setUnbind(null)} onYes={() => setUnbind("pw")} />
      )}
      {unbind === "pw" && (
        <ConfirmPassword title={t("robotUnbind")} onClose={() => setUnbind(null)}
          onConfirm={async (pw) => {
            const d = await api<{ robot_wipe?: string; old_connection_open?: boolean }>("POST", `/api/admin/robots/${enc(r.robot_id)}/revoke`, { confirm_password: pw });
            setUnbind(null);
            // 网页易用性第 1 轮 P0-10:如实说 —— 老版本不认远程清除;消息服务器没重启时旧连接还开着
            // 第 3 轮 P0-10:从没连上过的不说「下次连上时删数据」(跟确认框说法相反)
            const wipe = d.robot_wipe === "sent" ? "robotUnbound" : d.robot_wipe === "unsupported" ? "robotUnboundNoWipe" : r.ever_seen === false ? "robotUnboundNever" : "robotUnboundOffline";
            say([t(wipe, { id: label(r) }), d.old_connection_open ? t("robotUnboundOpen") : ""].filter(Boolean).join(" "));
            onClose();
            onChanged();
          }} />
      )}
      <RecentAlerts items={r.recent_problems} />
    </aside>
  );
}

/** 机器人编号(站点 ca.SAFE_ID)。 */
const ROBOT_ID = /^[A-Za-z0-9._-]{1,64}$/;

function AddRobot({ onClose, onDone }: { onClose: () => void; onDone: (id: string, code: string, hours: number) => void; say?: Say }) {
  const [id, setId] = useState("");
  const [days, setDays] = useState(365);
  const [busy, setBusy] = useState(false);
  const [manual, setManual] = useState(false);
  // 第 4 轮 admin N2:错误写在框里(toast 在弹窗遮罩下面看不清)
  const [err, setErr] = useState("");
  // P1-25:格式在框下面写明、自己查(不靠浏览器原生提示);重复编号说「已存在,先解绑」
  const idBad = id !== "" && !ROBOT_ID.test(id);
  async function submit(e: Event) {
    e.preventDefault();
    if (!ROBOT_ID.test(id)) return;
    setBusy(true);
    try {
      const d = await api<{ code: string; hours: number }>("POST", "/api/admin/robots", { robot_id: id, days });
      onDone(id, d.code, d.hours);
    } catch (x) {
      if (x instanceof ApiError && x.status === 409 && String((x.data as { error?: string } | undefined)?.error ?? x.message).includes("旧连接")) setErr(t("robotIdOldConn", { id }));
      else if (x instanceof ApiError && x.status === 409) setErr(t("robotIdTaken", { id }));
      else setErr(errText(x));
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal label={t("addRobot")} onClose={onClose}>
      <p>{t("addRobotScan")}</p>
      {!manual && (
        <div class="row end">
          <button type="button" class="btn sm" onClick={() => setManual(true)}>{t("addRobotManual")}</button>
          <button type="button" class="btn primary" onClick={onClose}>{t("close")}</button>
        </div>
      )}
      {manual && <form class="form" onSubmit={submit}>
        <p class="muted small">{t("addRobotHint")}</p>
        <label class="field">{t("robotId")}<input value={id} required autocomplete="off" aria-describedby="robot-id-rule" aria-invalid={err ? true : undefined} onInput={(e) => { setId(e.currentTarget.value); setErr(""); }} />
          <span id="robot-id-rule" class={idBad ? "error small" : "muted small"}>{t("robotIdRule")}</span></label>
        <details class="small"><summary>{t("addRobotCmdTitle")}</summary><p class="mono">{t("addRobotCmd")}</p></details>
        <label class="field">{t("certDays")}<input type="number" min={1} max={3650} value={days} onInput={(e) => setDays(Number(e.currentTarget.value))} /></label>
        {err && <p class="error small" role="alert" data-form-error="1">{err}</p>}
        <div class="row end">
          <button type="button" class="btn" onClick={onClose}>{t("cancel")}</button>
          <button type="submit" class="btn primary" disabled={busy}>{t("addRobot")}</button>
        </div>
      </form>}
    </Modal>
  );
}

function CodeDialog({ id, code, hours, onClose, say }: { id: string; code: string; hours: number; onClose: () => void; say: Say }) {
  // P1-24:复制要有反馈;http 下没有剪贴板接口,退回选中 + execCommand
  const box = useRef<HTMLTextAreaElement>(null);
  const [copied, setCopied] = useState(false);
  async function copy() {
    try {
      if (navigator.clipboard) await navigator.clipboard.writeText(code);
      else { box.current?.select(); document.execCommand("copy"); }
      setCopied(true);
    } catch {
      box.current?.select();
      say(t("copyManual"));
    }
  }
  return (
    <Modal label={t("activationCode", { id })} onClose={onClose}>
      <p class="muted small">{t("codeHint", { h: hours })}</p>
      {/* 第 2 轮 P1-24:多行框,码全看得见(原来单行要横着滚) */}
      <textarea class="codebox mono" readOnly rows={4} value={code} ref={box} onFocus={(e) => e.currentTarget.select()} aria-label={t("activationCode", { id })} />
      {/* 第 2 轮 admin N15:「已复制」只在按钮上显示(原来框里一行 + toast 两处,框还往上跳) */}
      <div class="row end">
        <button type="button" class="btn" onClick={() => void copy()}>{copied ? `✓ ${t("copied")}` : t("copy")}</button>
        <button type="button" class="btn primary" onClick={onClose}>{t("close")}</button>
      </div>
    </Modal>
  );
}

function WifiChange({ id, ch, act }: {
  id: string; ch: NonNullable<Wifi["change"]>; act: (fn: () => Promise<unknown>, msg?: string) => Promise<void>;
}) {
  const send = (approve: boolean) => void act(() => api("POST", `/api/robots/${enc(id)}/wifi`, { id: ch.id, approve }),
    t(approve ? "wifiApproved" : "wifiRejected"));
  return (
    <div class="wifi-change" role="status">
      <p>{t(ch.mode === "trial" ? "wifiChangeTrial" : "wifiChangeAsk", { ssid: ch.ssid })}</p>
      <div class="row">
        <button type="button" class="btn sm primary" onClick={() => send(true)}>{t("wifiApprove")}</button>
        <button type="button" class="btn sm" onClick={() => send(false)}>{t("wifiReject")}</button>
      </div>
    </div>
  );
}

function BindApprove({ req, onClose, onDone }: { req: BindReq; onClose: () => void; onDone: () => void }) {
  const [name, setName] = useState("");
  const [pw, setPw] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  async function submit(e: Event) {
    e.preventDefault();
    setBusy(true);
    setErr("");
    try {
      await api("POST", `/api/admin/bind/${enc(req.id)}/approve`, { confirm_password: pw, name });
      onDone();
    } catch (x) {
      setErr(x instanceof ApiError && x.status === 403 ? t("pwWrong")
        : x instanceof ApiError && x.status === 429 ? t("pwLocked") : errText(x));
      setPw("");
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal label={t("bindApproveTitle", { id: req.serial })} onClose={onClose}>
      <form class="form bind-approve" onSubmit={submit}>
        <p>{t("bindApproveHint", { code: req.check })}</p>
        <p class="check-digits big mono" aria-label={t("bindCheck")}>{req.check}</p>
        <label class="field">{t("robotName")}<input value={name} maxLength={32} placeholder={req.serial}
          onInput={(e) => setName(e.currentTarget.value)} /></label>
        <label class="field">{t("pwAgain")}<input type="password" autoComplete="current-password" value={pw} required
          onInput={(e) => setPw(e.currentTarget.value)} /></label>
        {err && <p class="error" role="alert">{err}</p>}
        <div class="row end">
          <button type="button" class="btn" onClick={onClose}>{t("cancel")}</button>
          <button type="submit" class="btn primary" disabled={busy || !pw}>{t("bindApprove")}</button>
        </div>
      </form>
    </Modal>
  );
}

/** 第 2 轮 admin N15:「1 patrol」不写「1 patrols」。 */
function patrolsN(n: number | null | undefined): string {
  return t(n === 1 ? "fleetPatrols1" : "fleetPatrols", { n: n ?? 0 });
}

/** 第 3 轮 zh N10:机器人设备的内部编号(disk、camera:front、link:wifi、rtk)换成人话,原编号放悬停。 */
export function devName(id: string): string {
  const zh = lang.value === "zh";
  const [k, sub] = id.split(":", 2);
  if (k === "disk") return zh ? "存储盘" : "Storage";
  if (k === "rtk") return zh ? "RTK 定位" : "RTK positioning";
  if (k === "board") return zh ? "主板" : "Board";
  if (k === "lidar") return zh ? "激光雷达" : "Lidar";
  if (k === "camera") return zh ? `摄像头 ${sub === "front" ? "前" : sub === "back" ? "后" : sub}` : `Camera ${sub}`;
  if (k === "link") return zh ? `网络 ${sub}` : `Network ${sub}`;
  return id;
}
