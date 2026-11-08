// 布置 → 路网(W48,docs/W48-路线网络-设计.md):在地图上画好机器人要沿着走的路 —— 点和连线(双向)。
// 「加点」以后点地图放点;先后点两个点把它们连起来,再点一次断开;拖点改位置;选中能删(连在上面的线一起删)。
// 侧栏写点数、线数、总长和没连上线的点。外框「保存」整份存(带看到的修订号,别人改过回 409)。
import { useEffect, useRef, useState } from "preact/hooks";
import { api } from "./api";
import { clickGuard, startDrag, swallowClick } from "./dragpt";
import { t, joinList } from "./i18n";
import { SaveCancelled, toMap, type TabProps } from "./layoutpage";
import { clientToMap } from "./routes";

export interface RnNode { id: string; x: number; y: number }
type Edge = [string, string];
interface RouteNet { revision: number; nodes: RnNode[]; edges: Edge[] }

const round = (v: number) => Math.round(v * 100) / 100;
const same = (e: Edge, a: string, b: string) => (e[0] === a && e[1] === b) || (e[0] === b && e[1] === a);
const sorted = (a: string, b: string): Edge => (a < b ? [a, b] : [b, a]);

/** 下一个点的名字:P1、P2 …(接着现有的最大号)。 */
export function nextId(nodes: RnNode[]): string {
  let n = 0;
  for (const x of nodes) {
    const m = /^P(\d+)$/.exec(x.id);
    if (m) n = Math.max(n, Number(m[1]));
  }
  return `P${n + 1}`;
}

/** 没连上任何线的点。 */
export function lonely(nodes: RnNode[], edges: Edge[]): string[] {
  const used = new Set(edges.flat());
  return nodes.filter((x) => !used.has(x.id)).map((x) => x.id);
}

type P2 = [number, number];
/** 两条线段相交(端点碰上也算)。 */
function cross(a: P2, b: P2, c: P2, d: P2): boolean {
  const o = (p: P2, q: P2, r: P2) => Math.sign((q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0]));
  const on = (p: P2, q: P2, r: P2) => Math.min(p[0], q[0]) <= r[0] && r[0] <= Math.max(p[0], q[0]) && Math.min(p[1], q[1]) <= r[1] && r[1] <= Math.max(p[1], q[1]);
  const o1 = o(a, b, c), o2 = o(a, b, d), o3 = o(c, d, a), o4 = o(c, d, b);
  if (o1 !== o2 && o3 !== o4) return true;
  return (o1 === 0 && on(a, b, c)) || (o2 === 0 && on(a, b, d)) || (o3 === 0 && on(c, d, a)) || (o4 === 0 && on(c, d, b));
}

/** P2-17:穿过虚拟墙的连线("a-b" 形式)。 */
export function wallCrossings(nodes: RnNode[], edges: Edge[], walls: P2[][]): string[] {
  const by = new Map(nodes.map((x) => [x.id, x]));
  return edges.filter(([a, b]) => {
    const p = by.get(a), q = by.get(b);
    if (!p || !q) return false;
    return walls.some((w) => w.some((pt, i) => i > 0 && cross([p.x, p.y], [q.x, q.y], w[i - 1], pt)));
  }).map(([a, b]) => `${a}-${b}`);
}

/** 存之前要确认的事(孤立点);没有就 null。
 *  第 2 轮 setup N1:穿墙线站点一定拒,不再问「还是要保存吗」—— 用 ``saveBlock`` 直接说不能存。 */
export function saveWarning(alone: string[]): string | null {
  return alone.length ? `${t("lyRnLonely", { ids: joinList(alone) })}\n\n${t("lyRnSaveAnyway")}` : null;
}

/** 站点一定不收的(连线穿过虚拟墙):说哪几条、怎么办;没有就 null。 */
export function saveBlock(bad: string[]): string | null {
  return bad.length ? t("lyRnCrossBlock", { ids: joinList(bad) }) : null;
}

function lengthM(nodes: RnNode[], edges: Edge[]): number {
  const by = new Map(nodes.map((x) => [x.id, x]));
  return edges.reduce((s, [a, b]) => {
    const p = by.get(a), q = by.get(b);
    return p && q ? s + Math.hypot(p.x - q.x, p.y - q.y) : s;
  }, 0);
}

export function RoadnetTab(p: TabProps) {
  const url = `/api/maps/${encodeURIComponent(p.map.map_id)}/${encodeURIComponent(p.map.version)}/route_net`;
  const [loaded, setLoaded] = useState<RouteNet | null>(null);
  const [nodes, setNodes] = useState<RnNode[]>([]);
  const [edges, setEdges] = useState<Edge[]>([]);
  const [adding, setAdding] = useState(false);
  const [sel, setSel] = useState<string | null>(null);
  const [problem, setProblem] = useState("");
  const root = useRef<HTMLDivElement>(null);
  const guard = useRef(clickGuard());

  // 这张图这一版的路网(标签按图和版本整个重建:换了图不会把旧图的点存到新图上)
  useEffect(() => {
    let live = true;
    api<RouteNet>("GET", url).then((d) => {
      if (!live) return;
      const net = { revision: d.revision ?? 0, nodes: d.nodes ?? [], edges: (d.edges ?? []) as Edge[] };
      setLoaded(net);
      setNodes(net.nodes);
      setEdges(net.edges);
    }).catch((e) => live && setProblem(String(e)));
    return () => { live = false; };
  }, [url]);

  const walls = (p.data.nav?.zones ?? []).filter((z) => Array.isArray(z.wall) && z.wall.length >= 2).map((z) => z.wall as P2[]);
  const changed = loaded !== null && (JSON.stringify(nodes) !== JSON.stringify(loaded.nodes) || JSON.stringify(edges) !== JSON.stringify(loaded.edges));
  useEffect(() => p.setDirty(changed), [changed]);
  useEffect(() => {
    if (loaded === null) return;
    p.registerSave(async () => {
      // 第 2 轮 setup N1:穿墙线站点一定拒 —— 直接说不能存;孤立点能存,再问一次
      const block = saveBlock(wallCrossings(nodes, edges, walls));
      if (block) { p.say(block); throw new SaveCancelled(); }
      const warn = saveWarning(lonely(nodes, edges));
      if (warn && !window.confirm(warn)) throw new SaveCancelled();
      const d = await api<RouteNet>("POST", url, { nodes, edges, base_revision: loaded.revision });
      const net = { revision: d.revision, nodes: d.nodes ?? nodes, edges: (d.edges ?? edges) as Edge[] };
      setLoaded(net);
      setNodes(net.nodes);
      setEdges(net.edges);
    });
    return () => p.registerSave(null);
  }, [nodes, edges, loaded, p.data.nav]);

  // 第 2 轮 setup N6:Esc 取消选中(原来选上就取消不了,接着点别的点必然连上)
  useEffect(() => {
    if (sel === null) return;
    const key = (e: KeyboardEvent) => { if (e.key === "Escape") setSel(null); };
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, [sel]);

  function pick(px: number, py: number) {
    if (!adding) return;
    const [x, y] = toMap(p.meta, px, py);
    const n = { id: nextId(nodes), x: round(x), y: round(y) };
    setNodes([...nodes, n]);
  }

  /** 点一个点:没选中的先选中;已经选中另一个就把两个连上(连着就断开),再选中这一个接着连。 */
  function tapNode(id: string) {
    if (sel === id) { setSel(null); return; }        // 第 2 轮 setup N6:再点一次自己 = 取消选中
    if (sel === null) {
      setSel(id);
      return;
    }
    const has = edges.some((e) => same(e, sel, id));
    setEdges(has ? edges.filter((e) => !same(e, sel, id)) : [...edges, sorted(sel, id)]);
    setSel(id);
  }

  function removeNode(id: string) {
    setNodes(nodes.filter((x) => x.id !== id));
    setEdges(edges.filter((e) => e[0] !== id && e[1] !== id));
    setSel(null);
  }

  const drag = (id: string) => (e: PointerEvent) => {
    startDrag(e, guard.current, (cx, cy) => {
      const m = clientToMap(root.current, p.meta, cx, cy);
      if (!m) return;
      setNodes((all) => all.map((x) => (x.id === id ? { ...x, x: round(m[0]), y: round(m[1]) } : x)));
    });
  };

  const by = new Map(nodes.map((x) => [x.id, x]));
  const alone = lonely(nodes, edges);
  const bad = wallCrossings(nodes, edges, walls);
  const cur = sel !== null ? by.get(sel) ?? null : null;
  return (
    <div class="ly-tab">
      <div ref={root} onClickCapture={(e) => swallowClick(guard.current, e)}>
        <p.Map
          drawing={adding}
          onPick={adding ? pick : sel !== null ? () => setSel(null) : undefined}
          marks={(s) => <>
            {edges.map(([a, b]) => {
              const pa = by.get(a), pb = by.get(b);
              if (!pa || !pb) return null;
              const [x1, y1] = s.map(pa.x, pa.y);
              const [x2, y2] = s.map(pb.x, pb.y);
              return <line key={`${a}-${b}`} class={bad.includes(`${a}-${b}`) ? "rn-edge bad" : "rn-edge"} data-rn-edge={`${a}-${b}`} x1={x1} y1={y1} x2={x2} y2={y2} />;
            })}
            {nodes.map((n) => {
              const [x, y] = s.map(n.x, n.y);
              return (
                <g key={n.id} class={`rn-node${n.id === sel ? " on" : ""}${alone.includes(n.id) ? " alone" : ""}`} data-rn-node={n.id}
                  onPointerDown={drag(n.id) as never} onClick={(e: MouseEvent) => { e.stopPropagation(); tapNode(n.id); }}>
                  <circle cx={x} cy={y} r={7} />
                  <text x={x + 9} y={y - 9}>{n.id}</text>
                </g>
              );
            })}
          </>} />
      </div>
      <div class="ly-side">
        {adding
          ? <button type="button" class="btn primary" onClick={() => setAdding(false)}>{t("lyRnDone")}</button>
          : <button type="button" class="btn primary" disabled={loaded === null} onClick={() => { setAdding(true); setSel(null); }}>{t("lyRnAdd")}</button>}
        <p class="muted small">{adding ? t("lyRnAddHint") : t("lyRnHint")}</p>
        {problem && <p class="small bad">{problem}</p>}
        {loaded !== null && nodes.length === 0 && <p class="muted small">{t("lyRnEmpty")}</p>}
        {nodes.length > 0 && (
          <p class="small">{t("lyRnStats", { nodes: String(nodes.length), edges: String(edges.length), len: lengthM(nodes, edges).toFixed(1) })}</p>
        )}
        {alone.length > 0 && <p class="small warn">{t("lyRnLonely", { ids: joinList(alone) })}</p>}
        {bad.length > 0 && <p class="small bad" data-rn-cross="1">{t("lyRnCrossWall", { ids: joinList(bad) })}</p>}
        {cur && (
          <section class="panel ly-detail">
            <h3>{cur.id}</h3>
            <p class="muted small">{t("lyRnSelHint")}</p>
            <div class="row end">
              <button type="button" class="btn sm" data-rn-deselect="1" onClick={() => setSel(null)}>{t("lyRnDeselect")}</button>
              <button type="button" class="btn sm" onClick={() => removeNode(cur.id)}>{t("lyRnRemovePoint")}</button>
            </div>
          </section>
        )}
      </div>
    </div>
  );
}
