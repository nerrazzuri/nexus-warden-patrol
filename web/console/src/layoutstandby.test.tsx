// @vitest-environment happy-dom
// W44 第三期 布置 → 待命点:选中一个点图挪过去、存下;加一个待命点(选哪台、起名);设默认。
import { cleanup, fireEvent, render, waitFor } from "@testing-library/preact";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { setFetch } from "./api";
import { lang } from "./i18n";
import type { LayerData, OwnLayer, TabProps } from "./layoutpage";
import { sameSpots, spName, StandbyTab } from "./layoutstandby";

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
const META = { width: 100, height: 100, m_per_px: 0.1, left_x: 0, top_y: 10, zones: [] };

let posted: { url: string; body: Record<string, unknown> }[];
let save: (() => Promise<void>) | null;
beforeEach(() => {
  lang.value = "zh";
  posted = [];
  save = null;
  setFetch(((url: string, init?: RequestInit) => {
    if (init?.method === "POST") posted.push({ url, body: JSON.parse(String(init.body ?? "{}")) });
    if (url.startsWith("/api/chargers")) return Promise.resolve(json({ chargers: [] }));
    return Promise.resolve(json({ points: [] }));
  }) as typeof fetch);
});
afterEach(cleanup);

const data: LayerData = { areas: [], nav: null, routes: [], guardRoutes: [], posts: [], cameras: [], robots: ["A", "B"],
  standby: [{ robot_id: "A", name: "dock", x: 2, y: 2, yaw: 0, map_id: "home", map_version: "3", default: true }] };
const SCREEN = { map: (x: number, y: number): [number, number] => [x, y], px: (x: number, y: number): [number, number] => [x, y], k: 1 };
const FakeMap = (o: OwnLayer) => <div class="fakemap"><button type="button" class="pick" onClick={() => o.onPick?.(40, 30)}>pick</button><svg>{o.marks?.(SCREEN)}</svg></div>;
const props = (): TabProps => ({
  map: { map_id: "home", version: "3", note: "" }, base: "/api/maps/home/3", meta: META, data, say: () => {},
  reload: () => Promise.resolve(), setDirty: () => {}, registerSave: (fn) => { save = fn; }, Map: FakeMap,
});
const btn = (root: Element, text: string) => Array.from(root.querySelectorAll("button")).find((b) => b.textContent?.trim() === text) as HTMLButtonElement;

describe("第 9 轮 W9-12 待命点的叫法", () => {
  it("标原点时自动加的(home)写「A 的待命点」,自己起名的写「A · 名字」", () => {
    lang.value = "zh";
    expect(spName({ robot_id: "A", name: "home" })).toBe("A 的待命点");
    expect(spName({ robot_id: "A", name: "dock" })).toBe("A · dock");
    // 第 11 轮 W11-04:home 已登记在别的图上时站点起名 home-<图名>,也是自动加的
    expect(spName({ robot_id: "A", name: "home-estate-1" })).toBe("A 的待命点");
    expect(spName({ robot_id: "B", name: "home-estate-1-7" })).toBe("B 的待命点");
    expect(sameSpots([{ robot_id: "A", name: "home-estate-1", x: 1, y: 1 }, { robot_id: "B", name: "home-estate-1", x: 1, y: 1 }])[0].labels)
      .toEqual(["A", "B"]);
  });
});

describe("布置 → 待命点", () => {
  it("选中以后点图挪过去,存下", async () => {
    const { container: c } = render(<StandbyTab {...props()} />);
    fireEvent.click(btn(c, "A · dock"));
    fireEvent.click(c.querySelector(".pick")!);
    await save!();
    expect(posted.find((p) => p.url === "/api/robots/A/standby")?.body).toEqual(
      { name: "dock", map_id: "home", map_version: "3", x: 4, y: 7, yaw: 0, default: true });
  });

  it("添加待命点", async () => {
    const { container: c } = render(<StandbyTab {...props()} />);
    fireEvent.click(btn(c, "添加待命点"));
    fireEvent.click(c.querySelector(".pick")!);
    fireEvent.change(document.querySelector('.modal select[name="robot"]')!, { target: { value: "B" } });
    fireEvent.input(document.querySelector('.modal input[name="name"]')!, { target: { value: "porch" } });
    fireEvent.submit(document.querySelector(".modal form")!);
    expect(c.querySelector(".ly-side")!.textContent).toContain("B · porch");
    await save!();
    await waitFor(() => expect(posted.find((p) => p.url === "/api/robots/B/standby")?.body).toMatchObject({ name: "porch", x: 4, y: 7, default: true }));
    expect(posted.some((p) => p.url === "/api/robots/A/standby")).toBe(false);
  });

  it("第 2 轮 setup N12 / N13:弹窗焦点在名字框;填中文写明为什么不行", async () => {
    const { container: c } = render(<StandbyTab {...props()} />);
    fireEvent.click(btn(c, "添加待命点"));
    fireEvent.click(c.querySelector(".pick")!);
    const inp = document.querySelector('.modal input[name="name"]') as HTMLInputElement;
    expect(document.activeElement).toBe(inp);
    fireEvent.input(inp, { target: { value: "门口" } });
    expect(document.querySelector("[data-sb-name-bad]")!.textContent).toContain("不能有空格、中文");
    expect((document.querySelector('.modal button[type="submit"]') as HTMLButtonElement).disabled).toBe(true);
  });

  it("删要确认", async () => {
    const { container: c } = render(<StandbyTab {...props()} />);
    fireEvent.click(btn(c, "A · dock"));
    fireEvent.click(btn(c.querySelector(".ly-detail")!, "删除"));
    fireEvent.click(btn(document.querySelector(".modal")!, "删除"));
    await save!();
    expect(posted.find((p) => p.url === "/api/robots/A/standby")?.body).toEqual({ name: "dock", remove: true });
  });
});

describe("第 4 轮 maps N1 / setup P0-14", () => {
  it("从上一版带过来的待命点列出来,留下后存到这一版", async () => {
    const nav = { revision: 1, zones: [], proposal: { from_version: "2", zones: [],
      standby: [{ robot_id: "B", name: "home", x: 5, y: 5, yaw: 0, default: true }, { robot_id: "A", name: "dock", x: 1, y: 1, yaw: 0 }] } };
    const p = { ...props(), data: { ...data, nav: nav as unknown as LayerData["nav"] } };
    const { container: c } = render(<StandbyTab {...p} />);
    const box = c.querySelector("[data-carried-standby]")!;
    expect(box.getAttribute("data-carried-standby")).toBe("1");          // A · dock 这一版已经有了,不再列
    expect(box.textContent).toContain("从版本 2 带过来 1 个待命点");
    expect(box.querySelector("[data-carried-move]")!.textContent).toContain("从版本 2 挪到版本");
    expect(c.querySelector('[data-carried-mark="B/home"]')).toBeTruthy();          // 第 5 轮:没留下也画出来
    fireEvent.click(box.querySelector('[data-keep="B/home"]')!);
    expect(c.querySelector("[data-carried-standby]")).toBeNull();
    await save!();
    await waitFor(() => expect(posted.find((x) => x.url === "/api/robots/B/standby")?.body)
      .toMatchObject({ name: "home", map_version: "3", x: 5, y: 5, default: true }));
  });
});

// 网页第 5 轮遗留 minor #27:带过来的待命点只有「留下」,不要的没法丢
describe("minor #27:带过来的待命点能丢", () => {
  it("点「丢弃」告诉站点只丢这一个、列表里去掉;两个以上还有「全部丢弃」", async () => {
    const nav = { revision: 1, zones: [], proposal: { from_version: "2", zones: [],
      standby: [{ robot_id: "B", name: "home", x: 5, y: 5, yaw: 0, default: true }, { robot_id: "B", name: "gate", x: 6, y: 6, yaw: 0 }] } };
    let reloaded = 0;
    const p = { ...props(), data: { ...data, nav: nav as unknown as LayerData["nav"] }, reload: () => { reloaded++; return Promise.resolve(); } };
    const { container: c } = render(<StandbyTab {...p} />);
    const box = c.querySelector("[data-carried-standby]")!;
    expect(box.querySelector("[data-drop-all]")).toBeTruthy();
    fireEvent.click(box.querySelector('[data-drop="B/home"]')!);
    await waitFor(() => expect(posted.find((x) => x.url === "/api/maps/home/3/zones/proposal")?.body)
      .toEqual({ action: "drop_standby", standby: [{ robot_id: "B", name: "home" }] }));
    await waitFor(() => expect(c.querySelector('[data-drop="B/home"]')).toBeNull());
    expect(c.querySelector('[data-carried-mark="B/home"]')).toBeNull();
    expect(c.querySelector('[data-drop="B/gate"]')).toBeTruthy();
    expect(reloaded).toBeGreaterThan(0);
  });
});

describe("第 10 轮 W10-06", () => {
  it("A、B 的待命点在同一处:图上写「A、B」,不是只看到 B", () => {
    lang.value = "zh";
    const both: LayerData = { ...data, standby: [
      { robot_id: "A", name: "home", x: 2, y: 2, yaw: 0, map_id: "home", map_version: "3", default: true },
      { robot_id: "B", name: "home", x: 2.05, y: 2, yaw: 0, map_id: "home", map_version: "3", default: true },
      { robot_id: "B", name: "far", x: 8, y: 8, yaw: 0, map_id: "home", map_version: "3" }] };
    const { container: c } = render(<StandbyTab {...props()} data={both} />);
    const g = c.querySelectorAll("[data-standby-group]");
    expect(g.length).toBe(1);
    expect(g[0].textContent).toBe("A、B");
  });
});
