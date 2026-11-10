// @vitest-environment happy-dom
// 第 4 轮 duty N1 / N2 / r3-N10:结束演练的提示、要删的清单(人话、哪台、几点)、逐条留下
import { cleanup, fireEvent, render, waitFor } from "@testing-library/preact";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { AlertTestBar as AlertTest } from "./alerttest";
import { setFetch } from "./api";
import { lang } from "./i18n";

const json = (b: unknown) => new Response(JSON.stringify(b), { status: 200, headers: { "Content-Type": "application/json" } });
let posted: Record<string, unknown>[];
const MODE = { active: true, until_ms: Date.now() + 60_000, by: "alice",
  alarms: [{ key: "A/fallen#1", kind: "fallen", robot: "A", title: "测试：机器人摔倒", first_ms: Date.now() },
    { key: "site/intrusion_unanswered#2", kind: "intrusion_unanswered", robot: "site", title: "测试：防区 东区 有入侵,无机器人去:没有能派的机器人", first_ms: Date.now() }] };
beforeEach(() => {
  lang.value = "en";
  posted = [];
  setFetch(((_url: string, init?: RequestInit) => {
    if (init?.method === "POST") {
      const b = JSON.parse(String(init.body));
      posted.push(b);
      return Promise.resolve(json({ active: false, until_ms: null, by: "", ...(b.clear ? { cleared: 1 } : { cleared: 0 }) }));
    }
    return Promise.resolve(json(MODE));
  }) as typeof fetch);
});
afterEach(() => { cleanup(); lang.value = "zh"; });

describe("结束演练", () => {
  it("保留记录:不说都删了", async () => {
    const { container: c } = render(<AlertTest role="admin" onCleared={() => {}} />);
    await waitFor(() => expect(c.querySelector('[data-alert-test="on"]')).not.toBeNull());
    fireEvent.click(Array.from(c.querySelectorAll("button")).find((b) => b.textContent?.includes("keep"))!);
    await waitFor(() => expect(c.querySelector('[role="status"]')?.textContent).toContain("are kept"));
  });

  it("清单是英文、写哪台;取消勾选的留着", async () => {
    const { container: c } = render(<AlertTest role="admin" onCleared={() => {}} />);
    await waitFor(() => expect(c.querySelector('[data-alert-test="on"]')).not.toBeNull());
    const label = c.querySelector(".at-acts .ghost")!.textContent;
    fireEvent.click(c.querySelector(".at-acts .ghost")!);
    const list = await waitFor(() => document.querySelector("[data-drill-list]")!);
    expect(list.textContent).not.toMatch(/[㐀-鿿]/);
    expect(list.textContent).toContain("A · ");
    fireEvent.click(list.querySelector('[data-drill-key="A/fallen#1"]')!);
    const yes = Array.from(document.querySelectorAll(".modal button")).find((b) => b.textContent === label)!;
    fireEvent.click(yes);
    await waitFor(() => expect(posted.at(-1)).toEqual({ action: "end", clear: true, keep: ["A/fallen#1"] }));
  });
});
