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
    if (url === "/api/releases") return Promise.resolve(json({ releases: [], robots: { A: "v1", B: "v1" }, rollback: { A: true, B: false } }));
    if (url === "/api/versions") return Promise.resolve(json({ site: { version: "1.0" }, robots: [] }));
    return Promise.resolve(json({}, 404));
  }) as typeof fetch);
});
afterEach(cleanup);

describe("P1-78 退回上一版", () => {
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
