// @vitest-environment happy-dom
// 网页易用性第 2 轮:连不上站点时,没拿到数据的面板写「读取失败,正在重试」,不能显示成空状态
// (「没有地图」「没有未处理报警」会让人以为地图删了、一切安全);网络回来自己重新拉,不用刷新。
import { cleanup, render, waitFor } from "@testing-library/preact";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { setFetch } from "./api";
import { MonitorPage } from "./monitor";
import { lang } from "./i18n";
import { SiteMap } from "./mappage";
import { TodayPatrols } from "./todaypatrols";

const meta = { width: 400, height: 300, m_per_px: 0.05, left_x: -10, top_y: 8 };
const json = (body: unknown) => new Response(JSON.stringify(body), { headers: { "Content-Type": "application/json" } });
const unit = (id: string) => ({
  robot: {
    robot_id: id, active: true, fresh: true, revoked: false, held: null, status: { online: true, last_seen: 0 },
    loc: { pose: { x: 1, y: 1, yaw: 0 } },
    capabilities: { tasks: { patrol: { map_id: "map-A", map_version: "1" } } },
  },
  state: "idle", battery: 80, task: "",
});

let down: boolean;
beforeEach(() => {
  lang.value = "zh";
  down = true;
  setFetch((async (url: unknown) => {
    if (down) throw new TypeError("network");
    const u = String(url);
    if (u.endsWith("/preview")) return json(meta);
    if (u.endsWith("/areas")) return json({ areas: [] });
    if (u.includes("/patrols/today")) return json({ items: [] });
    if (u.includes("/runviz")) return json({ robots: {} });
    return json({ episodes: [], cameras: [] });
  }) as never);
});
afterEach(() => { cleanup(); vi.useRealTimers(); });

describe("地图面板", () => {
  it("预览拉不到:写读取失败、正在重试,不写没有地图;网络回来自己重拉出图", async () => {
    const r = render(<SiteMap units={[unit("A")] as never} p1={[]} now={0} selected={null} onSelect={() => {}} retryMs={20} />);
    await waitFor(() => expect(r.container.textContent).toContain("读取失败"));
    expect(r.container.textContent).not.toContain("尚无地图");
    down = false;
    await waitFor(() => expect(r.container.querySelector("svg, .mapcanvas, canvas")).not.toBeNull());
  });
});

describe("地图面板:站点上没有这张图", () => {
  it("易用性 37 场景测试:新站点没建图,机器人报的图 404 —— 写「尚无地图」,不写读取失败", async () => {
    setFetch((async (url: unknown) => {
      const u = String(url);
      if (u.endsWith("/preview") || u.endsWith("/areas")) return new Response(JSON.stringify({ error: "地图不存在" }), { status: 404, headers: { "Content-Type": "application/json" } });
      return json({ episodes: [], cameras: [], robots: {} });
    }) as never);
    const r = render(<SiteMap units={[unit("A")] as never} p1={[]} now={0} selected={null} onSelect={() => {}} retryMs={20} />);
    await waitFor(() => expect(r.container.textContent).toContain("尚无地图"));
    expect(r.container.textContent).not.toContain("读取失败");
  });
});

describe("今晚巡逻:值守巡逻", () => {
  it("易用性 37 场景测试:布防后机器人在跑值守巡逻 —— 值班页列出来,不写「今天没有巡逻」", async () => {
    setFetch((async (url: unknown) => {
      const u = String(url);
      if (u.includes("/patrols/today")) return json({ items: [] });
      if (u.includes("/guard/status")) return json({ duty: { id: 1, started_ms: 0 }, now_ms: 0, waiting: {}, zones: [],
        runs: [{ entry: 1, robot_id: "A", state: "lap", lap: 3, task_id: "t", next_lap_ms: 0, watch_zone: "" }] });
      return json({});
    }) as never);
    const r = render(<TodayPatrols guard />);
    await waitFor(() => expect(r.container.querySelector("[data-guard-run]")).not.toBeNull());
    expect(r.container.textContent).toContain("布防值守 · A");
    expect(r.container.textContent).not.toContain("今天没有巡逻");
    cleanup();
    // 没在值守(撤防了):照旧写没有
    setFetch((async (url: unknown) => json(String(url).includes("/guard/status") ? { duty: null, runs: [], now_ms: 0, waiting: {}, zones: [] } : { items: [] })) as never);
    const r2 = render(<TodayPatrols guard />);
    await waitFor(() => expect(r2.container.textContent).toContain("今天没有巡逻"));
  });
});

describe("人名", () => {
  it("易用性 37 场景测试:谁接的、谁派的显示人名(站点在 /api/robots 带 person_names),没起名的照旧显示登录名", async () => {
    const { byText, personNames } = await import("./sitetext");
    personNames.value = { gina: "Gina Tan" };
    try {
      expect(byText("gina")).toBe("Gina Tan");
      expect(byText("bob")).toBe("bob");
      expect(byText("site:schedule")).not.toContain("site");
    } finally { personNames.value = {}; }
  });
});

describe("今天的巡逻", () => {
  it("拉不到:写读取失败,不写今天没有巡逻;回来以后照常", async () => {
    const r = render(<TodayPatrols retryMs={20} />);
    await waitFor(() => expect(r.container.textContent).toContain("读取失败"));
    expect(r.container.textContent).not.toContain("今天没有巡逻");
    down = false;
    await waitFor(() => expect(r.container.textContent).not.toContain("读取失败"));
  });
});

describe("值班页列表", () => {
  it("连不上:报警列表、机器人列表写情况未知,不写没有报警、没有机器人", () => {
    const r = render(<MonitorPage units={[]} alerts={[]} now={1000} role="guard" stale
      say={vi.fn()} refresh={vi.fn(async () => {})} onZoom={() => {}} />);
    const queue = r.container.querySelector(".mon-left")!;
    expect(queue.textContent).toContain("报警情况未知");
    expect(queue.textContent).not.toContain("没有待处理");
    expect(r.container.querySelector(".mon-right")!.textContent).toContain("机器人情况未知");
    expect(r.container.querySelector(".mon-head h1")!.textContent).toContain("状态未知");
  });
});
