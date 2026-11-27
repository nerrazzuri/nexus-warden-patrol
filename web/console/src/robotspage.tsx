// 现场设置 → 机器人(redesign 第六期 R-A / R-A2 / M-robot;W44 第二期机器人页换样子)。
// 左栏:机器人列表(状态、名字、电量、在做什么、毛病)+「添加」;底下是等待批准加入的申请(核对码、核对并批准 / 拒绝)。
// 右边是选中那一台:页头名字、状态牌、编号 · 定位 · 派单方式 · 最后联系;「操作 / 设置」两个视图(经理只有操作)。
// 操作 = 值班页的单台机器人控制(画面、云台、喊话、警示、当前任务、派巡逻、姿态、定位、今天)+ 健康状况。
// 设置 = 名字、派单方式;检查单(要处理的在上,正常的按 连接 / 硬件 / 地图上的设置 收起来);排查与维护(W55 远程运维);
//        右栏告警记录(W72 三组)、解绑(原地确认 + 再输密码;解绑 = 机器人恢复出厂,W42)。
// W42:「添加」= 手机扫机器人贴纸;工程师的开通码流程收进「添加」里的一个按钮。
import { siteKnown, zhPunct } from "./sitetext";
import { useCallback, useEffect, useRef, useState } from "preact/hooks";
import { api, ApiError, enc } from "./api";
import { ConfirmPassword } from "./confirmpw";
import { hm, robotNames, siteDown, mapName } from "./data";
import { Modal } from "./dialogs";
import { alertTitle, lang, t, type Key } from "./i18n";
import { autoResolved, type Alert } from "./model";
import { locText, type UnitInfo } from "./live";
import { RobotControl } from "./robotctl";
import { RobotOps } from "./remoteops";
import { Sign } from "./signs";
import type { TodayItem } from "./todaypatrols";

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
  home_set?: boolean | null; standby_set?: boolean; standby_bad?: boolean; home_bad?: boolean;
  patrols_7d?: number; aborts_7d?: number; last_patrol_ms?: number | null; last_seen_ms?: number | null; ever_seen?: boolean;
  storage?: { used_ratio: number; backlog_files: number | null; oldest_backlog_s: number | null } | null;
  map?: { id: string; version: string | null; match: boolean | null } | null;
  devices?: { id: string; state: string; detail?: string }[];
  enrolled_at?: number | null; manual_note?: string; held?: { by: string; at_ms: number } | null;
  /** POC:能换哪几种姿态、正在跑的任务(老站点没有)。 */
  postures?: Posture[]; task?: string | null;
  /** 用户 11-21:雷达视野表(没学好时遮挡限速关着)。老站点、没有避障的机器人没有。 */
  fov?: { state: "ready" | "learning" | "none"; frames?: number; need?: number } | null;
  /** POC 11-05:上装能开哪几路、有哪些话术、能不能打字(老站点没有)。 */
  deter?: Deter | null;
  /** 第 9 轮 W9-06:正在跑的任务给人看的说法(不露 adhoc-forever-… 这种编号)。 */
  task_what?: { kind: string; route: string; forever: boolean } | null;
  /** W76:正在跑几圈的巡逻 —— 第几圈、共几圈(0 = 一直巡逻)。一圈的、老站点没有。 */
  lap?: { n: number; of: number } | null;
  /** 真机 11-25:遥控松手后倒数回待命点。 */
  standby_countdown?: { after: string; due_ms: number } | null;
  /** 真机 11-25:谁点的静音。 */
  muted?: string | null;
}
export interface Deter { outputs: string[]; max_s: number; tts: boolean; clips: string[];
  /** 第三档 #41:能念哪几种语言(竞品只会中文;英文靠 Orin 上合成)。没报 = 不知道,不挡。 */
  tts_langs?: string[] }
export const STROBE_S = [30, 60, 120, 300];
export const CLIP_KEY: Record<string, "clip_blocked" | "clip_passing" | "clip_distance" | "clip_restricted"> = {
  blocked: "clip_blocked", passing: "clip_passing", distance: "clip_distance", restricted: "clip_restricted",
};
export type Posture = "stand" | "lie" | "crawl";
export const POSTURE_KEY: Record<Posture, "rdStand" | "rdLie" | "rdCrawl"> = { stand: "rdStand", lie: "rdLie", crawl: "rdCrawl" };
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

export function RobotsPage({ say, now, units = [], readOnly = false, role = "admin", robot = null, alerts = [], refresh }: {
  say: Say; now: number; units?: UnitInfo[]; readOnly?: boolean; role?: string; robot?: string | null;
  alerts?: Alert[]; refresh?: () => Promise<void>;
}) {
  const [rows, setRows] = useState<RobotCard[] | null>(null);
  // 第 2 轮 N4:解绑了、消息服务还没重启的编号(常驻提示)
  const [openRevoked, setOpenRevoked] = useState<string[]>([]);
  // P2-08:从总览点「详情」带着 ?robot= 进来,直接打开那一台;没带就开第一台
  const [open, setOpen] = useState<string | null>(robot);
  const [view, setView] = useState<"op" | "set">("op");
  const [adding, setAdding] = useState(false);
  const [code, setCode] = useState<{ id: string; code: string; hours: number } | null>(null);
  const [pending, setPending] = useState<BindReq[]>([]);
  const [approving, setApproving] = useState<BindReq | null>(null);
  const [rejecting, setRejecting] = useState<string | null>(null);
  const [patrols, setPatrols] = useState<TodayItem[]>([]);
  const loadPending = useCallback(() => {
    if (readOnly) return;
    // 没开绑定的站点(没接站点目录)回 404:当没有
    api<{ requests: BindReq[] }>("GET", "/api/admin/bind").then((d) => setPending(d.requests ?? [])).catch(() => setPending([]));
  }, [readOnly]);
  const load = useCallback(() => {
    api<{ robots: RobotCard[]; open_revoked?: string[] }>("GET", "/api/robots/overview")
      .then((d) => {
        setOpenRevoked(d.open_revoked ?? []);
        const list = (d.robots ?? []).filter((r) => !r.revoked);
        setRows(list);
        setOpen((o) => (o && list.some((r) => r.robot_id === o) ? o : list[0]?.robot_id ?? null));
        robotNames.value = { ...robotNames.value, ...Object.fromEntries(list.filter((r) => r.name).map((r) => [r.robot_id, r.name])) };
      })
      .catch((e) => say(errText(e)));
    api<{ items: TodayItem[] }>("GET", "/api/patrols/today").then((d) => setPatrols(d.items ?? [])).catch(() => {});
  }, []);
  useEffect(load, [load]);
  useEffect(() => {
    loadPending();
    const h = window.setInterval(() => { load(); loadPending(); }, REFRESH_MS);
    return () => window.clearInterval(h);
  }, [load, loadPending]);
  const cur = rows?.find((r) => r.robot_id === open) ?? null;
  const u = cur ? units.find((x) => x.robot.robot_id === cur.robot_id) : undefined;
  const setView2 = !readOnly && view === "set";
  return (
    <section class="sp robots rb">
      <div class="rb-grid">
        <aside class="rb-list" aria-label={t("robots")}>
          <header class="rb-listhead">
            <h1>{t("roTitle", { n: rows?.length ?? "–" })}</h1>
            {!readOnly && <button type="button" class="btn" onClick={() => setAdding(true)}>{t("roAdd")}</button>}
          </header>
          {!readOnly && openRevoked.length > 0 && (
            <p class="warn sp-pad small" role="status" data-open-revoked="1">{t("robotsOpenRevoked", { ids: openRevoked.join(", ") })}</p>
          )}
          {rows && rows.length === 0 && <p class="empty sp-pad">{t("robotsNone")}</p>}
          {/* 第 4 轮 layout r3-N3:读不到时不是一片空 */}
          {rows == null && siteDown.value && <p class="note warn sp-pad" role="status" data-load-failed="1">{t("loadRetry")}</p>}
          <div class="robot-cards">
            {(rows ?? []).map((r) => {
              const ux = units.find((x) => x.robot.robot_id === r.robot_id);
              const warn = r.problems.length > 0 || !!r.wifi?.change;
              const sign = !r.online ? (r.ever_seen === false ? "idle" : "bad") : warn ? "warn" : "ok";
              const doing = !r.online ? (r.ever_seen === false ? t("fleetNeverSeenShort") : t("st_offline"))
                : ux && ux.task ? ux.task : r.task_what ? taskWhat(r.task_what) : ux ? t(`st_${ux.state}` as Key) : t("online");
              return (
                <button key={r.robot_id} type="button" data-robot={r.robot_id} aria-pressed={r.robot_id === open}
                  class={["robot-card", r.robot_id === open ? "on" : "", warn ? "warn" : ""].filter(Boolean).join(" ")}
                  onClick={() => setOpen(r.robot_id)}>
                  <Sign kind={sign} />
                  <span class="rb-name"><b class="robot-name" title={label(r)}>{label(r)}</b>{r.name && <small class="muted mono">{r.robot_id}</small>}</span>
                  <span class={`mono fleet-pct${r.battery_pct != null && r.battery_pct < 20 ? " warn-text" : ""}`}>{r.battery_pct == null ? "—" : `${r.battery_pct}%`}</span>
                  <span class="fleet-doing muted">
                    {/* P1-23:刚登记、还没连上过的不是故障:灰的「等它连上」,不是红的「离线」 */}
                    {!r.online && r.ever_seen !== false ? <span class="tone-error">{doing}</span>
                      : !r.online ? <span class="state" title={t("fleetNeverSeen")}>{doing}</span> : doing}
                    {" · "}{patrolsN(r.patrols_today)}
                  </span>
                  {r.problems.length > 0 && (
                    <span class="fleet-warn">{problemText(r.problems[0], r)}{r.problems.length > 1 ? ` · ${t("robotProblems", { n: r.problems.length })}` : ""}</span>
                  )}
                  {r.wifi?.change && <span class="fleet-warn">{t("wifiPending")}</span>}
                </button>
              );
            })}
          </div>
          {!readOnly && pending.length > 0 && (
            <section class="rb-enrol bind-pending" aria-label={t("bindPending")}>
              <h2><Sign kind="info" />{pending.length === 1 ? t("roEnrol1") : t("roEnrolN", { n: pending.length })}</h2>
              <p class="muted small">{t("bindPendingHint")}</p>
              <ul class="plain">
                {pending.map((p) => (
                  <li key={p.id} class="bind-req" data-serial={p.serial}>
                    <span class="muted"><span class="mono">{p.serial}</span> · {t("bindFrom", { t: hm(p.created_ms), src: p.source })}</span>
                    <span>{t("roVerifyCode")} <strong class="mono check-digits">{p.check}</strong></span>
                    {rejecting === p.id ? (
                      <span class="rb-ask" role="group">
                        <span>{t("bindRejectConfirm", { id: p.serial })}</span>
                        <span class="rb-row">
                          <button type="button" class="btn danger" onClick={() => {
                            setRejecting(null);
                            api("POST", `/api/admin/bind/${enc(p.id)}/reject`, {})
                              .then(() => say(t("bindRejected", { id: p.serial })))
                              .catch((e) => say(errText(e)))
                              .finally(loadPending);
                          }}>{t("bindReject")}</button>
                          <button type="button" class="btn" onClick={() => setRejecting(null)}>{t("cancel")}</button>
                        </span>
                      </span>
                    ) : (
                      <span class="rb-row">
                        <button type="button" class="btn primary" onClick={() => setApproving(p)}>{t("roVerify")}</button>
                        <button type="button" class="btn" onClick={() => setRejecting(p.id)}>{t("bindReject")}</button>
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            </section>
          )}
        </aside>
        {cur && (
          <div class="rb-main robot-detail" aria-label={label(cur)}>
            <header class="rb-head">
              <h2>{label(cur)}</h2>
              <StateTag r={cur} u={u} />
              <span class="rb-sub muted">{[cur.name ? cur.robot_id : "", locText(u) ? t(locText(u)!) : "",
                cur.manual_only ? t("manualOnly") : t("autoDispatch"),
                cur.last_seen_ms ? t("roLastContact", { t: ago(cur.last_seen_ms, now) }) : ""].filter(Boolean).join(" · ")}</span>
              {!readOnly && (
                <div class="seg rb-views" role="group" aria-label={label(cur)}>
                  <button type="button" aria-pressed={view === "op"} onClick={() => setView("op")}>{t("roOperate")}</button>
                  <button type="button" aria-pressed={view === "set"} onClick={() => setView("set")}>{t("roSettings")}</button>
                </div>
              )}
            </header>
            {setView2 ? (
              <RobotSettings key={cur.robot_id} r={cur} u={u} now={now} say={say} onChanged={load} onCode={setCode} />
            ) : u ? (
              <RobotControl key={cur.robot_id} u={u} role={role} now={now} alerts={alerts} patrols={patrols}
                since={startOfDay(now)} say={say} refresh={async () => { load(); await refresh?.(); }} onBack={() => {}} embedded
                sideExtra={<Health r={cur} now={now} />} />
            ) : (
              <div class="rb-off">
                <p class="sp-pad muted">{t("roNotConnected")}</p>
                <Health r={cur} now={now} />
              </div>
            )}
          </div>
        )}
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
    </section>
  );
}

const devOk = (s: string) => s === "online" || s === "ok";

function startOfDay(ms: number): number {
  const d = new Date(ms);
  d.setHours(0, 0, 0, 0);
  return d.getTime();
}

/** 名字旁边那块状态牌:在巡逻(绿)、离线(红)、还没连上(灰)、有毛病(黄)。 */
function StateTag({ r, u }: { r: RobotCard; u?: UnitInfo }) {
  if (!r.online) {
    return r.ever_seen === false ? <span class="rb-tag idle">{t("fleetNeverSeen")}</span>
      : <span class="rb-tag bad"><Sign kind="bad" />{t("st_offline")}</span>;
  }
  const warn = r.problems.length > 0 || !!r.wifi?.change;
  const s = u ? (u.stale ? t("stUnknown") : t(`st_${u.state}` as Key)) : t("online");
  return <span class={`rb-tag ${warn ? "warn" : "ok"}`}><Sign kind={warn ? "warn" : "ok"} />{s}{r.battery_pct != null && warn ? ` ${r.battery_pct}%` : ""}</span>;
}

/** 操作视图右栏末尾:电量、网络、存储、设备、软件、巡逻统计(老详情里的「现在」「巡逻」「基本信息」)。 */
function Health({ r, now }: { r: RobotCard; now: number }) {
  const bad = (r.devices ?? []).filter((x) => !devOk(x.state));
  const row = (k: Key, v: preact.ComponentChildren, warn = false) => <><dt>{t(k)}</dt><dd class={warn ? "warn-text" : undefined}>{v}</dd></>;
  const used = r.storage ? Math.round(r.storage.used_ratio * 100) : null;
  return (
    <section class="rc-sec rb-health">
      <h3 class="lbl">{t("roHealth")}</h3>
      <dl class="rb-kv">
        {row("roBattery", r.battery_pct == null ? "—" : `${r.battery_pct}%`, r.battery_pct != null && r.battery_pct < 20)}
        {row("roNetwork", r.wifi ? `${r.wifi.ssid || "—"} · ${t(`link_${r.wifi.link}` as Key)}` : "—")}
        {/* 第 11 轮 W11-02:不知道待传几个(站点从盘那一行读出的用量)只写用了多少 */}
        {r.storage && row("roStorage", r.storage.backlog_files == null ? t("rdStorageUsed", { p: used! })
          : t("rdStorageVal", { p: used!, n: r.storage.backlog_files }), used! >= 80)}
        {(r.devices?.length ?? 0) > 0 && row("roDevices", bad.length ? bad.map((x) => `${devName(x.id)} ${t(`dev_${x.state}` as Key)}`).join(" · ") : t("roDevicesOk"), bad.length > 0)}
        {row("roSoftware", <>{r.agent ?? "—"}{r.map && <> · <span>{mapName(r.map.id)} v{r.map.version ?? "?"}</span></>}
          {r.map?.match === false && <small class="rd-bad"> {t("rdMapBad")}</small>}</>, r.map?.match === false)}
        {row("roPatrols", <>{t("roPatrolsVal", { a: r.patrols_today, b: r.patrols_7d ?? "—", c: r.aborts_7d ?? "—" })}
          {r.last_patrol_ms != null && <span class="muted"> · {t("roLastPatrol", { t: when(r.last_patrol_ms, now) })}</span>}</>)}
      </dl>
    </section>
  );
}

type Check = { k: string; group: "conn" | "hw" | "setup"; sign: "ok" | "warn" | "bad" | "info"; label: Key; value: string; sub?: string; act?: preact.ComponentChildren };

/** 设置视图(R-A2):名字、派单方式;检查单(要处理的在上、正常的收起来按组列);排查与维护(远程运维);右栏告警记录、解绑。 */
function RobotSettings({ r, u, now, say, onChanged, onCode }: {
  r: RobotCard; u?: UnitInfo; now: number; say: Say; onChanged: () => void;
  onCode: (c: { id: string; code: string; hours: number }) => void;
}) {
  const [name, setName] = useState(r.name);
  const [ask, setAsk] = useState<{ text: string; yes: string; danger?: boolean; go: () => void } | null>(null);
  const [unbind, setUnbind] = useState(false);
  const [showOk, setShowOk] = useState(false);
  useEffect(() => setName(r.name), [r.robot_id, r.name]);
  const act = async (fn: () => Promise<unknown>, msg?: string) => {
    try {
      await fn();
      if (msg) say(msg);
    } catch (e) {
      say(errText(e));
    }
    onChanged();
  };
  const tasks = Object.keys(u?.robot.capabilities?.tasks ?? {});
  const askBtn = (text: string, yes: string, go: () => void, labelKey: Key) =>
    <button type="button" class="btn" onClick={() => setAsk({ text, yes, go })}>{t(labelKey)}</button>;
  const days = r.expires_at ? Math.floor((r.expires_at - now) / 86_400_000) : null;
  const compat: Key = r.compat === "ok" ? "compat_ok" : (`compat_${r.compat}` as Key);
  const badDevs = (r.devices ?? []).filter((x) => !devOk(x.state));
  const used = r.storage ? Math.round(r.storage.used_ratio * 100) : null;
  const checks: Check[] = [
    { k: "conn", group: "conn", sign: r.online ? "ok" : r.ever_seen === false ? "info" : "bad", label: "roConn",
      value: r.online ? t("roOnlineNow") : r.ever_seen === false ? t("fleetNeverSeen") : t("st_offline"),
      sub: r.last_seen_ms ? t("roLastContact", { t: ago(r.last_seen_ms, now) }) : undefined },
    r.wifi?.change ? {
      k: "wifi", group: "conn", sign: "info", label: "roWifi", value: t("roWifiReq", { ssid: r.wifi.change.ssid }),
      sub: t(r.wifi.change.mode === "trial" ? "wifiChangeTrial" : "wifiChangeAsk", { ssid: r.wifi.change.ssid }),
      act: <WifiChange id={r.robot_id} ch={r.wifi.change} act={act} />,
    } : { k: "wifi", group: "conn", sign: "ok", label: "roWifi", value: r.wifi ? `${r.wifi.ssid || "—"} · ${t(`link_${r.wifi.link}` as Key)}` : "—" },
    { k: "cert", group: "conn", sign: days != null && days < 30 ? "warn" : "ok", label: "roCert",
      value: r.expires_at ? t("roCertVal", { d: day(r.expires_at) }) : "—", sub: days != null ? t("roCertDays", { n: days }) : undefined,
      act: tasks.includes("cert_csr") ? <button type="button" class="btn"
        onClick={() => void act(() => api("POST", `/api/robots/${enc(r.robot_id)}/ops/cert-renew`), t("roCertRenewed"))}>{t("roCertRenew")}</button> : undefined },
    { k: "code", group: "conn", sign: "ok", label: "roCode", value: t("roCodeHint"),
      // P1-26 / P1-05:重出开通码先确认,说清是什么意思
      act: askBtn(t("newCodeAsk", { id: label(r) }), t("newCode"), () => void act(async () => {
        const d = await api<{ code: string; hours: number }>("POST", `/api/admin/robots/${enc(r.robot_id)}/code`, {});
        onCode({ id: r.robot_id, code: d.code, hours: d.hours });
      }), "roCodeIssue") },
    { k: "batt", group: "hw", sign: r.battery_pct != null && r.battery_pct < 20 ? "warn" : "ok", label: "roBattery",
      value: r.battery_pct == null ? "—" : r.battery_pct < 20 ? t("roBattLow", { p: r.battery_pct }) : `${r.battery_pct}%` },
    ...(r.storage ? [{ k: "storage", group: "hw" as const, sign: (used! >= 80 ? "warn" : "ok") as Check["sign"], label: "roStorage" as Key,
      value: r.storage.backlog_files == null ? t("rdStorageUsed", { p: used! }) : t("rdStorageVal", { p: used!, n: r.storage.backlog_files }) }] : []),
    { k: "sw", group: "hw", sign: r.compat !== "ok" || r.map?.match === false ? "warn" : "ok", label: "roSw",
      value: [`${r.agent ?? "—"} · ${t(compat)}`, r.map ? `${mapName(r.map.id)} v${r.map.version ?? "?"}` : ""].filter(Boolean).join(" · "),
      sub: r.map?.match === false ? t("rdMapBad") : r.map?.match === true ? t("rdMapOk") : undefined },
    ...((r.devices?.length ?? 0) > 0 ? [{ k: "devs", group: "hw" as const, sign: (badDevs.length ? "warn" : "ok") as Check["sign"], label: "roDevices" as Key,
      value: badDevs.length ? badDevs.map((x) => `${devName(x.id)} ${t(`dev_${x.state}` as Key)}`).join(" · ") : t("roDevicesOk"),
      sub: (r.devices ?? []).map((x) => devName(x.id)).join(" · ") }] : []),
    // 用户 11-27:老原点离墙太近(回原点会被拒)也写出来
    ...(r.home_set != null ? [{ k: "home", group: "setup" as const, sign: (r.home_set && !r.home_bad ? "ok" : "warn") as Check["sign"], label: "roOrigin" as Key,
      value: !r.home_set ? t("rdNoHome") : r.home_bad ? t("rdHomeBad") : t("roSet"),
      act: r.home_set && !r.home_bad ? undefined : <a class="btn" href="#/admin/localization">{t(r.home_bad ? "rdHomeBadGo" : "rdNoHomeGo")}</a> }] : []),
    // 易用性 37 复测 P1-7:默认待命点在图上走不了 —— 回待命点、值守都派不了,写出来
    ...(r.standby_set != null ? [{ k: "standby", group: "setup" as const, sign: (r.standby_set && !r.standby_bad ? "ok" : "warn") as Check["sign"], label: "roStandby" as Key,
      value: !r.standby_set ? t("rdNoStandby") : r.standby_bad ? t("rdStandbyBad") : t("roSet"),
      act: r.standby_set && !r.standby_bad ? undefined : <a class="btn" href="#/admin/layout?tab=standby">{t(r.standby_bad ? "rdStandbyBadGo" : "rdNoStandbyGo")}</a> }] : []),
    ...(r.fov ? [{ k: "fov", group: "setup" as const, sign: (r.fov.state === "ready" ? "ok" : "info") as Check["sign"], label: "roFov" as Key,
      value: r.fov.state === "ready" ? t("roFovReady")
        : r.fov.state === "learning" ? t("roFovLearning", { p: Math.min(99, Math.floor(100 * (r.fov.frames ?? 0) / Math.max(1, r.fov.need ?? 1))) })
        : t("roFovNone"),
      sub: r.fov.state === "ready" ? undefined : t("roFovHint") }] : []),
    ...r.problems.filter((p) => !("device" in p)).map((p, i) => ({ k: `p${i}`, group: "hw" as const, sign: "warn" as const, label: "roIssue" as Key,
      value: problemText(p, r), sub: "first_ms" in p ? when(p.first_ms, now) : undefined })),
  ];
  const need = checks.filter((c) => c.sign !== "ok");
  const okc = checks.filter((c) => c.sign === "ok");
  const row = (c: Check) => (
    <li key={c.k} class={`rb-check ${c.sign}`} data-check={c.k}>
      <Sign kind={c.sign} />
      <b>{t(c.label)}</b>
      <span class="rb-cval"><span class={c.sign === "warn" || c.sign === "bad" ? "warn-text" : undefined}>{c.value}</span>{c.sub && <small class="muted">{c.sub}</small>}</span>
      <span class="rb-cact">{c.act}</span>
    </li>
  );
  const GROUPS: [Check["group"], Key][] = [["conn", "roGConn"], ["hw", "roGHw"], ["setup", "roGSetup"]];
  return (
    <div class="rb-set">
      <div class="rb-setmain">
        <div class="rb-setbar">
          <form class="rb-namef" onSubmit={(e) => { e.preventDefault(); void act(() => api("POST", `/api/admin/robots/${enc(r.robot_id)}/name`, { name: name.trim() }),
            name.trim() ? t("saved") : t("robotNameCleared", { id: r.robot_id })); }}>
            <label class="lbl" for={`rd-name-${r.robot_id}`}>{t("robotName")}</label>
            <input id={`rd-name-${r.robot_id}`} name="name" value={name} maxLength={32} placeholder={r.robot_id}
              onInput={(e) => setName(e.currentTarget.value)} />
            <button type="submit" class="btn" disabled={name === r.name} title={name === r.name ? t("rdWhyNameSame") : undefined}>{t("robotNameSave")}</button>
            {/* P2-12:写明最多几个字(原来超了悄悄截掉) */}
            <small class={name.length >= 32 ? "warn-text" : "muted"} data-name-count="1">{t("robotNameCount", { n: name.length, max: 32 })}</small>
          </form>
          <div class="rb-dispatch">
            <span class="lbl">{t("dispatchMode")}</span>
            <div class="seg" role="group" aria-label={t("dispatchMode")}>
              {/* P1-26:切派遣方式先确认,说清是什么意思(原地,不弹窗) */}
              <button type="button" aria-pressed={!r.manual_only} onClick={() => r.manual_only && setAsk({ text: t("setAutoAsk", { id: label(r) }), yes: t("setAuto"),
                go: () => void act(() => api("POST", `/api/robots/${enc(r.robot_id)}/service`, { manual_only: false }), t("setAutoDone", { id: label(r) })) })}>{t("autoDispatch")}</button>
              <button type="button" aria-pressed={r.manual_only} onClick={() => !r.manual_only && setAsk({ text: t("setManualAsk", { id: label(r) }), yes: t("setManual"),
                go: () => void act(() => api("POST", `/api/robots/${enc(r.robot_id)}/service`, { manual_only: true }), t("setManualDone", { id: label(r) })) })}>{t("manualOnly")}</button>
            </div>
            <span class="muted small">{t(r.manual_only ? "roDispatchManual" : "roDispatchAuto")}{r.manual_only && r.manual_note ? ` ${siteKnown(r.manual_note)}` : ""}</span>
          </div>
        </div>
        {ask && !ask.danger && (
          <div class="rb-ask sp-pad" role="group">
            <p>{ask.text}</p>
            <span class="rb-row">
              <button type="button" class="btn primary" onClick={() => { const g = ask.go; setAsk(null); g(); }}>{ask.yes}</button>
              <button type="button" class="btn" onClick={() => setAsk(null)}>{t("cancel")}</button>
            </span>
          </div>
        )}
        <h3 class="rb-sum">{need.length === 0 ? <b>{t("roAllOk")}</b> : <><b>{need.length === 1 ? t("roAttention1") : t("roAttentionN", { n: need.length })}</b> {t("roOtherOk", { n: okc.length })}.</>}</h3>
        {need.length > 0 && <ul class="rb-checks">{need.map(row)}</ul>}
        <div class="rb-okbar">
          <span class="muted">{t("roOtherOk", { n: okc.length })}</span>
          <button type="button" class="linkbtn" aria-expanded={showOk || need.length === 0} onClick={() => setShowOk(!showOk)}>{showOk || need.length === 0 ? t("roCollapse") : t("roExpand")}</button>
        </div>
        {(showOk || need.length === 0) && GROUPS.map(([g, k]) => {
          const xs = okc.filter((c) => c.group === g);
          return xs.length ? <div key={g}><h4 class="sp-lbl">{t(k)}</h4><ul class="rb-checks">{xs.map(row)}</ul></div> : null;
        })}
        <h4 class="sp-lbl">{t("roTrouble")}</h4>
        <p class="sp-pad muted small">{t("roTroubleHint")}</p>
        <div class="sp-pad rb-ops"><RobotOps robotId={r.robot_id} tasks={tasks} say={say} /></div>
      </div>
      <aside class="rb-setside">
        <RecentAlerts items={r.recent_problems} />
        <section class="rd-sec rb-removal">
          <h3 class="rd-h">{t("roRemoval")}</h3>
          {r.enrolled_at != null && <p class="muted small">{t("rdEnrolled")} {day(r.enrolled_at)}</p>}
          <button type="button" class="btn danger" onClick={() => setAsk({
            // 第 4 轮:解绑要重启消息服务器(吊销名单 broker 重启才读),所有机器人断线几秒 —— 写明会怎样
            text: `${t(r.online ? "robotUnbindConfirm" : r.ever_seen === false ? "robotUnbindConfirmNever" : "robotUnbindConfirmOffline", { id: label(r) })} ${t("robotUnbindBroker")}`,
            yes: t("roContinue"), danger: true, go: () => setUnbind(true) })}>{t("roUnbindBtn", { id: label(r) })}</button>
          <p class="muted small">{t("roUnbindHint")}</p>
          {ask?.danger && (
            <div class="rb-ask" role="group">
              <p>{ask.text}</p>
              <span class="rb-row">
                <button type="button" class="btn danger" onClick={() => { const g = ask.go; setAsk(null); g(); }}>{ask.yes}</button>
                <button type="button" class="btn" onClick={() => setAsk(null)}>{t("cancel")}</button>
              </span>
            </div>
          )}
        </section>
      </aside>
      {unbind && (
        <ConfirmPassword title={t("robotUnbind")} onClose={() => setUnbind(false)}
          onConfirm={async (pw) => {
            const d = await api<{ robot_wipe?: string; old_connection_open?: boolean }>("POST", `/api/admin/robots/${enc(r.robot_id)}/revoke`, { confirm_password: pw });
            setUnbind(false);
            // 网页易用性第 1 轮 P0-10:如实说 —— 老版本不认远程清除;消息服务器没重启时旧连接还开着
            // 第 3 轮 P0-10:从没连上过的不说「下次连上时删数据」(跟确认框说法相反)
            const wipe = d.robot_wipe === "sent" ? "robotUnbound" : d.robot_wipe === "unsupported" ? "robotUnboundNoWipe" : r.ever_seen === false ? "robotUnboundNever" : "robotUnboundOffline";
            say([t(wipe, { id: label(r) }), d.old_connection_open ? t("robotUnboundOpen") : ""].filter(Boolean).join(" "));
            onChanged();
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

export interface VoicePreset { lang: string; text: string }
export const PRESET_LANGS: [string, string][] = [["zh", "中文"], ["en", "English"], ["ms", "Melayu"]];
const PRESETS_MAX = 12;
/** 句子里的语言名跟界面语言走(下拉框里写各自的本名)。 */
const LANG_NAME: Record<string, [string, string]> = { zh: ["Chinese", "中文"], en: ["English", "英文"], ms: ["Malay", "马来文"] };
export const langName = (l: string) => LANG_NAME[l]?.[lang.value === "zh" ? 1 : 0] ?? l;

/** 第三档 #41:管理员编辑常用喊话(整张换)。空的、重复的当场说,不发。 */
export function PresetEditor({ init, onClose, onSaved, inline }: { init: VoicePreset[]; onClose: () => void; onSaved: (p: VoicePreset[]) => void; inline?: boolean }) {
  const [rows, setRows] = useState<VoicePreset[]>(init.map((p) => ({ ...p })));
  const [err, setErr] = useState("");
  const [bad, setBad] = useState(-1);       // UIUX-049:出错的是第几句(标 aria-invalid、焦点放过去)
  const [busy, setBusy] = useState(false);
  const form = useRef<HTMLFormElement>(null);
  const put = (i: number, p: Partial<VoicePreset>) => {
    if (i === bad) setBad(-1);
    setRows(rows.map((x, j) => (j === i ? { ...x, ...p } : x)));
  };
  const flag = (i: number, msg: string) => {
    setBad(i);
    setErr(msg);
    form.current?.querySelectorAll<HTMLInputElement>("input[data-voice-text]")[i]?.focus();
  };
  async function save(e: Event) {
    e.preventDefault();
    const out = rows.map((x) => ({ lang: x.lang, text: x.text.trim() }));
    const empty = out.findIndex((x) => !x.text);
    if (empty >= 0) return flag(empty, t("rdPresetEmpty", { n: empty + 1 }));
    const dup = out.findIndex((x, i) => out.findIndex((y) => y.text === x.text) < i);
    if (dup >= 0) return flag(dup, t("rdPresetDup", { n: dup + 1 }));
    setBad(-1);
    setBusy(true);
    try {
      const r = await api<{ presets: VoicePreset[] }>("POST", "/api/voice-presets", { presets: out });
      onSaved(r.presets ?? out);
    } catch (x) {
      setErr(x instanceof ApiError ? x.message : String(x));
    } finally {
      setBusy(false);
    }
  }
  // 第七期(HANDOFF 不弹窗):单台控制里就地展开编辑,不开对话框
  const body = (
      <form class="form preset-form" ref={form} onSubmit={save}>
        <p class="muted small">{t("rdPresetsHint")}</p>
        {rows.map((x, i) => (
          <div class="preset-row" key={i}>
            <select data-voice-lang="1" aria-label={`${t("rdPresetLang")} ${i + 1}`} value={x.lang} onChange={(e) => put(i, { lang: e.currentTarget.value })}>
              {PRESET_LANGS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
            <input data-voice-text="1" aria-label={`${t("rdPresetText")} ${i + 1}`} maxLength={300} value={x.text}
              aria-invalid={i === bad ? true : undefined} aria-describedby={i === bad ? "preset-err" : undefined}
              onInput={(e) => put(i, { text: e.currentTarget.value })} />
            <button type="button" class="btn sm danger" data-voice-del="1" onClick={() => setRows(rows.filter((_, j) => j !== i))}>{t("rdPresetDel")}</button>
          </div>
        ))}
        {rows.length < PRESETS_MAX && (
          <button type="button" class="btn sm ly-new" onClick={() => setRows([...rows, { lang: lang.value === "zh" ? "zh" : "en", text: "" }])}>{t("rdPresetAdd")}</button>
        )}
        {err && <p class="error small" role="alert" id="preset-err" data-form-error="1">{err}</p>}
        <div class="row end">
          <button type="button" class="btn" onClick={onClose}>{t("cancel")}</button>
          <button type="submit" class="btn primary" disabled={busy}>{t("save")}</button>
        </div>
      </form>
  );
  if (inline) return <div class="preset-inline" role="group" aria-label={t("rdPresetsEdit")} data-preset-inline="1"><h4 class="lbl">{t("rdPresetsEdit")}</h4>{body}</div>;
  return <Modal label={t("rdPresetsEdit")} wide onClose={onClose}>{body}</Modal>;
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
    <span class="rb-col wifi-change">
      <button type="button" class="btn primary" onClick={() => send(true)}>{t("wifiApprove")}</button>
      <button type="button" class="btn" onClick={() => send(false)}>{t("wifiReject")}</button>
    </span>
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
