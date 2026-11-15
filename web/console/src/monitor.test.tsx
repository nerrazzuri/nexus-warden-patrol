// @vitest-environment happy-dom
// 值班(redesign 第二轮 V4 稿):左事件队列分安全 / 设备、本班已关闭、交班留言;中间状态头、地图那一排、画面布局;
// 右机器人、最近活动;底下整班时间轴。
import { cleanup, fireEvent, render, waitFor } from "@testing-library/preact";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { setFetch } from "./api";
import { lang } from "./i18n";
import type { UnitInfo } from "./live";
import type { Alert, RobotState } from "./model";
import { MonitorPage, recentActivity } from "./monitor";
import { shiftSpans } from "./shifttl";
import type { TodayItem } from "./todaypatrols";
import realRobots from "../../../mobile/test/fixtures/site_robots.json";

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
const unit = (id: string, state: RobotState, o: Partial<UnitInfo> = {}): UnitInfo => ({
  robot: { robot_id: id, active: true, fresh: true, revoked: false, held: null, status: { online: state !== "offline", last_seen: 0 } },
  state, battery: 80, task: "", ...o,
});
const alert = (o: Partial<Alert>): Alert => ({
  key: "k1", kind: "intrusion", level: "P1", robot: "A", title: "北区有人闯入", detail: "", first_ms: 1, last_ms: 1, count: 1,
  acked_by: "", acked_ms: null, resolved_ms: null, audience: "intrusion", context: { zone: "北区" }, ...o,
});
const NOW = Date.UTC(2026, 10, 15, 15, 0);   // 本班从 19:00(本地)开始;用相对 NOW 的时刻
let recent: Alert[] = [];
let posts: { url: string; body: unknown }[] = [];
let notes: { text: string }[] = [];

beforeEach(() => {
  lang.value = "zh";
  recent = [];
  notes = [];
  posts = [];
  vi.stubGlobal("IntersectionObserver", undefined);
  try { localStorage.clear(); } catch { /* */ }
  setFetch(((url: string, init?: RequestInit) => {
    if (init?.method === "POST") {
      posts.push({ url, body: JSON.parse(String(init.body ?? "{}")) });
      if (url === "/api/shift-notes") notes.push(JSON.parse(String(init.body)));
      return Promise.resolve(json({}));
    }
    if (url.startsWith("/api/alerts")) return Promise.resolve(json({ alerts: recent }));
    if (url.startsWith("/api/shift-notes")) return Promise.resolve(json({ latest: { id: 1, at_ms: NOW - 3_600_000, author: "olga", text: "停车场有施工车" } }));
    if (url.startsWith("/api/patrols/today")) return Promise.resolve(json({ items: [] }));
    if (url.startsWith("/api/cameras")) return Promise.resolve(json({ cameras: [] }));
    if (url.startsWith("/api/routes?")) return Promise.resolve(json({ revision: 1, timezone: "UTC", routes: [{ id: "loop-test", map_id: "m1", map_version: "1", title: "一楼夜巡" }], schedules: [] }));
    if (url === "/api/robots") return Promise.resolve(json({ robots: [{ ...realRobots.robots[0], robot_id: "B", running: { ...realRobots.robots[0].running, map_id: "m1", map_version: "1" } }] }));
    if (url === "/api/schedule") return Promise.resolve(json({ missions: ["loop-test"] }));
    if (url === "/api/robots/overview") return Promise.resolve(json({ robots: [{ robot_id: "A", online: true }, { robot_id: "B", online: true, map: { id: "m1", version: "1", match: true } }] }));
    if (url.startsWith("/api/robots/B/patrol-plan")) return Promise.resolve(json({ estimate_s: 600, start_ms: 0, queued: false, because: "", loops: 3 }));
    return Promise.resolve(json({}, 404));
  }) as typeof fetch);
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

const page = (alerts: Alert[], role = "guard", units = [unit("A", "patrolling"), unit("B", "charging", { battery: 18 })]) =>
  render(<MonitorPage units={units} alerts={alerts} now={NOW} role={role} me="gina" say={vi.fn()} refresh={vi.fn(async () => {})} onZoom={() => {}} />).container;

describe("值班 · 左栏事件队列", () => {
  it("安全事件(有人、火情)和设备与运营分开;都没有写「没有待处理」", () => {
    const c = page([]);
    expect(Array.from(c.querySelectorAll(".mon-none")).map((x) => x.textContent)).toEqual(["没有待处理", "没有待处理"]);
    cleanup();
    const d = page([alert({}), alert({ key: "k2", kind: "low_battery", level: "P2", audience: "help", robot: "B", title: "B 电量 18%" })]);
    const secs = d.querySelectorAll(".mon-left .mon-sec");
    expect(secs[0].querySelector(".mon-q")!.textContent).toContain("发现入侵");
    expect(secs[1].querySelector(".mon-q")!.textContent).toContain("B 电量 18%");
  });

  it("没人接的 P1 写「没人接」;接了写谁在处理;P2 没人接不写", () => {
    const c = page([alert({}), alert({ key: "k2", level: "P2", audience: "help", kind: "stuck", title: "卡住" })]);
    expect(c.querySelector(".mon-qrow.p1 .mon-qwho")!.textContent).toBe("没人接");
    expect(c.querySelector(".mon-qrow.p2 .mon-qwho")).toBeNull();
    cleanup();
    const d = page([alert({ acked_ms: 5, acked_by: "olga" })]);
    expect(d.querySelector(".mon-qrow.p1 .mon-qwho")!.textContent).toBe("olga 在处理");
  });

  it("技术类(给管理员的)不进值班队列", () => {
    const c = page([alert({ kind: "disk_full", level: "P2", audience: "owner", title: "站点磁盘快满了" })]);
    expect(c.querySelector(".mon-left")!.textContent).not.toContain("站点磁盘快满了");
  });

  it("本班已关闭:时刻、标题、结论;站点自己恢复的写「已恢复」", async () => {
    recent = [
      alert({ key: "c1", resolved_ms: NOW - 60_000, resolved_by: "olga", verdict: "false_alarm", first_ms: NOW - 120_000 }),
      alert({ key: "c2", kind: "robot_offline", audience: "offline", robot: "B", title: "B 离线", resolved_ms: NOW - 30_000, resolved_by: "site:back", first_ms: NOW - 90_000 }),
    ];
    const c = page([]);
    await waitFor(() => expect(c.querySelector(".mon-closed .mon-h")!.textContent).toBe("本班已关闭 2"));
    const rows = Array.from(c.querySelectorAll(".mon-closedlist li")).map((x) => x.textContent);
    expect(rows[0]).toContain("已恢复");
    expect(rows[1]).toContain("误报");
  });

  it("交班留言:上一条 + 写给下一班", async () => {
    const c = page([]);
    await waitFor(() => expect(c.querySelector(".mon-note")!.textContent).toContain("停车场有施工车"));
    fireEvent.input(c.querySelector(".mon-note textarea")!, { target: { value: "B 的电池要换" } });
    fireEvent.click(Array.from(c.querySelectorAll(".mon-note button")).find((b) => b.textContent === "留言")!);
    await waitFor(() => expect(notes).toEqual([{ text: "B 的电池要换" }]));
  });
});

describe("值班 · 中间", () => {
  it("平时写「全场正常」;保安有派去看一眼、临时路线;只读没有", () => {
    const c = page([]);
    expect(c.querySelector(".mon-head h1")!.textContent).toBe("全场正常");
    expect(Array.from(c.querySelectorAll(".mon-head-acts button")).map((b) => b.textContent)).toEqual(["派去看一眼", "临时路线"]);
    cleanup();
    expect(page([], "viewer").querySelectorAll(".mon-head-acts button").length).toBe(0);
  });

  it("地图那一排:全部 / 巡逻路线 / 防区 / 摄像头,选了记住", () => {
    const c = page([]);
    const tabs = Array.from(c.querySelectorAll(".mon-head .seg button"));
    expect(tabs.map((b) => b.textContent)).toEqual(["全部", "巡逻路线", "防区", "摄像头"]);
    fireEvent.click(tabs[2]);
    expect(c.querySelector(".mappage")!.getAttribute("data-preset")).toBe("zones");
    expect(localStorage.getItem("nexwar.mappreset")).toBe("zones");
  });

  it("画面:单 / 双 / 四画面 / 监控墙;监控墙收起地图", () => {
    const c = page([]);
    const tabs = () => Array.from(c.querySelectorAll(".mon-video-h .seg button"));
    expect(tabs().map((b) => b.textContent)).toEqual(["单画面", "双画面", "四画面", "监控墙"]);
    expect(c.querySelectorAll(".mon-tiles.dual > .slot").length).toBe(2);
    fireEvent.click(tabs()[0]);
    expect(c.querySelectorAll(".mon-tiles.single > .slot").length).toBe(1);
    fireEvent.click(tabs()[3]);
    expect(c.querySelector(".mon-map")).toBeNull();
    expect(c.querySelector(".livewall")).not.toBeNull();
  });

  it("全部急停后:写几台已急停,保安有「全部恢复…」", () => {
    const c = page([], "guard", [unit("A", "estop", { robot: { robot_id: "A", active: true, fresh: true, revoked: false, held: { by: "gina" }, status: { online: true, last_seen: 0 } } as never })]);
    expect(c.querySelector(".mon-head h1")!.textContent).toBe("1 台机器人已急停");
    expect(Array.from(c.querySelectorAll(".mon-head-acts button")).map((b) => b.textContent)).toContain("全部恢复…");
  });
});

describe("值班 · 右栏机器人", () => {
  it("每台:名字、状态标识、电量条(低于 30% 黄)、看画面、详情", () => {
    const c = page([]);
    const rows = c.querySelectorAll(".mon-robot");
    expect(rows.length).toBe(2);
    expect(rows[0].querySelector(".mon-state")!.className).toContain("ok");
    expect(rows[1].querySelector(".mon-state")!.className).toContain("idle");
    expect(rows[1].querySelector(".mon-bar")!.className).toContain("low");
    expect(Array.from(rows[0].querySelectorAll(".mon-robot-acts .btn")).slice(0, 2).map((b) => b.textContent)).toEqual(["看画面", "详情"]);
  });
});

describe("最近活动、整班时间轴", () => {
  const p = (o: Partial<TodayItem>): TodayItem => ({ at_ms: 0, kind: "schedule", label: "guard-1", robot: "A", by: "", state: "done", reason: "", end_ms: null, adhoc_id: "", ...o });
  it("最近活动:告警来了、谁接了、谁关了,巡逻开始、走完;新的在前", () => {
    const a = alert({ first_ms: 100, acked_ms: 200, acked_by: "gina", resolved_ms: 300, resolved_by: "gina", verdict: "false_alarm" });
    const xs = recentActivity([a], [p({ at_ms: 50, end_ms: 400, state: "done" })], 0, 1000);
    expect(xs.map((x) => x.text)).toEqual(["A 走完 guard-1", "gina 关闭：发现入侵", "gina 接手：发现入侵", "发现入侵", "A 开始 guard-1"]);
  });

  it("时间轴:巡逻(跑过、在跑)、离线(到恢复或现在)、事件分安全 / 设备;只取本班", () => {
    const { spans, marks } = shiftSpans(["A", "B"],
      [p({ at_ms: 100, end_ms: 200 }), p({ at_ms: 500, state: "running" }), p({ at_ms: 50, state: "next" })],
      [alert({ key: "tech", kind: "disk_80", audience: "owner", level: "P2", first_ms: 420 }), alert({ kind: "robot_offline", audience: "offline", robot: "B", first_ms: 300, resolved_ms: null }), alert({ key: "s", first_ms: 400 }),
        alert({ key: "e", kind: "stuck", audience: "help", level: "P2", first_ms: 450 }), alert({ key: "old", first_ms: -5 })], 0, 1000, 600);
    expect(spans).toEqual([{ robot: "A", from: 100, to: 200, kind: "patrol" }, { robot: "A", from: 500, to: 600, kind: "patrol" },
      { robot: "B", from: 300, to: 600, kind: "offline" }]);
    expect(marks.map((m) => [m.key, m.kind])).toEqual([["s", "security"], ["e", "equipment"]]);
  });
});

describe("右栏机器人(从老值班页搬来)", () => {
  const held = (id: string) => unit(id, "manual", { robot: { robot_id: id, active: true, fresh: true, revoked: false, held: { by: "gina", at_ms: NOW - 60_000 }, status: { online: true, last_seen: 0 } } as never });
  const noHome = (id: string) => unit(id, "idle", { robot: { robot_id: id, active: true, fresh: true, revoked: false, held: null, home_set: false, status: { online: true, last_seen: 0 } } as never });

  it("数据过期:状态写未知", () => {
    const c = page([], "guard", [unit("A", "patrolling", { stale: true })]);
    expect(c.querySelector(".mon-robot")!.textContent).toContain("未知");
    expect(c.querySelector(".mon-robot")!.textContent).not.toContain("巡逻中");
  });

  it("G-estop 全部急停后:页头写谁几点按的;先在页头原地确认(不弹窗)再全部恢复;卡片写急停;只读没有恢复按钮", async () => {
    const c = page([], "guard", [held("A"), held("B"), unit("C", "idle")]);
    expect(c.querySelector(".mon-head h1")!.textContent).toBe("2 台机器人已急停");
    expect(c.querySelector(".mon-head p")!.textContent).toContain("gina");
    expect(c.querySelector('[data-robot="A"] .mon-state')!.textContent).toBe("急停");
    expect(c.querySelector('[data-robot="A"] .mon-state')!.className).toContain("bad");
    fireEvent.click(Array.from(c.querySelectorAll(".mon-head button")).find((b) => b.textContent === "全部恢复…")!);
    expect(posts).toEqual([]);
    expect(document.querySelector(".modal")).toBeNull();
    expect(c.querySelector(".mon-ask")!.textContent).toContain("恢复全部 2 台");
    fireEvent.click(Array.from(c.querySelectorAll(".mon-ask button")).find((b) => b.textContent === "取消")!);
    expect(c.querySelector(".mon-ask")).toBeNull();
    fireEvent.click(Array.from(c.querySelectorAll(".mon-head button")).find((b) => b.textContent === "全部恢复…")!);
    fireEvent.click(c.querySelector(".mon-ask .btn.primary")!);
    await waitFor(() => expect(posts.map((p) => p.url).sort()).toEqual(["/api/robots/A/resume", "/api/robots/B/resume"]));
    cleanup();
    const d = page([], "viewer", [held("A")]);
    expect(d.querySelector(".mon-head h1")!.textContent).toBe("1 台机器人已急停");
    expect(d.querySelectorAll(".mon-head-acts button").length).toBe(0);
  });

  it("P2-08:钉住的那一路刷新后还在", () => {
    const c = page([]);
    fireEvent.click(c.querySelector(".slot-pin")!);
    expect(c.querySelector(".slot-pin")!.getAttribute("aria-pressed")).toBe("true");
    cleanup();
    expect(page([]).querySelector(".slot-pin")!.getAttribute("aria-pressed")).toBe("true");
  });

  it("详情:在中间打开这台的控制(不跳页、不弹窗);再点或点「全场」回来;管理员里面有去机器人设置的链接", async () => {
    const c = page([]);
    fireEvent.click(c.querySelector('[data-robot-more="B"]')!);
    expect(c.querySelector('.mon-robot.on')!.getAttribute("data-robot")).toBe("B");
    expect(c.querySelector('.mon-center .rc')!.getAttribute("data-robot")).toBe("B");
    expect(c.querySelector(".mon-head")).toBeNull();
    expect(c.querySelector(".rc-head a")).toBeNull();
    fireEvent.click(c.querySelector('[data-robot-more="B"]')!);
    expect(c.querySelector(".mon-center .rc")).toBeNull();
    cleanup();
    const d = page([], "admin");
    fireEvent.click(d.querySelector('[data-robot-more="A"]')!);
    expect(d.querySelector(".rc-head a")!.getAttribute("href")).toBe("#/admin/robots?robot=A");
    fireEvent.click(Array.from(d.querySelectorAll(".rc-head button")).find((b) => b.textContent === "全场")!);
    expect(d.querySelector(".mon-head")).not.toBeNull();
  });

  it("W8-09:保安在「详情」里派巡逻:选路线、圈数,写预计多久,派出", async () => {
    const c = page([]);
    fireEvent.click(c.querySelector('[data-robot-more="B"]')!);
    const route = await waitFor(() => { const x = c.querySelector('.rc select[name="route"]') as HTMLSelectElement; expect(x.options.length).toBe(2); return x; });
    fireEvent.change(route, { target: { value: "loop-test" } });
    fireEvent.change(c.querySelector('.rc select[name="loops"]')!, { target: { value: "3" } });
    await waitFor(() => expect(c.querySelector("[data-plan]")!.textContent).toContain("10"));
    fireEvent.click(Array.from(c.querySelectorAll(".rc-dispatch button")).find((b) => b.textContent === "开始巡逻")!);
    await waitFor(() => expect(posts).toContainEqual({ url: "/api/robots/B/patrol", body: { mission_id: "loop-test", loops: 3 } }));
  });

  it("新告警来了:控制视图让位给告警", () => {
    const units = [unit("A", "patrolling"), unit("B", "charging", { battery: 18 })];
    const say = vi.fn();
    const r = render(<MonitorPage units={units} alerts={[]} now={NOW} role="guard" me="gina" say={say} refresh={vi.fn(async () => {})} onZoom={() => {}} />);
    fireEvent.click(r.container.querySelector('[data-robot-more="A"]')!);
    expect(r.container.querySelector(".rc")).not.toBeNull();
    r.rerender(<MonitorPage units={units} alerts={[alert({})]} now={NOW} role="guard" me="gina" say={say} refresh={vi.fn(async () => {})} onZoom={() => {}} />);
    expect(r.container.querySelector(".rc")).toBeNull();
    expect(r.container.querySelector(".inc")).not.toBeNull();
  });

  it("W8-04:在跑几圈的那台写第几圈", () => {
    const c = page([], "guard", [unit("A", "patrolling", { task: "第 2 / 3 圈" }), unit("B", "idle")]);
    expect(c.querySelector('[data-robot="A"] .mon-robot-sub')!.textContent).toContain("第 2 / 3 圈");
  });

  it("W6-01 没原点:页头写哪几台出不了发;保安请联系管理员,管理员去定位页;离线的不算", () => {
    const c = page([], "guard", [noHome("A"), noHome("B"), unit("C", "idle")]);
    expect(c.querySelector(".mon-head h1")!.textContent).toContain("A、B");
    expect(c.querySelector(".mon-head p")!.textContent).toContain("请联系管理员");
    expect(c.querySelector('[data-robot="A"] .mon-robot-sub')!.textContent).toContain("没有原点");
    expect(c.querySelector('[data-robot="C"] .mon-robot-sub')).toBeNull();
    cleanup();
    expect(page([], "admin", [noHome("A")]).querySelector(".mon-head-acts a")!.getAttribute("href")).toBe("#/admin/localization");
    cleanup();
    const off = unit("A", "offline", { robot: { robot_id: "A", active: true, fresh: false, revoked: false, held: null, home_set: false, status: { online: false, last_seen: 0 } } as never });
    expect(page([], "guard", [off]).querySelector(".mon-head h1")!.textContent).not.toContain("出不了发");
  });
});

describe("G-compact 1366×768:右栏收成窄栏、时间轴收成一条(样式按宽度切,结构两份都在)", () => {
  it("窄栏:每台一个小块(名字、电量),点开这台的控制;巡逻 / 活动在原地展开右栏那一段", () => {
    const c = page([]);
    const chips = c.querySelectorAll(".mon-rail .mon-chip");
    expect(Array.from(chips).map((x) => x.textContent)).toEqual(["A80%", "B18%"]);
    expect(chips[1].className).toContain("low");
    fireEvent.click(chips[1]);
    expect(c.querySelector(".mon-center .rc")!.getAttribute("data-robot")).toBe("B");
    const [patrolBtn, actBtn] = Array.from(c.querySelectorAll(".mon-rail .mon-railbtn"));
    fireEvent.click(patrolBtn);
    expect(c.querySelector(".mon-right")!.getAttribute("data-rail")).toBe("patrol");
    fireEvent.click(actBtn);
    expect(c.querySelector(".mon-right")!.getAttribute("data-rail")).toBe("activity");
    fireEvent.click(actBtn);
    expect(c.querySelector(".mon-right")!.hasAttribute("data-rail")).toBe(false);
  });

  it("时间轴:收起时一条(全部机器人的巡逻、事件),「展开时间轴」看每台", () => {
    const c = page([]);
    expect(c.querySelector(".tl-mini")).not.toBeNull();
    expect(c.querySelector(".shifttl")!.className).not.toContain("open");
    fireEvent.click(c.querySelector(".tl-mini .btn")!);
    expect(c.querySelector(".shifttl")!.className).toContain("open");
    expect(c.querySelector(".tl-mini .btn")!.textContent).toBe("收起时间轴");
  });
});

describe("G-multi 同时几件事", () => {
  const two = () => [alert({ key: "n", title: "北门有人", first_ms: NOW - 120_000, last_ms: NOW - 120_000, acked_ms: NOW - 100_000, acked_by: "gina" }),
    alert({ key: "s", title: "南墙有人", robot: "B", first_ms: NOW - 60_000, last_ms: NOW - 60_000, context: { zone: "南区" } })];
  it("两件以上安全事件没点哪一件:中间是总览(地图 + 每件谁管、谁去、下一步);没人管的那件「接手」是唯一的主按钮", () => {
    const c = page(two());
    expect(c.querySelector(".multi")).not.toBeNull();
    expect(c.querySelector(".inc")).toBeNull();
    expect(c.querySelector(".multi-head h1")!.textContent).toBe("同时 2 件事");
    const rows = Array.from(c.querySelectorAll(".multi-table tbody tr"));
    expect(rows.length).toBe(2);
    expect(rows[0].textContent).toContain("北区");
    expect(rows[0].textContent).toContain("gina");
    expect(rows[1].querySelector(".multi-none")!.textContent).toBe("没人接");
    expect(c.querySelectorAll(".multi .btn.primary").length).toBe(1);
    expect(rows[1].querySelector(".btn.primary")!.textContent).toBe("接手");
  });

  it("接手发 ack;「打开」进这一件;点左栏哪一件也进那一件", async () => {
    const c = page(two());
    fireEvent.click(c.querySelector(".multi-table tbody tr:nth-child(2) .btn.primary")!);
    await waitFor(() => expect(posts.map((p) => p.url)).toContain("/api/alerts/s/ack"));
    fireEvent.click(Array.from(c.querySelectorAll(".multi-table tbody tr:first-child button")).find((b) => b.textContent === "打开")!);
    expect(c.querySelector(".inc")!.getAttribute("data-key")).toBe("n");
  });

  it("只读:没有接手按钮,只能打开看", () => {
    const c = page(two(), "viewer");
    expect(c.querySelectorAll(".multi .btn.primary").length).toBe(0);
    expect(Array.from(c.querySelectorAll(".multi-table button")).map((b) => b.textContent)).toEqual(["打开", "打开"]);
  });
});
