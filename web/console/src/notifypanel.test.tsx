// @vitest-environment happy-dom
// 1.1-2 告警外发:「系统」页的告警渠道 —— 加一个 WhatsApp 渠道、发测试、删要确认;令牌改的时候空着不发;读不到就不显示。
import { cleanup, fireEvent, render, waitFor } from "@testing-library/preact";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { setFetch } from "./api";
import { lang } from "./i18n";
import { NotifyPanel } from "./notifypanel";

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
let channels: Record<string, unknown>[];
let posts: [string, Record<string, unknown>][];
let status: number;

const view = () => ({ channels, recent: [{ id: 1, alert_key: "R1/fallen#1", tier: 1, channel: "主管", created_ms: 1, sent_ms: 2, dropped: "", error: "" }], sealed: true, hourly_cap: 30 });

beforeEach(() => {
  lang.value = "zh";
  posts = [];
  status = 200;
  channels = [{ id: 7, kind: "telegram", name: "主管", targets: ["-100"], levels: ["P1"], lang: "en", enabled: true, config: {}, has_secret: true, last_ok_ms: null, last_error: "连不上" }];
  setFetch(((url: string, init?: RequestInit) => {
    if (init?.method === "POST") {
      const body = JSON.parse(String(init.body || "{}"));
      posts.push([url, body]);
      if (url.endsWith("/test")) return Promise.resolve(json({ ok: true, error: "" }));
      if (url.endsWith("/remove")) { channels = []; return Promise.resolve(json(view())); }
      const ch = { id: 8, has_secret: true, last_ok_ms: null, last_error: "", config: {}, ...body };
      channels = [...channels, ch];
      return Promise.resolve(json(ch));
    }
    if (url === "/api/notify") return Promise.resolve(status === 200 ? json(view()) : json({ error: "x" }, status));
    return Promise.resolve(json({}, 404));
  }) as typeof fetch);
});
afterEach(cleanup);

const btn = (text: string) => Array.from(document.querySelectorAll("button")).filter((b) => b.textContent === text).pop()!;
const input = (c: Element, name: string, v: string) => fireEvent.input(c.querySelector(`[name="${name}"]`)!, { target: { value: v } });

describe("告警渠道", () => {
  it("列出渠道和出错原因;发测试;加 WhatsApp 渠道带模板和令牌", async () => {
    let said = "";
    const { container: c } = render(<NotifyPanel say={(s) => { said = s; }} />);
    await waitFor(() => expect(c.querySelector('[data-channel="主管"]')).not.toBeNull());
    expect(c.querySelector('[data-channel="主管"]')!.textContent).toContain("发送失败：连不上");
    expect(c.querySelector("[data-notify-recent]")!.textContent).toContain("仍未确认");
    fireEvent.click(btn("发测试"));
    await waitFor(() => expect(said).toContain("测试消息已发给 主管"));
    fireEvent.click(btn("加一个渠道"));
    const f = c.querySelector("[data-notify-form]")!;
    input(f, "name", "经理 WhatsApp");
    input(f, "targets", "+60123456789, +60198765432");
    input(f, "phone_number_id", "1234567");
    input(f, "template", "nexwar_alert");
    input(f, "secret", "EAAtok");
    fireEvent.click(f.querySelector('[name="level-P2"]')!);
    fireEvent.submit(f);
    await waitFor(() => expect(posts.some(([u]) => u === "/api/notify")).toBe(true));
    const [, body] = posts.find(([u]) => u === "/api/notify")!;
    expect(body).toMatchObject({ kind: "whatsapp", name: "经理 WhatsApp", targets: ["+60123456789", "+60198765432"], levels: ["P1", "P2"], secret: "EAAtok" });
    expect((body.config as Record<string, string>).template).toBe("nexwar_alert");
    await waitFor(() => expect(said).toBe("渠道 经理 WhatsApp 已保存。"));
  });

  it("改的时候令牌空着不发(保留原来的);删要先确认", async () => {
    const { container: c } = render(<NotifyPanel say={() => {}} />);
    await waitFor(() => expect(c.querySelector('[data-channel="主管"]')).not.toBeNull());
    fireEvent.click(btn("修改"));
    const f = c.querySelector("[data-notify-form]")!;
    expect((f.querySelector('[name="kind"]') as HTMLSelectElement).disabled).toBe(true);
    input(f, "name", "主管群");
    fireEvent.submit(f);
    await waitFor(() => expect(posts.length).toBe(1));
    expect(posts[0][0]).toBe("/api/notify/7");
    expect("secret" in posts[0][1]).toBe(false);
    expect("kind" in posts[0][1]).toBe(false);
    fireEvent.click(btn("删除"));
    expect(posts.length).toBe(1);
    fireEvent.click(btn("删除"));
    await waitFor(() => expect(posts.map(([u]) => u)).toContain("/api/notify/7/remove"));
  });

  it("没管理权限:整块不显示", async () => {
    status = 403;
    const { container: c } = render(<NotifyPanel say={() => {}} />);
    await new Promise((r) => setTimeout(r, 30));
    expect(c.querySelector("[data-notify]")).toBeNull();
  });
});
