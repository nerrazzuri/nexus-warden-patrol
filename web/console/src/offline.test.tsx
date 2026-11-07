// @vitest-environment happy-dom
// 网页易用性第 2 轮:连不上站点时,没拿到数据的面板写「读取失败,正在重试」,不能显示成空状态
// (「没有地图」「没有未处理报警」会让人以为地图删了、一切安全);网络回来自己重新拉,不用刷新。
import { cleanup, render, waitFor } from "@testing-library/preact";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { setFetch } from "./api";
import { DutyPage } from "./duty";
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
    const r = render(<DutyPage units={[]} alerts={[]} now={1000} role="guard" stale
      say={vi.fn()} refresh={vi.fn(async () => {})} onZoom={() => {}} />);
    const alarms = r.container.querySelector(".duty-alarms")!;
    expect(alarms.textContent).toContain("报警情况未知");
    expect(alarms.textContent).not.toContain("没有待处理");
    expect(r.container.querySelector(".duty-left")!.textContent).toContain("机器人情况未知");
  });
});
