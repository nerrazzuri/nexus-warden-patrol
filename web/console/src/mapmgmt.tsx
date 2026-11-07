// 地图管理页(管理员):每张图每个版本是什么、哪几只狗在用、发布到狗、回退、删旧版本、两版对比。
// 后端见 packages/site-node/src/nexwar_site/maps_admin*.py;文字走本文件里的 tr(英, 中),不碰 i18n.ts。
import { useCallback, useEffect, useRef, useState } from "preact/hooks";
import { api, ApiError, enc } from "./api";
import { ConfirmPassword } from "./confirmpw";
import { nameOf } from "./data";
import { Modal } from "./dialogs";
import { lang } from "./i18n";
import "./mapmgmt.css";
import { toPx, type PreviewMeta } from "./mapview";

type Say = (s: string) => void;

const tr = (en: string, zh: string): string => (lang.value === "zh" ? zh : en);

export interface Build {
  source: string | number | null;
  builder: string | null;
  frames: number | null;
  loop_closure: { used: boolean; closures: number | null; why: string | null };
  handedness: { verdict: string | null; why: string | null };
}
/** P1-50:版本来源说人话(原来直接显示 denoise、edit,看着像作者名)。 */
export function sourceText(src: string): string {
  // 站点登记的来源:import / edit / denoise,机器人传上来的是机器人编号
  const m: Record<string, [string, string]> = {
    import: ["imported", "导入的"], edit: ["edited in the map editor", "地图编辑器改出来的"],
    denoise: ["cleaned up (noise removed)", "去噪出来的"],
  };
  const hit = m[src];
  return hit ? tr(hit[0], hit[1]) : tr(`built by robot ${nameOf(src)}`, `机器人 ${nameOf(src)} 建的`);
}

export interface Version {
  version: string;
  created_ms: number;
  source: string;
  note: string;
  size_bytes: number;
  /** P1-87:登记了、站点盘上却没有的文件(老站点没有这一项)。 */
  missing?: string[];
  latest: boolean;
  build: Build | null;
  counts: { zones: number; nogo: number; slow: number; zones_rev: number; zones_confirmed: boolean | null; standby: number; intercepts: number };
  loaded_on: string[];
  previous_on: string[];
  thumbnail: string;
  has_raster: boolean;
  /** 11-05 现场第 10 条:缺定位文件的原因(带定位器的机器人用不了);空串 / 没有 = 齐了。 */
  unusable?: string;
}
export interface Activation {
  map_id: string; version: string; state: "pending" | "confirmed" | "failed" | "timeout"; at_ms: number; by: string; reason: string; confirmed: string | null;
  /** W71:等机器人换的时候站点发了多少(机器人上已有的文件不重下,所以到不了 total 也可能已下完)。 */
  download?: { bytes: number; total: number; at_ms: number } | null;
}
export interface Running {
  legacy: boolean;
  problems: string[];
  confirms?: string | null;
  map: { dog: string | null; site: string | null; match: boolean | null } | null;
  zones: { dog_rev: number | null; site_rev: number | null; match: boolean | null; basis: "digest" | "revision" | null } | null;
  mission?: { mission: string; rev: string } | null;
}
export interface Dog {
  robot_id: string;
  online: boolean;
  can_activate: boolean;
  loaded: { map_id: string; version: string } | null;
  running: Running | null;
  activation: Activation | null;
  history: Activation[];
  rollback: { map_id: string; version: string; local: boolean } | null;
}
export interface Overview { maps: { map_id: string; versions: Version[] }[]; robots: Dog[]; now_ms: number }
export interface PublishResult { robot_id: string; ok: boolean; state: string; reason: string; code?: string | null }
export interface DiffStats {
  a: string; b: string; width: number; height: number; caveat: string; likely_misaligned: boolean;
  alignment: number | null; frames_json_same: boolean | null; same_resolution: boolean;
  area_m2: Record<string, number>; colors: Record<string, string>; warning?: string;
}

function errText(e: unknown): string {
  return tr("Failed: ", "失败:") + (e instanceof ApiError ? e.message : String(e));
}

function when(ms: number): string {
  const d = new Date(ms);
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

function mb(bytes: number): string {
  return bytes >= 1e9 ? `${(bytes / 1e9).toFixed(1)} GB` : `${(bytes / 1e6).toFixed(bytes >= 1e7 ? 0 : 1)} MB`;
}

export function activationText(a: Activation, nowMs: number = Date.now()): string {
  switch (a.state) {
    case "pending": {
      // W71(用户 11-03:「下发到机器人的时候需要有个提示」):站点发了多少就写多少
      const d = a.download;
      if (!d) return tr("Sent — waiting for the robot to start downloading", "已发出,等机器人开始下载");
      const idle = Math.round((nowMs - d.at_ms) / 1000);
      const got = `${mb(d.bytes)} / ${mb(d.total)}`;
      if (idle > 15) return tr(`Downloaded ${got}; nothing sent for ${idle} s — loading, or the link is down`, `已下载 ${got};${idle} 秒没再下 —— 在载入,或者网断了`);
      return tr(`Downloading ${got}`, `正在下载 ${got}`);
    }
    case "confirmed":
      return a.confirmed === "localizer"
        ? tr("Confirmed by the localizer", "定位器已确认")
        : a.confirmed === "load"
          ? tr("Loaded (this robot has no localizer)", "已载入(这台机器人没有定位器)")
          : tr("Reported done (old agent: did not wait for the localizer)", "机器人报已换(老代理:没等定位器确认)");
    case "failed":
      return tr("Failed", "没成") + (a.reason ? `: ${a.reason}` : "");
    default:
      return tr("No answer for too long — treat as not done", "太久没动静,当作没换成");
  }
}

// ------------------------------------------------------------------ 页面

export function MapManagePage({ say, pollMs = 5000 }: { say: Say; pollMs?: number }) {
  const [data, setData] = useState<Overview | null>(null);
  const [err, setErr] = useState("");
  const [publish, setPublish] = useState<{ map_id: string; version: string; unusable?: string; source?: string; zonesOk?: boolean | null } | null>(null);
  const [deleting, setDeleting] = useState<{ map_id: string; version: string; back: string[]; latest: boolean } | null>(null);
  const [rolling, setRolling] = useState<Dog | null>(null);
  const [pick, setPick] = useState<string[]>([]);
  const [diff, setDiff] = useState<{ map_id: string; a: string; b: string } | null>(null);
  const [noise, setNoise] = useState<{ map_id: string; version: string } | null>(null);
  const gen = useRef(0);

  const load = useCallback(async () => {
    const my = ++gen.current;
    try {
      const d = await api<Overview>("GET", "/api/admin/maps");
      if (my === gen.current) {
        setData(d);
        setErr("");
      }
    } catch (e) {
      if (my === gen.current) setErr(errText(e));
    }
  }, []);
  useEffect(() => {
    void load();
    if (pollMs <= 0) return;
    const id = window.setInterval(() => void load(), pollMs);
    return () => window.clearInterval(id);
  }, [load, pollMs]);

  async function saveNote(map_id: string, version: string, note: string) {
    try {
      await api("POST", `/api/admin/maps/${enc(map_id)}/${enc(version)}/note`, { note });
      say(tr("Saved", "已保存"));
    } catch (e) {
      say(errText(e));
    }
    void load();
  }

  // P1-47:删除、退回跟发布一样再输密码(对话框里写清后果);密码错对话框不关
  async function doDelete(t: { map_id: string; version: string; back: string[] }, pw: string) {
    const r = await api<{ freed_bytes: number }>("POST", `/api/admin/maps/${enc(t.map_id)}/${enc(t.version)}/delete`,
      { confirm_password: pw, ...(t.back.length > 0 ? { confirm_rollback: true } : {}) });
    setDeleting(null);
    say(tr(`Deleted ${t.map_id}:${t.version} (freed ${mb(r.freed_bytes)})`, `已删除 ${t.map_id}:${t.version}(腾出 ${mb(r.freed_bytes)})`));
    setPick((p) => p.filter((v) => v !== t.version));
    void load();
  }

  async function doRollback(d: Dog, pw: string) {
    const r = await api<{ result: PublishResult }>("POST", "/api/admin/maps/rollback", { robot_id: d.robot_id, without_home: true, confirm_password: pw });
    setRolling(null);
    say(r.result.ok ? tr(`${d.robot_id}: rolling back…`, `${d.robot_id}:正在退回…`) : `${d.robot_id}: ${r.result.reason}`);
    void load();
  }

  const robots = data?.robots ?? [];
  return (
    <div class="admin mm">
      <section class="panel">
        <div class="panel-head">
          <h2>{tr("All versions", "所有版本")}</h2>
          {err && <span class="error" role="alert">{err}</span>}
          <span class="push" />
          {pick.length === 2 && (
            <button type="button" class="btn primary" onClick={() => {
              const [a, b] = pick.map((k) => k.split("\u0000"));
              setDiff({ map_id: a[0], a: a[1], b: b[1] });
            }}>{tr("Compare the two ticked", "对比勾选的两版")}</button>
          )}
        </div>
        {data && data.maps.length === 0 && <p class="pad muted">{tr("No map has been registered yet.", "站点里还没有登记任何地图。")}</p>}
        {(data?.maps ?? []).map((m) => (
          <div key={m.map_id} class="mm-map">
            <h2 class="mm-mapid mono">{m.map_id}</h2>
            <div class="mm-vers">
              {m.versions.map((v) => (
                <VersionCard key={v.version} map_id={m.map_id} v={v}
                  picked={pick.includes(`${m.map_id}\u0000${v.version}`)}
                  onPick={(on) => setPick((p) => {
                    const key = `${m.map_id}\u0000${v.version}`;
                    const rest = p.filter((k) => k !== key && k.split("\u0000")[0] === m.map_id);
                    return on ? [...rest, key].slice(-2) : rest;
                  })}
                  onNote={(n) => void saveNote(m.map_id, v.version, n)}
                  onPublish={() => setPublish({ map_id: m.map_id, version: v.version, unusable: v.unusable ?? "", source: v.source, zonesOk: v.counts.zones_confirmed })}
                  onDelete={() => setDeleting({ map_id: m.map_id, version: v.version, back: v.previous_on, latest: v.latest })}
                  onNoise={() => setNoise({ map_id: m.map_id, version: v.version })}
                />
              ))}
            </div>
          </div>
        ))}
        {pick.length === 1 && <p class="pad muted small">{tr("Tick a second version of the same map to compare.", "再勾选同一张图的另一个版本,就能对比。")}</p>}
      </section>

      <section class="panel">
        <div class="panel-head"><h2>{tr("Robots", "每台机器人")}</h2></div>
        {robots.length === 0 && <p class="pad muted">{tr("No robots enrolled.", "没有登记的机器人。")}</p>}
        {robots.length > 0 && (
          <table class="grid mm-dogs">
            <thead>
              <tr>
                <th>{tr("Robot", "机器人")}</th><th>{tr("Loaded", "加载的")}</th><th>{tr("Last publish", "最近一次下发")}</th>
                <th>{tr("Running config", "实际在跑的配置")}</th><th>{tr("Actions", "操作")}</th>
              </tr>
            </thead>
            <tbody>
              {robots.map((d) => (
                <tr key={d.robot_id} class={d.online ? undefined : "off"}>
                  <td class="mono">{d.robot_id}{!d.online && <span class="muted small"> · {tr("offline", "不在线")}</span>}</td>
                  <td class="mono">{d.loaded ? `${d.loaded.map_id}:${d.loaded.version}` : "—"}</td>
                  <td>{d.activation ? <ActivationCell a={d.activation} /> : <span class="muted">—</span>}</td>
                  <td><RunningCell r={d.running} /></td>
                  <td class="actions">
                    <button type="button" class="btn sm" disabled={!d.rollback} onClick={() => setRolling(d)}
                      title={d.rollback ? "" : tr("No previous version known for this robot", "不知道这台机器人的上一版")}>
                      {tr("Roll back", "退回上一版")}{d.rollback ? ` → ${d.rollback.version}` : ""}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      {publish && (
        <PublishDialog target={publish} dogs={robots} onClose={() => { setPublish(null); void load(); }} />
      )}
      {deleting && (
        <ConfirmPassword title={tr("Delete version", "删除版本")} onClose={() => setDeleting(null)} onConfirm={(pw) => doDelete(deleting, pw)}
          text={[
            tr(`Delete ${deleting.map_id}:${deleting.version}? Its files, zones, standby and intercept points are removed. This cannot be undone; the version number will not be used again.`,
              `删除 ${deleting.map_id}:${deleting.version}?它的文件、区域、待命点、拦截点都会删掉,不能恢复;这个版本号以后不再使用。`),
            deleting.back.length > 0 ? tr(`${deleting.back.join(", ")} would roll back to this version; after deleting, they cannot roll back to it.`,
              `${deleting.back.join("、")} 出问题时会退回这一版;删掉以后就退不回这一版了。`) : "",
            deleting.latest ? tr("This is the newest version of this map.", "这是这张图最新的一版。") : "",
          ].filter(Boolean).join(" ")} />
      )}
      {rolling && rolling.rollback && (
        <ConfirmPassword title={tr("Roll back", "退回上一版")} onClose={() => setRolling(null)} onConfirm={(pw) => doRollback(rolling, pw)}
          text={tr(`Roll ${rolling.robot_id} back to ${rolling.rollback.map_id}:${rolling.rollback.version}? `, `把 ${rolling.robot_id} 退回到 ${rolling.rollback.map_id}:${rolling.rollback.version}?`)
            + (rolling.rollback.local
              ? tr("The robot still has it locally — nothing is downloaded.", "机器人本地还留着这一版,不用重新下载。")
              : tr("The robot may not have it any more and will download it again.", "机器人上可能已经没有这一版,会重新下载。"))} />
      )}
      {diff && <DiffDialog target={diff} onClose={() => setDiff(null)} />}
      {noise && <NoiseDialog target={noise} onClose={() => setNoise(null)}
        onDone={(r) => { setNoise(null); say(tr(`Saved as v${r.version}: ${r.cleaned} spots cleaned. Confirm its zones before publishing.`, `另存成 v${r.version}:清了 ${r.cleaned} 处。发布前先确认它的区域。`)); void load(); }} />}
    </div>
  );
}

function ActivationCell({ a }: { a: Activation }) {
  return (
    <span class={`mm-act ${a.state}`}>
      <b>{a.map_id}:{a.version}</b> · <span data-state={a.state}>{activationText(a)}</span>
      <span class="muted small"> · {a.by} {when(a.at_ms)}</span>
    </span>
  );
}

function tick(ok: boolean | null): string {
  return ok === true ? "✓" : ok === false ? "✗" : "—";
}

function RunningCell({ r }: { r: Running | null }) {
  if (r === null) return <span class="muted">{tr("no report yet", "还没报")}</span>;
  if (r.legacy) return <span class="muted">{tr("Old agent: only the zone revision is compared", "老代理:只比区域修订号")}</span>;
  return (
    <div class="mm-run">
      <span class={r.map?.match === false ? "bad" : undefined}>
        {tr("Map", "图")} {tick(r.map?.match ?? null)}{r.map?.match == null ? <span class="muted small"> {tr("(not checkable)", "(查不了)")}</span> : null}
      </span>
      <span class={r.zones?.match === false ? "bad" : undefined}>
        {tr("Zones", "区域")} {tick(r.zones?.match ?? null)}
        {r.zones?.basis === "revision" && <span class="muted small"> {tr("(old agent: revision only)", "(旧版:只比修订号)")}</span>}
      </span>
      {r.mission && <span class="muted small mono">{tr("mission", "任务")} {r.mission.mission} · {r.mission.rev}</span>}
      {r.problems.map((p, i) => <span key={i} class="bad small">{p}</span>)}
    </div>
  );
}

function VersionCard(p: {
  map_id: string; v: Version; picked: boolean; onPick: (on: boolean) => void; onNote: (n: string) => void;
  onPublish: () => void; onDelete: () => void; onNoise?: () => void;
}) {
  const { v } = p;
  // 没改过就跟着站点的备注走;改过的是草稿(存了、站点那边的备注变成它,草稿就等于它,按钮自然灰掉)
  const [draft, setDraft] = useState<string | null>(null);
  const note = draft ?? v.note;
  const inUse = v.loaded_on.length > 0;
  // 网页易用性第 1 轮 P0-15:只有正在用的不能删;最新一版、退回目标都能删(确认框里说清后果)
  const whyNot = inUse ? tr("A robot is using this version", "有机器人在用这一版") : "";
  const b = v.build;
  return (
    <article class="mm-ver" aria-label={`${p.map_id}:${v.version}`}>
      <MapThumb src={v.thumbnail} />
      <div class="mm-body">
        <h3>
          <span class="mono">v{v.version}</span>
          {v.latest && <span class="mm-tag">{tr("latest", "最新")}</span>}
          <span class="muted small"> · {when(v.created_ms)} · {sourceText(v.source)} · {mb(v.size_bytes)}</span>
        </h3>
        {(v.missing ?? []).length > 0 && (
          <p class="error small" role="alert" data-missing="1">
            {tr(`Map files could not be read (${(v.missing ?? []).length} missing). Upload this version again or delete it.`,
              `地图文件读取失败（缺 ${(v.missing ?? []).length} 个文件）。重新上传这一版，或者删掉它。`)}
          </p>
        )}
        <div class="mm-notebox">
          <input type="text" aria-label={tr(`Note for v${v.version}`, `v${v.version} 的备注`)} value={note} maxLength={200}
            placeholder={tr("Note (what changed, why)", "备注(改了什么、为什么)")} onInput={(e) => setDraft(e.currentTarget.value)} />
          {/* P1-49:写到多少字了(最多 200,多了打不进去) */}
          <span class={note.length >= 200 ? "bad small mono" : "muted small mono"}>{note.length}/200</span>
          <button type="button" class="btn sm" disabled={note.trim() === v.note} onClick={() => p.onNote(note)}>{tr("Save note", "保存备注")}</button>
        </div>
        {/* P1-50:镜像警告留在外面;建图器、帧数、回环这些技术信息收起来 */}
        {b?.handedness.verdict === "mirrored" && <p class="bad small">{tr("Mirrored map — do not publish", "这一版镜像了 —— 别发布")}</p>}
        {b ? (
          <details class="mm-tech"><summary class="small muted">{tr("Technical details", "技术信息")}</summary>
          <p class="mm-build small">
            <span>{tr("Source", "来源")}: <b>{b.source ?? "—"}</b></span>
            <span>{tr("Builder", "建图器")}: {b.builder ?? "—"}{b.frames != null ? ` · ${b.frames} ${tr("frames", "帧")}` : ""}</span>
            <span>{tr("Loop closure", "回环")}: {b.loop_closure.used ? tr(`used (${b.loop_closure.closures ?? "?"})`, `用了(${b.loop_closure.closures ?? "?"} 处)`) : tr("not used", "没用") + (b.loop_closure.why ? ` (${b.loop_closure.why})` : "")}</span>
            <span class={b.handedness.verdict === "mirrored" ? "bad" : undefined}>
              {tr("Handedness check", "手性核对")}: {b.handedness.verdict ?? "—"}{b.handedness.verdict === "mirrored" ? tr(" — MIRRORED, do not publish", " —— 镜像了,别发布") : ""}
            </span>
          </p>
          </details>
        ) : null}
        <p class="small mm-counts">
          <span>{tr("Zones", "区域")} {v.counts.zones} <span class="muted">({v.counts.nogo} {tr("no-go", "禁行")}, {v.counts.slow} {tr("slow", "限速")})</span>
            {v.counts.zones_confirmed === false && <span class="bad"> · {tr("not confirmed", "没确认")}</span>}</span>
          <span>{tr("Standby points", "待命点")} {v.counts.standby}</span>
          <span>{tr("Intercept points", "拦截点")} {v.counts.intercepts}</span>
        </p>
        {v.unusable && <p class="bad small">{tr(`Robots with a localizer can't use this version: ${v.unusable}`, `带定位器的机器人用不了这一版:${v.unusable}`)}</p>}
        <p class="small mm-dogs-on">
          {v.loaded_on.length > 0 && <span>{tr("Loaded on", "正在用")}: {v.loaded_on.map((r) => <span key={r} class="mm-chip mono">{r}</span>)}</span>}
          {v.previous_on.length > 0 && <span class="muted">{tr("Rollback target of", "是退回目标")}: {v.previous_on.map((r) => <span key={r} class="mm-chip mono">{r}</span>)}</span>}
        </p>
        <div class="row mm-actions">
          <button type="button" class="btn sm primary" onClick={p.onPublish}>{tr("Publish to robots…", "发布到机器人…")}</button>
          <button type="button" class="btn sm" disabled={!!whyNot} title={whyNot} onClick={p.onDelete}>{tr("Delete", "删除")}</button>
          {p.onNoise && <button type="button" class="btn sm" disabled={!v.has_raster} onClick={p.onNoise}>{tr("Clean noise…", "清噪点…")}</button>}
          {/* W44 第四期:地图编辑器(橡皮擦、画障碍、区域名、特殊地面、摆正、底图),另存成新的一版 */}
          {v.has_raster && <a class="btn sm" href={`#/admin/mapedit?map=${enc(p.map_id)}&version=${enc(v.version)}`}>{tr("Edit…", "编辑…")}</a>}
          <label class="field-inline small">
            <input type="checkbox" checked={p.picked} disabled={!v.has_raster} onChange={(e) => p.onPick(e.currentTarget.checked)} />
            {tr("Compare", "对比")}
          </label>
        </div>
      </div>
    </article>
  );
}

// ------------------------------------------------------------------ 发布

/** 换图要丢的路线(P0-14):选中的机器人现在用的版本上画的路线,换到 ``target`` 以后都用不了。 */
function lostRoutes(target: { map_id: string; version: string }, dogs: Dog[], chosen: string[],
  routes: { id: string; map_id: string; map_version: string }[]): { from: string; same: boolean; ids: string[] }[] {
  const froms = new Map<string, { from: string; same: boolean; ids: string[] }>();
  for (const d of dogs) {
    if (!chosen.includes(d.robot_id) || !d.loaded) continue;
    if (d.loaded.map_id === target.map_id && d.loaded.version === target.version) continue;
    const key = `${d.loaded.map_id}\u0000${d.loaded.version}`;
    if (froms.has(key)) continue;
    const ids = routes.filter((r) => r.map_id === d.loaded!.map_id && r.map_version === d.loaded!.version).map((r) => r.id);
    if (ids.length) froms.set(key, { from: d.loaded.map_id === target.map_id ? d.loaded.version : `${d.loaded.map_id}:${d.loaded.version}`, same: d.loaded.map_id === target.map_id, ids });
  }
  return [...froms.values()];
}

/** 第 2 轮 N4:一版上画了多少布置(``GET …/layout``)。 */
export interface LayoutCounts { areas: number; exits: number; hides: number; posts: number; net_nodes: number; nogo: number; cameras: number; standby: number; proposal: boolean }

/** 第 2 轮 N4:``from`` 上有、``to`` 上没有的布置,一项一句。禁区、待命点在 ``to`` 有待核建议时另说。 */
export function missingLayout(from: LayoutCounts, to: LayoutCounts): { text: string; review: boolean }[] {
  const out: { text: string; review: boolean }[] = [];
  const n = (k: keyof LayoutCounts) => (from[k] as number) > 0 && (to[k] as number) === 0;
  const pl = (c: number, one: string, many: string) => `${c} ${c === 1 ? one : many}`;
  if (n("areas")) out.push({ text: tr(pl(from.areas, "zone", "zones"), `${from.areas} 个防区`), review: false });
  if (n("exits")) out.push({ text: tr(pl(from.exits, "exit line", "exit lines"), `${from.exits} 条出口线`), review: false });
  if (n("hides")) out.push({ text: tr(pl(from.hides, "hiding spot", "hiding spots"), `${from.hides} 个藏匿点`), review: false });
  if (n("posts")) out.push({ text: tr(pl(from.posts, "adjusted zone post", "adjusted zone posts"), `${from.posts} 个调过的防区查看点 / 值守位`), review: false });
  if (n("net_nodes")) out.push({ text: tr("the road network", "路网"), review: false });
  if (n("cameras")) out.push({ text: tr(pl(from.cameras, "camera", "cameras"), `${from.cameras} 个摄像头位置`), review: false });
  if (n("nogo")) out.push({ text: tr(pl(from.nogo, "no-go zone", "no-go zones"), `${from.nogo} 个禁区`), review: to.proposal });
  if (n("standby")) out.push({ text: tr(pl(from.standby, "standby point", "standby points"), `${from.standby} 个待命点`), review: to.proposal });
  return out;
}

export function PublishDialog({ target, dogs, onClose }: { target: { map_id: string; version: string; unusable?: string; source?: string; zonesOk?: boolean | null }; dogs: Dog[]; onClose: () => void }) {
  const [routes, setRoutes] = useState<{ id: string; map_id: string; map_version: string }[]>([]);
  useEffect(() => {
    api<{ routes: { id: string; map_id: string; map_version: string }[] }>("GET", `/api/routes?map_id=${enc(target.map_id)}`)
      .then((d) => setRoutes(d.routes ?? [])).catch(() => setRoutes([]));
  }, [target.map_id]);
  // 编辑、清噪点出来的版本跟原来同一个坐标系:默认一起搬 —— 第 2 轮 N4:是「搬」不是「抄」,
  // 还有机器人留在旧版、不在这次发布里时,搬走它们就没路线了:那时默认不搬
  const sameFrame = target.source === "edit" || target.source === "denoise";
  const leftBehind = (from: string, picked: string[]) => dogs.filter((d) => !picked.includes(d.robot_id) && d.loaded
    && d.loaded.map_id === target.map_id && d.loaded.version === from).map((d) => d.robot_id);
  const [carry, setCarry] = useState(() => {
    if (!sameFrame) return false;
    const picked = dogs.filter((d) => d.online && d.can_activate && !(target.unusable && d.running?.confirms === "localizer")
      && !(d.loaded && d.loaded.map_id === target.map_id && d.loaded.version === target.version)).map((d) => d.robot_id);
    const froms = new Set(dogs.filter((d) => picked.includes(d.robot_id) && d.loaded?.map_id === target.map_id).map((d) => d.loaded!.version));
    return [...froms].every((v) => leftBehind(v, picked).length === 0);
  });
  const [layouts, setLayouts] = useState<Record<string, LayoutCounts>>({});
  const [moved, setMoved] = useState<string[] | null>(null);
  // 11-05 现场第 10 条:缺定位文件的版本,带定位器的机器人收了也会拒 —— 不让勾
  const noLoc = (d: Dog) => !!target.unusable && d.running?.confirms === "localizer";
  const eligible = dogs.filter((d) => d.online && d.can_activate && !noLoc(d));
  // P1-46:默认勾上在线、能换图、还没用这一版的
  const [chosen, setChosen] = useState<string[]>(() => eligible
    .filter((d) => !(d.loaded && d.loaded.map_id === target.map_id && d.loaded.version === target.version)).map((d) => d.robot_id));
  const fromVersions = Array.from(new Set(dogs.filter((d) => chosen.includes(d.robot_id) && d.loaded?.map_id === target.map_id
    && d.loaded.version !== target.version).map((d) => d.loaded!.version))).sort();
  useEffect(() => {
    for (const v of [target.version, ...fromVersions]) {
      if (layouts[v]) continue;
      api<LayoutCounts>("GET", `/api/admin/maps/${enc(target.map_id)}/${enc(v)}/layout`)
        .then((d) => setLayouts((o) => ({ ...o, [v]: d }))).catch(() => { /* 查不到:不列 */ });
    }
  }, [target.map_id, target.version, fromVersions.join(",")]);
  // P1-45:禁行区没确认的版本站点会拒;先说、给去确认的入口,不让白输密码
  const zonesBad = target.zonesOk === false;
  const [noHome, setNoHome] = useState(false);
  const [pw, setPw] = useState("");
  const [busy, setBusy] = useState(false);
  const [results, setResults] = useState<PublishResult[] | null>(null);
  const [err, setErr] = useState("");
  async function go() {
    setBusy(true);
    setErr("");
    try {
      const lost = lostRoutes(target, dogs, chosen, routes);
      const r = await api<{ results: PublishResult[] }>("POST", `/api/admin/maps/${enc(target.map_id)}/${enc(target.version)}/publish`, { robots: chosen, without_home: noHome, confirm_password: pw });
      setResults(r.results);
      if (carry && r.results.some((x) => x.ok)) {
        const got: string[] = [];
        for (const l of lost.filter((x) => x.same)) {
          try {
            const m = await api<{ moved: string[] }>("POST", `/api/admin/maps/${enc(target.map_id)}/${enc(target.version)}/adopt-routes`, { from: l.from });
            got.push(...m.moved);
          } catch { /* 搬不了:结果里照样提示这些路线要重画 */ }
        }
        setMoved(got);
      }
    } catch (e) {
      setErr(e instanceof ApiError && e.status === 403 ? tr("Wrong password.", "密码不对。") : errText(e));
      setPw("");
    }
    setBusy(false);
  }
  return (
    <Modal label={tr(`Publish ${target.map_id}:${target.version}`, `发布 ${target.map_id}:${target.version}`)} onClose={onClose}>
      {results ? (
        <>
          <ul class="mm-results">
            {results.map((r) => (
              <li key={r.robot_id} class={r.ok ? "ok" : "bad"}>
                <b class="mono">{r.robot_id}</b>{" "}
                {r.ok ? tr("Robot accepted — it is downloading / loading. Watch its status in the Robots table.", "机器人收下了,正在下载、载入。结果看「每台机器人」那张表。") : r.reason}
              </li>
            ))}
          </ul>
          {moved && moved.length > 0 && <p class="small">{tr(`Patrol routes moved to v${target.version}: ${moved.join(", ")}. Check them on the Routes page.`, `已把巡逻路线搬到 v${target.version}:${moved.join("、")}。请到「路线」页核对一遍。`)}</p>}
          {!moved && lostRoutes(target, dogs, chosen, routes).length > 0 && (
            <p class="warn small">{tr(`Patrol routes drawn on the old version are not on v${target.version}; today's patrols that use them will not run until you redraw or move them.`,
              `旧版本上画的巡逻路线不在 v${target.version} 上;用到它们的今日巡逻不会跑,要重画或搬过来。`)}</p>
          )}
          <div class="row end"><button type="button" class="btn primary" onClick={onClose}>{tr("Close", "关闭")}</button></div>
        </>
      ) : (
        <>
          <fieldset class="checks">
            <legend>{tr("Robots", "发到这几台机器人")}</legend>
            {dogs.length === 0 && <span class="muted">{tr("No robots enrolled.", "没有登记的机器人。")}</span>}
            {dogs.map((d) => {
              const ok = d.online && d.can_activate && !noLoc(d);
              return (
                <label key={d.robot_id}>
                  <input type="checkbox" disabled={!ok} checked={chosen.includes(d.robot_id)}
                    onChange={(e) => setChosen((c) => (e.currentTarget.checked ? [...c, d.robot_id] : c.filter((x) => x !== d.robot_id)))} />
                  <span class="mono"> {d.robot_id}</span>
                  <span class="muted small"> · {d.loaded ? `${tr("now", "现在")} ${d.loaded.map_id}:${d.loaded.version}` : tr("no map loaded", "没加载地图")}
                    {!d.online ? ` · ${tr("offline", "不在线")}` : !d.can_activate ? ` · ${tr("cannot switch maps", "不能换图")}`
                      : noLoc(d) ? ` · ${tr("has a localizer; this version lacks localization files", "带定位器,这一版缺定位文件")}` : ""}</span>
                </label>
              );
            })}
          </fieldset>
          {eligible.length === 0 && dogs.length > 0 && <p class="muted small">{tr("No robot is online and able to switch maps.", "没有在线、又能换图的机器人。")}</p>}
          {lostRoutes(target, dogs, chosen, routes).map((l) => (
            <div key={l.from} class="warn small mm-lost">
              <p>{tr(`${l.ids.length} patrol route(s) are drawn on ${l.same ? "v" : ""}${l.from} (${l.ids.join(", ")}). After switching to v${target.version} they cannot run, and today's patrols that use them stop.`,
                `${l.same ? "v" : ""}${l.from} 上画着 ${l.ids.length} 条巡逻路线(${l.ids.join("、")})。换到 v${target.version} 以后它们不能跑,今日计划里用到它们的巡逻也会停。`)}</p>
              {l.same ? (
                <>
                  <label><input type="checkbox" checked={carry} onChange={(e) => setCarry(e.currentTarget.checked)} />{" "}
                    {tr(`Move these routes to v${target.version} too (only if v${target.version} was edited or cleaned from v${l.from}: same coordinates)`,
                      `把这些路线也搬到 v${target.version}(只在 v${target.version} 是从 v${l.from} 编辑、清噪点出来的时候勾:坐标一样)`)}</label>
                  {carry && leftBehind(l.from, chosen).length > 0 && (
                    <p data-left-behind class="warn">{tr(`${leftBehind(l.from, chosen).join(", ")} stay on v${l.from} (not in this publish). Moving takes the routes off v${l.from}, so they would have no routes.`,
                      `${leftBehind(l.from, chosen).join("、")} 还在 v${l.from} 上、不在这次发布里。路线是搬走不是复制,搬了它们就没有这些路线了。`)}</p>
                  )}
                </>
              ) : <p class="muted">{tr("This is a different map: redraw the routes on it.", "这是另一张图:要在新图上重画路线。")}</p>}
            </div>
          ))}
          {fromVersions.map((v) => {
            const from = layouts[v], to = layouts[target.version];
            if (!from || !to) return null;
            const miss = missingLayout(from, to);
            if (miss.length === 0) return null;
            const plain = miss.filter((m) => !m.review), review = miss.filter((m) => m.review);
            return (
              <div key={`miss-${v}`} class="warn small mm-missing">
                {plain.length > 0 && <p>{tr(`On v${v} but not on v${target.version}: ${plain.map((m) => m.text).join(", ")}. After switching they do nothing on these robots — draw them again on v${target.version}.`,
                  `v${v} 上有、v${target.version} 上没有:${plain.map((m) => m.text).join("、")}。换过去以后这些在这几台机器人上都不起作用,要在 v${target.version} 上重画。`)}</p>}
                {review.length > 0 && <p>{tr(`${review.map((m) => m.text).join(", ")} were carried over from an earlier version but are not in effect yet. Check and keep them on the Zones page.`,
                  `${review.map((m) => m.text).join("、")}已从上一版带过来,还没生效:要到「区域」页逐个核对、留下。`)}</p>}
              </div>
            );
          })}
          <fieldset class="checks mm-options">
            <legend>{tr("Options", "选项")}</legend>
            <label><input type="checkbox" checked={noHome} onChange={(e) => setNoHome(e.currentTarget.checked)} /> {tr("Publish even if a robot has no home origin on this version", "机器人在这一版上没有原点也照发")}</label>
          </fieldset>
          {zonesBad && (
            <p class="warn small" role="alert">{tr(`The no-go zones of v${target.version} are not confirmed yet; robots will refuse it. `, `v${target.version} 的禁行区还没确认,机器人会拒收。`)}
              <a href="#/admin/layout?tab=nogo" onClick={onClose}>{tr(`Confirm them in Setup → No-go (pick v${target.version})`, `去「设置 → 禁行区」确认(选 v${target.version})`)}</a></p>
          )}
          <p class="muted small">{tr("Each robot switches on its own: it downloads, waits until idle, loads, and (if it has a localizer) waits for the localizer to accept the map. A robot the localizer rejects goes back to its previous map.", "每台机器人各自换:下载、等空闲、载入,有定位器的还要等定位器收下新图;定位器不收的,机器人会退回原来那张。")}</p>
          {/* W44 第四期(设计 §5.2 第 4 条):换图要再输一次密码 */}
          <label class="field">{tr("Your password (switching maps matters)", "你的密码(换图要紧,再输一次)")}
            <input type="password" name="confirm_pw" autoComplete="current-password" value={pw} onInput={(e) => setPw(e.currentTarget.value)} />
          </label>
          {err && <p class="error" role="alert">{err}</p>}
          <div class="row end">
            <button type="button" class="btn" onClick={onClose}>{tr("Cancel", "取消")}</button>
            <button type="button" class="btn primary" disabled={busy || chosen.length === 0 || !pw || zonesBad} title={chosen.length === 0 ? tr("Tick at least one robot", "至少勾一台机器人") : !pw ? tr("Enter your password", "输入你的密码") : undefined} onClick={() => void go()}>{tr("Publish", "发布")}</button>
          </div>
        </>
      )}
    </Modal>
  );
}

// ------------------------------------------------------------------ 对比

const LEGEND: [string, string, string][] = [
  ["same_wall", "Wall in both", "两版都有的墙"],
  ["same_free", "Free in both", "两版都是空地"],
  ["wall_only_a", "Wall only in A", "只有 A 有的墙"],
  ["wall_only_b", "Wall only in B", "只有 B 有的墙"],
  ["free_only_a", "Free in A, not mapped in B", "A 是空地、B 没扫到"],
  ["free_only_b", "Not mapped in A, free in B", "A 没扫到、B 是空地"],
];

export function DiffDialog({ target, onClose }: { target: { map_id: string; a: string; b: string }; onClose: () => void }) {
  const [stats, setStats] = useState<DiffStats | null>(null);
  const [err, setErr] = useState("");
  const gen = useRef(0);
  const q = `/api/admin/maps/${enc(target.map_id)}/${enc(target.a)}/diff`;
  // P1-48:说明里的 A、B 换成版本号(机器人也叫 A、B,容易看混)
  const vn = (x: string) => x.replace(/\bA\b/g, `v${target.a}`).replace(/\bB\b/g, `v${target.b}`);
  useEffect(() => {
    const my = ++gen.current;
    setStats(null);
    setErr("");
    api<DiffStats>("GET", `${q}?with=${enc(target.b)}`)
      .then((d) => { if (my === gen.current) setStats(d); })
      .catch((e) => { if (my === gen.current) setErr(errText(e)); });
  }, [q, target.b]);
  return (
    <Modal wide label={tr(`Compare v${target.a} with v${target.b}`, `对比 v${target.a} 和 v${target.b}`)} onClose={onClose}>
      {err && <p class="error" role="alert">{err}</p>}
      {!stats && !err && <p class="muted">{tr("Rendering…", "正在画…")}</p>}
      {stats && (
        <div class="mm-diff">
          <p class="mm-caveat" role="note">{stats.caveat}</p>
          {stats.likely_misaligned && (
            <p class="mm-misaligned bad" role="alert">
              {vn(tr(`Only ${Math.round((stats.alignment ?? 0) * 100)}% of A's wall cells have a wall of B next to them: these two versions are very likely NOT in the same coordinate frame. The picture below is not meaningful.`,
                `A 的墙只有 ${Math.round((stats.alignment ?? 0) * 100)}% 在 B 里也有墙:这两版很可能不在同一个坐标系里,下面的图没有意义。`))}
            </p>
          )}
          {stats.frames_json_same === false && <p class="small bad">{tr("The two versions have different frames.json (lidar mounting / frame conventions).", "两版的 frames.json 不一样(雷达装法、坐标约定)。")}</p>}
          {stats.frames_json_same === true && <p class="small muted">{tr("Same frames.json in both (a good sign, not a proof).", "两版的 frames.json 一样(是好兆头,不是证明)。")}</p>}
          {!stats.same_resolution && <p class="small muted">{vn(tr("Different resolutions: B was resampled to the finer grid.", "分辨率不同:按较细的重采。"))}</p>}
          {/* P1-48:点图在新标签页看原图(能放大) */}
          <a href={`${q}.png?with=${enc(target.b)}`} target="_blank" rel="noopener" title={tr("Open full size", "看原图")}>
            <img class="mm-diffimg" alt={tr("Difference image", "差异图")} src={`${q}.png?with=${enc(target.b)}`} />
          </a>
          <ul class="mm-legend small">
            {LEGEND.map(([k, en, zh]) => (
              <li key={k}>
                <span class="mm-sw" style={{ background: stats.colors[k] }} aria-hidden="true" /> {vn(tr(en, zh))}
                <span class="muted"> · {stats.area_m2[k]?.toFixed(1)} m²</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      <div class="row end"><button type="button" class="btn" onClick={onClose}>{tr("Close", "关闭")}</button></div>
    </Modal>
  );
}

// ------------------------------------------------------------------ 清噪点(W41)

interface Speck { id: number; x: number; y: number; px: number }
interface NoiseList { digest: string; res: number; max_m2: number; ring_m: number; specks: Speck[] }
export interface DenoiseResult { version: string; cleaned: number; cells: number; homes_copied: number }

/** 这一版里「零星噪点」的候选画在图上(红圈),点一下去掉、再点加回;确认后清掉、另存成新的一版。 */
export function NoiseDialog({ target, onClose, onDone }: {
  target: { map_id: string; version: string }; onClose: () => void; onDone: (r: DenoiseResult) => void;
}) {
  const base = `/api/admin/maps/${enc(target.map_id)}/${enc(target.version)}`;
  const view = `/api/maps/${enc(target.map_id)}/${enc(target.version)}`;
  const [list, setList] = useState<NoiseList | null>(null);
  const [meta, setMeta] = useState<PreviewMeta | null>(null);
  const [skip, setSkip] = useState<Set<number>>(new Set());
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  // 外审 R6:预览(元数据、底图)拿不到就不许清 —— 看不到图就挑不了「细杆子留着」
  const [previewErr, setPreviewErr] = useState("");
  const [tries, setTries] = useState(0);
  // 复查 N3:底图(preview.png)真加载好了才算看得到;重试换个地址真的重拉
  const [imgOk, setImgOk] = useState(false);
  useEffect(() => {
    let live = true;
    api<NoiseList>("GET", `${base}/noise`).then((d) => live && setList(d)).catch((e) => live && setErr(errText(e)));
    return () => { live = false; };
  }, [base]);
  // 复查 N6:重置放在点「重试」那一下同步做;放在 effect 里,新底图加载得快会被后跑的 effect 盖掉。
  // 复查 N7:请求代次也在那一下推进 —— 前一次的预览请求迟到(哪怕失败)只认最新那一代,不污染
  const gen = useRef(0);
  const retry = () => { gen.current += 1; setImgOk(false); setPreviewErr(""); setTries((t) => t + 1); };
  useEffect(() => {
    const mine = gen.current;
    const current = () => mine === gen.current;
    api<PreviewMeta>("GET", `${view}/preview`).then((m) => { if (current()) setMeta(m); })
      .catch((e) => { if (current()) { setMeta(null); setPreviewErr(errText(e)); } });
    return () => { if (mine === gen.current) gen.current += 1; };   // 换图、关掉:这一代作废
  }, [view, tries]);
  const n = list ? list.specks.filter((s) => !skip.has(s.id)).length : 0;
  const toggle = (id: number) => setSkip((cur) => { const next = new Set(cur); if (next.has(id)) next.delete(id); else next.add(id); return next; });
  async function go() {
    if (!list) return;
    setBusy(true);
    try {
      onDone(await api<DenoiseResult>("POST", `${base}/denoise`, { digest: list.digest, skip: [...skip] }));
    } catch (e) {
      setErr(errText(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal wide label={tr(`Clean noise in v${target.version}`, `清 v${target.version} 的噪点`)} onClose={onClose}>
      {err && <p class="error" role="alert">{err}</p>}
      {previewErr && (
        <p class="error" role="alert">
          {tr(`Map preview unavailable (${previewErr}) — can't clean without seeing the spots.`, `地图预览拿不到(${previewErr}):看不到图就不能清。`)}{" "}
          <button type="button" class="btn" data-noise-retry="1" onClick={retry}>{tr("Retry", "重试")}</button>
        </p>
      )}
      {!list && !err && <p class="muted">{tr("Looking for noise…", "正在找…")}</p>}
      {list && (
        <div class="mm-noise">
          <p class="small">{tr(
            `Red circles: tiny isolated obstacle specks (≤ ${list.max_m2} m², open floor all around within ${list.ring_m} m) — usually people walking while the map was built. They block the planner. Click a circle to keep that one (e.g. a thin post).`,
            `红圈:很小、四周 ${list.ring_m} 米都是空地的占用格(每处不超过 ${list.max_m2} 平方米)—— 多半是建图时有人走动留下的,会把规划的路封住。是真东西(比如细杆子)就点一下那个圈,留着它。`)}</p>
          {list.specks.length === 0 ? <p class="muted">{tr("No noise found in this version.", "这一版没找到噪点。")}</p> : meta && (
            <svg class="mm-noiseimg" viewBox={`0 0 ${meta.width} ${meta.height}`} role="img" aria-label={tr("Noise on the map", "图上的噪点")}>
              <image key={tries} href={`${view}/preview.png${tries ? `?try=${tries}` : ""}`} x={0} y={0} width={meta.width} height={meta.height}
                onLoad={() => setImgOk(true)}
                onError={() => { setImgOk(false); setPreviewErr(tr("map image failed to load", "底图加载失败")); }} />
              {list.specks.map((s) => {
                const p = toPx(meta, s.x, s.y);
                const kept = skip.has(s.id);
                // 网页易用性第 1 轮 P0-11:原来只有 2 像素的圈线能点(fill=none),大图缩小以后几乎点不中;
                // 整个圈都能点,圈按图的大小放大;下面另有一张清单可以逐个勾
                const r = Math.max(6, Math.round(Math.max(meta.width, meta.height) / 60));
                return <circle key={s.id} data-speck={s.id} data-kept={kept ? "1" : "0"} cx={p.px} cy={p.py} r={r}
                  fill="transparent" pointer-events="all" stroke={kept ? "#888" : "#e53935"} stroke-width={Math.max(2, r / 4)} stroke-dasharray={kept ? "3 2" : undefined}
                  style={{ cursor: "pointer" }} onClick={() => toggle(s.id)}><title>{`#${s.id} (${s.x}, ${s.y}) · ${s.px}`}</title></circle>;
              })}
            </svg>
          )}
          {list.specks.length > 0 && (
            <ul class="mm-specks plain">
              {list.specks.map((s) => (
                <li key={s.id}>
                  <label><input type="checkbox" data-keep={s.id} checked={skip.has(s.id)} onChange={() => toggle(s.id)} />{" "}
                    {tr(`Keep #${s.id} at (${s.x}, ${s.y})`, `留着 #${s.id}(${s.x}, ${s.y})`)}</label>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
      <div class="row end">
        <button type="button" class="btn" onClick={onClose}>{tr("Cancel", "取消")}</button>
        <button type="button" class="btn primary" data-denoise="1" disabled={!list || n === 0 || busy || !meta || !imgOk || !!previewErr} onClick={() => void go()}>
          {tr(`Clean ${n} spots → save as a new version`, `清掉 ${n} 处,另存成新的一版`)}
        </button>
      </div>
    </Modal>
  );
}

/** P2-40:缩略图读不到时显示占位,不出破图图标。 */
function MapThumb({ src }: { src?: string | null }) {
  const [bad, setBad] = useState(false);
  if (!src || bad) return <div class="mm-thumb mm-thumb-none" data-thumb-none="1" aria-hidden="true">{tr("No preview", "无预览")}</div>;
  return <img class="mm-thumb" src={src} alt="" loading="lazy" width={120} height={120} onError={() => setBad(true)} />;
}
