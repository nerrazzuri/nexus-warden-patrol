// @vitest-environment happy-dom
// 布防向导(用户 11-13):用户自己配布防值守时卡住 —— 存了防区路线没进值守方案、机器人只许手动派,系统没说为什么不走。
import { cleanup, fireEvent, render, waitFor, type RenderResult } from "@testing-library/preact";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { setFetch } from "./api";
import { afterLines, ArmWizard, dailySlots, missingText, needsWizard, PatrolReason, patrolHint, wholeMap, type Readiness } from "./armwizard";
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
let schedule: { enabled: boolean; slots: unknown[] };
beforeEach(() => {
  schedule = { enabled: false, slots: [] };
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
    if (url === "/api/arming/schedule") return Promise.resolve(json(schedule));
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
  it("笔记本复测 11-15:覆盖前列出旧时间 —— 同一时段的几天并一起,七天写「每天」", async () => {
    const { slotsText } = await import("./armwizard");
    const week = [0, 1, 2, 3, 4, 5, 6].map((day) => ({ zone: "", day, start: "22:00", end: "24:00" }));
    expect(slotsText([...week, { zone: "", day: 5, start: "00:00", end: "06:00" }, { zone: "", day: 6, start: "00:00", end: "06:00" }]))
      .toBe("每天 22:00–24:00；周六、周日 00:00–06:00");
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
  it("外审 Minor:英文界面的未出发原因翻成英文", () => {
    lang.value = "en";
    try {
      const e1 = [{ id: 1, route: "guard-1", robot: "", gap_min: 0, shuffle: false }];
      const [lines] = afterLines(e1, { duty: null, runs: [], waiting: { 1: "A 不在线" }, zones: [], now_ms: 1 }, () => "R");
      expect(lines[0]).toBe("“R” has not started: A is offline");
      // 外审 2 Minor:值守常见的几种原因都有英文
      const why = (w: string) => afterLines(e1, { duty: null, runs: [], waiting: { 1: w }, zones: [], now_ms: 1 }, () => "R")[0][0];
      expect(why("A 设成只许手动派")).toBe("“R” has not started: A is set to manual dispatch only");
      expect(why("A 在回充")).toBe("“R” has not started: A is charging");
      expect(why("A 还没报电量")).toBe("“R” has not started: A has not reported its battery yet");
      expect(why("A 电量 20%,不够跑一圈(要 ≥ 40%),先补能")).toBe("“R” has not started: A is at 20%, not enough for a lap (needs ≥ 40%); charging first");
      expect(why("A 刚连回来,等它报手上的任务")).toBe("“R” has not started: A just reconnected; waiting for it to report its task");
      expect(why("A 没登记")).toBe("“R” has not started: A is not registered");
      expect(why("A 要人在旁边监护,不自己出去")).toBe("“R” has not started: A needs a person beside it and does not go out alone");
      expect(why("防区路线 g1 上布防着的防区里没有点")).toBe("“R” has not started: zone route g1 has no points in the armed zones");
    } finally { lang.value = "zh"; }
  });

  it("哪台在跑哪条第几圈、哪条在等为什么;每条都有结果才算说完", () => {
    const entries = [{ id: 1, route: "guard-1", robot: "", gap_min: 0, shuffle: false }, { id: 2, route: "old", robot: "B", gap_min: 0, shuffle: false }];
    const title = (id: string) => (id === "guard-1" ? "防区巡逻 1" : id);
    const st = { duty: null, runs: [{ entry: 1, robot_id: "A", state: "lap", lap: 1, task_id: "t1", next_lap_ms: 0, watch_zone: "" }],
      waiting: { 2: "B 设成只许手动派" }, zones: [], now_ms: 1 };
    expect(afterLines(entries, st, title)).toEqual([["A 正在跑「防区巡逻 1」，第 1 圈。", "「old」还没出发：B 设成只许手动派"], true]);
    expect(afterLines(entries, { ...st, waiting: {} }, title)).toEqual([["A 正在跑「防区巡逻 1」，第 1 圈。"], false]);
  });

  it("外审:只有 lap 才说「正在跑」;值守、等下一圈、暂停各说各的,有原因带上", () => {
    const e1 = [{ id: 1, route: "guard-1", robot: "", gap_min: 0, shuffle: false }];
    const run = (state: string) => ({ duty: null, runs: [{ entry: 1, robot_id: "A", state, lap: 2, task_id: "t1", next_lap_ms: 0, watch_zone: "1" }],
      waiting: {}, zones: [], now_ms: 1 });
    const title = () => "R";
    // 外审 2:watch 是在去值守点的路上(到了才是 post)
    expect(afterLines(e1, run("watch"), title)[0]).toEqual(["A 跑完第 2 圈，正在去「R」的值守点。"]);
    expect(afterLines(e1, run("post"), title)[0]).toEqual(["A 跑完第 2 圈，在「R」的值守点守着。"]);
    expect(afterLines(e1, run("wait"), title)[0]).toEqual(["A 在等「R」的下一圈。"]);
    expect(afterLines(e1, { ...run("resume"), waiting: { 1: "A 电量低，先去补能" } }, title)[0])
      .toEqual(["A 在等「R」的下一圈：A 电量低，先去补能"]);
    expect(afterLines(e1, run("paused"), title)[0]).toEqual(["A 在「R」上暂停了。"]);
    expect(afterLines(e1, run("held"), title)[0]).toEqual(["A 在「R」上暂停了。"]);
    // 外审 2:正在停下 / 收队还没确认停住 → 照实说,也接着看(不算有结果)
    expect(afterLines(e1, run("stopping"), title)).toEqual([["A 正在停下（「R」），等它确认停住。"], false]);
    expect(afterLines(e1, run("standdown"), title)).toEqual([["A 正在收队（「R」），等它确认停住。"], false]);
  });
});

const q = (r: RenderResult, sel: string) => r.container.ownerDocument.querySelector<HTMLElement>(sel);
const nextOn = (r: RenderResult) => !(r.getByText("下一步") as HTMLButtonElement).disabled;
async function openWiz(props: Partial<Parameters<typeof ArmWizard>[0]> = {}): Promise<RenderResult> {
  const r = render(<ArmWizard say={() => {}} onClose={() => {}} {...props} />);
  await waitFor(() => expect(q(r, "[data-wiz-step=zones]")).not.toBeNull());
  return r;
}
function pickZone(r: RenderResult, z: string) {
  const box = [...r.container.ownerDocument.querySelectorAll<HTMLInputElement>("[data-wiz-zones] input[type=checkbox]")]
    .find((x) => x.parentElement?.textContent?.trim() === z);
  fireEvent.click(box!);
}
function pickRoute(r: RenderResult, id: string) {
  const radio = [...r.container.ownerDocument.querySelectorAll<HTMLInputElement>("input[name=wiz-route]")]
    .find((x) => x.parentElement?.textContent?.includes(id));
  fireEvent.click(radio!);
}
function pickTime(r: RenderResult, which: "keep" | "daily" | "manual") {
  const radios = [...r.container.ownerDocument.querySelectorAll<HTMLInputElement>("input[name=wiz-time]")];
  const x = which === "daily" ? radios.find((e) => e.parentElement?.querySelector("select[data-wiz-from]"))
    : radios.find((e) => e.parentElement?.textContent?.includes(which === "manual" ? "手动" : "保留"));
  fireEvent.click(x!);
}
async function next(r: RenderResult, step: string) {
  fireEvent.click(r.getByText("下一步"));
  await waitFor(() => expect(q(r, `[data-wiz-step=${step}]`)).not.toBeNull());
}
/** 从第 1 步走到「什么时候布防」:选防区 1、选路线 guard-1。 */
async function toTime(r: RenderResult) {
  pickZone(r, "1");
  await next(r, "route");
  pickRoute(r, "guard-1");
  await next(r, "time");
}
/** 再选「手动」走到「谁去巡逻」。 */
async function toWho(r: RenderResult) {
  await toTime(r);
  pickTime(r, "manual");
  await next(r, "who");
}

describe("布防向导", () => {
  it("用户 11-15:每次打开都从第 1 步重新开始 —— 不跳步、不预先打勾、防区不预选;选了防区才能下一步", async () => {
    ready.missing = [];   // 以前「都齐了」直接跳到确认页
    const r = await openWiz();
    const items = [...r.container.ownerDocument.querySelectorAll(".wiz-steps li")];
    expect(items.some((x) => x.classList.contains("done"))).toBe(false);
    expect(items.map((x) => (x.querySelector("button") as HTMLButtonElement).disabled)).toEqual([false, true, true, true, true]);
    const boxes = [...r.container.ownerDocument.querySelectorAll<HTMLInputElement>("[data-wiz-zones] input")];
    expect(boxes.map((x) => x.checked)).toEqual([false]);
    expect(nextOn(r)).toBe(false);
    pickZone(r, "1");
    expect(nextOn(r)).toBe(true);
    await next(r, "route");
    // 笔记本复测 11-15:只有一条能用的路线时默认选上(防区照样不预选)
    expect([...r.container.ownerDocument.querySelectorAll<HTMLInputElement>("input[name=wiz-route]")].map((x) => x.checked)).toEqual([true]);
    expect(nextOn(r)).toBe(true);
    expect(items[0].classList.contains("done")).toBe(true);
  });

  it("走完一遍:A 只许手动派能改成自动派遣;方案是空的直接存;布防后说谁出发了,第 5 步「确认」打勾", async () => {
    let changes = 0;
    const r = await openWiz({ arming: true, onChanged: () => { changes++; } });
    await toWho(r);
    expect(q(r, "[data-wiz-robot=A]")!.textContent).toContain("A 设成只许手动派");
    fireEvent.click(q(r, "[data-wiz-robot=A] button")!);
    await waitFor(() => expect(posted.some((p) => p.url === "/api/robots/A/service" && p.body.manual_only === false)).toBe(true));
    await waitFor(() => expect(q(r, "[data-wiz-robot=A]")!.textContent).toContain("能派"));
    expect(changes).toBe(1);   // 外审 3:改成自动派遣也算改过,背后的页要重读
    await next(r, "confirm");
    const plan = posted.find((p) => p.url === "/api/guard/plan")!.body;
    expect(plan.entries).toEqual([{ route: "guard-1", robot: "", gap_min: 0, shuffle: false, end_standby: true }]);
    expect(plan.base_revision).toBe(0);
    expect(q(r, "[data-wiz-missing]")).toBeNull();
    const items = () => [...r.container.ownerDocument.querySelectorAll(".wiz-steps li")];
    expect(items().map((x) => x.classList.contains("done"))).toEqual([true, true, true, true, false]);
    status = { duty: { id: 1, started_ms: 1 }, runs: [{ entry: 1, robot_id: "B", state: "lap", lap: 1, task_id: "guard-1-x", next_lap_ms: 0, watch_zone: "" }], waiting: {}, zones: [], now_ms: 1 };
    fireEvent.click(r.getByText("现在布防"));
    await waitFor(() => expect(posted.some((p) => p.url === "/api/mode" && p.body.mode === "armed")).toBe(true));
    // 用户 11-15:布防成功了第 5 步也打勾
    await waitFor(() => expect(items()[4].classList.contains("done")).toBe(true));
    expect(items()[4].textContent).toMatch(/^✓ 5\. /);
    // UIUX-036:按方案逐条说哪台在跑哪条、第几圈
    await waitFor(() => expect(q(r, "[data-wiz-after]")!.textContent).toBe("B 正在跑「guard-1」，第 1 圈。"), { timeout: 4000 });
  });

  it("没有防区:停在第一步;「整张图作为一个防区」按地图外框建一个「全场」,建好自动勾上", async () => {
    ready = { ...ready, zones: [], routes: [], missing: ["zones", "route", "plan"] };
    let changes = 0;
    const r = await openWiz({ onChanged: () => { changes++; } });
    expect(r.getByText("这张图上还没有防区。")).toBeTruthy();
    expect(nextOn(r)).toBe(false);
    fireEvent.click(r.getByText("整张图作为一个防区"));
    await waitFor(() => expect(posted.some((p) => p.url.endsWith("/areas"))).toBe(true));
    const a = posted.find((p) => p.url.endsWith("/areas"))!;
    expect(a.url).toBe("/api/maps/estate-1/7/areas");
    expect(a.body).toEqual({ zone: "全场", points: [[-2, -2], [8, -2], [8, 3], [-2, 3]] });
    await waitFor(() => expect(nextOn(r)).toBe(true));
    const box = r.container.ownerDocument.querySelector<HTMLInputElement>("[data-wiz-zones] input")!;
    expect(box.checked).toBe(true);
    expect(changes).toBe(1);   // 外审 3:背后的布置页要重读,不然再存「全场」会盖掉这个
  });

  it("已有几个防区:只用选的那几个生成路线", async () => {
    ready = { ...ready, zones: ["1", "2"], routes: [] };
    const r = await openWiz();
    pickZone(r, "2");
    await next(r, "route");
    fireEvent.click(r.getByText("按选的防区自动生成"));
    await waitFor(() => expect(posted.some((p) => p.url === "/api/guard-routes/generate")).toBe(true));
    const g = posted.find((p) => p.url === "/api/guard-routes/generate")!.body;
    expect((g.zones as { zone: string }[]).map((z) => z.zone)).toEqual(["2"]);
  });

  it("第 3 步不预选:选了才能下一步;时间表本来关着、选「手动」不存", async () => {
    const r = await openWiz();
    await toTime(r);
    expect([...r.container.ownerDocument.querySelectorAll<HTMLInputElement>("input[name=wiz-time]")].some((x) => x.checked)).toBe(false);
    expect(nextOn(r)).toBe(false);
    pickTime(r, "manual");
    await next(r, "who");
    expect(posted.some((p) => p.url === "/api/arming/schedule")).toBe(false);
  });

  it("布防时间:选「每天 21:30 到 06:00」存成启用的时间表(本来没有时间表,不用问)", async () => {
    const r = await openWiz();
    await toTime(r);
    pickTime(r, "daily");
    await next(r, "who");
    const s = posted.find((p) => p.url === "/api/arming/schedule")!.body;
    expect(s.enabled).toBe(true);
    expect(s.slots).toHaveLength(14);
  });

  it("用户 11-15:要覆盖现在的布防时间先问,确认了才存;不确认留在这一步", async () => {
    schedule = { enabled: true, slots: [{ zone: "", day: 0, start: "20:00", end: "24:00" }, { zone: "", day: 1, start: "00:00", end: "05:00" }] };
    const r = await openWiz();
    await toTime(r);
    pickTime(r, "daily");
    fireEvent.click(r.getByText("下一步"));
    await waitFor(() => expect(r.getByText(/会替换现在的布防时间（每周 2 段）：周一 20:00–24:00；周二 00:00–05:00。/)).toBeTruthy());
    expect(posted.some((p) => p.url === "/api/arming/schedule")).toBe(false);
    fireEvent.click(r.getAllByText("保存这个时间").find((el: HTMLElement) => el.tagName === "BUTTON")!);
    await waitFor(() => expect(q(r, "[data-wiz-step=who]")).not.toBeNull());
    expect(posted.some((p) => p.url === "/api/arming/schedule")).toBe(true);
  });

  it("用户 11-15:选「手动」会关掉现在的时间表,也先问", async () => {
    schedule = { enabled: true, slots: [{ zone: "", day: 0, start: "20:00", end: "24:00" }] };
    const r = await openWiz();
    await toTime(r);
    pickTime(r, "manual");
    fireEvent.click(r.getByText("下一步"));
    await waitFor(() => expect(r.getByText(/会关掉现在的布防时间表（每周 1 段）/)).toBeTruthy());
    expect(posted.some((p) => p.url === "/api/arming/schedule")).toBe(false);
  });

  it("「保留现在的布防时间」不存、不问", async () => {
    schedule = { enabled: true, slots: [{ zone: "", day: 0, start: "20:00", end: "24:00" }] };
    const r = await openWiz();
    await toTime(r);
    pickTime(r, "keep");
    await next(r, "who");
    expect(posted.some((p) => p.url.startsWith("/api/arming/schedule"))).toBe(false);
  });

  it("在地图上改防区:就地嵌布置页的防区编辑器,不跳页面、没有别的标签", async () => {
    const before = location.hash;
    const r = await openWiz();
    fireEvent.click(r.getByText("在地图上新画或修改防区"));
    const doc = r.container.ownerDocument;
    await waitFor(() => expect(doc.querySelector(".wiz-editor .layout")).not.toBeNull());
    expect(doc.querySelector(".wiz-editor .ly-tabs")).toBeNull();
    expect(doc.querySelector(".wiz-editor select")).toBeNull();
    expect(doc.querySelector(".wiz-editor")!.textContent).toContain("estate-1 · v7");
    expect(location.hash).toBe(before);
  });

  it("用户 11-15:值守方案里已有别的,换之前列出来问;确认了方案只剩这一条", async () => {
    plan = { ...plan, revision: 3, entries: [
      { id: 1, route: "other", robot: "B", gap_min: 5, shuffle: true, end_standby: false },
      { id: 2, route: "guard-1", robot: "", gap_min: 0, shuffle: true, end_standby: false }] };
    const r = await openWiz();
    await toWho(r);
    fireEvent.change(q(r, "[data-wiz-step=who] select")!, { target: { value: "B" } });
    fireEvent.click(r.getByText("下一步"));
    await waitFor(() => expect(r.getByText("值守方案里已经有：other（B）；guard-1（哪台空就派哪台）。换成「guard-1」（B）吗？")).toBeTruthy());
    expect(posted.some((p) => p.url === "/api/guard/plan")).toBe(false);
    fireEvent.click(r.getAllByText("替换值守方案").find((el: HTMLElement) => el.tagName === "BUTTON")!);
    await waitFor(() => expect(q(r, "[data-wiz-step=confirm]")).not.toBeNull());
    const body = posted.find((p) => p.url === "/api/guard/plan")!.body;
    expect(body.base_revision).toBe(3);
    // 隐藏选项(打乱、每圈回待命点)照这条原来的
    expect(body.entries).toEqual([{ route: "guard-1", robot: "B", gap_min: 0, shuffle: true, end_standby: false }]);
  });

  it("值守方案里就是这一条、人和休息都没变:不问,直接存", async () => {
    plan = { ...plan, entries: [{ id: 1, route: "guard-1", robot: "", gap_min: 0, shuffle: false, end_standby: true }] };
    const r = await openWiz();
    await toWho(r);
    await next(r, "confirm");
    expect(posted.some((p) => p.url === "/api/guard/plan")).toBe(true);
  });

  it("外审 1 #2:改布防时间会马上撤防,先说清楚,确认了才存", async () => {
    preview = { before: { mode: "armed", state: "armed", zones: [{ zone: "1", armed: true }] },
      after: { mode: "home", state: "disarmed", zones: [{ zone: "1", armed: false }] } };
    const r = await openWiz();
    await toTime(r);
    pickTime(r, "daily");
    fireEvent.click(r.getByText("下一步"));
    await waitFor(() => expect(r.getAllByText("保存这个时间").length).toBeGreaterThan(0));
    expect(posted.some((p) => p.url === "/api/arming/schedule")).toBe(false);
    fireEvent.click(r.getAllByText("保存这个时间").find((el: HTMLElement) => el.tagName === "BUTTON")!);
    await waitFor(() => expect(posted.some((p) => p.url === "/api/arming/schedule")).toBe(true));
  });

  it("外审 1 #4:一个防区都不经过的路线不能选,写原因", async () => {
    ready.routes = [...ready.routes, { id: "far", title: "远处", zones: [], in_plan: false }];
    const r = await openWiz();
    pickZone(r, "1");
    await next(r, "route");
    await waitFor(() => expect(q(r, "[data-route-nozone]")?.textContent).toBe("一个防区都不经过，机器人不会去跑"));
    const radios = r.container.ownerDocument.querySelectorAll<HTMLInputElement>("input[name=wiz-route]");
    // 笔记本复测 11-15:只有一条能用就默认选上,能直接下一步
    expect([...radios].map((x) => [x.checked, x.disabled])).toEqual([[true, false], [false, true]]);
    expect((r.getByText("下一步") as HTMLButtonElement).disabled).toBe(false);
  });

  it("外审 2 #2:预演失败不存,说原因", async () => {
    let said = "";
    preview = { __fail: true };
    const r = await openWiz({ say: (s) => { said = s; } });
    await toTime(r);
    pickTime(r, "daily");
    fireEvent.click(r.getByText("下一步"));
    await waitFor(() => expect(said).toContain("预演坏了"));
    expect(posted.some((p) => p.url === "/api/arming/schedule")).toBe(false);
    expect(q(r, "[data-wiz-step=time]")).not.toBeNull();
  });

  it("外审 1 #10:自动生成的编号被别的路线占着(409),换下一个;生成的那条选上", async () => {
    ready = { ...ready, routes: [], missing: ["route", "plan"] };
    taken.add("guard-estate-1-7");
    let changes = 0;
    const r = await openWiz({ onChanged: () => { changes++; } });
    pickZone(r, "1");
    await next(r, "route");
    fireEvent.click(r.getByText("按选的防区自动生成"));
    await waitFor(() => expect(posted.some((p) => p.url === "/api/routes/guard-estate-1-7-2")).toBe(true));
    expect(q(r, ".wiz-editor")).toBeNull();
    await waitFor(() => expect(changes).toBe(1));
  });

  it("只布防、不让机器人巡逻:直接布防,不存方案", async () => {
    let closed = false;
    const r = await openWiz({ arming: true, onClose: () => { closed = true; } });
    fireEvent.click(r.getByText("只布防，不让机器人巡逻"));
    await waitFor(() => expect(closed).toBe(true));
    expect(posted.map((p) => p.url)).toEqual(["/api/mode"]);
  });
});

describe("第二档:向导细节", () => {
  it("走过的步骤打勾、留着序号,能点回去;没走到的点不了", async () => {
    const r = await openWiz({ arming: true });
    await toWho(r);
    const items = [...r.container.ownerDocument.querySelectorAll(".wiz-steps li")];
    expect(items[2].classList.contains("done")).toBe(true);
    expect(items[2].textContent).toMatch(/^✓ 3\. /);
    expect((items[4].querySelector("button") as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(items[0].querySelector("button")!);
    await waitFor(() => expect(q(r, "[data-wiz-step=zones]")).not.toBeNull());
  });

  it("UIUX-041:第 3 步的时间一律 24 小时制(半小时一档的下拉,不用浏览器的时间框)", async () => {
    const r = await openWiz();
    await toTime(r);
    const doc = r.container.ownerDocument;
    const from = doc.querySelector<HTMLSelectElement>("select[data-wiz-from]")!;
    expect(doc.querySelector("input[type=time]")).toBeNull();
    const opts = [...from.options].map((o) => o.textContent);
    expect(opts).toContain("21:30");
    expect(opts).toContain("00:00");
    expect(opts.some((o) => /AM|PM|上午|下午/.test(o ?? ""))).toBe(false);
    expect(doc.querySelector("select[data-wiz-to]")).not.toBeNull();
  });

  it("UIUX-042:机器人一行名字不写两遍;UIUX-043:「去机器人页」带 ?robot=", async () => {
    ready.robots = [{ id: "A", code: "manual_only", why: "A 设成只许手动派" }, { id: "B", code: "offline", why: "B 离线" }];
    const r = await openWiz({ arming: true });
    await toWho(r);
    expect(q(r, "[data-wiz-robot=A]")!.textContent).not.toMatch(/^A\s+A/);
    expect(q(r, "[data-wiz-robot=B] a")!.getAttribute("href")).toBe("#/admin/robots?robot=B");
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

  it("UIUX-039:经理 / 保安(开不了向导)也看到原因,不带向导按钮,写找管理员", async () => {
    const r = render(<PatrolReason />);
    await waitFor(() => expect(r.container.textContent).toContain("布防着，但机器人不会自己巡逻：值守方案里没有给机器人分配防区路线。"));
    expect(r.container.textContent).toContain("请联系管理员");
    expect(r.queryByText("打开布防向导")).toBeNull();
  });

  it("UIUX-039:顶栏布防后提示 —— patrolHint 缺东西时给一句,齐了给空", async () => {
    expect(await patrolHint()).toContain("机器人不会自己巡逻");
    ready.missing = [];
    expect(await patrolHint()).toBe("");
  });
});
