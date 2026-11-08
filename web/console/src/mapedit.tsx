// 地图编辑器第一版(W44 第四期,设计 §6;「高级 → 地图」每一版的「编辑…」打开)。
// - 橡皮擦、画障碍:画笔(点几下连成一笔)/ 直线 / 方框,粗细 0.1–1 m;改的是机器人「哪里能走」的平面图,另存成新的一版。
// - 区域命名、特殊地面(楼梯、台阶、斜坡默认放慢,草地、碎石路只标出来)、摆正(只转显示)、底图(只是显示):跟着版本存。
// - 撤销、重做;「另存」之前列出这一次擦了多少、画了多少,确认才存。虚拟墙、禁行区、限速区去「布置 → 禁行区」。
// 清噪点在「地图」页每一版的「清噪点…」里(那一页外审过,自己另存一版)。
import { useUnsaved } from "./unsaved";
import type { FunctionComponent } from "preact";
import { useEffect, useRef, useState } from "preact/hooks";
import { api, apiUpload, ApiError, enc } from "./api";
import { Confirm } from "./dialogs";
import { t, type Key } from "./i18n";
import { polyPx, toMap, type OwnLayer } from "./layoutpage";
import { MapCanvas } from "./mapcanvas";
import { apply, closedLoop, type Display, type GridOp, type History, newTerrain, redo, screenRect, start, summary, type TerrainKind, undo } from "./mapeditops";
import type { PreviewMeta, Pt } from "./mapview";

type Say = (s: string) => void;
type Tool = "erase" | "obstacle" | "region" | "terrain" | "rotate" | "basemap";
type Shape = GridOp["shape"];
const TERRAIN: TerrainKind[] = ["stairs", "step", "slope", "grass", "gravel"];
const TOOL_KEY: Record<Tool, Key> = { erase: "meErase", obstacle: "meObstacle", region: "meRegion", terrain: "meTerrain", rotate: "meRotate", basemap: "meBasemap" };
const EMPTY: Display = { rotate_deg: null, basemap: null, regions: [], terrain: [] };

export function editTarget(hash: string): { map_id: string; version: string; from?: string } | null {
  const q = new URLSearchParams(hash.split("?")[1] ?? "");
  const m = q.get("map");
  const v = q.get("version");
  const from = q.get("from");
  return m && v ? { map_id: m, version: v, ...(from ? { from } : {}) } : null;
}

function errText(e: unknown): string {
  return t("failed", { why: e instanceof ApiError ? e.message : String(e) });
}

type Target = { map_id: string; version: string; from?: string };

/** 外审 R5:编辑器跟「哪张图哪一版」绑死 —— 换了就按 key 整个重建(草稿、选的点、确认框、文件全清掉),
 *  旧的回包、旧的另存回来不碰新的那个。 */
export function MapEditPage({ say, target, Canvas }: { say: Say; target: Target | null; Canvas?: FunctionComponent<OwnLayer> }) {
  if (!target) return <p class="empty">{t("meNoTarget")}</p>;
  return <Editor key={`${target.map_id}\u0000${target.version}`} say={say} target={target} Canvas={Canvas} />;
}

function Editor({ say, target, Canvas }: { say: Say; target: Target; Canvas?: FunctionComponent<OwnLayer> }) {
  const base = `/api/maps/${enc(target.map_id)}/${enc(target.version)}`;
  const adm = `/api/admin/maps/${enc(target.map_id)}/${enc(target.version)}`;
  const alive = useRef(true);
  const [loadErr, setLoadErr] = useState(false);
  const [meta, setMeta] = useState<PreviewMeta | null>(null);
  const [digest, setDigest] = useState("");
  const [hist, setHist] = useState<History | null>(null);
  // P1-53:一打开不默认选橡皮擦(点图就擦掉了);先选工具
  const [tool, setTool] = useState<Tool | null>(null);
  const [result, setResult] = useState(false);
  const [shape, setShape] = useState<Shape>("stroke");
  const [width, setWidth] = useState(0.3);
  const [pts, setPts] = useState<Pt[]>([]);
  // 第 2 轮 P1-53:方框按住拖着画(拖的时候先画个虚框,松手才算)
  const [rect, setRect] = useState<[Pt, Pt] | null>(null);
  const [kind, setKind] = useState<TerrainKind>("stairs");
  const [name, setName] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [asking, setAsking] = useState(false);
  const [stale, setStale] = useState(false);
  const [busy, setBusy] = useState(false);
  const [bmSize, setBmSize] = useState<[number, number] | null>(null);

  useEffect(() => {
    // 三样(预览、栅格摘要、显示设置)都读到了才算就绪;哪样读不出来都不能存(显示设置读不出来不当成空的:
    // 存了会把区域名、特殊地面全抹掉)
    const ok = <T,>(f: (v: T) => void) => (v: T) => { if (alive.current) f(v); };
    const bad = () => { if (alive.current) setLoadErr(true); };
    api<PreviewMeta>("GET", `${base}/preview`).then(ok(setMeta)).catch(bad);
    api<{ digest: string }>("GET", `${adm}/noise`).then(ok((d) => setDigest(d.digest || ""))).catch(bad);
    api<Display>("GET", `${adm}/display`).then(ok((d) => setHist(start({ ...EMPTY, ...d })))).catch(bad);
    return () => { alive.current = false; };
  }, []);

  const bmFile = hist?.now.display.basemap?.file;
  useEffect(() => {
    if (!bmFile || typeof Image === "undefined") return;
    const img = new Image();
    img.onload = () => setBmSize([img.naturalWidth, img.naturalHeight]);
    img.src = `${adm}/basemap?f=${enc(bmFile)}`;
  }, [bmFile, adm]);

  const ready = !!meta && !!digest && !!hist && !loadErr;
  const now = hist?.now;
  const dirty = !!hist && hist.past.length > 0;
  useUnsaved("mapedit", dirty);
  const sum = now ? summary(now) : { erased: 0, obstacle: 0 };
  const change = (f: Parameters<typeof apply>[1]) => setHist((h) => (h ? apply(h, f) : h));
  const grid = tool === "erase" || tool === "obstacle";
  const need = grid ? (shape === "stroke" ? 1 : 2) : tool === "region" || tool === "terrain" ? 3 : 0;

  function finish(points = pts) {
    if (grid) {
      // P2-19:摆正转了角度时,方框按屏幕上看到的方向画(原来按地图坐标轴,屏幕上是斜的);
      // 交给站点的是首尾相接的一笔,站点把圈里整块擦 / 加(W61)
      const rot = now?.display.rotate_deg ?? meta?.rotation_deg ?? 0;
      const tilted = shape === "rect" && points.length === 2 && Math.abs(rot % 90) > 0.5;
      const op: GridOp = tilted
        ? { op: tool as GridOp["op"], shape: "stroke", points: screenRect(points[0], points[1], rot), width_m: 0.1 }
        : { op: tool as GridOp["op"], shape, points, width_m: width };
      change((s) => ({ ...s, ops: [...s.ops, op] }));
    } else if (tool === "region" && name.trim()) {
      const n = name.trim();
      change((s) => ({ ...s, display: { ...s.display, regions: [...s.display.regions.filter((r) => r.name !== n), { name: n, polygon: points }] } }));
      setName("");
    } else if (tool === "terrain") {
      change((s) => ({ ...s, display: { ...s.display, terrain: [...s.display.terrain, newTerrain(s.display.terrain, kind, points)] } }));
    }
    setPts([]);
  }

  function pick(px: number, py: number) {
    if (!meta || !need) return;
    const p = toMap(meta, px, py);
    const next = [...pts, p];
    if (grid && shape !== "stroke" && next.length === 2) finish(next);
    else setPts(next);
  }

  async function save() {
    if (!hist || !ready) return;
    setAsking(false);
    setBusy(true);
    try {
      let version = target.version;
      let got: { erased_m2?: number; obstacle_m2?: number } = {};
      if (hist.now.ops.length) {
        const r = await api<{ version: string; erased_m2?: number; obstacle_m2?: number }>("POST", `${adm}/edit`, { digest, ops: hist.now.ops });
        version = r.version;
        got = r;
      }
      const vb = `/api/admin/maps/${enc(target.map_id)}/${enc(version)}`;
      let display = hist.now.display;
      if (display.basemap && file && version !== target.version) {
        // 底图文件跟着版本放:另存成新版本时再传一次
        const up = await apiUpload<{ file: string }>(`${vb}/basemap`, file, { "Content-Type": file.type || "image/png" });
        display = { ...display, basemap: { ...display.basemap, file: up.file } };
      }
      // 等回包的时候换了图:人确认过的这一次照样存完(显示设置跟着它的新版本),只是不跳、不碰新的那个
      await api("POST", `${vb}/display`, display);
      // 第 2 轮 P1-55:报站点实际改了的面积(原来就是空地的不算),跟版本备注一致
      say(version === target.version ? t("saved")
        : got.erased_m2 != null ? t("meSavedAsArea", { v: version, e: got.erased_m2, o: got.obstacle_m2 ?? 0 }) : t("meSavedAs", { v: version }));
      // 存好了就不算没存(P0-12 的离开提醒不该再问);另存出新版本就跳过去(P1-55)
      if (alive.current) setHist(start(display));
      if (alive.current && version !== target.version) location.hash = `#/admin/mapedit?map=${enc(target.map_id)}&version=${enc(version)}&from=${enc(target.version)}`;
    } catch (e) {
      if (!alive.current) return;
      if (e instanceof ApiError && e.status === 409) setStale(true);
      else say(errText(e));
    } finally {
      if (alive.current) setBusy(false);
    }
  }

  async function upload(f: File) {
    try {
      const d = await apiUpload<{ file: string }>(`${adm}/basemap`, f, { "Content-Type": f.type || "image/png" });
      if (!alive.current) return;
      setFile(f);
      change((s) => ({ ...s, display: { ...s.display, basemap: { file: d.file, x: meta?.left_x ?? 0, y: meta?.top_y ?? 0, scale: meta?.m_per_px ?? 0.05, rotate_deg: 0, opacity: 0.5 } } }));
    } catch (e) {
      say(errText(e));
    }
  }

  // 第 3 轮 maps N2 / P1-53:原来每次渲染都新造一个 Map 组件 → 地图整个重挂,拖框拖到一半就丢了
  // (只剩一个 5×6 的虚线框)。现在直接渲染 MapCanvas
  const Map = (o: OwnLayer) => (Canvas ? <Canvas {...o} /> : meta ? (
    <MapCanvas meta={{ ...meta, rotation_deg: now?.display.rotate_deg ?? meta.rotation_deg }} raster={`${base}/preview.png`} label={t("meTitle")}
      drawing={o.drawing} onPick={o.onPick} onDragRect={o.onDragRect} world={o.world} marks={o.marks} areas={o.areas} />
  ) : null);
  const strokeW = (w: number) => (meta ? w / meta.m_per_px : 2);
  const bm = now?.display.basemap;

  // P2-19:Ctrl+Z 撤销、Ctrl+Y / Ctrl+Shift+Z 重做(在输入框里打字时不管)
  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      if (!(e.ctrlKey || e.metaKey)) return;
      const tag = (e.target as HTMLElement | null)?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
      const k = e.key.toLowerCase();
      if (k === "y" || (k === "z" && e.shiftKey)) { e.preventDefault(); setHist((h) => (h && h.future.length ? redo(h) : h)); }
      else if (k === "z") { e.preventDefault(); setHist((h) => (h && h.past.length ? undo(h) : h)); }
    };
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, []);

  return (
    <section class="mapedit" data-ready={ready ? "1" : undefined}>
      <div class="panel-head">
        <h1>{t("meTitle")} · <span class="mono">{target.map_id}:{target.version}</span></h1>
        <a class="btn push" href="#/admin/maps">{t("meBack")}</a>
        <button type="button" class="btn" disabled={!hist?.past.length} onClick={() => setHist((h) => (h ? undo(h) : h))}>{t("meUndo")}</button>
        <button type="button" class="btn" disabled={!hist?.future.length} onClick={() => setHist((h) => (h ? redo(h) : h))}>{t("meRedo")}</button>
        <button type="button" class="btn primary me-save" disabled={!dirty || busy || !ready} onClick={() => setAsking(true)}>{now?.ops.length ? t("meSaveNew") : t("save")}</button>
      </div>
      <p class="muted small">{t("meExplain")}</p>
      {/* 第 2 轮 P1-55:另存出来的新版本还没用上 —— 给「去发布」入口 */}
      {target.from && <p class="me-newver small" data-publish-link="1">{t("meNewVersion", { v: target.version, from: target.from })}{" "}
        <a href="#/admin/maps">{t("meGoPublish")}</a></p>}
      {stale && <div class="ly-conflict" role="alert">{t("meStale")}</div>}
      {loadErr && <div class="ly-conflict me-loaderr" role="alert">{t("meLoadErr")}</div>}
      <div class="ly-tab">
        <div class={result ? "me-canvas result" : "me-canvas"}>
          {Map({
            drawing: need > 0,
            onPick: need > 0 ? pick : undefined,
            onDragRect: grid && shape === "rect" && meta ? (a: Pt, b: Pt, done: boolean) => {
              const A = toMap(meta, a[0], a[1]);
              const B = toMap(meta, b[0], b[1]);
              if (done) { setRect(null); finish([A, B]); } else setRect([A, B]);
            } : undefined,
            areas: now?.display.regions.map((r) => ({ name: r.name, pts: r.polygon, kind: "zone" as const })),
            world: meta && now ? <>
              {bm && bmSize && (() => {
                const x = (bm.x - meta.left_x) / meta.m_per_px;
                const y = (meta.top_y - bm.y) / meta.m_per_px;
                return <image class="me-basemap" href={`${adm}/basemap?f=${enc(bm.file)}`} x={x} y={y} opacity={bm.opacity}
                  width={bmSize[0] * bm.scale / meta.m_per_px} height={bmSize[1] * bm.scale / meta.m_per_px}
                  transform={`rotate(${bm.rotate_deg} ${x} ${y})`} />;
              })()}
              {now.display.terrain.map((tr) => <polygon key={tr.id} class={`me-terrain ${tr.kind}`} points={polyPx(meta, tr.polygon)}><title>{t(`terr_${tr.kind}` as Key)}</title></polygon>)}
              {now.ops.map((o, i) => o.shape === "rect"
                ? <polygon key={i} class={`me-op ${o.op}`} points={polyPx(meta, [o.points[0], [o.points[1][0], o.points[0][1]], o.points[1], [o.points[0][0], o.points[1][1]]])} />
                : closedLoop(o)
                  ? <polygon key={i} class={`me-op loop ${o.op}`} points={polyPx(meta, o.points)} stroke-width={strokeW(o.width_m)} />
                  : <polyline key={i} class={`me-op ${o.op}`} points={polyPx(meta, o.points.length > 1 ? o.points : [o.points[0], o.points[0]])} stroke-width={strokeW(o.width_m)} />)}
              {pts.length > 0 && <polyline class="draft-line" points={polyPx(meta, pts)} />}
              {rect && <polygon class="draft-line" data-drag-rect="1" points={polyPx(meta, [rect[0], [rect[1][0], rect[0][1]], rect[1], [rect[0][0], rect[1][1]]])} />}
            </> : null })}
          {/* P1-52:图例;能切到「擦完的样子」(擦的画成空地、加的画成墙) */}
          <div class="me-legend small" data-me-legend="1">
            <span><i class="me-sw erase" aria-hidden="true" />{t("meLegErase")}</span>
            <span><i class="me-sw obstacle" aria-hidden="true" />{t("meLegObstacle")}</span>
            <span><i class="me-sw terrain" aria-hidden="true" />{t("meLegTerrain")}</span>
            <label class="push"><input type="checkbox" name="me-result" checked={result} onChange={(e) => setResult(e.currentTarget.checked)} /> {t("meShowResult")}</label>
          </div>
        </div>
        <div class="ly-side">
          <div class="me-tools" role="toolbar" aria-label={t("meTools")}>
            {(Object.keys(TOOL_KEY) as Tool[]).map((k) => (
              <button key={k} type="button" aria-pressed={tool === k} data-tool={k} onClick={() => { setTool(k); setPts([]); }}>{t(TOOL_KEY[k])}</button>
            ))}
            <a class="btn sm" href="#/admin/layout?tab=nogo">{t("meNogoLink")}</a>
          </div>
          {grid && (
            <>
              <div class="seg" role="group" aria-label={t("meShape")}>
                {(["stroke", "line", "rect"] as Shape[]).map((s) => (
                  <button key={s} type="button" aria-pressed={shape === s} onClick={() => { setShape(s); setPts([]); }}>{t(s === "stroke" ? "meStroke" : s === "line" ? "meLine" : "meRect")}</button>
                ))}
              </div>
              {shape !== "rect" && (
                <label class="field">{t("meWidth", { w: width.toFixed(1) })}
                  <input name="width" type="range" min={0.1} max={1} step={0.1} value={width} onInput={(e) => setWidth(Number(e.currentTarget.value))} />
                  <span class="range-ends muted small" aria-hidden="true"><span>0.1 m</span><span>1.0 m</span></span>
                </label>
              )}
              <p class="muted small">{t(shape === "stroke" ? "meStrokeHint" : shape === "line" ? "meLineHint" : "meRectHint")}</p>
            </>
          )}
          {tool === "region" && (
            <label class="field">{t("meRegionName")}<input name="region" value={name} maxLength={64} onInput={(e) => setName(e.currentTarget.value)} /></label>
          )}
          {tool === "terrain" && (
            <label class="field">{t("meTerrainKind")}
              <select name="kind" value={kind} onChange={(e) => setKind(e.currentTarget.value as TerrainKind)}>
                {TERRAIN.map((k) => <option key={k} value={k}>{t(`terr_${k}` as Key)}</option>)}
              </select>
            </label>
          )}
          {(tool === "region" || tool === "terrain") && <p class="muted small">{t("mePolyHint")}</p>}
          {tool === null && <p class="muted small">{t("mePickTool")}</p>}
          {pts.length > 0 && (
            <div class="row wrap">
              <span class="muted small">{t(grid ? "meStrokePts" : "drawHint", { n: pts.length })}</span>
              <button type="button" class="btn sm" onClick={() => setPts(pts.slice(0, -1))}>{t("undoPoint")}</button>
              <button type="button" class="btn sm primary" disabled={pts.length < need || (tool === "region" && !name.trim())} onClick={() => finish()}>{t("lyDrawDone")}</button>
            </div>
          )}
          {tool === "rotate" && now && (
            <>
              <label class="field">{t("meRotateDeg", { d: Math.round(now.display.rotate_deg ?? meta?.rotation_deg ?? 0) })}
                <input name="rotate" type="range" min={-180} max={180} step={1} value={now.display.rotate_deg ?? meta?.rotation_deg ?? 0}
                  onChange={(e) => { const v = Number(e.currentTarget.value); change((s) => ({ ...s, display: { ...s.display, rotate_deg: v } })); }} />
                <span class="range-ends muted small" aria-hidden="true"><span>-180°</span><span>0°</span><span>180°</span></span>
              </label>
              <button type="button" class="btn sm" onClick={() => change((s) => ({ ...s, display: { ...s.display, rotate_deg: null } }))}>{t("meRotateAuto")}</button>
              <p class="muted small">{t("meRotateHint")}</p>
            </>
          )}
          {tool === "basemap" && now && (
            <>
              <input type="file" name="basemap" accept="image/png,image/jpeg" onChange={(e) => { const f = e.currentTarget.files?.[0]; if (f) void upload(f); }} />
              {bm && (["x", "y", "scale", "rotate_deg", "opacity"] as const).map((k) => (
                <label key={k} class="field">{t(`meBm_${k}` as Key)}
                  <input type="number" name={`bm_${k}`} step={k === "opacity" ? 0.1 : k === "scale" ? 0.001 : 0.5}
                    value={Number(bm[k].toFixed(k === "scale" ? 4 : 2))}
                    onChange={(e) => { const v = Number(e.currentTarget.value); change((s) => ({ ...s, display: { ...s.display, basemap: s.display.basemap ? { ...s.display.basemap, [k]: v } : null } })); }} />
                </label>
              ))}
              <p class="muted small">{t("meBasemapHint")}</p>
            </>
          )}
          {now && (now.display.regions.length > 0 || now.display.terrain.length > 0) && (
            <ul class="plain ly-list">
              {now.display.regions.map((r) => (
                <li key={`r-${r.name}`} class="row"><span>{r.name}</span>
                  <button type="button" class="btn sm push" onClick={() => change((s) => ({ ...s, display: { ...s.display, regions: s.display.regions.filter((x) => x.name !== r.name) } }))}>{t("remove")}</button></li>
              ))}
              {now.display.terrain.map((tr) => (
                <li key={tr.id} class="row me-terr-row" data-terrain={tr.id}><span class="me-tname">{t(`terr_${tr.kind}` as Key)}</span>
                  <label class="small">{t("meSlow")}<input type="number" class="me-slow" name={`slow_${tr.id}`} min={0} max={2} step={0.1} value={tr.slow_mps ?? 0}
                    onChange={(e) => { const v = Number(e.currentTarget.value); change((s) => ({ ...s, display: { ...s.display, terrain: s.display.terrain.map((x) => (x.id === tr.id ? { ...x, slow_mps: v > 0 ? v : null } : x)) } })); }} /></label>
                  <button type="button" class="btn sm push" onClick={() => change((s) => ({ ...s, display: { ...s.display, terrain: s.display.terrain.filter((x) => x.id !== tr.id) } }))}>{t("remove")}</button></li>
              ))}
            </ul>
          )}
        </div>
      </div>
      {asking && (
        <Confirm text={now?.ops.length ? t("meConfirmNew", { e: sum.erased, o: sum.obstacle }) : t("meConfirmDisplay")}
          yes={now?.ops.length ? t("meSaveNew") : t("save")} onNo={() => setAsking(false)} onYes={() => void save()} />
      )}
    </section>
  );
}
