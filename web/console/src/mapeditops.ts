// 地图编辑器的操作栈(W44 第四期,设计 §6):橡皮擦、画障碍(栅格那一半,存成新的一版),区域名、特殊地面、摆正、底图
// (显示那一半,跟着版本存),禁行区、虚拟墙、限速区等(11-10 搬进编辑器,跟着版本存)。撤销、重做一起管;
// 另存之前估一下擦了多少、画了多少。不碰 DOM,好测。
import type { NavZone, Pt } from "./mapview";

export type GridOp = { op: "erase" | "obstacle"; shape: "stroke" | "line" | "rect"; points: Pt[]; width_m: number };
export type TerrainKind = "stairs" | "step" | "slope" | "grass" | "gravel";
export interface Terrain { id: string; kind: TerrainKind; polygon: Pt[]; slow_mps: number | null }
export interface Basemap { file: string; x: number; y: number; scale: number; rotate_deg: number; opacity: number }
export interface Display { rotate_deg: number | null; basemap: Basemap | null; regions: { name: string; polygon: Pt[] }[]; terrain: Terrain[] }
/** 禁行区等(布置那一套的格式;新画的临时区带 ``for_s``)。 */
export type ZoneDraft = NavZone & { for_s?: number };
export interface EditState { ops: GridOp[]; display: Display; zones: ZoneDraft[] }

/** 楼梯、台阶、斜坡默认放慢 0.3 m/s,草地、碎石路默认不放慢(设计 §11 第 16 条)。 */
export const SLOW_DEFAULT: Record<TerrainKind, number | null> = { stairs: 0.3, step: 0.3, slope: 0.3, grass: null, gravel: null };

export interface History { past: EditState[]; now: EditState; future: EditState[] }

export function start(display: Display, zones: ZoneDraft[] = []): History {
  return { past: [], now: { ops: [], display, zones }, future: [] };
}

export function apply(h: History, f: (s: EditState) => EditState): History {
  return { past: [...h.past, h.now].slice(-200), now: f(h.now), future: [] };
}

export function undo(h: History): History {
  if (!h.past.length) return h;
  return { past: h.past.slice(0, -1), now: h.past[h.past.length - 1], future: [h.now, ...h.future] };
}

export function redo(h: History): History {
  if (!h.future.length) return h;
  return { past: [...h.past, h.now], now: h.future[0], future: h.future.slice(1) };
}

/** 画笔终点离起点不超过这么远(米;跟 3 倍粗细取大的)就算圈(W61;站点 map_edit.CLOSE_M 同一个数)。 */
export const CLOSE_M = 0.5;

/** 画笔首尾接上了(至少 3 个点,终点回到起点附近):圈里面整块一起擦 / 一起画(W61,用户 2026-11-01)。 */
export function closedLoop(o: GridOp): boolean {
  if (o.shape !== "stroke" || o.points.length < 3) return false;
  const [ax, ay] = o.points[0];
  const [bx, by] = o.points[o.points.length - 1];
  return Math.hypot(bx - ax, by - ay) <= Math.max(CLOSE_M, 3 * o.width_m);
}

/** 一个操作大概盖了多少平方米(给人确认用,不是精确值;站点回的才准)。 */
export function areaOf(o: GridOp): number {
  if (closedLoop(o)) {
    let a = 0;
    const p = o.points;
    for (let i = 0; i < p.length; i++) {
      const [x1, y1] = p[i];
      const [x2, y2] = p[(i + 1) % p.length];
      a += x1 * y2 - x2 * y1;
    }
    return Math.abs(a) / 2;
  }
  if (o.shape === "rect") {
    const [[x0, y0], [x1, y1]] = o.points;
    return Math.abs(x1 - x0) * Math.abs(y1 - y0);
  }
  let len = 0;
  for (let i = 1; i < o.points.length; i++) len += Math.hypot(o.points[i][0] - o.points[i - 1][0], o.points[i][1] - o.points[i - 1][1]);
  return len * o.width_m + Math.PI * (o.width_m / 2) ** 2;
}

export function summary(s: EditState): { erased: number; obstacle: number } {
  const sum = (k: GridOp["op"]) => Math.round(s.ops.filter((o) => o.op === k).reduce((a, o) => a + areaOf(o), 0) * 10) / 10;
  return { erased: sum("erase"), obstacle: sum("obstacle") };
}

/** 新的特殊地面:id 不重,按种类给默认的放慢。 */
export function newTerrain(have: Terrain[], kind: TerrainKind, polygon: Pt[]): Terrain {
  let n = have.length + 1;
  while (have.some((t) => t.id === `t${n}`)) n++;
  return { id: `t${n}`, kind, polygon, slow_mps: SLOW_DEFAULT[kind] };
}

/** 网页易用性 P2-19:画面转了 ``deg`` 度(摆正)时,两个对角点在**屏幕上**围出的方框,换回地图坐标
 *  (首尾相接 5 个点)。画布把图转 +deg(像素坐标 y 朝下);地图坐标 y 朝上,所以屏幕方向 = 地图转 −deg。 */
export function screenRect(a: Pt, b: Pt, deg: number): Pt[] {
  const r = (deg * Math.PI) / 180;
  const c = Math.cos(r), s = Math.sin(r);
  const to = ([x, y]: Pt): Pt => [c * x + s * y, -s * x + c * y];
  const from = ([x, y]: Pt): Pt => [c * x - s * y, s * x + c * y];
  const qa = to(a), qb = to(b);
  const round = (v: number) => Math.round(v * 1000) / 1000;
  const pts = [qa, [qb[0], qa[1]] as Pt, qb, [qa[0], qb[1]] as Pt].map((q) => from(q).map(round) as Pt);
  return [...pts, pts[0]];
}
