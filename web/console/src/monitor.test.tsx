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
let notes: { text: string }[] = [];

beforeEach(() => {
  lang.value = "zh";
  recent = [];
  notes = [];
  vi.stubGlobal("IntersectionObserver", undefined);
  try { localStorage.clear(); } catch { /* */ }
  setFetch(((url: string, init?: RequestInit) => {
    if (init?.method === "POST") {
      if (url === "/api/shift-notes") notes.push(JSON.parse(String(init.body)));
      return Promise.resolve(json({}));
    }
    if (url.startsWith("/api/alerts")) return Promise.resolve(json({ alerts: recent }));
    if (url.startsWith("/api/shift-notes")) return Promise.resolve(json({ latest: { id: 1, at_ms: NOW - 3_600_000, author: "olga", text: "停车场有施工车" } }));
    if (url.startsWith("/api/patrols/today")) return Promise.resolve(json({ items: [] }));
    if (url.startsWith("/api/cameras")) return Promise.resolve(json({ cameras: [] }));
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
