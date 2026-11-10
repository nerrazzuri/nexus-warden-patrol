// @vitest-environment happy-dom
// W44 值班页(设计 §4.1):报警横幅三个按钮、结论发对、别人处理掉了横幅消失、技术类不出横幅、迷路了能帮它找位置。
import { cleanup, fireEvent, render, waitFor } from "@testing-library/preact";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { setFetch } from "./api";
import { DutyPage } from "./duty";
import { lang } from "./i18n";
import type { UnitInfo } from "./live";
import type { Alert, RobotState } from "./model";

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

const unit = (id: string, state: RobotState, o: Partial<UnitInfo> = {}): UnitInfo => ({
  robot: { robot_id: id, active: true, fresh: true, revoked: false, held: null, status: { online: state !== "offline", last_seen: 0 } },
  state, battery: 80, task: "", ...o,
});
const alert = (o: Partial<Alert>): Alert => ({
  key: "k1", kind: "intrusion", level: "P1", robot: "A", title: "北区有人闯入", detail: "", first_ms: 1, last_ms: 1, count: 1,
  acked_by: "", acked_ms: null, resolved_ms: null, audience: "intrusion", context: { zone: "北区" }, ...o,
});

let posts: { url: string; body: unknown }[] = [];
let resolveStatus = 200;

beforeEach(() => {
  lang.value = "zh";
  posts = [];
  resolveStatus = 200;
  vi.stubGlobal("IntersectionObserver", undefined);
  setFetch(((url: string, init?: RequestInit) => {
    if (init?.method === "POST") {
      posts.push({ url, body: JSON.parse(String(init.body ?? "{}")) });
      return Promise.resolve(url.endsWith("/resolve") && resolveStatus !== 200 ? json({ error: "没有这条告警" }, resolveStatus) : json({}));
    }
    if (url.startsWith("/api/cameras")) return Promise.resolve(json({ cameras: [{ name: "cam3", zone: "北区", rtsp: true }] }));
    return Promise.resolve(json({}, 404));
  }) as typeof fetch);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function page(alerts: Alert[], units = [unit("A", "patrolling"), unit("B", "idle")], say = vi.fn(), refresh = vi.fn(async () => {})) {
  const r = render(<DutyPage units={units} alerts={alerts} now={1000} role="guard" say={say} refresh={refresh} onZoom={() => {}} />);
  return { ...r, say, refresh };
}
const btn = (c: Element, text: string) => Array.from(c.querySelectorAll("button")).find((b) => b.textContent?.includes(text)) as HTMLButtonElement | undefined;

describe("值班页的报警横幅", () => {
  it("实测查出:站点给的「在哪」(命名区域)写在横幅上", () => {
    const { container: c } = page([alert({ kind: "stuck", audience: "help", robot: "A", title: "卡住了", context: { where: "A区" } as never })]);
    expect(c.querySelector(".banner")!.textContent).toContain("在A区");
  });

  // 网页易用性第 1 轮 P0-04:关警报不能一点就关 —— 横幅上点「详情 / 关闭」,在详情里选结论、可写备注才关
  const closeVia = async (c: Element, verdict: string, note = "") => {
    fireEvent.click(btn(c.querySelector(".banner")!, "详情 / 关闭")!);
    const m = c.ownerDocument.querySelector(".alertdetail")!;
    expect(posts).toEqual([]);
    const go = btn(m, "关闭报警")!;
    expect(go.disabled).toBe(true);
    fireEvent.click(btn(m, verdict)!);
    if (note) fireEvent.input(m.querySelector("input")!, { target: { value: note } });
    fireEvent.click(btn(m, "关闭报警")!);
  };

  it("横幅上没有一点就关的按钮;在详情里选「确认有人」才发 intruder", async () => {
    const { container: c } = page([alert({})]);
    expect(btn(c.querySelector(".banner")!, "确认有人")).toBeUndefined();
    expect(btn(c.querySelector(".banner")!, "已处理")).toBeUndefined();
    await closeVia(c, "确认有人");
    await waitFor(() => expect(posts).toContainEqual({ url: "/api/alerts/k1/resolve", body: { verdict: "intruder", note: "" } }));
  });

  it("我来处理 = 确认收到", async () => {
    const { container: c } = page([alert({})]);
    fireEvent.click(btn(c.querySelector(".banner")!, "我来处理")!);
    await waitFor(() => expect(posts).toContainEqual({ url: "/api/alerts/k1/ack", body: {} }));
  });

  it("误报带备注", async () => {
    const { container: c } = page([alert({})]);
    await closeVia(c, "误报", "风吹倒的纸箱");
    await waitFor(() => expect(posts).toContainEqual({ url: "/api/alerts/k1/resolve", body: { verdict: "false_alarm", note: "风吹倒的纸箱" } }));
  });

  it("机器人需要帮忙的:结论是处理好了、误报,没有确认有人", async () => {
    const { container: c } = page([alert({ kind: "stuck", audience: "help", title: "A 被挡住了" })]);
    fireEvent.click(btn(c.querySelector(".banner")!, "详情 / 关闭")!);
    const m = c.ownerDocument.querySelector(".alertdetail")!;
    expect(btn(m, "确认有人")).toBeUndefined();
    fireEvent.click(btn(m, "已处理")!);
    fireEvent.click(btn(m, "关闭报警")!);
    await waitFor(() => expect(posts).toContainEqual({ url: "/api/alerts/k1/resolve", body: { verdict: "handled", note: "" } }));
  });

  it("别人处理掉了:说一次、刷新、详情关掉", async () => {
    resolveStatus = 404;
    const r = page([alert({})]);
    await closeVia(r.container, "确认有人");
    await waitFor(() => expect(r.say).toHaveBeenCalledWith("这条报警已被别人处理。"));
    expect(r.say).toHaveBeenCalledTimes(1);
    expect(r.refresh).toHaveBeenCalled();
    r.rerender(<DutyPage units={[unit("A", "patrolling")]} alerts={[]} now={2000} role="guard" say={r.say} refresh={r.refresh} onZoom={() => {}} />);
    expect(r.container.querySelector(".banner")).toBeNull();
    expect(r.container.ownerDocument.querySelector(".alertdetail")).toBeNull();
  });

  it("P0-20:只读账号横幅上只有详情,没有处理按钮", () => {
    const { container: c } = render(<DutyPage units={[unit("A", "patrolling")]} alerts={[alert({})]} now={2000} role="viewer"
      say={vi.fn()} refresh={vi.fn(async () => {})} onZoom={() => {}} />);
    const b = c.querySelector(".banner")!;
    expect(btn(b, "我来处理")).toBeUndefined();
    fireEvent.click(btn(b, "详情")!);
    const m = c.ownerDocument.querySelector(".alertdetail")!;
    expect(btn(m, "关闭报警")).toBeUndefined();
    expect(m.textContent).toContain("你的账号只能查看报警");
  });

  it("P0-05:点待处理列表里的一条打开详情", () => {
    const { container: c } = page([alert({})]);
    fireEvent.click(c.querySelector(".alarmlist-main")!);
    expect(c.ownerDocument.querySelector(".alertdetail")).not.toBeNull();
  });

  it("技术类不出横幅", () => {
    const { container: c } = page([alert({ kind: "cert_expiring", audience: "owner", title: "证书快到期" })]);
    expect(c.querySelector(".banner")).toBeNull();
  });

  it("两件报警写还有几件", () => {
    const { container: c } = page([alert({}), alert({ key: "k2", robot: "B", kind: "stuck", audience: "help", last_ms: 0 })]);
    expect(c.querySelector(".banner")!.textContent).toContain("另有 1 件");
  });

  it("迷路了有帮它找位置,点了地图上提示怎么做", async () => {
    const { container: c } = page([alert({ kind: "loc_lost_paused", audience: "help", robot: "B", title: "B 迷路了" })]);
    fireEvent.click(btn(c.querySelector(".banner")!, "协助定位")!);
    await waitFor(() => expect(c.querySelector(".duty-map")!.textContent).toContain("在地图上点击 B 的实际位置"));
  });

  it("有人闯入的现场放那个防区的摄像头", async () => {
    const { container: c } = page([alert({})]);
    await waitFor(() => expect(c.querySelector(".slot img.scene")?.getAttribute("data-src")).toBe("/api/cameras/cam3/live"));
  });
});

describe("W74 看见人:到场才能关", () => {
  const seen = (ctx: Record<string, unknown> = {}) => alert({
    key: "p1", kind: "dog_sees_person", title: "机器人看见人了",
    context: { zone: "北区", last_seen: { map_id: "m", map_version: "1", x: 5, y: 6, at_ms: 1000 }, ...ctx } as never,
  });

  it("没到场:有已到场,点了发 arrive;确认有人、误报都不出", async () => {
    const { container: c } = page([seen()]);
    const b = c.querySelector(".banner")!;
    expect(btn(b, "确认有人")).toBeUndefined();
    expect(btn(b, "误报")).toBeUndefined();
    expect(b.textContent).toContain("到场后才能关");
    fireEvent.click(btn(b, "已到场")!);
    await waitFor(() => expect(posts).toContainEqual({ url: "/api/alerts/p1/arrive", body: {} }));
  });

  it("到场了:写谁到场,详情里能选确认有人、误报", () => {
    const { container: c } = page([seen({ arrived_by: "张三", arrived_ms: 900 })]);
    const b = c.querySelector(".banner")!;
    expect(b.textContent).toContain("张三 已到场");
    expect(btn(b, "已到场")).toBeUndefined();
    fireEvent.click(btn(b, "详情 / 关闭")!);
    const m = c.ownerDocument.querySelector(".alertdetail")!;
    expect(btn(m, "确认有人")).toBeDefined();
    expect(btn(m, "误报")).toBeDefined();
  });

  it("去向不明写在横幅上", () => {
    const { container: c } = page([seen({ lost_ms: 900 })]);
    expect(c.querySelector(".banner")!.textContent).toContain("去向不明");
  });

  it("W74 二期:机器人在跟、跟丢了最后在哪", () => {
    const { container: c } = page([seen({ follow: "follow", person: { x: 1, y: 2, at_ms: 900 } })]);
    expect(c.querySelector(".banner")!.textContent).toContain("机器人正跟着这个人");
    cleanup();
    const { container: d } = page([seen({ follow: "lost", lost_ms: 900, person: { x: 1, y: 2, at_ms: 900, where: "东门附近" } })]);
    const b = d.querySelector(".banner")!.textContent!;
    expect(b).toContain("最后在 东门附近");
    expect(b).not.toContain("正跟着");
  });
});

describe("值班页的地图", () => {
  const META = { width: 100, height: 100, m_per_px: 0.05, left_x: 0, top_y: 5 };
  const onMap = (state: RobotState = "patrolling") => unit("A", state, {
    robot: { robot_id: "A", active: true, fresh: true, revoked: false, held: null, status: { online: true, last_seen: 0 },
      loc: { pose: { x: 1, y: 1, yaw: 0 } }, capabilities: { tasks: { patrol: { map_id: "m", map_version: "1" } } } },
  });
  beforeEach(() => {
    setFetch(((url: string, init?: RequestInit) => {
      if (init?.method === "POST") return Promise.resolve(json({}));
      if (url.endsWith("/preview")) return Promise.resolve(json(META));
      if (url.endsWith("/areas")) return Promise.resolve(json({ areas: [] }));
      return Promise.resolve(json({}, 404));
    }) as typeof fetch);
  });

  it("平时只看,不进点图选位置", async () => {
    const { container: c } = page([], [onMap()]);
    await waitFor(() => expect(c.querySelector(".duty-map svg.map")).not.toBeNull());
    expect(c.querySelector(".duty-map svg.map")!.classList.contains("drawing")).toBe(false);
    expect(c.querySelector(".duty-map")!.textContent).not.toContain("点地图选一个位置");
  });

  it("点了帮它找位置才进点图选位置", async () => {
    const { container: c } = page([alert({ kind: "loc_lost_paused", audience: "help", robot: "A", title: "A 迷路了" })], [onMap()]);
    await waitFor(() => expect(c.querySelector(".duty-map svg.map")).not.toBeNull());
    fireEvent.click(btn(c.querySelector(".banner")!, "协助定位")!);
    await waitFor(() => expect(c.querySelector(".duty-map svg.map")!.classList.contains("drawing")).toBe(true));
  });
});

describe("值班页的状态条", () => {
  it("数据过期_状态写未知", () => {
    const { container: c } = page([], [unit("A", "patrolling", { stale: true })]);
    expect(c.querySelector(".duty-list")!.textContent).toContain("未知");
    expect(c.querySelector(".duty-list")!.textContent).not.toContain("巡逻中");
  });

  it("每台一条,写名字、状态、电量", () => {
    const { container: c } = page([]);
    const rows = c.querySelectorAll(".duty-list .duty-row");
    expect(rows.length).toBe(2);
    expect(rows[0].textContent).toContain("A");
    expect(rows[0].textContent).toContain("80%");
  });
});

describe("网页易用性第 1 轮 P0-02 / P0-06:不该说一切正常的时候", () => {
  it("连不上站点:写状态未知,不写一切正常", () => {
    const { container: c } = render(<DutyPage units={[unit("A", "idle")]} alerts={[]} now={1000} role="guard" stale
      say={vi.fn()} refresh={vi.fn(async () => {})} onZoom={() => {}} />);
    expect(c.textContent).toContain("状态未知");
    expect(c.textContent).not.toContain("一切正常");
    // 第 3 轮 layout N3:报警计数写 ?
    expect(c.querySelector("[data-alarm-count]")!.textContent).toBe("?");
  });

  it("全部急停后:写几台已停止,保安能全部恢复(先确认)", async () => {
    const held = (id: string) => unit(id, "manual", { robot: { robot_id: id, active: true, fresh: true, revoked: false,
      held: { by: "gina" }, status: { online: true, last_seen: 0 } } as never });
    const r = page([], [held("A"), held("B"), unit("C", "idle")]);
    expect(r.container.textContent).toContain("2 台已停止");
    expect(r.container.textContent).not.toContain("一切正常");
    fireEvent.click(btn(r.container, "全部恢复")!);
    expect(posts).toEqual([]);
    fireEvent.click(btn(r.container.ownerDocument.querySelector(".modal")!, "全部恢复")!);
    await waitFor(() => expect(posts.map((p) => p.url).sort()).toEqual(["/api/robots/A/resume", "/api/robots/B/resume"]));
    await waitFor(() => expect(r.say).toHaveBeenCalledWith("已恢复 2 台机器人。"));
  });

  it("只读账号看得到已停止,没有恢复按钮", () => {
    const h = unit("A", "manual", { robot: { robot_id: "A", active: true, fresh: true, revoked: false, held: { by: "x" },
      status: { online: true, last_seen: 0 } } as never });
    const { container: c } = render(<DutyPage units={[h]} alerts={[]} now={1000} role="viewer" say={vi.fn()} refresh={vi.fn(async () => {})} onZoom={() => {}} />);
    expect(c.textContent).toContain("1 台已停止");
    expect(btn(c, "全部恢复")).toBeUndefined();
  });
});

describe("网页易用性第 1 轮 P2-08", () => {
  it("钉住的那一路刷新后还在", () => {
    localStorage.removeItem("nexwar.duty.pins");
    const { container: c } = page([]);
    fireEvent.click(c.querySelector(".slot-pin")!);
    expect(c.querySelector(".slot-pin")!.getAttribute("aria-pressed")).toBe("true");
    cleanup();
    const { container: d } = page([]);
    expect(d.querySelector(".slot-pin")!.getAttribute("aria-pressed")).toBe("true");
    localStorage.removeItem("nexwar.duty.pins");
  });
});

describe("网页易用性第 1 轮 P2-08 详情", () => {
  it("每台一行有「详情」:保安去地图找它,管理员去机器人页打开它", () => {
    const { container: c } = page([]);
    expect(c.querySelector('[data-robot-more="A"]')!.getAttribute("href")).toBe("#/map?robot=A");
    cleanup();
    const { container: d } = render(<DutyPage units={[unit("A", "idle")]} alerts={[]} now={1000} role="admin" say={vi.fn()} refresh={vi.fn(async () => {})} onZoom={() => {}} />);
    expect(d.querySelector('[data-robot-more="A"]')!.getAttribute("href")).toBe("#/admin/robots?robot=A");
  });
});
