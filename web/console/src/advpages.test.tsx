// @vitest-environment happy-dom
// W44 第四期 高级 → 诊断、软件升级、系统:检查单说人话、打包日志是下载、上传要再输密码、在线下载灰着、备份没成功写红、VPN 还没装。
import { cleanup, fireEvent, render, waitFor } from "@testing-library/preact";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { DiagPage, deviceText } from "./advdiag";
import { parseSpeeds, SystemPage2 } from "./advsystem";
import { isLoopbackOrigin, pairChoices, pickPairUrl } from "./admin";
import { UpgradePage } from "./advupgrade";
import { setFetch } from "./api";
import { lang } from "./i18n";

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
let health: unknown;
let lanAddrs: string[] = [];
let uploads: { url: string; headers: Record<string, string> }[];
let posted: { url: string; body: unknown }[];

beforeEach(() => {
  lang.value = "zh";
  uploads = [];
  posted = [];
  health = { ok: false, version: "1.4.0", checks: { db: { ok: true }, disk: { ok: true, detail: "剩 120 GB" }, backup: { ok: false, detail: "已经 9 天没有备份成功" } } };
  setFetch(((url: string, init?: RequestInit) => {
    if (init?.method === "POST") {
      const h = (init.headers ?? {}) as Record<string, string>;
      if (url === "/api/releases/upload") {
        uploads.push({ url, headers: h });
        return Promise.resolve(h["X-Nexwar-Confirm"] === "my-own-password" ? json({ release: { name: "v1.5.0" } }) : json({ error: "密码不对" }, 403));
      }
      posted.push({ url, body: JSON.parse(String(init.body ?? "{}")) });
      return Promise.resolve(json({}));
    }
    if (url === "/api/health") return Promise.resolve(json(health));
    if (url === "/api/problem-reports") return Promise.resolve(json({ reports: [
      { code: "NW-1110-7F3A", at_ms: 1, by: "anonymous@10.0.0.9", note: "登不上", robot: "A", device: "Pixel 7", app: "1.4.0", bytes: 9 },
      { code: "NW-1110-0B12", at_ms: 2, by: "bob", note: "", robot: "", device: "", app: "", bytes: 9 }] }));
    if (url === "/api/pairing/addresses") return Promise.resolve(json({ addresses: lanAddrs }));
    if (url === "/api/teleop-speeds") return Promise.resolve(json({ speeds: [0.3, 0.6, 1.0, 1.3, 1.6, 2.0] }));
    if (url === "/api/robots") return Promise.resolve(json({ robots: [{ robot_id: "A", fresh: true, revoked: false, devices: { items: [{ id: "camera:front", state: "online" }, { id: "rtk", state: "degraded", detail: "浮点解" }] } }] }));
    if (url === "/api/releases") return Promise.resolve(json({ releases: [{ name: "v1.4.0", note: "" }], robots: { A: "v1.4.0" } }));
    if (url === "/api/versions") return Promise.resolve(json({ site: { version: "1.4.0" }, robots: [], clients: [] }));
    return Promise.resolve(json({}, 404));
  }) as typeof fetch);
});
afterEach(cleanup);
const btn = (root: Element, text: string) => Array.from(root.querySelectorAll("button")).find((b) => b.textContent?.trim() === text) as HTMLButtonElement;

describe("诊断", () => {
  it("检查单说人话,机器人的设备也列", async () => {
    const { container: c } = render(<DiagPage say={() => {}} />);
    await waitFor(() => expect(c.querySelector('[data-check="db"]')!.textContent).toContain("数据库"));
    expect(c.querySelector('[data-check="backup"]')!.className).toContain("bad");
    await waitFor(() => expect(c.querySelector('[data-robot="A"]')!.textContent).toContain("前摄像头画面正常"));
    expect(c.querySelector('[data-robot="A"]')!.textContent).toContain("浮点解");
    expect(deviceText("link:router")).toContain("router");
    expect(deviceText("relay")).toBe("relay");
    expect(deviceText("board")).toBe("主控板温度");
    expect(deviceText("fan:stir")).toBe("风扇 stir");
    expect(deviceText("amp")).toBe("功放");
    expect(deviceText("lens:thermal")).toBe("热像镜头");
    expect(deviceText("nav2")).toBe("自主导航（Nav2）");
  });
  it("打包日志是下载:默认最近 24 小时", () => {
    const { container: c } = render(<DiagPage say={() => {}} />);
    const a = c.querySelector<HTMLAnchorElement>("[data-bundle] a.btn")!;
    expect(a.hasAttribute("download")).toBe(true);
    const q = new URLSearchParams(a.getAttribute("href")!.split("?")[1]);
    expect(Number(q.get("to")) - Number(q.get("from"))).toBe(24 * 3_600_000);
  });
  it("App 传的问题单:列出来、按编号找、整包下载", async () => {
    const { container: c } = render(<DiagPage say={() => {}} />);
    await waitFor(() => expect(c.querySelectorAll("[data-problems] li").length).toBe(2));
    const li = c.querySelector('[data-code="NW-1110-7F3A"]')!;
    expect(li.textContent).toContain("登不上");
    expect(li.querySelector("a")!.getAttribute("href")).toBe("/api/problem-reports/NW-1110-7F3A/bundle");
    const find = c.querySelector<HTMLInputElement>("[data-problems] input")!;
    find.value = "0b12";
    find.dispatchEvent(new Event("input"));
    await waitFor(() => expect(c.querySelectorAll("[data-problems] li").length).toBe(1));
  });
  it("导出诊断包:场景参数和时间段都进下载地址;选了场景还没选哪一个,按钮灰着", async () => {
    const { bundleHref, toLocalInput, fromLocalInput } = await import("./bundlepanel");
    expect(bundleHref("alert", "A/stuck#1", 1, 2)).toBe("/api/support-bundle?alert=A%2Fstuck%231&from=1&to=2");
    expect(bundleHref("time", "x", 1, 2)).toBe("/api/support-bundle?from=1&to=2");
    const ms = new Date(2026, 10, 7, 8, 35).getTime();
    expect(fromLocalInput(toLocalInput(ms))).toBe(ms);
    const { container: c } = render(<DiagPage say={() => {}} />);
    const sel = c.querySelector<HTMLSelectElement>("#bundle-scene")!;
    sel.value = "robot";
    sel.dispatchEvent(new Event("change"));
    await waitFor(() => expect(c.querySelector("[data-bundle] button[disabled]")).not.toBeNull());
  });
});

describe("系统", () => {
  it("备份没成功写红,VPN 还没装", async () => {
    const { container: c } = render(<SystemPage2 me={{ name: "a", role: "admin", display_name: "", site_name: "翠湖庄园" }} now={0} say={() => {}} />);
    await waitFor(() => expect(c.querySelector(".sys-backup .sys-row")!.className).toContain("bad"));
    expect(c.querySelector(".sys-backup")!.textContent).toContain("9 天");
    expect(c.querySelector(".sys-vpn")!.textContent).toContain("未安装");
    expect(c.textContent).toContain("翠湖庄园");
  });
});

describe("POC 配对码地址", () => {
  it("本机打开(127.0.0.1/localhost)换成局域网地址;没有就不给", () => {
    expect(isLoopbackOrigin("https://127.0.0.1:8443")).toBe(true);
    expect(isLoopbackOrigin("https://localhost:8443")).toBe(true);
    expect(isLoopbackOrigin("https://[::1]:8443")).toBe(true);
    expect(isLoopbackOrigin("https://192.168.1.5:8443")).toBe(false);
    expect(pickPairUrl("https://127.0.0.1:8443", ["https://192.168.1.5:8443"])).toBe("https://192.168.1.5:8443");
    expect(pickPairUrl("https://10.0.0.2:8443", ["https://192.168.1.5:8443"])).toBe("https://10.0.0.2:8443");
    expect(pickPairUrl("https://localhost:8443", [])).toBeNull();
    // 用户 11-05:二维码默认就是网页自己的地址(不只是局域网地址),它排在可选的最前
    expect(pairChoices("https://site.example:8443", ["https://192.168.1.5:8443"])).toEqual(["https://site.example:8443", "https://192.168.1.5:8443"]);
    expect(pairChoices("https://192.168.1.5:8443", ["https://192.168.1.5:8443"])).toEqual(["https://192.168.1.5:8443"]);
    expect(pairChoices("https://127.0.0.1:8443", ["https://192.168.1.5:8443"])).toEqual(["https://192.168.1.5:8443"]);
  });

  it("列出局域网地址可点", async () => {
    lanAddrs = ["https://192.168.1.5:8443", "https://10.0.0.7:8443"];
    const { container: c } = render(<SystemPage2 me={{ name: "a", role: "admin", display_name: "", site_name: "x" }} now={0} say={() => {}} />);
    await waitFor(() => expect(c.querySelectorAll("[data-pair-lan] button").length).toBe(2));
    lanAddrs = [];
  });
});

describe("POC 遥控速度档", () => {
  it("显示速度表;改了保存发给站点;不合规的当场说", async () => {
    const { container: c } = render(<SystemPage2 me={{ name: "a", role: "admin", display_name: "", site_name: "x" }} now={0} say={() => {}} />);
    const box = await waitFor(() => { const i = c.querySelector<HTMLInputElement>('.sys-teleop input[name="speeds"]'); expect(i?.value).toBe("0.3, 0.6, 1, 1.3, 1.6, 2"); return i!; });
    fireEvent.input(box, { target: { value: "0.6, 0.3" } });
    expect(c.querySelector(".sys-teleop")!.textContent).toContain("从小到大不重复");
    expect(btn(c.querySelector(".sys-teleop")!, "保存速度档").disabled).toBe(true);
    fireEvent.input(box, { target: { value: "0.3，0.8 1.2" } });
    fireEvent.click(btn(c.querySelector(".sys-teleop")!, "保存速度档"));
    await waitFor(() => expect(posted.find((p) => p.url === "/api/teleop-speeds")?.body).toEqual({ speeds: [0.3, 0.8, 1.2] }));
  });
  it("解析:上限 2.0、最多 8 个", () => {
    expect(parseSpeeds("0.3, 2")).toEqual([0.3, 2]);
    expect(parseSpeeds("0.3, 2.1")).toBeNull();
    expect(parseSpeeds("")).toBeNull();
    expect(parseSpeeds("0, 1")).toBeNull();
    expect(parseSpeeds("1 1")).toBeNull();
    expect(parseSpeeds("0.1 0.2 0.3 0.4 0.5 0.6 0.7 0.8 0.9")).toBeNull();
  });
});

describe("软件升级", () => {
  it("上传要再输密码,在线下载灰着", async () => {
    const { container: c } = render(<UpgradePage say={() => {}} />);
    expect(btn(c, "在线下载").disabled).toBe(true);
    const f = new File([new Uint8Array([1, 2, 3])], "v1.5.0.tar.gz");
    fireEvent.change(c.querySelector('input[name="pkg"]')!, { target: { files: [f] } });
    fireEvent.click(btn(c, "上传升级包"));
    fireEvent.input(document.querySelector('form.confirm-pw input[type="password"]')!, { target: { value: "my-own-password" } });
    fireEvent.submit(document.querySelector("form.confirm-pw")!);
    await waitFor(() => expect(uploads.length).toBe(1));
    expect(uploads[0].headers["X-Nexwar-Confirm"]).toBe("my-own-password");
  });
  it("充电且空闲时切换", async () => {
    const { container: c } = render(<UpgradePage say={() => {}} />);
    await waitFor(() => expect(c.querySelector('[data-release="v1.4.0"]')).not.toBeNull());
    fireEvent.click(btn(c.querySelector('[data-release="v1.4.0"]')!, "充电且空闲时切换"));
    await waitFor(() => expect(posted[0]).toEqual({ url: "/api/robots/A/release", body: { action: "activate", name: "v1.4.0", when: "charging" } }));
  });
});

describe("第 2 轮 P1-73:支持包文件名带日期", () => {
  it("nexwar_support-年月日-时分.tar.gz", async () => {
    const { supportName } = await import("./advdiag");
    expect(supportName(new Date(2026, 10, 8, 9, 5).getTime())).toBe("nexwar_support-20261108-0905.tar.gz");
  });
});
