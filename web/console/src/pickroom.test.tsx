// @vitest-environment happy-dom
// I3 11-17(可用性对比):值班页地图只剩 768×296,「派去看一眼」选点时卡片还盖住一块;离机器人 1 m 点下去
// 选中的是机器人。选点时视频收起、地图占满;地图有看得见的放大 / 缩小;选点时点到机器人身上也是选点。
import { cleanup, fireEvent, render, waitFor } from "@testing-library/preact";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { setFetch } from "./api";
import { lang } from "./i18n";
import type { UnitInfo } from "./live";
import { SiteMap } from "./mappage";
import type { Robot } from "./model";

const META = { width: 400, height: 300, m_per_px: 0.05, left_x: -10, top_y: 8 };
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
const robot: Robot = {
  robot_id: "A", active: true, fresh: true, revoked: false, held: null,
  loc: { pose: { x: 2, y: 3, yaw: 0 }, anchored: true, source: "scan_match", sigma_m: 0.12, quality: 0.88, reason: "" },
  status: { online: true, last_seen: 0 },
  capabilities: { tasks: { patrol: { map_id: "m1", map_version: "1" } } },
};
const unit: UnitInfo = { robot, state: "idle", battery: 80, task: "" };

beforeEach(() => {
  lang.value = "en";
  const proto = SVGElement.prototype as unknown as { getScreenCTM?: () => unknown };
  proto.getScreenCTM = function () { return { a: 1, b: 0, c: 0, d: 1, e: 0, f: 0, inverse() { return this; } }; };
  setFetch((async (url: RequestInfo | URL) => {
    const u = String(url);
    if (u.endsWith("/api/maps/m1/1/preview")) return json(META);
    if (u.endsWith("/api/maps/m1/1/areas")) return json({ areas: [] });
    return json({ error: "nope" }, 404);
  }) as never);
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

function scale(c: Element): number {
  const m = /^matrix\(([^)]+)\)$/.exec(c.querySelector("g.map-world")!.getAttribute("transform") ?? "")!;
  const [a, b] = m[1].trim().split(/[\s,]+/).map(Number);
  return Math.hypot(a, b);
}

describe("I3:选点时地图好用", () => {
  it("选点时点到机器人身上:是选点,不是选中机器人", async () => {
    const sel = vi.fn(), pick = vi.fn();
    const { container: c } = render(<SiteMap units={[unit]} p1={[]} now={0} selected={null} onSelect={sel} picking onPickMap={pick} />);
    await waitFor(() => expect(c.querySelector("g.bot")).not.toBeNull());
    fireEvent.click(c.querySelector("g.bot .bot-dot")!);
    expect(sel).not.toHaveBeenCalled();
  });
  it("不在选点:点机器人照样选中它", async () => {
    const sel = vi.fn();
    const { container: c } = render(<SiteMap units={[unit]} p1={[]} now={0} selected={null} onSelect={sel} />);
    await waitFor(() => expect(c.querySelector("g.bot")).not.toBeNull());
    fireEvent.click(c.querySelector("g.bot .bot-dot")!);
    expect(sel).toHaveBeenCalledWith("A");
  });
  it("地图有放大、缩小按钮,按了比例跟着变;全图回去", async () => {
    const { container: c } = render(<SiteMap units={[unit]} p1={[]} now={0} selected={null} onSelect={() => {}} />);
    await waitFor(() => expect(c.querySelector("g.map-world")).not.toBeNull());
    const s0 = scale(c);
    fireEvent.click(c.querySelector('button[data-zoom="in"]')!);
    await waitFor(() => expect(scale(c)).toBeGreaterThan(s0 * 1.2));
    fireEvent.click(c.querySelector('button[data-zoom="out"]')!);
    await waitFor(() => expect(scale(c)).toBeCloseTo(s0, 6));
    expect(c.querySelector('button[data-zoom="in"]')!.getAttribute("aria-label")).toBe("Zoom in");
  });
});
