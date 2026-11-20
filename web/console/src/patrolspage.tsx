// 记录与录像 → 巡逻记录(真机 11-20:网页没有这一页,App 有;巡逻拍的照片只能去站点盘上找)。
// 左:标签 + 筛选(今天 / 有异常 / 全部、哪台机器人)+ 今天几趟、几趟有异常;中:一趟一行(时间、路线、机器人、
// 结果、判读、照片张数);右:选中那一趟 —— 每张照片(点位、哪一路相机、模型判读、人工复核),点开看原图。
// 跟 App 的「巡逻记录」(mobile/lib/ui/site_runs.dart)同一个口径:/api/runs、/api/runs/<id>。
import { useEffect, useState } from "preact/hooks";
import { api, enc } from "./api";
import { nameOf } from "./data";
import { t, type Key } from "./i18n";
import { SubTabs } from "./shell";
import { siteStr } from "./sitetext";

export interface RunRow {
  id: number; robot_id: string; mission?: string; title?: string; kind?: string; stamp?: string;
  photos?: number; judged_ms?: number | null; verdicts?: Record<string, number> | null; reviewed?: number;
  running?: boolean; ended?: string | null; finished?: boolean; result?: string | null;
}
interface Photo {
  name: string; waypoint?: string; camera?: string;
  finding?: { verdict?: string; reason?: string } | null; review?: { verdict?: string; note?: string } | null;
}

const STAMP = /^(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})Z(?:-\S+)?$/;

/** 目录名 `20261120T093408Z-955734` → 当地时刻;认不出来是 null。 */
export function stampTime(stamp: string | undefined): Date | null {
  const m = STAMP.exec(stamp ?? "");
  return m ? new Date(Date.UTC(+m[1], +m[2] - 1, +m[3], +m[4], +m[5], +m[6])) : null;
}

const two = (n: number) => String(n).padStart(2, "0");
export function stampText(stamp: string | undefined): string {
  const d = stampTime(stamp);
  return d ? `${d.getFullYear()}-${two(d.getMonth() + 1)}-${two(d.getDate())} ${two(d.getHours())}:${two(d.getMinutes())}` : stamp ?? "";
}

/** 一趟的标题:路线名;临时路线、报警出动、回原点 / 待命点、手动派的说是哪一种(任务号不给人看)。 */
export function runTitle(r: RunRow): string {
  const m = r.mission ?? "";
  if (/^temp-/.test(m)) return t("ptOneOff");
  if (/^incident-/.test(m)) return t("ptIncident");
  if (r.kind === "home" || /^(standby-)?home-/.test(m)) return t("ptHome");
  if (r.kind === "standby" || /^standby-/.test(m)) return t("ptStandby");
  if (/^(task|goto)-[0-9a-f]+$/.test(m)) return t("ptByHand");
  return r.title || m;
}

export function runResult(r: RunRow): { text: string; bad: boolean } {
  if (r.running) return { text: t("ptRunning"), bad: false };
  if (r.ended === "preempted" || r.result === "preempted") return { text: t("ptPreempted"), bad: false };
  if (!r.finished) return { text: t("ptUnfinished"), bad: true };
  if (r.result === "aborted" || r.result === "abort") return { text: t("ptStopped"), bad: true };
  if (r.result === "failed") return { text: t("ptFailed"), bad: true };
  return { text: t("ptDone"), bad: false };
}

const VERDICT: Record<string, Key> = { normal: "ptNormal", abnormal: "ptAbnormal", unclear: "ptUnclear", pending: "ptPending" };
export const verdictText = (v: string | null | undefined) => t(VERDICT[v ?? "pending"] ?? "ptPending");
export const abnormal = (r: RunRow) => (r.verdicts?.abnormal ?? 0) > 0;

function verdictSummary(r: RunRow): string {
  if (!r.photos) return t("ptNoPhotos");
  if (r.judged_ms == null || !r.verdicts || Object.keys(r.verdicts).length === 0) return t("ptNotJudged");
  return ["abnormal", "unclear", "normal", "pending"].filter((k) => (r.verdicts![k] ?? 0) > 0)
    .map((k) => `${verdictText(k)} ${r.verdicts![k]}`).join(" · ");
}

type Show = "today" | "anomalies" | "all";

export function PatrolsPage(props: { role: string; robots: string[] }) {
  const [rows, setRows] = useState<RunRow[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [show, setShow] = useState<Show | null>(null);
  const [robot, setRobot] = useState("");
  const [sel, setSel] = useState<number | null>(null);

  useEffect(() => {
    let live = true;
    const pull = () => api<{ runs: RunRow[] }>("GET", `/api/runs?limit=200${robot ? `&robot=${enc(robot)}` : ""}`)
      .then((d) => { if (live) { setRows(d.runs ?? []); setFailed(false); } })
      .catch(() => { if (live) setFailed(true); });
    pull();
    // 跟 App 一样:开着就隔 30 秒取一次(正在跑的那一趟跑完、新开跑的自己出来)
    const h = setInterval(pull, 30_000);
    return () => { live = false; clearInterval(h); };
  }, [robot]);

  const now = new Date();
  const isToday = (r: RunRow) => { const d = stampTime(r.stamp); return !!d && d.toDateString() === now.toDateString(); };
  const today = (rows ?? []).filter(isToday);
  // 没选过:今天有就看今天,没有看全部
  const mode: Show = show ?? (today.length > 0 ? "today" : "all");
  const shown = (rows ?? []).filter((r) => mode === "all" || (mode === "today" ? isToday(r) : abnormal(r)));
  const focus = shown.find((r) => r.id === sel) ?? null;
  const robots = Array.from(new Set([...props.robots, ...(rows ?? []).map((r) => r.robot_id)])).sort();

  return (
    <div class="ev patrols">
      <aside class="ev-left">
        <SubTabs page="patrols" role={props.role} rail />
        <fieldset class="ev-f">
          <legend>{t("ptShow")}</legend>
          {(["today", "anomalies", "all"] as const).map((s) => (
            <label key={s} class="ev-check"><input type="radio" name="pt-show" data-show={s} checked={mode === s} onChange={() => setShow(s)} />
              {t(s === "today" ? "ptToday" : s === "anomalies" ? "ptAnomalies" : "ptAll")}</label>
          ))}
        </fieldset>
        <label class="ev-f">{t("ptRobot")}
          <select value={robot} data-pt-robot="1" onChange={(e) => { setRobot(e.currentTarget.value); setSel(null); }}>
            <option value="">{t("ptAll")}</option>
            {robots.map((r) => <option key={r} value={r}>{nameOf(r)}</option>)}
          </select>
        </label>
        <div class="ev-sum pt-sum" aria-label={t("ptToday")}>
          <h3>{t("ptToday")}</h3>
          <div><b>{rows == null ? "–" : today.length}</b><span>{t("ptSumRuns")}</span></div>
          <div class={today.some(abnormal) ? "has" : ""}><b>{rows == null ? "–" : today.filter(abnormal).length}</b><span>{t("ptSumAnomalies")}</span></div>
          <div class={today.some((r) => runResult(r).bad) ? "has" : ""}><b>{rows == null ? "–" : today.filter((r) => runResult(r).bad).length}</b><span>{t("ptSumUnfinished")}</span></div>
        </div>
      </aside>

      <section class="ev-main">
        <header class="ev-head"><div><h1>{t("ptTitle")}</h1><p class="muted small">{t("ptSub")}</p></div></header>
        {rows == null && <p class={failed ? "empty warn" : "empty"}>{t(failed ? "loadRetry" : "loading")}</p>}
        {rows != null && shown.length === 0 && <p class="empty">{t(rows.length === 0 ? "ptNone" : "ptNoneHere")}</p>}
        {shown.length > 0 && (
          <table class="ev-table pt-table">
            <thead><tr><th>{t("ptColTime")}</th><th>{t("ptColRun")}</th><th>{t("ptColResult")}</th><th>{t("ptColPhotos")}</th></tr></thead>
            <tbody>
              {shown.map((r) => {
                const res = runResult(r);
                return (
                  <tr key={r.id} class={`it${focus?.id === r.id ? " on" : ""}`} data-run={r.id} onClick={() => setSel(r.id)}>
                    <td class="mono">{stampText(r.stamp)}</td>
                    <td><button type="button" class="linkish strong" onClick={(e) => { e.stopPropagation(); setSel(r.id); }}>{runTitle(r)}</button>
                      <small class="muted"> · {nameOf(r.robot_id)}</small></td>
                    <td><span class={res.bad ? "ev-none" : undefined}>{res.text}</span>
                      {r.photos ? <small class={abnormal(r) ? "pt-bad" : "muted"}> · {abnormal(r) ? `${verdictText("abnormal")} ${r.verdicts!.abnormal}` : verdictSummary(r)}</small> : null}
                      {(r.reviewed ?? 0) > 0 && <small class="muted"> · {t("ptReviewed", { n: r.reviewed ?? 0 })}</small>}</td>
                    <td class="mono">{r.photos ? r.photos : <span class="muted">{t("ptNoPhotos")}</span>}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </section>

      <aside class="ev-side">
        {focus ? <RunPanel key={focus.id} run={focus} /> : <p class="empty muted">{t("ptPick")}</p>}
      </aside>
    </div>
  );
}

function RunPanel({ run }: { run: RunRow }) {
  const [photos, setPhotos] = useState<Photo[] | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let live = true;
    api<{ photos?: Photo[] }>("GET", `/api/runs/${run.id}`)
      .then((d) => live && setPhotos(d.photos ?? []))
      .catch(() => live && setFailed(true));
    return () => { live = false; };
  }, [run.id]);
  const res = runResult(run);
  return (
    <div class="evp pt-run" data-pt-run={run.id}>
      <header class="pt-runhead">
        <h2>{runTitle(run)}</h2>
        <p class="muted small">{stampText(run.stamp)} · {nameOf(run.robot_id)} · <span class={res.bad ? "ev-none" : undefined}>{res.text}</span></p>
      </header>
      {photos == null && <p class={failed ? "empty warn" : "empty"}>{t(failed ? "loadRetry" : "loading")}</p>}
      {photos != null && photos.length === 0 && <p class="empty muted">{t("ptRunNoPhotos")}</p>}
      {photos != null && photos.length > 0 && (
        <ul class="pt-photos">
          {photos.map((p) => {
            const src = `/api/runs/${run.id}/photos/${enc(p.name)}`;
            const shown = p.review?.verdict ?? p.finding?.verdict;
            return (
              <li key={p.name} data-photo={p.name} class={shown === "abnormal" ? "bad" : undefined}>
                <a href={src} target="_blank" rel="noopener"><img src={src} alt={`${p.waypoint ?? ""} ${p.camera ?? ""}`} loading="lazy" /></a>
                <div>
                  <b>{p.waypoint ?? "—"}</b><span class="muted"> · {p.camera ?? ""}</span>
                  <p class={shown === "abnormal" ? "pt-bad" : undefined}>{verdictText(shown)}{p.review ? ` (${t("ptByPerson")})` : ""}</p>
                  {p.review?.note ? <p class="muted small">{p.review.note}</p>
                    : p.finding?.reason ? <p class="muted small">{siteStr(p.finding.reason)}</p> : null}
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
