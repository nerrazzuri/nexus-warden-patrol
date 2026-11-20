// @vitest-environment happy-dom
// 真机 11-20:网页的巡逻记录(App 有、网页没有)—— 列表、筛选、选一趟看照片和判读。
import { cleanup, fireEvent, render, waitFor } from "@testing-library/preact";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { setFetch } from "./api";
import { lang } from "./i18n";
import { PatrolsPage, runResult, runTitle, stampText } from "./patrolspage";

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
const stamp = (d: Date) => d.toISOString().replace(/[-:]/g, "").replace(/\.\d+Z$/, "Z");
const NOW = new Date();
const RUNS = [
  { id: 157, robot_id: "C40221", mission: "TestPatrol", stamp: `${stamp(NOW)}-955734`, photos: 9, finished: true, result: "done",
    judged_ms: 1, verdicts: { normal: 8, abnormal: 1 } },
  { id: 150, robot_id: "C40221", mission: "goto-ab12cd", stamp: "20261101T010000Z", photos: 0, finished: false },
];
let asked: string[] = [];

beforeEach(() => {
  lang.value = "en";
  asked = [];
  setFetch(((url: string) => {
    asked.push(url);
    if (url.startsWith("/api/runs?")) return Promise.resolve(json({ runs: RUNS }));
    if (url === "/api/runs/157") return Promise.resolve(json({ run: RUNS[0], photos: [
      { name: "W2-front.jpg", waypoint: "W2", camera: "front", finding: { verdict: "abnormal", reason: "door open" } },
      { name: "W3-front.jpg", waypoint: "W3", camera: "front", finding: { verdict: "normal", reason: "" }, review: { verdict: "normal", note: "ok" } },
    ] }));
    return Promise.resolve(json({}, 404));
  }) as typeof fetch);
});
afterEach(cleanup);

describe("巡逻记录", () => {
  it("标题、结果说人话;认得带后缀的目录名", () => {
    expect(runTitle({ id: 1, robot_id: "A", mission: "goto-ab12cd" })).toBe("Dispatched manually");
    expect(runTitle({ id: 1, robot_id: "A", mission: "r1", title: "Night loop" })).toBe("Night loop");
    expect(runResult({ id: 1, robot_id: "A", finished: true, result: "aborted" })).toEqual({ text: "Stopped", bad: true });
    expect(stampText("20261120T093408Z-955734")).toMatch(/^2026-11-20 \d\d:\d\d$/);
  });

  it("默认看今天;有异常的标出来;选一趟看每张照片、判读、原图链接", async () => {
    const { container: c } = render(<PatrolsPage role="guard" robots={["C40221"]} />);
    await waitFor(() => expect(c.querySelector('[data-run="157"]')).not.toBeNull());
    expect(c.querySelector('[data-run="150"]')).toBeNull();
    expect(c.querySelector('[data-run="157"]')!.textContent).toContain("Abnormal 1");
    fireEvent.click(c.querySelector('input[data-show="all"]')!);
    await waitFor(() => expect(c.querySelector('[data-run="150"]')!.textContent).toContain("Not completed"));
    fireEvent.click(c.querySelector('[data-run="157"]')!);
    await waitFor(() => expect(c.querySelectorAll(".pt-photos li").length).toBe(2));
    const first = c.querySelector('[data-photo="W2-front.jpg"]')!;
    expect(first.className).toBe("bad");
    expect(first.querySelector("a")!.getAttribute("href")).toBe("/api/runs/157/photos/W2-front.jpg");
    expect(c.querySelector('[data-photo="W3-front.jpg"]')!.textContent).toContain("staff review");
    fireEvent.change(c.querySelector("select[data-pt-robot]")!, { target: { value: "C40221" } });
    await waitFor(() => expect(asked).toContain("/api/runs?limit=200&robot=C40221"));
  });
});
