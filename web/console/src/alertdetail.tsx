// 报警记录页右栏的这一条(redesign 第五期 G-records;原来是弹窗 AlertDetail):标题、几点 / 在哪 / 结论,
// 那一刻的录像(前后两路切换、导出片段、去录像页)、该做什么、经过;10 分钟内能重新打开。
// 处理(接手、派机器人、下结论)在值班页的「这件事」里做 —— 没关的这里给「去处理」跳过去。只读账号只看。
import { useEffect, useRef, useState } from "preact/hooks";
import { alertAdvice, alertHeadline, canHandleAlerts } from "./alertinfo";
import { api, ApiError, enc } from "./api";
import { hm, nameOf } from "./data";
import { lang, t, type Key } from "./i18n";
import { verdictText } from "./mappage";
import { autoResolved, type Alert } from "./model";
import { NAV_FAIL_CODES } from "./navcodes.g";
import { ascending, recordingLink, segmentAt, type Recording } from "./recordings";
import { byText, SiteSpan, siteText } from "./sitetext";

/** 处理后这么久内能撤销(站点 alerts.REOPEN_MS)。 */
export const REOPEN_MS = 10 * 60_000;

/** 提示条上的一个按钮(第 2 轮 duty N8)。 */
export interface ToastAction { label: string; run: () => void }

type Verdict = "intruder" | "false_alarm" | "handled";

/** 这种警报能选哪些结论:有人闯入类三种都有,其余是「处理好了 / 误报」。 */
export function verdictsFor(a: Alert): Verdict[] {
  return a.audience === "intrusion" || a.audience === "fire" ? ["intruder", "false_alarm", "handled"] : ["handled", "false_alarm"];
}

/** 这条报警有没有机器人录像可看(摄像头、站点自己的报警没有)。 */
export function hasRecording(a: { robot: string; kind: string }): boolean {
  return a.robot !== "site" && !a.robot.startsWith("cctv:") && a.kind !== "cctv_offline";
}

/** 这件事的经过(值班页「这件事」、报警记录页、回放共用):发现、重复、接手、到场、跟丢、关闭。 */
export function incidentLog(a: Alert): { at: number; text: string }[] {
  const log: { at: number; text: string }[] = [{ at: a.first_ms, text: alertHeadline(a) }];
  if (a.count > 1) log.push({ at: a.last_ms, text: t("incRepeat", { n: a.count }) });
  if (a.acked_ms != null && a.acked_by) log.push({ at: a.acked_ms, text: t("actTook", { who: byText(a.acked_by), what: "" }).replace(/[:：]\s*$/, "") });
  if (a.context?.arrived_ms != null) log.push({ at: a.context.arrived_ms, text: t("incArrivedBy", { who: byText(a.context.arrived_by) || "—" }) });
  if (a.context?.lost_ms != null) log.push({ at: a.context.lost_ms, text: t("dutyLost") });
  // 易用性 37 场景测试:喊话、警灯、警笛也进经过
  for (const w of a.context?.warnings ?? []) {
    if (typeof w?.at_ms !== "number") continue;
    const k: Key = w.output === "speaker" ? "incWarnSpeak" : w.output === "strobe" ? "incWarnStrobe" : w.output === "siren" ? "incWarnSiren" : "incWarnOther";
    log.push({ at: w.at_ms, text: t(k, { who: byText(w.by), o: w.output }) });
  }
  if (a.resolved_ms != null) {
    const note = (a.context as { note?: string } | undefined)?.note;
    log.push({ at: a.resolved_ms, text: `${t("incClosed")} · ${verdictText(a)}${a.resolved_by ? ` · ${byText(a.resolved_by)}` : ""}${note ? ` · “${siteText(note).text}”` : ""}` });
  }
  return log.sort((x, y) => x.at - y.at);
}

/** 「22:05:14」。 */
export function hms(ms: number): string {
  const d = new Date(ms);
  const p = (n: number) => String(n).padStart(2, "0");
  return `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}

/** 位置一栏:防区 / 地点,摄像头报警加摄像头名。 */
export function placeOf(a: Alert): string {
  const cam = a.robot.startsWith("cctv:") ? a.robot.slice(5) : "";
  return [a.context?.zone ?? a.context?.where ?? "", cam].filter(Boolean).join(" · ");
}

export function EventPanel(props: {
  a: Alert;
  role: string;
  now: number;
  refresh: () => Promise<void>;
  say: (s: string, act?: ToastAction) => void;
}) {
  const a = props.a;
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  useEffect(() => setErr(""), [a.key]);
  const open = a.resolved_ms == null;
  const can = canHandleAlerts(props.role);
  const code = (a.context as { code?: unknown } | undefined)?.code;
  const navCode = typeof code === "string" && Object.hasOwn(NAV_FAIL_CODES, code) ? [code, NAV_FAIL_CODES[code]] as const : null;
  const advice = alertAdvice(a);
  const place = placeOf(a);
  const reopenBy = a.resolved_ms != null ? a.resolved_ms + REOPEN_MS : 0;
  const canReopen = !open && can && props.now < reopenBy && !autoResolved(a);

  async function reopen() {
    setBusy(true);
    setErr("");
    try {
      await api("POST", `/api/alerts/${enc(a.key)}/reopen`, {});
      props.say(t("incReopened"));
      await props.refresh();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  const status = open
    ? (a.acked_by ? t("evOpenSub", { who: t("dutyTakenBy", { who: byText(a.acked_by) }) }) : t("evOpenNobody"))
    : autoResolved(a) ? t("evAutoRecovered")
      : t("evClosedSub", { v: verdictText(a) || t("monResolved"), who: byText(a.resolved_by) || "—", t: a.resolved_ms ? hm(a.resolved_ms) : "" });
  const errCode = (a.context as { err?: unknown } | undefined)?.err;
  return (
    <div class="evp" data-key={a.key}>
      <header class="evp-head">
        <h2>{alertHeadline(a)}</h2>
        <p>
          {[hms(a.first_ms), place, a.robot !== "site" && !a.robot.includes(":") ? nameOf(a.robot) : ""].filter(Boolean).join(" · ")}
          {!place && a.context?.pose && <> · <a href={`#/duty?alarm=${encodeURIComponent(a.key)}`} data-where-map="1">{t("evOnMap")}</a></>}
          {" · "}{status}
        </p>
        {typeof errCode === "string" && <p class="mono small" data-err="1">{t("errCodeLabel", { c: errCode })}</p>}
      </header>
      {hasRecording(a) ? <EvPlayer a={a} role={props.role} /> : <p class="evp-norec muted">{t("evNoRec")}</p>}
      {(open && can || canReopen) && (
        <div class="evp-acts">
          {open && can && <a class="btn primary" href={`#/duty?alarm=${encodeURIComponent(a.key)}`} data-respond="1">{t("evRespond")}</a>}
          {canReopen && <button type="button" class="btn" disabled={busy} onClick={() => void reopen()}>{t("evReopenUntil", { t: hm(reopenBy) })}</button>}
        </div>
      )}
      {!can && <p class="muted small">{t("evReadOnly")}</p>}
      {err && <p class="error" role="alert">{err}</p>}
      <section class="evp-sec">
        <h3>{t("evTimeline")}</h3>
        <ol class="evp-log">
          {incidentLog(a).map((x, i) => <li key={i}><time class="mono">{hms(x.at)}</time><span>{x.text}</span></li>)}
        </ol>
      </section>
      {advice && <section class="evp-sec ad-do"><h3>{t("incWhatToDo")}</h3><p>{advice}</p></section>}
      {/* 导航 V1 第 5 节:机器人报了认得的原因码 → 写「怎么回事 + 该做什么」(跟手机同一份码表) */}
      {navCode && (
        <section class="evp-sec ad-navcode" data-nav-code={navCode[0]}>
          <h3>{lang.value === "zh" ? "原因" : "Why"}</h3>
          <p class="small">{navCode[1][lang.value === "zh" ? 1 : 0]}</p>
          <p class="small"><b>{lang.value === "zh" ? "该做什么：" : "What to do: "}</b>{navCode[1][lang.value === "zh" ? 3 : 2]}</p>
          {/* 易用性第 6 轮 W6-10:原因码给工程师看,收在技术详情里 */}
          <details class="techdetail"><summary>{lang.value === "zh" ? "技术详情" : "Technical details"}</summary><p class="small mono">{navCode[0]}</p></details>
        </section>
      )}
      {a.detail && (
        <section class="evp-sec ad-site">
          <h3>{t("incMore")}</h3>
          <p class="small"><SiteSpan s={a.detail} /></p>
          {siteText(a.detail).raw && <details class="techdetail"><summary>{lang.value === "zh" ? "技术详情" : "Technical details"}</summary><p class="small mono">{a.detail}</p></details>}
        </section>
      )}
    </div>
  );
}

/** 那一刻的录像:报警前 2 分钟到关闭后 1 分钟(最多 15 分钟)一条刻度,点哪放哪;前 / 后两路换着看。 */
function EvPlayer({ a, role }: { a: Alert; role: string }) {
  const [cam, setCam] = useState<"front" | "back">("front");
  const [rows, setRows] = useState<Recording[] | null>(null);
  const [segS, setSegS] = useState(60);
  const [head, setHead] = useState(a.first_ms);
  const [cur, setCur] = useState<{ rec: Recording; offsetS: number } | null>(null);
  const [paused, setPaused] = useState(true);
  const video = useRef<HTMLVideoElement>(null);
  const from = a.first_ms - 2 * 60_000;
  const to = Math.min(Math.max(a.resolved_ms ?? a.last_ms, a.first_ms) + 60_000, a.first_ms + 15 * 60_000);
  useEffect(() => { setCam("front"); setHead(a.first_ms); }, [a.key]);
  useEffect(() => {
    let live = true;
    setRows(null);
    setCur(null);
    api<{ recordings: Recording[]; segment_s?: number }>("GET",
      `/api/recordings?robot=${enc(a.robot)}&camera=${cam}&since=${from - 10 * 60_000}&until=${to}&limit=100`)
      .then((d) => {
        if (!live) return;
        const asc = ascending(d.recordings ?? []);
        const s = d.segment_s ?? 60;
        setSegS(s);
        setRows(asc);
        setCur(segmentAt(asc, head, s));
      })
      .catch(() => live && setRows([]));
    return () => { live = false; };
  }, [a.key, cam]);
  const seek = (ms: number) => {
    setHead(ms);
    const hit = rows ? segmentAt(rows, ms, segS) : null;
    if (hit && cur && hit.rec.id === cur.rec.id && video.current) {
      try { video.current.currentTime = hit.offsetS; } catch { /* 还没载入 */ }
    } else setCur(hit);
  };
  const other = cam === "front" ? "back" : "front";
  const pct = (ms: number) => Math.min(100, Math.max(0, ((ms - from) / (to - from)) * 100));
  return (
    <div class="evp-player">
      <div class="evp-well">
        <span class="evp-cam">{`${nameOf(a.robot)} ${t(cam)}`}</span>
        <span class="evp-tag">{t("evRecording", { t: hms(head) })}</span>
        {cur ? (
          <video ref={video} key={cur.rec.id} src={`/api/recordings/${cur.rec.id}/video`} playsInline muted
            aria-label={`${nameOf(a.robot)} ${t(cam)}`}
            onLoadedMetadata={(e) => { const v = e.currentTarget as HTMLVideoElement; try { v.currentTime = cur.offsetS; } catch { /* */ } }}
            onPlay={() => setPaused(false)} onPause={() => setPaused(true)}
            onTimeUpdate={(e) => setHead(cur.rec.start_ms + (e.currentTarget as HTMLVideoElement).currentTime * 1000)} />
        ) : <p class="evp-empty muted">{rows == null ? t("loading") : t("evRecNone")}</p>}
      </div>
      <div class="evp-scrub" role="slider" aria-label={t("evTimeline")} aria-valuemin={from} aria-valuemax={to} aria-valuenow={head} tabIndex={0}
        onClick={(e) => { const b = (e.currentTarget as Element).getBoundingClientRect(); if (b.width > 0) seek(from + ((e.clientX - b.left) / b.width) * (to - from)); }}
        onKeyDown={(e) => { if (e.key === "ArrowLeft") seek(Math.max(from, head - 10_000)); if (e.key === "ArrowRight") seek(Math.min(to, head + 10_000)); }}>
        <span class="mono">{hm(from)}</span>
        {(rows ?? []).filter((r) => r.start_ms < to && r.start_ms + segS * 1000 > from).map((r) => (
          <i key={r.id} class="evp-have" style={{ left: `${pct(r.start_ms)}%`, width: `${pct(r.start_ms + segS * 1000) - pct(r.start_ms)}%` }} />
        ))}
        <b class="evp-mark" style={{ left: `${pct(head)}%` }} />
        <span class="mono">{hm(to)}</span>
      </div>
      <div class="evp-btns">
        <button type="button" class="btn" disabled={!cur} onClick={() => { const v = video.current; if (v) { if (v.paused) void v.play().catch(() => {}); else v.pause(); } }}>
          {t(paused ? "evPlay" : "evPause")}
        </button>
        <button type="button" class="btn" data-other-cam="1" onClick={() => setCam(other)}>{t("evOtherCam", { cam: t(other) })}</button>
        {(role === "admin" || role === "engineer")
          ? <a class="btn" href={`/api/recordings/clip?robot=${enc(a.robot)}&camera=${cam}&since=${Math.floor(from)}&until=${Math.floor(to)}`}>{t("evExportClip")}</a>
          : <a class="btn" href={recordingLink(a)}>{t("evFullRec")}</a>}
      </div>
    </div>
  );
}
