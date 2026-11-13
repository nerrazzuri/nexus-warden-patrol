// @vitest-environment happy-dom
// 易用性第 6 轮 W6-08:诊断导出的选择列表 —— 英文界面不露中文原话;巡逻写清时间 · 机器人 · 路线 · 谁派的;用词报警 / 巡逻
import { cleanup, fireEvent, render, waitFor } from "@testing-library/preact";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { setFetch } from "./api";
import { BundlePanel, runLabel } from "./bundlepanel";
import { lang } from "./i18n";

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
const T0 = new Date(2026, 10, 9, 1, 18).getTime();

beforeEach(() => {
  setFetch(((url: string) => {
    if (url.startsWith("/api/alerts")) return Promise.resolve(json({ alerts: [{ key: "B/disk_80#2", kind: "disk_80", robot: "B", level: "P2",
      title: "机器人的发件箱所在的盘即将写满", detail: "", first_ms: T0, last_ms: T0, count: 1 }] }));
    if (url.startsWith("/api/runs")) return Promise.resolve(json({ runs: [
      { id: 10, robot_id: "A", mission: "temp-1794158305644", stamp: "x", first_ms: T0, by: "demo", points: 10 },
      { id: 11, robot_id: "A", mission: "demo-loop", stamp: "y", first_ms: T0, by: "site:schedule", points: 4 },
      { id: 12, robot_id: "B", mission: "temp-17", stamp: "z", first_ms: T0 }] }));
    return Promise.resolve(json({ since_ms: T0, until_ms: T0 + 1, robot: null, scene: "" }));
  }) as typeof fetch);
});
afterEach(cleanup);

const opts = (c: Element, label: string) => Array.from(c.querySelectorAll(`select[aria-label="${label}"] option`)).map((o) => o.textContent);

describe("W6-08 诊断导出的列表", () => {
  it("英文:报警标题按种类;巡逻写时间 · 机器人 · 路线 · 谁派的", async () => {
    lang.value = "en";
    const { container: c } = render(<BundlePanel robots={["A", "B"]} fileName={() => "x"} />);
    const scene = c.querySelector("#bundle-scene") as HTMLSelectElement;
    fireEvent.change(scene, { target: { value: "alert" } });
    await waitFor(() => expect(opts(c, "An alarm").length).toBe(2));
    expect(opts(c, "An alarm")[1]).toBe("11-09 01:18 · B · Robot storage almost full");
    fireEvent.change(scene, { target: { value: "run" } });
    await waitFor(() => expect(opts(c, "A patrol").length).toBe(4));
    expect(opts(c, "A patrol").slice(1)).toEqual([
      "11-09 01:18 · A · temporary route, 10 points · sent by demo",
      "11-09 01:18 · A · demo-loop · by schedule",
      "11-09 01:18 · B · temporary route",
    ]);
  });
  it("中文:用报警、巡逻(不是告警、巡检)", () => {
    lang.value = "zh";
    const { container: c } = render(<BundlePanel robots={[]} fileName={() => "x"} />);
    const text = Array.from(c.querySelectorAll("option, p, label")).map((e) => e.textContent).join(" ");
    expect(text).toContain("某条报警");
    expect(text).toContain("某一趟巡逻");
    expect(text).not.toMatch(/告警|巡检/);
  });
});

// 补测(da0a60ea):「去看看」那一趟在列表里是 task-60a9ef78b711
describe("补测 W6-08 去看看那一趟", () => {
  it("写「去一个点」和谁派的,不露任务号", () => {
    lang.value = "zh";
    const s = runLabel({ id: 2, robot_id: "B", mission: "task-60a9ef78b711", first_ms: 1794307980000, by: "gina", kind: "goto" } as never);
    expect(s).toContain("去一个点");
    expect(s).toContain("gina 派的");
    expect(s).not.toContain("60a9ef78");
  });
});

describe("minor #19:回原点、回待命点那一趟", () => {
  it("写回原点 / 回待命点,不露 standby- 编号", () => {
    lang.value = "zh";
    const home = runLabel({ id: 3, robot_id: "A", mission: "standby-3cf9d8fb1ceb", first_ms: 1794307980000, by: "demo", kind: "home" } as never);
    expect(home).toContain("回原点");
    expect(home).not.toContain("3cf9d8");
    const sb = runLabel({ id: 4, robot_id: "A", mission: "standby-aaaa", first_ms: 1794307980000, kind: "standby" } as never);
    expect(sb).toContain("回待命点");
    expect(runLabel({ id: 5, robot_id: "A", mission: "standby-bbbb", first_ms: 1794307980000 } as never)).toContain("回待命点");
  });
});

describe("minor #23:报警、巡逻下拉能筛", () => {
  it("输几个字只剩对得上的(机器人、标题、日期都能筛)", async () => {
    lang.value = "zh";
    const { container: c } = render(<BundlePanel robots={["A", "B"]} fileName={() => "x"} />);
    const scene = c.querySelector("#bundle-scene") as HTMLSelectElement;
    fireEvent.change(scene, { target: { value: "run" } });
    await waitFor(() => expect(opts(c, "某一趟巡逻").length).toBe(4));
    const box = c.querySelector("input[data-bundle-filter]") as HTMLInputElement;
    fireEvent.input(box, { target: { value: "demo-loop" } });
    expect(opts(c, "某一趟巡逻").slice(1)).toEqual(["11-09 01:18 · A · demo-loop · 按日程"]);
    fireEvent.input(box, { target: { value: "  " } });
    expect(opts(c, "某一趟巡逻").length).toBe(4);
    fireEvent.change(scene, { target: { value: "alert" } });
    await waitFor(() => expect(opts(c, "某条报警").length).toBe(2));
    const box2 = c.querySelector("input[data-bundle-filter]") as HTMLInputElement;
    fireEvent.input(box2, { target: { value: "没有这个" } });
    expect(opts(c, "某条报警").slice(1)).toEqual([]);
    expect(c.textContent).toContain("没有对得上的");
  });
});
