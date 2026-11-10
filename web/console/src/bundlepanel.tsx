// 诊断 → 导出诊断包(日志设计 第 5 条,用户 11-10):按场景导出 —— 选一条告警、一趟巡检、一台机器人,
// 时间段按它自动取(开始前 10 分钟到结束后 10 分钟),可以改。出事过几天才导也取得到(留存期内)。
// 包里有站点、机器人的日志和轨迹、各种记录,不含密钥、令牌、照片录像。
import { useEffect, useState } from "preact/hooks";
import { api } from "./api";
import { alertHeadline } from "./alertinfo";
import { hm, md, nameOf } from "./data";
import { t } from "./i18n";
import type { Alert } from "./model";

export type Scene = "time" | "robot" | "run" | "alert";
interface Run { id: number; robot_id: string; mission: string; stamp: string; first_ms: number; by?: string; points?: number | null }

/** 易用性第 6 轮 W6-08:「11-09 01:18 · A · 临时路线 10 个点 · demo 派的」(原来只有 temp-1794… 编号)。 */
export function runLabel(r: Run): string {
  const route = r.mission.startsWith("temp-")
    ? (r.points ? t("bpTempRouteN", { n: r.points }) : t("bpTempRoute")) : r.mission;
  const by = !r.by ? "" : r.by.startsWith("site:") ? t("bpBySchedule") : t("bpBy", { n: r.by });
  return [`${md(r.first_ms)} ${hm(r.first_ms)}`, nameOf(r.robot_id), route, by].filter(Boolean).join(" · ");
}
interface Win { since_ms: number; until_ms: number; robot: string | null; scene: string }

const p2 = (n: number) => String(n).padStart(2, "0");
/** 毫秒 → ``<input type="datetime-local">`` 的值(本地时间)。 */
export function toLocalInput(ms: number): string {
  const d = new Date(ms);
  return `${d.getFullYear()}-${p2(d.getMonth() + 1)}-${p2(d.getDate())}T${p2(d.getHours())}:${p2(d.getMinutes())}`;
}
export function fromLocalInput(s: string): number | null {
  const ms = new Date(s).getTime();
  return Number.isFinite(ms) ? ms : null;
}

/** 下载地址:场景参数 + 时间段。 */
export function bundleHref(scene: Scene, pick: string, from: number | null, to: number | null): string {
  const q = new URLSearchParams();
  if (scene !== "time" && pick) q.set(scene, pick);
  if (from !== null) q.set("from", String(from));
  if (to !== null) q.set("to", String(to));
  return `/api/support-bundle?${q.toString()}`;
}

export function BundlePanel({ robots, fileName }: { robots: string[]; fileName: () => string }) {
  const [scene, setScene] = useState<Scene>("time");
  const [pick, setPick] = useState("");
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [runs, setRuns] = useState<Run[]>([]);
  const [from, setFrom] = useState(() => toLocalInput(Date.now() - 24 * 3_600_000));
  const [to, setTo] = useState(() => toLocalInput(Date.now()));
  const [err, setErr] = useState("");

  useEffect(() => {
    if (scene === "alert") api<{ alerts: Alert[] }>("GET", "/api/alerts?all=1&limit=200").then((d) => setAlerts(d.alerts ?? [])).catch(() => {});
    if (scene === "run") api<{ runs: Run[] }>("GET", "/api/runs?limit=100").then((d) => setRuns(d.runs ?? [])).catch(() => {});
  }, [scene]);

  // 选了告警 / 巡检:问站点按它取哪一段,填进时间段(可以再改)
  useEffect(() => {
    setErr("");
    if (scene === "time" || scene === "robot" || !pick) return;
    api<Win>("GET", `/api/support-bundle/window?${scene}=${encodeURIComponent(pick)}`)
      .then((w) => { setFrom(toLocalInput(w.since_ms)); setTo(toLocalInput(w.until_ms)); })
      .catch((e) => setErr(String((e as Error).message ?? e)));
  }, [scene, pick]);

  const f = fromLocalInput(from), u = fromLocalInput(to);
  const bad = f === null || u === null || u <= f || u - f > 7 * 86_400_000;
  const needPick = scene !== "time" && !pick;
  return (
    <section class="panel bundle" data-bundle>
      <h2>{t("bundleTitle")}</h2>
      <p class="muted small">{t("bundleHint")}</p>
      <div class="row wrap">
        <label class="small muted" for="bundle-scene">{t("bundleScene")}</label>
        <select id="bundle-scene" value={scene} onChange={(e) => { setScene(e.currentTarget.value as Scene); setPick(""); }}>
          <option value="time">{t("sceneTime")}</option>
          <option value="alert">{t("sceneAlert")}</option>
          <option value="run">{t("sceneRun")}</option>
          <option value="robot">{t("sceneRobot")}</option>
        </select>
        {scene === "robot" && (
          <select aria-label={t("sceneRobot")} value={pick} onChange={(e) => setPick(e.currentTarget.value)}>
            <option value="">{t("bundlePick")}</option>
            {robots.map((r) => <option key={r} value={r}>{nameOf(r)}</option>)}
          </select>
        )}
        {scene === "alert" && (
          <select aria-label={t("sceneAlert")} value={pick} onChange={(e) => setPick(e.currentTarget.value)}>
            <option value="">{t("bundlePick")}</option>
            {alerts.map((a) => <option key={a.key} value={a.key}>{[`${md(a.first_ms)} ${hm(a.first_ms)}`, a.robot && a.robot !== "site" ? nameOf(a.robot) : "", alertHeadline(a)].filter(Boolean).join(" · ")}</option>)}
          </select>
        )}
        {scene === "run" && (
          <select aria-label={t("sceneRun")} value={pick} onChange={(e) => setPick(e.currentTarget.value)}>
            <option value="">{t("bundlePick")}</option>
            {runs.map((r) => <option key={r.id} value={String(r.id)}>{runLabel(r)}</option>)}
          </select>
        )}
      </div>
      <div class="row wrap">
        <label class="small muted" for="bundle-from">{t("bundleFrom")}</label>
        <input id="bundle-from" type="datetime-local" value={from} onInput={(e) => setFrom(e.currentTarget.value)} />
        <label class="small muted" for="bundle-to">{t("bundleTo")}</label>
        <input id="bundle-to" type="datetime-local" value={to} onInput={(e) => setTo(e.currentTarget.value)} />
        {bad || needPick
          ? <button class="btn" disabled>{t("supportBundle")}</button>
          : <a class="btn primary" href={bundleHref(scene, pick, f, u)} download={fileName()}>{t("supportBundle")}</a>}
      </div>
      {bad && !needPick && <p class="small warn">{t("bundleBadRange")}</p>}
      {err && <p class="small warn">{err}</p>}
    </section>
  );
}

export interface Problem { code: string; at_ms: number; by: string; note: string; robot: string; device: string; app: string; bytes: number }

/** 问题单(日志设计 第 6 条):App 上传的日志,一张一个编号。工程师(远程登录)按编号下载整包,不用管理员转。 */
export function ProblemList() {
  const [list, setList] = useState<Problem[] | null>(null);
  const [q, setQ] = useState("");
  useEffect(() => {
    api<{ reports: Problem[] }>("GET", "/api/problem-reports").then((d) => setList(d.reports ?? [])).catch(() => setList(null));
  }, []);
  if (list === null) return null;                  // 没有这一项的老站点、没权限:不显示
  const want = q.trim().toUpperCase();
  const shown = want ? list.filter((p) => p.code.includes(want)) : list;
  return (
    <section class="panel problems" data-problems>
      <div class="row wrap">
        <h2>{t("problemsTitle")}</h2>
        <input class="push" type="search" placeholder={t("problemsFind")} aria-label={t("problemsFind")} value={q} onInput={(e) => setQ(e.currentTarget.value)} />
      </div>
      <p class="muted small">{t("problemsHint")}</p>
      {shown.length === 0 ? <p class="muted">{t("problemsNone")}</p> : (
        <ul class="plain">
          {shown.map((p) => (
            <li key={p.code} class="row wrap" data-code={p.code}>
              <b class="mono">{p.code}</b>
              <span class="muted small">{toLocalInput(p.at_ms).replace("T", " ")} · {p.robot ? nameOf(p.robot) + " · " : ""}{p.by}{p.device ? " · " + p.device : ""}</span>
              {p.note && <span>{p.note}</span>}
              <a class="btn push" href={`/api/problem-reports/${p.code}/bundle`} download={`nexwar_${p.code}.tar.gz`}>{t("supportBundle")}</a>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
