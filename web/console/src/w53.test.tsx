// @vitest-environment happy-dom
// W53 网页:今天的巡逻、账号申请审批(W52)、开站清单、使用教程(第一次自动开、关了记下)、拒绝原因按语言说、
// 只看角色、经理能进布防时间页。
import { cleanup, fireEvent, render, waitFor } from "@testing-library/preact";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { setFetch } from "./api";
import { HelpDialog, SetupChecklist, WEB_TOUR } from "./guide";
import { lang, refusalText } from "./i18n";
import { canPatrol, canSchedule } from "./model";
import { pageAllowed, roleLabel } from "./shell";
import { siteHm, TodayPatrols } from "./todaypatrols";
import { Requests } from "./userspage";

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
let posted: { url: string; body: Record<string, unknown> }[];
let reqs: Record<string, unknown>[];
let guide: Record<string, unknown>;

beforeEach(() => {
  lang.value = "zh";
  posted = [];
  reqs = [{ id: "r1", name: "wangxm", display: "王小明", created_ms: Date.now() }];
  guide = { tour: 1, web_tour: 0, setup_hidden: false, skip: [] };
  setFetch(((url: string, init?: RequestInit) => {
    if (init?.method === "POST") {
      const body = JSON.parse(String(init.body ?? "{}"));
      posted.push({ url, body });
      if (url.startsWith("/api/account-requests/")) reqs = [];
      if (url === "/api/me/guide") { guide = { ...guide, ...body }; return Promise.resolve(json(guide)); }
      return Promise.resolve(json({ ok: true }));
    }
    if (url === "/api/patrols/today") {
      return Promise.resolve(json({ items: [
        { at_ms: Date.now(), kind: "schedule", label: "外围一圈", robot: "A", by: "", state: "done", reason: "", end_ms: null, adhoc_id: "" },
        { at_ms: Date.now(), kind: "adhoc", label: "临时路线 3 个点", robot: "B", by: "gina", state: "queued", reason: "", end_ms: null, adhoc_id: "q" },
        { at_ms: Date.now(), kind: "schedule", label: "demo-loop", robot: "A", by: "", state: "missed", reason: "manual_only", end_ms: null, adhoc_id: "" },
      ] }));
    }
    if (url === "/api/account-requests") return Promise.resolve(json({ requests: reqs }));
    if (url === "/api/setup") {
      return Promise.resolve(json({ items: [{ id: "robots", done: true, skipped: false }, { id: "arming", done: false, skipped: (guide.skip as string[]).includes("arming") },
        { id: "zones", done: false, skipped: false }], done: 1, total: 3 }));
    }
    if (url === "/api/me") return Promise.resolve(json({ name: "alice", role: "admin", guide }));
    return Promise.resolve(json({}, 404));
  }) as typeof fetch);
});
afterEach(cleanup);

const btn = (root: Element, text: string) => Array.from(root.querySelectorAll("button")).find((b) => b.textContent?.trim() === text) as HTMLButtonElement;

describe("W53 网页", () => {
  it("今天的巡逻:一行一趟,临时的写谁派的", async () => {
    const { container: c } = render(<TodayPatrols />);
    await waitFor(() => expect(c.querySelectorAll(".today-row").length).toBe(3));
    expect(c.textContent).toContain("完成");
    // 第 12 轮 W12-03:只许手动派、过了点没跑:写原因,不露 manual_only
    expect(c.textContent).toContain("A 只许手动派");
    expect(c.textContent).not.toContain("manual_only");
    expect(c.textContent).toContain("临时路线 3 个点 · B · gina");
    expect(c.textContent).toContain("排队中");
  });

  it("账号申请:权限默认只看,选保安、再输密码批准", async () => {
    const { container: c } = render(<Requests say={() => {}} onDone={() => {}} />);
    await waitFor(() => expect(c.querySelector('tr[data-req="r1"]')).not.toBeNull());
    const sel = c.querySelector("select") as HTMLSelectElement;
    expect(sel.value).toBe("viewer");
    fireEvent.change(sel, { target: { value: "guard" } });
    fireEvent.click(btn(c, "批准"));
    const pw = await waitFor(() => document.querySelector("dialog input[type=password]") as HTMLInputElement);
    fireEvent.input(pw, { target: { value: "my-password" } });
    fireEvent.submit(pw.closest("form")!);
    await waitFor(() => expect(posted.some((p) => p.url === "/api/account-requests/r1/approve")).toBe(true));
    const p = posted.find((x) => x.url === "/api/account-requests/r1/approve")!;
    expect(p.body).toEqual({ role: "guard", confirm_password: "my-password" });
  });

  it("没有申请就不占地方", async () => {
    reqs = [];
    const { container: c } = render(<Requests say={() => {}} onDone={() => {}} />);
    await new Promise((r) => setTimeout(r, 20));
    expect(c.textContent).toBe("");
  });

  it("开站清单:做完的打勾,没做的能「不用了」、能「去做」,能收起", async () => {
    const { container: c } = render(<SetupChecklist />);
    await waitFor(() => expect(c.querySelector('li[data-item="arming"]')).not.toBeNull());
    expect(c.textContent).toContain("开站清单 1/3");
    fireEvent.click(btn(c.querySelector('li[data-item="arming"]')!, "跳过"));
    await waitFor(() => expect(posted.some((p) => p.url === "/api/me/guide" && Array.isArray(p.body.skip))).toBe(true));
    // P1-75:跳过的写明「没设置」、能撤销;「去做」到那一项的标签页
    await waitFor(() => expect(c.querySelector('li[data-item="arming"]')!.textContent).toContain("并没有设置"));
    fireEvent.click(btn(c.querySelector('li[data-item="arming"]')!, "撤销跳过"));
    await waitFor(() => expect(posted.some((p) => p.url === "/api/me/guide" && Array.isArray(p.body.skip) && p.body.skip.length === 0)).toBe(true));
    expect(c.querySelector('li[data-item="zones"] a')!.getAttribute("href")).toBe("#/admin/layout?tab=nogo");
    fireEvent.click(btn(c, "暂不处理"));
    await waitFor(() => expect(posted.some((p) => p.body.setup_hidden === true)).toBe(true));
  });

  it("使用教程:按角色几步,点到最后「好了」记下看过了;常见问题按角色挑", async () => {
    let closed = false;
    const { container: c } = render(<HelpDialog role="guard" onClose={() => { closed = true; }} />, { container: document.body });
    expect(c.textContent).toContain("1 / 5");
    // P2-46:一打开就记下(还没点「完成」)
    await waitFor(() => expect(posted.some((p) => p.url === "/api/me/guide" && p.body.web_tour === WEB_TOUR)).toBe(true));
    for (let i = 0; i < 4; i++) fireEvent.click(btn(c, "下一步"));
    fireEvent.click(btn(c, "完成"));
    expect(closed).toBe(true);
    await waitFor(() => expect(posted.some((p) => p.url === "/api/me/guide" && p.body.web_tour === WEB_TOUR)).toBe(true));
    cleanup();
    const { container: d } = render(<HelpDialog role="guard" onClose={() => {}} />, { container: document.body });
    fireEvent.click(btn(d, "常见问题"));
    expect(d.textContent).toContain("巡逻为何排队");
    expect(d.textContent).not.toContain("如何添加账号");
  });

  it("时刻按站点的钟(外审 #12)", () => {
    const ms = Date.UTC(2027, 0, 15, 8, 0);
    expect(siteHm(ms, 480)).toBe("16:00");
    expect(siteHm(ms, 0)).toBe("08:00");
  });

  it("拒绝原因:英文界面用 reason_en,中文照原话", () => {
    const data = { reason_code: "offline", reason_en: "Offline." };
    lang.value = "en";
    expect(refusalText("A 不在线", data)).toBe("Offline.");
    expect(refusalText("别的", undefined)).toBe("别的");
    lang.value = "zh";
    expect(refusalText("A 不在线", data)).toBe("A 不在线");
  });

  it("角色:只看的有名字、什么都不能派;经理能派巡逻、排日程、进布防时间页,别的管理页进不去", () => {
    expect(roleLabel("viewer")).toBe("roleViewer");
    expect(canPatrol("viewer") || canSchedule("viewer")).toBe(false);
    expect(canPatrol("owner") && canSchedule("owner")).toBe(true);
    expect(pageAllowed("admin/arming", "owner")).toBe(true);
    expect(pageAllowed("admin/users", "owner")).toBe(false);
    expect(pageAllowed("admin/layout", "owner")).toBe(false);
  });
});

describe("网页易用性第 1 轮 P1-68", () => {
  it("帮助先说当前这一页是干什么的", () => {
    const { container: c } = render(<HelpDialog role="admin" page="admin/arming" onClose={() => {}} />, { container: document.body });
    expect(c.querySelector("[data-help-here]")!.textContent).toContain("布防");
  });
});

describe("第 2 轮 admin N11", () => {
  it("没权限的页:帮助说给谁用、找管理员,不介绍这页功能", () => {
    const { container: c } = render(<HelpDialog role="viewer" page="admin/robots" noAccess="管理员" onClose={() => {}} />, { container: document.body });
    expect(c.querySelector("[data-help-here]")).toBeNull();
    expect(c.querySelector("[data-help-noaccess]")!.textContent).toContain("给「管理员」用");
  });
});

// 第 9 轮 W9-05:下一趟排给的机器人蹲着 —— 那一行写出来
describe("W9-05 今天的巡逻:下一趟的机器人没就绪", () => {
  it("写「B 现在没站起来,到点前不好就跑不了」", async () => {
    setFetch(((url: string) => Promise.resolve(url === "/api/patrols/today"
      ? json({ items: [{ at_ms: Date.now() + 60_000, kind: "schedule", label: "route-1", title: "一楼夜巡", robot: "B", by: "", state: "next", reason: "", end_ms: null, adhoc_id: "", not_ready: ["motion"] }] })
      : json({}, 404))) as typeof fetch);
    const { container: c } = render(<TodayPatrols />);
    await waitFor(() => expect(c.querySelector("[data-not-ready]")).not.toBeNull());
    expect(c.querySelector("[data-not-ready]")!.textContent).toContain("B 现在没站起来，到点前不好就跑不了");
    expect(c.textContent).not.toContain("motion");
  });
});

// 易用性第 6 轮 W6-02:排给的那台只许手动派 —— 写「不会跑」和原因,管理员给去改的入口
describe("W6-02 今天的巡逻:不会跑的说清楚", () => {
  const blocked = () => setFetch(((url: string) => Promise.resolve(url === "/api/patrols/today"
    ? json({ items: [{ at_ms: Date.now(), kind: "schedule", label: "demo-loop", robot: "A", by: "", state: "blocked", reason: "manual_only", end_ms: null, adhoc_id: "" }] })
    : json({}, 404))) as typeof fetch);
  it("保安:不会跑 + 只许手动派,没有去改的按钮;不出 manual_only 原话", async () => {
    blocked();
    const { container: c } = render(<TodayPatrols />);
    await waitFor(() => expect(c.querySelectorAll(".today-row").length).toBe(1));
    expect(c.textContent).toContain("不会跑");
    expect(c.textContent).toContain("A 只许手动派");
    expect(c.textContent).not.toContain("manual_only");
    expect(c.textContent).not.toContain("下一次");
    expect(c.querySelector(".today-row a")).toBeNull();
  });
  it("管理员:给去机器人设置改的入口", async () => {
    blocked();
    const { container: c } = render(<TodayPatrols canFix />);
    await waitFor(() => expect(c.querySelector(".today-row a")).not.toBeNull());
    expect(c.querySelector(".today-row a")!.getAttribute("href")).toBe("#/admin/robots?robot=A");
  });
  // 易用性第 7 轮:路线画的那一版跟机器人用的对不上 —— 两边版本写出来(也是到点不会跑的原因)
  it("路线和机器人的地图版本对不上:写出两边的版本,不出 map_mismatch 原话", async () => {
    setFetch(((url: string) => Promise.resolve(url === "/api/patrols/today"
      ? json({ items: [{ at_ms: Date.now(), kind: "schedule", label: "demo-loop", robot: "A", by: "", state: "blocked", reason: "map_mismatch", end_ms: null, adhoc_id: "", map: { route: "11", robot: "12" } }] })
      : json({}, 404))) as typeof fetch);
    const { container: c } = render(<TodayPatrols />);
    await waitFor(() => expect(c.querySelectorAll(".today-row").length).toBe(1));
    expect(c.textContent).toContain("路线画在 v11 上，A 用的是 v12");
    expect(c.textContent).not.toContain("map_mismatch");
  });
});

// 第 8 轮 W8-03 / W8-04:被日程接替的一直巡逻不写「未完成」、不露 preempted;在跑的写第几圈
describe("第 8 轮 今天的巡逻:被接替、第几圈", () => {
  it("被日程接替:写跑了几圈、哪条日程接的,不写未完成和 preempted", async () => {
    setFetch(((url: string) => Promise.resolve(url === "/api/patrols/today"
      ? json({ items: [{ at_ms: Date.now(), kind: "adhoc", label: "loop-test", robot: "B", by: "demo", state: "handed_over", reason: "", end_ms: Date.now(), adhoc_id: "f1", forever: true, handover: { by: "schedule", name: "cut-test", laps: 6 } }] })
      : json({}, 404))) as typeof fetch);
    const { container: c } = render(<TodayPatrols />);
    await waitFor(() => expect(c.querySelectorAll(".today-row").length).toBe(1));
    expect(c.textContent).toContain("已跑 6 圈，由日程 cut-test 接替");
    expect(c.textContent).toContain("被接替");
    expect(c.textContent).not.toContain("未完成");
    expect(c.textContent).not.toContain("preempted");
    expect(c.querySelector(".tdchip")!.className).not.toMatch(/bad/);
  });
  it("在跑的一直巡逻:写「一直巡逻 · 第 3 圈」", async () => {
    setFetch(((url: string) => Promise.resolve(url === "/api/patrols/today"
      ? json({ items: [{ at_ms: Date.now(), kind: "adhoc", label: "loop-test", robot: "B", by: "demo", state: "running", reason: "", end_ms: null, adhoc_id: "f1", forever: true, lap: { n: 3, of: 0 } }] })
      : json({}, 404))) as typeof fetch);
    const { container: c } = render(<TodayPatrols />);
    await waitFor(() => expect(c.querySelectorAll(".today-row").length).toBe(1));
    expect(c.textContent).toContain("一直巡逻 · 第 3 圈");
  });
});

// 第 8 轮 W8-08:路线画在别的版本上时清单说在哪一版;日程的路线跑不了说哪条
describe("第 8 轮 开站清单:路线在别的版本上", () => {
  it("写「有 1 条路线画在 v11 上,机器人在用 v7:在 v7 上重画」和跑不了的日程", async () => {
    setFetch(((url: string) => Promise.resolve(url === "/api/setup"
      ? json({ items: [
        { id: "routes", done: false, skipped: false, elsewhere: [{ route: "demo-loop", map: "m1", version: "11" }], using: [{ map: "m1", version: "7" }] },
        { id: "schedule", done: false, skipped: false, blocked: ["demo-night"] }], done: 0, total: 2 })
      : url === "/api/me" ? json({ name: "alice", role: "admin", guide: { tour: 1, setup_hidden: false, skip: [] } }) : json({}, 404))) as typeof fetch);
    const { container: c } = render(<SetupChecklist />);
    await waitFor(() => expect(c.querySelector('[data-item="routes"]')).not.toBeNull());
    expect(c.querySelector('[data-item="routes"]')!.textContent).toContain("有 1 条路线（demo-loop）画在 v11 上，机器人在用 v7：在 v7 上重画");
    expect(c.querySelector('[data-item="schedule"]')!.textContent).toContain("日程 demo-night 要跑的路线跑不了");
  });
});

// minor #21(liang-d5 W7):标原点时自动加了待命点,清单打勾 —— 写明待命点就是原点
describe("minor #21 开站清单:待命点就是原点", () => {
  it("写「A 的待命点就是原点（标原点时自动加的）」", async () => {
    setFetch(((url: string) => Promise.resolve(url === "/api/setup"
      ? json({ items: [{ id: "standby", done: true, skipped: false, robots: [], at_home: ["A"] }], done: 1, total: 1 })
      : url === "/api/me" ? json({ name: "alice", role: "admin", guide: { tour: 1, setup_hidden: false, skip: [] } }) : json({}, 404))) as typeof fetch);
    const { container: c } = render(<SetupChecklist />);
    await waitFor(() => expect(c.querySelector('[data-item="standby"]')).not.toBeNull());
    expect(c.querySelector('[data-item="standby"]')!.textContent).toContain("A 的待命点就是原点（标原点时自动加的）");
  });
});

// minor #40:登记了还没报在用哪张图的机器人 —— 原点、待命点不打勾,写明是哪几台
describe("minor #40 开站清单:没报地图的机器人", () => {
  it("写「B 还没报在用哪张图」", async () => {
    setFetch(((url: string) => Promise.resolve(url === "/api/setup"
      ? json({ items: [{ id: "home", done: false, skipped: false, robots: [], no_map: ["B"] }], done: 0, total: 1 })
      : url === "/api/me" ? json({ name: "alice", role: "admin", guide: { tour: 1, setup_hidden: false, skip: [] } }) : json({}, 404))) as typeof fetch);
    const { container: c } = render(<SetupChecklist />);
    await waitFor(() => expect(c.querySelector('[data-item="home"]')).not.toBeNull());
    expect(c.querySelector('[data-item="home"]')!.textContent).toContain("B 还没报在用哪张图");
  });
});

// 第 8 轮 W8-11:今天的巡逻写路线显示名
describe("第 8 轮 今天的巡逻写显示名", () => {
  it("有显示名写显示名", async () => {
    setFetch(((url: string) => Promise.resolve(url === "/api/patrols/today"
      ? json({ items: [{ at_ms: Date.now(), kind: "schedule", label: "route-1", title: "一楼夜巡", robot: "A", by: "", state: "later", reason: "", end_ms: null, adhoc_id: "" }] })
      : json({}, 404))) as typeof fetch);
    const { container: c } = render(<TodayPatrols />);
    await waitFor(() => expect(c.querySelectorAll(".today-row").length).toBe(1));
    expect(c.textContent).toContain("一楼夜巡 · A");
    expect(c.textContent).not.toContain("route-1");
  });
});

