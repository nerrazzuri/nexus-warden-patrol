// 第四档 #44(用户 11-21):客户自己导出、导入路线 —— 存成一个文件,换台电脑、重装站点、
// 或者同一张图的新版本上照着再建一遍。只管路线本身(点、朝向、动作、名字);排程跟机器人、
// 时间绑着,不进文件。导进来照样一条条走站点的「存路线」,逐点校验没过的那条存不下、说原因。
import type { Route, RoutePoint } from "./routes";

export const ROUTE_FILE_FORMAT = "nexwar-routes";
export const ROUTE_FILE_V = 1;

export interface RouteFileEntry {
  id: string;
  title?: string;
  waypoints: RoutePoint[];
  policy: Record<string, unknown>;
}
export interface RouteFile {
  format: typeof ROUTE_FILE_FORMAT;
  v: number;
  kind: "patrol" | "guard";
  map_id: string;
  map_version: string;
  exported_ms: number;
  routes: RouteFileEntry[];
}

export function buildRouteFile(routes: readonly Route[], map: { map_id: string; version: string },
  kind: "patrol" | "guard", now = Date.now()): RouteFile {
  return {
    format: ROUTE_FILE_FORMAT, v: ROUTE_FILE_V, kind, map_id: map.map_id, map_version: map.version, exported_ms: now,
    routes: routes.map((r) => ({
      id: r.id, ...(r.title ? { title: r.title } : {}), waypoints: r.waypoints.map((p) => ({ ...p })), policy: r.policy ?? {},
    })),
  };
}

export function routeFileName(f: RouteFile): string {
  const d = new Date(f.exported_ms);
  const ymd = `${d.getFullYear()}${String(d.getMonth() + 1).padStart(2, "0")}${String(d.getDate()).padStart(2, "0")}`;
  const safe = (s: string) => s.replace(/[^\w.-]+/g, "_");
  return `${f.kind === "guard" ? "guard-routes" : "routes"}-${safe(f.map_id)}-v${safe(f.map_version)}-${ymd}.json`;
}

/** 读文件出错给的原因(界面按 key 翻译)。 */
export type ParseError = "notJson" | "notRouteFile" | "newerVersion" | "badRoute" | "empty";

const num = (x: unknown) => typeof x === "number" && Number.isFinite(x);
/** 跟站点 routes.NAME_RE 一样。 */
const ID_RE = /^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/;

export function parseRouteFile(text: string): RouteFile | { error: ParseError } {
  let d: unknown;
  try { d = JSON.parse(text); } catch { return { error: "notJson" }; }
  if (!d || typeof d !== "object" || (d as RouteFile).format !== ROUTE_FILE_FORMAT) return { error: "notRouteFile" };
  const f = d as RouteFile;
  if (typeof f.v !== "number" || f.v > ROUTE_FILE_V) return { error: "newerVersion" };
  if (typeof f.map_id !== "string" || typeof f.map_version !== "string" || !Array.isArray(f.routes)) return { error: "notRouteFile" };
  if (f.routes.length === 0) return { error: "empty" };
  for (const r of f.routes) {
    if (!r || typeof r.id !== "string" || !ID_RE.test(r.id) || !Array.isArray(r.waypoints)) return { error: "badRoute" };
    for (const p of r.waypoints) {
      if (!p || typeof p.name !== "string" || !num(p.x) || !num(p.y) || !num(p.yaw)) return { error: "badRoute" };
    }
    if (r.title != null && typeof r.title !== "string") return { error: "badRoute" };
    if (r.policy != null && (typeof r.policy !== "object" || Array.isArray(r.policy))) return { error: "badRoute" };
  }
  return { ...f, kind: f.kind === "guard" ? "guard" : "patrol" };
}

/** 导进来每一条怎么办:new 新建;replace 这一版上有同名的,盖掉(要勾);rename 编号在别处用过 / 删掉过,换个编号新建。 */
export interface ImportRow {
  from: RouteFileEntry;
  action: "new" | "replace" | "rename";
  /** 存成哪个编号。 */
  id: string;
  /** replace 时这一条现在的修订号(存的时候带上,别人刚改过就 409)。 */
  base: number;
}

/**
 * here:这张图这一版上现有的路线;taken:全站用过的编号(别的图、别的版本上的,删掉过的)。
 */
export function planImport(f: RouteFile, here: readonly Route[], taken: Iterable<string>): ImportRow[] {
  const used = new Set(taken);
  for (const r of here) used.add(r.id);
  const hereById = new Map(here.map((r) => [r.id, r]));
  const rows: ImportRow[] = [];
  for (const e of f.routes) {
    const cur = hereById.get(e.id);
    if (cur) { rows.push({ from: e, action: "replace", id: e.id, base: cur.revision }); continue; }
    if (!used.has(e.id)) { rows.push({ from: e, action: "new", id: e.id, base: 0 }); used.add(e.id); continue; }
    let n = 2;
    const stem = e.id.slice(0, 60);
    while (used.has(`${stem}-${n}`)) n++;
    const id = `${stem}-${n}`;
    used.add(id);
    rows.push({ from: e, action: "rename", id, base: 0 });
  }
  return rows;
}
