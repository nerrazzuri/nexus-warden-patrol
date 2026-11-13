import type { ComponentChildren } from "preact";
// 地图页签(B0 专业版 2.4):地图铺满 + 右侧栏。正常的狗绿点 + 朝向;异常的用形状 + 颜色;P1 位置是
// 菱形 + 报警圈(未确认时闪)。侧栏只给**选中**的狗拉前后两路小画面(有 P1 时默认选 P1 的狗)。
// 地图本身(转正、全图、缩放平移、区域名、图例、比例尺、平面图)在 mapcanvas.tsx;狗和报警点画在屏上坐标里
// (大小不跟着缩放变),位置用跟底图同一个变换算。
import { siteStr } from "./sitetext";
import { useEffect, useMemo, useState } from "preact/hooks";
import { reportStart, type StartCheck } from "./alertinfo";
import { api, ApiError, enc } from "./api";
import { hm, nameOf, useDutySettings } from "./data";
import { siteHm } from "./todaypatrols";
import { Modal } from "./dialogs";
import { alertTitle, andList, lang, refusalText, t, type Key } from "./i18n";
import { pageAllowed } from "./shell";
import { locText, type UnitInfo } from "./live";
import { ENGINEERING_LAYERS, etaNext, fanOut, labelAbove, LAYERS, layersFor, loadLayers, saveLayers, labelRows, mapPins, mapTodo, olderOpen, shiftStart, staleAfter, staleCells, tonightEvents, zoneDecor,
  type AuthzRow, type Cell, type Layer, type ModeView } from "./maplayers";
import { fanPath } from "./layoutpage";
import { MapCanvas, type CanvasArea, type LegendKey, type Screen } from "./mapcanvas";
import { heading, namedAreas, onMap, toPx, type PreviewMeta, type Pt } from "./mapview";
import { abnormal, alarmState, autoResolved, canArm, canDispatch, canFindPose, canPatrol, robotMap, type Alert } from "./model";
import { notAccepted, usePosePick, type CommandReply } from "./posepick";
import { pxToMap, yawToward } from "./routes";
import { RunLegendItems, VizWorld, vizAvoid, vizHas, vizMarks, vizOnMap } from "./runlayers";
import { useEpisodes, useRunViz } from "./runviz";

/** 屏上的大小(像素):狗的圆点半径、报警圈半径、狗编号字号。 */
const BOT_R = 7;
const PIN_R = 14;
const LABEL_PX = 12;

/**
 * 地图页上的区域:站点在预览里给的 areas(有名字的区域)在前;防区接口(老站点只有它)里同名的不重画。
 */
export function mapAreas(meta: PreviewMeta, sec: { zone: string; points: Pt[] }[]): CanvasArea[] {
  const named = namedAreas(meta).map((a): CanvasArea => ({ name: a.name, pts: a.pts, kind: "area" }));
  const seen = new Set(named.map((a) => a.name));
  for (const s of sec) {
    if (!s.zone || seen.has(s.zone) || !Array.isArray(s.points) || s.points.length < 3) continue;
    seen.add(s.zone);
    named.push({ name: s.zone, pts: s.points, kind: "area" });
  }
  // W44 第四期:地图编辑器里起的区域名(A区、北区……)也画上
  for (const r of meta.display?.regions ?? []) {
    if (!r.name || seen.has(r.name) || !Array.isArray(r.polygon) || r.polygon.length < 3) continue;
    seen.add(r.name);
    named.push({ name: r.name, pts: r.polygon, kind: "area" });
  }
  return named;
}

/** 地图本体(W44:值班页下半屏、地图页共用):底图、区域、机器人、报警圈、运行图层、点图「去这里 / 在这里设位置」。 */
const NO_AREAS: { zone: string; points: Pt[] }[] = [];

export function SiteMap(props: {
  units: UnitInfo[];
  /** 图上画报警圈的告警(带位置的)。 */
  p1: Alert[];
  now: number;
  selected: string | null;
  onSelect: (id: string) => void;
  role?: string;
  /** 标红的防区(报警的那几个,W44 值班页)。 */
  hot?: Set<string>;
  /** 画不画「近 7 天定位出过问题的地方」(保安页不画,设计 §4.3)。 */
  episodes?: boolean;
  /** 能不能点图「去这里 / 在这里设位置」(默认能;值班页只在「帮它找位置」时能)。 */
  pick?: boolean;
  /** 浮在图左上角的一句提示(值班页「帮它找位置」时说怎么做)。 */
  hint?: string | null;
  /** 第 2 轮 P1-56:「帮它定位」设完位置、机器人定位好了(页面退出定位模式)。 */
  onLocated?: (robotId: string) => void;
  /** 这张图上有名字的区域(值班页拿来算每台机器人在哪个防区)。 */
  onAreas?: (areas: CanvasArea[]) => void;
  /** 点图交给页面(地图页:让最近的机器人过去看看、临时路线);给了就不进「去这里 / 设位置」。坐标是地图米。 */
  onPickMap?: (x: number, y: number, map: { map_id: string; version: string }) => void;
  /** 画不画禁行区、限速区、虚拟墙(地图页的禁行区图层,默认关)。默认画。 */
  navZones?: boolean;
  /** 画不画规划路径、轨迹(地图页的巡逻路线图层)。默认画。 */
  route?: boolean;
  /** 防区标签、颜色(地图页的防区和布防图层)。 */
  areaDecor?: (name: string) => { label: string; tone: "armed" | "off" } | null;
  /** 世界层(预览像素)、标记层(屏上)里页面自己多画的。 */
  extraWorld?: (meta: PreviewMeta, map: { map_id: string; version: string }) => ComponentChildren;
  extraMarks?: (s: Screen, meta: PreviewMeta, map: { map_id: string; version: string }) => ComponentChildren;
  /** 在巡逻的机器人下面写「下一个点约 N 分钟」(地图页的巡逻路线图层)。 */
  eta?: boolean;
  /** 现在画的是哪张图(页面按它去拉轨迹覆盖、待命点)。 */
  onMapShown?: (map: { map_id: string; version: string } | null, meta: PreviewMeta | null) => void;
  /** 连不上站点(没有机器人数据时不说「没有地图」)。 */
  stale?: boolean;
  /** 预览拉不到隔多久再拉(毫秒;测试里调小)。 */
  retryMs?: number;
}) {
  const sel = props.units.find((u) => u.robot.robot_id === props.selected) ?? props.units[0];
  // 底图跟着选中的狗(外审 W39-I2:原来总是第一只有图的狗,选中的狗可能在另一张图上);选中的狗没报图
  // 才退回第一只有图的
  const selMap = sel ? robotMap(sel.robot) : null;
  const which = selMap ?? props.units.map((u) => robotMap(u.robot)).find((m) => m) ?? null;
  const key = which ? `${which.map_id}/${which.version}` : "";
  // 预览、区域记着是哪张图的:换图以后才回来的旧回包不认
  const [got, setGot] = useState<{ key: string; meta: PreviewMeta | null; areas: { zone: string; points: Pt[] }[]; failed?: boolean }>({ key: "", meta: null, areas: [] });
  // 第 2 轮:预览拉不到(断线)不能当成「没有地图」—— 记着失败了,按 retryMs 再拉,拉到为止
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    if (!which) return;
    let live = true;
    const base = `/api/maps/${enc(which.map_id)}/${enc(which.version)}`;
    let timer = 0;
    api<PreviewMeta>("GET", `${base}/preview`).then((m) => live && setGot((g) => ({ key, meta: m, areas: g.key === key ? g.areas : [] })))
      .catch(() => {
        if (!live) return;
        setGot((g) => ({ key, meta: g.key === key ? g.meta : null, areas: g.key === key ? g.areas : [], failed: true }));
        timer = window.setTimeout(() => setRetry((n) => n + 1), props.retryMs ?? 5_000);
      });
    api<{ areas: { zone: string; points: Pt[] }[] }>("GET", `${base}/areas`).then((d) => live && setGot((g) => ({ ...g, key, meta: g.key === key ? g.meta : null, areas: d.areas })))
      .catch(() => {});
    return () => { live = false; window.clearTimeout(timer); };
  }, [key, retry]);
  const meta = got.key === key ? got.meta : null;
  const loadFailed = got.key === key && !!got.failed && !meta;
  // 没载入时也用同一个空列表:每次给新的 [] 会让回报区域的效果每次渲染都触发,页面跟着重画,停不下来
  const areas = got.key === key ? got.areas : NO_AREAS;
  const onAreas = props.onAreas;
  useEffect(() => {
    if (onAreas) onAreas(meta ? mapAreas(meta, areas) : []);
  }, [meta, areas]);
  const onMapShown = props.onMapShown;
  useEffect(() => {
    if (onMapShown) onMapShown(which && meta ? { map_id: which.map_id, version: which.version } : null, meta);
  }, [key, meta]);
  // 只画加载着这张图的狗(别的图上的坐标画在这张图上是错的)
  const onThisMap = (u: UnitInfo) => { const m = robotMap(u.robot); return !!(m && which && m.map_id === which.map_id && m.version === which.version); };
  // 点图 → 去这里 / 在这里设位置(posepick.tsx;只有管理员、保安)
  const pose = usePosePick({ meta, map: which ? { map_id: which.map_id, version: which.version } : null,
    robotId: sel?.robot.robot_id ?? null, robotMap: selMap,
    robotAt: sel && onThisMap(sel) ? sel.robot.loc?.pose ?? null : null, role: props.role ?? "",
    canFind: canFindPose(sel?.robot), locate: props.pick === true,
    locNow: locText(sel ?? undefined), hint: props.pick === true ? props.hint : null,
    onSettled: props.onLocated });
  // 运行可视化:规划路径、轨迹、被挡位置(2 s 一拉),近 7 天定位出过问题的地方
  const viz = useRunViz(!!which);
  const vizRobots = which ? vizOnMap(viz, which.map_id, which.version) : [];
  const since = useMemo(() => Date.now() - 7 * 86_400_000, [key]);
  const { rows: episodes } = useEpisodes({ map_id: which?.map_id, map_version: which?.version, since_ms: since, limit: 300 }, !!which && props.episodes !== false);
  const eps = props.episodes === false ? [] : episodes ?? [];
  const etaOf = (u: UnitInfo): number | null => {
    if (u.state !== "patrolling") return null;
    const v = vizRobots.find(([id]) => id === u.robot.robot_id)?.[1];
    const p = u.robot.loc?.pose;
    return etaNext(v?.path, p ? [p.x, p.y] : null);
  };

  // 图上真画得出来的报警点、狗(图例只列有的)
  const pins = !which || !meta ? [] : props.p1.flatMap((a) => {
    const p = a.context?.pose;
    if (!p || p.map_id !== which.map_id || p.map_version !== which.version) return [];
    const { px, py } = toPx(meta, p.x, p.y);
    return onMap(meta, px, py) ? [{ a, px, py }] : [];
  });
  const bots = !meta ? [] : props.units.flatMap((u) => {
    const pose = u.robot.loc?.pose;
    if (!pose || !onThisMap(u)) return [];
    const { px, py } = toPx(meta, pose.x, pose.y);
    return onMap(meta, px, py, 20) ? [{ u, px, py, yaw: pose.yaw }] : [];
  });
  // P2-15:机器人、报警两项一直在图例里(没有的时候也说清是什么样子)
  const legend: LegendKey[] = ["robot", "alarm"];

  return (
    <div class="mapbox" {...pose.wrapProps}>
        {!which || !meta ? (
          <p class={loadFailed || (!which && props.stale) ? "empty warn" : "empty"} role="status">
            {t(loadFailed || (!which && props.stale) ? "loadRetry" : "noMap")}</p>
        ) : (
          <MapCanvas meta={meta} raster={`/api/maps/${enc(which.map_id)}/${enc(which.version)}/preview.png`} label={t("mapAria")}
            areas={mapAreas(meta, areas).map((a) => {
              const d = props.areaDecor?.(a.name);
              return { ...a, ...(d ? { label: d.label, tone: d.tone } : {}), ...(props.hot?.has(a.name) ? { hot: true } : {}) };
            })}
            navZones={props.navZones} legend={legend} drawing={!!(props.onPickMap ?? (props.pick === false ? undefined : pose.onPick))}
            onPick={props.onPickMap ? (px, py) => { const [x, y] = pxToMap(meta, px, py); props.onPickMap!(x, y, which); }
              : props.pick === false ? undefined : pose.onPick}
            world={<>{props.route !== false && <VizWorld meta={meta} robots={vizRobots} />}{props.extraWorld?.(meta, which)}</>}
            // 「去这里」浮在图的右上角(不在图下面另占一块);运行图层的图例并进底图图例那一行
            // 第 2 轮 P1-56:定位时那句说明放进设位置的小卡片里(原来左上一句、卡片里一句、侧栏一句,还互相压着)
            overlay={<>{props.hint && !(props.pick === true && pose.panel) && <div class="map-hint" role="status">{props.hint}</div>}{!props.onPickMap && props.pick !== false && pose.panel}</>}
            legendExtra={<RunLegendItems has={vizHas(vizRobots, eps)} />}
            // 区域名让开报警圈、狗(圆点 + 下面的编号)
            avoid={(s) => [
              ...vizAvoid(s, meta, vizRobots),
              ...pins.map(({ px, py }) => { const [x, y] = s.px(px, py); return { x, y, r: PIN_R + 2 }; }),
              ...bots.map(({ px, py }) => { const [x, y] = s.px(px, py); return { x, y: y + LABEL_PX / 2, r: BOT_R + LABEL_PX + 4 }; }),
            ]}
            marks={(s) => (
              <>
                {!props.onPickMap && props.pick !== false && pose.marks(s)}
                {props.route !== false && vizMarks(s, meta, vizRobots, eps)}
                {props.extraMarks?.(s, meta, which)}
                {pins.map(({ a, px, py }) => {
                  const [x, y] = s.px(px, py);
                  const h = PIN_R / 2.5;
                  return (
                    <g key={a.key} class={alarmState(a, props.now) === "unacked" ? "alarm-pin flash" : "alarm-pin"}>
                      <circle cx={x} cy={y} r={PIN_R} class="ring" />
                      <path d={`M${x} ${y - h}l${h} ${h}-${h} ${h}-${h}-${h}z`} class="diamond" />
                    </g>
                  );
                })}
                {(() => {
                  // W6-15:停在同一处的几台摊开画(不然后一台的点盖住前一台),细线连回原位
                  const real = bots.map((b) => s.px(b.px, b.py));
                  const fan = fanOut(real, BOT_R * 2 + 3);
                  const rows = labelRows(fan, BOT_R * 4);
                  const above = labelAbove(fan, BOT_R, LABEL_PX);
                  const step = (LABEL_PX + 2) * (props.eta ? 2 : 1);
                  return bots.map(({ u, px, py, yaw }, i) => {
                  const [x, y] = fan[i];
                  const [rx, ry] = real[i];
                  const moved = Math.hypot(x - rx, y - ry) > 0.5;
                  // 第 9 轮 W6-15:名字底下压着另一台的点 → 画到点上面(往上错开)
                  // (挪上去时最后一行字的底边在点上面 2 像素;有「第几圈 · 多久到」那一行也算进去)
                  const dy = above[i] ? -(BOT_R * 2 + 4) - step - rows[i] * step : rows[i] * step;
                  // 朝向:在预览上往 yaw 走一小段,跟着图一起变换,再在屏上取定长
                  const e = heading(px, py, yaw, 10);
                  const [ex0, ey0] = s.px(e.hx, e.hy);
                  const ex = ex0 + x - rx, ey = ey0 + y - ry;
                  const n = Math.hypot(ex - x, ey - y) || 1;
                  const len = BOT_R * 2.2;
                  const a = abnormal(u.state);
                  const on = u.robot.robot_id === sel?.robot.robot_id;
                  return (
                    <g key={u.robot.robot_id} class={`bot ${a ?? "ok"}${on ? " on" : ""}`} onClick={(e) => {
                      // 第 4 轮 maps N3:点已选中的这台本身 = 在它身上选点(帮它定位时最自然的点法),交给地图
                      if (on && pose.onPick && props.pick === true && !props.onPickMap) return;   // 只在「帮它定位」时(pick 明说要选点)
                      e.stopPropagation(); props.onSelect(u.robot.robot_id);
                    }}>
                      {moved && <line x1={rx} y1={ry} x2={x} y2={y} class="bot-leader" data-bot-leader="1" />}
                      <line x1={x} y1={y} x2={x + ((ex - x) / n) * len} y2={y + ((ey - y) / n) * len} class="bot-head" />
                      <circle cx={x} cy={y} r={BOT_R} class="bot-dot" />
                      <text x={x} y={y + dy + BOT_R + LABEL_PX + 2} class="bot-label" font-size={LABEL_PX}>{nameOf(u.robot.robot_id)}</text>
                      {/* 第 9 轮 W8-04:几圈的巡逻写第几圈,后面跟多久到下一个点 */}
                      {props.eta && (etaOf(u) != null || u.task) && (
                        <text x={x} y={y + dy + BOT_R + LABEL_PX * 2 + 4} class="bot-label eta" font-size={LABEL_PX - 1} data-bot-eta="1">
                          {[u.task, etaOf(u) != null ? t("etaNextMin", { n: Math.max(1, Math.round(etaOf(u)! / 60)) }) : ""].filter(Boolean).join(" · ")}
                        </text>
                      )}
                    </g>
                  );
                  });
                })()}
              </>
            )} />
        )}
      </div>
  );
}

export function MapPage(props: {
  units: UnitInfo[];
  p1: Alert[];
  now: number;
  selected: string | null;
  onSelect: (id: string) => void;
  onVideo: (id: string) => void;
  role?: string;
  mode: ModeView | null;
  /** 保安的「全部布防」(设计 §11 第 14 条):模式不是布防时才有。 */
  onArm: () => void;
  say?: (s: string) => void;
  /** 连不上站点(第 2 轮:没有数据时不说「没有地图」)。 */
  stale?: boolean;
}) {
  const say = props.say ?? (() => {});
  const duty = useDutySettings();
  const [layers, setLayers] = useState<Set<Layer>>(loadLayers);
  const [shown, setShown] = useState<{ map: { map_id: string; version: string } | null; meta: PreviewMeta | null }>({ map: null, meta: null });
  const [look, setLook] = useState<{ at: Pt; map: { map_id: string; version: string } } | null>(null);
  const [route, setRoute] = useState<Pt[] | null>(null);
  // P1-16:派出去的临时路线留在图上(哪台在走);走过的地方由「路线」图层的轨迹画出
  // 第 2 轮 duty N2:派出后跟着出发检查的结果走 —— 被拒了侧栏写没出发、为什么,不再说「正在走」
  const [sentRoute, setSentRoute] = useState<{ robot: string; pts: Pt[]; refused?: string; at?: number } | null>(null);
  const [cells, setCells] = useState<{ cell_m: number; cells: Cell[] } | null>(null);
  const [authz, setAuthz] = useState<AuthzRow[]>([]);
  const [recent, setRecent] = useState<Alert[]>([]);
  const [standby, setStandby] = useState<{ name: string; x: number; y: number }[]>([]);
  // W44 第三期:固定摄像头放在图上的(管理员在「布置 → 摄像头」放的);点了看实时画面
  const [cams, setCams] = useState<PlacedCam[]>([]);
  const [liveCam, setLiveCam] = useState<string | null>(null);
  useEffect(() => {
    api<{ cameras: PlacedCam[] }>("GET", "/api/cameras").then((d) => setCams(d.cameras ?? [])).catch(() => setCams([]));
  }, []);
  const active = layersFor(layers, props.role ?? "");
  const on = (l: Layer) => active.has(l);
  const flip = (l: Layer) => {
    const n = new Set(layers);
    if (n.has(l)) n.delete(l);
    else n.add(l);
    saveLayers(n);
    setLayers(n);
  };
  const mapKey = shown.map ? `${shown.map.map_id}/${shown.map.version}` : "";

  // 本班出的事(含已处理的):30 秒一拉;第 4 轮 duty N4:顶栏的报警一变(推过来的)马上再拉,不等 30 秒
  const p1Key = props.p1.map((a) => `${a.key}:${a.count ?? 1}:${a.resolved_ms ?? ""}`).join(",");
  useEffect(() => {
    let live = true;
    const pull = () => api<{ alerts: Alert[] }>("GET", "/api/alerts?all=1&limit=200").then((d) => live && setRecent(d.alerts ?? [])).catch(() => {});
    void pull();
    const id = window.setInterval(pull, 30_000);
    return () => { live = false; window.clearInterval(id); };
  }, [p1Key]);
  useEffect(() => {
    let live = true;
    api<{ authorizations: AuthzRow[] }>("GET", "/api/lists/authorizations").then((d) => live && setAuthz(d.authorizations ?? [])).catch(() => {});
    return () => { live = false; };
  }, []);
  // 多久没巡过:最近 24 小时每格最后一次有机器人到过的时刻,一分钟一拉
  useEffect(() => {
    if (!shown.map || !on("stale")) return;
    let live = true;
    const m = shown.map;
    const pull = () => api<{ cell_m: number; cells: Cell[] }>("GET",
      `/api/coverage?map_id=${enc(m.map_id)}&map_version=${enc(m.version)}&since=${Date.now() - 86_400_000}`)
      .then((d) => live && setCells(d)).catch(() => live && setCells(null));
    void pull();
    const id = window.setInterval(pull, 60_000);
    return () => { live = false; window.clearInterval(id); };
  }, [mapKey, on("stale")]);
  // 待命点:这张图上各台机器人的
  useEffect(() => {
    if (!shown.map) return;
    let live = true;
    const m = shown.map;
    Promise.all(props.units.map((u) => api<{ points: { name: string; x: number; y: number; map_id: string; map_version: string }[] }>(
      "GET", `/api/robots/${enc(u.robot.robot_id)}/standby`).then((d) => d.points ?? []).catch(() => [])))
      .then((all) => live && setStandby(all.flat().filter((p) => p.map_id === m.map_id && p.map_version === m.version)));
    return () => { live = false; };
  }, [mapKey, props.units.length]);

  const since = shiftStart(props.now, duty.shift_hours);
  const events = tonightEvents(recent, since);
  const pins = mapPins(recent, since);
  const todo = mapTodo(recent, since);
  const older = olderOpen(recent, since);
  const stale = cells ? staleCells(cells.cells, props.now, staleAfter(duty.stale_hours)) : [];
  const onThisMap = (u: UnitInfo) => { const m = robotMap(u.robot); return !!(m && shown.map && m.map_id === shown.map.map_id && m.version === shown.map.version); };
  const robotsHere = props.units.filter((u) => u.state !== "offline" && onThisMap(u)).map((u) => u.robot.robot_id);
  const toRec = (a: Alert) => { location.hash = `#/recordings?robot=${enc(a.robot)}&t=${a.first_ms}`; };
  const names: Record<Layer, Key> = { zones: "layerZones", cameras: "layerCameras", route: "layerRoute", standby: "layerStandby",
    events: "layerEvents", stale: "layerStale", nogo: "layerNoGo", loc: "layerLoc" };

  return (
    <div class="mappage">
      <SiteMap units={props.units} p1={props.p1} now={props.now} selected={props.selected} onSelect={props.onSelect} role={props.role} stale={props.stale}
        episodes={on("loc")} navZones={on("nogo")} route={on("route")} eta={on("route")}
        areaDecor={on("zones") ? (n) => zoneDecor(n, props.mode, authz) : (n) => ({ label: n, tone: "armed" })}
        onMapShown={(map, meta) => setShown({ map, meta })}
        onPickMap={canDispatch(props.role ?? "") ? (x, y, map) => {
          if (route) setRoute([...route, [x, y]]);
          else setLook({ at: [x, y], map });
        } : canPatrol(props.role ?? "") && route ? (x, y) => setRoute([...route, [x, y]]) : undefined}
        hint={route ? t("trHint", { n: route.length }) : null}
        extraWorld={(meta) => (
          <>
            <defs>
              <pattern id="stale-hatch" width="8" height="8" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
                <rect width="8" height="8" class="stale-bg" /><line x1="0" y1="0" x2="0" y2="8" class="stale-line" />
              </pattern>
            </defs>
            {on("stale") && cells && stale.map((c) => {
              const tl = toPx(meta, c.i * cells.cell_m, (c.j + 1) * cells.cell_m);
              const w = cells.cell_m / meta.m_per_px;
              return <rect key={`${c.i}:${c.j}`} x={tl.px} y={tl.py} width={w} height={w} class="stale-cell" />;
            })}
            {on("cameras") && shown.map && camWorld(meta, camsOnMap(cams, shown.map))}
            {route && route.length > 1 && (
              <polyline class="temp-route" points={route.map(([x, y]) => { const p = toPx(meta, x, y); return `${p.px},${p.py}`; }).join(" ")} />
            )}
            {!route && sentRoute && !sentRoute.refused && sentRoute.pts.length > 1 && (
              <polyline class="temp-route sent" data-sent-route={sentRoute.robot}
                points={sentRoute.pts.map(([x, y]) => { const p = toPx(meta, x, y); return `${p.px},${p.py}`; }).join(" ")} />
            )}
          </>
        )}
        extraMarks={(s) => (
          <>
            {/* 第 2 轮 duty N9:点了哪儿就在哪儿标一下,确认框说的是这个点 */}
            {look && shown.map && look.map.map_id === shown.map.map_id && look.map.version === shown.map.version && (() => {
              const [x, y] = s.map(look.at[0], look.at[1]);
              return <g class="look-mark" data-look-mark="1"><circle cx={x} cy={y} r={10} /><circle cx={x} cy={y} r={3} class="dot" /></g>;
            })()}
            {on("cameras") && shown.map && camMarks(s, camsOnMap(cams, shown.map), setLiveCam)}
            {on("standby") && standby.map((p) => {
              const [x, y] = s.map(p.x, p.y);
              return <g key={`sb:${p.name}`} class="standby-mark"><rect x={x - 3} y={y - 3} width="6" height="6" /><text x={x + 6} y={y + 4}>{p.name}</text></g>;
            })}
            {on("events") && shown.map && pins.flatMap((a) => {
              const p = a.context?.pose;
              if (!p || p.map_id !== shown.map!.map_id || p.map_version !== shown.map!.version) return [];
              const [x, y] = s.map(p.x, p.y);
              return [(
                <g key={`ev:${a.key}`} class={`event-pin ${a.audience ?? ""}`} onClick={(e) => { e.stopPropagation(); toRec(a); }}>
                  <line x1={x} y1={y} x2={x} y2={y - 10} />
                  <text x={x} y={y - 14}>{`${hm(a.first_ms)} ${alertTitle(lang.value, a.kind, a.title).slice(0, 12)}`}</text>
                </g>
              )];
            })}
            {(route ?? sentRoute?.pts ?? []).map(([mx, my], i) => {
              const [x, y] = s.map(mx, my);
              return <g key={`tr:${i}`} class={route ? "temp-pt" : "temp-pt sent"}><circle cx={x} cy={y} r="9" /><text x={x} y={y + 4}>{i + 1}</text></g>;
            })}
          </>
        )} />
      <aside class="sidebar maprp" aria-label={t("tabMap")}>
        <h3>{t("mapShow")}</h3>
        <div class="layers">
          {LAYERS.map((l) => (
            <label key={l}><input type="checkbox" checked={on(l)} onChange={() => flip(l)} />{t(names[l])}</label>
          ))}
        </div>
        {props.role === "engineer" && (
          <details class="eng-layers">
            <summary>{t("layerEngineering")}</summary>
            <div class="layers">
              {ENGINEERING_LAYERS.map((l) => (
                <label key={l}><input type="checkbox" checked={on(l)} onChange={() => flip(l)} />{t(names[l])}</label>
              ))}
            </div>
          </details>
        )}
        {props.mode && props.mode.mode !== "armed" && canArm(props.role ?? "") && (
          <button type="button" class="btn primary arm-all" onClick={props.onArm}>{t("armAll")}</button>
        )}
        {/* W72(用户 11-03):侧栏只列还要人处理的,最多几条;已解决、自动恢复的去报警记录看 */}
        {/* 第 3 轮 layout N3:连不上站点时不说「没有要处理的」,说状态未知、计数写 ? */}
        <h3>{t("mapTodoN", { n: props.stale && todo.length === 0 ? "?" : todo.length })}</h3>
        {older > 0 && <p class="small"><a href="#/alarms">{t("mapTodoOlder", { n: older })}</a></p>}
        {todo.length === 0 ? (props.stale ? <p class="warn small" data-stale="1">{t("dutyStaleAlarms")}</p> : <p class="muted small">{t(older > 0 ? "mapTodoNoneShift" : "mapTodoNone")}</p>) : (
          <ul class="evlist">
            {todo.map((a) => (
              <li key={a.key}>
                <button type="button" class="evrow" onClick={() => toRec(a)}>
                  <time class="mono">{hm(a.first_ms)}</time>
                  <span class={`ev-what ${a.audience ?? ""}`}>{alertTitle(lang.value, a.kind, a.title)}</span>
                  <small class="muted">{t("evOpen")}{a.robot && a.robot !== "site" && !a.robot.includes(":") ? ` · ${t("evToRec")}` : ""}</small>
                </button>
              </li>
            ))}
          </ul>
        )}
        {events.length > 0 && <a class="small" href="#/alarms">{t("mapAllShift", { n: events.length })}</a>}
        {route ? (
          shown.map && <TempRoutePanel canFix={pageAllowed("admin/localization", props.role ?? "")} map={shown.map} points={route} robots={robotsHere} say={say}
            onUndo={() => setRoute(route.slice(0, -1))} onCancel={() => setRoute(null)}
            onSent={(robot, check) => {
              setSentRoute({ robot, pts: route, at: Date.now() });
              if (!on("route")) flip("route");            // 看得到它走到哪了
              setRoute(null);
              void check?.then((r) => {
                if (r.state === "refused") setSentRoute((s) => (s && s.robot === robot ? { ...s, refused: joinWhyAct(r.why, r.act) } : s));
              });
            }} />
        ) : sentRoute ? (
          <div class={sentRoute.refused ? "tip warn" : "tip"} data-sent-tip={sentRoute.refused ? "refused" : "1"}>
            <p>{sentRoute.refused ? t("trSentRefused", { id: nameOf(sentRoute.robot), why: sentRoute.refused }) : t("trSentShown", { id: nameOf(sentRoute.robot) })}</p>
            {/* 第 4 轮 r3-duty-N3:派出以后跳过了点,侧栏说一声(原来一直写「在临时路线上」) */}
            {!sentRoute.refused && (() => {
              const sk = recent.filter((a) => a.robot === sentRoute.robot && a.resolved_by === "site:skipped" && a.first_ms >= (sentRoute.at ?? 0) - 5_000);
              return sk.length > 0 ? <p class="warn-text small" data-sent-skipped="1">{t("trSentSkipped", { id: nameOf(sentRoute.robot), why: siteStr(sk[0].detail || sk[0].title) })}</p> : null;
            })()}
            <button type="button" class="btn sm" onClick={() => setSentRoute(null)}>{t("trSentHide")}</button>
          </div>
        ) : canPatrol(props.role ?? "") && (
          <div class="tip">
            <p>{t("mapTip")}</p>
            <button type="button" class="btn sm" onClick={() => { setLook(null); setRoute([]); }}>{t("trStart")}</button>
          </div>
        )}
      </aside>
      {look && <GoLookCard canFix={pageAllowed("admin/localization", props.role ?? "")} map={look.map} at={look.at} units={props.units} say={say} onClose={() => setLook(null)} />}
      {liveCam && (
        <Modal label={liveCam} onClose={() => setLiveCam(null)} wide>
          <img class="cam-live" alt={liveCam} src={`/api/cameras/${enc(liveCam)}/live`} />
        </Modal>
      )}
    </div>
  );
}

/** 结论说成人话(报警记录页也用)。 */
export function verdictText(a: Alert): string {
  // 第 4 轮 duty N5:跳过一次的点没到过,不是「自己恢复了」
  if (a.resolved_by === "site:skipped") return t("vSkipped");
  if (autoResolved(a)) return t("vAuto");
  return a.verdict === "intruder" ? t("vIntruder") : a.verdict === "false_alarm" ? t("vFalse") : a.verdict === "handled" ? t("vHandled") : t("vDone");
}

/** 点图以后的小卡片:问站点最近的机器人是谁、大约几分钟,确认了才派(设计 §4.3)。 */
/** 放在图上的固定摄像头(站点 /api/cameras 带 placement)。 */
export interface PlacedCam { name: string; zone?: string; live?: boolean; placement?: { map_id: string; map_version: string; x: number; y: number; yaw: number; fov_deg: number } | null }

export function camsOnMap(cams: PlacedCam[], map: { map_id: string; version: string }): PlacedCam[] {
  return cams.filter((c) => c.placement && c.placement.map_id === map.map_id && c.placement.map_version === map.version);
}

/** 摄像头图层(世界层):看着的那一块扇形。 */
export function camWorld(meta: PreviewMeta, cams: PlacedCam[]) {
  return cams.map((c) => <path key={`fan:${c.name}`} class="cam-fan" d={fanPath(meta, c.placement!)} />);
}

/** 摄像头图层(标记层):一个点 + 名字,点了看实时画面。 */
export function camMarks(s: Screen, cams: PlacedCam[], open: (name: string) => void) {
  return cams.map((c) => {
    const [x, y] = s.map(c.placement!.x, c.placement!.y);
    return (
      <g key={`cam:${c.name}`} class="cam-mark" data-cam={c.name} role="button" onClick={(e) => { e.stopPropagation(); if (c.live !== false) open(c.name); }}>
        <circle cx={x} cy={y} r={6} /><text x={x + 9} y={y + 4}>{c.name}</text>
      </g>
    );
  });
}

export function GoLookCard(props: { map: { map_id: string; version: string }; at: Pt; units: UnitInfo[]; onClose: () => void; say: (s: string) => void; canFix?: boolean; exclude?: string }) {
  const [got, setGot] = useState<{ robot_id: string; eta_s: number } | null | "none" | "error">(null);
  const [why, setWhy] = useState("");
  const [busy, setBusy] = useState(false);
  const [x, y] = props.at;
  useEffect(() => {
    let live = true;
    api<{ robot_id: string; eta_s: number }>("GET",
      `/api/robots/nearest?map_id=${enc(props.map.map_id)}&map_version=${enc(props.map.version)}&x=${x}&y=${y}${props.exclude ? `&exclude=${enc(props.exclude)}` : ""}`)
      .then((d) => live && setGot(d))
      .catch((e) => {
        if (!live) return;
        // 第 4 轮 duty N3:能派的都没标原点(出不了发)—— 说是哪几台、怎么办
        const d = e instanceof ApiError ? e.data as { reason?: string; robots?: string[] } | undefined : undefined;
        if (e instanceof ApiError && e.status === 404 && d?.reason === "no_home") { setGot("error"); setWhy(t(props.canFix ? "lookNoHome" : "lookNoHomeGuard", { ids: andList((d.robots ?? []).map(nameOf)) })); }
        // minor #20(W7-02):有能派的、但都走不到这个点(墙里、障碍上、不连通)
        else if (e instanceof ApiError && e.status === 404 && d?.reason === "unreachable") { setGot("error"); setWhy(t("lookUnreachable")); }
        else if (e instanceof ApiError && e.status === 404) setGot("none");
        else { setGot("error"); setWhy(e instanceof ApiError ? e.message : String(e)); }
      });
    return () => { live = false; };
  }, [x, y, props.map.map_id, props.map.version, props.exclude]);
  async function send(id: string) {
    setBusy(true);
    const p = props.units.find((u) => u.robot.robot_id === id)?.robot.loc?.pose;
    const yaw = (p ? yawToward(p.x, p.y, x, y) : null) ?? 0;
    try {
      const sentAt = Date.now();
      const r = await api<CommandReply>("POST", `/api/robots/${enc(id)}/goto`,
        { target: { map_id: props.map.map_id, map_version: props.map.version, frame_id: "map", x, y, yaw } });
      const no = notAccepted(r);
      // 网页易用性第 1 轮 P0-03:收下 ≠ 出发了(出发前检查在后头),确认完再说
      if (no) props.say(no);
      else void reportStart(nameOf(id), sentAt, props.say, { robot: id, canFix: props.canFix });
      props.onClose();
    } catch (e) {
      setWhy(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <div class="golook" role="dialog" aria-label={t("lookTitle")}>
      {got === null && <p class="muted">{t("lookAsking")}</p>}
      {got === "none" && <p>{props.exclude ? t("lookOnlySelf", { id: nameOf(props.exclude) }) : t("lookNone")}</p>}
      {got === "error" && <p class="error">{why}</p>}
      {got && typeof got === "object" && (
        <p>{t("lookWho", { id: nameOf(got.robot_id), n: Math.max(1, Math.round(got.eta_s / 60)) })}</p>
      )}
      {why && got !== "error" && <p class="error">{why}</p>}
      <div class="row end">
        <button type="button" class="btn" onClick={props.onClose}>{t("cancel")}</button>
        {got && typeof got === "object" && (
          <button type="button" class="btn primary" disabled={busy} onClick={() => send(got.robot_id)}>{t("lookSend")}</button>
        )}
      </div>
    </div>
  );
}

/** P1-16:落点后多久去站点查一次。 */
export const TEMP_CHECK_MS = 400;

/** 保安的临时路线(设计 §4.3,用户选的):按顺序点几个点、选一台、开始;走一趟就没了,不存。 */
export function TempRoutePanel(props: {
  canFix?: boolean;
  map: { map_id: string; version: string };
  points: Pt[];
  robots: string[];
  onUndo: () => void;
  onCancel: () => void;
  /** ``check``:出发检查的结果(排进日程的没有)。 */
  onSent: (robot: string, check?: Promise<StartCheck>) => void;
  say: (s: string) => void;
}) {
  const [robot, setRobot] = useState<string | null>(props.robots[0] ?? null);
  const [errs, setErrs] = useState<string[]>([]);
  // 第 2 轮 P1-16:落点检查查出问题的点(改点以前「开始」灰掉;按了站点也只会回 400、看着没反应)
  const [bad, setBad] = useState(0);
  const [busy, setBusy] = useState(false);
  const pointText = (list: { index: number | null; problem: string }[]) =>
    list.map((x) => (x.index == null ? siteStr(x.problem) : t("trBadPoint", { n: x.index + 1, why: siteStr(x.problem) })));
  // P1-16:点一下就查(穿墙、在禁行区里、没扫到的地方),不用等按「开始」
  const key = JSON.stringify(props.points);
  useEffect(() => {
    if (props.points.length === 0) { setErrs([]); setBad(0); return; }
    let live = true;
    const id = window.setTimeout(() => {
      api<{ errors: { index: number | null; problem: string }[] }>("POST", "/api/route-check",
        { points: props.points.map(([x, y]) => ({ x, y })), map_id: props.map.map_id, map_version: props.map.version, ...(robot ? { robot } : {}) })
        .then((d) => { if (live) { setErrs(pointText(d.errors ?? [])); setBad((d.errors ?? []).length); } })
        .catch(() => { /* 老站点没有这个接口:按「开始」时照样查 */ });
    }, TEMP_CHECK_MS);
    return () => { live = false; window.clearTimeout(id); };
  }, [key, props.map.map_id, props.map.version, robot]);
  async function go() {
    if (!robot) return;
    setBusy(true);
    setErrs([]);
    try {
      const sentAt = Date.now();
      const r = await api<CommandReply & { queued?: boolean; start_after_ms?: number; because?: string; utc_offset_min?: number }>(
        "POST", `/api/robots/${enc(robot)}/patrol`,
        { points: props.points.map(([x, y]) => ({ x, y })), map_id: props.map.map_id, map_version: props.map.version });
      // W53:撞上日程就排到后面(日程优先),说排到几点
      if (r.queued) {
        props.say(t("trQueued", { id: robot, at: siteHm(r.start_after_ms ?? 0, r.utc_offset_min), why: r.because ?? "" }));
        props.onSent(robot);
        return;
      }
      const no = notAccepted(r);
      if (no) setErrs([no]);
      else props.onSent(robot, reportStart(nameOf(robot), sentAt, props.say, { robot, canFix: props.canFix }));
    } catch (e) {
      const list = e instanceof ApiError ? (e.data as { errors?: { index: number | null; problem: string }[] } | undefined)?.errors : undefined;
      setErrs(list && list.length ? pointText(list) : [e instanceof ApiError ? refusalText(e.message, e.data) : String(e)]);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div class="temproute">
      <h3>{t("trTitle")}</h3>
      <p class="muted small">{t("trHint", { n: props.points.length })}</p>
      <div class="seg" role="group" aria-label={t("robots")}>
        {props.robots.map((id) => (
          <button key={id} type="button" aria-pressed={robot === id} onClick={() => setRobot(id)}>{id}</button>
        ))}
      </div>
      {errs.map((e) => <p key={e} class="error" role="alert">{e}</p>)}
      {bad > 0 && <p class="muted small" data-fix-points="1">{t("trFixPoints")}</p>}
      <div class="row">
        <button type="button" class="btn sm" disabled={props.points.length === 0} onClick={props.onUndo}>{t("trUndo")}</button>
        <button type="button" class="btn sm" onClick={props.onCancel}>{t("cancel")}</button>
        <button type="button" class="btn sm primary push" disabled={busy || !robot || props.points.length === 0 || bad > 0} onClick={go}>{t("trGo")}</button>
      </div>
    </div>
  );
}

/** 第 3 轮 duty N1:原因和办法之间补句号(原来拼成「…no origin yet Localize the robot…」)。 */
export function joinWhyAct(why: string, act: string): string {
  if (!act) return why;
  const zh = lang.value === "zh";
  return /[.。!！?？]$/.test(why) ? `${why}${zh ? "" : " "}${act}` : `${why}${zh ? "。" : ". "}${act}`;
}
