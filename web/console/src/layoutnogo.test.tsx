// @vitest-environment happy-dom
// W44 第三期 布置 → 禁行区(设计 §5.2、§9):禁行区 / 虚拟墙 / 限速区,临时的选几天;收紧当场生效;删了写「等你确认」,
// 确认那一句是人话,放宽的确认要再输密码;机器人还没收到写「等机器人确认中」。
import { cleanup, fireEvent, render, waitFor } from "@testing-library/preact";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { setFetch } from "./api";
import { lang } from "./i18n";
import type { LayerData, NavZones, OwnLayer, TabProps } from "./layoutpage";
import { NogoTab } from "./layoutnogo";

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
const META = { width: 100, height: 100, m_per_px: 0.1, left_x: 0, top_y: 10, zones: [] };
const POOL = { id: "n1", kind: "nogo", label: "泳池", polygon: [[1, 1], [3, 1], [3, 3]] as [number, number][] };

let posted: { url: string; body: Record<string, unknown> }[];
let save: (() => Promise<void>) | null;
let reloaded: string[];
let robots: unknown[];
beforeEach(() => {
  lang.value = "zh";
  posted = [];
  save = null;
  reloaded = [];
  robots = [];
  setFetch(((url: string, init?: RequestInit) => {
    if (init?.method === "POST") {
      posted.push({ url, body: JSON.parse(String(init.body ?? "{}")) });
      return Promise.resolve(json({ revision: 3, zones: [], auto_confirmed: true }));
    }
    if (url.startsWith("/api/robots")) return Promise.resolve(json({ robots }));
    return Promise.resolve(json({}, 404));
  }) as typeof fetch);
});
afterEach(cleanup);

const nav = (o: Partial<NavZones> = {}): NavZones => ({ revision: 2, zones: [POOL], confirmed: { revision: 2, by: "olga", at_ms: 1, current: true, how: "confirm" }, held: [], ...o });
const FakeMap = (o: OwnLayer) => (
  <div class="fakemap" data-legend={(o.legend ?? []).join(",")}>
    <button type="button" class="pick" onClick={() => o.onPick?.(10, 20)}>pick</button>
    <svg>{o.world}{o.marks?.({ map: (x: number, y: number) => [x, y], px: (x: number, y: number) => [x, y], k: 1 })}</svg>
  </div>
);
const props = (n: NavZones): TabProps => ({
  map: { map_id: "home", version: "3", note: "" }, base: "/api/maps/home/3", meta: META,
  data: { areas: [], nav: n, routes: [], guardRoutes: [], posts: [], standby: [], cameras: [], robots: ["A"] } as LayerData, say: () => {},
  reload: (k) => { reloaded.push(String(k)); return Promise.resolve(); }, setDirty: () => {}, registerSave: (fn) => { save = fn; }, Map: FakeMap,
});
const btn = (root: Element, text: string) => Array.from(root.querySelectorAll("button")).find((b) => b.textContent?.trim() === text) as HTMLButtonElement;
function draw(c: Element, kind: string, n: number) {
  fireEvent.click(btn(c, kind));
  for (let i = 0; i < n; i++) fireEvent.click(c.querySelector(".pick")!);
  fireEvent.click(btn(c, "完成绘制"));
}

describe("布置 → 禁行区", () => {
  it("第 2 轮 P2-15:禁区、虚拟墙在图上写名字;虚拟墙不是红色那一类;图例补上画了的种类", () => {
    const WALL = { id: "w1", kind: "nogo", label: "围栏", polygon: [], wall: [[1, 1], [4, 1]] as [number, number][] };
    const { container: c } = render(<NogoTab {...props(nav({ zones: [POOL, WALL] as never }))} />);
    expect(c.querySelector('[data-nogo-name="n1"]')!.textContent).toBe("泳池");
    expect(c.querySelector('[data-nogo-name="w1"]')!.textContent).toBe("围栏");
    expect(c.querySelector('[data-nogo-wall="w1"]')!.getAttribute("class")).toContain("vwall-line");
    expect(c.querySelector(".fakemap")!.getAttribute("data-legend")!.split(",").sort()).toEqual(["nogo", "vwall"]);
  });

  it("第 3 轮 maps N1:有带过来的禁行区建议、这一版一个都没有:列出来,能留下(带 adopt 确认)或丢掉;不给确认空集", async () => {
    const n = nav({ zones: [], confirmed: null, proposal: { from_version: "7", zones: [POOL] } } as never);
    const { container: c } = render(<NogoTab {...props(n)} />);
    const box = c.querySelector("[data-nogo-prop]")!;
    expect(box.textContent).toContain("泳池");
    expect(box.textContent).toContain("第 7 版");
    expect(btn(c, "确认此版本")).toBeUndefined();
    fireEvent.click(box.querySelector("[data-prop-keep]")!);
    await waitFor(() => expect(posted.find((x) => x.url.endsWith("/zones/confirm"))).toBeTruthy());
    expect(posted.find((x) => x.url.endsWith("/zones/confirm"))!.body).toMatchObject({ confirm: true, adopt: { zones: ["n1"] } });
    fireEvent.click(box.querySelector("[data-prop-drop]")!);
    await waitFor(() => expect(posted.find((x) => x.url.endsWith("/zones/proposal"))?.body).toEqual({ action: "discard" }));
  });

  it("画禁行区_收紧当场生效", async () => {
    const { container: c } = render(<NogoTab {...props(nav())} />);
    draw(c, "画禁行区", 3);
    fireEvent.input(document.querySelector('.modal input[name="label"]')!, { target: { value: "高楼楼梯" } });
    fireEvent.submit(document.querySelector(".modal form")!);
    expect(c.querySelector(".ly-side")!.textContent).toContain("高楼楼梯");
    await save!();
    const b = posted.find((p) => p.url === "/api/maps/home/3/zones")!.body;
    expect(b.base_revision).toBe(2);
    expect((b.zones as { label: string }[]).map((z) => z.label)).toEqual(["泳池", "高楼楼梯"]);
    expect(reloaded).toContain("nav");
  });

  it("删了写等你确认,确认要那一句和密码", async () => {
    const n = nav({ zones: [], held: [POOL], confirmed: { revision: 2, by: "olga", at_ms: 1, current: false, how: "confirm" }, revision: 3 });
    const { container: c } = render(<NogoTab {...props(n)} />);
    expect(c.querySelector(".nogo-status")!.textContent).toContain("待你确认");
    expect(c.querySelector(".nogo-status")!.textContent).toContain("泳池");
    fireEvent.click(btn(c, "确认此版本"));
    const yes = btn(document.querySelector(".modal")!, "确认");
    expect(yes.disabled).toBe(true);
    fireEvent.click(document.querySelector('.modal input[name="sure"]')!);
    // P1-32:密码就在同一个框里;没输密码还不能点
    expect(btn(document.querySelector(".modal")!, "确认").disabled).toBe(true);
    fireEvent.input(document.querySelector('.modal input[type="password"]')!, { target: { value: "my-own-password" } });
    expect(document.querySelectorAll(".modal").length).toBe(1);
    fireEvent.click(btn(document.querySelector(".modal")!, "确认"));
    await waitFor(() => expect(posted.find((p) => p.url === "/api/maps/home/3/zones/confirm")?.body).toEqual(
      { revision: 3, confirm: true, empty_ok: true, confirm_password: "my-own-password" }));
  });

  it("临时的带天数", async () => {
    const { container: c } = render(<NogoTab {...props(nav())} />);
    draw(c, "画禁行区", 3);
    fireEvent.click(document.querySelector('.modal input[name="temp"]')!);
    fireEvent.change(document.querySelector('.modal select[name="days"]')!, { target: { value: "3" } });
    fireEvent.submit(document.querySelector(".modal form")!);
    await save!();
    const zs = posted.find((p) => p.url === "/api/maps/home/3/zones")!.body.zones as { for_s?: number }[];
    expect(zs[1].for_s).toBe(3 * 86400);
  });

  it("虚拟墙两个点就行", async () => {
    const { container: c } = render(<NogoTab {...props(nav())} />);
    draw(c, "画虚拟墙", 2);
    fireEvent.submit(document.querySelector(".modal form")!);
    await save!();
    const zs = posted.find((p) => p.url === "/api/maps/home/3/zones")!.body.zones as { wall?: unknown; kind: string }[];
    expect(zs[1].kind).toBe("nogo");
    expect(zs[1].wall).toEqual([[1, 8], [1, 8]]);
  });

  it("机器人还没收到写等机器人确认中", async () => {
    robots = [{ robot_id: "A", running: { map_id: "home", map_version: "3", zones: { match: false, dog_rev: 1, site_rev: 2 } } }];
    const { container: c } = render(<NogoTab {...props(nav())} />);
    await waitFor(() => expect(c.querySelector(".nogo-status")!.textContent).toContain("等待机器人确认"));
  });

  it("人员忽略区:没有硬禁区那一项,种类 ignore", async () => {
    const { container: c } = render(<NogoTab {...props(nav())} />);
    draw(c, "画人员忽略区", 3);
    expect(document.querySelector('.modal input[name="hard"]')).toBeNull();
    fireEvent.submit(document.querySelector(".modal form")!);
    await save!();
    const zs = posted.find((p) => p.url === "/api/maps/home/3/zones")!.body.zones as { kind: string; hard?: boolean }[];
    expect(zs[1].kind).toBe("ignore");
    expect(zs[1].hard).toBeUndefined();
  });

  it("从没确认过的写清楚,不说删了什么", () => {
    const { container: c } = render(<NogoTab {...props(nav({ confirmed: null, held: [], zones: [] }))} />);
    expect(c.querySelector(".nogo-status")!.textContent).toContain("此版本尚未确认");
    expect(c.querySelector(".nogo-status")!.textContent).not.toContain("删掉");
  });
});

describe("网页易用性第 1 轮 P1-31", () => {
  it("点图上的区域选中它,能改名,存的时候带新名字", async () => {
    const big = { ...POOL, id: "n2", label: "花园", polygon: [[0, 6], [4, 6], [4, 10], [0, 10]] as [number, number][] };
    const { container: c } = render(<NogoTab {...props(nav({ zones: [POOL, big] }))} />);
    fireEvent.click(c.querySelector(".pick")!);                  // (1,8) 在花园里
    expect(c.querySelector('[data-pick-zone="n2"]')!.className).toContain("on");
    fireEvent.click(c.querySelector("[data-rename]")!);
    const inp = document.querySelector('.modal input[name="label"]') as HTMLInputElement;
    expect(inp.value).toBe("花园");
    fireEvent.input(inp, { target: { value: "后花园" } });
    fireEvent.submit(document.querySelector(".modal form")!);
    await save!();
    const body = posted.find((x) => x.url === "/api/maps/home/3/zones")!.body as { zones: { id: string; label: string }[] };
    expect(body.zones.find((z) => z.id === "n2")!.label).toBe("后花园");
  });
});

describe("第 3 轮 setup N8", () => {
  it("改成跟别的禁区同名:说重名,不能点完成", () => {
    const big = { ...POOL, id: "n2", label: "花园", polygon: [[0, 6], [4, 6], [4, 10], [0, 10]] as [number, number][] };
    const { container: c } = render(<NogoTab {...props(nav({ zones: [POOL, big] }))} />);
    fireEvent.click(c.querySelector('[data-pick-zone="n2"]')!);
    fireEvent.click(c.querySelector("[data-rename]")!);
    const inp = document.querySelector('.modal input[name="label"]') as HTMLInputElement;
    fireEvent.input(inp, { target: { value: POOL.label } });
    expect(document.querySelector(".modal [data-dup]")).not.toBeNull();
    expect((document.querySelector('.modal button[type="submit"]') as HTMLButtonElement).disabled).toBe(true);
  });
});

describe("第 3 轮 setup N3", () => {
  it("墙、装不下名字的区域:名字写在上边外面;装得下写中间", async () => {
    const { nameSpot } = await import("./layoutnogo");
    expect(nameSpot([[100, 100], [160, 100]], "测试虚拟墙", true)).toEqual([130, 90]);
    expect(nameSpot([[0, 0], [30, 0], [30, 30], [0, 30]], "测试禁区名字", false)).toEqual([15, -10]);
    expect(nameSpot([[0, 0], [300, 0], [300, 100], [0, 100]], "泳池", false)).toEqual([150, 50]);
  });
});
