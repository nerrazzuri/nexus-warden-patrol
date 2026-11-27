// @vitest-environment happy-dom
// 现场设置 → 机器人(redesign 第六期 R-A / R-A2 / M-robot):左栏列表 + 加入申请;右边选中那一台「操作 / 设置」。
// 操作 = 单台机器人控制(robotctl.test 测按钮)+ 健康状况;设置 = 名字、派单方式、检查单、排查与维护、告警记录、解绑。
import { cleanup, fireEvent, render, waitFor } from "@testing-library/preact";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { setFetch } from "./api";
import { robotNames } from "./data";
import { lang } from "./i18n";
import type { UnitInfo } from "./live";
import { LiveWall } from "./livewall";
import { RobotsPage } from "./robotspage";

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
const NOW = new Date(2026, 9, 27, 12).getTime();

const card = (o: Record<string, unknown>) => ({ robot_id: "A", name: "", revoked: false, expires_at: NOW + 300 * 86_400_000, online: true,
  battery_pct: 76, patrols_today: 3, problems: [], recent_problems: [], agent: "0.9.1", compat: "ok", manual_only: false, ...o });
let robots: Record<string, unknown>[];
let posted: { url: string; body: Record<string, unknown> }[];
let pending: Record<string, unknown>[];
let said: string[];
let task: string | null;
let presets: { lang: string; text: string }[] | null = null;
let openRevoked: string[] = [];

beforeEach(() => {
  lang.value = "zh";
  posted = [];
  said = [];
  pending = [];
  task = null;
  presets = [{ lang: "zh", text: "警告，您已进入受限制区域，请立即离开。" }, { lang: "en", text: "Please leave." }];
  openRevoked = [];
  robotNames.value = {};
  robots = [card({}), card({ robot_id: "B", online: false, battery_pct: null, patrols_today: 0,
    problems: [{ key: "B/stuck#1", kind: "stuck", first_ms: NOW - 60_000 }, { device: "front_camera", state: "offline" }],
    recent_problems: [{ key: "B/stuck#1", kind: "stuck", first_ms: NOW - 60_000, resolved_ms: null }] })];
  setFetch(((url: string, init?: RequestInit) => {
    if (init?.method === "POST") {
      const body = JSON.parse(String(init.body ?? "{}"));
      posted.push({ url, body });
      if (/\/(patrol|standby\/return|abort|relocalize)$/.test(url)) return Promise.resolve(json({ command_id: "c1", ack: { command_id: "c1", result: "accepted" } }));
      if (url.endsWith("/name")) robots = robots.map((r) => (url.includes(`/${r.robot_id}/`) ? { ...r, name: body.name } : r));
      if (url.endsWith("/revoke")) return Promise.resolve(json({ robot_id: "A", summary: "CRL", robot_wipe: "offline", broker_restart: "systemctl restart x" }));
      if (url === "/api/voice-presets") {
        if (!body.presets.every((p: { text: string }) => p.text.trim())) return Promise.resolve(json({ error: "每句 1–300 个字" }, 400));
        presets = body.presets;
        return Promise.resolve(json({ presets }));
      }
      if (url.startsWith("/api/admin/bind/")) {
        if (url.endsWith("/approve") && body.confirm_password !== "pw") return Promise.resolve(json({ error: "密码不对" }, 403));
        pending = [];
        return Promise.resolve(json({ state: "ok" }));
      }
      return Promise.resolve(json({ robots }));
    }
    if (url.startsWith("/api/robots/overview")) return Promise.resolve(json({ robots, open_revoked: openRevoked }));
    if (url === "/api/schedule") return Promise.resolve(json({ missions: ["east-loop", "west-loop"] }));
    if (url === "/api/robots/A") return Promise.resolve(json({ robot_id: "A", status: { online: true, task: task ? { task_id: task, kind: "patrol", state: "running" } : null } }));
    if (url === "/api/admin/bind") return Promise.resolve(json({ requests: pending }));
    if (url === "/api/voice-presets" && presets) return Promise.resolve(json({ presets }));
    return Promise.resolve(json({}, 404));
  }) as typeof fetch);
});
afterEach(() => {
  cleanup();
  robotNames.value = {};
});

const page = (o: { units?: UnitInfo[]; role?: string; readOnly?: boolean } = {}) =>
  render(<RobotsPage say={(s) => said.push(s)} now={NOW} units={o.units} role={o.role} readOnly={o.readOnly} />);
const cardOf = (c: Element, id: string) => c.querySelector(`.robot-card[data-robot="${id}"]`)!;
const btn = (root: Element, text: string) => Array.from(root.querySelectorAll("button")).find((b) => b.textContent?.trim() === text) as HTMLButtonElement;
/** 选一台、切到「设置」。 */
const settings = async (c: Element, id: string) => {
  await waitFor(() => expect(cardOf(c, id)).not.toBeNull());
  fireEvent.click(cardOf(c, id));
  await waitFor(() => expect(c.querySelector(".rb-head h2")!.textContent).toBe(id));
  fireEvent.click(btn(c.querySelector(".rb-head")!, "设置"));
  return c.querySelector(".robot-detail")!;
};
const unitOf = (id: string, o: Record<string, unknown> = {}) => ({ robot: { robot_id: id, active: true, fresh: true, revoked: false, held: null,
  status: { online: true, last_seen: NOW / 1000 - 2, ready: { motion: true }, task: null }, capabilities: { tasks: {} } },
  state: "idle", battery: 76, task: "", ...o } as unknown as UnitInfo);

describe("机器人页 · 列表", () => {
  it("每台:名字、电量、在做什么、今天几趟、毛病;离线标红", async () => {
    const { container: c } = page();
    await waitFor(() => expect(cardOf(c, "B")).not.toBeNull());
    const b = cardOf(c, "B");
    expect(b.textContent).toContain("离线");
    expect(b.querySelector(".tone-error")).not.toBeNull();
    expect(b.textContent).toContain("2 个故障");
    expect(cardOf(c, "A").textContent).toContain("76%");
    expect(cardOf(c, "A").textContent).toContain("3 趟");
    expect(c.querySelector(".rb-listhead h1")!.textContent).toBe("机器人 2");
  });

  it("W60 没毛病就安静:没有提示条;有毛病多一条", async () => {
    const { container: c } = page();
    await waitFor(() => expect(cardOf(c, "A")).not.toBeNull());
    expect(cardOf(c, "A").querySelector(".fleet-warn")).toBeNull();
    expect(cardOf(c, "B").querySelector(".fleet-warn")).not.toBeNull();
  });

  it("第 9 轮 W9-09:盘只是快满了写「存储盘快满（86%）」,不写 disk 异常", async () => {
    robots = [card({ problems: [{ device: "disk", state: "degraded" }], storage: { used_ratio: 0.86, backlog_files: 0, oldest_backlog_s: null } }),
      card({ robot_id: "B", problems: [{ device: "camera:front", state: "error" }] })];
    const { container: c } = page();
    await waitFor(() => expect(cardOf(c, "A")?.querySelector(".fleet-warn")).toBeTruthy());
    expect(cardOf(c, "A").querySelector(".fleet-warn")!.textContent).toBe("存储盘快满（86%）");
    expect(cardOf(c, "B").querySelector(".fleet-warn")!.textContent).toBe("摄像头 前故障");
    expect(c.querySelector(".rb-list")!.textContent).not.toContain("disk");
  });

  it("W71 Nav2 没起来:提示条写 Nav2 不可用和原因", async () => {
    robots = [card({ problems: [{ nav2: "Nav2 转接节点未连接" }] })];
    const { container: c } = page();
    await waitFor(() => expect(cardOf(c, "A")?.querySelector(".fleet-warn")).toBeTruthy());
    expect(cardOf(c, "A").querySelector(".fleet-warn")!.textContent).toContain("Nav2 不可用（退回自带规划）：Nav2 转接节点未连接");
  });

  it("P1-23:还没连上过的是灰的「未激活」,不是红的离线", async () => {
    robots = [card({ robot_id: "N", online: false, ever_seen: false, battery_pct: null }), card({ robot_id: "B", online: false, ever_seen: true })];
    const { container: c } = page();
    await waitFor(() => expect(cardOf(c, "N")).not.toBeNull());
    const n = cardOf(c, "N");
    expect(n.textContent).toContain("未激活");
    expect(n.querySelector(".state")!.getAttribute("title")).toContain("还没连上");
    expect(n.querySelector(".tone-error")).toBeNull();
    expect(cardOf(c, "B").querySelector(".tone-error")).not.toBeNull();
  });

  it("第 2 轮 N4:消息服务没重启的常驻一条,写要重启、才能重新添加", async () => {
    openRevoked = ["T7"];
    const { container: c } = page();
    await waitFor(() => expect(c.querySelector("[data-open-revoked]")).not.toBeNull());
    expect(c.querySelector("[data-open-revoked]")!.textContent).toContain("T7");
    expect(c.querySelector("[data-open-revoked]")!.textContent).toContain("重启消息服务");
  });

  it("保安页用起的名字", () => {
    robotNames.value = { A: "南区" };
    const u: UnitInfo = { robot: { robot_id: "A", active: true, fresh: true, revoked: false, held: null, status: { online: true, last_seen: 0 }, capabilities: null },
      state: "idle", battery: 50, task: "" };
    const { container: c } = render(<LiveWall units={[u]} alerts={[]} now={0} onZoom={() => {}} />);
    expect(c.querySelector(".lw-card .slot-name")!.textContent).toBe("南区");
  });
});

describe("机器人页 · 操作", () => {
  it("默认开第一台、在「操作」:单台控制嵌在页里(没有它自己的页头),右栏末尾是健康状况", async () => {
    robots[0] = card({ patrols_7d: 12, aborts_7d: 1, storage: { used_ratio: 0.42, backlog_files: 3, oldest_backlog_s: 90 },
      map: { id: "estate-1", version: "7", match: false }, wifi: { ssid: "Estate", link: "wifi", change: null } });
    const { container: c } = page({ units: [unitOf("A")] });
    await waitFor(() => expect(c.querySelector(".robot-detail .rc")).not.toBeNull());
    expect(c.querySelector(".rb-head h2")!.textContent).toBe("A");
    expect(btn(c.querySelector(".rb-head")!, "操作").getAttribute("aria-pressed")).toBe("true");
    expect(c.querySelector(".rc-head")).toBeNull();
    const h = c.querySelector(".rc-side .rb-health")!.textContent!;
    for (const s of ["76%", "Estate", "已用 42%", "待传 3 个", "estate-1 v7", "与站点不一致", "7 天 12 次", "中止 1 次"]) expect(h).toContain(s);
  });

  it("还没连上的:写连上后才能操作,照样有健康状况", async () => {
    const { container: c } = page();
    await waitFor(() => expect(c.querySelector(".rb-off")).not.toBeNull());
    expect(c.querySelector(".rb-off")!.textContent).toContain("连上后才能操作");
    expect(c.querySelector(".rb-off .rb-health")).not.toBeNull();
  });

  it("第 11 轮 W11-02:不知道待传几个只写「已用 88%」,不写 null", async () => {
    robots = [card({ storage: { used_ratio: 0.88, backlog_files: null, oldest_backlog_s: null } })];
    const { container: c } = page();
    await waitFor(() => expect(c.querySelector(".rb-health")).not.toBeNull());
    const d = c.querySelector(".rb-health")!.textContent!;
    expect(d).toContain("已用 88%");
    expect(d).not.toContain("null");
    expect(d).not.toContain("待传");
  });

  it("M-robot 经理只看:没有添加、加入申请、「设置」;操作视图照样(派巡逻由单台控制按经理收)", async () => {
    pending = [{ id: "ab12", serial: "D1M-7", check: "042917", model: "", version: "", source: "x", created_ms: NOW, expires_ms: NOW + 1 }];
    const { container: c } = page({ readOnly: true, role: "owner", units: [unitOf("A")] });
    await waitFor(() => expect(c.querySelector(".robot-detail .rc")).not.toBeNull());
    expect(btn(c, "添加")).toBeUndefined();
    expect(c.querySelector(".rb-views")).toBeNull();
    expect(c.querySelector(".bind-pending")).toBeNull();
    expect(c.querySelector('.robot-detail input[name="name"]')).toBeNull();
  });
});

describe("机器人页 · 设置", () => {
  it("改名字", async () => {
    const { container: c } = page();
    const d = await settings(c, "A");
    fireEvent.input(d.querySelector('input[name="name"]')!, { target: { value: "南区" } });
    fireEvent.click(btn(d, "保存名字"));
    await waitFor(() => expect(posted.find((p) => p.url === "/api/admin/robots/A/name")?.body).toEqual({ name: "南区" }));
    await waitFor(() => expect(cardOf(c, "A").textContent).toContain("南区"));
  });

  it("检查单:要处理的在上(换 Wi-Fi 等批准、地图不一致、毛病);正常的收起来,展开按组列", async () => {
    robots = [card({ map: { id: "estate-1", version: "7", match: false }, home_set: true, standby_set: false,
      wifi: { ssid: "Estate", link: "4g", change: { id: "0a1b2c3d4e5f", ssid: "New", mode: "trial", expires_ms: NOW } } })];
    const { container: c } = page();
    expect(await waitFor(() => cardOf(c, "A").textContent)).toContain("WiFi 变更待确认");
    const d = await settings(c, "A");
    const need = Array.from(d.querySelectorAll(".rb-checks"))[0];
    expect(Array.from(need.querySelectorAll("[data-check]")).map((x) => x.getAttribute("data-check"))).toEqual(["wifi", "sw", "standby"]);
    expect(d.querySelector(".rb-sum")!.textContent).toContain("3 项要处理");
    expect(need.querySelector('[data-check="wifi"]')!.textContent).toContain("正在尝试 WiFi「New」");
    expect(need.querySelector('a[href="#/admin/layout?tab=standby"]')).not.toBeNull();
    expect(d.querySelector('[data-check="cert"]')).toBeNull();
    fireEvent.click(btn(d, "展开"));
    expect(d.querySelector('[data-check="cert"]')!.textContent).toContain("还剩 300 天");
    expect(Array.from(d.querySelectorAll(".sp-lbl")).map((x) => x.textContent)).toContain("连接");
    fireEvent.click(btn(need.querySelector('[data-check="wifi"]')!, "确认换 WiFi"));
    await waitFor(() => expect(posted.at(-1)).toEqual({ url: "/api/robots/A/wifi", body: { id: "0a1b2c3d4e5f", approve: true } }));
  });

  it("用户 11-27:老原点离墙太近 —— 原点那一项要处理,写重新标,链到定位页", async () => {
    robots = [card({ home_set: true, home_bad: true, standby_set: true })];
    const { container: c } = page();
    await waitFor(() => cardOf(c, "A"));
    const d = await settings(c, "A");
    const need = Array.from(d.querySelectorAll(".rb-checks"))[0];
    const home = need.querySelector('[data-check="home"]')!;
    expect(home.textContent).toContain("原点离墙、障碍或禁行区太近");
    expect(home.querySelector('a[href="#/admin/localization"]')!.textContent).toBe("去重新标原点");
  });

  it("W72 详情:设备、手动原因、登记日期都在", async () => {
    robots[0] = card({ devices: [{ id: "lidar", state: "online" }, { id: "camera:thermal", state: "error" }], enrolled_at: NOW - 86_400_000 * 10,
      manual_only: true, manual_note: "先试跑" });
    const { container: c } = page();
    const d = (await settings(c, "A")).textContent!;
    for (const s of ["摄像头 thermal 故障", "激光雷达", "先试跑", "只手动派"]) expect(d).toContain(s);
  });

  it("用户 11-21:雷达视野表在学写进度、学好了算正常", async () => {
    robots[0] = card({ fov: { state: "learning", frames: 240, need: 600 } });
    const { container: c } = page();
    const d = await settings(c, "A");
    const row = d.querySelector('[data-check="fov"]')!;
    expect(row.textContent).toContain("边走边学（40%）");
    expect(row.textContent).toContain("盲区限速不生效");
    expect(row.closest(".rb-checks")).toBe(d.querySelectorAll(".rb-checks")[0]);
  });

  it("P1-26 / P1-05:切派单方式、重出开通码先在原地确认(不弹窗),说清是什么意思", async () => {
    const { container: c } = page();
    const d = await settings(c, "A");
    fireEvent.click(btn(d.querySelector(".rb-dispatch")!, "仅限手动"));
    expect(posted.some((p) => p.url.endsWith("/service"))).toBe(false);
    expect(document.querySelector(".modal")).toBeNull();
    const ask = d.querySelector(".rb-ask")!;
    expect(ask.textContent).toMatch(/报警|排程/);
    fireEvent.click(btn(ask, "改为仅限手动"));
    await waitFor(() => expect(posted.find((p) => p.url === "/api/robots/A/service")?.body).toEqual({ manual_only: true }));
    // 都正常时检查单直接全展开
    fireEvent.click(btn(d.querySelector('[data-check="code"]')!, "重出开通码…"));
    expect(posted.some((p) => p.url.endsWith("/code"))).toBe(false);
    expect(d.querySelector(".rb-ask")!.textContent).toContain("旧码会立刻作废");
  });

  it("告警记录在右栏,分三组:要处理(P1)、待跟进、记录(自动恢复的标出来、收起来)", async () => {
    robots = [card({ robot_id: "B", recent_problems: [
      { key: "B/robot_offline#2", kind: "robot_offline", level: "P1", first_ms: NOW - 50_000, resolved_ms: NOW - 40_000, resolved_by: "site:back_soon" },
      { key: "B/loc_degraded#1", kind: "loc_degraded", level: "P2", first_ms: NOW - 60_000, resolved_ms: null, resolved_by: "" },
      { key: "B/stuck#1", kind: "stuck", level: "P1", first_ms: NOW - 70_000, resolved_ms: null, resolved_by: "" },
      { key: "B/fallen#1", kind: "fallen", level: "P1", first_ms: NOW - 80_000, resolved_ms: NOW - 1000, resolved_by: "gina" },
    ] })];
    const { container: c } = page();
    const d = await settings(c, "B");
    const sec = d.querySelector(".rb-setside .robot-alerts")!;
    expect(Array.from(sec.querySelectorAll("[data-group]")).map((g) => g.getAttribute("data-group"))).toEqual(["act", "later", "log"]);
    expect(sec.querySelector('[data-group="act"]')!.textContent).toContain("未到达点位");
    const log = sec.querySelector('[data-group="log"]') as HTMLDetailsElement;
    expect(log.open).toBe(false);
    expect(log.textContent).toContain("自动恢复");
    expect(log.textContent).toContain("已处理");
  });

  it("第 10 轮 W9-10:点位没到那条只写一遍,用全角标点", async () => {
    robots = [card({ robot_id: "B", recent_problems: [
      { key: "B/stuck#3", kind: "stuck", level: "P2", title: "点位 P7 未到达,已跳过", first_ms: NOW - 50_000, resolved_ms: null, resolved_by: "" },
    ] })];
    const { container: c } = page();
    const d = await settings(c, "B");
    const sec = d.querySelector(".robot-alerts")!;
    expect(sec.textContent).toContain("点位 P7 未到达，已跳过");
    expect(sec.textContent).not.toContain("未到达,已跳过");
  });
});

describe("机器人页 · 解绑(第 2 轮 P0-10:说实话)", () => {
  const ask = async (id: string) => {
    const { container: c } = page();
    const d = await settings(c, id);
    fireEvent.click(Array.from(d.querySelectorAll(".rb-removal button")).find((b) => b.textContent!.startsWith("解绑"))!);
    expect(document.querySelector(".modal")).toBeNull();
    return { c, d, txt: d.querySelector(".rb-removal .rb-ask")!.textContent ?? "" };
  };
  it("原地确认写明恢复出厂、所有机器人会断线;继续 → 再输密码", async () => {
    const { d, txt } = await ask("A");
    expect(txt).toContain("恢复出厂");
    expect(txt).toContain("所有机器人会断线");
    fireEvent.click(btn(d.querySelector(".rb-removal .rb-ask")!, "继续"));
    await waitFor(() => expect(document.querySelector("form.confirm-pw")).not.toBeNull());
    fireEvent.input(document.querySelector('form.confirm-pw input[type="password"]')!, { target: { value: "my-own-password" } });
    fireEvent.submit(document.querySelector("form.confirm-pw")!);
    await waitFor(() => expect(posted.find((p) => p.url === "/api/admin/robots/A/revoke")?.body).toEqual({ confirm_password: "my-own-password" }));
    await waitFor(() => expect(said.join()).toContain("下次连接站点时将自动清除数据"));
  });
  it("在线:现在就清;录像已经在站点上的留着", async () => {
    const { txt } = await ask("A");
    expect(txt).toContain("现在就清除");
    expect(txt).toContain("站点上已有的录像不删");
  });
  it("离线:下次连上才清,证书现在作废", async () => {
    const { txt } = await ask("B");
    expect(txt).toContain("下次连上站点时");
    expect(txt).not.toContain("现在就清除");
  });
  it("从没连上过:没有东西要清", async () => {
    robots = [card({ robot_id: "T9", online: false, ever_seen: false })];
    const { txt } = await ask("T9");
    expect(txt).toContain("从没连上过");
  });
});

describe("机器人页 · 加入、添加", () => {
  it("W42 等待批准加入:核对码;核对并批准要再输密码、能起名字", async () => {
    pending = [{ id: "ab12", serial: "D1M-7", check: "042917", model: "D1 Max", version: "1", source: "192.168.1.20", created_ms: NOW, expires_ms: NOW + 1 }];
    const { container: c } = page();
    await waitFor(() => expect(c.querySelector('.bind-req[data-serial="D1M-7"]')).not.toBeNull());
    const row = c.querySelector('.bind-req[data-serial="D1M-7"]')!;
    expect(row.textContent).toContain("042917");
    expect(c.querySelector(".rb-enrol h2")!.textContent).toContain("1 个加入申请");
    fireEvent.click(btn(row, "核对并批准…"));
    const form = document.querySelector("form.bind-approve")!;
    expect(form.textContent).toContain("042917");
    fireEvent.input(form.querySelector('input:not([type="password"])')!, { target: { value: "西区" } });
    fireEvent.input(form.querySelector('input[type="password"]')!, { target: { value: "wrong" } });
    fireEvent.submit(form);
    await waitFor(() => expect(document.querySelector("form.bind-approve .error")?.textContent).toContain("密码错误"));
    fireEvent.input(form.querySelector('input[type="password"]')!, { target: { value: "pw" } });
    fireEvent.submit(form);
    await waitFor(() => expect(said.join()).toContain("D1M-7 已加入站点"));
    expect(posted.at(-1)).toEqual({ url: "/api/admin/bind/ab12/approve", body: { confirm_password: "pw", name: "西区" } });
    await waitFor(() => expect(c.querySelector(".bind-pending")).toBeNull());
  });

  it("W42 拒绝申请:原地确认", async () => {
    pending = [{ id: "cd34", serial: "D1M-8", check: "111111", model: "", version: "", source: "x", created_ms: NOW, expires_ms: NOW + 1 }];
    const { container: c } = page();
    await waitFor(() => expect(c.querySelector('.bind-req[data-serial="D1M-8"]')).not.toBeNull());
    fireEvent.click(btn(c.querySelector(".bind-req")!, "拒绝"));
    expect(document.querySelector(".modal")).toBeNull();
    expect(c.querySelector(".bind-req .rb-ask")!.textContent).toContain("D1M-8");
    fireEvent.click(btn(c.querySelector(".bind-req .rb-ask")!, "拒绝"));
    await waitFor(() => expect(posted.at(-1)?.url).toBe("/api/admin/bind/cd34/reject"));
  });

  it("W42 添加:说明用手机扫贴纸,工程师的开通码收在按钮后面", async () => {
    const { container: c } = page();
    await waitFor(() => expect(cardOf(c, "A")).not.toBeNull());
    fireEvent.click(btn(c, "添加"));
    const m = document.querySelector(".modal")!;
    expect(m.textContent).toContain("扫描机器人贴纸");
    expect(m.querySelector("form")).toBeNull();
    fireEvent.click(btn(m, "工程师：用开通码手动添加"));
    const f = document.querySelector(".modal form")!;
    expect(f.querySelector("details")!.textContent).toContain("provision --code");
    const input = f.querySelector("input") as HTMLInputElement;
    expect(f.textContent).toContain("最多 64 个");
    fireEvent.input(input, { target: { value: "D1 07" } });
    expect(f.querySelector("#robot-id-rule")!.className).toContain("error");
    fireEvent.submit(f);
    expect(posted.some((p) => p.url === "/api/admin/robots")).toBe(false);
  });

  it("第 4 轮 admin N2:添加重复编号,错误写在弹窗里,不只靠 toast", async () => {
    setFetch(((url: string, init?: RequestInit) => {
      if (init?.method === "POST" && url === "/api/admin/robots") return Promise.resolve(json({ error: "A 已登记且未吊销;先 revoke" }, 409));
      if (url.startsWith("/api/robots/overview")) return Promise.resolve(json({ robots, open_revoked: [] }));
      return Promise.resolve(json({}, 404));
    }) as typeof fetch);
    const c = page();
    await waitFor(() => expect(cardOf(c.container, "A")).not.toBeNull());
    fireEvent.click(btn(c.container, "添加"));
    fireEvent.click(await c.findByText("工程师：用开通码手动添加"));
    const dlg = c.container.ownerDocument.querySelector("dialog")!;
    fireEvent.input(dlg.querySelector("input")!, { target: { value: "A" } });
    fireEvent.submit(dlg.querySelector("form")!);
    await waitFor(() => expect(dlg.querySelector("[data-form-error]")?.textContent).toContain("A"));
    expect(said).toEqual([]);
  });
});
