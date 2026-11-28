// @vitest-environment happy-dom
// 1.1-5 值班簿:列一天(手写的 + 站点记的);写一条带类别、补记时间;更正另写一条带 corrects;
// 只读账号不能写;打印开站点出的那一页;只看手写的 / 站点记的。
import { cleanup, fireEvent, render, waitFor } from "@testing-library/preact";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { setFetch } from "./api";
import { lang } from "./i18n";
import { dayRange, ObPage } from "./obpage";

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
let gets: string[];
let posts: Record<string, unknown>[];
const NOW = new Date(2026, 10, 28, 15, 0).getTime();

beforeEach(() => {
  lang.value = "en";
  gets = [];
  posts = [];
  setFetch(((url: string, init?: RequestInit) => {
    if (init?.method === "POST") {
      posts.push(JSON.parse(String(init.body)));
      return Promise.resolve(json({ entry: { id: 9 } }));
    }
    gets.push(url);
    return Promise.resolve(json({ entries: [
      { at_ms: NOW - 3600_000, source: "manual", category: "visitor", text: "Lorry WXY 1234 in", author: "gina", robot: "", id: 3, corrected_by: 4 },
      { at_ms: NOW - 3500_000, source: "manual", category: "visitor", text: "Plate is WXY 1243", author: "gina", robot: "", id: 4, corrects: 3 },
      { at_ms: NOW - 3000_000, source: "alarm", category: "alarm", text: "P1 Intruder north", author: "", robot: "A", alert: "A/intrusion#1" },
    ] }));
  }) as typeof fetch);
});
afterEach(cleanup);

describe("值班簿", () => {
  it("列这一天:更正过的划掉、写由哪条更正;打印开站点那一页", async () => {
    const { container: c } = render(<ObPage role="guard" me="gina" now={NOW} />);
    await waitFor(() => expect(c.querySelector('[data-ob-row="3"]')).not.toBeNull());
    const r = dayRange("2026-11-28");
    expect(gets[0]).toBe(`/api/ob?since=${r.since}&until=${r.until}&lang=en`);
    expect(c.querySelector('[data-ob-row="3"]')!.className).toContain("ob-fixed");
    expect(c.querySelector('[data-ob-row="3"]')!.textContent).toContain("(corrected by #4)");
    expect(c.querySelector('[data-ob-row="4"]')!.textContent).toContain("Correction to #3:");
    expect(c.querySelector('[data-ob-fix="3"]')).toBeNull();
    expect(c.querySelector('[data-ob-source="alarm"]')!.textContent).toContain("P1 Intruder north");
    expect(c.querySelector<HTMLAnchorElement>("[data-ob-print]")!.getAttribute("href")).toBe(`/api/ob/print?since=${r.since}&until=${r.until}&lang=en`);
    fireEvent.click(Array.from(c.querySelectorAll("button")).find((b) => b.textContent === "Written")!);
    expect(c.querySelector('[data-ob-source="alarm"]')).toBeNull();
  });

  it("写一条:类别、内容、补记时间;更正带 corrects", async () => {
    const { container: c } = render(<ObPage role="guard" me="gina" now={NOW} />);
    await waitFor(() => expect(c.querySelector('[data-ob-row="4"]')).not.toBeNull());
    fireEvent.change(c.querySelector('[name="category"]')!, { target: { value: "patrol" } });
    fireEvent.input(c.querySelector('[name="text"]')!, { target: { value: "North fence checked" } });
    fireEvent.input(c.querySelector('[name="when"]')!, { target: { value: "2026-11-28T14:30" } });
    fireEvent.click(Array.from(c.querySelectorAll("button")).find((b) => b.textContent === "Add entry")!);
    await waitFor(() => expect(posts.length).toBe(1));
    expect(posts[0]).toEqual({ category: "patrol", text: "North fence checked", at_ms: new Date("2026-11-28T14:30").getTime() });
    fireEvent.click(c.querySelector('[data-ob-fix="4"]')!);
    expect(c.querySelector("[data-ob-fixing]")!.textContent).toContain("Correcting entry #4");
    fireEvent.input(c.querySelector('[name="text"]')!, { target: { value: "Plate is WXY 1248" } });
    const add = Array.from(c.querySelectorAll("button")).find((b) => b.textContent === "Add entry")!;
    await waitFor(() => expect(add.disabled).toBe(false));
    fireEvent.click(Array.from(c.querySelectorAll("button")).find((b) => b.textContent === "Add entry")!);
    await waitFor(() => expect(posts.length).toBe(2));
    expect(posts[1]).toEqual({ category: "visitor", text: "Plate is WXY 1248", corrects: 4 });
  });

  it("只读账号:不能写", async () => {
    const { container: c } = render(<ObPage role="viewer" now={NOW} />);
    await waitFor(() => expect(c.querySelector('[data-ob-row="4"]')).not.toBeNull());
    expect(c.querySelector("[data-ob-write]")).toBeNull();
    expect(c.querySelector("[data-ob-fix]")).toBeNull();
  });
});
