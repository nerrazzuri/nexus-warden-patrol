// @vitest-environment happy-dom
// 网页易用性第 1 轮 P1-78:机器人退回上一版先确认;站点说不能退的不给按钮。
import { cleanup, fireEvent, render, waitFor } from "@testing-library/preact";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { UpgradePage } from "./advupgrade";
import { setFetch } from "./api";
import { lang } from "./i18n";

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
let posts: { url: string; body: unknown }[] = [];

beforeEach(() => {
  lang.value = "zh";
  posts = [];
  setFetch(((url: string, init?: RequestInit) => {
    if (init?.method === "POST") { posts.push({ url, body: JSON.parse(String(init.body ?? "{}")) }); return Promise.resolve(json({ ack: {} })); }
    if (url === "/api/releases") return Promise.resolve(json({ releases: [], robots: { A: "v1", B: "v1", C: null }, rollback: { A: true, B: false } }));
    if (url === "/api/versions") return Promise.resolve(json({ site: { version: "1.0" }, robots: [] }));
    return Promise.resolve(json({}, 404));
  }) as typeof fetch);
});
afterEach(cleanup);

describe("P1-78 退回上一版", () => {
  it("第 2 轮 P1-78:没报版本的写为什么", async () => {
    const { container: c } = render(<UpgradePage say={() => {}} />);
    await waitFor(() => expect(c.querySelector('[data-robot="C"] [data-no-release]')).not.toBeNull());
    expect(c.querySelector('[data-robot="A"] [data-no-release]')).toBeNull();
  });

  it("先确认再发;不能退的那台没有按钮", async () => {
    const { container: c } = render(<UpgradePage say={() => {}} />);
    const rowA = await waitFor(() => { const r = c.querySelector('[data-robot="A"]'); expect(r).not.toBeNull(); return r as HTMLElement; });
    expect(c.querySelector('[data-robot="B"] button')).toBeNull();
    expect(c.querySelector('[data-robot="B"]')!.textContent).toContain("不能退回上一版");
    fireEvent.click(rowA.querySelector("button")!);
    expect(posts).toEqual([]);
    const m = c.ownerDocument.querySelector(".modal") as HTMLElement;
    fireEvent.click(Array.from(m.querySelectorAll("button")).find((b) => b.textContent === "回退到上一版本")!);
    await waitFor(() => expect(posts).toContainEqual({ url: "/api/robots/A/release", body: { action: "rollback" } }));
  });
});

describe("网页易用性第 1 轮 P2-24", () => {
  it("同一个账号同一个 App 版本的多次登录合成一行,写登录过几次", async () => {
    const { groupClients } = await import("./admin");
    const g = groupClients([
      { name: "gina", kind: "app", version: "1.0.0", platform: "android", last_used: 10 },
      { name: "gina", kind: "app", version: "1.0.0", platform: "android", last_used: 30 },
      { name: "gina", kind: "web", last_used: 20 },
      { name: "olga", kind: "app", version: "1.0.0", platform: "android", last_used: 5 },
    ]);
    expect(g.map((x) => [x.name, x.kind, x.n, x.last_used])).toEqual([["gina", "app", 2, 30], ["gina", "web", 1, 20], ["olga", "app", 1, 5]]);
  });
});

describe("第 2 轮 config N10", () => {
  it("平台名写成人认得的", async () => {
    const { platformName } = await import("./advupgrade");
    expect(platformName("android")).toBe("Android");
    expect(platformName("ios")).toBe("iOS");
    expect(platformName("tizen")).toBe("tizen");
  });
});

describe("第 3 轮 config N11 / P1-77", () => {
  it("没报版本的不再接着给「退回」或「软件太老」", async () => {
    const { container: c } = render(<UpgradePage say={() => {}} />);
    await waitFor(() => expect(c.querySelector('[data-robot="C"] [data-no-release]')).not.toBeNull());
    expect(c.querySelector('[data-robot="C"] button')).toBeNull();
    expect(c.querySelector('[data-robot="C"]')!.textContent).not.toContain("不能退回");
  });

  it("包不对(400 / 409 / 413)跟密码不对(403)分开", async () => {
    const { ApiError, badPackage } = await import("./api");
    expect(badPackage(new ApiError(400, "签名不匹配"))).toBe(true);
    expect(badPackage(new ApiError(409, "已存在"))).toBe(true);
    expect(badPackage(new ApiError(403, "密码不对"))).toBe(false);
  });
});

describe("真机 11-20:点了装、切以后看得见结果", () => {
  it("机器人拒了不再说「正在切换」;最近一条命令、事件、排队都写出来,排队能取消", async () => {
    const said: string[] = [];
    setFetch(((url: string, init?: RequestInit) => {
      if (init?.method === "POST") {
        const body = JSON.parse(String(init.body ?? "{}"));
        posts.push({ url, body });
        return Promise.resolve(json(body.action === "unqueue" ? { removed: true } : { ack: { result: "rejected", reason: "busy" } }));
      }
      if (url === "/api/releases") return Promise.resolve(json({
        releases: [{ name: "r27" }], robots: { A: "v1" }, rollback: { A: true },
        last: { A: { cmd: { kind: "release_activate", name: "r27", at_ms: 0, result: "rejected", reason: "busy" },
                     event: { kind: "release_committed", name: "v1", at_ms: 0 } } },
        queue: [{ robot_id: "A", name: "r27", last_reason: "busy", retry_at_ms: 0 }],
      }));
      if (url === "/api/versions") return Promise.resolve(json({ site: { version: "1.0" }, robots: [] }));
      return Promise.resolve(json({}, 404));
    }) as typeof fetch);
    const { container: c } = render(<UpgradePage say={(s) => said.push(s)} />);
    const st = await waitFor(() => { const r = c.querySelector('[data-up-status="A"]'); expect(r).not.toBeNull(); return r as HTMLElement; });
    expect(st.querySelector('[data-up-cmd="rejected"]')!.textContent).toContain("切换到 r27");
    expect(st.querySelector('[data-up-event="release_committed"]')!.textContent).toContain("现在运行 v1");
    expect(st.querySelector('[data-up-queue="r27"]')!.textContent).toContain("排队中");
    fireEvent.click(Array.from(c.querySelectorAll("button")).find((b) => b.textContent === "立即切换")!);
    await waitFor(() => expect(said.some((s) => s.startsWith("A 拒绝"))).toBe(true));
    expect(said.some((s) => s.includes("正在切换"))).toBe(false);
    fireEvent.click(Array.from(st.querySelectorAll("button")).find((b) => b.textContent === "取消排队")!);
    await waitFor(() => expect(posts).toContainEqual({ url: "/api/robots/A/release", body: { action: "unqueue" } }));
  });
});

describe("真机 11-25:看得出是几号构建、下载有进度条、忙的时候说在忙什么", () => {
  const page = (rel: unknown, site: unknown = { version: "1.0.0-rc.1", release_build: 36, release_name: "2026-11-26-abcdef12" }) => {
    setFetch(((url: string, init?: RequestInit) => {
      if (init?.method === "POST") return Promise.resolve(json({ ack: {} }));
      if (url === "/api/releases") return Promise.resolve(json(rel));
      if (url === "/api/versions") return Promise.resolve(json({ site, robots: [] }));
      return Promise.resolve(json({}, 404));
    }) as typeof fetch);
    return render(<UpgradePage say={() => {}} />).container;
  };

  it("站点自己一行写清是这台电脑、几号构建;机器人和升级包也写构建号;升级包那一栏不再叫「站点上的…」", async () => {
    const c = page({ releases: [{ name: "2026-11-26-abcdef12", build: 36 }, { name: "2026-11-24-166a47ee" }], robots: { A: "2026-11-24-166a47ee" }, builds: { A: null } });
    const site = await waitFor(() => { const r = c.querySelector("[data-site-version]"); expect(r?.textContent).toContain("构建 36"); return r!; });
    expect(site.textContent).toContain("站点（这台电脑）");
    expect(site.textContent).toContain("2026-11-26-abcdef12");
    expect(c.querySelector('[data-release="2026-11-26-abcdef12"]')!.textContent).toContain("构建 36");
    expect(c.querySelector('[data-release="2026-11-24-166a47ee"]')!.textContent).not.toContain("构建");
    expect(c.textContent).toContain("机器人升级包（存在站点上）");
    expect(c.textContent).not.toContain("站点上的升级包");
  });

  it("装的时候有进度条(哪一步、百分比);装好了就没了", async () => {
    const c = page({ releases: [], robots: { A: "v1" }, builds: { A: 35 },
      last: { A: { cmd: { kind: "release_install", name: "r36", at_ms: 1, result: "accepted" }, event: null,
                   progress: { name: "r36", stage: "superlio", pct: 80, at_ms: 2 } } } });
    const bar = await waitFor(() => { const b = c.querySelector('[data-up-progress="install"]'); expect(b).not.toBeNull(); return b!; });
    expect(bar.textContent).toContain("编译 Super-LIO");
    expect(bar.textContent).toContain("80%");
    expect(bar.querySelector('[role="progressbar"]')!.getAttribute("aria-valuenow")).toBe("80");
    expect(c.querySelector('[data-robot="A"]')!.textContent).toContain("v1 · 构建 35");
  });

  it("切换:收下了、正在重启各一格;新版跑起来就没进度条了", async () => {
    let c = page({ releases: [], robots: { A: "v1" },
      last: { A: { cmd: { kind: "release_activate", name: "r36", at_ms: 5, result: "accepted" },
                   event: { kind: "release_activating", name: "r36", at_ms: 6 } } } });
    const bar = await waitFor(() => { const b = c.querySelector('[data-up-progress="activate"]'); expect(b).not.toBeNull(); return b!; });
    expect(bar.textContent).toContain("正在用新版重启");
    cleanup();
    c = page({ releases: [], robots: { A: "r36" },
      last: { A: { cmd: { kind: "release_activate", name: "r36", at_ms: 5, result: "accepted" },
                   event: { kind: "release_committed", name: "r36", at_ms: 9 } } } });
    await waitFor(() => expect(c.querySelector('[data-up-event="release_committed"]')).not.toBeNull());
    expect(c.querySelector("[data-up-progress]")).toBeNull();
  });

  it("拒的原因是「忙」:写在忙什么,不只是 busy(中文、英文)", async () => {
    const why = "busy: 正在装 r36(编 Super-LIO,80%) —— 重启那几秒谁都无法停止它,等它完";
    const rel = { releases: [], robots: { A: "v1" }, last: { A: { cmd: { kind: "release_activate", name: "r36", at_ms: 5, result: "rejected", reason: why }, event: null } } };
    let c = page(rel);
    let line = await waitFor(() => { const p = c.querySelector('[data-up-cmd="rejected"]'); expect(p).not.toBeNull(); return p!; });
    expect(line.textContent).toContain("机器人在忙：正在装 r36");
    expect(line.textContent).not.toContain("busy");
    cleanup();
    lang.value = "en";
    c = page(rel);
    line = await waitFor(() => { const p = c.querySelector('[data-up-cmd="rejected"]'); expect(p).not.toBeNull(); return p!; });
    expect(line.textContent).toContain("The robot is busy: installing r36 (building Super-LIO, 80%)");
  });
});
