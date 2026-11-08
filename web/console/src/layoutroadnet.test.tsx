// @vitest-environment happy-dom
// W48 布置 → 路网:读出来、点地图放点、先后点两个点连线(再点断开)、删点连线一起删、没连上的点标出来、存带修订号。
import { cleanup, fireEvent, render, waitFor } from "@testing-library/preact";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { setFetch } from "./api";
import { lang } from "./i18n";
import type { LayerData, OwnLayer, TabProps } from "./layoutpage";
import { RoadnetTab } from "./layoutroadnet";

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
const META = { width: 100, height: 100, m_per_px: 0.1, left_x: 0, top_y: 10, zones: [] };
const URL = "/api/maps/home/3/route_net";

let posted: { url: string; body: Record<string, unknown> }[];
let save: (() => Promise<void>) | null;
let net: Record<string, unknown>;
let status: number;
beforeEach(() => {
  window.confirm = () => true;   // P2-17:存之前会问(孤立点、穿墙);默认点「确定」
  lang.value = "zh";
  posted = [];
  save = null;
  status = 200;
  net = { map_id: "home", map_version: "3", revision: 2, nodes: [{ id: "P1", x: 1, y: 1 }, { id: "P2", x: 5, y: 1 }], edges: [["P1", "P2"]], length_m: 4 };
  setFetch(((url: string, init?: RequestInit) => {
    if (init?.method === "POST") {
      const body = JSON.parse(String(init.body ?? "{}"));
      posted.push({ url, body });
      if (status !== 200) return Promise.resolve(json({ error: "改过了" }, status));
      return Promise.resolve(json({ ...net, ...body, revision: (net.revision as number) + 1, pushed: {} }));
    }
    if (url === URL) return Promise.resolve(json(net));
    return Promise.resolve(json({}));
  }) as typeof fetch);
});
afterEach(cleanup);

const data: LayerData = { areas: [], nav: null, routes: [], guardRoutes: [], posts: [], cameras: [], robots: ["A"], standby: [] };
// 假地图:两个「点地图」按钮(不同位置),再把标签画的点、线渲染出来好点
const FakeMap = (o: OwnLayer) => (
  <div class="fakemap">
    <button type="button" class="pick1" onClick={() => o.onPick?.(40, 30)}>pick1</button>
    <button type="button" class="pick2" onClick={() => o.onPick?.(80, 30)}>pick2</button>
    <svg>{o.marks?.({ map: (x: number, y: number) => [x * 10, 100 - y * 10] } as never)}</svg>
  </div>
);
const props = (): TabProps => ({
  map: { map_id: "home", version: "3", note: "" }, base: "/api/maps/home/3", meta: META, data, say: () => {},
  reload: () => Promise.resolve(), setDirty: () => {}, registerSave: (fn) => { save = fn; }, Map: FakeMap,
});
const btn = (root: Element, text: string) => Array.from(root.querySelectorAll("button")).find((b) => b.textContent?.trim() === text) as HTMLButtonElement;
const node = (c: Element, id: string) => c.querySelector(`[data-rn-node="${id}"]`) as SVGElement;

/** 存;要是弹了站内确认框(孤立点),点「仍然保存」。 */
async function saveYes(): Promise<void> {
  const p = save!();
  for (let i = 0; i < 20; i++) {
    await new Promise((ok) => setTimeout(ok, 5));
    const m = document.querySelector(".modal");
    if (m) { fireEvent.click(btn(m, "仍然保存")); break; }
  }
  return p;
}

describe("布置 → 路网", () => {
  it("读出来,写点数、线数、总长", async () => {
    const { container: c } = render(<RoadnetTab {...props()} />);
    await waitFor(() => expect(c.querySelector(".ly-side")!.textContent).toContain("2 个点 · 1 条线"));
    expect(node(c, "P1")).not.toBeNull();
  });

  it("加点、连线、存:带修订号", async () => {
    const { container: c } = render(<RoadnetTab {...props()} />);
    await waitFor(() => expect(node(c, "P2")).not.toBeNull());
    fireEvent.click(btn(c, "添加节点"));
    fireEvent.click(c.querySelector(".pick1")!);
    fireEvent.click(c.querySelector(".pick2")!);
    fireEvent.click(btn(c, "完成添加"));
    expect(c.querySelector(".ly-side")!.textContent).toContain("未连接的节点：P3、P4");
    fireEvent.click(node(c, "P2"));
    fireEvent.click(node(c, "P3"));                       // 先后点两个点:连上(P3 接着选中)
    fireEvent.click(node(c, "P4"));
    await saveYes();
    const body = posted.find((p) => p.url === URL)!.body;
    expect(body.base_revision).toBe(2);
    expect(body.nodes).toEqual([{ id: "P1", x: 1, y: 1 }, { id: "P2", x: 5, y: 1 }, { id: "P3", x: 4, y: 7 }, { id: "P4", x: 8, y: 7 }]);
    expect(body.edges).toEqual([["P1", "P2"], ["P2", "P3"], ["P3", "P4"]]);
  });

  it("再点一次断开;删点连线一起删", async () => {
    const { container: c } = render(<RoadnetTab {...props()} />);
    await waitFor(() => expect(node(c, "P2")).not.toBeNull());
    fireEvent.click(node(c, "P1"));
    fireEvent.click(node(c, "P2"));                       // 已经连着:断开
    expect(c.querySelector(".ly-side")!.textContent).toContain("0 条线");
    fireEvent.click(node(c, "P1"));
    fireEvent.click(node(c, "P2"));                       // 再连上
    fireEvent.click(node(c, "P1"));
    fireEvent.click(btn(c.querySelector(".ly-detail")!, "删除此节点"));
    await saveYes();
    const body = posted.find((p) => p.url === URL)!.body;
    expect(body.nodes).toEqual([{ id: "P2", x: 5, y: 1 }]);
    expect(body.edges).toEqual([]);
  });

  it("第 2 轮 setup N6:再点自己、点空白、按 Esc、点「取消选中」都能取消,之后点别的点不会连上", async () => {
    const { container: c } = render(<RoadnetTab {...props()} />);
    await waitFor(() => expect(node(c, "P2")).not.toBeNull());
    const on = () => c.querySelector(".rn-node.on")?.getAttribute("data-rn-node") ?? null;
    fireEvent.click(node(c, "P1")); expect(on()).toBe("P1");
    fireEvent.click(node(c, "P1")); expect(on()).toBeNull();
    fireEvent.click(node(c, "P1")); fireEvent.click(c.querySelector(".pick1")!); expect(on()).toBeNull();
    fireEvent.click(node(c, "P1")); fireEvent.keyDown(window, { key: "Escape" }); expect(on()).toBeNull();
    fireEvent.click(node(c, "P1")); fireEvent.click(c.querySelector("[data-rn-deselect]")!); expect(on()).toBeNull();
    fireEvent.click(node(c, "P2"));
    expect(c.querySelector(".ly-side")!.textContent).toContain("1 条线");   // 没有误连 / 误断
  });

  it("第 2 轮 setup N1:有穿墙线时存:不弹确认,直接说不能存", async () => {
    const said: string[] = [];
    let asked = 0;
    window.confirm = () => { asked++; return true; };
    const d = { ...data, nav: { ...(data.nav ?? {}), zones: [{ name: "墙", wall: [[3, -5], [3, 5]] }] } } as never;
    render(<RoadnetTab {...props()} data={d} say={(m: string) => said.push(m)} />);
    await waitFor(() => expect(document.querySelector("[data-rn-cross]")).not.toBeNull());
    await waitFor(() => expect(save).not.toBeNull());
    const { SaveCancelled } = await import("./layoutpage");
    await expect(save!()).rejects.toBeInstanceOf(SaveCancelled);
    expect(asked).toBe(0);
    expect(said[0]).toContain("不能保存");
    expect(posted.filter((p) => p.url === URL)).toEqual([]);
  });

  it("别人改过:存的时候抛出来(外框说刚才有人改过)", async () => {
    const { container: c } = render(<RoadnetTab {...props()} />);
    await waitFor(() => expect(node(c, "P2")).not.toBeNull());
    fireEvent.click(btn(c, "添加节点"));
    fireEvent.click(c.querySelector(".pick1")!);
    status = 409;
    await expect(saveYes()).rejects.toMatchObject({ status: 409 });
  });

  it("没有路网:说清楚", async () => {
    net = { map_id: "home", map_version: "3", revision: 0, nodes: [], edges: [], length_m: 0 };
    const { container: c } = render(<RoadnetTab {...props()} />);
    await waitFor(() => expect(c.querySelector(".ly-side")!.textContent).toContain("此地图尚无路网"));
  });
});

describe("网页易用性第 1 轮 P2-17", () => {
  it("穿过虚拟墙的连线标出来;有孤立点、穿墙时存之前要确认", async () => {
    const { saveWarning, wallCrossings } = await import("./layoutroadnet");
    const nodes = [{ id: "P1", x: 0, y: 0 }, { id: "P2", x: 4, y: 0 }, { id: "P3", x: 0, y: 3 }];
    const wall: [number, number][][] = [[[2, -1], [2, 1]]];
    expect(wallCrossings(nodes, [["P1", "P2"], ["P1", "P3"]], wall)).toEqual(["P1-P2"]);
    expect(wallCrossings(nodes, [["P1", "P3"]], wall)).toEqual([]);
    expect(saveWarning([])).toBeNull();
    expect(saveWarning(["P3"])).toContain("还是要保存吗");
  });

  it("第 2 轮 setup N1:穿墙线不问「还是要保存吗」,直接说不能存、怎么办", async () => {
    const { saveBlock } = await import("./layoutroadnet");
    expect(saveBlock([])).toBeNull();
    const m = saveBlock(["P1-P2"])!;
    expect(m).toContain("不能保存");
    expect(m).toContain("P1-P2");
    expect(m).not.toContain("还是要保存吗");
  });
});

describe("网页易用性第 1 轮 P2-17 存之前确认", () => {
  it("有孤立点:点「取消」就不存", async () => {
    // 第 4 轮:站内的确认框(不是浏览器自带的 confirm)
    let native = 0;
    window.confirm = () => { native++; return true; };
    const { container: c } = render(<RoadnetTab {...props()} />);
    await waitFor(() => expect(node(c, "P2")).not.toBeNull());
    fireEvent.click(btn(c, "添加节点"));
    fireEvent.click(c.querySelector(".pick1")!);
    fireEvent.click(btn(c, "完成添加"));
    const { SaveCancelled } = await import("./layoutpage");
    const done = save!();
    const modal = await waitFor(() => { const m = document.querySelector(".modal"); expect(m).not.toBeNull(); return m!; });
    expect(modal.textContent).toContain("未连接的节点：P3");
    fireEvent.click(btn(modal, "取消"));
    await expect(done).rejects.toBeInstanceOf(SaveCancelled);
    expect(native).toBe(0);
    expect(posted.filter((p) => p.url === URL)).toEqual([]);
  });
});
