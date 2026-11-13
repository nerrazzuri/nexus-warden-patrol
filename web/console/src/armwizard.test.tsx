// @vitest-environment happy-dom
// 布防向导(用户 11-13):用户自己配布防值守时卡住 —— 存了防区路线没进值守方案、机器人只许手动派,系统没说为什么不走。
import { cleanup, fireEvent, render, waitFor } from "@testing-library/preact";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { setFetch } from "./api";
import { afterLines, ArmWizard, dailySlots, missingText, needsWizard, PatrolReason, wholeMap, type Readiness } from "./armwizard";
import { lang } from "./i18n";

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
const MAPS = { maps: [{ map_id: "estate-1", version: "6", note: "", loaded_on: [] }, { map_id: "estate-1", version: "7", note: "", active: true, loaded_on: ["A", "B"] }] };
const META = { width: 100, height: 50, m_per_px: 0.1, left_x: -2, top_y: 3, zones: [] };
const R: Readiness = {
  map_id: "estate-1", map_version: "7", zones: ["1"], routes: [{ id: "guard-1", title: "", zones: ["1"], in_plan: false }],
  robots: [{ id: "A", code: "manual_only", why: "A 设成只许手动派" }, { id: "B", code: "", why: "" }], missing: ["plan"],
};

let ready: Readiness;
let status: unknown;
let plan: Record<string, unknown>;
let preview: Record<string, unknown> | null;
let taken: Set<string>;
let posted: { url: string; body: Record<string, unknown> }[];
let gets: string[];
beforeEach(() => {
  lang.value = "zh";
  ready = structuredClone(R);
  status = { duty: null, runs: [], waiting: {}, zones: [], now_ms: 1 };
  posted = [];
  gets = [];
  plan = { revision: 0, entries: [], limits: {}, forecast: { entries: [], zones: [], warnings: [] } };
  preview = null;
  taken = new Set();
  setFetch(((url: string, init?: RequestInit) => {
    if (init?.method === "POST") {
      const body = JSON.parse(String(init.body ?? "{}"));
      posted.push({ url, body });
      if (url === "/api/guard/plan") {
        ready.missing = [];
        const es = (body as { entries: Record<string, unknown>[] }).entries;
        plan = { ...plan, revision: Number(plan.revision) + 1, entries: es.map((e, i) => ({ id: i + 1, ...e })) };
      }
      if (url === "/api/guard-routes/generate") {
        return Promise.resolve(json({ waypoints: [{ name: "1-1", x: 1, y: 1, yaw: 0 }], problems: [], zones: [{ zone: "1", points: 1, note: "" }] }));
      }
      if (url === "/api/arming/schedule/preview") {
        const m = { mode: "armed", state: "armed", zones: [{ zone: "1", armed: true }] };
        if (preview?.__fail) return Promise.resolve(json({ error: "预演坏了" }, 500));
        return Promise.resolve(json(preview ?? { before: m, after: m }));
      }
      if (url.startsWith("/api/routes/") && taken.has(decodeURIComponent(url.split("/").pop()!))) {
        return Promise.resolve(json({ error: "路线别人刚改过", errors: [] }, 409));
      }
      if (url.endsWith("/areas")) ready = { ...ready, zones: [String(body.zone)], missing: ready.missing.filter((m) => m !== "zones") };
      if (url === "/api/robots/A/service") ready.robots[0] = { id: "A", code: "", why: "" };
      return Promise.resolve(json({ revision: 1, entries: [], limits: {}, forecast: { entries: [], zones: [], warnings: [] } }));
    }
    gets.push(url);
    if (url === "/api/maps") return Promise.resolve(json(MAPS));
    if (url.startsWith("/api/guard/readiness")) return Promise.resolve(json(ready));
    if (url === "/api/guard/plan") return Promise.resolve(json(plan));
    if (url === "/api/arming/schedule") return Promise.resolve(json({ enabled: false, slots: [] }));
    if (url === "/api/guard/status") return Promise.resolve(json(status));
    if (url.endsWith("/preview")) return Promise.resolve(json(META));
    return Promise.resolve(json({}, 404));
  }) as typeof fetch);
});
afterEach(cleanup);

describe("布防向导的小函数", () => {
  it("每天 21:30 到 06:00:跨半夜拆成两段,一周 14 段;不跨半夜一周 7 段", () => {
    const s = dailySlots(21 * 60 + 30, 6 * 60);
    expect(s).toHaveLength(14);
    expect(s).toContainEqual({ zone: "", day: 0, start: "21:30", end: "24:00" });
    expect(s).toContainEqual({ zone: "", day: 0, start: "00:00", end: "06:00" });
    expect(dailySlots(8 * 60, 18 * 60)).toHaveLength(7);
  });
  it("整张图的外框按地图元数据算(米)", () => {
    expect(wholeMap(META)).toEqual([[-2, -2], [8, -2], [8, 3], [-2, 3]]);
  });
  it("为什么不巡逻:按步骤先说缺的第一样;缺机器人时说每台的原因", () => {
    expect(missingText({ ...R, missing: ["zones", "route", "plan", "robot"] })).toBe("这张图上没有防区");
    expect(missingText({ ...R, missing: ["plan"] })).toBe("值守方案里没有给机器人分配防区路线");
    expect(missingText({ ...R, missing: ["robot"] })).toBe("A 设成只许手动派");
    expect(missingText({ ...R, missing: [] })).toBe("");
    lang.value = "en";
    expect(missingText({ ...R, missing: ["robot"] })).toBe("A is set to manual dispatch only");
    expect(missingText({ ...R, missing: ["plan"] })).toBe("no zone route is assigned to a robot");
  });
  it("点布防前查:图由站点挑(跟手机同一张,外审 1 #8);缺东西才开向导", async () => {
    expect(await needsWizard()).toBe(true);
    expect(gets).toContain("/api/guard/readiness");
    ready.missing = [];
    expect(await needsWizard()).toBe(false);
  });
});

describe("UIUX-036:布防后逐条说", () => {
  it("哪台在跑哪条第几圈、哪条在等为什么;每条都有结果才算说完", () => {
    const entries = [{ id: 1, route: "guard-1", robot: "", gap_min: 0, shuffle: false }, { id: 2, route: "old", robot: "B", gap_min: 0, shuffle: false }];
    const title = (id: string) => (id === "guard-1" ? "防区巡逻 1" : id);
    const st = { duty: null, runs: [{ entry: 1, robot_id: "A", state: "lap", lap: 1, task_id: "t1", next_lap_ms: 0, watch_zone: "" }],
      waiting: { 2: "B 设成只许手动派" }, zones: [], now_ms: 1 };
    expect(afterLines(entries, st, title)).toEqual([["A 正在跑「防区巡逻 1」，第 1 圈。", "「old」还没出发：B 设成只许手动派"], true]);
    expect(afterLines(entries, { ...st, waiting: {} }, title)).toEqual([["A 正在跑「防区巡逻 1」，第 1 圈。"], false]);
  });
});

describe("布防向导", () => {
  it("缺值守方案:直接到「谁去巡逻」;说 A 只许手动派、能改成自动派遣;存方案;布防后说谁出发了", async () => {
    let changes = 0;
    const r = render(<ArmWizard say={() => {}} onClose={() => {}} arming onChanged={() => { changes++; }} />);
    await waitFor(() => expect(r.container.ownerDocument.querySelector("[data-wiz-step=who]")).not.toBeNull());
    const doc = r.container.ownerDocument;
    expect(doc.querySelector("[data-wiz-robot=A]")!.textContent).toContain("A 设成只许手动派");
    fireEvent.click(doc.querySelector<HTMLButtonElement>("[data-wiz-robot=A] button")!);
    await waitFor(() => expect(posted.some((p) => p.url === "/api/robots/A/service" && p.body.manual_only === false)).toBe(true));
    await waitFor(() => expect(doc.querySelector("[data-wiz-robot=A]")!.textContent).toContain("能派"));
    expect(changes).toBe(1);   // 外审 3:改成自动派遣也算改过,背后的页要重读
    fireEvent.click(r.getByText("下一步"));
    await waitFor(() => expect(posted.some((p) => p.url === "/api/guard/plan")).toBe(true));
    const plan = posted.find((p) => p.url === "/api/guard/plan")!.body;
    expect(plan.entries).toEqual([{ route: "guard-1", robot: "", gap_min: 0, shuffle: false, end_standby: true }]);
    expect(plan.base_revision).toBe(0);
    await waitFor(() => expect(doc.querySelector("[data-wiz-step=confirm]")).not.toBeNull());
    expect(doc.querySelector("[data-wiz-missing]")).toBeNull();
    status = { duty: { id: 1, started_ms: 1 }, runs: [{ entry: 1, robot_id: "B", state: "lap", lap: 1, task_id: "guard-1-x", next_lap_ms: 0, watch_zone: "" }], waiting: {}, zones: [], now_ms: 1 };
    fireEvent.click(r.getByText("现在布防"));
    await waitFor(() => expect(posted.some((p) => p.url === "/api/mode" && p.body.mode === "armed")).toBe(true));
    // UIUX-036:按方案逐条说哪台在跑哪条、第几圈(原来只说「B 已出发」)
    await waitFor(() => expect(doc.querySelector("[data-wiz-after]")!.textContent).toBe("B 正在跑「guard-1」，第 1 圈。"), { timeout: 4000 });
  });

  it("没有防区:停在第一步;「整张图作为一个防区」按地图外框建一个「全场」", async () => {
    ready = { ...ready, zones: [], routes: [], missing: ["zones", "route", "plan"] };
    let changes = 0;
    const r = render(<ArmWizard say={() => {}} onClose={() => {}} onChanged={() => { changes++; }} />);
    await waitFor(() => expect(r.getByText("这张图上还没有防区。")).toBeTruthy());
    expect((r.getByText("下一步") as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(r.getByText("整张图作为一个防区"));
    await waitFor(() => expect(posted.some((p) => p.url.endsWith("/areas"))).toBe(true));
    const a = posted.find((p) => p.url.endsWith("/areas"))!;
    expect(a.url).toBe("/api/maps/estate-1/7/areas");
    expect(a.body).toEqual({ zone: "全场", points: [[-2, -2], [8, -2], [8, 3], [-2, 3]] });
    await waitFor(() => expect((r.getByText("下一步") as HTMLButtonElement).disabled).toBe(false));
    expect(changes).toBe(1);   // 外审 3:背后的布置页要重读,不然再存「全场」会盖掉这个
  });

  it("布防时间:选「每天 21:30 到 06:00」存成启用的时间表", async () => {
    ready.missing = [];
    const r = render(<ArmWizard say={() => {}} onClose={() => {}} />);
    await waitFor(() => expect(r.container.ownerDocument.querySelector("[data-wiz-step=confirm]")).not.toBeNull());
    fireEvent.click(r.getByText(/什么时候布防/));
    fireEvent.click(r.getByText("下一步"));
    await waitFor(() => expect(posted.some((p) => p.url === "/api/arming/schedule")).toBe(true));
    const s = posted.find((p) => p.url === "/api/arming/schedule")!.body;
    expect(s.enabled).toBe(true);
    expect(s.slots).toHaveLength(14);
  });

  it("在地图上改防区:就地嵌布置页的防区编辑器,不跳页面、没有别的标签", async () => {
    ready.missing = ["zones"];
    const before = location.hash;
    const r = render(<ArmWizard say={() => {}} onClose={() => {}} />);
    await waitFor(() => expect(r.getByText("在地图上修改防区")).toBeTruthy());
    fireEvent.click(r.getByText("在地图上修改防区"));
    const doc = r.container.ownerDocument;
    await waitFor(() => expect(doc.querySelector(".wiz-editor .layout")).not.toBeNull());
    expect(doc.querySelector(".wiz-editor .ly-tabs")).toBeNull();
    expect(doc.querySelector(".wiz-editor select")).toBeNull();
    expect(doc.querySelector(".wiz-editor")!.textContent).toContain("estate-1 · v7");
    expect(location.hash).toBe(before);
  });

  it("UIUX-036:值守方案里不止一条时,确认页全列出来", async () => {
    ready.missing = [];
    plan = { ...plan, entries: [{ id: 1, route: "guard-1", robot: "", gap_min: 0, shuffle: false, end_standby: true },
      { id: 2, route: "old", robot: "B", gap_min: 0, shuffle: false, end_standby: true }] };
    const r = render(<ArmWizard say={() => {}} onClose={() => {}} />);
    await waitFor(() => expect(r.container.ownerDocument.querySelector("[data-wiz-plan]")?.textContent).toBe("guard-1（哪台空就派哪台）；old（B）"));
  });

  it("外审 1 #1 #9:存方案只换这条路线那一行,别的路线、隐藏选项都不动", async () => {
    plan = { ...plan, revision: 3, entries: [
      { id: 1, route: "other", robot: "B", gap_min: 5, shuffle: true, end_standby: false },
      { id: 2, route: "guard-1", robot: "", gap_min: 0, shuffle: true, end_standby: false }] };
    const r = render(<ArmWizard say={() => {}} onClose={() => {}} />);
    await waitFor(() => expect(r.container.ownerDocument.querySelector("[data-wiz-step=who]")).not.toBeNull());
    fireEvent.change(r.container.ownerDocument.querySelector("[data-wiz-step=who] select")!, { target: { value: "B" } });
    fireEvent.click(r.getByText("下一步"));
    await waitFor(() => expect(posted.some((p) => p.url === "/api/guard/plan")).toBe(true));
    const body = posted.find((p) => p.url === "/api/guard/plan")!.body;
    expect(body.base_revision).toBe(3);
    expect(body.entries).toEqual([
      { route: "other", robot: "B", gap_min: 5, shuffle: true, end_standby: false },
      { route: "guard-1", robot: "B", gap_min: 0, shuffle: true, end_standby: false }]);
  });

  it("外审 1 #2:改布防时间会马上撤防,先说清楚,确认了才存", async () => {
    ready.missing = [];
    preview = { before: { mode: "armed", state: "armed", zones: [{ zone: "1", armed: true }] },
      after: { mode: "home", state: "disarmed", zones: [{ zone: "1", armed: false }] } };
    const r = render(<ArmWizard say={() => {}} onClose={() => {}} />);
    await waitFor(() => expect(r.container.ownerDocument.querySelector("[data-wiz-step=confirm]")).not.toBeNull());
    fireEvent.click(r.getByText(/什么时候布防/));
    fireEvent.click(r.getByText("下一步"));
    await waitFor(() => expect(r.getAllByText("保存这个时间").length).toBeGreaterThan(0));
    expect(posted.some((p) => p.url === "/api/arming/schedule")).toBe(false);
    fireEvent.click(r.getAllByText("保存这个时间").find((el) => el.tagName === "BUTTON")!);
    await waitFor(() => expect(posted.some((p) => p.url === "/api/arming/schedule")).toBe(true));
  });

  it("外审 1 #4:一个防区都不经过的路线不能选,写原因", async () => {
    ready.routes = [...ready.routes, { id: "far", title: "远处", zones: [], in_plan: false }];
    ready.missing = ["plan"];
    const r = render(<ArmWizard say={() => {}} onClose={() => {}} />);
    await waitFor(() => expect(r.container.ownerDocument.querySelector("[data-wiz-step=who]")).not.toBeNull());
    fireEvent.click(r.getByText(/巡逻路线/));
    await waitFor(() => expect(r.container.ownerDocument.querySelector("[data-route-nozone]")?.textContent).toBe("一个防区都不经过，机器人不会去跑"));
    const radios = r.container.ownerDocument.querySelectorAll<HTMLInputElement>("input[name=wiz-route]");
    expect([...radios].map((x) => [x.checked, x.disabled])).toEqual([[true, false], [false, true]]);
  });

  it("外审 2 #2:预演失败不存,说原因", async () => {
    ready.missing = [];
    let said = "";
    preview = { __fail: true };
    const r = render(<ArmWizard say={(s) => { said = s; }} onClose={() => {}} />);
    await waitFor(() => expect(r.container.ownerDocument.querySelector("[data-wiz-step=confirm]")).not.toBeNull());
    fireEvent.click(r.getByText(/什么时候布防/));
    fireEvent.click(r.getByText("下一步"));
    await waitFor(() => expect(said).toContain("预演坏了"));
    expect(posted.some((p) => p.url === "/api/arming/schedule")).toBe(false);
    expect(r.container.ownerDocument.querySelector("[data-wiz-step=time]")).not.toBeNull();
  });

  it("外审 1 #10:自动生成的编号被别的路线占着(409),换下一个", async () => {
    ready = { ...ready, routes: [], missing: ["route", "plan"] };
    taken.add("guard-estate-1-7");
    let changes = 0;
    const r = render(<ArmWizard say={() => {}} onClose={() => {}} onChanged={() => { changes++; }} />);
    await waitFor(() => expect(r.getByText("按防区自动生成")).toBeTruthy());
    fireEvent.click(r.getByText("按防区自动生成"));
    await waitFor(() => expect(posted.some((p) => p.url === "/api/routes/guard-estate-1-7-2")).toBe(true));
    expect(r.container.ownerDocument.querySelector(".wiz-editor")).toBeNull();
    await waitFor(() => expect(changes).toBe(1));
  });

  it("只布防、不让机器人巡逻:直接布防,不存方案", async () => {
    let closed = false;
    const r = render(<ArmWizard say={() => {}} onClose={() => { closed = true; }} arming />);
    await waitFor(() => expect(r.getByText("只布防，不让机器人巡逻")).toBeTruthy());
    fireEvent.click(r.getByText("只布防，不让机器人巡逻"));
    await waitFor(() => expect(closed).toBe(true));
    expect(posted.map((p) => p.url)).toEqual(["/api/mode"]);
  });
});

describe("布防着却不巡逻:说原因", () => {
  it("缺东西时写一句并给向导入口;齐了不写", async () => {
    let opened = false;
    const r = render(<PatrolReason onWizard={() => { opened = true; }} />);
    await waitFor(() => expect(r.container.textContent).toContain("布防着，但机器人不会自己巡逻：值守方案里没有给机器人分配防区路线。"));
    fireEvent.click(r.getByText("打开布防向导"));
    expect(opened).toBe(true);
    cleanup();
    ready.missing = [];
    const r2 = render(<PatrolReason onWizard={() => {}} />);
    await new Promise((ok) => setTimeout(ok, 50));
    expect(r2.container.querySelector("[data-patrol-reason]")).toBeNull();
  });
});
