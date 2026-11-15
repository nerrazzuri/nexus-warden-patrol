// @vitest-environment happy-dom
// 值班页的「这件事」(redesign 第三期 V4-alarm):有告警中间换成这一件;接手、到场、协助定位在页头;关之前要选结论;
// 只读看进度;经理不派不警示;点「全场地图」回平时。从老值班页(duty.test.tsx)的横幅、详情弹窗那些测试搬过来。
import { cleanup, fireEvent, render, waitFor } from "@testing-library/preact";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { setFetch } from "./api";
import { IncidentView, incidentSteps, responder } from "./incident";
import { lang, t } from "./i18n";
import type { UnitInfo } from "./live";
import type { Alert, RobotState } from "./model";
import { MonitorPage } from "./monitor";

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
const unit = (id: string, state: RobotState, o: Partial<UnitInfo> = {}): UnitInfo => ({
  robot: { robot_id: id, active: true, fresh: true, revoked: false, held: null, status: { online: state !== "offline", last_seen: 0 } },
  state, battery: 80, task: "", ...o,
});
const placed = (id: string, x: number, deter = false): UnitInfo => unit(id, "patrolling", {
  robot: { robot_id: id, active: true, fresh: true, revoked: false, held: null, status: { online: true, last_seen: 0 }, loc: { pose: { x, y: 0, yaw: 0 } },
    capabilities: { tasks: deter ? { deter: { outputs: ["speaker", "strobe"], clips: ["restricted"] } } : {} } } as never,
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
  try { localStorage.clear(); } catch { /* */ }
  setFetch(((url: string, init?: RequestInit) => {
    if (init?.method === "POST") {
      posts.push({ url, body: JSON.parse(String(init.body ?? "{}")) });
      return Promise.resolve(url.endsWith("/resolve") && resolveStatus !== 200 ? json({ error: "没有这条告警" }, resolveStatus) : json({}));
    }
    if (url.startsWith("/api/cameras")) return Promise.resolve(json({ cameras: [{ name: "cam3", zone: "北区" }] }));
    if (url.startsWith("/api/alerts")) return Promise.resolve(json({ alerts: [] }));
    return Promise.resolve(json({}, 404));
  }) as typeof fetch);
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

function page(alerts: Alert[], units = [unit("A", "patrolling"), unit("B", "idle")], role = "guard") {
  const say = vi.fn(), refresh = vi.fn(async () => {});
  const r = render(<MonitorPage units={units} alerts={alerts} now={1000} role={role} me="gina" say={say} refresh={refresh} onZoom={() => {}} />);
  return { ...r, c: r.container, say, refresh };
}
const btn = (c: Element, text: string) => Array.from(c.querySelectorAll("button")).find((b) => b.textContent === text) as HTMLButtonElement | undefined;
const inc = (c: Element) => c.querySelector(".inc")!;

describe("有告警:中间是这件事", () => {
  it("页头写标题、级别、类别、在哪;平时的地图头不出", () => {
    const { c } = page([alert({ kind: "stuck", audience: "help", level: "P2", title: "卡住了", context: { where: "A区" } as never })]);
    expect(inc(c).querySelector(".inc-head p")!.textContent).toContain("P2 · 设备与运营 · A区");
    expect(c.querySelector(".mon-head")).toBeNull();
  });

  it("接手 = 确认收到(蓝底主按钮,一屏一个)", async () => {
    const { c } = page([alert({})]);
    const take = btn(inc(c), "接手")!;
    expect(take.className).toContain("primary");
    expect(c.querySelectorAll(".inc .btn.primary").length).toBe(1);
    fireEvent.click(take);
    await waitFor(() => expect(posts).toContainEqual({ url: "/api/alerts/k1/ack", body: {} }));
  });

  it("没有一点就关:先选结论(确认有人闯入)才能关,带备注", async () => {
    const { c } = page([alert({ acked_ms: 5, acked_by: "gina" })]);
    const close = btn(inc(c), "关闭报警")!;
    expect(close.disabled).toBe(true);
    fireEvent.click(btn(inc(c), "确认有人闯入")!);
    fireEvent.input(inc(c).querySelector(".inc-noteinput")!, { target: { value: "翻墙进来的" } });
    fireEvent.click(btn(inc(c), "关闭报警")!);
    await waitFor(() => expect(posts).toContainEqual({ url: "/api/alerts/k1/resolve", body: { verdict: "intruder", note: "翻墙进来的" } }));
  });

  it("机器人要帮忙的:结论是已处理、误报,没有确认有人", () => {
    const { c } = page([alert({ kind: "stuck", audience: "help", title: "A 被挡住了" })]);
    expect(btn(inc(c), "确认有人闯入")).toBeUndefined();
    expect(btn(inc(c), "已处理")).toBeDefined();
    expect(btn(inc(c), "误报")).toBeDefined();
  });

  it("别人处理掉了:说一次、刷新、回全场", async () => {
    resolveStatus = 404;
    const r = page([alert({})]);
    fireEvent.click(btn(inc(r.c), "误报")!);
    fireEvent.click(btn(inc(r.c), "关闭报警")!);
    await waitFor(() => expect(r.say).toHaveBeenCalledWith("这条报警已被别人处理。"));
    expect(r.say).toHaveBeenCalledTimes(1);
    expect(r.refresh).toHaveBeenCalled();
  });

  it("只读账号:看进度(谁在处理、哪台、还没结论),没有接手、结论按钮", () => {
    const { c } = page([alert({ acked_ms: 5, acked_by: "olga" })], [unit("A", "patrolling")], "viewer");
    expect(btn(inc(c), "接手")).toBeUndefined();
    expect(btn(inc(c), "关闭报警")).toBeUndefined();
    expect(inc(c).querySelector(".inc-disp")!.textContent).toContain("olga 在处理");
    expect(inc(c).querySelector(".inc-disp")!.textContent).toContain("还没有结论");
  });

  it("点左栏另一条看另一条;点全场地图回平时,来了新的又切回来", () => {
    const two = [alert({}), alert({ key: "k2", kind: "stuck", audience: "help", level: "P2", robot: "B", title: "B 卡住了", last_ms: 0 })];
    const r = page(two);
    expect(inc(r.c).getAttribute("data-key")).toBe("k1");
    fireEvent.click(r.c.querySelectorAll(".mon-qrow button")[1]);
    expect(inc(r.c).getAttribute("data-key")).toBe("k2");
    fireEvent.click(btn(inc(r.c), "全场地图")!);
    expect(r.c.querySelector(".inc")).toBeNull();
    expect(r.c.querySelector(".mon-head h1")!.textContent).toContain("发现入侵");
    // 来了新的:只有它一件安全事件就切到它;已经有别的安全事件开着(第 4 期 G-multi)先看总览
    r.rerender(<MonitorPage units={[unit("A", "patrolling")]} alerts={[alert({ key: "k9", first_ms: 9, last_ms: 9 }), ...two.slice(1)]} now={2000} role="guard" say={r.say} refresh={r.refresh} onZoom={() => {}} />);
    expect(inc(r.c).getAttribute("data-key")).toBe("k9");
    fireEvent.click(btn(inc(r.c), "全场地图")!);
    r.rerender(<MonitorPage units={[unit("A", "patrolling")]} alerts={[alert({ key: "k10", first_ms: 10, last_ms: 10 }), alert({ key: "k9", first_ms: 9, last_ms: 9 }), ...two.slice(1)]} now={2000} role="guard" say={r.say} refresh={r.refresh} onZoom={() => {}} />);
    expect(r.c.querySelector(".inc")).toBeNull();
    expect(Array.from(r.c.querySelectorAll(".multi-table tbody tr")).map((x) => x.getAttribute("data-key"))).toEqual(["k9", "k10"]);
  });

  it("技术类(给管理员的)不打开这件事", () => {
    const { c } = page([alert({ kind: "cert_expiring", audience: "owner", level: "P2", title: "证书快到期" })]);
    expect(c.querySelector(".inc")).toBeNull();
  });

  it("迷路了:页头是协助定位,点了回全场地图点位置", async () => {
    const { c } = page([alert({ kind: "loc_lost_paused", audience: "help", level: "P2", robot: "B", title: "B 迷路了" })]);
    fireEvent.click(btn(inc(c), "协助定位")!);
    expect(c.querySelector(".inc")).toBeNull();
  });

  it("有人闯入:放那个防区的摄像头画面", async () => {
    const { c } = page([alert({})]);
    await waitFor(() => expect(inc(c).querySelector(".mon-tile figcaption")?.textContent).toContain("cam3 · 北区"));
  });
});

describe("三组操作和角色", () => {
  const near = alert({ key: "s", robot: "site", kind: "intrusion_unanswered", context: { zone: "北区", pose: { map_id: "m", map_version: "1", x: 0, y: 0 } } });
  it("站点名下的入侵:最近的机器人是 B(10 米),派、警示、通知三组", () => {
    const { c } = page([near], [placed("A", 40), placed("B", 10, true)]);
    expect(responder(near, [placed("A", 40), placed("B", 10)])!.u.robot.robot_id).toBe("B");
    expect(Array.from(c.querySelectorAll(".inc-act h3")).map((h) => h.textContent)).toEqual(["派机器人", "现场警示 · B 的喇叭和警灯", "通知"]);
    expect(btn(inc(c), "派机器人去北区")).toBeDefined();
    expect(c.querySelector(".mon-right .mon-h")!.textContent).toBe("机器人 · 离事发点近的在前");
    expect(c.querySelector(".mon-robot")!.getAttribute("data-robot")).toBe("B");
  });

  it("警示:喊话发 restricted、警灯 30 秒", async () => {
    const { c } = page([near], [placed("B", 10, true)]);
    fireEvent.click(btn(inc(c), "喊话警告")!);
    fireEvent.click(btn(inc(c), "警灯 30 秒")!);
    await waitFor(() => expect(posts.filter((p) => p.url === "/api/robots/B/deter").map((p) => p.body)).toEqual([
      { output: "speaker", on: true, max_s: 60, clip: "restricted" }, { output: "strobe", on: true, max_s: 30 }]));
  });

  it("经理:能接手、关,不能派、不能警示(写由值班保安操作,不放灰按钮)", () => {
    const { c } = page([near], [placed("B", 10, true)], "owner");
    expect(btn(inc(c), "接手")).toBeDefined();
    expect(btn(inc(c), "派机器人去北区")).toBeUndefined();
    expect(btn(inc(c), "喊话警告")).toBeUndefined();
    expect(inc(c).textContent).toContain("由值班保安操作");
    expect(inc(c).querySelectorAll("button[disabled]").length).toBe(1);   // 只有没选结论时的「关闭报警」
  });
});

describe("W74 看见人:到场才能关", () => {
  const seen = (ctx: Record<string, unknown> = {}) => alert({
    key: "p1", kind: "dog_sees_person", title: "机器人看见人了", acked_ms: 5, acked_by: "gina",
    context: { zone: "北区", last_seen: { map_id: "m", map_version: "1", x: 5, y: 6, at_ms: 1000 }, ...ctx } as never,
  });

  it("没到场:页头是已到场,点了发 arrive;结论不出,写到场后才能关", async () => {
    const { c } = page([seen()]);
    expect(btn(inc(c), "确认有人闯入")).toBeUndefined();
    expect(inc(c).querySelector(".inc-disp")!.textContent).toContain("到场后才能关");
    fireEvent.click(btn(inc(c).querySelector(".inc-head")!, "已到场")!);
    await waitFor(() => expect(posts).toContainEqual({ url: "/api/alerts/p1/arrive", body: {} }));
  });

  it("到场了:进度到「已到场」写谁,能选结论", () => {
    const { c } = page([seen({ arrived_by: "张三", arrived_ms: 900 })]);
    const step = inc(c).querySelector('[data-step="incOnSite"]')!;
    expect(step.className).toBe("done");
    expect(step.textContent).toContain("张三");
    expect(btn(inc(c), "确认有人闯入")).toBeDefined();
  });

  it("在跟、去向不明写在页头", () => {
    const { c } = page([seen({ follow: "follow" })]);
    expect(inc(c).querySelector(".inc-head p")!.textContent).toContain("机器人正跟着这个人");
    cleanup();
    const { c: d } = page([seen({ lost_ms: 900 })]);
    expect(inc(d).querySelector(".inc-head p")!.textContent).toContain("去向不明");
  });
});

describe("进度条", () => {
  it("安全事件:发现 / 接手 / 派出 / 关闭;设备类没有派出", () => {
    expect(incidentSteps(alert({})).map((s) => s.key)).toEqual(["incDetected", "incAssigned", "incDispatched", "incClosed"]);
    expect(incidentSteps(alert({ audience: "help", kind: "stuck" })).map((s) => s.key)).toEqual(["incDetected", "incAssigned", "incClosed"]);
    const s = incidentSteps(alert({ acked_ms: 5, acked_by: "gina", resolved_ms: 9, resolved_by: "gina", verdict: "false_alarm" }));
    expect(s.every((x) => x.at != null)).toBe(true);
  });

  it("关了的:从本班已关闭点进来是回放(第五期 G-playback),写结论;经过在右栏,10 分钟内能重新打开;回到实时", async () => {
    const closed = alert({ acked_ms: 5, acked_by: "gina", resolved_ms: 900, resolved_by: "gina", verdict: "false_alarm" });
    setFetch(((url: string, init?: RequestInit) => {
      if (init?.method === "POST") { posts.push({ url, body: JSON.parse(String(init.body ?? "{}")) }); return Promise.resolve(json({})); }
      if (url.startsWith("/api/alerts")) return Promise.resolve(json({ alerts: [closed] }));
      return Promise.resolve(json({ cameras: [] }));
    }) as typeof fetch);
    const { c } = page([]);
    const row = await waitFor(() => { const b = c.querySelector(".mon-closedlist button") as HTMLButtonElement; expect(b).not.toBeNull(); return b; });
    fireEvent.click(row);
    const pb = c.querySelector(".pb")!;
    expect(pb.querySelector(".pb-banner h1")!.textContent).toContain("已关闭：误报");
    expect(pb.querySelector(".pb-tag")!.textContent).toMatch(/^回放 · \d\d:\d\d:\d\d$/);
    expect(pb.querySelector(".pb-banner p")!.textContent).toContain("不是实时画面");
    const hist = c.querySelector(".mon-pbhist")!;
    expect(hist.textContent).toContain("gina");
    expect(c.querySelector(".mon-closedlist li.on")).not.toBeNull();
    fireEvent.click(Array.from(hist.querySelectorAll("button")).find((b) => b.textContent!.startsWith("重新打开"))!);
    await waitFor(() => expect(posts).toContainEqual({ url: "/api/alerts/k1/reopen", body: {} }));
  });

  it("回放:「回到实时」回平时的样子;点时间轴某一刻也是回放,时间轴上画黄线", async () => {
    const closed = alert({ acked_ms: 5, acked_by: "gina", resolved_ms: 900, resolved_by: "gina", verdict: "false_alarm" });
    setFetch(((url: string) => {
      if (url.startsWith("/api/alerts")) return Promise.resolve(json({ alerts: [closed] }));
      return Promise.resolve(json({ cameras: [] }));
    }) as typeof fetch);
    const { c } = page([]);
    const row = await waitFor(() => { const b = c.querySelector(".mon-closedlist button") as HTMLButtonElement; expect(b).not.toBeNull(); return b; });
    fireEvent.click(row);
    expect(c.querySelector(".shifttl .tl-play")).not.toBeNull();
    fireEvent.click(c.querySelector(".pb [data-live]")!);
    expect(c.querySelector(".pb")).toBeNull();
    expect(c.querySelector(".shifttl .tl-play")).toBeNull();
  });
});

describe("报警记录页「去处理」(第五期)", () => {
  it("#/duty?alarm= 带过来的那一件直接打开,哪怕不是最要紧的那件", () => {
    const a1 = alert({ key: "k1", first_ms: 10 }), a2 = alert({ key: "k2", kind: "stuck", audience: "help", level: "P2", title: "B 被挡住", first_ms: 20 });
    const r = render(<MonitorPage openKey="k2" units={[unit("A", "patrolling")]} alerts={[a1, a2]} now={1000} role="guard" me="gina"
      say={() => {}} refresh={async () => {}} onZoom={() => {}} />);
    expect(r.container.querySelector(".inc")!.getAttribute("data-key")).toBe("k2");
  });
});

describe("监控墙", () => {
  it("告警视图切到监控墙:还能点「全场地图」回去(地图那一栏收起来了)", () => {
    const onSite = vi.fn();
    const c = render(<IncidentView a={alert({})} units={[]} alerts={[]} now={1} role="guard" mode={null} cams={[]} layout="wall" onLayout={() => {}}
      say={() => {}} refresh={async () => {}} onSite={onSite} onZoom={() => {}} onFindPose={() => {}} onAreas={() => {}} />).container;
    fireEvent.click(Array.from(c.querySelectorAll(".inc-wall button")).find((b) => b.textContent === t("incSiteMap"))!);
    expect(onSite).toHaveBeenCalled();
  });
});
