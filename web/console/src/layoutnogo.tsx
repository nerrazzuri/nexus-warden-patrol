// 布置 → 禁行区(W44 第三期,设计 §5.2、§9;规则是决策 66 和 W41 的,一条不改,只换成人话):
// - 三种:禁行区(圈一块)、虚拟墙(画一条线,站点存成约 0.3 m 宽的禁行带)、限速区(圈一块,填限速);可以设成临时的(几天)。
// - 加、收紧:保存就生效。删、缩小(放宽):要确认,确认之前机器人照旧绕开原来的范围;网页上确认放宽要再输一次密码。
// - 机器人还没收到在生效的那一份:写「等机器人确认中」。
// 人员忽略区(W41,机器人在里面看见人不报)、抹掉区(机器人永远不去、画图时抹成没建图)。
// 11-10(用户:「所有动作都要在编辑器中完成」):画、删、改名、拖顶点都搬进地图编辑器(mapedit.tsx);这一页只看
// 这一版有哪些、在不在生效,确认此版本、处理带过来的建议,给「去编辑器里改」。
import { useEffect, useState } from "preact/hooks";
import { api, ApiError } from "./api";
import { Modal } from "./dialogs";
import { t, joinList } from "./i18n";
import { siteKnown } from "./sitetext";
import { polyPx, type NavZones, type TabProps } from "./layoutpage";
import type { LegendKey } from "./mapcanvas";
import type { NavZone, Pt } from "./mapview";

export type Draw = "nogo" | "wall" | "slow" | "ignore" | "erase";
export interface Form { label: string; hard: boolean; speed: number; temp: boolean; days: number }
/** 新画的:站点要的格式(临时的带 for_s,站点按自己的钟换成到期时刻)。 */
export type Draft = NavZone & { for_s?: number };
const DAYS = [1, 3, 7, 30];

/** 一个区域给人看的一行字:种类、硬、临时到什么时候。 */
export function nogoLine(z: Draft): string {
  const kind = z.wall ? t("kindVWall") : z.kind === "slow" ? t("kindSlow", { v: z.max_speed_mps ?? "?" }) : z.kind === "ignore" ? t("kindIgnore") : z.kind === "erase" ? t("eraseLabel") : t("kindNoGo");
  const bits = [kind];
  if (z.hard) bits.push(t("kindHard"));
  if (typeof z.until_ms === "number") {
    const d = new Date(z.until_ms);
    const two = (v: number) => String(v).padStart(2, "0");
    bits.push(t("kindTemp", { t: `${two(d.getMonth() + 1)}-${two(d.getDate())} ${two(d.getHours())}:${two(d.getMinutes())}` }));
  } else if (z.for_s) bits.push(t("lyTempDays", { n: Math.round(z.for_s / 86400) }));
  return bits.join(" · ");
}

interface RobotRun { robot_id: string; running?: { map_id?: string; map_version?: string; zones?: { match?: boolean | null } | null } | null }

/** 这一版禁行区的状态(在生效 / 等你确认 / 从没确认过 / 等机器人)、带过来的建议、「确认此版本」。
 *  布置 → 禁行区 和地图编辑器都用(11-10:画都在编辑器里画)。``changed``:页面上还有没存的改动(不给确认)。 */
export function NogoStatus({ nav, base, mapId, version, changed, say, reload, draft = false }: {
  nav: NavZones | null; base: string; mapId: string; version: string; changed: boolean; say: (s: string) => void; reload: () => Promise<void>;
  /** 11-10:编辑草稿 —— 禁行区在「发布」时一起确认,这里不给单独确认 */
  draft?: boolean;
}) {
  const [confirming, setConfirming] = useState(false);
  const [behind, setBehind] = useState<string[]>([]);
  useEffect(() => {
    let live = true;
    api<{ robots: RobotRun[] }>("GET", "/api/robots").then((d) => {
      if (!live) return;
      setBehind((d.robots ?? []).filter((r) => r.running?.map_id === mapId && r.running?.map_version === version
        && r.running?.zones?.match === false).map((r) => r.robot_id));
    }).catch(() => {});
    return () => { live = false; };
  }, [nav?.revision]);
  const held = nav?.held ?? [];
  const current = !!nav?.confirmed?.current;
  // 第 3 轮 maps N1:上一版带过来、还没核的禁行区。网页上原来看不到也采纳不了,确认就确认了一个空集
  const prop = nav?.proposal && nav.proposal.zones.length > 0 ? nav.proposal : null;
  async function takeProposal(keep: boolean) {
    if (!nav || !prop) return;
    try {
      if (keep) {
        await api("POST", `${base}/zones/confirm`, { revision: nav.revision, confirm: true, adopt: { zones: prop.zones.map((z) => z.id) } });
        say(t("lyNogoPropKept", { n: prop.zones.length }));
      } else {
        await api("POST", `${base}/zones/proposal`, { action: "discard" });
        say(t("lyNogoPropDropped"));
      }
      await reload();
    } catch (e) {
      say(t("failed", { why: e instanceof ApiError ? e.message : String(e) }));
    }
  }
  async function confirm(pw?: string) {
    if (!nav) return;
    await api("POST", `${base}/zones/confirm`, {
      revision: nav.revision, confirm: true, ...(nav.zones.length === 0 ? { empty_ok: true } : {}), ...(pw ? { confirm_password: pw } : {}),
    });
    setConfirming(false);
    say(t("navConfirmedOk", { rev: nav.revision }));
    await reload();
  }
  return (
    <div class="nogo-status">
      {!nav ? <p class="muted">…</p> : current && held.length === 0
        ? <p class="ok-text">{t("lyNogoLive")}</p>
        : held.length > 0 ? <p class="warn-text">{t("lyNogoWaitYou", { names: joinList(held.map((z) => siteKnown(z.label) || z.id)) })}</p>
        // 第 4 轮 maps N1:另存出来的版本已经抄了来源版本的区域 —— 说「已有 n 个,核一下再确认」,不说「去画」
        : (nav.zones?.length ?? 0) > 0 ? <p class="warn-text" data-nogo-copied="1">{t("lyNogoCopiedCheck", { n: nav.zones.length })}</p>
        : <p class="warn-text">{t("lyNogoNeverConfirmed")}</p>}
      {behind.length > 0 && <p class="warn-text">{t("lyNogoWaitRobot", { ids: joinList(behind) })}</p>}
      {prop && (
        <div class="nogo-prop" data-nogo-prop="1">
          <p class="warn-text">{t(prop.frame?.same === false ? "lyNogoPropFrame" : "lyNogoProp", { v: prop.from_version, n: prop.zones.length })}</p>
          <ul class="plain small">{prop.zones.map((z) => <li key={z.id}>{siteKnown(z.label) || z.id}</li>)}</ul>
          <div class="row wrap">
            <button type="button" class="btn sm primary" data-prop-keep="1" disabled={changed} onClick={() => void takeProposal(true)}>{t("lyNogoPropKeep")}</button>
            <button type="button" class="btn sm" data-prop-drop="1" disabled={changed} onClick={() => void takeProposal(false)}>{t("lyNogoPropDrop")}</button>
          </div>
        </div>
      )}
      {/* 第 3 轮 maps N1:有没核的建议、这一版又一个都没画时,先处理建议,不给确认空集 */}
      {draft && <p class="muted small" data-nogo-draft="1">{t("lyNogoDraft")}</p>}
      {nav && !current && !changed && !draft && !(prop && nav.zones.length === 0)
        && <button type="button" class="btn sm primary" onClick={() => setConfirming(true)}>{t("navConfirmBtn")}</button>}
      {/* 第 2 轮 maps N12:从发布对话框跳来的,确认完给「回去发布」 */}
      {current && typeof location !== "undefined" && /[?&]from=publish\b/.test(location.hash)
        && <a class="btn sm" href="#/admin/maps" data-back-publish="1">{t("lyNogoBackPublish")}</a>}
      {/* P1-32:勾「我确认」和输密码在同一个对话框里(原来是两个) */}
      {confirming && <SureDialog needPw={held.length > 0} onNo={() => setConfirming(false)} onYes={(pw) => confirm(pw)} />}
    </div>
  );
}

/** 一个区域在图上的样子(布置 → 禁行区、地图编辑器都用)。 */
export function zoneShape(meta: TabProps["meta"], z: Draft, sel = false) {
  return z.wall
    ? <polyline key={z.id} points={polyPx(meta, z.wall)} class={`nogo-line vwall-line${z.hard ? " hard" : ""}`} data-nogo-wall={z.id} />
    : <polygon key={z.id} points={polyPx(meta, z.polygon)} class={`${z.kind === "slow" ? "slow-area" : z.kind === "ignore" ? "ignore-area" : z.kind === "erase" ? "erase-area" : z.hard ? "nogo-area hard" : "nogo-area"}${sel ? " sel" : ""}`} />;
}

/** 区域的名字(屏上坐标;第 2 轮 P2-15、第 3 轮 setup N3)。 */
export function zoneName(s: { map: (x: number, y: number) => [number, number] | Pt }, z: Draft) {
  const ring = z.wall ?? z.polygon;
  if (!ring || ring.length === 0) return null;
  const name = siteKnown(z.label) || z.id;
  const [sx, sy] = nameSpot(ring.map(([x, y]) => s.map(x, y) as [number, number]), name, !!z.wall);
  const kind = z.wall ? "wall" : z.kind === "nogo" ? (z.hard ? "hard" : "nogo") : z.kind;
  return <text key={`n:${z.id}`} x={sx} y={sy} class={`nogo-name k-${kind}`} data-nogo-name={z.id}>{name}</text>;
}

export function zoneLegend(zs: Draft[]): LegendKey[] {
  return [...new Set(zs.map((z): LegendKey => (z.wall ? "vwall" : z.kind === "slow" ? "slow" : z.kind === "ignore" ? "ignore"
    : z.kind === "erase" ? "erase" : z.hard ? "hard" : "nogo")))];
}

/** 新画的区域:id 不重(按种类开头),名字、硬、限速、临时照表单。 */
export function newZone(draw: Draw, pts: Pt[], f: Form, have: Draft[], rev: number): Draft {
  let id = `${draw === "wall" ? "w" : draw === "slow" ? "s" : draw === "ignore" ? "i" : draw === "erase" ? "e" : "n"}${rev + 1}`;
  while (have.some((z) => z.id === id)) id += "x";
  const z: Draft = { id, kind: draw === "slow" || draw === "ignore" || draw === "erase" ? draw : "nogo", label: f.label.trim(), polygon: draw === "wall" ? [] : pts };
  if (draw === "wall") { z.wall = pts; delete (z as Partial<Draft>).polygon; }
  if (draw === "slow") z.max_speed_mps = f.speed;
  else if (f.hard && draw !== "ignore" && draw !== "erase") z.hard = true;
  if (f.temp) z.for_s = f.days * 86400;
  return z;
}

/** 布置 → 禁行区(11-10 起只看、只确认):禁行区、虚拟墙、限速区都在地图编辑器里画(用户:「所有动作都要在编辑器中
 *  完成」)。这里列出这一版有哪些、在不在生效,给「确认此版本」和「去编辑器里改」。 */
export function NogoTab(p: TabProps) {
  const nav = p.data.nav;
  const zones: Draft[] = nav?.zones ?? [];
  useEffect(() => { p.setDirty(false); p.registerSave(null); }, []);
  const edit = `#/admin/mapedit?map=${encodeURIComponent(p.map.map_id)}&version=${encodeURIComponent(p.map.version)}&tool=nogo`;
  return (
    <div class="ly-tab">
      <p.Map legend={zoneLegend(zones)} world={<>
        {zones.map((z) => zoneShape(p.meta, z))}
        {(nav?.held ?? []).map((z) => <polygon key={`held-${z.id}`} points={polyPx(p.meta, z.polygon)} class="nogo-area held" />)}
      </>} marks={(s) => <>{zones.map((z) => zoneName(s, z))}</>} />
      <div class="ly-side">
        <NogoStatus nav={nav} base={p.base} mapId={p.map.map_id} version={p.map.version} changed={false} say={p.say} reload={() => p.reload("nav")} />
        <a class="btn primary" href={edit} data-nogo-edit="1">{t("lyNogoEditInEditor")}</a>
        <p class="muted small">{t("lyNogoHint")}</p>
        <ul class="plain ly-list">
          {zones.length === 0 && <li class="muted small">{t("noNavZones")}</li>}
          {zones.map((z) => (
            <li key={z.id} class="row"><span><b>{siteKnown(z.label) || z.id}</b> <span class="muted small nowrap">{nogoLine(z)}</span></span></li>
          ))}
        </ul>
      </div>
    </div>
  );
}

/** 第 3 轮 setup N8:禁区不许重名(确认框里列名字,重名分不清是哪一块)。 */
function nameTaken(label: string, taken: string[]): boolean {
  return taken.includes(label.trim());
}

/** 默认名已经有了就往后加「2」「3」…… */
function freshName(base: string, taken: string[]): string {
  if (!taken.includes(base)) return base;
  for (let i = 2; ; i++) if (!taken.includes(`${base} ${i}`)) return `${base} ${i}`;
}

export function RenameNogo({ initial, taken, onClose, onSave }: { initial: string; taken: string[]; onClose: () => void; onSave: (label: string) => void }) {
  const [v, setV] = useState(initial);
  const dup = nameTaken(v, taken);
  const ok = v.trim().length > 0 && v.trim().length <= 64 && !dup;
  return (
    <Modal label={t("lyRename")} onClose={onClose}>
      <form class="form" onSubmit={(e) => { e.preventDefault(); if (ok) onSave(v.trim()); }}>
        <label class="field">{t("navName")}<input name="label" value={v} maxLength={64} autoFocus aria-invalid={dup || undefined} onInput={(e) => setV(e.currentTarget.value)} /></label>
        {dup && <p class="small bad" role="alert" data-dup="1">{t("lyNogoNameTaken", { z: v.trim() })}</p>}
        <div class="row end">
          <button type="button" class="btn" onClick={onClose}>{t("cancel")}</button>
          <button type="submit" class="btn primary" disabled={!ok}>{t("dlgApply")}</button>
        </div>
      </form>
    </Modal>
  );
}

/** 确认那一句(人话):勾上才能确认;删了、缩了禁行区(``needPw``)就在同一个框里再输密码。 */
export function SureDialog({ onYes, onNo, needPw }: { onYes: (pw?: string) => Promise<void>; onNo: () => void; needPw: boolean }) {
  const [sure, setSure] = useState(false);
  const [pw, setPw] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const go = async () => {
    setBusy(true);
    setErr("");
    try { await onYes(needPw ? pw : undefined); } catch (e) { setErr(t("failed", { why: e instanceof ApiError ? e.message : String(e) })); } finally { setBusy(false); }
  };
  return (
    <Modal label={t("navConfirmBtn")} onClose={onNo}>
      <form onSubmit={(e) => { e.preventDefault(); if (sure && (!needPw || pw)) void go(); }}>
        <p>{t("lyNogoConfirmLead")}</p>
        <label class="field-check"><input type="checkbox" name="sure" checked={sure} onChange={(e) => setSure(e.currentTarget.checked)} />{t("lyNogoSure")}</label>
        {needPw && (
          <label class="field">{t("lyNogoPw")}<input type="password" name="confirm_pw" autoComplete="current-password" value={pw}
            onInput={(e) => setPw(e.currentTarget.value)} /></label>
        )}
        {err && <p class="error small" role="alert">{err}</p>}
        <div class="row end">
          <button type="button" class="btn" onClick={onNo}>{t("cancel")}</button>
          <button type="submit" class="btn primary" disabled={!sure || (needPw && !pw) || busy}>{t("lyConfirm")}</button>
        </div>
      </form>
    </Modal>
  );
}

export function NogoForm({ kind, taken, onClose, onSave }: { kind: Draw; taken: string[]; onClose: () => void; onSave: (f: Form) => void }) {
  const [f, setF] = useState<Form>({
    label: freshName(kind === "wall" ? t("legendVWall") : kind === "slow" ? t("legendSlow") : kind === "ignore" ? t("legendIgnore") : kind === "erase" ? t("eraseLabel") : t("legendNoGo"), taken),
    hard: false, speed: 0.3, temp: false, days: 3,
  });
  // P1-37:限速 0.1–5 m/s,跟输入框的 min/max 一个口径(原来 0.05 也能存);范围写在框下面
  const speedOk = f.speed >= 0.1 && f.speed <= 5;
  const dup = nameTaken(f.label, taken);
  const ok = f.label.trim().length > 0 && f.label.trim().length <= 64 && (kind !== "slow" || speedOk) && !dup;
  return (
    <Modal label={kind === "wall" ? t("navFormTitleVWall") : kind === "slow" ? t("navFormTitleSlow") : kind === "ignore" ? t("navFormTitleIgnore") : kind === "erase" ? t("drawErase") : t("navFormTitleNoGo")} onClose={onClose}>
      <form class="form" onSubmit={(e) => { e.preventDefault(); if (ok) onSave(f); }}>
        <label class="field">{t("navName")}<input name="label" value={f.label} maxLength={64} autoFocus onInput={(e) => setF({ ...f, label: e.currentTarget.value })} /></label>
        {dup && <p class="small bad" role="alert" data-dup="1">{t("lyNogoNameTaken", { z: f.label.trim() })}</p>}
        {kind === "slow" ? (
          <label class="field">{t("navSpeed")}<input type="number" name="speed" min={0.1} max={5} step={0.1} value={f.speed}
            onInput={(e) => setF({ ...f, speed: Number(e.currentTarget.value) })} />
            <span class={speedOk ? "muted small" : "error small"}>{t("navSpeedRange")}</span></label>
        ) : kind === "ignore" || kind === "erase" ? null : (
          <label class="field-check"><input type="checkbox" name="hard" checked={f.hard} onChange={(e) => setF({ ...f, hard: e.currentTarget.checked })} />{t("navHard")}</label>
        )}
        <label class="field-check"><input type="checkbox" name="temp" checked={f.temp} onChange={(e) => setF({ ...f, temp: e.currentTarget.checked })} />{t("lyTemp")}</label>
        {f.temp && (
          <label class="field">{t("lyTempFor")}
            <select name="days" value={String(f.days)} onChange={(e) => setF({ ...f, days: Number(e.currentTarget.value) })}>
              {DAYS.map((d) => <option key={d} value={String(d)}>{t("lyTempDays", { n: d })}</option>)}
            </select>
          </label>
        )}
        <div class="row end">
          <button type="button" class="btn" onClick={onClose}>{t("cancel")}</button>
          <button type="submit" class="btn primary" disabled={!ok}>{t("dlgApply")}</button>
        </div>
      </form>
    </Modal>
  );
}

/** 名字写在哪(屏上坐标):区域装得下就在中间;墙、装不下的区域写在上边外面一点。 */
export function nameSpot(pts: [number, number][], name: string, line: boolean): [number, number] {
  const xs = pts.map((p) => p[0]), ys = pts.map((p) => p[1]);
  const cx = (Math.min(...xs) + Math.max(...xs)) / 2;
  const w = Math.max(...xs) - Math.min(...xs), h = Math.max(...ys) - Math.min(...ys);
  const textW = [...name].reduce((a, ch) => a + (ch.charCodeAt(0) > 0x2e80 ? 12 : 7), 0);
  if (!line && w >= textW + 8 && h >= 20) return [cx, (Math.min(...ys) + Math.max(...ys)) / 2];
  return [cx, Math.min(...ys) - 10];
}
