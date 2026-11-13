// 地图(地图页、防区页共用):给客户看的显示 —— 转正、全图、滚轮缩放 / 拖动平移、区域名、图例 + 比例尺、平面图。
// 只改显示,站点、狗用的坐标一个不动。
//
// 两层:
// - 世界层(g.map-world):底图(平面图或栅格)和多边形(禁行 / 限速区、区域、防区、正在画的线)用预览像素坐标画,
//   整层一个 transform = matrix(…)(放大、转正、平移合在一起,见 mapview.worldMatrix),跟着图一起转;
// - 标记层(g.map-marks):字(区域名、狗编号)、狗、报警点画在屏上坐标里(位置用同一个矩阵算),
//   不转、不跟着缩放变大小 —— 字永远是正的。
// 屏上一点 → 预览像素:世界层的 getScreenCTM().inverse()(浏览器按画的那个 transform 倒回去)。
import type { ComponentChildren } from "preact";
import { useEffect, useLayoutEffect, useRef, useState } from "preact/hooks";
import { t, type Key } from "./i18n";
import { siteKnown } from "./sitetext";
import {
  applyMat,
  clampView,
  fitView,
  matrixAttr,
  placeLabel,
  rotationOf,
  scaleBar,
  toPx,
  worldMatrix,
  zoomView,
  type Box,
  type NavZone,
  type Obstacle,
  type PreviewMeta,
  type Pt,
  type View,
} from "./mapview";
import { rasterShade, scheme } from "./theme";

/** 图上画的有名字的多边形(地图坐标,米):area = 区域(淡),zone = 防区(防区页上能改的那些,显眼)。 */
export interface CanvasArea {
  name: string;
  pts: Pt[];
  /** 第 3 轮:region = 地图编辑里起名字的显示区域(不是防区);ref = 布置里别的页的防区淡显。 */
  kind: "area" | "zone" | "region" | "ref";
  /** 报警的防区:标红(W44)。 */
  hot?: boolean;
  /** 布置里选中的那一块:蓝色(蓝色只表示选中;第 2 轮 setup N9,原来借了报警的红色)。 */
  sel?: boolean;
  /** 图上写的字(不给 = 名字);W44 地图页写「主楼 · 布防」。 */
  label?: string;
  /** 布防绿色实框、撤防灰色虚框(W44 地图页的防区和布防图层)。 */
  tone?: "armed" | "off";
}

/** 图例超过这么多项就收成按钮。 */
const LEGEND_INLINE = 6;

export type LegendKey = "floor" | "wall" | "seen" | "curb" | "unknown" | "nogo" | "hard" | "vwall" | "erase" | "slow" | "ignore" | "area" | "zone" | "region" | "ref" | "exit" | "hide" | "standby" | "camera" | "robot" | "alarm";
const LEGEND_ORDER: LegendKey[] = ["floor", "wall", "seen", "curb", "unknown", "nogo", "hard", "vwall", "erase", "slow", "ignore", "area", "zone", "region", "ref", "exit", "hide", "standby", "camera", "robot", "alarm"];
const LEGEND_TEXT: Record<LegendKey, Key> = {
  floor: "legendFloor", wall: "legendWall", seen: "legendSeen", curb: "legendCurb", unknown: "legendUnknown", nogo: "legendNoGo",
  hard: "hardNoGoLegend", vwall: "legendVWall", erase: "legendErase", slow: "legendSlow", ignore: "legendIgnore",
  area: "legendArea", zone: "legendZone", region: "legendRegion", ref: "legendZoneRef", exit: "legendExit", hide: "legendHide", standby: "legendStandby", camera: "legendCamera", robot: "legendRobot", alarm: "legendAlarm",
};

/** 底图的灰度(站点 map_preview:空地 254、墙 0、看到过 232、未知 205;平面图:地面白、墙深灰、看到过是
 *  透明度 0.35 的白、未知透明;路沿两种都是 150)。 */
const SHADE = { raster: { floor: 254, wall: 0, seen: 232, unknown: 205, curb: 150 }, plan: { floor: 255, wall: 34, seenAlpha: 0.35, curb: 150 } };

/** 标记层用:地图坐标 / 预览像素 → 屏上。 */
export interface Screen {
  map(x: number, y: number): Pt;
  px(px: number, py: number): Pt;
  k: number;
}

/** 量不到大小(测试环境)时先用这个。 */
const FALLBACK: Box = { w: 960, h: 600 };

function useBox(ref: { current: HTMLElement | null }): Box {
  const [box, setBox] = useState<Box>(FALLBACK);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const read = () => {
      const r = el.getBoundingClientRect();
      if (r.width > 0 && r.height > 0) setBox((b) => (Math.abs(b.w - r.width) < 0.5 && Math.abs(b.h - r.height) < 0.5 ? b : { w: r.width, h: r.height }));
    };
    read();
    if (typeof ResizeObserver === "undefined") {
      window.addEventListener("resize", read);
      return () => window.removeEventListener("resize", read);
    }
    const ro = new ResizeObserver(read);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return box;
}

function polyAttr(meta: PreviewMeta, pts: Pt[]): string {
  return pts.map(([x, y]) => { const p = toPx(meta, x, y); return `${p.px},${p.py}`; }).join(" ");
}

/** 客户端坐标 → 某个 SVG 元素的用户坐标(浏览器给的 CTM 倒回去)。 */
function fromClient(el: SVGGraphicsElement | null, x: number, y: number): Pt | null {
  const m = el?.getScreenCTM();
  if (!m) return null;
  const i = m.inverse();
  return [i.a * x + i.c * y + i.e, i.b * x + i.d * y + i.f];
}

export function MapCanvas(props: {
  meta: PreviewMeta;
  /** 栅格预览(preview.png)的地址;站点给了平面图就画平面图,读不出来再退回它。 */
  raster: string;
  label: string;
  areas?: CanvasArea[];
  /** 页面自己在标记层画了的、要进图例的(狗、报警点)。 */
  legend?: LegendKey[];
  /** 世界层里多画的(预览像素坐标)。 */
  world?: ComponentChildren;
  /** 标记层里多画的(屏上坐标)。 */
  marks?: (s: Screen) => ComponentChildren;
  /** 标记层里区域名要让开的东西(狗、报警点),屏上坐标。 */
  avoid?: (s: Screen) => Obstacle[];
  drawing?: boolean;
  /** 点了图(不是拖):点的那一处的预览像素。 */
  onPick?: (px: number, py: number) => void;
  /** 第 2 轮 P1-53:给了就按住拖出方框(起点、当前点,预览像素;松手 done),不平移地图。 */
  onDragRect?: (a: [number, number], b: [number, number], done: boolean) => void;
  /** 浮在地图上的东西(比如「去这里」小卡片),放在图框里、不占图下面的高。 */
  overlay?: ComponentChildren;
  /** 图例那一行里多加的项(页面自己画的图层,比如规划路径、轨迹),跟底图图例排一行。 */
  legendExtra?: ComponentChildren;
  /** 画不画禁行区、限速区、虚拟墙(默认画;W44 地图页禁行区图层默认关)。抹掉区照画。 */
  navZones?: boolean;
}) {
  const { meta } = props;
  const wrap = useRef<HTMLDivElement>(null);
  const svg = useRef<SVGSVGElement>(null);
  const world = useRef<SVGGElement>(null);
  const box = useBox(wrap);
  const [planBad, setPlanBad] = useState<string | null>(null);
  const plan = meta.plan && typeof meta.plan.url === "string" && meta.plan.url && planBad !== meta.plan.url ? meta.plan : null;
  const rot = rotationOf(meta);
  // 换了图(或者转角、大小变了)就回到全图;没动过也一直是全图(框变大小跟着重新放)
  const key = `${props.raster}|${rot}|${meta.width}x${meta.height}`;
  const [user, setUser] = useState<{ key: string; v: View } | null>(null);
  const view = user && user.key === key ? clampView(meta, box, user.v) : fitView(meta, box);
  const live = useRef(view);
  live.current = view;
  const M = worldMatrix(meta, view);
  const setView = (v: View) => {
    const c = clampView(meta, box, v);
    live.current = c;
    setUser({ key, v: c });
  };

  const drag = useRef<{ id: number; x: number; y: number; v: View; moved: boolean } | null>(null);
  const dragged = useRef(false);
  const [dragging, setDragging] = useState(false);

  function onWheel(e: WheelEvent) {
    e.preventDefault();
    const dy = e.deltaMode === 1 ? e.deltaY * 16 : e.deltaMode === 2 ? e.deltaY * box.h : e.deltaY;
    if (!Number.isFinite(dy) || dy === 0) return;
    // 以指针下面那一点为定点;事件里没有指针位置就以框的中心
    const q = Number.isFinite(e.clientX) && Number.isFinite(e.clientY) ? fromClient(svg.current, e.clientX, e.clientY) : null;
    const [qx, qy] = q ?? [box.w / 2, box.h / 2];
    setView(zoomView(live.current, Math.exp(-Math.max(-600, Math.min(600, dy)) * 0.0015), qx, qy));
  }
  function onPointerDown(e: PointerEvent) {
    if (e.button !== 0) return;
    dragged.current = false;
    drag.current = { id: e.pointerId, x: e.clientX, y: e.clientY, v: live.current, moved: false };
  }
  function onPointerMove(e: PointerEvent) {
    const d = drag.current;
    if (!d || d.id !== e.pointerId) return;
    if (!d.moved) {
      if (Math.hypot(e.clientX - d.x, e.clientY - d.y) < 5) return;
      d.moved = true;
      setDragging(true);
      try { svg.current?.setPointerCapture(e.pointerId); } catch { /* 拿不到也能拖 */ }
    }
    if (props.onDragRect) {
      const a = fromClient(world.current, d.x, d.y);
      const b = fromClient(world.current, e.clientX, e.clientY);
      if (a && b) props.onDragRect(a, b, false);
      return;
    }
    const a = fromClient(svg.current, d.x, d.y);
    const b = fromClient(svg.current, e.clientX, e.clientY);
    if (a && b) setView({ k: d.v.k, cx: d.v.cx + b[0] - a[0], cy: d.v.cy + b[1] - a[1] });
  }
  function onPointerEnd(e: PointerEvent) {
    const d = drag.current;
    if (!d || d.id !== e.pointerId) return;
    // 拖过:接下来那一下 click 不算点(不选狗、不加角)
    if (d.moved && e.type === "pointerup") dragged.current = true;
    if (d.moved && props.onDragRect) {
      const a = fromClient(world.current, d.x, d.y);
      const b = fromClient(world.current, e.clientX, e.clientY);
      if (a && b) props.onDragRect(a, b, e.type === "pointerup");
    }
    drag.current = null;
    setDragging(false);
  }
  function onClickCapture(e: MouseEvent) {
    if (!dragged.current) return;
    dragged.current = false;
    e.stopPropagation();
    e.preventDefault();
  }
  function onClick(e: MouseEvent) {
    if (!props.onPick) return;
    const p = fromClient(world.current, e.clientX, e.clientY);
    if (p) props.onPick(p[0], p[1]);
  }

  const screen: Screen = {
    map: (x, y) => { const p = toPx(meta, x, y); return applyMat(M, p.px, p.py); },
    px: (px, py) => applyMat(M, px, py),
    k: view.k,
  };
  const obstacles = props.avoid?.(screen) ?? [];
  const zones = (meta.zones ?? []).filter((z) => Array.isArray(z.polygon) && z.polygon.length >= 3)
    .filter((z) => props.navZones !== false || z.kind === "erase");
  const areas = props.areas ?? [];
  const present = new Set<LegendKey>(["floor", "wall", "unknown", ...(props.legend ?? [])]);
  if (zones.some((z) => z.kind === "nogo" && !z.hard && !z.wall)) present.add("nogo");
  if (zones.some((z) => z.kind === "nogo" && z.hard && !z.wall)) present.add("hard");
  if (zones.some((z) => !!z.wall)) present.add("vwall");
  if (zones.some((z) => z.kind === "slow")) present.add("slow");
  if (zones.some((z) => z.kind === "ignore")) present.add("ignore");
  // 地图台账 M9、44:看到过、狗没走过(站点说这一版有才列);抹掉区(站点已经把那一块画成没建图,这里只描边)
  if (meta.seen === true) present.add("seen");
  if (meta.curb === true) present.add("curb");   // 路沿、绿化岛(11-10)
  if (zones.some((z) => z.kind === "erase")) present.add("erase");
  for (const a of areas) present.add(a.kind);
  const bar = scaleBar(meta.m_per_px, view.k);
  const cls = ["map", props.drawing ? "drawing" : "", dragging ? "dragging" : ""].filter(Boolean).join(" ");

  return (
    <div class="mapcanvas">
      <div class="mapwrap" ref={wrap}>
        <svg ref={svg} class={cls} viewBox={`0 0 ${box.w} ${box.h}`} role="img" aria-label={props.label}
          onWheel={onWheel} onPointerDown={onPointerDown} onPointerMove={onPointerMove} onPointerUp={onPointerEnd}
          onPointerCancel={onPointerEnd} onClickCapture={onClickCapture} onClick={onClick}>
          <g class="map-world" ref={world} transform={matrixAttr(M)}>
            {/* 第 9 轮 W6-15:深色下平面图的「未建图」是透明的、露出页面底色,「已扫描未到达」(半透明的地面色)
                叠上去跟它几乎一样。垫一层栅格「未建图」的灰,三种灰跟栅格图一样分得开 */}
            {plan && scheme.value === "dark" && <rect x="0" y="0" width={meta.width} height={meta.height} fill={rasterShade(SHADE.raster.unknown, "dark")} data-plan-backdrop="1" />}
            <image key={plan ? plan.url : props.raster} href={plan ? plan.url : props.raster} x="0" y="0" width={meta.width} height={meta.height}
              preserveAspectRatio="none" class={plan ? "mapimg plan" : "mapimg"}
              onError={plan ? () => setPlanBad(plan.url) : undefined} />
            {/* 虚拟墙(2026-10-15)画成一条粗线(画的那条),不画站点算的那条窄带子 */}
            {zones.map((z) => (z.kind === "nogo" || z.kind === "slow" || z.kind === "erase" || z.kind === "ignore") && !z.wall && (
              <polygon key={z.id} points={polyAttr(meta, z.polygon)}
                class={z.kind === "nogo" ? (z.hard ? "nogo-area hard" : "nogo-area") : z.kind === "erase" ? "erase-area" : z.kind === "ignore" ? "ignore-area" : "slow-area"}>
                {(z.kind === "nogo" || z.kind === "erase") && <title>{navZoneTip(z)}</title>}
              </polygon>
            ))}
            {zones.filter((z) => Array.isArray(z.wall) && z.wall.length >= 2).map((z) => (
              <polyline key={`w:${z.id}`} points={polyAttr(meta, z.wall!)} class={z.hard ? "vwall-line hard" : "vwall-line"} data-vwall={z.id}>
                <title>{navZoneTip(z)}</title>
              </polyline>
            ))}
            {areas.map((a, i) => (
              <polygon key={`${i}:${a.kind}:${a.name}`} points={polyAttr(meta, a.pts)} class={`${a.kind === "zone" || a.kind === "region" ? "sec-area" : "sec-area quiet"}${a.kind === "region" ? " region" : ""}${a.tone ? ` ${a.tone}` : ""}${a.hot ? " hot" : ""}${a.sel ? " sel" : ""}`} data-area={a.name} />
            ))}
            {props.world}
          </g>
          <g class="map-marks">
            {/* P2-15:禁区上写名字(屏上的字,跟区域名一样:正的、不跟着缩放;屏上放不下就不写) */}
            {zones.filter((z) => z.kind === "nogo" && !z.wall && z.polygon.length >= 3 && (z.label || z.id)).map((z) => {
              const text = siteKnown(z.label) || z.id;
              const at = placeLabel(z.polygon.map(([x, y]) => screen.map(x, y)), text, 12, obstacles);
              if (!at) return null;
              return <text key={`n:${z.id}`} x={at[0]} y={at[1]} class="nogo-name" data-nogo-name={z.id} font-size={12} dominant-baseline="central">{text}</text>;
            })}
            {areas.map((a, i) => {
              const font = a.kind === "zone" || a.kind === "region" ? 14 : 13;
              const text = a.label ?? a.name;
              const sp = a.pts.map(([x, y]) => screen.map(x, y));
              // 第 3 轮 maps N3:起了名字的区域放不下名字就写在它上边外面(原来干脆不写,框上看不出是哪块)
              const at = placeLabel(sp, text, font, obstacles)
                ?? (a.kind === "region" && sp.length ? [(Math.min(...sp.map((p) => p[0])) + Math.max(...sp.map((p) => p[0]))) / 2, Math.min(...sp.map((p) => p[1])) - 10] as Pt : null);
              if (!at) return null;
              const [x, y] = at;
              return (
                <text key={`${i}:${a.kind}:${a.name}`} x={x} y={y} class={a.kind === "zone" || a.kind === "region" ? "area-label" : "area-label quiet"}
                  font-size={font} dominant-baseline="central">{text}</text>
              );
            })}
            {props.marks?.(screen)}
          </g>
        </svg>
        {props.overlay}
      </div>
      <div class="mapbar">
        <LegendBar keys={LEGEND_ORDER.filter((k) => present.has(k))} plan={!!plan} extra={props.legendExtra} />
        <div class="mapctl">
          <span class="scale" role="img" aria-label={t("scaleAria", { m: bar.m })}>
            <svg class="scalebar" width={bar.px + 2} height="10" data-px={bar.px} aria-hidden="true"><path d={`M1 1V9H${bar.px + 1}V1`} /></svg>
            <span class="scale-label" aria-hidden="true">{t("scaleM", { m: bar.m })}</span>
          </span>
          <button type="button" class="btn sm" title={t("wholeMapHint")} onClick={() => setUser(null)}>{t("wholeMap")}</button>
        </div>
      </div>
    </div>
  );
}

/** 悬停在禁行区、抹掉区上看到的那句话:名字、是不是硬禁区(决策 65)、临时区什么时候到期(决策 66)。 */
export function navZoneTip(z: NavZone): string {
  const name = siteKnown(z.label) || z.id;
  const base = z.wall
    ? (z.hard ? t("hardVWallTip", { label: name }) : t("vwallTip", { label: name }))
    : z.kind === "erase"
      ? (z.hard ? t("hardEraseTip", { label: name }) : t("eraseTip", { label: name }))
      : z.hard ? t("hardNoGoTip", { label: name }) : t("noGoTip", { label: name });
  if (typeof z.until_ms !== "number") return base;
  const d = new Date(z.until_ms);
  const two = (v: number) => String(v).padStart(2, "0");
  return base + t("zoneUntil", { t: `${two(d.getMonth() + 1)}-${two(d.getDate())} ${two(d.getHours())}:${two(d.getMinutes())}` });
}

/** 图例里的一小块,跟图上画的一样(底图的灰度按现在的主题算,跟 --map-raster 一样)。 */
function Swatch({ k, plan }: { k: LegendKey; plan: boolean }) {
  const s = scheme.value;
  const shade = (g: number) => rasterShade(g, s);
  let body: ComponentChildren;
  if (k === "floor") body = <rect x="0.5" y="0.5" width="15" height="11" fill={shade(plan ? SHADE.plan.floor : SHADE.raster.floor)} class="sw-edge" />;
  else if (k === "wall") body = <rect x="0.5" y="0.5" width="15" height="11" fill={shade(plan ? SHADE.plan.wall : SHADE.raster.wall)} class="sw-edge" />;
  else if (k === "seen") body = plan
    ? <><rect x="0.5" y="0.5" width="15" height="11" class={s === "dark" ? "sw-edge" : "sw-bg sw-edge"} fill={s === "dark" ? shade(SHADE.raster.unknown) : undefined} /><rect x="0.5" y="0.5" width="15" height="11" fill={shade(SHADE.plan.floor)} fill-opacity={SHADE.plan.seenAlpha} /></>
    : <rect x="0.5" y="0.5" width="15" height="11" fill={shade(SHADE.raster.seen)} class="sw-edge" />;
  else if (k === "curb") body = <rect x="0.5" y="0.5" width="15" height="11" fill={shade(plan ? SHADE.plan.curb : SHADE.raster.curb)} class="sw-edge" />;
  else if (k === "erase") body = <rect x="1" y="1" width="14" height="10" class="erase-area" />;
  else if (k === "unknown") body = plan && s !== "dark"
    ? <rect x="0.5" y="0.5" width="15" height="11" class="sw-bg sw-edge" />
    : <rect x="0.5" y="0.5" width="15" height="11" fill={shade(SHADE.raster.unknown)} class="sw-edge" />;
  else if (k === "nogo") body = <rect x="1" y="1" width="14" height="10" class="nogo-area" />;
  else if (k === "hard") body = <rect x="1.5" y="1.5" width="13" height="9" class="nogo-area hard" />;
  else if (k === "slow") body = <rect x="1" y="1" width="14" height="10" class="slow-area" />;
  else if (k === "ignore") body = <rect x="1" y="1" width="14" height="10" class="ignore-area" />;
  else if (k === "vwall") body = <path d="M1 9L7 3L15 3" class="vwall-line" />;
  else if (k === "area") body = <rect x="1" y="1" width="14" height="10" class="sec-area quiet" />;
  else if (k === "zone") body = <rect x="1" y="1" width="14" height="10" class="sec-area" />;
  else if (k === "region") body = <rect x="1" y="1" width="14" height="10" class="sec-area region" />;
  else if (k === "ref") body = <rect x="1" y="1" width="14" height="10" class="sec-area quiet" />;
  else if (k === "exit") body = <path d="M1 6L15 6" class="mark-exit" />;
  else if (k === "hide") body = <circle cx="8" cy="6" r="4" class="sw-hide" />;
  else if (k === "robot") body = <circle cx="8" cy="6" r="5" class="sw-robot" />;
  // 第 4 轮 setup N3:待命点、摄像头标签的图例里有本标签的图标
  else if (k === "standby") body = <circle cx="8" cy="6" r="5" class="sw-standby" />;
  else if (k === "camera") body = <><path d="M8 6L15 1.5V10.5Z" class="sw-camfan" /><circle cx="6" cy="6" r="4" class="sw-cam" /></>;
  else body = <path d="M8 0.5l5.5 5.5-5.5 5.5-5.5-5.5z" class="sw-alarm" />;
  return <svg class="sw" width="16" height="12" viewBox="0 0 16 12" aria-hidden="true">{body}</svg>;
}

/** 地图下面的图例。第 3 轮 P2-31:项多了收成「图例」按钮,点开是完整的一列。
 *  第 4 轮 layout P2-31 / N2、zh N7:按实际宽度收(放不下就收,不只看条数);点外面、按 Esc 收起。 */
function LegendBar({ keys, plan, extra }: { keys: LegendKey[]; plan: boolean; extra?: ComponentChildren }) {
  const ul = useRef<HTMLUListElement>(null);
  const fold = useRef<HTMLDetailsElement>(null);
  const [tight, setTight] = useState(false);
  const [width, setWidth] = useState(0);
  const many = keys.length > LEGEND_INLINE;
  // 宽度变了先按一行试,放不下再收
  useLayoutEffect(() => { setTight(false); }, [width, keys.join()]);
  useLayoutEffect(() => {
    const el = ul.current;
    if (!many && !tight && el && el.scrollWidth > el.clientWidth + 1) setTight(true);
  });
  useEffect(() => {
    const bar = (ul.current ?? fold.current)?.parentElement;
    if (!bar || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver((es) => setWidth(Math.round(es[0].contentRect.width)));
    ro.observe(bar);
    return () => ro.disconnect();
  }, []);
  useEffect(() => {
    const close = (e: Event) => {
      const d = fold.current;
      if (!d?.open) return;
      if (e instanceof KeyboardEvent ? e.key === "Escape" : !d.contains(e.target as Node)) d.open = false;
    };
    document.addEventListener("keydown", close);
    document.addEventListener("pointerdown", close);
    return () => { document.removeEventListener("keydown", close); document.removeEventListener("pointerdown", close); };
  }, []);
  const folded = many || tight;
  const list = (
    <ul ref={ul} class={folded ? "maplegend pop" : "maplegend"} aria-label={t("legend")}>
      {keys.map((k) => (
        <li key={k} data-legend={k}><Swatch k={k} plan={plan} />{t(LEGEND_TEXT[k])}</li>
      ))}
      {extra}
    </ul>
  );
  return folded
    ? <details ref={fold} class="legend-fold"><summary>{t("legend")} · {keys.length}</summary>{list}</details>
    : list;
}
