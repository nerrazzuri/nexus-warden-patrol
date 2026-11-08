// 布置 → 禁行区(W44 第三期,设计 §5.2、§9;规则是决策 66 和 W41 的,一条不改,只换成人话):
// - 三种:禁行区(圈一块)、虚拟墙(画一条线,站点存成约 0.3 m 宽的禁行带)、限速区(圈一块,填限速);可以设成临时的(几天)。
// - 加、收紧:保存就生效。删、缩小(放宽):要确认,确认之前机器人照旧绕开原来的范围;网页上确认放宽要再输一次密码。
// - 机器人还没收到在生效的那一份:写「等机器人确认中」。
// 改的先记在页面上,外框「保存」整份存(带打开时看到的修订号;别人改过回 409,外框说「刚才有人改过」)。
// 人员忽略区(W41,机器人在里面看见人不报)、抹掉区(机器人永远不去、画图时抹成没建图)也在这里画。
import { useEffect, useRef, useState } from "preact/hooks";
import { api, ApiError } from "./api";
import { Confirm, Modal } from "./dialogs";
import { clickGuard, startDrag, swallowClick } from "./dragpt";
import { t } from "./i18n";
import { siteKnown } from "./sitetext";
import { closesLoop, polyPx, toMap, type NavZones, type TabProps } from "./layoutpage";
import { pointInPolygon, type NavZone, type Pt } from "./mapview";
import { clientToMap } from "./routes";

type Draw = "nogo" | "wall" | "slow" | "ignore" | "erase";
interface Form { label: string; hard: boolean; speed: number; temp: boolean; days: number }
/** 新画的:站点要的格式(临时的带 for_s,站点按自己的钟换成到期时刻)。 */
type Draft = NavZone & { for_s?: number };
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

export function NogoTab(p: TabProps) {
  const nav = p.data.nav;
  const [zones, setZones] = useState<Draft[]>(nav?.zones ?? []);
  const [draw, setDraw] = useState<Draw | null>(null);
  const [pts, setPts] = useState<Pt[]>([]);
  const [form, setForm] = useState(false);
  const [removing, setRemoving] = useState<Draft | null>(null);
  const [confirming, setConfirming] = useState<"ask" | null>(null);
  const [behind, setBehind] = useState<string[]>([]);
  // P1-31:选中一个已画好的(点图上或点列表),能拖顶点、改名
  const [sel, setSel] = useState<string | null>(null);
  const [renaming, setRenaming] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const guard = useRef(clickGuard());

  const changed = JSON.stringify(zones) !== JSON.stringify(nav?.zones ?? []);
  useEffect(() => p.setDirty(changed), [changed]);
  useEffect(() => {
    p.registerSave(async () => {
      if (!nav) return;
      await api<NavZones>("POST", `${p.base}/zones`, { zones, base_revision: nav.revision });
      await p.reload("nav");
    });
    return () => p.registerSave(null);
  }, [zones, nav?.revision]);
  useEffect(() => {
    let live = true;
    api<{ robots: RobotRun[] }>("GET", "/api/robots").then((d) => {
      if (!live) return;
      setBehind((d.robots ?? []).filter((r) => r.running?.map_id === p.map.map_id && r.running?.map_version === p.map.version
        && r.running?.zones?.match === false).map((r) => r.robot_id));
    }).catch(() => {});
    return () => { live = false; };
  }, [nav?.revision]);

  const held = nav?.held ?? [];
  const current = !!nav?.confirmed?.current;
  const shown = zones;
  const minPts = draw === "wall" ? 2 : 3;

  async function confirm(pw?: string) {
    if (!nav) return;
    await api("POST", `${p.base}/zones/confirm`, {
      revision: nav.revision, confirm: true, ...(nav.zones.length === 0 ? { empty_ok: true } : {}), ...(pw ? { confirm_password: pw } : {}),
    });
    setConfirming(null);
    p.say(t("navConfirmedOk", { rev: nav.revision }));
    await p.reload("nav");
  }

  const cur = zones.find((z) => z.id === sel) ?? null;
  const curPts = cur ? (cur.wall ?? cur.polygon) : [];
  const dragVertex = (id: string, i: number) => (e: PointerEvent) => {
    startDrag(e, guard.current, (cx, cy) => {
      const m = clientToMap(root.current, p.meta, cx, cy);
      if (!m) return;
      const at: Pt = [m[0], m[1]];
      setZones((all) => all.map((z) => (z.id !== id ? z : z.wall
        ? { ...z, wall: z.wall.map((q, j) => (j === i ? at : q)) }
        : { ...z, polygon: z.polygon.map((q, j) => (j === i ? at : q)) })));
    });
  };
  return (
    <div class="ly-tab">
      <div ref={root} onClickCapture={(e) => swallowClick(guard.current, e)}>
      <p.Map
        drawing={!!draw}
        onPick={draw ? (px, py) => {
          if (draw !== "wall" && closesLoop(p.meta, pts, px, py)) { setForm(true); return; }
          setPts((d) => [...d, toMap(p.meta, px, py)]);
        } : (px, py) => {
          const at = toMap(p.meta, px, py);
          const hit = zones.find((z) => !z.wall && z.polygon.length >= 3 && pointInPolygon(at, z.polygon));
          if (hit) setSel(hit.id);
        }}
        world={<>
          {shown.map((z) => z.wall
            ? <polyline key={z.id} points={polyPx(p.meta, z.wall)} class="nogo-line" />
            : <polygon key={z.id} points={polyPx(p.meta, z.polygon)} class={`${z.kind === "slow" ? "slow-area" : z.kind === "ignore" ? "ignore-area" : z.kind === "erase" ? "erase-area" : z.hard ? "nogo-area hard" : "nogo-area"}${z.id === sel ? " sel" : ""}`} />)}
          {held.map((z) => <polygon key={`held-${z.id}`} points={polyPx(p.meta, z.polygon)} class="nogo-area held" />)}
          {pts.length > 0 && <polyline points={polyPx(p.meta, pts)} class={draw === "wall" ? "draft-line vwall" : "draft-line"} />}
        </>}
        marks={(s) => <>
          {pts.map(([x, y], i) => { const [sx, sy] = s.map(x, y); return <circle key={i} cx={sx} cy={sy} r={5} class="draft-pt" />; })}
          {!draw && cur && curPts.map(([x, y], i) => {
            const [sx, sy] = s.map(x, y);
            return <circle key={`v${i}`} cx={sx} cy={sy} r={7} class="vtx-handle" data-vtx={i} onPointerDown={dragVertex(cur.id, i)}><title>{t("lyDragVertex")}</title></circle>;
          })}
        </>} />
      </div>
      <div class="ly-side">
        <div class="nogo-status">
          {!nav ? <p class="muted">…</p> : current && held.length === 0
            ? <p class="ok-text">{t("lyNogoLive")}</p>
            : held.length > 0 ? <p class="warn-text">{t("lyNogoWaitYou", { names: held.map((z) => siteKnown(z.label) || z.id).join("、") })}</p>
            : <p class="warn-text">{t("lyNogoNeverConfirmed")}</p>}
          {behind.length > 0 && <p class="warn-text">{t("lyNogoWaitRobot", { ids: behind.join("、") })}</p>}
          {nav && !current && !changed && <button type="button" class="btn sm primary" onClick={() => setConfirming("ask")}>{t("navConfirmBtn")}</button>}
          {/* 第 2 轮 maps N12:从发布对话框跳来的,确认完给「回去发布」 */}
          {current && typeof location !== "undefined" && /[?&]from=publish\b/.test(location.hash)
            && <a class="btn sm" href="#/admin/maps" data-back-publish="1">{t("lyNogoBackPublish")}</a>}
        </div>
        {draw ? (
          <div class="row wrap">
            <span class="muted small">{draw === "wall" ? t("vwallDrawHint", { n: pts.length, w: 0.3 })
              : draw === "erase" ? t("eraseDrawHint", { n: pts.length }) : t("navDrawHint", { n: pts.length })}</span>
            {/* 第 2 轮 P1-51:「不会删已画的禁行区」原来只在悬停提示里,触屏看不到 */}
            {draw === "erase" && <span class="muted small" data-erase-tip="1">{t("drawEraseTip")}</span>}
            <button type="button" class="btn sm" disabled={!pts.length} onClick={() => setPts(pts.slice(0, -1))}>{t("undoPoint")}</button>
            <button type="button" class="btn sm" onClick={() => { setDraw(null); setPts([]); }}>{t("cancel")}</button>
            <button type="button" class="btn sm primary" disabled={pts.length < minPts} onClick={() => setForm(true)}>{t("lyDrawDone")}</button>
          </div>
        ) : (
          // P1-33/38:分两组 —— 管机器人怎么走的、管人员检测的(忽略区不是「机器人不进」);「不可通行」写明不是删禁行区
          <div class="nogo-groups">
            <p class="small muted">{t("nogoGroupMove")}</p>
            <div class="row wrap">
              <button type="button" class="btn" onClick={() => { setDraw("nogo"); setPts([]); }}>{t("drawNoGo")}</button>
              <button type="button" class="btn" onClick={() => { setDraw("wall"); setPts([]); }}>{t("drawVWall")}</button>
              <button type="button" class="btn" onClick={() => { setDraw("slow"); setPts([]); }}>{t("drawSlow")}</button>
              <button type="button" class="btn" title={t("drawEraseTip")} onClick={() => { setDraw("erase"); setPts([]); }}>{t("drawErase")}</button>
            </div>
            <p class="small muted">{t("nogoGroupPeople")}</p>
            <div class="row wrap">
              <button type="button" class="btn" onClick={() => { setDraw("ignore"); setPts([]); }}>{t("drawIgnore")}</button>
            </div>
          </div>
        )}
        <p class="muted small">{t("lyNogoHint")}</p>
        <ul class="plain ly-list">
          {shown.length === 0 && <li class="muted small">{t("noNavZones")}</li>}
          {shown.map((z) => (
            <li key={z.id} class="row">
              <span><button type="button" class={z.id === sel ? "linklike on" : "linklike"} data-pick-zone={z.id}
                onClick={() => setSel(z.id === sel ? null : z.id)}><b>{siteKnown(z.label) || z.id}</b></button> <span class="muted small">{nogoLine(z)}</span></span>
              {z.id === sel && <button type="button" class="btn sm push" data-rename="1" onClick={() => setRenaming(true)}>{t("lyRename")}</button>}
              <button type="button" class={z.id === sel ? "btn sm" : "btn sm push"} onClick={() => setRemoving(z)}>{t("remove")}</button>
            </li>
          ))}
          {cur && <li class="muted small">{t("lyDragVertex")}</li>}
        </ul>
      </div>
      {renaming && cur && (
        <RenameNogo initial={cur.label} onClose={() => setRenaming(false)}
          onSave={(label) => { setZones(zones.map((z) => (z.id === cur.id ? { ...z, label } : z))); setRenaming(false); }} />
      )}
      {form && draw && (
        <NogoForm kind={draw} onClose={() => setForm(false)} onSave={(f) => {
          let id = `${draw === "wall" ? "w" : draw === "slow" ? "s" : draw === "ignore" ? "i" : draw === "erase" ? "e" : "n"}${(nav?.revision ?? 0) + 1}`;
          while (zones.some((z) => z.id === id)) id += "x";
          const z: Draft = { id, kind: draw === "slow" || draw === "ignore" || draw === "erase" ? draw : "nogo", label: f.label.trim(), polygon: draw === "wall" ? [] : pts };
          if (draw === "wall") { z.wall = pts; delete (z as Partial<Draft>).polygon; }
          if (draw === "slow") z.max_speed_mps = f.speed;
          else if (f.hard && draw !== "ignore" && draw !== "erase") z.hard = true;
          if (f.temp) z.for_s = f.days * 86400;
          setZones([...zones, z]);
          setForm(false);
          setDraw(null);
          setPts([]);
        }} />
      )}
      {removing && (
        <Confirm text={t("lyNogoRemoveAsk", { label: siteKnown(removing.label) || removing.id })} yes={t("remove")} danger onNo={() => setRemoving(null)}
          onYes={() => { const z = removing; setRemoving(null); setZones(zones.filter((o) => o.id !== z.id)); }} />
      )}
      {/* P1-32:勾「我确认」和输密码在同一个对话框里(原来是两个) */}
      {confirming === "ask" && (
        <SureDialog needPw={held.length > 0} onNo={() => setConfirming(null)} onYes={(pw) => confirm(pw)} />
      )}
    </div>
  );
}

function RenameNogo({ initial, onClose, onSave }: { initial: string; onClose: () => void; onSave: (label: string) => void }) {
  const [v, setV] = useState(initial);
  const ok = v.trim().length > 0 && v.trim().length <= 64;
  return (
    <Modal label={t("lyRename")} onClose={onClose}>
      <form class="form" onSubmit={(e) => { e.preventDefault(); if (ok) onSave(v.trim()); }}>
        <label class="field">{t("navName")}<input name="label" value={v} maxLength={64} autoFocus onInput={(e) => setV(e.currentTarget.value)} /></label>
        <div class="row end">
          <button type="button" class="btn" onClick={onClose}>{t("cancel")}</button>
          <button type="submit" class="btn primary" disabled={!ok}>{t("dlgApply")}</button>
        </div>
      </form>
    </Modal>
  );
}

/** 确认那一句(人话):勾上才能确认;删了、缩了禁行区(``needPw``)就在同一个框里再输密码。 */
function SureDialog({ onYes, onNo, needPw }: { onYes: (pw?: string) => Promise<void>; onNo: () => void; needPw: boolean }) {
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

function NogoForm({ kind, onClose, onSave }: { kind: Draw; onClose: () => void; onSave: (f: Form) => void }) {
  const [f, setF] = useState<Form>({
    label: kind === "wall" ? t("legendVWall") : kind === "slow" ? t("legendSlow") : kind === "ignore" ? t("legendIgnore") : kind === "erase" ? t("eraseLabel") : t("legendNoGo"),
    hard: false, speed: 0.3, temp: false, days: 3,
  });
  // P1-37:限速 0.1–5 m/s,跟输入框的 min/max 一个口径(原来 0.05 也能存);范围写在框下面
  const speedOk = f.speed >= 0.1 && f.speed <= 5;
  const ok = f.label.trim().length > 0 && f.label.trim().length <= 64 && (kind !== "slow" || speedOk);
  return (
    <Modal label={kind === "wall" ? t("navFormTitleVWall") : kind === "slow" ? t("navFormTitleSlow") : kind === "ignore" ? t("navFormTitleIgnore") : kind === "erase" ? t("drawErase") : t("navFormTitleNoGo")} onClose={onClose}>
      <form class="form" onSubmit={(e) => { e.preventDefault(); if (ok) onSave(f); }}>
        <label class="field">{t("navName")}<input name="label" value={f.label} maxLength={64} autoFocus onInput={(e) => setF({ ...f, label: e.currentTarget.value })} /></label>
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
