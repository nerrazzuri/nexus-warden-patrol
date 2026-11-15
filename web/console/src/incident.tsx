// 值班页的「这件事」(redesign 第二轮 V4-alarm 稿):有告警时值班页中间换成这一件 —— 页头(标识、标题、哪儿几点、
// 接手)、进度条(发现 / 接手 / 派出 / 到场 / 关闭)、画面(现场摄像头 + 机器人)和这一片的地图、三组操作
// (派机器人 / 现场警示 / 通知)、结论和这件事的经过。原来的报警详情弹窗(AlertDetail)在值班页不再用:不弹窗,
// 同一个页框里切换。只读账号看得到进度(谁在处理、哪台机器人、结论),没有操作。
import { useEffect, useState } from "preact/hooks";
import { hms, incidentLog, REOPEN_MS, verdictsFor } from "./alertdetail";
import { alertAdvice, alertHeadline, canHandleAlerts } from "./alertinfo";
import { api, ApiError, enc } from "./api";
import { CameraWell, camLabel } from "./camera";
import { hm, nameOf } from "./data";
import { lang, t, type Key } from "./i18n";
import type { UnitInfo } from "./live";
import { LiveWall } from "./livewall";
import type { CanvasArea } from "./mapcanvas";
import { GoLookCard, MapPage, verdictText } from "./mappage";
import { autoResolved, canDispatch, robotCams, type Alert, type Mode } from "./model";
import { Sign, type VideoLayout } from "./signs";
import { NAV_FAIL_CODES } from "./navcodes.g";
import { recordingLink } from "./recordings";
import { pageAllowed } from "./shell";
import { isSecurity } from "./shifttl";
import { byText, SiteSpan } from "./sitetext";

/** 要先到场才能关的(站点 alert_store.ARRIVAL_KINDS)。 */
const ARRIVE = new Set(["dog_sees_person"]);
const LOST = new Set(["loc_lost_paused", "loc_lost_idle"]);
type Verdict = "intruder" | "false_alarm" | "handled";
const VKEY: Record<Verdict, Key> = { intruder: "incVIntruder", false_alarm: "incVFalse", handled: "incVHandled" };

export interface FixedCam { name: string; zone: string }
type Step = { key: Key; at: number | null; who?: string };

/** 这件事走到哪一步:发现 → 接手 → 派出(安全事件) → 到场(要到场的那类) → 关闭。 */
export function incidentSteps(a: Alert): Step[] {
  const steps: Step[] = [{ key: "incDetected", at: a.first_ms }];
  steps.push({ key: "incAssigned", at: a.acked_ms, who: a.acked_by ? byText(a.acked_by) : undefined });
  if (isSecurity(a)) {
    const robot = a.robot && a.robot !== "site" && !a.robot.includes(":");
    steps.push({ key: "incDispatched", at: robot ? a.first_ms : null, who: robot ? nameOf(a.robot) : undefined });
  }
  if (ARRIVE.has(a.kind)) steps.push({ key: "incOnSite", at: a.context?.arrived_ms ?? null, who: a.context?.arrived_by });
  steps.push({ key: "incClosed", at: a.resolved_ms, who: a.resolved_ms != null ? verdictText(a) : undefined });
  return steps;
}

/** 报警点(看见人的取最后看见的位置,其余取机器人报的位置)。 */
export function alarmPoint(a: Alert): { map_id: string; map_version: string; x: number; y: number } | null {
  return a.context?.last_seen ?? a.context?.pose ?? null;
}

/** 哪台机器人管这件事:告警记在它名下的那台;站点名下的(没机器人去)取离报警点最近、在线的那台。 */
export function responder(a: Alert, units: UnitInfo[]): { u: UnitInfo; dist: number | null } | null {
  const p = alarmPoint(a);
  const dist = (u: UnitInfo) => {
    const q = u.robot.loc?.pose;
    return p && q ? Math.hypot(q.x - p.x, q.y - p.y) : null;
  };
  const own = units.find((u) => u.robot.robot_id === a.robot);
  if (own) return { u: own, dist: dist(own) };
  const near = units.filter((u) => u.state !== "offline" && dist(u) != null).sort((x, y) => dist(x)! - dist(y)!)[0];
  return near ? { u: near, dist: dist(near) } : null;
}

export function IncidentView(props: {
  a: Alert;
  units: UnitInfo[];
  alerts: Alert[];
  now: number;
  role: string;
  mode: Mode | null;
  stale?: boolean;
  cams: FixedCam[];
  layout: VideoLayout;
  onLayout: (l: VideoLayout) => void;
  say: (s: string) => void;
  refresh: () => Promise<void>;
  onSite: () => void;
  onZoom: (robot: string) => void;
  onFindPose: (robot: string) => void;
  onAreas?: (a: CanvasArea[]) => void;
}) {
  const a = props.a;
  const [verdict, setVerdict] = useState<Verdict | null>(null);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [sending, setSending] = useState(false);
  useEffect(() => { setVerdict(null); setNote(""); setErr(""); setSending(false); }, [a.key]);

  const open = a.resolved_ms == null;
  const can = canHandleAlerts(props.role);
  const dispatch = canDispatch(props.role);
  const mustArrive = ARRIVE.has(a.kind) && a.context?.arrived_ms == null;
  const site = a.robot === "site" || a.robot.includes(":");
  const sec = isSecurity(a);
  const where = a.context?.zone ?? a.context?.person?.where ?? a.context?.where ?? "";
  const point = alarmPoint(a);
  const resp = responder(a, props.units);
  const rid = resp?.u.robot.robot_id ?? "";
  const scene = sec && a.context?.zone ? props.cams.find((c) => c.zone === a.context?.zone) : undefined;
  const deter = (resp?.u.robot.capabilities?.tasks?.deter ?? null) as { outputs?: string[]; clips?: string[]; tts?: boolean } | null;
  const code = (a.context as { code?: unknown } | undefined)?.code;
  const navCode = typeof code === "string" && Object.hasOwn(NAV_FAIL_CODES, code) ? [code, NAV_FAIL_CODES[code]] as const : null;
  const advice = alertAdvice(a);

  async function post(action: string, body: unknown) {
    setBusy(true);
    setErr("");
    try {
      await api("POST", `/api/alerts/${enc(a.key)}/${action}`, body);
      if (action === "resolve") props.say(t("incClosedUndo", { t: hm(Date.now() + REOPEN_MS) }));
      if (action === "reopen") props.say(t("incReopened"));
      if (action === "backup") props.say(t("incBackupSent"));
      await props.refresh();
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) { props.say(t("incGone")); await props.refresh(); props.onSite(); }
      else setErr(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }
  async function deterSend(body: Record<string, unknown>, ok: string) {
    try {
      await api("POST", `/api/robots/${enc(rid)}/deter`, body);
      props.say(ok);
    } catch (e) {
      props.say(t("failed", { why: e instanceof ApiError ? e.message : String(e) }));
    }
  }

  // ---- 页头 ----
  const sub = [a.level, t(sec ? "incSecurity" : "incEquipment"), where, scene?.name ?? "", hms(a.first_ms),
    a.context?.follow === "follow" ? t("dutyFollowing") : a.context?.lost_ms != null ? t("dutyLost") : "",
    a.context?.exit ? t("incExit", { exit: a.context.exit }) : "", site ? "" : nameOf(a.robot)].filter(Boolean).join(" · ");
  let primary: preact.ComponentChildren = null;
  if (open && can && a.acked_ms == null) {
    primary = <button type="button" class="btn primary" disabled={busy} onClick={() => void post("ack", {})}>{t("incTake")}</button>;
  } else if (open && can && mustArrive) {
    primary = <button type="button" class="btn primary" disabled={busy} onClick={() => void post("arrive", {})}>{t("incArrive")}</button>;
  } else if (open && a.acked_by) {
    primary = <span class="inc-owner"><Sign kind="info" />{t("incHandling", { who: byText(a.acked_by) })}</span>;
  }
  // 迷路了:协助定位(接手前后都在;接手前主按钮是「接手」,它是普通按钮)
  const findPose = open && can && LOST.has(a.kind)
    ? <button type="button" class={a.acked_ms != null ? "btn primary" : "btn"} onClick={() => props.onFindPose(a.robot)}>{t("dutyFindPose")}</button> : null;

  // ---- 画面 ----
  const tiles: { key: string; label: string; el: preact.ComponentChildren }[] = [];
  if (scene) {
    const feed = { label: scene.name, src: `/api/cameras/${enc(scene.name)}/live`, health: `/api/cameras/${enc(scene.name)}/health` };
    tiles.push({ key: `c:${scene.name}`, label: t("incSceneCam", { cam: scene.name, zone: where }),
      el: <CameraWell robot={scene.name} cam="front" now={props.now} variant="main" forceLive feed={feed} /> });
  }
  if (resp) {
    const dist = awayText(resp.dist, where) ? ` · ${awayText(resp.dist, where)}` : "";
    tiles.push({ key: `r:${rid}`, label: `${camLabel(rid, "front")}${dist}`,
      el: <CameraWell robot={rid} cam="front" now={props.now} variant="main" forceLive onOpen={() => props.onZoom(rid)} /> });
    if (robotCams(resp.u.robot).includes("thermal")) {
      tiles.push({ key: `t:${rid}`, label: camLabel(rid, "thermal"), el: <CameraWell robot={rid} cam="thermal" now={props.now} variant="main" forceLive /> });
    }
  }
  for (const u of props.units) {
    if (u.robot.robot_id !== rid && u.state !== "offline") {
      tiles.push({ key: `r:${u.robot.robot_id}`, label: camLabel(u.robot.robot_id, "front"),
        el: <CameraWell robot={u.robot.robot_id} cam="front" now={props.now} variant="main" onOpen={() => props.onZoom(u.robot.robot_id)} /> });
    }
  }
  const n = props.layout === "single" ? 1 : props.layout === "dual" ? 2 : 4;
  const layouts: { v: VideoLayout; key: Key }[] = [{ v: "single", key: "monSingle" }, { v: "dual", key: "monDual" }, { v: "quad", key: "monQuad" }, { v: "wall", key: "monWall" }];

  // ---- 三组操作 ----
  const nameR = rid ? nameOf(rid) : "";
  const battery = resp?.u.battery != null ? Math.round(resp.u.battery) : null;
  const strobe = deter?.outputs?.includes("strobe") ?? false;
  const speaker = (deter?.outputs?.includes("speaker") ?? false) && ((deter?.clips?.length ?? 0) > 0 || deter?.tts === true);
  const warnClip = deter?.clips?.includes("restricted") ? "restricted" : deter?.clips?.[0] ?? `tts:${lang.value === "zh" ? "zh" : "en"}:${t("incWarnWords")}`;
  const groups: preact.ComponentChildren[] = [];
  if (open && point) {
    groups.push(
      <section key="d" class="inc-act" aria-label={t("incDispatchH")}>
        <h3 class="lbl">{t("incDispatchH")}</h3>
        {dispatch ? (
          sending ? (
            <GoLookCard canFix={pageAllowed("admin/localization", props.role)} map={{ map_id: point.map_id, version: point.map_version }}
              at={[point.x, point.y]} units={props.units} onClose={() => setSending(false)} say={props.say}
              exclude={a.audience === "help" && a.robot && a.robot !== "site" ? a.robot : undefined} />
          ) : (
            <button type="button" class="btn" onClick={() => setSending(true)}>{where ? t("incDispatchTo", { where }) : t("incDispatch")}</button>
          )
        ) : <p class="inc-state">{resp ? t("incResponder", { id: nameR }) : t("incNoResponder")}</p>}
        <p class="inc-note">{[nameR && battery != null ? t("incBattery", { id: nameR, p: battery }) : "",
          resp?.dist != null && resp.dist >= 1 ? t("incDist", { m: Math.round(resp.dist) }) : ""].filter(Boolean).join(" · ")}</p>
      </section>,
    );
  }
  if (open && sec && resp && (strobe || speaker)) {
    groups.push(
      <section key="w" class="inc-act" aria-label={t("incDeterH", { id: nameR })}>
        <h3 class="lbl">{t("incDeterH", { id: nameR })}</h3>
        {dispatch ? (
          <div class="inc-btns">
            {speaker && <button type="button" class="btn" onClick={() => void deterSend({ output: "speaker", on: true, max_s: 60, clip: warnClip }, t("rdSpeakDone", { id: nameR }))}>{t("incAnnounce")}</button>}
            {strobe && <button type="button" class="btn" onClick={() => void deterSend({ output: "strobe", on: true, max_s: 30 }, t("rdStrobeOnDone", { id: nameR, s: 30 }))}>{t("incStrobe")}</button>}
          </div>
        ) : <p class="inc-state">{t("incDeterNotYours")}</p>}
        <p class="inc-note">{t("incDeterHint", { id: nameR })}</p>
      </section>,
    );
  }
  if (open) {
    groups.push(
      <section key="n" class="inc-act" aria-label={t("incNotifyH")}>
        <h3 class="lbl">{t("incNotifyH")}</h3>
        <p class="inc-state">{t(a.level === "P1" ? "incPushedP1" : "incPushedP2")}</p>
        <p class="inc-note">{t("incPushHint")}</p>
        {/* 第 8 期:请求支援 —— 站点给经理、管理员推一条,这里记下谁几点叫的 */}
        {a.context?.backup_by ? <p class="inc-state" data-backup-done="1">{t("incBackupDone", { who: String(a.context.backup_by), t: hm(Number(a.context.backup_ms ?? a.last_ms)) })}</p>
          : can && <button type="button" class="btn" data-backup="1" disabled={busy} onClick={() => void post("backup", {})}>{t("incBackup")}</button>}
      </section>,
    );
  }

  // ---- 经过 ----
  const log = incidentLog(a);

  return (
    <div class="inc" data-key={a.key} data-level={a.level}>
      <header class={`inc-head ${a.level === "P1" ? "p1" : "p2"}`}>
        <Sign kind={a.level === "P1" ? "bad" : "warn"} />
        <div class="inc-head-text">
          <h1>{alertHeadline(a)}</h1>
          <p title={sub}>{sub}</p>
        </div>
        <div class="inc-head-acts">{findPose}{findPose && a.acked_ms != null ? null : primary}</div>
      </header>
      <ol class="inc-steps" aria-label={t("incProgress")}>
        {incidentSteps(a).map((s) => (
          <li key={s.key} class={s.at != null ? "done" : ""} data-step={s.key}>
            {s.at != null ? <Sign kind="ok" /> : <i class="sign idle" aria-hidden="true" />}
            <span>{t(s.key)}{s.at != null && s.key === "incDetected" ? ` ${hm(s.at)}` : ""}</span>
            {s.who && <small>{s.who}</small>}
          </li>
        ))}
      </ol>
      {props.layout === "wall" ? (
        <div class="inc-wall">
          <div class="mon-video-h">
            <LayoutSeg layouts={layouts} v={props.layout} on={props.onLayout} />
            <span class="push" />
            {!site && <a class="btn" href={recordingLink(a)}>{t("incReplay")}</a>}
            <button type="button" class="btn" onClick={props.onSite}>{t("incSiteMap")}</button>
          </div>
          <LiveWall units={props.units} alerts={props.alerts} now={props.now} onZoom={props.onZoom} />
        </div>
      ) : (
        <div class="inc-body">
          <section class="inc-video" aria-label={t("monVideo")}>
            <div class="mon-video-h">
              <LayoutSeg layouts={layouts} v={props.layout} on={props.onLayout} />
              <span class="push" />
              {!site && <a class="btn" href={recordingLink(a)}>{t("incReplay")}</a>}
            </div>
            <div class={`mon-tiles ${props.layout}`}>
              {tiles.length === 0 && <p class="muted">{t("incNoVideo")}</p>}
              {tiles.slice(0, n).map((x) => <figure key={x.key} class="mon-tile"><figcaption>{x.label}</figcaption>{x.el}</figure>)}
            </div>
          </section>
          <section class="inc-map" aria-label={t("tabMap")}>
            <div class="inc-map-h">
              <b>{where || t("incAlarmPoint")}</b>
              {resp?.dist != null && resp.dist >= 1 && <span class="muted">{t("incAwayShort", { id: nameR, m: Math.round(resp.dist) })}</span>}
            </div>
            <div class="mon-map">
              <MapPage units={props.units} p1={a.level === "P1" ? [a] : []} now={props.now} role={props.role} stale={props.stale}
                selected={rid || null} onSelect={() => {}} mode={props.mode} say={props.say} preset="all" tool={null} recent={[a]}
                hot={new Set(a.context?.zone ? [a.context.zone] : [])} onAreas={props.onAreas} />
            </div>
            <div class="inc-map-f"><button type="button" class="btn" onClick={props.onSite}>{t("incSiteMap")}</button></div>
          </section>
        </div>
      )}
      {groups.length > 0 && <div class="inc-acts" data-n={groups.length}>{groups}</div>}
      {(advice || navCode || a.detail) && (
        <details class="inc-more">
          <summary>{t("incMore")}</summary>
          {advice && <p><b>{t("incWhatToDo")}</b> {advice}</p>}
          {navCode && <p data-nav-code={navCode[0]}>{navCode[1][lang.value === "zh" ? 1 : 0]} {navCode[1][lang.value === "zh" ? 3 : 2]}</p>}
          {a.detail && <p class="small"><SiteSpan s={a.detail} /></p>}
        </details>
      )}
      <footer class="inc-foot">
        <div class="inc-disp">
          <span class="lbl">{t("incDisposition")}</span>
          {open && can && !mustArrive && (
            <>
              <div class="seg" role="group" aria-label={t("incDisposition")}>
                {verdictsFor(a).map((v) => <button key={v} type="button" aria-pressed={verdict === v} onClick={() => setVerdict(v)}>{t(VKEY[v])}</button>)}
              </div>
              {verdict && <input class="inc-noteinput" value={note} maxLength={200} placeholder={t("incNoteHint")} aria-label={t("incNote")} onInput={(e) => setNote(e.currentTarget.value)} />}
              <button type="button" class={verdict ? "btn primary" : "btn"} disabled={busy || verdict == null}
                onClick={() => verdict && void post("resolve", { verdict, note: note.trim() })}>{t("incClose")}</button>
            </>
          )}
          {open && can && mustArrive && <span class="inc-state">{t("dutyArriveFirst")}</span>}
          {open && !can && <span class="inc-state">{a.acked_by ? t("incHandling", { who: byText(a.acked_by) }) : t("monUnassigned")}{resp ? ` · ${t("incResponder", { id: nameR })}` : ""} · {t("incNoVerdict")}</span>}
          {!open && (
            <>
              <span class="inc-state">{t("dClosedLine", { v: verdictText(a), who: byText(a.resolved_by) || "—", t: a.resolved_ms ? hm(a.resolved_ms) : "" })}</span>
              {can && a.resolved_ms != null && props.now - a.resolved_ms < REOPEN_MS && !autoResolved(a) && (
                <button type="button" class="btn" disabled={busy} onClick={() => void post("reopen", {})}>{t("incReopen")}</button>
              )}
            </>
          )}
        </div>
        <ol class="inc-log" aria-label={t("incTimeline")}>
          {log.map((x, i) => <li key={i}><time class="mono">{hms(x.at)}</time> {x.text}</li>)}
        </ol>
        {err && <p class="error" role="alert">{err}</p>}
      </footer>
    </div>
  );
}

/** 「离北门 48 米」:没地名写「离报警点」;不到 1 米(就是它自己看见的)不写。 */
export function awayText(dist: number | null | undefined, where: string): string {
  if (dist == null || dist < 1) return "";
  return where ? t("incAway", { m: Math.round(dist), where }) : t("incAwayPoint", { m: Math.round(dist) });
}

function LayoutSeg({ layouts, v, on }: { layouts: { v: VideoLayout; key: Key }[]; v: VideoLayout; on: (l: VideoLayout) => void }) {
  return (
    <div class="seg" role="tablist" aria-label={t("monVideo")}>
      {layouts.map((l) => <button key={l.v} type="button" role="tab" aria-selected={v === l.v} class={v === l.v ? "on" : ""} onClick={() => on(l.v)}>{t(l.key)}</button>)}
    </div>
  );
}

