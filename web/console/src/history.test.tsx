// @vitest-environment happy-dom
// liang-d5 第 5 轮前:全站活动日志(按日期、人、类别查,翻页,导出)、往天的巡逻。
import { cleanup, fireEvent, render, waitFor } from "@testing-library/preact";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { ActivityPage, activityQuery } from "./activitypage";
import { setFetch } from "./api";
import { lang } from "./i18n";
import { TodayPatrols } from "./todaypatrols";

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
let calls: string[] = [];
let total = 3;

beforeEach(() => {
  lang.value = "zh";
  calls = [];
  total = 3;
  setFetch(((url: string) => {
    calls.push(url);
    if (url.startsWith("/api/audit?")) {
      const q = new URLSearchParams(url.split("?")[1]);
      const off = Number(q.get("offset") ?? 0);
      return Promise.resolve(json({ total, audit: [
        { id: 10 + off, at: Date.now(), actor: "gina", action: "POST /api/mode", target: "disarmed", status: 200 },
        { id: 11 + off, at: Date.now(), actor: "olga", action: "POST /api/robots/A/goto", target: "A", status: 200 },
      ] }));
    }
    if (url === "/api/patrols/today") return Promise.resolve(json({ date: "2026-11-08", utc_offset_min: 480, items: [] }));
    if (url.startsWith("/api/patrols/day?date=")) return Promise.resolve(json({ date: url.slice(-10), utc_offset_min: 480, items: [
      { at_ms: Date.UTC(2026, 10, 5, 14, 0), kind: "schedule", label: "夜巡", robot: "A", by: "", state: "aborted", reason: "", end_ms: null, adhoc_id: "", stopped_by: "gina" },
    ] }));
    return Promise.resolve(json({}));
  }) as typeof fetch);
});
afterEach(() => { cleanup(); lang.value = "en"; });

describe("全站活动日志", () => {
  it("查询串:日期范围、人、类别;结束早于开始回 null", () => {
    const q = activityQuery({ from: "2026-11-05", to: "2026-11-05", actor: " gina ", group: "arming" })!;
    expect(q).toContain("actor=gina");
    expect(q).toContain("group=arming");
    expect(activityQuery({ from: "2026-11-06", to: "2026-11-05", actor: "", group: "" })).toBeNull();
  });

  it("每行写是谁、做了什么;按类别筛去站点查;导出链接带同样的条件", async () => {
    const { container: c } = render(<ActivityPage now={Date.now()} />);
    await waitFor(() => expect(c.querySelectorAll("[data-audit]").length).toBe(2));
    expect(c.querySelector("[data-audit]")!.textContent).toContain("gina");
    fireEvent.change(c.querySelector("select")!, { target: { value: "arming" } });
    await waitFor(() => expect(calls.at(-1)).toContain("group=arming"));
    expect(c.querySelector<HTMLAnchorElement>("[data-export]")!.getAttribute("href")).toMatch(/group=arming&format=csv$/);
  });

  it("超过一页能翻", async () => {
    total = 450;
    const { container: c } = render(<ActivityPage now={Date.now()} />);
    await waitFor(() => expect(c.querySelector("[data-act-pages]")!.textContent).toContain("共 450 条"));
    fireEvent.click([...c.querySelectorAll("button")].find((b) => b.textContent === "下一页")!);
    await waitFor(() => expect(calls.at(-1)).toContain("offset=200"));
  });
});

describe("往天的巡逻", () => {
  it("选个日期去站点查那天;能回到今天", async () => {
    const { container: c } = render(<TodayPatrols />);
    await waitFor(() => expect(c.querySelector<HTMLInputElement>("input[type=date]")!.value).toBe("2026-11-08"));
    fireEvent.change(c.querySelector("input[type=date]")!, { target: { value: "2026-11-05" } });
    await waitFor(() => expect(c.querySelectorAll(".today-row").length).toBe(1));
    expect(calls).toContain("/api/patrols/day?date=2026-11-05");
    expect(c.querySelector(".today-h")!.textContent).toContain("2026-11-05 的巡逻");
    expect(c.querySelector(".today-row")!.textContent).toContain("gina");
    fireEvent.click([...c.querySelectorAll("button")].find((b) => b.textContent === "今天")!);
    await waitFor(() => expect(c.querySelector(".today-h")!.textContent).not.toContain("2026-11-05"));
  });
});
