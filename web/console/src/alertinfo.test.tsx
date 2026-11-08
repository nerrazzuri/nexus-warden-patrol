// @vitest-environment happy-dom
// 网页易用性第 1 轮:P0-01 出发前检查没过写清是哪一项、怎么办;P0-03 派出后如实说走没走;
// P0-04 关了的 10 分钟内能撤销;定位页能标原点。
import { cleanup, fireEvent, render, waitFor } from "@testing-library/preact";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AlertDetail } from "./alertdetail";
import { alertAdvice, alertHeadline, reportStart, watchStart } from "./alertinfo";
import { LocPage } from "./advloc";
import { setFetch } from "./api";
import { lang } from "./i18n";
import type { UnitInfo } from "./live";
import type { Alert } from "./model";

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
let listed: Alert[] = [];
let posts: { url: string; body: unknown }[] = [];
let homeStatus = 200;

const alert = (o: Partial<Alert>): Alert => ({
  key: "A/preflight_refused#1", kind: "preflight_refused", level: "P2", robot: "A", title: "出发前检查未通过:地图还未标原点",
  detail: "原文", first_ms: 10_000, last_ms: 10_000, count: 1, acked_by: "", acked_ms: null, resolved_ms: null,
  context: { check: "home" } as never, ...o,
});

beforeEach(() => {
  lang.value = "zh";
  listed = [];
  posts = [];
  homeStatus = 200;
  setFetch(((url: string, init?: RequestInit) => {
    if (init?.method === "POST") {
      posts.push({ url, body: JSON.parse(String(init.body ?? "{}")) });
      if (url.endsWith("/home/here")) return Promise.resolve(json(homeStatus === 200 ? { ack: {} } : { error: "定位不好" }, homeStatus));
      return Promise.resolve(json({}));
    }
    if (url.startsWith("/api/alerts")) return Promise.resolve(json({ alerts: listed }));
    return Promise.resolve(json({}, 404));
  }) as typeof fetch);
});
afterEach(() => cleanup());

const btn = (c: Element, text: string) => Array.from(c.querySelectorAll("button")).find((b) => b.textContent?.includes(text)) as HTMLButtonElement | undefined;
const now = async () => {};

describe("P0-01 出发前检查没过", () => {
  it("标题写是哪一项,办法写去哪儿标原点;英文也一样", () => {
    const a = alert({});
    expect(alertHeadline(a)).toBe("出发前检查未通过，机器人未出发：地图还未标原点");
    expect(alertAdvice(a)).toContain("在这儿标原点");
    lang.value = "en";
    expect(alertHeadline(a)).toBe("Pre-departure check failed, robot did not leave: the map has no origin yet");
    expect(alertHeadline(alert({ context: { check: "battery" } as never }))).toContain("battery too low");
  });

  it("别的警报不改标题、没有办法", () => {
    const a = alert({ kind: "stuck", title: "卡住了", context: undefined });
    expect(alertHeadline(a)).not.toContain("：");
    expect(alertAdvice(a)).toBeNull();
  });
});

describe("P0-03 派出后如实说", () => {
  it("发出以后出了「出发前检查未通过」:说没出发和原因", async () => {
    listed = [alert({ first_ms: Date.now() + 500, last_ms: Date.now() + 500 })];
    const say = vi.fn();
    const r = await reportStart("A", Date.now(), say, { sleep: now, tries: 3 });
    expect(r.state).toBe("refused");
    expect(say.mock.calls[0][0]).toBe("已发给 A，正在确认它能出发…");
    expect(say.mock.calls[1][0]).toContain("A 没有出发：地图还未标原点");
    expect(say.mock.calls[1][0]).not.toContain("已出发");
  });

  it("一直没被拒:说已出发;别的机器人的拒单不算", async () => {
    listed = [alert({ robot: "B", first_ms: Date.now(), last_ms: Date.now() })];
    const say = vi.fn();
    const r = await reportStart("A", Date.now(), say, { sleep: now, tries: 3 });
    expect(r.state).toBe("started");
    expect(say).toHaveBeenLastCalledWith("A 已出发");
  });

  it("早就过去的拒单不算", async () => {
    listed = [alert({ first_ms: Date.now() - 3600_000, last_ms: Date.now() - 3600_000 })];
    expect((await watchStart("A", Date.now(), { sleep: now, tries: 2 })).state).toBe("started");
  });

  it("站点一直问不通:不说出发了", async () => {
    setFetch((() => Promise.reject(new TypeError("network"))) as typeof fetch);
    const say = vi.fn();
    const r = await reportStart("A", Date.now(), say, { sleep: now, tries: 2 });
    expect(r.state).toBe("unknown");
    expect(say).toHaveBeenCalledTimes(1);
  });
});

describe("P0-04 关了能撤销", () => {
  const show = (a: Alert, n: number, role = "guard") => render(
    <AlertDetail a={a} role={role} now={n} units={[]} onClose={() => {}} refresh={async () => {}} say={() => {}} />);

  it("10 分钟内有撤销,点了发 reopen;写着谁关的、备注", async () => {
    const a = alert({ kind: "stuck", resolved_ms: 100_000, resolved_by: "gina", verdict: "false_alarm",
      context: { note: "纸箱" } as never });
    const { container: c } = show(a, 100_000 + 9 * 60_000);
    const m = c.ownerDocument.querySelector(".alertdetail")!;
    expect(m.textContent).toContain("gina");
    expect(m.textContent).toContain("纸箱");
    fireEvent.click(btn(m, "撤销关闭")!);
    await waitFor(() => expect(posts).toContainEqual({ url: `/api/alerts/${encodeURIComponent(a.key)}/reopen`, body: {} }));
  });

  it("过了 10 分钟、只读账号:没有撤销", () => {
    const a = alert({ kind: "stuck", resolved_ms: 100_000, resolved_by: "gina", verdict: "handled" });
    const { container: c } = show(a, 100_000 + 11 * 60_000);
    expect(btn(c.ownerDocument.querySelector(".alertdetail")!, "撤销关闭")).toBeUndefined();
    cleanup();
    const { container: d } = show(a, 100_001, "viewer");
    expect(btn(d.ownerDocument.querySelector(".alertdetail")!, "撤销关闭")).toBeUndefined();
  });

  it("详情里写该做什么", () => {
    const { container: c } = show(alert({}), 20_000);
    expect(c.ownerDocument.querySelector(".ad-do")!.textContent).toContain("在这儿标原点");
  });
});

describe("定位页标原点", () => {
  const unit = (): UnitInfo => ({
    robot: { robot_id: "A", active: true, fresh: true, revoked: false, held: null, status: { online: true, last_seen: 0 },
      loc: { pose: { x: 0, y: 0, yaw: 0 }, anchored: true, sigma_m: 0.05 } as never },
    state: "idle", battery: 90, task: "",
  });

  it("管理员:定位好的有「在这儿标原点」,先确认再发", async () => {
    const { container: c } = render(<LocPage units={[unit()]} alerts={[]} now={0} role="admin" />);
    fireEvent.click(btn(c, "在这儿标原点")!);
    expect(posts).toEqual([]);
    fireEvent.click(btn(c.ownerDocument.querySelector(".modal")!, "在这儿标原点")!);
    await waitFor(() => expect(posts).toContainEqual({ url: "/api/robots/A/home/here", body: {} }));
    await waitFor(() => expect(c.textContent).toContain("已给 A 标好原点"));
  });

  it("保安没有这个按钮", () => {
    const { container: c } = render(<LocPage units={[unit()]} alerts={[]} now={0} role="guard" />);
    expect(btn(c, "在这儿标原点")).toBeUndefined();
  });
});

describe("P1-14 今日巡逻的原因说人话", () => {
  it("出发前检查、半路没电翻成人话,认不出的原样", async () => {
    const { plainReason } = await import("./alertinfo");
    expect(plainReason("起飞前检查未通过: home(地图 'mall' 未标原点,先去标一个换电位); battery(...)")).toBe("出发前检查未通过：地图还未标原点");
    expect(plainReason("电量 22% 低于中止线 25%")).toBe("电量不足，中途返回");
    expect(plainReason("到点没有能派的机器人")).toBe("到点没有能派的机器人");
    lang.value = "en";
    expect(plainReason("起飞前检查未通过: localized(定位当前是 Lost)")).toBe("Pre-departure check failed: localization is not settled");
  });
});

describe("第 2 轮 P0-05:详情里有位置、接手后说下一步", () => {
  const show = (a: Alert) => render(
    <AlertDetail a={a} role="guard" now={1000} units={[]} onClose={() => {}} refresh={async () => {}} say={() => {}} />);
  it("只有地图坐标、没有区域名:写「在地图上标着」并能跳过去", () => {
    const r = show(alert({ kind: "intrusion", context: { pose: { map_id: "m", map_version: "1", x: 1, y: 2 } } }));
    const link = r.container.querySelector("a[data-where-map]") as HTMLAnchorElement;
    expect(link).not.toBeNull();
    expect(link.getAttribute("href")).toBe("#/map");
  });
  it("已接手、还开着:写下一步(派机器人看、看画面或录像、选结论关闭)", () => {
    const r = show(alert({ kind: "intrusion", acked_by: "gina", acked_ms: 500 }));
    expect(r.container.querySelector("[data-next-step]")!.textContent).toContain("选结论");
  });
});
