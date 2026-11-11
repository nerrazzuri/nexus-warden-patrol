// @vitest-environment happy-dom
// W44 第二期 用户页(设计 §5.1「用户」):角色写界面名字、自己那一行不能删停、工程师临时账号(再输密码、口令只显示一次、
// 还剩多久、只能提前关和删)、看谁做过什么、删人要确认。
import { cleanup, fireEvent, render, waitFor } from "@testing-library/preact";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { setFetch } from "./api";
import { lang } from "./i18n";
import { AuditLine, type AuditRow, lastLoginText, UsersPage } from "./userspage";

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
const NOW = new Date(2026, 9, 27, 12, 0).getTime();

const acct = (o: Record<string, unknown>) => ({ name: "x", role: "guard", disabled: false, display_name: "", expires_ms: null, last_login_ms: null, expired: false, ...o });
let accounts: Record<string, unknown>[];
let posted: { url: string; body: Record<string, unknown> }[];
let pwOk: boolean;
let caps: { vpn?: boolean };

beforeEach(() => {
  lang.value = "zh";
  posted = [];
  pwOk = true;
  caps = { vpn: true };
  accounts = [
    acct({ name: "alice", role: "admin", display_name: "陈太", last_login_ms: NOW - 3_600_000 }),
    acct({ name: "olga", role: "owner", display_name: "陈先生" }),
    acct({ name: "gina", role: "guard", display_name: "王保安", last_login_ms: NOW - 3 * 86_400_000 }),
    acct({ name: "eng-20261027-0900", role: "engineer", display_name: "李工", expires_ms: NOW + 2 * 3_600_000 + 10 * 60_000 }),
  ];
  setFetch(((url: string, init?: RequestInit) => {
    if (init?.method === "POST") {
      const body = JSON.parse(String(init.body ?? "{}"));
      posted.push({ url, body });
      if (url === "/api/accounts/engineer") {
        if (!pwOk) return Promise.resolve(json({ error: "密码不对" }, 403));
        return Promise.resolve(json({ name: "eng-20261027-1200", password: "s3cret-once-only", expires_ms: NOW + 4 * 3_600_000, accounts,
          ...(body.vpn ? { vpn: { conf: "[Interface]\nAddress = 10.77.0.200/32\n", address: "10.77.0.200" } } : {}) }));
      }
      if (url.endsWith("/remove")) accounts = accounts.filter((a) => !url.includes(`/${a.name}/`));
      return Promise.resolve(json({ accounts }));
    }
    if (url.startsWith("/api/accounts")) return Promise.resolve(json({ accounts }));
    if (url === "/api/system/caps") return Promise.resolve(json({ priv: true, push: true, vpn: caps.vpn }));
    if (url.startsWith("/api/audit")) {
      return Promise.resolve(json({ audit: [{ id: 1, at: NOW - 60_000, actor: "gina", actor_role: "guard", action: "POST /api/mode", target: "armed", status: 200 },
        { id: 2, at: NOW - 30_000, actor: "gina", actor_role: "guard", action: "POST /api/robots/A/goto", target: "A", status: 403 },
        { id: 3, at: NOW - 20_000, actor: "gina", actor_role: "guard", action: "POST /api/weird/thing", target: "", status: 200 }] }));
    }
    return Promise.resolve(json({}, 404));
  }) as typeof fetch);
});
afterEach(cleanup);

const page = () => render(<UsersPage me="alice" say={() => {}} now={NOW} />);
const tr = (c: Element, name: string) => c.querySelector(`tr[data-name="${name}"]`)!;
const btn = (root: Element, text: string) => Array.from(root.querySelectorAll("button")).find((b) => b.textContent?.trim() === text) as HTMLButtonElement;

describe("用户页", () => {
  it("最后登录说人话", () => {
    expect(lastLoginText(null, NOW)).toBe("从未登录");
    expect(lastLoginText(NOW - 3_600_000, NOW)).toBe("今天 11:00");
    expect(lastLoginText(NOW - 3 * 86_400_000, NOW)).toBe("3 天前");
  });

  it("角色写界面名字", async () => {
    const { container: c } = page();
    await waitFor(() => expect(tr(c, "alice")).not.toBeNull());
    expect(tr(c, "alice").textContent).toContain("管理员（最高权限）");
    expect(tr(c, "olga").textContent).toContain("经理");
    expect(tr(c, "eng-20261027-0900").textContent).toContain("工程师（临时）");
    expect((tr(c, "gina").querySelector("select") as HTMLSelectElement).selectedOptions[0].textContent).toBe("保安");
  });

  it("自己那一行不能删、不能停用", async () => {
    const { container: c } = page();
    await waitFor(() => expect(tr(c, "alice")).not.toBeNull());
    expect(btn(tr(c, "alice"), "删除")).toBeUndefined();
    expect(btn(tr(c, "alice"), "停用")).toBeUndefined();
    expect(btn(tr(c, "gina"), "删除")).toBeTruthy();
  });

  it("第 2 轮 P1-65:站点没装 VPN,「签发 VPN」灰着、写原因", async () => {
    caps = { vpn: false };
    const { container: c } = page();
    await waitFor(() => expect(tr(c, "alice")).not.toBeNull());
    fireEvent.click(btn(c, "给工程师开临时账号"));
    await waitFor(() => expect((document.querySelector('form.eng-form input[name="vpn"]') as HTMLInputElement).disabled).toBe(true));
    expect(document.querySelector("[data-novpn]")!.textContent).toContain("没有装远程访问");
  });

  it("开工程师账号要再输密码,口令只显示一次", async () => {
    const { container: c } = page();
    await waitFor(() => expect(tr(c, "alice")).not.toBeNull());
    fireEvent.click(btn(c, "给工程师开临时账号"));
    fireEvent.input(document.querySelector('form.eng-form input[name="display"]')!, { target: { value: "王工" } });
    fireEvent.click(document.querySelector('form.eng-form input[value="24"]')!);
    const vpn = document.querySelector('form.eng-form input[name="vpn"]') as HTMLInputElement;
    expect(vpn.checked).toBe(false);                                              // P1-65:默认不勾
    fireEvent.click(vpn);
    fireEvent.submit(document.querySelector("form.eng-form")!);
    await waitFor(() => expect(document.querySelector("form.confirm-pw")).not.toBeNull());
    fireEvent.input(document.querySelector('form.confirm-pw input[type="password"]')!, { target: { value: "my-own-password" } });
    fireEvent.submit(document.querySelector("form.confirm-pw")!);
    await waitFor(() => expect(document.body.textContent).toContain("s3cret-once-only"));
    expect(posted.find((p) => p.url === "/api/accounts/engineer")!.body).toEqual({ display_name: "王工", hours: 24, vpn: true, confirm_password: "my-own-password" });
    expect(document.body.textContent).toContain("10.77.0.200");                    // W55:勾了就同时发 VPN 配置
    expect(document.querySelector('a[download="nexwar_eng-20261027-1200.conf"]')).not.toBeNull();
    expect(document.body.textContent).toContain("eng-20261027-1200");
    expect(document.body.textContent).toContain("关闭后无法再查看");
    fireEvent.click(btn(document.body, "关闭"));
    expect(document.body.textContent).not.toContain("s3cret-once-only");
  });

  it("密码输错不关对话框", async () => {
    pwOk = false;
    const { container: c } = page();
    await waitFor(() => expect(tr(c, "alice")).not.toBeNull());
    fireEvent.click(btn(c, "给工程师开临时账号"));
    fireEvent.input(document.querySelector('form.eng-form input[name="display"]')!, { target: { value: "王工" } });
    fireEvent.submit(document.querySelector("form.eng-form")!);
    await waitFor(() => expect(document.querySelector("form.confirm-pw")).not.toBeNull());
    fireEvent.input(document.querySelector('form.confirm-pw input[type="password"]')!, { target: { value: "wrong-password" } });
    fireEvent.submit(document.querySelector("form.confirm-pw")!);
    await waitFor(() => expect(document.querySelector("form.confirm-pw")!.textContent).toContain("密码错误"));
  });

  it("工程师那一行写还剩多久、只能提前关和删", async () => {
    const { container: c } = page();
    await waitFor(() => expect(tr(c, "eng-20261027-0900")).not.toBeNull());
    const r = tr(c, "eng-20261027-0900");
    expect(r.textContent).toContain("剩余 2 小时 10 分");
    expect(r.querySelector("select")).toBeNull();
    expect(btn(r, "重设密码")).toBeUndefined();
    fireEvent.click(btn(r, "提前关闭"));
    expect(posted.find((p) => p.url === "/api/accounts/eng-20261027-0900")).toBeUndefined();   // P1-05:先确认
    fireEvent.click(btn(c.ownerDocument.querySelector(".modal")!, "提前关闭"));
    await waitFor(() => expect(posted.find((p) => p.url === "/api/accounts/eng-20261027-0900")?.body).toEqual({ disabled: true }));
  });

  it("点一个人看他做过什么", async () => {
    const { container: c } = page();
    await waitFor(() => expect(tr(c, "gina")).not.toBeNull());
    fireEvent.click(tr(c, "gina").querySelector(".user-name")!);
    await waitFor(() => expect(c.querySelector(".user-audit")!.textContent).toContain("切换布防模式"));
    // P1-66:写成功 / 被拒绝;认不得的写「其他操作」,不露接口路径
    const au = c.querySelector(".user-audit")!;
    expect(au.querySelectorAll('[data-result="refused"]').length).toBe(1);
    expect(au.querySelectorAll('[data-result="ok"]').length).toBe(2);
    expect(au.textContent).toContain("其他操作");
    expect(au.textContent).not.toContain("/api/");
  });

  it("删人要确认", async () => {
    const { container: c } = page();
    await waitFor(() => expect(tr(c, "gina")).not.toBeNull());
    fireEvent.click(btn(tr(c, "gina"), "删除"));
    expect(document.body.textContent).toContain("操作记录仍保留");
    fireEvent.click(btn(document.querySelector(".modal, [role=dialog]")!, "删除"));
    await waitFor(() => expect(posted.map((p) => p.url)).toContain("/api/accounts/gina/remove"));
    await waitFor(() => expect(c.querySelector('tr[data-name="gina"]')).toBeNull());
  });
});


describe("网页易用性第 1 轮 P1-05 / P1-63 / P1-64", () => {
  it("改角色先确认(升管理员写清后果),停用先确认;新增用户能选只读", async () => {
    const { container: c } = page();
    await waitFor(() => expect(tr(c, "gina")).not.toBeNull());
    const sel = tr(c, "gina").querySelector("select") as HTMLSelectElement;
    fireEvent.change(sel, { target: { value: "admin" } });
    expect(posted.some((p) => p.url === "/api/accounts/gina")).toBe(false);
    const m = c.ownerDocument.querySelector(".modal")!;
    expect(m.textContent).toContain("管理员能增删用户");
    fireEvent.click(btn(m, "改角色"));
    await waitFor(() => expect(posted.find((p) => p.url === "/api/accounts/gina")?.body).toEqual({ role: "admin" }));
    posted.length = 0;
    fireEvent.click(btn(tr(c, "gina"), "停用"));
    expect(posted.length).toBe(0);
    fireEvent.click(btn(c.ownerDocument.querySelector(".modal")!, "停用"));
    await waitFor(() => expect(posted.find((p) => p.url === "/api/accounts/gina")?.body).toEqual({ disabled: true }));
    fireEvent.click(btn(c, "添加用户"));
    const opts = Array.from(c.ownerDocument.querySelectorAll(".modal select option")).map((o) => (o as HTMLOptionElement).value);
    expect(opts).toContain("viewer");
  });
});

describe("第 2 轮 P1-66:操作记录说人话", () => {
  it("添加、解绑、重出激活码有自己的名字;对象里的内部编号不摆出来", async () => {
    const { actionText, targetText } = await import("./userspage");
    lang.value = "en";
    expect(actionText("POST /api/admin/robots")).toBe("Added a robot");
    expect(actionText("POST /api/admin/robots/A/revoke")).toBe("Unbound a robot");
    expect(actionText("POST /api/admin/robots/A/code")).toBe("Issued a new activation code");
    expect(actionText("POST /api/robots/A/map")).toBe("Switched a robot's map");          // 第 5 轮 P1-66
    expect(actionText("POST /api/robots/A/deter")).toBe("Sounded a robot's deterrent");
    expect(targetText("estate-1:7/mark:294c9dd2ce8a")).toBe("map estate-1 v7");
    expect(targetText("A")).toBe("A");
    lang.value = "zh";
  });
});

describe("第 3 轮 P1-66 活动记录", () => {
  it("日程、值班设置、例外、看录像认得;模式、例外编号写人话;改账号写改了什么", async () => {
    const { actionText, targetText, changeText } = await import("./userspage");
    const { lang } = await import("./i18n");
    lang.value = "zh";
    expect(actionText("POST /api/schedule")).toBe("改了巡逻日程");
    expect(actionText("POST /api/duty-settings")).toBe("改了值班设置");
    expect(actionText("POST /api/arming/exceptions")).toBe("加了布防例外");
    expect(actionText("POST /api/arming/exceptions/2/remove")).toBe("删了布防例外");
    expect(actionText("POST /api/route-schedules/s1")).toBe("改了巡逻日程");
    expect(actionText("POST /api/teleop-speeds")).toBe("改了遥控速度");
    expect(targetText("estate-1:7/R4M-Zone2")).toBe(`${targetText("estate-1:7/" + "a".repeat(12)).trim()} · R4M-Zone2`);
    expect(targetText("camera/gate")).toBe("摄像头 gate");
    expect(changeText({ first_day: "2026-11-09", last_day: "2026-11-10" })).toBe("2026-11-09 – 2026-11-10");
    expect(actionText("VIEW")).toBe("查看");
    expect(targetText("armed")).toBe("布防");
    expect(targetText("exception/2")).toBe("第 2 条例外");
    expect(changeText({ role: "guard", disabled: true })).toBe("权限改成保安；停用");
  });
});

describe("日志设计 第 1、2 条:操作记录写出前后变化、来源;系统事件也说人话", () => {
  it("改模式写从什么到什么,待命点写加删和坐标,叫停写当时在跑什么", async () => {
    const { changeText } = await import("./userspage");
    lang.value = "zh";
    expect(changeText({ from: "armed", to: "home", source: "app" })).toContain("布防 → 留守");
    expect(changeText({ op: "add", name: "dock", x: 1.5, y: -2 })).toBe("新增 dock (1.50, -2.00)");
    expect(changeText({ op: "remove", name: "dock" })).toBe("删除 dock");
    expect(changeText({ doing: { task: "t-9", kind: "patrol", state: "running" } })).toBe("当时在跑 patrol t-9");
    expect(changeText({ note: "迟了 31 分钟;之前没派出去:A 站点设成只许手动派,不接排程" })).toContain("只许手动派");
  });
  it("日程、机器人上下线、告警这些系统事件有自己的名字,记录者写「系统」", async () => {
    const { actionText, AuditLine } = await import("./userspage");
    lang.value = "zh";
    expect(actionText("schedule skip")).toBe("日程这一轮没跑");
    expect(actionText("schedule supervised")).toBe("日程没能派出机器人");
    expect(actionText("schedule started")).toBe("日程开始巡逻");
    expect(actionText("robot offline")).toBe("机器人离线");
    expect(actionText("alert escalated")).toBe("报警没人确认，已升级");
    const c = render(<ul><AuditLine who r={{ id: 1, at: 0, actor: "site:schedule", action: "schedule skip",
      target: "demo-night", status: 200, detail: { note: "迟了 31 分钟", source: "system" } }} /></ul>).container;
    expect(c.textContent).toContain("系统");
    expect(c.textContent).not.toContain("site:schedule");
    const w = render(<ul><AuditLine r={{ id: 2, at: 0, actor: "alice", action: "POST /api/mode",
      target: "home", status: 200, detail: { from: "armed", to: "home", source: "web" } }} /></ul>).container;
    expect(w.querySelector("[data-source=web]")?.textContent).toBe("网页");
    // W6-06:没报自己是什么程序的令牌(命令行、脚本)写「脚本」,不冒充 App
    const a = render(<ul><AuditLine r={{ id: 3, at: 0, actor: "alice", action: "POST /api/mode",
      target: "home", status: 200, detail: { source: "api" } }} /></ul>).container;
    expect(a.querySelector("[data-source=api]")?.textContent).toBe("脚本");
  });
});

describe("日志设计 第 7 条:错误码", () => {
  it("被拒的一行显示十六进制码,悬停是英文名;成功的行(W6-07)码只在悬停里", async () => {
    const { AuditLine } = await import("./userspage");
    lang.value = "zh";
    const c = render(<ul><AuditLine r={{ id: 3, at: 0, actor: "alice", action: "POST /api/mode",
      target: "n", status: 403, detail: { err: "0x0302", err_name: "sched.missed" } }} /></ul>).container;
    const tag = c.querySelector("[data-err]");
    expect(tag?.textContent).toBe("0x0302");
    expect(tag?.getAttribute("title")).toBe("sched.missed");
    cleanup();
    const ok = render(<ul><AuditLine r={{ id: 4, at: 0, actor: "site:schedule", action: "schedule skip",
      target: "n", status: 200, detail: { err: "0x0302", err_name: "sched.missed" } }} /></ul>).container;
    expect(ok.querySelector("[data-err]")).toBeNull();
    expect(ok.querySelector("[data-audit]")!.getAttribute("title")).toBe("0x0302 sched.missed");
  });
});

// 易用性第 6 轮 W6-07:正常的行不挂 0x 码;对象写人话、跟界面语言;登录那一条执行人不写 login:
describe("W6-07 操作记录读得懂", () => {
  const line = (r: Partial<AuditRow>) => render(<ul><AuditLine who r={{ id: 9, at: 0, actor: "alice", action: "POST /api/mode", target: "", status: 200, ...r } as AuditRow} /></ul>).container;
  it("成功的行不挂码;被拒的照样挂", () => {
    lang.value = "zh";
    expect(line({ detail: { err: "0x0509" } }).querySelector("[data-err]")).toBeNull();
    cleanup();
    expect(line({ status: 403, detail: { err: "0x0101", error: "不行" } }).querySelector("[data-err]")).not.toBeNull();
  });
  it("报警的对象写「报警:标题 · 机器人」,标题跟界面语言,不重复站点那句中文", () => {
    lang.value = "en";
    const c = line({ action: "alert escalated", target: "B/disk_80#2", detail: { title: "机器人的发件箱所在的盘即将写满" } });
    expect(c.textContent).toContain("Alarm: Robot storage almost full · B");
    expect(c.textContent).not.toContain("发件箱");
    expect(c.textContent).not.toContain("disk_80");
  });
  it("诊断包:写成「支持包 · 报警:… · 时间段」;老格式也不露中文原话", () => {
    lang.value = "en";
    const c = line({ action: "DOWNLOAD /api/support-bundle", target: "support-bundle/alert:A/schedule_blocked#3/1794307980000-1794310380000" });
    expect(c.textContent).toContain("Support bundle");
    expect(c.textContent).toContain("Scheduled patrol blocked · A");
    cleanup();
    const o = line({ action: "DOWNLOAD /api/support-bundle", target: "support-bundle/告警 A/schedule_blocked#3(排程 demo-night 无法派单:…)/1794307980000-1794310380000" });
    expect(o.textContent).toContain("Support bundle");
    expect(o.textContent).not.toContain("告警");
  });
  // 补测(da0a60ea):诊断包按一趟巡逻写「第 25 趟巡逻」、临时路线写 temp-…、删草稿写「修改地图或防区」
  it("补测:一趟巡逻写「机器人 · 路线」;临时路线、去看看不露编号;删地图版本单说;产生报警", () => {
    lang.value = "zh";
    const r = line({ action: "DOWNLOAD /api/support-bundle", target: "support-bundle/run:25:A:temp-1794360229453/1794307980000-1794310380000" });
    expect(r.textContent).toContain("A · 临时路线");
    expect(r.textContent).not.toContain("第 25 趟");
    cleanup();
    const g = line({ action: "DOWNLOAD /api/support-bundle", target: "support-bundle/run:26:B:task-60a9ef78b711/1794307980000-1794310380000" });
    expect(g.textContent).toContain("B · 去一个点");
    expect(g.textContent).not.toContain("60a9ef78");
    cleanup();
    const d = line({ action: "POST /api/robots/A/patrol", target: "temp-1794360229453" });
    expect(d.textContent).toContain("临时路线");
    expect(d.textContent).not.toContain("1794360229453");
    cleanup();
    const del = line({ action: "POST /api/admin/maps/estate-1/13/delete", target: "estate-1:13" });
    expect(del.textContent).toContain("删除了地图版本");
    expect(del.textContent).toContain("地图 estate-1 第 13 版");
    cleanup();
    expect(line({ action: "alert raised", target: "B/disk_80#2" }).textContent).toContain("产生报警");
  });
  it("登录那一条执行人写账号名", () => {
    lang.value = "zh";
    const c = line({ actor: "login:demo", action: "POST /api/login" });
    expect(c.querySelector(".audit-who")!.textContent).toBe("demo");
  });
});
