// 值班页回放(redesign 第五期 G-playback):点左栏「本班已关闭」的一件,或点底下时间轴某一刻,中间换成那一刻的录像 ——
// 上面黄条写「回放 · 22:05:14」、这是多久以前的、不是实时画面,「回到实时」是唯一的主按钮;
// 左 画面(单 / 双 / 四:这台的前后两路;四 = 两台各两路)+ 倍速、±10 秒、暂停、截图、导出片段(管理员)、跳到几点、保留这一段(值班的人);
// 右 那一刻机器人在哪(轨迹前后)。右栏的机器人一直是实时状态,这件事的经过加在右栏;时间轴上黄线是回放位置。
import { useEffect, useRef, useState } from "preact/hooks";
import { alertHeadline } from "./alertinfo";
import { api, enc } from "./api";
import { hm, nameOf } from "./data";
import { t, type Key } from "./i18n";
import { verdictText } from "./mappage";
import { autoResolved, type Alert } from "./model";
import { ascending, clockSeconds, dateInput, dayRange, nextSegment, segmentAt, type Recording, type TrackPt } from "./recordings";
import { canExport, canReview, fileStamp, RecMap } from "./recpage";
import { hms } from "./alertdetail";

export interface Playback { key: string | null; robot: string; at: number }
type PbLayout = "single" | "dual" | "quad";
const SPEEDS = [0.5, 1, 2, 4];
const HOUR = 3_600_000;

/** 「1 小时 35 分钟」。 */
export function agoText(ms: number): string {
  const m = Math.max(0, Math.floor(ms / 60_000));
  return m >= 60 ? t("pbAgoH", { h: Math.floor(m / 60), m: m % 60 }) : t("pbAgoM", { m });
}

/** 这件事回放看哪台:机器人报的就是它;摄像头 / 站点报的看第一台。 */
export function playRobot(a: Alert, robots: string[]): string {
  return a.robot !== "site" && !a.robot.includes(":") ? a.robot : robots[0] ?? "";
}

/** 一路录像(按小时一桶拉前后几小时)。 */
function useRecs(robot: string, cam: string, at: number): { rows: Recording[] | null; segS: number } {
  const bucket = Math.floor(at / HOUR);
  const [got, setGot] = useState<{ key: string; rows: Recording[]; segS: number } | null>(null);
  const key = `${robot}/${cam}/${bucket}`;
  useEffect(() => {
    if (!robot) return;
    let live = true;
    api<{ recordings: Recording[]; segment_s?: number }>("GET",
      `/api/recordings?robot=${enc(robot)}&camera=${cam}&since=${(bucket - 2) * HOUR}&until=${(bucket + 3) * HOUR}&limit=2000`)
      .then((d) => live && setGot({ key, rows: ascending(d.recordings ?? []), segS: d.segment_s ?? 60 }))
      .catch(() => live && setGot({ key, rows: [], segS: 60 }));
    return () => { live = false; };
  }, [key]);
  return got && got.key === key ? { rows: got.rows, segS: got.segS } : { rows: null, segS: 60 };
}

export function PlaybackView(props: {
  play: Playback;
  alert: Alert | null;
  robots: string[];
  role: string;
  now: number;
  say: (s: string) => void;
  /** 回放位置变了(时间轴上的黄线跟着)。 */
  onHead: (ms: number) => void;
  onLive: () => void;
}) {
  const a = props.alert;
  const [robot, setRobot] = useState(props.play.robot);
  const [head, setHeadRaw] = useState(props.play.at);
  const [gen, setGen] = useState(0);
  const [playing, setPlaying] = useState(true);
  const [speed, setSpeed] = useState(1);
  const [layoutRaw, setLayout] = useState<PbLayout>("dual");
  // 用户 11-15:只有一台机器人 = 前、后两路分开放,不给单 / 双 / 四画面的选择
  const layout: PbLayout = props.robots.length <= 1 ? "dual" : layoutRaw;
  const [goto, setGoto] = useState("");
  const [gotoBad, setGotoBad] = useState(false);
  const [cur, setCur] = useState<Recording | null>(null);
  const [track, setTrack] = useState<TrackPt[]>([]);
  const [trackFailed, setTrackFailed] = useState(false);
  const master = useRef<HTMLVideoElement>(null);
  const setHead = (ms: number) => { setHeadRaw(ms); props.onHead(ms); };
  const jump = (ms: number) => { setHead(ms); setGen((g) => g + 1); };
  useEffect(() => { setRobot(props.play.robot); jump(props.play.at); }, [props.play.key, props.play.robot, props.play.at]);
  const bucket = Math.floor(head / HOUR);
  useEffect(() => {
    let live = true;
    api<{ points: TrackPt[] }>("GET", `/api/robots/${enc(robot)}/track?since=${(bucket - 1) * HOUR}&until=${(bucket + 2) * HOUR}`)
      .then((d) => { if (live) { setTrack(Array.isArray(d.points) ? d.points : []); setTrackFailed(false); } })
      .catch(() => { if (live) { setTrack([]); setTrackFailed(true); } });
    return () => { live = false; };
  }, [robot, bucket]);

  const others = props.robots.filter((r) => r !== robot);
  const tiles: { robot: string; cam: "front" | "back" }[] = layout === "single" ? [{ robot, cam: "front" }]
    : layout === "dual" ? [{ robot, cam: "front" }, { robot, cam: "back" }]
      : [robot, ...others.slice(0, 1)].flatMap((r) => [{ robot: r, cam: "front" as const }, { robot: r, cam: "back" as const }]);
  const clipFrom = a ? a.first_ms - 60_000 : head;
  const clipTo = a ? Math.min(Math.max(a.resolved_ms ?? a.last_ms, a.first_ms) + 60_000, a.first_ms + 30 * 60_000) : head + 5 * 60_000;
  // 外审 1 #6:按录像编号记「保留」,跳走再跳回来不回退(子格缓存里的那份还是旧的)
  const [kept, setKept] = useState<Record<string, boolean>>({});
  const curKeep = cur ? (kept[String(cur.id)] ?? !!cur.keep) : false;
  const keep = async () => {
    if (!cur) return;
    const id = cur.id;
    try {
      const d = await api<{ recording: Recording }>("POST", `/api/recordings/${id}/keep`, { keep: !curKeep });
      setKept((k) => ({ ...k, [String(id)]: !!d.recording.keep }));
      setCur((c) => (c && c.id === id ? d.recording : c));
    } catch (e) {
      props.say(t("failed", { why: e instanceof Error ? e.message : String(e) }));
    }
  };
  const snap = () => {
    const v = master.current;
    if (!v || !v.videoWidth) return;
    try {
      const c = document.createElement("canvas");
      c.width = v.videoWidth;
      c.height = v.videoHeight;
      c.getContext("2d")?.drawImage(v, 0, 0);
      const link = document.createElement("a");
      link.href = c.toDataURL("image/png");
      link.download = `${robot}-front-${fileStamp(head)}.png`;
      link.click();
    } catch {
      props.say(t("recSnapFailed"));
    }
  };
  const title = a ? (a.resolved_ms != null
    ? t("pbTitleClosed", { what: alertHeadline(a), v: autoResolved(a) ? t("evAutoRecovered") : verdictText(a) || t("monResolved") })
    : alertHeadline(a)) : t("pbTitleFree", { id: nameOf(robot), t: hms(head) });
  const layouts: { v: PbLayout; key: Key }[] = [{ v: "single", key: "monSingle" }, { v: "dual", key: "monDual" }, { v: "quad", key: "monQuad" }];
  return (
    <div class="pb" data-key={props.play.key ?? undefined}>
      <header class="pb-banner">
        <span class="pb-tag"><i aria-hidden="true" />{t("pbTag", { t: hms(head) })}</span>
        <div class="pb-text">
          <h1>{title}</h1>
          <p>{t("pbAgo", { d: agoText(props.now - head) })}</p>
        </div>
        <button type="button" class="btn primary" data-live="1" onClick={props.onLive}>{t("pbLive")}</button>
      </header>
      <div class="pb-body">
        <div class="pb-video">
          <div class="pb-bar">
            {props.robots.length > 1 && (
              <div class="seg" role="tablist" aria-label={t("monVideo")}>
                {layouts.map((l) => <button key={l.v} type="button" role="tab" aria-selected={layout === l.v} class={layout === l.v ? "on" : ""}
                  onClick={() => setLayout(l.v)}>{t(l.key)}</button>)}
              </div>
            )}
            {props.robots.length > 1 && (
              <div class="seg" role="group" aria-label={t("pbRobot")}>
                {props.robots.map((r) => <button key={r} type="button" aria-pressed={r === robot} onClick={() => { setRobot(r); setGen((g) => g + 1); }}>{nameOf(r)}</button>)}
              </div>
            )}
            <span class="push" />
            <div class="seg" role="group" aria-label={t("pbSpeed")}>
              {SPEEDS.map((s) => <button key={s} type="button" aria-pressed={s === speed} onClick={() => setSpeed(s)}>{s}×</button>)}
            </div>
          </div>
          <div class={`pb-tiles ${layout}`}>
            {tiles.map((x, i) => (
              <PbTile key={`${x.robot}/${x.cam}`} robot={x.robot} cam={x.cam} head={head} gen={gen} playing={playing} speed={speed}
                master={i === 0} vref={i === 0 ? master : undefined}
                onHead={i === 0 ? setHead : undefined} onCur={i === 0 ? setCur : undefined}
                onEnded={i === 0 ? (next) => { if (next != null) jump(next); else setPlaying(false); } : undefined} />
            ))}
          </div>
          <div class="pb-ctl">
            <button type="button" class="btn" onClick={() => jump(head - 10_000)}>{t("pbBack")}</button>
            <button type="button" class="btn" aria-pressed={!playing} onClick={() => setPlaying(!playing)}>{t(playing ? "pbPause" : "pbPlay")}</button>
            <button type="button" class="btn" onClick={() => jump(Math.min(props.now, head + 10_000))}>{t("pbFwd")}</button>
            <span class="push" />
            <button type="button" class="btn" disabled={!cur} onClick={snap}>{t("pbSnap")}</button>
            {canExport(props.role)
              ? <a class="btn" data-clip="1" href={`/api/recordings/clip?robot=${enc(robot)}&camera=front&since=${Math.floor(clipFrom)}&until=${Math.floor(clipTo)}`}>{t("pbClip", { a: hm(clipFrom), b: hm(clipTo) })}</a>
              : <a class="btn" href={`#/recordings?robot=${enc(robot)}&t=${Math.round(head)}`}>{t("pbFull")}</a>}
          </div>
          <div class="pb-ctl">
            <label class="pb-goto">
              <span class="sr-only">{t("pbGoto")}</span>
              <input type="text" class="mono" inputMode="numeric" maxLength={8} placeholder={t("pbGoto")} value={goto} aria-invalid={gotoBad || undefined}
                onInput={(e) => { setGoto(e.currentTarget.value); setGotoBad(false); }}
                onKeyDown={(e) => {
                  if (e.key !== "Enter") return;
                  const s = clockSeconds(goto);
                  const day = dayRange(dateInput(head));
                  if (s == null || !day) { setGotoBad(true); return; }
                  jump(Math.min(props.now, day.since + s * 1000));
                }} />
              {gotoBad && <small class="error" role="alert">{t("pbGotoBad")}</small>}
            </label>
            <span class="push" />
            {canReview(props.role) && (
              <button type="button" class="btn" aria-pressed={curKeep} disabled={!cur} onClick={() => void keep()} title={t("recKeepHint")}>
                {t(curKeep ? "pbKept" : "pbKeep")}
              </button>
            )}
          </div>
        </div>
        <div class="pb-map">
          <div class="pb-map-h"><b>{t("pbPositions", { t: hm(head) })}</b><span class="muted">{t("pbPosHint")}</span></div>
          <RecMap robot={robot} track={track} failed={trackFailed} head={head} onSeek={jump} />
        </div>
      </div>
    </div>
  );
}

/** 一路回放画面。第一格(master)带着走:报回放位置、放完接下一段;其余各格跟着它,差 2 秒以上就对一下。 */
function PbTile(p: {
  robot: string; cam: "front" | "back"; head: number; gen: number; playing: boolean; speed: number; master: boolean;
  vref?: { current: HTMLVideoElement | null };
  onHead?: (ms: number) => void; onCur?: (r: Recording | null) => void; onEnded?: (next: number | null) => void;
}) {
  const { rows, segS } = useRecs(p.robot, p.cam, p.head);
  const [cur, setCur] = useState<Recording | null>(null);
  const own = useRef<HTMLVideoElement | null>(null);
  const want = useRef(0);
  const bind = (el: HTMLVideoElement | null) => { own.current = el; if (p.vref) p.vref.current = el; };
  useEffect(() => {
    if (!rows) return;
    const hit = segmentAt(rows, p.head, segS);
    if (!hit) { setCur(null); p.onCur?.(null); return; }
    want.current = hit.offsetS;
    const v = own.current;
    if (cur?.id === hit.rec.id && v) {
      if (Math.abs(v.currentTime - hit.offsetS) > 2) { try { v.currentTime = hit.offsetS; } catch { /* 还没载入 */ } }
    } else { setCur(hit.rec); p.onCur?.(hit.rec); }
  }, [p.gen, p.master ? 0 : Math.floor(p.head / 2000), rows]);
  useEffect(() => {
    const v = own.current;
    if (!v) return;
    v.playbackRate = p.speed;
    if (p.playing) void v.play()?.catch(() => {}); else v.pause();
  }, [p.playing, p.speed, cur?.id]);
  return (
    <figure class="pb-tile" data-cam={p.cam}>
      <figcaption>
        <span><b>{nameOf(p.robot)}</b> {t(p.cam === "front" ? "front" : "back")}</span>
        <span class="pb-tag sm">{t("pbTag", { t: hms(p.head) })}</span>
      </figcaption>
      {cur ? (
        <video ref={bind} key={cur.id} src={`/api/recordings/${cur.id}/video`} muted playsInline autoplay={p.playing}
          aria-label={`${nameOf(p.robot)} ${t(p.cam === "front" ? "front" : "back")}`}
          onLoadedMetadata={(e) => {
            const v = e.currentTarget as HTMLVideoElement;
            v.playbackRate = p.speed;
            try { v.currentTime = Math.min(want.current, Math.max(0, v.duration - 0.1)); } catch { /* */ }
          }}
          onTimeUpdate={p.onHead ? (e) => p.onHead!(cur.start_ms + (e.currentTarget as HTMLVideoElement).currentTime * 1000) : undefined}
          onEnded={p.onEnded ? () => p.onEnded!(nextSegment(rows ?? [], cur)?.start_ms ?? null) : undefined} />
      ) : <p class="pb-none muted">{rows == null ? t("loading") : t("pbNoRec")}</p>}
    </figure>
  );
}
