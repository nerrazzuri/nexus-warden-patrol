// 1.1-4 远程喊话:按住说话(松开就发给机器人放)、听回话(机器人录几秒传回来)、最近的对讲记录。
// 设计 docs/1.1-4-远程喊话-设计.md。录音只在站点留一天。
import { useEffect, useRef, useState } from "preact/hooks";
import { api, apiUpload, ApiError, enc } from "./api";
import { t } from "./i18n";

export const TALK_MAX_S = 30;
const LISTEN_S = 10;

export interface TalkRow {
  id: string; direction: "out" | "in"; account: string; created_ms: number; state: string; error?: string; bytes: number;
}

/** 浏览器能不能录:要 HTTPS(或本机)、要有 MediaRecorder。 */
export function canRecord(): boolean {
  return typeof window !== "undefined" && typeof MediaRecorder !== "undefined"
    && !!navigator.mediaDevices?.getUserMedia && (window.isSecureContext ?? true);
}

/** 站点等回话的时限(site talk.py REPLY_TIMEOUT_MS)。 */
const REPLY_TIMEOUT_S = 90;

function stateText(r: TalkRow): string {
  if (r.state === "refused") return t("tkRefused", { why: r.error || "" });
  if (r.direction === "in") return r.state === "recorded" ? t("tkReply") : r.state === "failed" ? t("tkReplyFailed", { why: r.error || "" }) : t("tkWaiting");
  return r.state === "fetched" ? t("tkPlayed") : t("tkSent");
}

export function TalkPanel({ robot, name, listen, disabled, say }: {
  robot: string; name: string; listen: boolean; disabled: boolean; say: (s: string) => void;
}) {
  const [rows, setRows] = useState<TalkRow[] | null>(null);
  const [rec, setRec] = useState<"idle" | "rec" | "send">("idle");
  const [secs, setSecs] = useState(0);
  const [asking, setAsking] = useState(false);
  const media = useRef<{ r: MediaRecorder; stream: MediaStream; chunks: Blob[]; timer: number; tick: number; t0: number } | null>(null);
  const live = useRef(true);
  // 外审 1.1 #12:手还按着没有。要麦克风权限、开设备要等;等的时候松了手就不录
  const held = useRef(false);
  const starting = useRef(false);
  const ok = canRecord();

  const load = () => api<{ talks: TalkRow[] }>("GET", `/api/robots/${enc(robot)}/talks`)
    .then((d) => live.current && setRows(d.talks ?? [])).catch(() => live.current && setRows(null));
  useEffect(() => {
    live.current = true;
    void load();
    return () => { live.current = false; stopTracks(); };
  }, [robot]);
  // 等回话的时候每 2 秒看一眼(最多等录音时长 + 20 秒)
  // 外审 1.1 第 2 轮 #11:一直问到站点给结论(站点 90 秒没等到标「没录到」),多 10 秒余量
  const waiting = rows?.some((r) => r.direction === "in" && r.state === "waiting" && Date.now() - r.created_ms < (REPLY_TIMEOUT_S + 10) * 1000);
  useEffect(() => {
    if (!waiting) return;
    const h = window.setInterval(() => void load(), 2000);
    return () => window.clearInterval(h);
  }, [waiting, robot]);

  function press() {
    held.current = true;
    void start();
  }

  function release() {
    held.current = false;
    finish();
  }

  function stopTracks() {
    const m = media.current;
    if (!m) return;
    window.clearTimeout(m.timer);
    window.clearInterval(m.tick);
    m.stream.getTracks().forEach((x) => x.stop());
  }

  async function start() {
    if (rec !== "idle" || disabled || starting.current) return;
    let stream: MediaStream;
    starting.current = true;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      say(t("tkNoMic"));
      return;
    } finally {
      starting.current = false;
    }
    if (!held.current || !live.current) {               // 等权限的时候松了手、离开了页面:不录
      stream.getTracks().forEach((x) => x.stop());
      return;
    }
    const r = new MediaRecorder(stream);
    const m = { r, stream, chunks: [] as Blob[], timer: 0, tick: 0, t0: Date.now() };
    r.ondataavailable = (e) => { if (e.data.size > 0) m.chunks.push(e.data); };
    r.onstop = () => void send(m.chunks, r.mimeType || "audio/webm", Date.now() - m.t0);
    media.current = m;
    m.timer = window.setTimeout(() => finish(), TALK_MAX_S * 1000);
    m.tick = window.setInterval(() => setSecs(Math.floor((Date.now() - m.t0) / 1000)), 250);
    setSecs(0);
    setRec("rec");
    r.start();
  }

  function finish() {
    const m = media.current;
    if (!m || m.r.state !== "recording") return;
    stopTracks();
    m.r.stop();
  }

  async function send(chunks: Blob[], mime: string, ms: number) {
    media.current = null;
    if (ms < 600 || chunks.length === 0) {               // 点一下就松开:不发
      setRec("idle");
      say(t("tkTooShort"));
      return;
    }
    setRec("send");
    try {
      const blob = new Blob(chunks, { type: mime });
      const d = await apiUpload<{ ack?: { result?: string; reason?: string } }>(
        `/api/robots/${enc(robot)}/talk`, blob, { "Content-Type": mime.split(";")[0] });
      const res = d.ack?.result;
      say(res === "accepted" || res === "duplicate" ? t("tkSentTo", { id: name }) : t("tkRefused", { why: d.ack?.reason ?? "" }));
    } catch (e) {
      say(e instanceof ApiError ? e.message : String(e));
    } finally {
      if (live.current) setRec("idle");
      void load();
    }
  }

  async function ask() {
    setAsking(true);
    try {
      const d = await api<{ ack?: { result?: string; reason?: string } }>("POST", `/api/robots/${enc(robot)}/listen`, { seconds: LISTEN_S });
      const res = d.ack?.result;
      say(res === "accepted" || res === "duplicate" ? t("tkListening", { id: name, n: LISTEN_S }) : t("tkRefused", { why: d.ack?.reason ?? "" }));
    } catch (e) {
      say(e instanceof ApiError ? e.message : String(e));
    } finally {
      if (live.current) setAsking(false);
      void load();
    }
  }

  const label = rec === "rec" ? t("tkRecording", { n: secs, max: TALK_MAX_S }) : rec === "send" ? t("tkSending") : t("tkHold");
  return (
    <div class="tk" data-talk="1">
      <div class="tk-row">
        <button type="button" class={`btn tk-hold${rec === "rec" ? " is-rec" : ""}`} data-talk-hold="1"
          disabled={disabled || !ok || rec === "send"} title={!ok ? t("tkNeedHttps") : undefined}
          aria-pressed={rec === "rec"}
          onPointerDown={(e) => { e.preventDefault(); press(); }}
          onPointerUp={() => release()} onPointerLeave={() => release()} onPointerCancel={() => release()}
          onKeyDown={(e) => { if ((e.key === " " || e.key === "Enter") && !e.repeat) { e.preventDefault(); press(); } }}
          onKeyUp={(e) => { if (e.key === " " || e.key === "Enter") release(); }}>
          {label}
        </button>
        {listen && (
          <button type="button" class="btn" data-talk-listen="1" disabled={disabled || asking || !!waiting} onClick={() => void ask()}>
            {waiting ? t("tkWaiting") : t("tkListen", { n: LISTEN_S })}
          </button>
        )}
      </div>
      {!ok && <p class="muted small">{t("tkNeedHttps")}</p>}
      {rows !== null && rows.length > 0 && (
        <ul class="tk-list" aria-label={t("tkRecent")}>
          {rows.slice(0, 5).map((r) => (
            <li key={r.id} data-talk-row={r.id}>
              <span class="tk-who">{r.direction === "out" ? r.account : name}</span>
              <span class="muted small">{new Date(r.created_ms).toLocaleTimeString()} · {stateText(r)}</span>
              {(r.direction === "out" || r.state === "recorded") && r.bytes > 0 && (
                <audio controls preload="none" src={`/api/talk/${r.id}`} aria-label={t("tkPlay")} />
              )}
            </li>
          ))}
        </ul>
      )}
      <p class="muted small">{t("tkKeep")}</p>
    </div>
  );
}
