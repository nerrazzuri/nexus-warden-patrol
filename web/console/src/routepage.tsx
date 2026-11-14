// 巡检路线页(2026-10-14,管理员):选地图版本 → 图上看这一版上的路线(折线 + 带号的点)→ 点图加点、
// 拖点改位置、拖圆形把手转朝向、调顺序、删点、设点上的动作 → 存(站点逐点校验,错的点标红)。
// 每条路线下面是它的排程。站点存的路线、排程是唯一真理源;存的时候带 base_revision,别人改过的不会被盖掉。
import type { FunctionComponent } from "preact";
import { useCallback, useEffect, useRef, useState } from "preact/hooks";
import { api, ApiError, enc } from "./api";
import { Confirm } from "./dialogs";
import { startDrag, clickGuard, swallowClick } from "./dragpt";
import { colon, joinList, t, type Key } from "./i18n";
import { SaveCancelled, type OwnLayer } from "./layoutpage";
import { MapCanvas } from "./mapcanvas";
import { PoseMarker } from "./posemarker";
import { DispatchOnce } from "./routedispatch";
import { toPx, type PreviewMeta } from "./mapview";
import "./routes.css";
import {
  addPoint,
  clientToMap,
  degOf,
  deletePoint,
  dwellOf,
  handleAt,
  hasAction,
  movePoint,
  patchPoint,
  radOf,
  reorder,
  setDwell,
  toggleAction,
  yawToward,
  clock,
  type Draft,
  type RouteEta,
  type PointProblem,
  type Route,
  type RoutePoint,
  type RouteSchedule,
  type RouteView,
  freeId,
  routeLabel,
} from "./routes";
import { rt } from "./routes_i18n";
import { siteKnown, siteStr } from "./sitetext";
import { clip, siteDown } from "./data";

type Say = (s: string) => void;
interface MapRow { map_id: string; version: string; note: string }

export const NAME_RE = /^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/;
const DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"] as const;
/** P1-39:点改完多久去站点查一次(拖点时不用每一下都查)。 */
export const CHECK_DELAY_MS = 600;
const PT_R = 11;
const HANDLE_PX = 30;

function errText(e: unknown): string {
  return t("failed", { why: e instanceof ApiError ? e.message : String(e) });
}

const same = (a: Draft | null, r: Route | undefined): boolean =>
  !!a && !!r && !a.isNew && JSON.stringify(a.points) === JSON.stringify(r.waypoints) && (a.title ?? "") === (r.title ?? "");

/** 嵌进「布置」页(W44 第三期):图、地图版本、保存按钮都用外框的;不显示坐标数字(设计 §1:改路线不用看到坐标)。 */
export interface RouteEmbed {
  map: MapRow;
  meta: PreviewMeta;
  Map: FunctionComponent<OwnLayer>;
  setDirty: (b: boolean) => void;
  registerSave: (fn: (() => Promise<void>) | null) => void;
}

/** 布置页里正在改的那条路线:标签重建(「看最新的」、退回历史)以后自动再打开,不退回列表(演示站点实测)。
 *  自己点「返回」就清掉。 */
let reopen: { map: string; id: string } | null = null;

/** ``kind``(W73):``patrol`` 巡逻路线(默认,带排程);``guard`` 防区路线(只给布防值守用,没有排程,能按防区生成)。 */
export function RoutesPage({ say, embed, kind = "patrol" }: { say: Say; embed?: RouteEmbed; kind?: "patrol" | "guard" }) {
  const guardKind = kind === "guard";
  const [maps, setMaps] = useState<MapRow[]>(embed ? [embed.map] : []);
  const [selState, setSel] = useState<MapRow | null>(embed?.map ?? null);
  const sel = embed ? embed.map : selState;
  const [metaState, setMeta] = useState<PreviewMeta | null>(embed?.meta ?? null);
  const meta = embed ? embed.meta : metaState;
  const [view, setView] = useState<RouteView | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [orig, setOrig] = useState<Route | undefined>(undefined);
  const [pi, setPi] = useState<number | null>(null);
  const [problems, setProblems] = useState<PointProblem[]>([]);
  const [conflict, setConflict] = useState(false);
  const [removing, setRemoving] = useState(false);
  // 2026-10-15 用户:所有路线一起画在图上太乱 —— 图上只画列表里选中的那一条;要对照别的路线再打开
  const [showOthers, setShowOthers] = useState(false);
  const [genOpen, setGenOpen] = useState(false);
  const [genNotes, setGenNotes] = useState<string[]>([]);
  const [genStandby, setGenStandby] = useState(false);
  const [eta, setEta] = useState<RouteEta | null>(null);
  const root = useRef<HTMLDivElement>(null);
  const guard = useRef(clickGuard());
  // 外审 R2(2026-10-15 下午):读、存、删、重新拉的回包都可能晚到 —— 出发时记下「哪张图、第几次编辑」,
  // 回来时对不上就不碰页面(服务端已经存下的不撤,只是不把它放进现在这一页)。换图、进编辑、新建、回列表、
  // 删掉都算新的一次编辑。
  const mapKey = sel ? `${sel.map_id}\u0000${sel.version}` : "";
  const live = useRef({ map: mapKey, gen: 0 });
  if (live.current.map !== mapKey) live.current = { map: mapKey, gen: live.current.gen + 1 };
  const ticket = () => ({ ...live.current });
  const still = (tk: { map: string; gen: number }) => live.current.map === tk.map && live.current.gen === tk.gen;
  const sameMap = (tk: { map: string }) => live.current.map === tk.map;
  const nextEdit = () => { live.current = { ...live.current, gen: live.current.gen + 1 }; };

  useEffect(() => {
    if (embed) return;
    api<{ maps: MapRow[] }>("GET", "/api/maps").then((d) => {
      setMaps(d.maps);
      setSel((s) => s ?? d.maps[d.maps.length - 1] ?? null);
    }).catch((e) => say(errText(e)));
  }, []);
  const base = sel ? `/api/maps/${enc(sel.map_id)}/${enc(sel.version)}` : "";
  const load = useCallback(() => {
    if (!sel) return Promise.resolve();
    const tk = ticket();
    return api<RouteView>("GET", `/api/routes?map_id=${enc(sel.map_id)}&map_version=${enc(sel.version)}&kind=${kind}`)
      .then((v) => { if (sameMap(tk)) setView(v); })
      .catch((e) => { if (sameMap(tk)) { setView(null); say(errText(e)); } });
  }, [sel?.map_id, sel?.version]);
  useEffect(() => {
    setMeta(null);
    setDraft(null);
    setOrig(undefined);
    setPi(null);
    setProblems([]);
    setConflict(false);
    setView(null);
    if (!base) return;
    const tk = ticket();
    if (!embed) {
      api<PreviewMeta>("GET", `${base}/preview`).then((m) => { if (sameMap(tk)) setMeta(m); })
        .catch(() => { if (sameMap(tk)) setMeta(null); });
    }
    void load();
  }, [base]);

  const routes = view?.routes ?? [];
  const [allIds, setAllIds] = useState<string[]>([]);
  const [retired, setRetired] = useState<{ ids: string[]; titles: Record<string, string> }>({ ids: [], titles: {} });
  const autoId = () => freeId("route", [...allIds, ...routes.map((r) => r.id)], view, "route");
  // 第 8 轮 W8-08:这一版上没有路线时,看同一张图的别的版本上有没有(有就说在哪一版,客户以为路线丢了)
  const [elsewhere, setElsewhere] = useState<Route[]>([]);
  const noneHere = !!view && routes.length === 0;
  useEffect(() => {
    setElsewhere([]);
    if (!noneHere || !sel) return;
    api<RouteView>("GET", `/api/routes?kind=${kind}`)
      .then((v) => setElsewhere(v.routes.filter((r) => r.map_id === sel.map_id && r.map_version !== sel.version)))
      .catch(() => setElsewhere([]));
  }, [noneHere, sel?.map_id, sel?.version]);
  const dirty = !!draft && (draft.isNew ? draft.points.length > 0 : !same(draft, orig));
  const bad = new Map<number, string>();
  for (const p of problems) if (p.index !== null) bad.set(p.index, siteStr(p.problem));
  const wholeProblems = problems.filter((p) => p.index === null);
  // 11-05 现场第 15、35 条:刚存下的这一版里要原地转又贴墙的点(改了以后不算,存了再看)
  const warns = new Map<number, string>();
  if (!dirty && draft && orig && orig.id === draft.id) for (const w of orig.warnings ?? []) warns.set(w.index, w.warning);
  // W44 第三期:两点之间走不通(站点逐段查,``segment: [i, i+1]``)
  const badSegs = problems.filter((p) => Array.isArray(p.segment)).map((p) => p.segment as [number, number]);

  useEffect(() => {
    if (!embed || draft || !view || !reopen || reopen.map !== mapKey) return;
    const r = view.routes.find((x) => x.id === reopen?.id);
    if (r) edit(r);
  }, [view]);
  function edit(r: Route) {
    if (embed) reopen = { map: mapKey, id: r.id };
    nextEdit();
    setDraft({ id: r.id, title: r.title ?? "", isNew: false, base: r.revision, points: r.waypoints, policy: r.policy, map: mapKey });
    setOrig(r);
    setPi(null);
    setProblems([]);
    setConflict(false);
    setGenNotes([]);
  }
  /** W73:按防区生成的草稿 → 新建路线的编辑页(还没存;问题照存路线时那样标出来)。 */
  function fromGenerated(id: string, points: RoutePoint[], errs: PointProblem[], notes: string[], standby = false) {
    nextEdit();
    setGenOpen(false);
    setDraft({ id, isNew: true, base: 0, points, policy: {}, map: mapKey });
    setOrig(undefined);
    setPi(null);
    setProblems(errs);
    setConflict(false);
    setGenNotes([points.length ? rt("guardGenDone", { n: points.length }) : rt("guardGenNone"), ...notes]);
    setGenStandby(standby);
  }
  // 第 4 轮 setup N4:点「+ 新建路线」后光标进名字框(autoFocus 只在页面第一次载入时管用)
  const nameBox = useRef<HTMLInputElement>(null);
  const isNew = !!draft?.isNew;
  useEffect(() => { if (isNew) nameBox.current?.focus(); }, [isNew]);
  function startNew() {
    // 新建:右侧栏换成编辑页,名字在编辑页顶上填(2026-10-15 用户:原来名字框夹在路线列表和点位列表中间)
    nextEdit();
    setDraft({ id: "", title: "", isNew: true, base: 0, points: [], policy: {}, map: mapKey });
    // 第 8 轮 W8-11:写中文名时自动给编号 —— 编号全站唯一(别的图、别的版本上的也算)
    // 第 11 轮 W11-01:删掉过的编号也算用过
    api<RouteView>("GET", "/api/routes").then((v) => {
      setAllIds([...v.routes.map((x) => x.id), ...(v.retired_routes ?? [])]);
      setRetired({ ids: v.retired_routes ?? [], titles: v.retired_titles?.route ?? {} });
    }).catch(() => { setAllIds([]); setRetired({ ids: [], titles: {} }); });
    setOrig(undefined);
    setPi(null);
    setProblems([]);
    setConflict(false);
  }
  // P1-39:改了点就让站点查一遍(跟存的时候同一套:穿墙、在禁行区里、走不通),当场标红;不存
  const checkGen = useRef(0);
  const pointsKey = draft ? JSON.stringify(draft.points) : "";
  useEffect(() => {
    if (!draft || !sel || draft.points.length === 0 || !dirty) return;
    const my = ++checkGen.current;
    const id = window.setTimeout(() => {
      api<{ errors: PointProblem[] }>("POST", "/api/route-check", { map_id: sel.map_id, map_version: sel.version, waypoints: draft.points })
        .then((d) => { if (my === checkGen.current) setProblems(d.errors ?? []); })
        .catch(() => { /* 老站点没有这个接口:存的时候照样会查 */ });
    }, CHECK_DELAY_MS);
    return () => window.clearTimeout(id);
  }, [pointsKey, sel?.map_id, sel?.version]);

  function change(points: RoutePoint[], keepProblems = false) {
    setDraft((d) => (d ? { ...d, points } : d));
    if (!keepProblems) setProblems([]);
  }

  function pick(px: number, py: number) {
    if (!meta || !draft) return;
    const [x, y] = [Math.round((meta.left_x + px * meta.m_per_px) * 100) / 100, Math.round((meta.top_y - py * meta.m_per_px) * 100) / 100];
    change(addPoint(draft.points, x, y));
    setPi(draft.points.length);
  }

  /** ``strict``:失败了抛出去(嵌进布置页时外框按 409 说「刚才有人改过」)。 */
  async function save(strict = false) {
    if (!draft || !sel) return;
    if (draft.map !== mapKey) {
      // 草稿不是在现在选的这张图上编的(外审 R2):不发,不然点会改绑到别的图上
      say(rt("routeWrongMap"));
      return;
    }
    const tk = ticket();
    setProblems([]);
    setConflict(false);
    try {
      const r = await api<Route>("POST", `/api/routes/${enc(draft.id)}`, {
        map_id: sel.map_id, map_version: sel.version, waypoints: draft.points, policy: draft.policy, base_revision: draft.base, kind,
        ...(draft.title != null ? { title: draft.title } : {}),
      });
      if (!still(tk)) return;                 // 已经离开这条路线 / 这张图:存下了,但不放进现在这一页
      say(rt("routeSaved", { rev: r.revision }));
      setDraft({ id: r.id, title: r.title ?? "", isNew: false, base: r.revision, points: r.waypoints, policy: r.policy, map: tk.map });
      setOrig(r);
      await load();
    } catch (e) {
      if (!still(tk)) return;
      if (e instanceof ApiError && e.status === 409) setConflict(true);
      const errs = e instanceof ApiError ? (e.data as { errors?: PointProblem[] } | undefined)?.errors : undefined;
      if (Array.isArray(errs) && errs.length) {
        setProblems(errs);
        const first = errs.find((x) => x.index !== null);
        if (first) setPi(first.index);
      }
      say(errText(e));
      if (strict) throw e;
    }
  }
  async function reloadRoute() {
    if (!draft) return;
    const tk = ticket();
    try {
      const r = await api<Route>("GET", `/api/routes/${enc(draft.id)}`);
      if (!still(tk)) return;
      if (sel && (r.map_id !== sel.map_id || r.map_version !== sel.version)) {
        // 别人把这条路线改到了别的图上:不放进这张图的编辑页
        say(rt("routeMovedMap", { map: `${r.map_id} · v${r.map_version}` }));
        setDraft(null);
        await load();
        return;
      }
      edit(r);
      await load();
    } catch (e) {
      if (!still(tk)) return;
      say(errText(e));
      setDraft(null);
      await load();
    }
  }
  async function del() {
    if (!draft) return;
    setRemoving(false);
    const tk = ticket();
    try {
      await api("POST", `/api/routes/${enc(draft.id)}/delete`, { base_revision: draft.base });
      if (!still(tk)) return;
      say(rt("routeDeleted"));
      nextEdit();
      setDraft(null);
      setOrig(undefined);
      await load();
    } catch (e) {
      if (!still(tk)) return;
      say(errText(e));
    }
  }

  // ---- 图上
  const pts = draft?.points ?? [];
  const others = showOthers ? routes.filter((r) => r.id !== draft?.id) : [];
  const schedCount = (id: string) => (view?.schedules ?? []).filter((s) => s.mission === id).length;
  const line = (ps: { x: number; y: number }[]) => ps.map((p) => { const q = toPx(meta!, p.x, p.y); return `${q.px},${q.py}`; }).join(" ");

  function dragPoint(i: number) {
    return (e: PointerEvent) => {
      setPi(i);
      startDrag(e, guard.current, (cx, cy) => {
        const m = meta && clientToMap(root.current, meta, cx, cy);
        if (m) setDraft((d) => (d ? { ...d, points: movePoint(d.points, i, m[0], m[1]) } : d));
      });
    };
  }
  function dragHandle(i: number) {
    return (e: PointerEvent) => {
      startDrag(e, guard.current, (cx, cy) => {
        const m = meta && clientToMap(root.current, meta, cx, cy);
        if (!m) return;
        setDraft((d) => {
          if (!d) return d;
          const p = d.points[i];
          const yaw = yawToward(p.x, p.y, m[0], m[1]);
          return yaw === null ? d : { ...d, points: patchPoint(d.points, i, { yaw }) };
        });
      });
    };
  }

  // 第 12 轮 W11-01:查全站(别的版本上的、删掉用过的编号),不是只查这一版
  const nameTaken = !!draft?.isNew && (routes.some((r) => r.id === draft.id) || allIds.includes(draft.id));
  // 第 13 轮 W13-03 ①:撞的是删掉的那条用过的编号 —— 站点上没有这条路线,说清是谁用过
  const retiredHit = nameTaken && !!draft && retired.ids.includes(draft.id) && !routes.some((r) => r.id === draft.id);
  const takenMsg = !retiredHit ? rt("routeNameTaken")
    : retired.titles[draft!.id] ? rt("routeIdRetired", { title: retired.titles[draft!.id] }) : rt("routeIdRetiredNoName");
  const canSave = !!draft && dirty && pts.length > 0 && NAME_RE.test(draft.id) && !nameTaken;
  useEffect(() => { embed?.setDirty(dirty); }, [dirty]);
  useEffect(() => {
    if (!embed) return;
    // 第 2 轮 P1-39 / layout N3:有改动但存不了(名字不对、重名、没有点)时按顶上「保存」说清为什么,不是没反应
    const why = !draft || !dirty ? null
      : nameTaken ? takenMsg
      : !NAME_RE.test(draft.id) ? rt("routeNameHint")
      : pts.length === 0 ? rt("routeNoPoints") : null;
    embed.registerSave(canSave ? () => save(true)
      : why ? async () => { say(why); throw new SaveCancelled(); } : null);
    return () => embed.registerSave(null);
  });
  function back() {
    if (dirty && !window.confirm(rt("routeUnsaved"))) return;
    reopen = null;
    nextEdit();
    setDraft(null);
    setOrig(undefined);
    setPi(null);
    setProblems([]);
    setConflict(false);
    setGenNotes([]);
  }

  const etaFor = draft && !draft.isNew && !dirty ? draft.id : "";
  useEffect(() => {
    setEta(null);
    if (!etaFor) return;
    const tk = ticket();
    api<RouteEta>("GET", `/api/routes/${enc(etaFor)}/eta`).then((d) => { if (still(tk)) setEta(d); }).catch(() => {});
  }, [etaFor, draft?.base]);
  const etaOf = new Map((eta?.waypoints ?? []).map((w) => [w.name, w]));

  const selPoint = draft && pi !== null ? draft.points[pi] : undefined;
  const mySchedules = (view?.schedules ?? []).filter((s) => draft && !draft.isNew && s.mission === draft.id);

  const MapLike = (embed ? embed.Map : MapCanvas) as FunctionComponent<Parameters<typeof MapCanvas>[0]>;
  return (
    <div class={embed ? "routes-embed" : "admin"}>
      <section class={embed ? undefined : "panel"}>
        {/* P2-14:嵌在「布置」里不要这一栏(原来用 hidden,被 .panel-head 的 flex 盖掉,出了两个地图版本框) */}
        {!embed && <div class="panel-head">
          <h1>{rt("routesTitle")}</h1>
          <label class="field-inline">{rt("routesMap")}
            <select value={sel ? `${sel.map_id}\u0000${sel.version}` : ""} onChange={(e) => {
              if (dirty && !window.confirm(rt("routeUnsaved"))) return;
              const [m, v] = e.currentTarget.value.split("\u0000");
              setSel(maps.find((x) => x.map_id === m && x.version === v) ?? null);
            }}>
              {maps.map((m) => <option key={`${m.map_id}:${m.version}`} value={`${m.map_id}\u0000${m.version}`}>{m.map_id} · v{m.version}{m.note ? ` · ${clip(siteKnown(m.note))}` : ""}</option>)}
            </select>
          </label>
          <span class="push" />
          {dirty && <span class="muted small" role="status">{rt("routeUnsaved")}</span>}
        </div>}
        <div class="routesplit">
          <div class="routemap" ref={root} onClickCapture={(e) => swallowClick(guard.current, e)}>
            {!sel || !meta ? <p class="empty">{t(siteDown.value ? "loadRetry" : "noMap")}</p> : (
              <MapLike meta={meta} raster={`${base}/preview.png`} label={guardKind ? rt("guardTitle") : rt("routesTitle")}
                drawing={!!draft} onPick={draft ? pick : undefined}
                overlay={!draft && routes.length > 0 ? <p class="routepick-hint small" data-route-hint="1">{rt("routePickHint")}</p> : undefined}
                world={<>
                  {others.map((r) => <polyline key={r.id} points={line(r.waypoints)} class="route-line other" data-route={r.id} />)}
                  {draft && pts.length > 1 && <polyline points={line(pts)} class="route-line" data-route={draft.id} />}
                  {badSegs.map(([a, b]) => pts[a] && pts[b] && <polyline key={`seg${a}`} points={line([pts[a], pts[b]])} class="route-line bad-seg" data-bad-seg={a} />)}
                </>}
                marks={(s) => (
                  <>
                    {/* 路线的点:定位箭头(posemarker.tsx),中间是序号,三角尖指着到点后的朝向;选中的那一个三角尖能拖 */}
                    {others.map((r) => r.waypoints.map((p, i) => {
                      const h = handleAt(meta, s, p.x, p.y, p.yaw, HANDLE_PX);
                      return <PoseMarker key={`${r.id}:${i}`} x={h.x} y={h.y} hx={h.hx} hy={h.hy} r={8} label={i + 1}
                        class="route-pt other" />;
                    }))}
                    {pts.map((p, i) => {
                      const h = handleAt(meta, s, p.x, p.y, p.yaw, HANDLE_PX);
                      return (
                        <PoseMarker key={i} x={h.x} y={h.y} hx={h.hx} hy={h.hy} r={PT_R} label={i + 1} selected={i === pi}
                          class={`route-pt${i === pi ? " on" : ""}${bad.has(i) ? " bad" : warns.has(i) ? " warn" : ""}`}
                          attrs={{ "data-point": String(i), onPointerDown: dragPoint(i),
                            onClick: (e: MouseEvent) => { e.stopPropagation(); setPi(i); } } as Record<string, unknown>}
                          handle={i === pi ? { data: i, onPointerDown: dragHandle(i) } : undefined}>
                          <title>{`${i + 1}. ${p.name}${bad.has(i) ? ` — ${bad.get(i)}` : warns.has(i) ? ` — ${warns.get(i)}` : ""}`}</title>
                        </PoseMarker>
                      );
                    })}
                  </>
                )} />
            )}
          </div>
          <div class="routeside">
            {!draft ? (
              <>
            {/* 列表页:只有路线列表;点一条或「新建路线」换成编辑页(跟手机一样) */}
            <div class="routeside-head">
              <h2>{guardKind ? rt("guardTitle") : rt("routesTitle")}</h2>
              {guardKind && <button type="button" class="btn sm" data-guard-gen="1" onClick={() => setGenOpen(!genOpen)} disabled={!sel || !meta}
                aria-pressed={genOpen}>{rt("guardGenBtn")}</button>}
              <button type="button" class="btn sm primary" onClick={startNew} disabled={!sel || !meta}>{rt("routeNewBtn")}</button>
            </div>
            {guardKind && <p class="muted small">{rt("guardOnlyArmed")}</p>}
            {genOpen && sel && <GuardGenerate map={sel} taken={routes.map((r) => r.id)} say={say} onDone={fromGenerated} onClose={() => setGenOpen(false)} />}
            {routes.length === 0 && <p class="muted small">{guardKind ? rt("guardNone") : rt("routesNone")}</p>}
            {routes.length === 0 && elsewhere.length > 0 && (
              <p class="muted small" data-routes-elsewhere="1">
                {[...new Set(elsewhere.map((r) => r.map_version))].map((v) => {
                  const here = elsewhere.filter((r) => r.map_version === v);
                  return rt("routesOnOther", { v, n: here.length, names: here.map((r) => r.id).join("、") });
                }).join(" ")}
              </p>
            )}
            <ul class="routelist" aria-label={guardKind ? rt("guardTitle") : rt("routesTitle")}>
              {routes.map((r) => {
                const n = schedCount(r.id);
                return (
                  <li key={r.id}>
                    <button type="button" class="routerow" data-route-row={r.id} onClick={() => edit(r)}>
                      <span class="routerow-name">{routeLabel(r)}</span>
                      <span class="muted small">
                        {rt("routePointsN", { n: r.waypoints.length })}
                        {n > 0 && ` · ${rt("routeSchedN", { n })}`}
                        {!r.bound && <span class="bad"> · {rt("routeUnboundTag")}</span>}
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
            {routes.length > 1 && (
              <label class="small field-check">
                <input type="checkbox" checked={showOthers} onChange={(e) => setShowOthers(e.currentTarget.checked)} />
                {rt("routesShowOthers")}
              </label>
            )}
              </>
            ) : (
              <>
                {/* 编辑页 */}
                <button type="button" class="link routeback" onClick={back}>{rt("routeBack")}</button>
                {draft.isNew ? (
                  <label class="routename">
                    <span class="small">{rt("routeName")}</span>
                    <input aria-label={rt("routeName")} placeholder={rt("routeName")} value={draft.title || draft.id} maxLength={40} ref={nameBox}
                      aria-invalid={nameTaken || undefined}
                      onInput={(e) => {
                        // 第 8 轮 W8-11:只有字母数字的当编号;写了中文(或别的)当显示名,编号自动给
                        const v = e.currentTarget.value.trim();
                        setDraft((d) => (d ? (NAME_RE.test(v) || !v ? { ...d, id: v, title: "" } : { ...d, id: autoId(), title: v }) : d));
                      }} />
                    <span class={`small${nameTaken ? " bad" : " muted"}`} data-route-id-hint="1">
                      {nameTaken ? takenMsg : draft.title ? rt("routeAutoId", { id: draft.id }) : rt("routeNameHint")}
                    </span>
                  </label>
                ) : (
                  <>
                    <h2>{draft.title || draft.id}</h2>
                    <label class="routename">
                      <span class="small">{rt("routeTitle")}</span>
                      <input name="routeTitle" aria-label={rt("routeTitle")} value={draft.title ?? ""} maxLength={40} placeholder={draft.id}
                        onInput={(e) => { const title = e.currentTarget.value; setDraft((d) => (d ? { ...d, title } : d)); }} />
                      <span class="small muted">{rt("routeIdIs", { id: draft.id })}</span>
                    </label>
                  </>
                )}
                {sel && <p class="muted small">{rt("routeBind", { v: sel.version })}</p>}
                {orig && !orig.bound && <p class="muted small">{rt("routeUnbound")}</p>}
                <p class="muted small">{rt("routeAddHint")}</p>
                {conflict && (
                  <p class="small" role="alert">{rt("routeConflict")} <button type="button" class="link" onClick={() => void reloadRoute()}>{rt("routeReload")}</button></p>
                )}
                {problems.length > 0 && <p class="small bad" role="alert">{rt("routeProblems", { n: problems.length })}</p>}
                {wholeProblems.map((p, i) => <p key={i} class="small bad">{siteStr(p.problem)}</p>)}
                {[...warns.values()].map((w, i) => <p key={`w${i}`} class="small warn" data-route-warn={i}>{w}</p>)}
                {genNotes.map((n, i) => <p key={`g${i}`} class="muted small" data-gen-note={i}>{n}</p>)}
                {/* P1-40:有防区没生成出点(多半是没设待命点)→ 给入口 */}
                {genStandby && embed && <p class="small"><a href="#/admin/layout?tab=standby" data-gen-standby="1">{rt("guardGoStandby")}</a></p>}
                {draft && pts.length > 1 && (eta && !dirty ? (
                  <p class="small route-eta" data-eta-total="1" title={rt("etaBasis", { v: eta.speed_mps })}>
                    {rt("etaTotal", { t: clock(eta.total_s) })}{eta.basis === "straight" && <span class="muted"> · {rt("etaStraight")}</span>}
                  </p>
                ) : !draft.isNew && dirty ? <p class="muted small">{rt("etaAfterSave")}</p> : null)}
                {pts.length === 0 && <p class="muted small">{rt("routeNoPoints")}</p>}
                <ul class="pointlist" aria-label={rt("routePoints")}>
                  {pts.map((p, i) => (
                    <li key={i} aria-current={i === pi ? "true" : undefined}>
                      <span class="num">{i + 1}</span>
                      <button type="button" class="link" title={p.name} onClick={() => setPi(i)}><span class="pname">{p.name}</span></button>
                      {bad.has(i) && <span class="bad" title={bad.get(i)}>!</span>}
                      <span class="push" />
                      {!dirty && etaOf.has(p.name) && (() => {
                        const e = etaOf.get(p.name)!;
                        return <span class="mono small eta" data-eta={i} title={`${rt("etaPoint", { t: clock(e.arrive_s) })}${e.actual_s !== null ? ` · ${rt("etaActual", { t: clock(e.actual_s) })}` : ""}`}>
                          +{clock(e.arrive_s)}</span>;
                      })()}
                      <button type="button" class="btn sm" aria-label={`${rt("pointUp")} ${i + 1}`} disabled={i === 0}
                        onClick={() => { change(reorder(pts, i, i - 1)); setPi(i - 1); }}>▲</button>
                      <button type="button" class="btn sm" aria-label={`${rt("pointDown")} ${i + 1}`} disabled={i === pts.length - 1}
                        onClick={() => { change(reorder(pts, i, i + 1)); setPi(i + 1); }}>▼</button>
                      <button type="button" class="btn sm" aria-label={`${rt("pointRemove")} ${i + 1}`}
                        onClick={() => { change(deletePoint(pts, i)); setPi(null); }}>✕</button>
                    </li>
                  ))}
                </ul>
                {bad.size > 0 && (
                  <ul class="small bad">{[...bad].map(([i, why]) => <li key={i}>{i + 1}. {pts[i]?.name}: {why}</li>)}</ul>
                )}
                {selPoint && pi !== null ? (
                  <PointForm p={selPoint} names={pts.map((x) => x.name)} idx={pi} plain={!!embed} onChange={(patch) => change(patchPoint(pts, pi, patch), true)}
                    onActions={(p2) => change(pts.map((x, k) => (k === pi ? p2 : x)), true)} />
                ) : pts.length > 0 && <p class="muted small">{rt("pointSelectHint")}</p>}
                {/* UIUX-006:删除放最左、红框,跟保存 / 派巡逻隔开 */}
                <div class="row route-acts">
                  {!draft.isNew && <button type="button" class="btn danger" onClick={() => setRemoving(true)}>{rt("routeDelete")}</button>}
                  <span class="push" />
                  <button type="button" class="btn" disabled={!dirty} onClick={() => (draft.isNew ? setDraft(null) : orig && edit(orig))}>{rt("routeDiscard")}</button>
                  {!embed && <button type="button" class="btn primary" disabled={!canSave} onClick={() => void save()}>{rt("routeSave")}</button>}
                  {!draft.isNew && !dirty && !guardKind && <DispatchOnce route={draft.id} title={draft.title} say={say} />}
                </div>
                {!draft.isNew && !guardKind && (
                  <SchedulePanel route={draft.id} view={view} schedules={mySchedules} say={say} reload={load} />
                )}
              </>
            )}
          </div>
        </div>
      </section>
      {removing && draft && (
        <Confirm text={rt("routeDeleteConfirm", { name: draft.title || draft.id })} yes={rt("routeDelete")} danger onNo={() => setRemoving(false)} onYes={() => void del()} />
      )}
    </div>
  );
}

interface GenZone { zone: string; on: boolean; laps: number; dwell_s: number; photos: number }
interface GenResult { waypoints: RoutePoint[]; problems: PointProblem[]; zones: { zone: string; points: number; note: string }[] }

/** W73:按防区生成防区路线(设计 §4.2)。站点给的是草稿:放进编辑页,看过、挪过再存。 */
function GuardGenerate({ map, taken, say, onDone, onClose }: {
  map: MapRow; taken: string[]; say: Say;
  onDone: (id: string, points: RoutePoint[], problems: PointProblem[], notes: string[], standby?: boolean) => void; onClose: () => void;
}) {
  const [zones, setZones] = useState<GenZone[] | null>(null);
  // 第 2 轮 setup N14:给个默认名(guard-1、guard-2…第一个没用过的),不用先手填
  const [name, setName] = useState(() => { let n = 1; while (taken.includes(`guard-${n}`)) n++; return `guard-${n}`; });
  const [spacing, setSpacing] = useState(6);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    api<{ areas: { zone: string }[] }>("GET", `/api/maps/${enc(map.map_id)}/${enc(map.version)}/areas`)
      .then((d) => setZones((d.areas ?? []).map((a) => ({ zone: a.zone, on: true, laps: 1, dwell_s: 0, photos: 1 }))))
      .catch(() => setZones([]));
  }, [map.map_id, map.version]);
  const patch = (z: string, f: Partial<GenZone>) => setZones((all) => (all ?? []).map((x) => (x.zone === z ? { ...x, ...f } : x)));
  const num = (v: string, lo: number, hi: number) => { const n = Number(v); return Number.isFinite(n) ? Math.min(hi, Math.max(lo, n)) : lo; };
  const picked = (zones ?? []).filter((z) => z.on);
  const dup = taken.includes(name.trim());
  const ok = picked.length > 0 && NAME_RE.test(name.trim()) && !dup && !busy;
  // 「生成」灰着时说为什么
  const why = busy || zones === null || zones.length === 0 ? "" : !name.trim() ? rt("guardGenNeedName")
    : !NAME_RE.test(name.trim()) || dup ? rt("guardGenFixName") : picked.length === 0 ? rt("guardGenNeedZone") : "";
  async function go() {
    setBusy(true);
    try {
      const r = await api<GenResult>("POST", "/api/guard-routes/generate", {
        map_id: map.map_id, map_version: map.version, spacing_m: spacing,
        zones: picked.map((z) => ({ zone: z.zone, laps: z.laps, dwell_s: z.dwell_s, photos: z.photos })),
      });
      // 第 2 轮 P1-40:原因按界面语言;只有原因真跟待命点有关才给「去设待命点」
      const empty = r.zones.filter((z) => z.points === 0);
      const notes = empty.map((z) => rt("guardGenZoneNone", { zone: siteKnown(z.zone), why: siteStr(z.note) }));
      onDone(name.trim(), r.waypoints, r.problems ?? [], notes, empty.some((z) => /待命点/.test(z.note ?? "")));
    } catch (e) {
      say(errText(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <form class="panel guard-gen" aria-label={rt("guardGenTitle")} onSubmit={(e) => { e.preventDefault(); if (ok) void go(); }}>
      <h3>{rt("guardGenTitle")}</h3>
      <label class="routename">
        <span class="small">{rt("routeName")}</span>
        <input aria-label={rt("routeName")} value={name} maxLength={64} onInput={(e) => setName(e.currentTarget.value)} />
        <span class={`small${dup || (name && !NAME_RE.test(name.trim())) ? " bad" : " muted"}`}>{dup ? rt("routeNameTaken") : rt("routeNameHint")}</span>
      </label>
      {zones === null ? <p class="muted small">…</p> : zones.length === 0 ? <p class="muted small">{rt("guardGenNoZones")}</p> : (
        <table class="guard-gen-zones">
          <caption class="small">{rt("guardGenZones")}</caption>
          <thead><tr><th /><th class="small">{rt("guardGenLaps")}</th><th class="small">{rt("guardGenDwell")}</th><th class="small">{rt("guardGenPhotos")}</th></tr></thead>
          <tbody>
            {zones.map((z) => (
              <tr key={z.zone} data-gen-zone={z.zone}>
                <td><label><input type="checkbox" checked={z.on} onChange={(e) => patch(z.zone, { on: e.currentTarget.checked })} /> {z.zone}</label></td>
                <td><input type="number" min="1" max="10" step="1" value={z.laps} aria-label={`${z.zone} ${rt("guardGenLaps")}`} disabled={!z.on}
                  onInput={(e) => patch(z.zone, { laps: num(e.currentTarget.value, 1, 10) })} /></td>
                <td><input type="number" min="0" max="600" step="1" value={z.dwell_s} aria-label={`${z.zone} ${rt("guardGenDwell")}`} disabled={!z.on}
                  onInput={(e) => patch(z.zone, { dwell_s: num(e.currentTarget.value, 0, 600) })} /></td>
                <td><input type="number" min="0" max="5" step="1" value={z.photos} aria-label={`${z.zone} ${rt("guardGenPhotos")}`} disabled={!z.on}
                  onInput={(e) => patch(z.zone, { photos: num(e.currentTarget.value, 0, 5) })} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <label class="field">{rt("guardGenSpacing")}
        <input type="number" min="1" max="30" step="0.5" value={spacing} onInput={(e) => setSpacing(num(e.currentTarget.value, 1, 30))} />
      </label>
      <div class="row end">
        <button type="button" class="btn sm" onClick={onClose}>{t("cancel")}</button>
        <button type="submit" class="btn sm primary" disabled={!ok}>{rt("guardGenGo")}</button>
      </div>
      {why && <p class="small muted" data-gen-why="1">{why}</p>}
    </form>
  );
}

/** 底部操作栏的高度(吸在面板底部),表单要露在它上面。 */
const SIDE_BAR_PX = 72;
export function revealInSide(el: HTMLElement): void {
  const side = el.closest<HTMLElement>(".routeside");
  if (!side || side.scrollHeight <= side.clientHeight) return;
  const s = side.getBoundingClientRect();
  const f = el.getBoundingClientRect();
  const bottom = s.bottom - SIDE_BAR_PX;
  if (f.top < s.top) side.scrollTop -= s.top - f.top;
  else if (f.bottom > bottom) side.scrollTop += Math.min(f.bottom - bottom, f.top - s.top);
}

function PointForm({ p, idx, names, plain, onChange, onActions }: {
  p: RoutePoint; idx: number; names: string[]; plain?: boolean;
  onChange: (patch: Partial<RoutePoint>) => void; onActions: (p: RoutePoint) => void;
}) {
  const dup = names.some((n, k) => k !== idx && n === p.name);
  // UIUX-012:点了哪个点,右侧面板就滚到它的表单。外审:只滚面板自己(宽屏上它单独滚),
  // 窄屏上下排时面板不单独滚 → 不动,免得拖点时把整页、地图滚走
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => { if (box.current) revealInSide(box.current); }, [idx]);
  const num = (v: string) => (v.trim() === "" || !Number.isFinite(Number(v)) ? null : Number(v));
  return (
    <div class="pointform" ref={box} aria-label={`${idx + 1}`}>
      <label class="field wide">{rt("pointName")}
        <input value={p.name} maxLength={64} aria-invalid={dup || !p.name.trim()} onInput={(e) => onChange({ name: e.currentTarget.value })} />
      </label>
      {!plain && <><label class="field">{rt("pointX")}
        <input type="number" step="0.01" value={p.x} onInput={(e) => { const v = num(e.currentTarget.value); if (v !== null) onChange({ x: v }); }} />
      </label>
      <label class="field">{rt("pointY")}
        <input type="number" step="0.01" value={p.y} onInput={(e) => { const v = num(e.currentTarget.value); if (v !== null) onChange({ y: v }); }} />
      </label>
      <label class="field">{rt("pointYaw")}
        <input type="number" step="1" value={degOf(p.yaw)} onInput={(e) => { const v = num(e.currentTarget.value); if (v !== null) onChange({ yaw: radOf(v) }); }} />
      </label></>}
      {plain && <p class="muted small wide">{rt("pointDragHint")}</p>}
      <label class="field">{rt("pointDwell")}
        <input type="number" min="0" step="1" value={dwellOf(p)} onInput={(e) => { const v = num(e.currentTarget.value); if (v !== null && v >= 0) onActions(setDwell(p, v)); }} />
      </label>
      <label class="wide field-check"><input type="checkbox" checked={hasAction(p, "photo", "front")} onChange={() => onActions(toggleAction(p, { type: "photo", camera: "front" }))} /> {rt("pointPhotoFront")}</label>
      <label class="wide field-check"><input type="checkbox" checked={hasAction(p, "photo", "back")} onChange={() => onActions(toggleAction(p, { type: "photo", camera: "back" }))} /> {rt("pointPhotoBack")}</label>
      <label class="wide field-check"><input type="checkbox" checked={hasAction(p, "light")} onChange={() => onActions(toggleAction(p, { type: "light", on: true }))} /> {rt("pointLight")}</label>
      {/* 设计 §2.4:拍热像、量温度要等热像实物接上(契约的拍照现在只认前、后两路) */}
      <label class="wide field-check muted" data-thermal="photo"><input type="checkbox" disabled /> <span class="fc-text">{rt("pointThermal")} <span class="small">· {rt("thermalLater")}</span></span></label>
      <label class="wide field-check muted" data-thermal="temp"><input type="checkbox" disabled /> <span class="fc-text">{rt("pointTemp")} <span class="small">· {rt("thermalLater")}</span></span></label>
      <label class="field wide">{rt("pointCheck")}
        <input value={p.check ?? ""} maxLength={500} onInput={(e) => { const v = e.currentTarget.value; const { check: _c, ...rest } = p; onActions(v ? { ...rest, check: v } : rest); }} />
      </label>
    </div>
  );
}

/** P2-39:经理在网页上排巡逻日程(布防页的「巡逻日程」标签):挑一条路线,下面是跟路线页同一个排程面板。
 *  路线本身(画点、改名)还是管理员在「布置」里改。 */
export function PatrolSchedules({ say, canEdit }: { say: Say; canEdit: boolean }) {
  const [view, setView] = useState<RouteView | null>(null);
  const [route, setRoute] = useState("");
  const load = useCallback(() => api<RouteView>("GET", "/api/routes?kind=patrol")
    .then((v) => { setView(v); setRoute((r) => r || v.routes[0]?.id || ""); })
    .catch((e) => { setView(null); say(errText(e)); }), []);
  useEffect(() => { void load(); }, [load]);
  if (!view) return <p class="muted">{t("loading")}</p>;
  if (view.routes.length === 0) return <p class="muted" data-no-routes="1">{rt("routesNone")}</p>;
  const count = (id: string) => view.schedules.filter((s) => s.mission === id).length;
  return (
    <section class="panel arm-patrols">
      <div class="panel-head">
        <h2>{rt("routeSchedules")}</h2>
        <label class="field-inline">{rt("schedRoute")}
          <select name="route" value={route} onChange={(e) => setRoute(e.currentTarget.value)}>
            {view.routes.map((r) => <option key={r.id} value={r.id}>{routeLabel(r)}{count(r.id) ? ` (${count(r.id)})` : ""}</option>)}
          </select>
        </label>
      </div>
      <div class="arm-patrols-body">
        {canEdit ? <SchedulePanel key={route} inPanel route={route} view={view} schedules={view.schedules.filter((s) => s.mission === route)} say={say} reload={load} />
          : <p class="muted small">{rt("schedReadOnly")}</p>}
      </div>
    </section>
  );
}

function SchedulePanel({ route, view, schedules, say, reload, inPanel }: {
  route: string; view: RouteView | null; schedules: RouteSchedule[]; say: Say; reload: () => Promise<void>; inPanel?: boolean;
}) {
  const [tz, setTz] = useState("");
  // 第 2 轮 config N2 / N3:编号自动给(路线名-1、-2…第一个没用过的);用过的当场说,不等站点回「有人先改过」
  const all = view?.schedules ?? [];
  const nextId = () => freeId(route, all.map((x) => x.id), view, "schedule");
  const [id, setId] = useState(nextId);
  // 第 3 轮 config N6:原来加好后 setId(nextId()) 用的是这一次渲染的旧列表 → 编号框还是刚用过的,当场标红。
  // 编号没人改过(自动给的)时,列表一变就重新挑;刚打开页面列表还没到时也一样
  const [autoId, setAutoId] = useState(true);
  const ids = all.map((x) => x.id).join(",");
  useEffect(() => { if (autoId) setId(nextId()); }, [ids, route, autoId]);
  // 第 8 轮 W8-11:写中文名就当显示名,编号照旧自动给
  const [title, setTitle] = useState("");
  const [at, setAt] = useState("22:00");
  const [days, setDays] = useState<string[]>([...DAYS]);
  const [win, setWin] = useState(30);
  const [missed, setMissed] = useState<"skip" | "run_late" | "alarm">("skip");
  // 第 8 轮 W8-06:由哪台跑(空 = 哪台空就哪台)
  const [robot, setRobot] = useState("");
  const [robots, setRobots] = useState<string[]>([]);
  // 第 9 轮 A9-01:只许手动派的机器人在选项里写明(排了日程也不会派它)
  const [manual, setManual] = useState<Set<string>>(new Set());
  useEffect(() => {
    api<{ robots: { robot_id: string; revoked?: boolean; manual_only?: boolean }[] }>("GET", "/api/robots")
      .then((d) => {
        const live = d.robots.filter((x) => !x.revoked);
        setRobots(live.map((x) => x.robot_id));
        setManual(new Set(live.filter((x) => x.manual_only).map((x) => x.robot_id)));
      }).catch(() => setRobots([]));
  }, []);
  const [removing, setRemoving] = useState<RouteSchedule | null>(null);
  const call = async (path: string, body: unknown, done: string): Promise<boolean> => {
    try {
      await api("POST", path, body);
      say(done);
      await reload();
      return true;
    } catch (e) {
      say(errText(e));
      return false;
    }
  };
  const idTaken = all.some((x) => x.id === id.trim()) || (view?.retired_schedules ?? []).includes(id.trim());
  const sameTime = schedules.some((x) => x.at === at && x.days.some((d) => days.includes(d)));
  // UIUX-018:哪一格不对就在那一格下面说;动过的格子才说(刚加完清空的「几点开始」不当场标红),
  // 「加排程」灰着时旁边写还差哪几样
  const [touched, setTouched] = useState<Set<string>>(new Set());
  const touch = (k: string) => setTouched((s) => (s.has(k) ? s : new Set(s).add(k)));
  const bad = {
    id: !NAME_RE.test(id.trim()) ? rt("schedErrId") : "",
    at: !/^([01][0-9]|2[0-3]):[0-5][0-9]$/.test(at) ? rt("schedErrAt") : "",
    days: days.length === 0 ? rt("schedErrDays") : "",
    win: !(win >= 1 && win <= 1440) ? rt("schedErrWin") : "",
  };
  const label = { id: rt("schedId"), at: rt("schedAt"), days: rt("schedDays"), win: rt("schedWindow") };
  const missing = (Object.keys(bad) as (keyof typeof bad)[]).filter((k) => bad[k]).map((k) => label[k]);
  const err = (k: keyof typeof bad) => touched.has(k) && bad[k]
    ? <span class="error small" data-sched-err={k}>{bad[k]}</span> : null;
  return (
    <>
      {/* 第 4 轮 r2-config-N3:放在「巡逻日程」面板里时面板已有标题,不再标一次 */}
      {!inPanel && <h2>{rt("routeSchedules")}</h2>}
      {view && view.timezone === null ? (
        <form class="row" onSubmit={(e) => { e.preventDefault(); void call("/api/route-timezone", { timezone: tz.trim() }, t("saved")); }}>
          <label class="field">{rt("schedTimezone")}
            <input value={tz} placeholder="Asia/Kuala_Lumpur" onInput={(e) => setTz(e.currentTarget.value)} />
          </label>
          <button type="submit" class="btn sm" disabled={!tz.trim()}>{rt("schedSetTimezone")}</button>
          <p class="muted small">{rt("schedTimezoneHint")}</p>
        </form>
      ) : (
        <>
          {view && <p class="muted small">{rt("schedTimezone")}{colon()}<span class="mono">{view.timezone}</span></p>}
          {schedules.length === 0 && <p class="muted small">{rt("routeNoSchedules")}</p>}
          <ul class="sched-list">
            {schedules.map((s) => (
              <li key={s.id}>
                <span class="strong" title={s.title ? s.id : undefined}>{routeLabel(s)}</span>
                <span class="mono small">{s.at}</span>
                <span class="muted small">{s.days.map((d) => t(d as Key)).join(" ")}</span>
                <span class="muted small" data-sched-robot="1">{s.robot ? rt("schedByRobot", { id: s.robot }) : rt("schedAnyRobot")}</span>
                <button type="button" class="link push" aria-label={`${rt("schedRemove")} ${routeLabel(s)}`} onClick={() => setRemoving(s)}>{t("remove")}</button>
              </li>
            ))}
          </ul>
          <form class="form sched-form" onSubmit={(e) => {
            e.preventDefault();
            if (idTaken) return;
            void call(`/api/route-schedules/${enc(id.trim())}`, { mission: route, at, days, window_min: win, on_missed: missed, base_revision: 0, ...(robot ? { robot } : {}), ...(title ? { title } : {}) }, rt("schedSaved"))
              // 加好了换下一个编号(列表刷新后挑),不留着旧的;第 4 轮 r3-config-N6:开始时间也清掉(不然黄字「这个时间已有」指的就是刚加的)
              .then((ok) => { if (ok) { setAutoId(true); setAt(""); setTitle(""); setTouched(new Set()); } });
          }}>
            <label class="field">{rt("schedId")}<input value={title || id} maxLength={64} aria-invalid={idTaken || (touched.has("id") && !!bad.id) || undefined} onInput={(e) => {
              const v = e.currentTarget.value;
              touch("id");
              if (!v.trim() || NAME_RE.test(v.trim())) { setTitle(""); setAutoId(false); setId(v); } else { setTitle(v.trim()); setAutoId(true); }
            }} />
              {title && <span class="muted small" data-sched-auto-id="1">{rt("routeAutoId", { id })}</span>}
              {idTaken && <span class="error small" role="alert" data-sched-dup="1">{rt("schedIdTaken")}</span>}
              {!idTaken && err("id")}</label>
            {/* P1-03:时间一律 24 小时制(浏览器的时间框可能按系统显示成上午 / 下午) */}
            <label class="field">{rt("schedAt")}<input name="at" type="text" inputMode="numeric" pattern="([01][0-9]|2[0-3]):[0-5][0-9]" placeholder="21:00"
              maxLength={5} value={at} aria-invalid={(touched.has("at") && !!bad.at) || undefined}
              onInput={(e) => { touch("at"); setAt(e.currentTarget.value); }} />{err("at")}</label>
            <fieldset class="checks row-wrap">
              <legend>{rt("schedDays")}</legend>
              {DAYS.map((d) => (
                <label key={d}><input type="checkbox" checked={days.includes(d)}
                  onChange={() => { touch("days"); setDays(days.includes(d) ? days.filter((x) => x !== d) : [...days, d]); }} /> {t(d)}</label>
              ))}
              {err("days")}
            </fieldset>
            <label class="field">{rt("schedWindow")}<input type="number" min="1" max="1440" value={win} aria-invalid={(touched.has("win") && !!bad.win) || undefined}
              onInput={(e) => { touch("win"); setWin(Number(e.currentTarget.value)); }} />{err("win")}</label>
            <label class="field">{rt("schedRobot")}
              <select name="schedRobot" value={robot} onChange={(e) => setRobot(e.currentTarget.value)}>
                <option value="">{rt("schedAnyRobot")}</option>
                {robots.map((x) => <option key={x} value={x}>{manual.has(x) ? rt("schedManualRobot", { id: x }) : x}</option>)}
              </select>
            </label>
            <label class="field">{rt("schedMissed")}
              <select value={missed} onChange={(e) => setMissed(e.currentTarget.value as typeof missed)}>
                <option value="skip">{rt("schedSkip")}</option>
                <option value="run_late">{rt("schedRunLate")}</option>
                <option value="alarm">{rt("schedAlarm")}</option>
              </select>
            </label>
            <p class="muted small">{rt("schedNote")}</p>
            {sameTime && <p class="warn small" data-sched-same="1">{rt("schedSameTime", { at })}</p>}
            <button type="submit" class="btn sm sched-add" disabled={idTaken || missing.length > 0}>{rt("schedAdd")}</button>
            {missing.length > 0 && <p class="small muted" role="status" data-sched-missing="1">{rt("schedMissing", { what: joinList(missing) })}</p>}
          </form>
        </>
      )}
      {removing && (
        <Confirm text={rt("schedRemoveConfirm", { name: routeLabel(removing) })} yes={rt("schedRemove")} danger onNo={() => setRemoving(null)}
          onYes={() => { const s = removing; setRemoving(null); void call(`/api/route-schedules/${enc(s.id)}/delete`, { base_revision: s.revision }, rt("schedRemoved", { id: routeLabel(s) })); }} />
      )}
    </>
  );
}
