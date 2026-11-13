// @vitest-environment happy-dom
// W44 第一期:新外壳(顶栏、路由、主题、管理员的临时提醒页)。真的把 Console 渲染出来看。
import { cleanup, fireEvent, render, waitFor } from "@testing-library/preact";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { setFetch } from "./api";
import type { Me } from "./app";
import { Console } from "./console";
import { lang } from "./i18n";
import type { Alert } from "./model";
import { pageAllowed, pageScheme, readRoute, roleLabel, schemeFor, SideNav, TopBar } from "./shell";
import { applyTheme } from "./theme";

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

const alert = (o: Partial<Alert>): Alert => ({
  key: "k", kind: "stuck", level: "P1", robot: "A", title: "t", detail: "", first_ms: 1, last_ms: 1, count: 1,
  acked_by: "", acked_ms: null, resolved_ms: null, ...o,
});

let alerts: Alert[] = [];
let posted: { url: string; body: unknown }[] = [];
let drill: { active: boolean; until_ms: number | null; by: string } = { active: false, until_ms: null, by: "" };

function fakeSite() {
  setFetch(((url: string, init?: RequestInit) => {
    if (init?.method === "POST") {
      posted.push({ url, body: JSON.parse(String(init.body ?? "{}")) });
      return Promise.resolve(json({}));
    }
    if (url.startsWith("/api/robots")) return Promise.resolve(json({ robots: [] }));
    if (url.startsWith("/api/alerts")) return Promise.resolve(json({ alerts }));
    if (url.startsWith("/api/mode")) return Promise.resolve(json({ mode: "armed", until_ms: null }));
    if (url.startsWith("/api/deterrence")) return Promise.resolve(json({ sessions: [] }));
    if (url.startsWith("/api/watch/summary")) return Promise.resolve(json({ robots: [] }));
    if (url.startsWith("/api/alert-test")) return Promise.resolve(json(drill));
    return Promise.resolve(json({}, 404));
  }) as typeof fetch);
}

const me = (role: string): Me => ({ name: "wang", role, display_name: "王", site_name: "翠湖庄园" });

beforeEach(() => {
  lang.value = "zh";
  alerts = [];
  posted = [];
  drill = { active: false, until_ms: null, by: "" };
  location.hash = "";
  fakeSite();
});
afterEach(() => {
  cleanup();
  applyTheme("light");
});

describe("外壳的纯函数", () => {
  it("实测查出:没权限的页面写清楚,不给空白", () => {
    expect(pageAllowed("admin/users", "admin")).toBe(true);
    expect(pageAllowed("admin/users", "engineer")).toBe(false);
    expect(pageAllowed("admin/users", "owner")).toBe(false);
    expect(pageAllowed("admin/home", "engineer")).toBe(true);
    expect(pageAllowed("admin/home", "guard")).toBe(false);
    expect(pageAllowed("duty", "guard")).toBe(true);
  });

  it("角色的界面名字", () => {
    expect(roleLabel("admin")).toBe("roleOwner");
    expect(roleLabel("guard")).toBe("roleGuard");
    expect(roleLabel("owner")).toBe("roleFamily");
    expect(roleLabel("engineer")).toBe("roleEngineer");
  });
  it("W60 全站默认深色(管理页不再换浅色)", () => {
    for (const p of ["duty", "live", "map", "recordings", "alarms", "admin/users", "admin/system"] as const) expect(pageScheme(p)).toBe("dark");
  });
  it("个人选了就按个人的,选「跟随系统」就跟系统", () => {
    expect(schemeFor("duty", "auto", false)).toBe("dark");
    expect(schemeFor("admin/users", "auto", false)).toBe("dark");
    expect(schemeFor("duty", "light", true)).toBe("light");
    expect(schemeFor("admin/users", "dark", false)).toBe("dark");
    expect(schemeFor("duty", "system", false)).toBe("light");
    expect(schemeFor("admin/users", "system", true)).toBe("dark");
  });
  it("老地址跳新地址", () => {
    expect(readRoute("#/reports").page).toBe("admin/reports");
    expect(readRoute("#/localization").page).toBe("admin/localization");
    expect(readRoute("#/admin/notices").page).toBe("admin/home");
    expect(readRoute("#/admin/lists").page).toBe("admin/access");
    expect(readRoute("").page).toBe("duty");
    expect(readRoute("#/nonsense").page).toBe("duty");
    expect(readRoute("#/recordings?robot=A&t=5")).toMatchObject({ page: "recordings", robot: "A", at: 5 });
  });
});

describe("新外壳", () => {
  it("默认进值班页", async () => {
    const c = render(<Console me={me("guard")} onOut={() => {}} />);
    await waitFor(() => expect(c.container.querySelector('main[data-page="duty"]')).not.toBeNull());
  });

  const groups = (c: Element) => Array.from(c.querySelectorAll(".sidenav .navgroup-title")).map((x) => x.textContent);
  const hrefs = (c: Element) => Array.from(c.querySelectorAll(".sidenav a")).map((x) => x.getAttribute("href"));

  it("W60 左侧导航:保安只有值班一组(没有管理功能)", () => {
    const g = render(<Console me={me("guard")} onOut={() => {}} />);
    expect(groups(g.container)).toEqual(["值班"]);
    expect(hrefs(g.container)).toEqual(["#/duty", "#/live", "#/map", "#/alarms", "#/recordings"]);
    expect(g.container.querySelector(".topbar .tabsnav")).toBeNull();
  });

  it("W60 管理员:值班、管理、系统三组,高级默认收着、点开才有", () => {
    const a = render(<Console me={me("admin")} onOut={() => {}} />);
    expect(groups(a.container)).toEqual(["值班", "管理", "系统", "高级"]);
    expect(hrefs(a.container)).toEqual(expect.arrayContaining(["#/admin/robots", "#/admin/layout", "#/admin/arming", "#/admin/access",
      "#/admin/users", "#/admin/reports", "#/admin/home"]));
    expect(hrefs(a.container)).not.toContain("#/admin/system");
    fireEvent.click(Array.from(a.container.querySelectorAll(".sidenav .navgroup-title")).find((x) => x.textContent === "高级")!);
    expect(hrefs(a.container)).toEqual(expect.arrayContaining(["#/admin/maps", "#/admin/localization", "#/admin/diag", "#/admin/upgrade", "#/admin/system"]));
  });

  it("在高级的页里,高级是展开的;顶栏标题写组名和页名", () => {
    location.hash = "#/admin/system";
    const a = render(<Console me={me("admin")} onOut={() => {}} />);
    expect(a.container.querySelector('.sidenav a[href="#/admin/system"]')!.getAttribute("aria-current")).toBe("page");
    expect(a.container.querySelector(".topbar .pagetitle")!.textContent).toBe("高级系统");   // P2-19:组名跟侧栏一样
  });

  it("工程师看得到管理、看不到用户", () => {
    const e = render(<Console me={me("engineer")} onOut={() => {}} />);
    expect(hrefs(e.container)).not.toContain("#/admin/users");
    expect(hrefs(e.container)).toContain("#/admin/robots");
  });

  it("W60 经理:机器人(只看)、布防时间、报表;进得去(原来布防时间进去是空白页)", () => {
    location.hash = "#/admin/arming";
    const f = render(<Console me={me("owner")} onOut={() => {}} />);
    expect(groups(f.container)).toEqual(["值班", "管理", "系统"]);
    expect(hrefs(f.container).filter((h) => h!.startsWith("#/admin/"))).toEqual(["#/admin/robots", "#/admin/arming", "#/admin/reports"]);
    expect(f.container.querySelector(".adminbody")).not.toBeNull();
    expect(f.container.querySelector(".noaccess")).toBeNull();
  });

  it("没权限的管理页写清楚,不渲染页面", () => {
    location.hash = "#/admin/users";
    const g = render(<Console me={me("guard")} onOut={() => {}} />);
    expect(g.container.querySelector(".noaccess")).not.toBeNull();
    expect(g.container.querySelector(".adminbody")).toBeNull();
  });

  it("顶栏没有语言按钮,在用户菜单里", () => {
    const c = render(<Console me={me("guard")} onOut={() => {}} />);
    const bar = c.container.querySelector(".topbar")!;
    expect(Array.from(bar.querySelectorAll("button")).some((b) => b.textContent === "EN")).toBe(false);
    fireEvent.click(bar.querySelector(".usermenu > button")!);
    expect(Array.from(bar.querySelectorAll("button")).some((b) => b.textContent === "EN")).toBe(true);
  });

  it("W58 用户菜单里能打开第三方软件声明(P2-22:在对话框里看)", async () => {
    const urls: string[] = [];
    vi.stubGlobal("fetch", (u: string) => { urls.push(u); return Promise.resolve(new Response("MIT License\nfoo", { status: 200 })); });
    const c = render(<Console me={me("guard")} onOut={() => {}} />);
    const bar = c.container.querySelector(".topbar")!;
    fireEvent.click(bar.querySelector(".usermenu > button")!);
    const b = Array.from(bar.querySelectorAll("button")).find((x) => x.textContent === "第三方软件声明")!;
    fireEvent.click(b);
    await waitFor(() => expect(document.querySelector("[data-notices]")!.textContent).toContain("MIT License"));
    expect(urls).toContain("/assets/third-party-notices.txt");
    vi.unstubAllGlobals();
  });

  it("W6-05(用户 11-11 改了):布防状态点开切模式,选了先弹确认,不直接切", async () => {
    const c = render(<Console me={me("guard")} onOut={() => {}} />);
    await waitFor(() => expect(c.container.querySelector(".armstate")!.textContent).toContain("布防"));
    const s = c.container.querySelector("button.armstate") as HTMLButtonElement;
    expect(s).not.toBeNull();
    fireEvent.click(s);
    fireEvent.click(Array.from(c.container.querySelectorAll("[data-mode-menu] button")).find((b) => b.textContent === "留守")!);
    await waitFor(() => expect(document.body.textContent).toContain("留守"));
    expect(document.querySelector(".modal, dialog")).not.toBeNull();
  });

  it("报警数只数给保安的", async () => {
    alerts = [alert({ key: "a", kind: "stuck", audience: "help" }), alert({ key: "b", kind: "cert_expiring", level: "P2", audience: "owner" })];
    const c = render(<Console me={me("guard")} onOut={() => {}} />);
    await waitFor(() => expect(c.container.querySelector(".alarmcount")!.textContent).toContain("1"));
  });

  it("W60 切到管理页还是深色(真的挂上)", async () => {
    location.hash = "#/map";
    const c = render(<Console me={me("admin")} onOut={() => {}} />);
    await waitFor(() => expect(document.documentElement.dataset.theme).toBe("dark"));
    location.hash = "#/admin/users";
    window.dispatchEvent(new HashChangeEvent("hashchange"));
    await new Promise((r) => setTimeout(r, 20));
    expect(document.documentElement.dataset.theme).toBe("dark");
    c.unmount();
  });

  it("现场概况只列技术类的要你处理的事,保安进不去", async () => {
    alerts = [alert({ key: "a", kind: "cert_expiring", level: "P2", title: "证书快到期", audience: "owner" }),
      alert({ key: "b", kind: "stuck", title: "卡住了", audience: "help" })];
    location.hash = "#/admin/notices";
    const a = render(<Console me={me("admin")} onOut={() => {}} />);
    await waitFor(() => expect(a.container.querySelector(".home-todo")!.textContent).toContain("证书"));
    expect(a.container.querySelector(".home-todo")!.textContent).not.toContain("卡住了");
    fireEvent.click(Array.from(a.container.querySelectorAll(".home-todo button")).find((b) => b.textContent === "已处理")!);
    await waitFor(() => expect(posted).toContainEqual({ url: "/api/alerts/a/resolve", body: { verdict: "handled" } }));
    cleanup();
    const g = render(<Console me={me("guard")} onOut={() => {}} />);
    expect(g.container.querySelector(".home")).toBeNull();
  });
});


// 易用性第 6 轮 W6-05(用户 11-11:保安也能撤防):顶栏的布防状态点开就能切 —— 布防、留守、临时撤防
describe("W6-05 顶栏点布防状态切模式", () => {
  const mode = { mode: "armed", label: "布防", source: "manual", state: "armed" } as never;
  const bar = (role: string, onMode = vi.fn(), stale = false) => ({ onMode, c: render(<TopBar me={me(role)} page="duty" mode={mode} alarms={0} now={0} pref="system"
    onPref={() => {}} onStop={() => {}} onSignOut={() => {}} onSay={() => {}} onMode={onMode} stale={stale} />).container });
  it("保安:点开有布防、留守、临时撤防,点留守交给外壳去确认", () => {
    lang.value = "zh";
    const { c, onMode } = bar("guard");
    fireEvent.click(c.querySelector("button.armstate")!);
    const menu = c.querySelector("[data-mode-menu]")!;
    const items = Array.from(menu.querySelectorAll("button")).map((b) => b.textContent);
    expect(items).toEqual(["布防", "留守", "临时撤防"]);
    expect((menu.querySelector("button[aria-pressed=true]") as HTMLButtonElement).textContent).toBe("布防");
    fireEvent.click(Array.from(menu.querySelectorAll("button")).find((b) => b.textContent === "留守")!);
    expect(onMode).toHaveBeenCalledWith("home");
    expect(c.querySelector("[data-mode-menu]")).toBeNull();
  });
  it("只看的:不是按钮,悬停说只能看", () => {
    lang.value = "zh";
    const { c } = bar("viewer");
    expect(c.querySelector("button.armstate")).toBeNull();
    expect(c.querySelector(".armstate")!.getAttribute("title")).toContain("只能看");
  });
  it("连不上站点:不给切", () => {
    lang.value = "zh";
    const { c } = bar("admin", vi.fn(), true);
    expect((c.querySelector("button.armstate") as HTMLButtonElement).disabled).toBe(true);
  });
});

describe("第 2 轮 P1-03:顶栏日期不会读反", () => {
  it("中英文都写 月-日", () => {
    const now = new Date(2026, 10, 8, 2, 4).getTime();
    for (const l of ["en", "zh"] as const) {
      lang.value = l;
      const r = render(<TopBar me={me("admin")} page="duty" mode={null} alarms={0} now={now} pref="system" onPref={() => {}} onStop={() => {}} onSignOut={() => {}} onSay={() => {}} />);
      expect(r.container.querySelector(".clock-date")!.textContent).toBe("11-08");
      cleanup();
    }
  });

  it("第 5 轮:按站点时区走,不按浏览器的", () => {
    const now = Date.UTC(2026, 10, 8, 18, 30);                 // 上海 11-09 02:30
    const mode = { mode: "armed", timezone: "Asia/Shanghai" } as never;
    const r = render(<TopBar me={me("admin")} page="duty" mode={mode} alarms={0} now={now} pref="system" onPref={() => {}} onStop={() => {}} onSignOut={() => {}} onSay={() => {}} />);
    expect(r.container.querySelector(".clock")!.textContent).toContain("11-09");
    expect(r.container.querySelector(".clock")!.textContent).toContain("02:30");
  });
});

describe("第 2 轮 duty N10 / N11:顶栏", () => {
  const mode = { mode: "armed", label: "布防", source: "manual", state: "armed" } as never;
  const bar = (o: { page?: string; held?: number; stale?: boolean }) => render(<TopBar me={me("guard")} page={(o.page ?? "map") as never} mode={mode} alarms={0} now={0}
    pref="system" onPref={() => {}} onStop={() => {}} onSignOut={() => {}} onSay={() => {}} held={o.held} stale={o.stale} />).container;
  it("有叫停的:别的页也显示「n 台已叫停 · 去恢复」,点了去总览;总览本页不重复", () => {
    lang.value = "zh";
    const c = bar({ held: 2 });
    expect(c.querySelector("[data-held-chip]")!.textContent).toBe("2 台已叫停 · 去恢复");
    expect(c.querySelector("[data-held-chip]")!.getAttribute("href")).toBe("#/duty");
    cleanup();
    expect(bar({ held: 2, page: "duty" }).querySelector("[data-held-chip]")).toBeNull();
    cleanup();
    expect(bar({ held: 0 }).querySelector("[data-held-chip]")).toBeNull();
  });
  it("连不上:布防状态变灰、写最后已知", () => {
    lang.value = "zh";
    const a = bar({ stale: true }).querySelector(".armstate")!;
    expect(a.className).toContain("stale");
    expect(a.textContent).toContain("最后已知");
  });
});

describe("第 2 轮 layout N11:手机菜单", () => {
  it("开着时 Esc、点外面都收起", () => {
    const c = render(<SideNav me={me("admin")} page="duty" alarms={0} notices={0} />).container;
    const toggle = c.querySelector(".nav-toggle") as HTMLButtonElement;
    fireEvent.click(toggle);
    expect(c.querySelector("#mainnav")!.className).toContain("open");
    fireEvent.keyDown(window, { key: "Escape" });
    expect(c.querySelector("#mainnav")!.className).not.toContain("open");
    fireEvent.click(toggle);
    fireEvent.pointerDown(document.body);
    expect(c.querySelector("#mainnav")!.className).not.toContain("open");
  });
});

describe("第 3 轮 admin N1", () => {
  it("换页时不对侧栏链接调 scrollIntoView(会把第一下 Tab 的起点挪走)", () => {
    const spy = vi.fn();
    const old = HTMLElement.prototype.scrollIntoView;
    HTMLElement.prototype.scrollIntoView = spy;
    try {
      const me = { name: "alice", role: "admin" } as Me;
      render(<SideNav me={me} page="admin/users" alarms={0} notices={0} />);
      expect(spy).not.toHaveBeenCalled();
    } finally {
      HTMLElement.prototype.scrollIntoView = old;
    }
  });
});

// W6-13 / minor #25:保安开着值班页、实时画面页,看不到「正在演练」(以前只在管理员总览、报警记录页)
describe("W6-13 演练提示", () => {
  for (const hash of ["", "#/live", "#/map"]) {
    it(`保安在 ${hash || "#/"} 也看得到正在演练`, async () => {
      drill = { active: true, until_ms: Date.now() + 600_000, by: "alice" };
      location.hash = hash;
      const c = render(<Console me={me("guard")} onOut={() => {}} />);
      await waitFor(() => expect(c.container.querySelector("[data-drill-note]")).not.toBeNull());
      expect(c.container.querySelector("[data-drill-note]")!.textContent).toContain("报警演练中");
    });
  }
  it("没在演练就不出", async () => {
    const c = render(<Console me={me("guard")} onOut={() => {}} />);
    await waitFor(() => expect(c.container.querySelector('main[data-page="duty"]')).not.toBeNull());
    await new Promise((r) => setTimeout(r, 30));
    expect(c.container.querySelector("[data-drill-note]")).toBeNull();
  });
});
