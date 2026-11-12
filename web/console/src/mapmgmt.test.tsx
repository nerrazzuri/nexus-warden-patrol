// @vitest-environment happy-dom
// 地图管理页:真的把组件渲染出来点。后端是假的(按路径回数据)。
import { cleanup, fireEvent, render, waitFor } from "@testing-library/preact";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { setFetch } from "./api";
import { lang } from "./i18n";
import { activationText, MapManagePage, rollLabel, routeCount } from "./mapmgmt";
import type { Activation, Dog, Overview, Version } from "./mapmgmt";

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
function held() {
  let go!: (r: Response) => void;
  const p = new Promise<Response>((res) => (go = res));
  return { p, go };
}

const ver = (v: string, over: Partial<Version> = {}): Version => ({
  version: v, created_ms: Date.UTC(2026, 9, 13, 8, 0), source: "dog-A", note: "", size_bytes: 12_500_000, latest: false,
  build: null, counts: { zones: 0, nogo: 0, slow: 0, zones_rev: 0, zones_confirmed: true, standby: 0, intercepts: 0 },
  loaded_on: [], previous_on: [], thumbnail: `/api/maps/estate/${v}/preview.png`, has_raster: true, ...over,
});
const dog = (id: string, over: Partial<Dog> = {}): Dog => ({
  robot_id: id, online: true, can_activate: true, loaded: { map_id: "estate", version: "2" },
  running: { legacy: false, problems: [], map: { dog: "a", site: "a", match: true }, zones: { dog_rev: 1, site_rev: 1, match: true, basis: "digest" } },
  activation: null, history: [], rollback: null, ...over,
});
const act = (state: Activation["state"], over: Partial<Activation> = {}): Activation => ({
  map_id: "estate", version: "2", state, at_ms: Date.UTC(2026, 9, 13, 9, 0), by: "alice", reason: "", confirmed: null, ...over,
});

const OVERVIEW = (): Overview => ({
  now_ms: 0,
  maps: [{
    map_id: "estate", versions: [
      ver("3", { latest: true, note: "after loop closure", build: {
        source: "bag-1013", builder: "mola-lidar-odometry", frames: 812,
        loop_closure: { used: true, closures: 3, why: null }, handedness: { verdict: "ok", why: null } },
      counts: { zones: 3, nogo: 2, slow: 1, zones_rev: 4, zones_confirmed: true, standby: 2, intercepts: 1 } }),
      ver("2", { loaded_on: ["A"], previous_on: ["B"] }),
      ver("1", { build: null }),
    ],
  }],
  robots: [
    dog("A", { activation: act("confirmed", { confirmed: "localizer" }), rollback: { map_id: "estate", version: "1", local: true } }),
    dog("B", { loaded: { map_id: "estate", version: "1" }, online: true }),
    dog("C", { online: false, can_activate: true, loaded: null, running: null }),
  ],
});

interface Calls { method: string; path: string; body: unknown }
let calls: Calls[];
let overview: Overview;
let routes: Record<string, (body: unknown, url: URL) => Response | Promise<Response>>;
const say = vi.fn();

function mount() {
  calls = [];
  setFetch(((url: string, init?: RequestInit) => {
    const u = new URL(url, "https://site");
    const method = init?.method ?? "GET";
    const body = init?.body ? JSON.parse(init.body as string) : undefined;
    calls.push({ method, path: u.pathname + u.search, body });
    const key = `${method} ${u.pathname}`;
    if (routes[key]) return Promise.resolve(routes[key](body, u));
    if (key === "GET /api/admin/maps") return Promise.resolve(json(overview));
    return Promise.resolve(json({ error: `no route ${key}` }, 404));
  }) as never);
  return render(<MapManagePage say={say} pollMs={0} />);
}

beforeEach(() => {
  lang.value = "en";
  overview = OVERVIEW();
  routes = {};
  say.mockReset();
});
afterEach(() => cleanup());

/** P1-47:删除、退回要再输密码。 */
function typePw(dialog: HTMLElement) {
  fireEvent.input(dialog.querySelector('input[type="password"]') as HTMLElement, { target: { value: "pw" } });
  fireEvent.submit(dialog.querySelector("form") as HTMLFormElement);
}

describe("总览", () => {
  it("每个版本:备注、构建信息、数量、哪几台机器人在用;最新一版标出来", async () => {
    const { container: c, getByLabelText } = mount();
    await waitFor(() => expect(c.textContent).toContain("v3"));
    const v3 = getByLabelText("estate:3");
    expect(v3.textContent).toContain("latest");
    expect(v3.textContent).toContain("bag-1013");
    expect(v3.textContent).toContain("used (3)");
    expect(v3.textContent).toContain("Mirror check: OK");
    expect(v3.textContent).toContain("Zones 3 (2 no-go, 1 slow)");
    expect(v3.textContent).toContain("Standby points 2");
    expect((getByLabelText("Note for v3") as HTMLInputElement).value).toBe("after loop closure");
    expect(getByLabelText("estate:2").textContent).toContain("Loaded on");
    expect(getByLabelText("estate:2").textContent).toContain("Previous version of");
    // P1-50:技术信息收在「技术信息」里;没有建图记录的不再写一行技术话;来源说人话
    expect(v3.querySelector("details.mm-tech .mm-build")).not.toBeNull();
    expect(getByLabelText("estate:1").querySelector("details.mm-tech")).toBeNull();
    expect((getByLabelText("estate:3").querySelector("img") as HTMLImageElement).getAttribute("src")).toBe("/api/maps/estate/3/preview.png");
  });

  it("P1-87:地图文件丢了的版本写「读取失败」", async () => {
    overview.maps[0].versions[1].missing = ["map.pgm"];
    const { getByLabelText } = mount();
    await waitFor(() => expect(getByLabelText("estate:2").querySelector("[data-missing]")).not.toBeNull());
    expect(getByLabelText("estate:3").querySelector("[data-missing]")).toBeNull();
  });

  it("镜像的版本用红字警告", async () => {
    overview.maps[0].versions[0].build!.handedness = { verdict: "mirrored", why: null };
    const { container: c } = mount();
    await waitFor(() => expect(c.textContent).toContain("MIRRORED"));
  });

  it("每台机器人:加载的版本、最近一次下发的状态、实际配置核对;中文", async () => {
    lang.value = "zh";
    const { container: c } = mount();
    await waitFor(() => expect(c.textContent).toContain("已在新图上定好位"));
    expect(c.textContent).toContain("estate:2");
    expect(c.textContent).toContain("不在线");
  });
});

describe("备注", () => {
  it("第 2 轮 P1-49:粘贴太长被截,说一声", async () => {
    const { getByLabelText, container: c } = mount();
    await waitFor(() => getByLabelText("Note for v2"));
    fireEvent.paste(getByLabelText("Note for v2"), { clipboardData: { getData: () => "x".repeat(300) } });
    await waitFor(() => expect(c.querySelector("[data-note-cut]")).not.toBeNull());
    expect(c.querySelector("[data-note-cut]")!.textContent).toContain("200");
  });

  it("改了才能存;存的时候带整段文字,存完重新拉", async () => {
    routes["POST /api/admin/maps/estate/2/note"] = () => json({ ok: true, note: "kept" });
    const { getByLabelText, getAllByText } = mount();
    await waitFor(() => getByLabelText("Note for v2"));
    const save = () => getAllByText("Save note")[1] as HTMLButtonElement;     // 第二张卡片是 v2
    expect(save().disabled).toBe(true);
    fireEvent.input(getByLabelText("Note for v2"), { target: { value: "after the storm" } });
    await waitFor(() => expect((getByLabelText("Note for v2") as HTMLInputElement).value).toBe("after the storm"));
    await waitFor(() => expect(save().disabled).toBe(false));
    fireEvent.click(save());
    await waitFor(() => expect(say).toHaveBeenCalledWith("Saved"));
    expect(calls.find((x) => x.method === "POST")?.body).toEqual({ note: "after the storm" });
    expect(calls.filter((x) => x.path === "/api/admin/maps").length).toBe(2);
  });
});

describe("发布", () => {
  it("P0-14:换图前说出旧版上的路线会停;编辑出来的版本默认一起搬,发完调 adopt-routes", async () => {
    overview.maps[0].versions[0] = { ...overview.maps[0].versions[0], source: "edit" };
    routes["GET /api/routes"] = () => json({ routes: [{ id: "night", map_id: "estate", map_version: "2" }, { id: "x", map_id: "estate", map_version: "3" }] });
    routes["POST /api/admin/maps/estate/3/publish"] = () => json({ results: [{ robot_id: "A", ok: true, state: "pending", reason: "" }] });
    routes["POST /api/admin/maps/estate/3/adopt-routes"] = () => json({ moved: ["night"] });
    const { container: c, getByLabelText } = mount();
    await waitFor(() => getByLabelText("estate:3"));
    fireEvent.click(getByLabelText("estate:3").querySelector(".btn.primary") as HTMLElement);
    const dialog = await waitFor(() => c.querySelector("dialog") as HTMLDialogElement);
    const boxes = Array.from(dialog.querySelectorAll("fieldset:not(.mm-options) input[type=checkbox]")) as HTMLInputElement[];
    expect(boxes[0].checked).toBe(true);                                          // P1-46:在线的默认勾上(A 现在用 2)
    const warn = await waitFor(() => { const w = dialog.querySelector(".mm-lost"); expect(w).not.toBeNull(); return w as HTMLElement; });
    expect(warn.textContent).toContain("night");
    expect(warn.textContent).not.toContain("x,");
    expect((warn.querySelector("input") as HTMLInputElement).checked).toBe(true);
    fireEvent.input(dialog.querySelector('input[name="confirm_pw"]') as HTMLElement, { target: { value: "pw" } });
    fireEvent.click(Array.from(dialog.querySelectorAll("button")).find((b) => b.textContent === "Publish") as HTMLElement);
    await waitFor(() => expect(calls.some((x) => x.path.endsWith("/adopt-routes"))).toBe(true));
    expect(calls.find((x) => x.path.endsWith("/adopt-routes"))?.body).toEqual({ from: "2" });
    await waitFor(() => expect(dialog.textContent).toContain("Patrol routes moved to v3: night"));
  });

  it("P0-14:不是编辑出来的版本默认不搬,发完提示路线要重画", async () => {
    routes["GET /api/routes"] = () => json({ routes: [{ id: "night", map_id: "estate", map_version: "2" }] });
    routes["POST /api/admin/maps/estate/3/publish"] = () => json({ results: [{ robot_id: "A", ok: true, state: "pending", reason: "" }] });
    const { container: c, getByLabelText } = mount();
    await waitFor(() => getByLabelText("estate:3"));
    fireEvent.click(getByLabelText("estate:3").querySelector(".btn.primary") as HTMLElement);
    const dialog = await waitFor(() => c.querySelector("dialog") as HTMLDialogElement);
    expect((dialog.querySelector("fieldset:not(.mm-options) input[type=checkbox]") as HTMLInputElement).checked).toBe(true);
    const warn = await waitFor(() => { const w = dialog.querySelector(".mm-lost"); expect(w).not.toBeNull(); return w as HTMLElement; });
    expect((warn.querySelector("input") as HTMLInputElement).checked).toBe(false);
    fireEvent.input(dialog.querySelector('input[name="confirm_pw"]') as HTMLElement, { target: { value: "pw" } });
    fireEvent.click(Array.from(dialog.querySelectorAll("button")).find((b) => b.textContent === "Publish") as HTMLElement);
    await waitFor(() => expect(dialog.textContent).toContain("will not run until you redraw or move them"));
    expect(calls.some((x) => x.path.endsWith("/adopt-routes"))).toBe(false);
  });

  it("第 2 轮 N4:还有机器人留在旧版、不在这次发布里 → 默认不搬,点名谁会没路线", async () => {
    overview.maps[0].versions[0] = { ...overview.maps[0].versions[0], source: "edit" };
    overview.robots.push(dog("D", { online: false, loaded: { map_id: "estate", version: "2" } }));
    routes["GET /api/routes"] = () => json({ routes: [{ id: "night", map_id: "estate", map_version: "2" }] });
    const { container: c, getByLabelText } = mount();
    await waitFor(() => getByLabelText("estate:3"));
    fireEvent.click(getByLabelText("estate:3").querySelector(".btn.primary") as HTMLElement);
    const dialog = await waitFor(() => c.querySelector("dialog") as HTMLDialogElement);
    const warn = await waitFor(() => { const w = dialog.querySelector(".mm-lost"); expect(w).not.toBeNull(); return w as HTMLElement; });
    const box = warn.querySelector("input") as HTMLInputElement;
    expect(box.checked).toBe(false);
    fireEvent.click(box);
    expect(warn.querySelector("[data-left-behind]")?.textContent).toContain("D");
  });

  it("第 3 轮(r2-maps-N2 残留):A、E 都在旧版、都勾上 → 默认搬;取消勾 A → 自动不搬,A 单数说 stays", async () => {
    overview.maps[0].versions[0] = { ...overview.maps[0].versions[0], source: "edit" };
    overview.robots.push(dog("E", { loaded: { map_id: "estate", version: "2" } }));
    routes["GET /api/routes"] = () => json({ routes: [{ id: "night", map_id: "estate", map_version: "2" }] });
    const { container: c, getByLabelText } = mount();
    await waitFor(() => getByLabelText("estate:3"));
    fireEvent.click(getByLabelText("estate:3").querySelector(".btn.primary") as HTMLElement);
    const dialog = await waitFor(() => c.querySelector("dialog") as HTMLDialogElement);
    const boxes = Array.from(dialog.querySelectorAll("fieldset:not(.mm-options) input[type=checkbox]")) as HTMLInputElement[];
    expect(boxes.filter((b) => b.checked).length).toBe(3);                      // A、B、E
    const warn = await waitFor(() => { const w = dialog.querySelector(".mm-lost"); expect(w).not.toBeNull(); return w as HTMLElement; });
    expect((warn.querySelector("input") as HTMLInputElement).checked).toBe(true);
    fireEvent.click(boxes[0]);
    await waitFor(() => expect((dialog.querySelector(".mm-lost input") as HTMLInputElement).checked).toBe(false));
    fireEvent.click(dialog.querySelector(".mm-lost input") as HTMLElement);
    expect(dialog.querySelector("[data-left-behind]")?.textContent).toMatch(/^A stays on v2/);
  });

  it("第 2 轮 N4:列出旧版有、新版没有的布置;带过来待核的说要去核", async () => {
    const zero = { areas: 0, exits: 0, hides: 0, posts: 0, net_nodes: 0, nogo: 0, cameras: 0, standby: 0, proposal: false };
    routes["GET /api/admin/maps/estate/2/layout"] = () => json({ ...zero, areas: 2, exits: 1, net_nodes: 5, nogo: 3, cameras: 1 });
    routes["GET /api/admin/maps/estate/3/layout"] = () => json({ ...zero, proposal: true });
    routes["GET /api/admin/maps/estate/1/layout"] = () => json(zero);
    const { container: c, getByLabelText } = mount();
    await waitFor(() => getByLabelText("estate:3"));
    fireEvent.click(getByLabelText("estate:3").querySelector(".btn.primary") as HTMLElement);
    const dialog = await waitFor(() => c.querySelector("dialog") as HTMLDialogElement);
    const miss = await waitFor(() => { const w = dialog.querySelector(".mm-missing"); expect(w).not.toBeNull(); return w as HTMLElement; });
    expect(miss.textContent).toContain("v2");
    expect(miss.textContent).toContain("2 zones");
    expect(miss.textContent).toContain("1 exit line");
    expect(miss.textContent).toContain("road network");
    expect(miss.textContent).toContain("1 camera");
    expect(miss.textContent).toContain("Check and keep them in Setup (No-go areas and Standby points tabs)");
  });

  it("只列在线又能换图的机器人;选了才能发;结果一只一行(成功和拒绝分开)", async () => {
    routes["POST /api/admin/maps/estate/3/publish"] = (b) => json({ results: [
      { robot_id: "A", ok: true, state: "pending", reason: "" },
      { robot_id: "B", ok: false, state: "refused", reason: "estate:3 的禁行区还没确认", code: "zones_unconfirmed" },
    ], b });
    const { container: c, getByText, getByLabelText } = mount();
    await waitFor(() => getByLabelText("estate:3"));
    fireEvent.click(getByLabelText("estate:3").querySelector(".btn.primary") as HTMLElement);
    const dialog = await waitFor(() => {
      const d = c.querySelector("dialog");
      expect(d).not.toBeNull();
      return d as HTMLDialogElement;
    });
    const boxes = Array.from(dialog.querySelectorAll("fieldset:not(.mm-options) input[type=checkbox]")) as HTMLInputElement[];
    expect(boxes.map((b) => b.disabled)).toEqual([false, false, true]);          // C 不在线
    const publish = Array.from(dialog.querySelectorAll("button")).find((b) => b.textContent === "Publish") as HTMLButtonElement;
    expect(publish.disabled).toBe(true);
    expect(boxes.map((b) => b.checked)).toEqual([true, true, false]);           // P1-46:在线、能换图的默认勾上
    
    fireEvent.click(dialog.querySelector(".mm-options input[type=checkbox]") as HTMLElement);
    expect(publish.disabled).toBe(true);                                          // 还没输密码
    fireEvent.input(dialog.querySelector('input[name="confirm_pw"]') as HTMLElement, { target: { value: "my-own-password" } });
    fireEvent.click(publish);
    await waitFor(() => expect(dialog.querySelectorAll(".mm-results li").length).toBe(2));
    expect(calls.find((x) => x.method === "POST")?.body).toEqual({ robots: ["A", "B"], without_home: true, confirm_password: "my-own-password" });
    const items = Array.from(dialog.querySelectorAll(".mm-results li"));
    expect(items[0].className).toBe("ok");
    expect(items[0].textContent).toContain("accepted");
    expect(items[1].className).toBe("bad");
    expect(items[1].textContent).toContain("禁行区还没确认");
    void getByText;
  });

  it("11-10 草稿:标「草稿」,不给下发、只给「打开草稿（预览、发布）」;正式版本的按钮叫「下发到机器人」", async () => {
    lang.value = "zh";
    overview.maps[0].versions[0] = { ...overview.maps[0].versions[0], source: "draft:alice", draft: true, draft_of: "2" };
    const { getByLabelText } = mount();
    await waitFor(() => getByLabelText("estate:3"));
    const card = getByLabelText("estate:3");
    expect(card.querySelector("[data-draft-tag]")!.textContent).toBe("草稿");
    expect(card.textContent).toContain("alice 在地图编辑器里的草稿");
    expect(Array.from(card.querySelectorAll("button")).some((b) => b.textContent?.includes("下发"))).toBe(false);
    expect(card.querySelector("[data-open-draft]")!.getAttribute("href")).toBe("#/admin/mapedit?map=estate&version=3&from=2");
    expect(Array.from(getByLabelText("estate:2").querySelectorAll("button")).map((b) => b.textContent)).toContain("下发到机器人…");
  });

  it("W6-12:只有最新那一版的「下发到机器人」是主按钮", async () => {
    lang.value = "zh";
    const { getByLabelText } = mount();
    await waitFor(() => getByLabelText("estate:3"));
    const send = (k: string) => Array.from(getByLabelText(k).querySelectorAll("button")).find((x) => x.textContent === "下发到机器人…");
    expect(send("estate:3")!.className).toContain("primary");
    expect(send("estate:2")!.className).not.toContain("primary");
  });
  it("缺定位文件的版本(11-05 现场第 10 条):卡片上写不能下发、缺什么;带定位器的机器人不能勾", async () => {
    lang.value = "zh";
    overview.maps[0].versions[0].unusable = "此地图需要重建:旧版建的图没有 Super-LIO 定位用的点云(superlio_map.pcd)";
    overview.robots[0].running = { ...overview.robots[0].running!, confirms: "localizer" };
    overview.robots[1].running = { ...overview.robots[1].running!, confirms: "load" };
    const { container: c, getByLabelText } = mount();
    await waitFor(() => getByLabelText("estate:3"));
    expect(getByLabelText("estate:3").textContent).toContain("这一版缺定位文件，机器人用不了");
    expect(getByLabelText("estate:3").textContent).toContain("superlio_map.pcd");
    expect(getByLabelText("estate:2").textContent).not.toContain("用不了");
    fireEvent.click(getByLabelText("estate:3").querySelector(".btn.primary") as HTMLElement);
    const dialog = await waitFor(() => c.querySelector("dialog") as HTMLDialogElement);
    const boxes = Array.from(dialog.querySelectorAll("fieldset:not(.mm-options) input[type=checkbox]")) as HTMLInputElement[];
    expect(boxes.map((b) => b.disabled)).toEqual([true, false, true]);           // A 带定位器、C 不在线
    expect(dialog.textContent).toContain("缺定位文件");
  });

  it("P1-45:禁行区没确认的版本,发布前就说、给去确认的入口,发布按钮灰着", async () => {
    overview.maps[0].versions[0] = { ...overview.maps[0].versions[0], counts: { ...overview.maps[0].versions[0].counts, zones_confirmed: false } };
    const { container: c, getByLabelText } = mount();
    await waitFor(() => getByLabelText("estate:3"));
    fireEvent.click(getByLabelText("estate:3").querySelector(".btn.primary") as HTMLElement);
    const dialog = await waitFor(() => c.querySelector("dialog") as HTMLDialogElement);
    fireEvent.input(dialog.querySelector('input[name="confirm_pw"]') as HTMLElement, { target: { value: "pw" } });
    expect(dialog.textContent).toContain("not confirmed");
    expect((dialog.querySelector('a[href^="#/admin/layout?tab=nogo&map="][href*="from=publish"]'))).not.toBeNull();   // 第 2 轮 maps N12:带版本
    expect((Array.from(dialog.querySelectorAll("button")).find((b) => b.textContent === "Publish") as HTMLButtonElement).disabled).toBe(true);
  });

  it("发布整个请求失败:对话框里显示错误,还能再试", async () => {
    routes["POST /api/admin/maps/estate/3/publish"] = () => json({ error: "boom" }, 500);
    const { container: c, getByLabelText } = mount();
    await waitFor(() => getByLabelText("estate:3"));
    fireEvent.click(getByLabelText("estate:3").querySelector(".btn.primary") as HTMLElement);
    const dialog = await waitFor(() => c.querySelector("dialog") as HTMLDialogElement);
    
    fireEvent.input(dialog.querySelector('input[name="confirm_pw"]') as HTMLElement, { target: { value: "pw" } });
    fireEvent.click(Array.from(dialog.querySelectorAll("button")).find((b) => b.textContent === "Publish") as HTMLElement);
    await waitFor(() => expect(dialog.textContent).toContain("boom"));
  });
});

describe("回退", () => {
  it("按钮上写着退到哪一版;确认文字说明机器人本地留着不用下载;点了发 rollback", async () => {
    routes["POST /api/admin/maps/rollback"] = () => json({ result: { robot_id: "A", ok: true, state: "pending", reason: "" } });
    const { container: c, getAllByText } = mount();
    await waitFor(() => getAllByText(/Roll back/));
    const buttons = Array.from(c.querySelectorAll(".mm-dogs tbody tr")).map((tr) => tr.querySelector("button") as HTMLButtonElement);
    expect(buttons.map((b) => b.disabled)).toEqual([false, true, true]);
    expect(buttons[0].textContent).toBe("Roll back to v1");
    fireEvent.click(buttons[0]);
    const dialog = await waitFor(() => c.querySelector("dialog") as HTMLDialogElement);
    expect(dialog.textContent).toContain("nothing is downloaded");
    typePw(dialog);
    await waitFor(() => expect(say).toHaveBeenCalledWith("A: rolling back…"));
    expect(calls.find((x) => x.path === "/api/admin/maps/rollback")?.body).toEqual({ robot_id: "A", without_home: true, confirm_password: "pw" });
  });

  it("机器人上没留的上一版:确认文字说会重新下载", async () => {
    overview.robots[0].rollback = { map_id: "estate", version: "1", local: false };
    const { container: c, getAllByText } = mount();
    await waitFor(() => getAllByText(/Roll back/));
    fireEvent.click(c.querySelector(".mm-dogs tbody tr button") as HTMLElement);
    const dialog = await waitFor(() => c.querySelector("dialog") as HTMLDialogElement);
    expect(dialog.textContent).toContain("download it again");
  });
});

describe("删除", () => {
  it("有机器人在用:按钮灰着带原因;最新一版也能删(P0-15);旧版本:确认后删,提示腾出多少", async () => {
    routes["POST /api/admin/maps/estate/1/delete"] = () => json({ deleted: "estate:1", freed_bytes: 12_500_000 });
    const { container: c, getByLabelText } = mount();
    await waitFor(() => getByLabelText("estate:3"));
    const del = (v: string) => Array.from(getByLabelText(`estate:${v}`).querySelectorAll("button")).find((b) => b.textContent === "Delete") as HTMLButtonElement;
    expect(del("3").disabled).toBe(false);
    expect(del("2").disabled).toBe(true);
    expect(del("2").title).toContain("A robot is using");
    expect(del("1").disabled).toBe(false);
    fireEvent.click(del("1"));
    const dialog = await waitFor(() => c.querySelector("dialog") as HTMLDialogElement);
    expect(dialog.textContent).toContain("cannot be undone");
    typePw(dialog);
    await waitFor(() => expect(say).toHaveBeenCalledWith("Deleted estate:1 (freed 13 MB)"));
  });

  it("站点拒了(409):把原因显示出来", async () => {
    routes["POST /api/admin/maps/estate/1/delete"] = () => json({ error: "estate:1 还有机器人在用(A)" }, 409);
    const { container: c, getByLabelText } = mount();
    await waitFor(() => getByLabelText("estate:1"));
    fireEvent.click(Array.from(getByLabelText("estate:1").querySelectorAll("button")).find((b) => b.textContent === "Delete") as HTMLElement);
    const dialog = await waitFor(() => c.querySelector("dialog") as HTMLDialogElement);
    typePw(dialog);
    await waitFor(() => expect(dialog.textContent).toContain("Robots are still using this map version (A)"));   // 错写在对话框里,能再试
  });
});

describe("对比", () => {
  const pickTwo = async (getByLabelText: (s: string) => HTMLElement, a = "3", b = "1") => {
    await waitFor(() => getByLabelText(`estate:${a}`));
    for (const v of [a, b]) fireEvent.click(getByLabelText(`estate:${v}`).querySelector("input[type=checkbox]") as HTMLElement);
  };
  const STATS = {
    a: "3", b: "1", width: 100, height: 80, caveat: "Separately built versions may not share a coordinate frame.", likely_misaligned: false,
    alignment: 0.93, frames_json_same: true, same_resolution: true,
    area_m2: { same_wall: 10, same_free: 90, wall_only_a: 1.5, wall_only_b: 0.5, free_only_a: 2, free_only_b: 3 },
    colors: { same_wall: "#464646", same_free: "#e1e1e1", wall_only_a: "#d62728", wall_only_b: "#1f77b4", free_only_a: "#ffa03c", free_only_b: "#3cbebe" },
  };

  it("勾两个才出对比按钮;打开后先看到提醒,再有图和图例", async () => {
    routes["GET /api/admin/maps/estate/3/diff"] = () => json(STATS);
    const { container: c, getByLabelText, queryByText, getByText } = mount();
    await pickTwo(getByLabelText as never);
    expect(queryByText("Compare the two ticked")).not.toBeNull();
    fireEvent.click(getByText("Compare the two ticked"));
    await waitFor(() => expect(c.querySelector(".mm-caveat")).not.toBeNull());
    expect(c.querySelector(".mm-caveat")!.textContent).toContain("may not share a coordinate frame");
    expect(c.querySelector(".mm-misaligned")).toBeNull();
    expect((c.querySelector(".mm-diffimg") as HTMLImageElement).getAttribute("src")).toBe("/api/admin/maps/estate/3/diff.png?with=1");
    expect(c.querySelectorAll(".mm-legend li").length).toBe(6);
    expect(c.querySelector(".mm-legend")!.textContent).toContain("Wall only in v3");    // P1-48:用版本号,不叫 A、B
    expect(calls.find((x) => x.path.includes("/diff?"))?.path).toBe("/api/admin/maps/estate/3/diff?with=1");
  });

  it("坐标系多半对不上:红框警告,说图没意义", async () => {
    routes["GET /api/admin/maps/estate/3/diff"] = () => json({ ...STATS, likely_misaligned: true, alignment: 0.04, frames_json_same: false });
    const { container: c, getByLabelText, getByText } = mount();
    await pickTwo(getByLabelText as never);
    fireEvent.click(getByText("Compare the two ticked"));
    await waitFor(() => expect(c.querySelector(".mm-misaligned")).not.toBeNull());
    expect(c.querySelector(".mm-misaligned")!.textContent).toContain("4%");
    expect(c.querySelector(".mm-misaligned")!.textContent).toContain("NOT in the same coordinate frame");
    expect(c.textContent).toContain("different frames.json");
  });

  it("只能在同一张图里勾两个;第三个顶掉最早勾的", async () => {
    routes["GET /api/admin/maps/estate/2/diff"] = () => json(STATS);
    const { getByLabelText, queryByText } = mount();
    await pickTwo(getByLabelText as never);
    const box = (v: string) => getByLabelText(`estate:${v}`).querySelector("input[type=checkbox]") as HTMLInputElement;
    fireEvent.click(box("2"));
    expect(box("3").checked).toBe(false);          // 3 被顶掉
    expect(box("1").checked && box("2").checked).toBe(true);
    expect(queryByText("Compare the two ticked")).not.toBeNull();
  });

  it("两次对比的回包乱序到:只认最后一次", async () => {
    const first = held();
    const second = held();
    let n = 0;
    routes["GET /api/admin/maps/estate/3/diff"] = () => { n += 1; return (n === 1 ? first : second).p as never; };
    routes["GET /api/admin/maps/estate/1/diff"] = () => second.p as never;
    const { container: c, getByLabelText, getByText } = mount();
    await pickTwo(getByLabelText as never, "3", "1");
    fireEvent.click(getByText("Compare the two ticked"));            // 3 vs 1(回包扣着)
    await waitFor(() => expect(n).toBe(1));
    fireEvent.click(Array.from(c.querySelectorAll("dialog .btn")).find((b) => b.textContent === "Close") as HTMLElement);
    fireEvent.click(getByLabelText("estate:3").querySelector("input[type=checkbox]") as HTMLElement);
    fireEvent.click(getByLabelText("estate:2").querySelector("input[type=checkbox]") as HTMLElement);
    fireEvent.click(getByText("Compare the two ticked"));            // 1 vs 2
    // 说明文字现在由网页写(第 2 轮 P1-01),哪次的回包用 data-a(版本号)认
    second.go(json({ ...STATS, a: "2" }));
    await waitFor(() => expect(c.querySelector(".mm-diff")?.getAttribute("data-a")).toBe("2"));
    first.go(json({ ...STATS, a: "3" }));
    await new Promise((r) => setTimeout(r, 20));
    expect(c.querySelector(".mm-diff")?.getAttribute("data-a")).toBe("2");
  });
});

describe("换图状态和运行配置的文字", () => {
  it("各个状态的说法;老代理的成功标出没等定位器", () => {
    expect(activationText(act("pending"))).toBe("Sent — waiting for the robot to start downloading");
    // W71:等机器人换的时候带下载进度
    expect(activationText(act("pending", { at_ms: 500, download: { bytes: 61e6, total: 145e6, at_ms: 1000 } }), 3000))
      .toBe("Downloading 61 MB / 145 MB");
    expect(activationText(act("pending", { at_ms: 500, download: { bytes: 145e6, total: 145e6, at_ms: 1000 } }), 31000))
      .toMatch(/nothing sent for 30 s/);
    // 第 4 轮 maps N2:回滚到已有的版本,下载记录是上一次的 —— 不算「多久没下」
    expect(activationText(act("pending", { at_ms: 700_000, download: { bytes: 145e6, total: 145e6, at_ms: 1000 } }), 702_000))
      .toBe("Switching to 2…");
    // W6-12:不出现 localizer 这种词
    expect(activationText(act("confirmed", { confirmed: "localizer" }))).toBe("Localized on the new map");
    expect(activationText(act("confirmed", { confirmed: "load" }))).toBe("Loaded");
    expect(activationText(act("confirmed", { confirmed: "legacy" }))).toContain("older robot software");
    for (const k of ["localizer", "load", "legacy"]) expect(activationText(act("confirmed", { confirmed: k }))).not.toMatch(/locali[sz]er/i);
    expect(activationText(act("failed", { reason: "rejected the prior (rolled back)" }))).toBe("Failed: rejected the prior (rolled back)");
    expect(activationText(act("timeout"))).toContain("treat as not done");
  });

  it("运行配置对不上:红字和原因;老代理标「只比修订号」", async () => {
    overview.robots[1].running = {
      legacy: false, problems: ["estate:1 content differs from the site"],
      map: { dog: "a", site: "b", match: false }, zones: { dog_rev: 2, site_rev: 2, match: true, basis: "revision" },
      mission: { mission: "night", rev: "abc123" } };
    overview.robots[0].running = { legacy: true, problems: [], map: null, zones: null };
    const { container: c } = mount();
    await waitFor(() => expect(c.textContent).toContain("content differs"));
    const rows = Array.from(c.querySelectorAll(".mm-dogs tbody tr"));
    expect(rows[0].textContent).toContain("Old agent: only the zone revision is compared");
    expect(rows[1].textContent).toContain("Map ✗");
    expect(rows[1].textContent).toContain("old agent: revision only");
    // 第 2 轮 P1-50:任务编号、哈希不摆在表里,悬停看
    expect(rows[1].textContent).not.toContain("abc123");
    expect(rows[1].querySelector('[title="night · abc123"]')).not.toBeNull();
  });
});

describe("第 2 轮 P1-50:版本来源写操作人", () => {
  it("编辑、清噪点、命令行导入带人;机器人建的写机器人", async () => {
    const { sourceText } = await import("./mapmgmt");
    lang.value = "en";
    expect(sourceText("edit:alice")).toBe("edited by alice in the map editor");
    expect(sourceText("denoise:bob")).toBe("noise cleaned up by bob");
    expect(sourceText("cli:liang")).toBe("imported by an engineer");
    expect(sourceText("edit")).toBe("edited in the map editor");
    expect(sourceText("A")).toContain("built by robot");
    lang.value = "zh";
    expect(sourceText("denoise:bob")).toBe("bob 清的噪点");
  });
});

describe("W41 清噪点", () => {
  it("是退回目标的版本(P0-15):能删,确认框说退不回去了,发 confirm_rollback", async () => {
    overview.maps[0].versions[2] = ver("1", { previous_on: ["A"] });
    let body: unknown = null;
    routes["POST /api/admin/maps/estate/1/delete"] = (b: unknown) => { body = b; return json({ deleted: "estate:1", freed_bytes: 1 }); };
    const { container: c, getByLabelText } = mount();
    await waitFor(() => getByLabelText("estate:1"));
    const del = Array.from(getByLabelText("estate:1").querySelectorAll("button")).find((b) => b.textContent === "Delete") as HTMLButtonElement;
    expect(del.disabled).toBe(false);
    fireEvent.click(del);
    const dialog = await waitFor(() => c.querySelector("dialog") as HTMLDialogElement);
    expect(dialog.textContent).toContain("cannot roll back to it");
    typePw(dialog);
    await waitFor(() => expect(body).toEqual({ confirm_password: "pw", confirm_rollback: true }));
  });

  it("红圈画在图上;点一个留着它;清掉其余的、另存新版,带上看过的那份摘要", async () => {
    routes["GET /api/admin/maps/estate/1/noise"] = () => json({ digest: "d1", res: 0.05, max_m2: 0.05, ring_m: 0.2,
      specks: [{ id: 1, x: 1.0, y: 2.0, px: 3 }, { id: 2, x: -1.0, y: 0.5, px: 1 }, { id: 3, x: 2.0, y: -1.0, px: 2 }] });
    routes["GET /api/maps/estate/1/preview"] = () => json({ width: 400, height: 300, m_per_px: 0.05, left_x: -10, top_y: 8 });
    routes["POST /api/admin/maps/estate/1/denoise"] = () => json({ version: "4", cleaned: 2, cells: 5, homes_copied: 1 });
    const { container: c, getByLabelText } = mount();
    await waitFor(() => getByLabelText("estate:1"));
    fireEvent.click(Array.from(getByLabelText("estate:1").querySelectorAll("button")).find((b) => b.textContent === "Clean noise…") as HTMLElement);
    await waitFor(() => expect(c.querySelectorAll("circle[data-speck]").length).toBe(3));
    fireEvent.load(c.querySelector(".mm-noiseimg image")!);   // 复查 N3:底图加载好了才许清
    // P0-11:整个圈都能点(不是只有圈线),圈按图的大小放大
    const circle = c.querySelector('circle[data-speck="2"]') as Element;
    expect(circle.getAttribute("pointer-events")).toBe("all");
    expect(circle.getAttribute("fill")).toBe("transparent");
    expect(Number(circle.getAttribute("r"))).toBeGreaterThanOrEqual(6);
    fireEvent.click(circle);
    expect(c.querySelector('circle[data-speck="2"]')!.getAttribute("data-kept")).toBe("1");
    expect((c.querySelector('input[data-keep="2"]') as HTMLInputElement).checked).toBe(true);
    fireEvent.click(c.querySelector('input[data-keep="3"]') as HTMLElement);       // 清单里勾也行
    expect(c.querySelector('circle[data-speck="3"]')!.getAttribute("data-kept")).toBe("1");
    fireEvent.click(c.querySelector('input[data-keep="3"]') as HTMLElement);
    const go = c.querySelector("[data-denoise]") as HTMLButtonElement;
    expect(go.textContent).toContain("Clean 2 spots");
    fireEvent.click(go);
    await waitFor(() => expect(say).toHaveBeenCalledWith(expect.stringContaining("Saved as draft v4")));
    const post = calls.find((x) => x.method === "POST" && x.path.endsWith("/denoise"))!;
    expect(post.body).toEqual({ digest: "d1", skip: [2] });
  });

  it("站点拒了(图换了):原因显示在对话框里", async () => {
    routes["GET /api/admin/maps/estate/1/noise"] = () => json({ digest: "d1", res: 0.05, max_m2: 0.05, ring_m: 0.2, specks: [{ id: 1, x: 1, y: 2, px: 3 }] });
    routes["GET /api/maps/estate/1/preview"] = () => json({ width: 400, height: 300, m_per_px: 0.05, left_x: -10, top_y: 8 });
    routes["POST /api/admin/maps/estate/1/denoise"] = () => json({ error: "这一版的栅格在你看过之后换了" }, 409);
    const { container: c, getByLabelText } = mount();
    await waitFor(() => getByLabelText("estate:1"));
    fireEvent.click(Array.from(getByLabelText("estate:1").querySelectorAll("button")).find((b) => b.textContent === "Clean noise…") as HTMLElement);
    await waitFor(() => expect(c.querySelector(".mm-noiseimg image")).not.toBeNull());
    fireEvent.load(c.querySelector(".mm-noiseimg image")!);   // 复查 N3:底图加载好了才许清
    await waitFor(() => expect((c.querySelector("[data-denoise]") as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(c.querySelector("[data-denoise]") as HTMLElement);
    await waitFor(() => expect(c.querySelector('[role="alert"]')?.textContent).toContain("changed after you opened it"));
  });
});

describe("第 2 轮 P0-14:路线条数的说法", () => {
  it("英文单复数写对,巡逻、防区分开数", () => {
    lang.value = "en";
    expect(routeCount(1, 0)).toBe("1 patrol route");
    expect(routeCount(2, 1)).toBe("2 patrol routes and 1 zone route");
    lang.value = "zh";
    expect(routeCount(2, 1)).toBe("2 条巡逻路线、1 条防区路线");
  });
});

describe("第 2 轮 maps N9:回滚按钮写清往哪走", () => {
  it("上一版比现在旧:退回到 v7;刚退回过、上一版更新:换回 v12", () => {
    expect(rollLabel({ loaded: { map_id: "e", version: "12" }, rollback: { map_id: "e", version: "7", local: true } })).toBe("Roll back to v7");
    expect(rollLabel({ loaded: { map_id: "e", version: "7" }, rollback: { map_id: "e", version: "12", local: true } })).toBe("Switch to v12 (newer)");
    expect(rollLabel({ loaded: null, rollback: null })).toBe("Roll back");
  });
});

describe("第 2 轮 maps N11:区域数括号里加起来等于总数", () => {
  it("4 个里 2 禁行 1 限速:另 1 个写不可通行 / 忽略区", async () => {
    overview.maps[0].versions[0].counts.zones = 4;
    const { container: c, getByLabelText } = mount();
    await waitFor(() => expect(c.textContent).toContain("v3"));
    expect(getByLabelText("estate:3").textContent).toContain("Zones 4 (2 no-go, 1 slow, 1 impassable / ignore)");
    expect(getByLabelText("estate:2").querySelector("[data-zone-other]")).toBeNull();
  });
});

describe("第 3 轮 maps N4", () => {
  it("少了一部分也说:3 个禁区里少了 2 个", async () => {
    const { missingLayout } = await import("./mapmgmt");
    const base = { areas: 0, exits: 0, hides: 0, posts: 0, net_nodes: 0, nogo: 0, cameras: 0, standby: 0, proposal: false };
    lang.value = "en";
    const got = missingLayout({ ...base, nogo: 3, areas: 2 }, { ...base, nogo: 1, areas: 2 });
    expect(got.map((m) => m.text)).toEqual(["2 of 3 no-go zones"]);
    lang.value = "zh";
    expect(missingLayout({ ...base, nogo: 3 }, { ...base, nogo: 1 })[0].text).toBe("3 个禁区里的 2 个");
  });
});

describe("第 4 轮 maps N4", () => {
  it("按名字比、分种类;删掉的和带过来待核的分开说", async () => {
    const { missingLayout } = await import("./mapmgmt");
    const base = { areas: 0, exits: 0, hides: 0, posts: 0, net_nodes: 0, nogo: 0, cameras: 0, standby: 0, proposal: false };
    lang.value = "en";
    const from = { ...base, nogo: 3, standby: 1, names: { areas: [], nogo: ["Wall", "Slow", "Keep"], standby: ["B/home"] },
      kinds: { Wall: "nogo", Slow: "slow", Keep: "nogo" } };
    // 新版本上 Keep 留着、多了 V8Only;少了 Wall(删了)和 Slow(删了);待命点带过来待核
    const to = { ...base, nogo: 2, proposal: true, names: { areas: [], nogo: ["Keep", "V8Only"], standby: [] },
      kinds: { Keep: "nogo", V8Only: "nogo" }, proposed: { nogo: [], standby: ["B/home"] } };
    const got = missingLayout(from, to);
    expect(got).toEqual([
      { text: "1 no-go area (Wall)", review: false },
      { text: "1 slow zone (Slow)", review: false },
      { text: "1 standby point (B/home)", review: true },
    ]);
  });
});
