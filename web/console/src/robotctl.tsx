// 单台机器人控制(redesign 第四期,design/console-v2/png-en/G-robot.png):值班页右栏「Details」进,在中间那一块切换,不弹窗。
// 左边画面(前 / 后 / 热成像,云台方向键、雨刷)+ 喊话(常用话、打字、语言)+ 警示(警灯、警笛、录好的话);
// 右边当前任务(停下 / 回待命点 / 回原点)、派巡逻(忙时排队)、派去看一眼、姿态、定位、今天这台的事。
// 权限跟老机器人页一样:派巡逻、停下 = 能派巡逻的(含经理);回待命、回原点、定位、恢复、姿态、云台、喊话、警示 = 能派单的。
// 只读只看。换姿态、停下回原点在原地确认(老页面是弹窗)。
import { byText } from "./sitetext";
import type { ComponentChildren } from "preact";
import { useEffect, useRef, useState } from "preact/hooks";
import { api, ApiError, enc } from "./api";
import { CameraWell } from "./camera";
import { hm, nameOf, mapName } from "./data";
import { refusalText, t, type Key } from "./i18n";
import { locText, type UnitInfo } from "./live";
import { lapText, LoopsSelect } from "./loops";
import { canDisarm, canDispatch, canFindPose, canPatrol, canTeleop, forGuard, isOwnerLike, robotCams, robotMap, type Alert } from "./model";
import { MapCanvas } from "./mapcanvas";
import { type PreviewMeta } from "./mapview";
import { recentActivity } from "./shifttl";
import { notAccepted, type CommandReply } from "./posepick";
import { CLIP_KEY, langName, POSTURE_KEY, PresetEditor, STROBE_S, taskWhat, type Posture, type RobotCard, type VoicePreset } from "./robotspage";
import { pageAllowed } from "./shell";
import { Sign, stateSign } from "./signs";
import { siteHm, type TodayItem } from "./todaypatrols";

type Say = (s: string) => void;
type Reply = CommandReply & { queued?: boolean; start_after_ms?: number; because?: string; utc_offset_min?: number };
/** 云台每按一下转多少度、上限(nexwar_contract.deter);雨刷刷多久。 */
const PAN_STEP = 15, TILT_STEP = 10, PAN_MAX = 180, TILT_MAX = 90, WIPER_S = 10;
const REFRESH_MS = 10_000;

export function RobotControl(props: {
  u: UnitInfo;
  role: string;
  now: number;
  alerts: Alert[];
  patrols: TodayItem[];
  since: number;
  say: Say;
  refresh: () => Promise<void>;
  onBack: () => void;
  /** 「派去看一眼…」:回全场地图、开看一眼工具。没有 = 不给(现场设置 → 机器人里)。 */
  onLook?: (robot: string) => void;
  /** 第六期 R-A:嵌在现场设置 → 机器人「操作」里 —— 不画自己的页头(那页有),右栏末尾接健康状况。 */
  embedded?: boolean;
  sideExtra?: ComponentChildren;
  /** 「协助定位」:回全场地图,在地图上点它的实际位置(老值班页的「帮它找位置」)。 */
  onFind?: (robot: string) => void;
}) {
  const id = props.u.robot.robot_id;
  const name = nameOf(id);
  // 实时数据(/api/robots,保安也能读)推出控制要的那些;机器人概况(管理员、经理能读)再补任务说法、待命点、语言
  const [ov, setOv] = useState<RobotCard | null>(null);
  const r: RobotCard = { ...cardFromUnit(props.u), ...(ov ?? {}), ...liveOf(props.u) };
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  // 用户 11-27:「中止并回原点」当场选回到原点后怎么办(布防值守跟着办):马上出发 / 等几分钟 / 撤防
  type After = { after: "go" | "wait" | "disarm"; min: number };
  const [ask, setAsk] = useState<{ text: string; yes: string; run: (o: After) => void; after?: boolean } | null>(null);
  const [after, setAfter] = useState<After["after"]>("wait");
  const [afterMin, setAfterMin] = useState(10);
  const load = () => api<{ robots: RobotCard[] }>("GET", "/api/robots/overview")
    .then((d) => setOv((d.robots ?? []).find((x) => x.robot_id === id) ?? null)).catch(() => setOv(null));
  useEffect(() => {
    setOv(null); setErr(null); setAsk(null);
    void load();
    const h = window.setInterval(load, REFRESH_MS);
    return () => window.clearInterval(h);
  }, [id]);

  const patrol = canPatrol(props.role);
  const dispatch = canDispatch(props.role);
  const off = !r.online;
  const path = (a: string) => `/api/robots/${enc(id)}/${a}`;
  const changed = () => { void load(); void props.refresh(); };
  async function send(fn: () => Promise<Reply | null>, ok: string) {
    setBusy(true);
    setErr(null);
    try {
      const res = await fn();
      if (res === null) return;
      if (res.queued) props.say(t("trQueued", { id: name, at: siteHm(res.start_after_ms ?? 0, res.utc_offset_min), why: res.because ?? "" }));
      else {
        const no = res.ack ? notAccepted(res) : null;
        if (no) setErr(t("rdNotAccepted", { why: no }));
        else props.say(ok);
      }
    } catch (e) {
      setErr(e instanceof ApiError ? refusalText(e.message, e.data) : String(e));
    } finally {
      setBusy(false);
      changed();
    }
  }
  const post = (a: string, body: Record<string, unknown> = {}) => () => api<Reply>("POST", path(a), body);
  const abort = () => send(async () => {
    const v = await api<{ status?: { task?: { task_id?: string } | null } | null }>("GET", `/api/robots/${enc(id)}`);
    const tid = v.status?.task?.task_id;
    if (!tid) { props.say(t("rdNoTask", { id: name })); return null; }
    const res = await api<Reply>("POST", path("abort"), { task_id: tid });
    for (const ms of [1500, 4000]) setTimeout(changed, ms);
    return res;
  }, t("rdSent", { id: name, what: t("rcStop") }));

  const u = props.u;
  // I1 11-17:1024×768 下右栏「详情」在页面下面,面板开在中间一块的上方、看不见:滚进视野、焦点给它
  const root = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = root.current;
    if (!el || props.embedded) return;
    el.scrollIntoView?.({ block: "start", behavior: "smooth" });
    el.focus({ preventScroll: true });
  }, [id]);
  const sign = u.stale ? "warn" : stateSign(u.state);
  const loc = locText(u);
  const seen = u.robot.status?.last_seen;
  const lastContact = seen ? Math.max(0, Math.round((props.now - seen * 1000) / 1000)) : null;
  const sub = [u.task, u.battery != null ? `${Math.round(u.battery)}%` : "", loc ? t(loc) : "",
    lastContact != null && !off ? t("rcLastContact", { s: lastContact }) : ""].filter(Boolean).join(" · ");
  const task = r.task ?? null;
  const offWhy = t(r.ever_seen === false ? "rdNeverNoCtl" : "rdOfflineNoCtl");
  const today = recentActivity(props.alerts.filter((a) => a.robot === id && forGuard(a)), props.patrols.filter((p) => p.robot === id), props.since, props.now).slice(0, 8);

  return (
    <div class="rc" data-robot={id} ref={root} tabIndex={-1}>
      {!props.embedded && <header class="rc-head">
        <button type="button" class="btn" onClick={props.onBack}>{t("rcSiteView")}</button>
        <b class="rc-name">{name}</b>
        <span class={`mon-state ${sign}`}><Sign kind={sign} />{u.stale ? t("stUnknown") : t(`st_${u.state}` as Key)}</span>
        <span class="rc-sub" title={sub}>{sub}</span>
        {pageAllowed("admin/robots", props.role) && <a class="btn push" href={`#/admin/robots?robot=${enc(id)}`}>{t("rcSettings")}</a>}
      </header>}
      <div class="rc-body">
        <div class="rc-main">
          {/* 用户 11-15:画面占 2/3、右边 1/3 是这台在地图上的位置 */}
          <div class="rc-top">
            <Video u={u} now={props.now} deter={dispatch ? r.deter ?? null : null} busy={busy} off={off} send={send} post={post} name={name} />
            <RobotMiniMap u={u} />
          </div>
          {dispatch && r.deter ? <Voice r={r} name={name} busy={busy} off={off} send={send} post={post} admin={isOwnerLike(props.role)} say={props.say} />
            : r.deter && <p class="rc-guard-only muted">{t("rcGuardOnly")}</p>}
        </div>
        <aside class="rc-side">
          <section class="rc-sec rc-task">
            <h3 class="lbl">{t("rcTaskH")}</h3>
            {r.held && (
              <div class="rc-held warn">
                <p>{t("rdHeld", { by: byText(r.held.by), t: hm(r.held.at_ms) })}</p>
                {dispatch && <button type="button" class="btn primary" disabled={busy}
                  onClick={() => void send(post("resume"), t("rdSent", { id: name, what: t("rdResume") }))}>{t("rdResume")}</button>}
              </div>
            )}
            {/* 真机 11-25:遥控松手后站点倒数再派回待命点 —— 写明它要自己走、还剩几秒,能取消 */}
            {r.standby_countdown && (
              <div class="rc-held warn" data-standby-countdown={id}>
                <p>{t("rcReturnIn", { s: Math.max(0, Math.ceil((r.standby_countdown.due_ms - props.now) / 1000)) })}</p>
                {patrol && <button type="button" class="btn primary" disabled={busy}
                  onClick={() => void send(async () => {
                    const d = await api<{ cancelled?: boolean; until_ms?: number | null }>("POST", path("standby/cancel"), {});
                    if (!d.cancelled) { props.say(t("rcReturnTooLate", { id: name })); return null; }
                    // 易用性 build 36 P1-4:写清楚值守到几点前不自动派这台
                    if (d.until_ms) { props.say(t("rcReturnStay", { id: name, t: hm(d.until_ms) })); return null; }
                    return {} as Reply;
                  },
                    t("rcReturnCancelled", { id: name }))}>{t("rcReturnCancel")}</button>}
              </div>
            )}
            {/* 真机 11-25:撤防了还在喊、App 关灯停不了喊话 —— 一键静音(到下次布防) */}
            {patrol && r.deter?.outputs.some((o) => o === "speaker" || o === "siren") && (
              <div class="rc-row" data-mute={id}>
                <button type="button" class="btn" aria-pressed={!!r.muted} disabled={busy}
                  onClick={() => void send(async () => { await api("POST", path("mute"), { on: !r.muted }); return {} as Reply; },
                    t(r.muted ? "rcUnmuted" : "rcMutedDone", { id: name }))}>{t(r.muted ? "rcUnmute" : "rcMute")}</button>
                {r.muted && <span class="muted small">{t("rcMutedBy", { by: r.muted })}</span>}
              </div>
            )}
            <p class="rc-task-now">{task ? (r.task_what ? [r.task_what.kind === "patrol" && r.task_what.route ? t("rcRunning", { what: r.task_what.route }) : taskWhat(r.task_what), lapText(r.lap)].filter(Boolean).join(" · ") : u.task || taskWhat(null)) : t("rcNoTask")}</p>
            {off && <p class="rc-off muted small">{offWhy}</p>}
            {(patrol || dispatch) && (
              <div class="rc-row">
                {patrol && <button type="button" class="btn" disabled={busy || off || task === null} title={task === null ? t("rdIdle") : undefined}
                  onClick={() => void abort()}>{t("rcStop")}</button>}
                {dispatch && <button type="button" class="btn" disabled={busy || off || r.standby_set === false}
                  title={r.standby_set === false ? t("rdNoStandby") : undefined}
                  onClick={() => task
                    // 易用性 37 用户 11-27 轮 P2-1:有任务时机器人拒(busy)—— 先问,确认了先中止这一趟再回
                    ? setAsk({ text: t("rdReturnAbortAsk", { id: name, what: taskWhat(r.task_what) }), yes: t("rdReturn"),
                        run: () => void send(post("standby/return", { abort: true }), t("rdSent", { id: name, what: t("rdReturn") })) })
                    : void send(post("standby/return"), t("rdSent", { id: name, what: t("rdReturn") }))}>{t("rdReturn")}</button>}
              </div>
            )}
            {dispatch && (
              task ? (
                <div class="rc-row"><button type="button" class="btn" disabled={busy || off}
                  onClick={() => { setAfter("wait"); setAfterMin(10); setAsk({ text: t("rdAbortHomeAsk", { id: name, what: taskWhat(r.task_what) }), yes: t("rdAbortHome"), after: true,
                    run: (o) => void send(post("home/return", { abort: true, after: o.after, ...(o.after === "wait" ? { wait_min: o.min } : {}) }),
                      t("rdSent", { id: name, what: t("rdAbortHome") })) }); }}>{t("rdAbortHome")}</button></div>
              ) : (
                <div class="rc-row"><button type="button" class="btn" disabled={busy || off || r.home_set === false}
                  title={r.home_set === false ? t("rdNoHome") : undefined}
                  onClick={() => void send(post("home/return"), t("rdSent", { id: name, what: t("rdHome") }))}>{t("rdHome")}</button></div>
              )
            )}
            {(patrol || dispatch) && <p class="muted small">{t(dispatch ? "rcTaskHint" : "rcTaskHintMgr")}</p>}
            {/* 第 2 轮 N2(老机器人页):没原点、没待命点 —— 写为什么灰着,管理员给去处理的链接 */}
            {dispatch && !off && (r.home_set === false || r.standby_set === false) && (
              <ul class="plain rd-why small muted" data-setup-why="1">
                {r.home_set === false && <li>{t("rdNoHome")} {isOwnerLike(props.role) && <a href="#/admin/localization">{t("rdNoHomeGo")}</a>}</li>}
                {r.standby_set === false && <li>{t("rdNoStandby")} {isOwnerLike(props.role) && <a href="#/admin/layout?tab=standby">{t("rdNoStandbyGo")}</a>}</li>}
              </ul>
            )}
          </section>
          {patrol && <Dispatch r={r} id={id} name={name} busy={busy} off={off} send={send} busyTask={!!task}
            onLook={dispatch && !off && props.onLook ? () => props.onLook!(id) : undefined} />}
          {(r.postures ?? []).length > 0 || loc ? (
            <section class="rc-sec rc-state">
              {(r.postures ?? []).length > 0 && (
                <div class="rc-posture rc-kv">
                  <span>{t("rdPosture")}: <b>{u.robot.status?.ready?.motion === false ? t("rcNotStanding") : t("rcStanding")}</b></span>
                  {canTeleop(props.role) && (r.postures ?? []).filter((m) => !(m === "stand" && u.robot.status?.ready?.motion !== false)).map((m: Posture) => (
                    <button key={m} type="button" class="btn" disabled={busy || off || !!task || !!r.held}
                      title={task ? t("rdPostureBusy", { id: name, what: taskWhat(r.task_what) }) : r.held ? t("rdPostureHeld") : undefined}
                      onClick={() => setAsk({ text: t("rdPostureAsk", { id: name, what: t(POSTURE_KEY[m]) }), yes: t(POSTURE_KEY[m]),
                        run: () => void send(post("posture", { mode: m }), t("rdPostureDone", { id: name, what: t(POSTURE_KEY[m]) })) })}>{t(POSTURE_KEY[m])}</button>
                  ))}
                </div>
              )}
              <div class="rc-loc rc-kv">
                <span>{t("rcLoc")}: <b>{loc ? t(loc) : "—"}</b></span>
                {dispatch && <button type="button" class="btn" disabled={busy || off || !canFindPose(u.robot)}
                  title={!canFindPose(u.robot) ? t("rdNoAutoLoc") : undefined}
                  onClick={() => void send(post("relocalize", { global: true }), t("rdSent", { id: name, what: t("rcReloc") }))}>{t("rcReloc")}</button>}
                {dispatch && props.onFind && <button type="button" class="btn" data-find="1" disabled={off} onClick={() => props.onFind!(id)}>{t("dutyFindPose")}</button>}
              </div>
            </section>
          ) : null}
          {ask && (
            <div class="rc-ask" role="group">
              <p>{ask.text}</p>
              {ask.after && (
                <fieldset class="rc-after" data-after-home>
                  <legend class="small">{t("rdAfterHome")}</legend>
                  <label><input type="radio" name="after" checked={after === "go"} onChange={() => setAfter("go")} /> {t("rdAfterGo")}</label>
                  <label><input type="radio" name="after" checked={after === "wait"} onChange={() => setAfter("wait")} /> {t("rdAfterWaitA")}{" "}
                    <input type="number" name="after_min" min={1} max={240} value={afterMin} disabled={after !== "wait"}
                      onInput={(e) => setAfterMin(Math.max(1, Math.min(240, Math.round(Number((e.target as HTMLInputElement).value) || 1))))} />{" "}{t("rdAfterWaitB")}</label>
                  {canDisarm(props.role) && <label><input type="radio" name="after" checked={after === "disarm"} onChange={() => setAfter("disarm")} /> {t("rdAfterDisarm")}</label>}
                  <p class="muted small">{t("rdAfterNote")}</p>
                </fieldset>
              )}
              <div class="rc-row">
                <button type="button" class="btn primary" onClick={() => { const a = ask; setAsk(null); a.run({ after, min: afterMin }); }}>{ask.yes}</button>
                <button type="button" class="btn" onClick={() => setAsk(null)}>{t("cancel")}</button>
              </div>
            </div>
          )}
          {err && <p class="error small rc-err" role="alert">{err}</p>}
          <section class="rc-sec rc-today">
            <h3 class="lbl">{t("rcToday")}</h3>
            {today.length === 0 ? <p class="muted small">{t("rcNothingToday")}</p> : (
              <ul class="mon-activity">{today.map((x, i) => <li key={i}><time class="mono">{hm(x.at)}</time><span>{x.text}</span></li>)}</ul>
            )}
          </section>
          {props.sideExtra}
        </aside>
      </div>
    </div>
  );
}

/** 用户 11-15:操作页右上角的小地图 —— 这台报的那张图 + 它现在的位置和朝向。 */
function RobotMiniMap({ u }: { u: UnitInfo }) {
  const m = robotMap(u.robot);
  const key = m ? `${m.map_id}/${m.version}` : "";
  const [got, setGot] = useState<{ key: string; meta: PreviewMeta | null; failed?: boolean }>({ key: "", meta: null });
  useEffect(() => {
    if (!m) return;
    let live = true;
    api<PreviewMeta>("GET", `/api/maps/${enc(m.map_id)}/${enc(m.version)}/preview`)
      .then((meta) => live && setGot({ key, meta })).catch(() => live && setGot({ key, meta: null, failed: true }));
    return () => { live = false; };
  }, [key]);
  const pose = u.robot.loc?.pose ?? null;
  const meta = got.key === key ? got.meta : null;
  return (
    <section class="rc-map" aria-label={t("rcMapH")}>
      <h3 class="lbl">{t("rcMapH")}{m && <span class="muted"> · {mapName(m.map_id)} v{m.version}</span>}</h3>
      {!m ? <p class="muted small">{t("rcMapNone")}</p>
        : !meta ? <p class="muted small">{got.failed && got.key === key ? t("loadRetry") : t("rcMapLoading")}</p> : (
          <MapCanvas meta={meta} raster={`/api/maps/${enc(m.map_id)}/${enc(m.version)}/preview.png`} label={t("rcMapH")}
            marks={(sc) => {
              if (!pose) return null;
              const [sx, sy] = sc.map(pose.x, pose.y);
              const yaw = pose.yaw ?? 0;
              return <g class="rc-robot-mark" data-robot-mark="1">
                <line x1={sx} y1={sy} x2={sx + 18 * Math.cos(yaw)} y2={sy - 18 * Math.sin(yaw)} />
                <circle cx={sx} cy={sy} r={7} />
              </g>;
            }} />
        )}
    </section>
  );
}

/** 从实时数据(``/api/robots`` 的一台)推出控制要用的:在线、叫停、任务号、原点、第几圈、地图、能换的姿态、警示能力。 */
export function cardFromUnit(u: UnitInfo): RobotCard {
  const rb = u.robot as UnitInfo["robot"] & { lap?: RobotCard["lap"]; running?: { map_id?: string | null; map_version?: string | null } | null };
  const tasks = (rb.capabilities?.tasks ?? {}) as Record<string, unknown>;
  const fresh = u.state !== "offline";
  const d = tasks.deter as { outputs?: unknown[]; max_s?: number; tts?: boolean; clips?: unknown[]; tts_langs?: unknown[] } | undefined;
  const deter = fresh && d && Array.isArray(d.outputs) && d.outputs.length > 0
    ? { outputs: d.outputs.map(String), max_s: Number(d.max_s ?? 600), tts: !!d.tts, clips: (d.clips ?? []).map(String),
      ...(Array.isArray(d.tts_langs) ? { tts_langs: d.tts_langs.map(String) } : {}) } : null;
  const modes = (tasks.posture as { modes?: unknown[] } | undefined)?.modes;
  return {
    robot_id: rb.robot_id, name: rb.name ?? "", revoked: rb.revoked, expires_at: 0, battery_pct: u.battery,
    patrols_today: 0, problems: [], recent_problems: [], agent: null, compat: "", manual_only: false,
    home_set: rb.home_set, lap: rb.lap ?? null, deter,
    postures: fresh && Array.isArray(modes) ? modes.map(String) as Posture[] : [],
    map: rb.running?.map_id ? { id: rb.running.map_id, version: rb.running.map_version ?? null, match: null } : null,
    ...liveOf(u),
  };
}

/** 跟着实时数据走、不等概况的那几样。 */
function liveOf(u: UnitInfo): Pick<RobotCard, "online" | "held" | "task" | "standby_countdown" | "muted"> {
  const st = u.robot.status as { task?: { task_id?: string } | null } | null | undefined;
  return { online: u.state !== "offline", held: (u.robot.held as RobotCard["held"]) ?? null, task: st?.task?.task_id ?? null,
    standby_countdown: u.robot.standby_countdown ?? null, muted: u.robot.muted ?? null };
}

interface Plan { estimate_s?: number | null; start_ms?: number; queued?: boolean; because?: string; utc_offset_min?: number; forever?: boolean; return_pct?: number }
type Send = (fn: () => Promise<Reply | null>, ok: string) => Promise<void>;
type Post = (a: string, body?: Record<string, unknown>) => () => Promise<Reply>;

/** 画面:前 / 后 / 热成像切换;云台方向键、雨刷叠在画面上(这台有、能操作才有)。 */
function Video({ u, now, deter, busy, off, send, post, name }: {
  u: UnitInfo; now: number; deter: RobotCard["deter"] | null; busy: boolean; off: boolean; send: Send; post: Post; name: string;
}) {
  // 用户 11-15:至少前 / 后 / 热成像三路都列出来;这台没报的那一路画面上写明,不藏
  const has = robotCams(u.robot);
  const cams = [...(["front", "back", "thermal"] as const), ...has.filter((c) => c === "payload")] as ("front" | "back" | "thermal" | "payload")[];
  const [cam, setCam] = useState<typeof cams[number]>("front");
  const [aim, setAim] = useState<[number, number]>([0, 0]);
  const id = u.robot.robot_id;
  useEffect(() => { setCam("front"); setAim([0, 0]); }, [id]);
  const ptz = !!deter?.outputs.includes("ptz");
  const wiper = !!deter?.outputs.includes("wiper");
  // 竞品云台没有回读角度:按「上次按到哪」算
  const turn = (dp: number, dt: number) => {
    const center = dp === 0 && dt === 0;
    const pan = center ? 0 : Math.max(-PAN_MAX, Math.min(PAN_MAX, aim[0] + dp));
    const tilt = center ? 0 : Math.max(-TILT_MAX, Math.min(TILT_MAX, aim[1] + dt));
    setAim([pan, tilt]);
    void send(post("deter", { output: "ptz", on: true, pan, tilt }), t("rdPtzDone", { id: name, pan, tilt }));
  };
  const dis = busy || off;
  return (
    <section class="rc-video">
      <div class="rc-video-h">
        <div class="seg rc-cams" role="tablist" aria-label={t("monVideo")}>
          {cams.map((c) => <button key={c} type="button" role="tab" aria-selected={cam === c} class={cam === c ? "on" : ""} onClick={() => setCam(c)}>{t(c)}</button>)}
        </div>
        {ptz && <span class="rc-ptz-read mono push">{t("rcPtzRead", { pan: aim[0], tilt: aim[1] })}</span>}
      </div>
      <div class="rc-video-well">
        {has.includes(cam) ? <CameraWell key={`${id}:${cam}`} robot={id} cam={cam} now={now} variant="main" />
          : <div class="rc-nocam" data-nocam={cam}>{t("rcNoCam", { cam: t(cam) })}</div>}
        {ptz && (
          <div class="rc-ptz" aria-label={t("rdPtz")}>
            <button type="button" class="btn" data-ptz="up" aria-label={t("rdPtzUp")} disabled={dis} onClick={() => turn(0, -TILT_STEP)}><Arrow d="up" /></button>
            <button type="button" class="btn" data-ptz="left" aria-label={t("rdPtzLeft")} disabled={dis} onClick={() => turn(-PAN_STEP, 0)}><Arrow d="left" /></button>
            <button type="button" class="btn" data-ptz="center" disabled={dis} onClick={() => turn(0, 0)}>{t("rdPtzCenter")}</button>
            <button type="button" class="btn" data-ptz="right" aria-label={t("rdPtzRight")} disabled={dis} onClick={() => turn(PAN_STEP, 0)}><Arrow d="right" /></button>
            <button type="button" class="btn" data-ptz="down" aria-label={t("rdPtzDown")} disabled={dis} onClick={() => turn(0, TILT_STEP)}><Arrow d="down" /></button>
          </div>
        )}
        {wiper && <button type="button" class="btn rc-wiper" disabled={dis}
          onClick={() => void send(post("deter", { output: "wiper", on: true, max_s: WIPER_S }), t("rdWiperDone", { id: name, s: WIPER_S }))}>{t("rcWiper", { s: WIPER_S })}</button>}
      </div>
    </section>
  );
}

function Arrow({ d }: { d: "up" | "down" | "left" | "right" }) {
  const p = { up: "M4 10l4-4 4 4", down: "M4 6l4 4 4-4", left: "M10 4l-4 4 4 4", right: "M6 4l4 4-4 4" }[d];
  return <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true"><path d={p} fill="none" stroke="currentColor" stroke-width="2" /></svg>;
}

/** 喊话(常用话、打字 + 语言、停)和警示(警灯带时长、关、警笛、录好的话)。 */
function Voice({ r, name, busy, off, send, post, admin, say }: {
  r: RobotCard; name: string; busy: boolean; off: boolean; send: Send; post: Post; admin: boolean; say: Say;
}) {
  const d = r.deter!;
  const speaker = d.outputs.includes("speaker");
  const tts = speaker && d.tts;
  const langs = (d.tts_langs ?? ["zh"]);
  const [presets, setPresets] = useState<VoicePreset[] | null>(null);
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState("");
  const [sayLang, setSayLang] = useState(langs[0] ?? "zh");
  const [secs, setSecs] = useState(STROBE_S[0]);
  useEffect(() => {
    if (!tts) return;
    let live = true;
    api<{ presets: VoicePreset[] }>("GET", "/api/voice-presets").then((x) => live && setPresets(x.presets ?? [])).catch(() => live && setPresets(null));
    return () => { live = false; };
  }, [tts, r.robot_id]);
  useEffect(() => setText(""), [r.robot_id]);
  const deter = (body: Record<string, unknown>) => post("deter", body);
  const dis = busy || off;
  const words = text.trim();
  const strobe = d.outputs.includes("strobe");
  const siren = d.outputs.includes("siren");
  // 真机 11-20:路线开的本体灯网页关不掉(deter output=light,前 / 后 / 都)
  const light = d.outputs.includes("light");
  const [lightSide, setLightSide] = useState<"both" | "front" | "back">("both");
  return (
    <>
      {speaker && (
        <section class="rc-sec rc-voice">
          <h3 class="lbl">{t("rcAnnounce")}</h3>
          <div class="rc-voice-body">
            {tts && presets !== null && (
              <div class="rc-presets" data-voice-presets="1">
                {presets.map((p) => {
                  const cant = d.tts_langs != null && !d.tts_langs.includes(p.lang);
                  return (
                    <button key={p.lang + p.text} type="button" class="btn rc-preset" disabled={dis || cant}
                      title={cant ? t("rdPresetCantLang", { id: name, lang: langName(p.lang) }) : p.text}
                      onClick={() => void send(deter({ output: "speaker", on: true, max_s: 60, clip: `tts:${p.lang}:${p.text}` }), t("rdSpeakDone", { id: name }))}>
                      {p.text}
                    </button>
                  );
                })}
                {presets.length === 0 && <span class="muted small">{t("rdPresetsNone")}</span>}
                {admin && <button type="button" class="linkish" data-voice-edit="1" onClick={() => setEditing(true)}>{t("rcEditPresets")}</button>}
              </div>
            )}
            {editing && presets !== null && (
              <PresetEditor init={presets} onClose={() => setEditing(false)}
                onSaved={(p) => { setPresets(p); setEditing(false); say(t("rdPresetsSaved")); }} inline />
            )}
            {tts && (
              <form class="rc-say" onSubmit={(e) => {
                e.preventDefault();
                if (!words) return;
                void send(deter({ output: "speaker", on: true, max_s: 60, clip: `tts:${sayLang}:${words}` }), t("rdSpeakDone", { id: name }));
              }}>
                <select name="say_lang" aria-label={t("rcSayLang")} value={sayLang} onChange={(e) => setSayLang(e.currentTarget.value)}>
                  {langs.map((l) => <option key={l} value={l}>{langName(l)}</option>)}
                </select>
                <input name="say" aria-label={t("rdSpeakText")} placeholder={t("rcSayPh")} maxLength={300} value={text}
                  onInput={(e) => setText(e.currentTarget.value)} />
                <button type="submit" class="btn" disabled={dis || !words} title={!words ? t("rdSpeakNeedText") : undefined}>{t("rcSpeak")}</button>
                <button type="button" class="btn" disabled={dis}
                  onClick={() => void send(deter({ output: "speaker", on: false }), t("rdSpeakStopped", { id: name }))}>{t("rdSpeakStop")}</button>
              </form>
            )}
            {/* 外审 1 #5:不会 TTS 的机器人放录好的话也要能停 */}
            {!tts && d.clips.length > 0 && (
              <div class="rc-row"><button type="button" class="btn" data-speak-stop="1" disabled={dis}
                onClick={() => void send(deter({ output: "speaker", on: false }), t("rdSpeakStopped", { id: name }))}>{t("rdSpeakStop")}</button></div>
            )}
          </div>
        </section>
      )}
      {light && (
        <section class="rc-sec rc-light" data-rc-light="1">
          <h3 class="lbl">{t("rcLightH")}</h3>
          <div class="rc-deter-body">
            <select name="light_side" aria-label={t("rcLightWhich")} value={lightSide} onChange={(e) => setLightSide(e.currentTarget.value as typeof lightSide)}>
              <option value="both">{t("rcLightBoth")}</option>
              <option value="front">{t("rcLightFront")}</option>
              <option value="back">{t("rcLightBack")}</option>
            </select>
            <button type="button" class="btn" disabled={dis}
              onClick={() => void send(deter({ output: "light", on: true, max_s: d.max_s, side: lightSide }), t("rcLightOnDone", { id: name, min: Math.round(d.max_s / 60) }))}>{t("rcLightOn")}</button>
            <button type="button" class="btn" disabled={dis}
              onClick={() => void send(deter({ output: "light", on: false, side: lightSide }), t("rcLightOffDone", { id: name }))}>{t("rcOff")}</button>
          </div>
        </section>
      )}
      {(strobe || siren || (speaker && d.clips.length > 0)) && (
        <section class="rc-sec rc-deter">
          <h3 class="lbl">{t("rcDeterH")}</h3>
          <div class="rc-deter-body">
            {(strobe || siren) && (
              <select name="strobe_s" aria-label={t("rdStrobeFor")} value={String(secs)} onChange={(e) => setSecs(Number(e.currentTarget.value))}>
                {STROBE_S.filter((s) => s <= d.max_s).map((s) => <option key={s} value={String(s)}>{t("rcSecs", { s })}</option>)}
              </select>
            )}
            {strobe && <button type="button" class="btn" disabled={dis}
              onClick={() => void send(deter({ output: "strobe", on: true, max_s: secs }), t("rdStrobeOnDone", { id: name, s: secs }))}>{t("rdStrobeOn")}</button>}
            {strobe && <button type="button" class="btn" disabled={dis}
              onClick={() => void send(deter({ output: "strobe", on: false }), t("rdStrobeOffDone", { id: name }))}>{t("rcOff")}</button>}
            {siren && <button type="button" class="btn" disabled={dis}
              onClick={() => void send(deter({ output: "siren", on: true, max_s: secs }), t("rcSirenDone", { id: name, s: secs }))}>{t("rcSiren")}</button>}
            {speaker && d.clips.map((c) => (
              <button key={c} type="button" class="btn" disabled={dis}
                onClick={() => void send(deter({ output: "speaker", on: true, max_s: 60, clip: c }), t("rdSpeakDone", { id: name }))}>
                {CLIP_KEY[c] ? t(CLIP_KEY[c]) : c}
              </button>
            ))}
          </div>
        </section>
      )}
    </>
  );
}

/** 派巡逻:路线、几圈;正在跑的时候排在后面(日程优先)。路线画在别的地图版本上的不能选。 */
function Dispatch({ r, id, name, busy, off, send, busyTask, onLook }: {
  r: RobotCard; id: string; name: string; busy: boolean; off: boolean; send: Send; busyTask: boolean; onLook?: () => void;
}) {
  const [routes, setRoutes] = useState<string[] | null>(null);
  const [drawn, setDrawn] = useState<Record<string, { id: string; v: string; title?: string }>>({});
  const [pick, setPick] = useState("");
  const [loops, setLoops] = useState(1);
  useEffect(() => {
    let live = true;
    api<{ missions?: string[] }>("GET", "/api/schedule")
      .then((d) => { if (!live) return; const m = d.missions ?? []; setRoutes(m); setPick(m.length === 1 ? m[0] : ""); })
      .catch(() => live && setRoutes([]));
    api<{ routes?: { id: string; map_id?: string; map_version?: string; title?: string }[] }>("GET", "/api/routes")
      .then((d) => live && setDrawn(Object.fromEntries((d.routes ?? []).map((x) => [x.id, { id: x.map_id ?? "", v: x.map_version ?? "", title: x.title }]))))
      .catch(() => live && setDrawn({}));
    return () => { live = false; };
  }, [id]);
  const otherMap = (m: string): string | null => {
    const d = drawn[m];
    if (!d || !d.v || !r.map?.version) return null;
    if (d.id && r.map.id && d.id !== r.map.id) return `${d.id} v${d.v}`;
    return d.v === r.map.version ? null : `v${d.v}`;
  };
  const ok = !!pick && otherMap(pick) === null;
  // 站点估这一趟多久、现在走还是排在后面(老站点没有这个接口:不写)
  const [plan, setPlan] = useState<Plan | null>(null);
  useEffect(() => {
    setPlan(null);
    if (!ok) return;
    let live = true;
    api<Plan>("GET", `/api/robots/${enc(id)}/patrol-plan?mission_id=${encodeURIComponent(pick)}&loops=${loops}`)
      .then((p) => live && setPlan(p)).catch(() => {});
    return () => { live = false; };
  }, [id, pick, loops, ok]);
  const queued = plan ? !!plan.queued : busyTask;
  return (
    <section class="rc-sec rc-dispatch">
      <h3 class="lbl">{t("rcDispatchH")}</h3>
      {routes !== null && routes.length === 0 ? <p class="muted small">{t("rdNoRoutesAsk")}</p> : (
        <>
          <select name="route" aria-label={t("rdRoute")} value={ok ? pick : ""} onChange={(e) => setPick(e.currentTarget.value)}>
            <option value="">{t("rdPickRoute")}</option>
            {(routes ?? []).map((m) => <option key={m} value={m} disabled={otherMap(m) !== null}>{drawn[m]?.title || m}</option>)}
          </select>
          <div class="rc-row">
            <LoopsSelect value={loops} onChange={setLoops} />
            <button type="button" class="btn" disabled={busy || off || !ok} title={!ok ? t("rdWhyPickRoute") : undefined}
              onClick={() => void send(() => api<Reply>("POST", `/api/robots/${enc(id)}/patrol`, { mission_id: pick, loops }),
                t("rdPatrolSent", { id: name, route: drawn[pick]?.title || pick }))}>{t(queued ? "rcQueue" : "rcStart")}</button>
          </div>
          {/* W8-02 / UIUX-022(老机器人页):画在别的地图版本上的路线,原因整句写在下拉外面 */}
          {(routes ?? []).some((m) => otherMap(m) !== null) && (
            <ul class="plain small warn" data-route-why="1">
              {(routes ?? []).filter((m) => otherMap(m) !== null).map((m) => <li key={m}>{drawn[m]?.title || m} {t("rdRouteOtherMap", { at: otherMap(m) ?? "", id: name, v: `v${r.map?.version ?? ""}` })}</li>)}
            </ul>
          )}
          {plan && (
            <p class="muted small" data-plan="1">
              {plan.forever ? (plan.return_pct != null ? t("doForeverPct", { n: plan.return_pct }) : t("doForever"))
                : [plan.estimate_s != null ? t("doEta", { m: Math.max(1, Math.round(plan.estimate_s / 60)) }) : "",
                  plan.queued ? t("doQueued", { at: siteHm(plan.start_ms ?? 0, plan.utc_offset_min), why: plan.because ?? "" }) : t("doNow")].filter(Boolean).join(" · ")}
            </p>
          )}
          {!plan && busyTask && <p class="muted small">{t("rcQueueHint")}</p>}
        </>
      )}
      {onLook && <button type="button" class="btn rc-look" onClick={onLook}>{t("rcSpotCheck")}</button>}
    </section>
  );
}
