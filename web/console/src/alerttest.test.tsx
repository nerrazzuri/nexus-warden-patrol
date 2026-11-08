// @vitest-environment happy-dom
// POC 第 8 项:告警测试模式条幅 —— 管理员开、结束并清掉(先确认);保安只看得到条幅。
import { cleanup, fireEvent, render, waitFor } from "@testing-library/preact";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { AlertTestBar } from "./alerttest";
import { setFetch } from "./api";
import { alertTitle, lang } from "./i18n";

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
let mode: Record<string, unknown>;
// 结束时刻放在一小时以后(写死某天的钟点,过了那天测试就坏)
const END_AT = Date.now() + 3600_000;
const endHm = () => { const d = new Date(END_AT); return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`; };
let posted: unknown[];

beforeEach(() => {
  lang.value = "zh";
  posted = [];
  mode = { active: false, until_ms: null, by: "" };
  setFetch(((url: string, init?: RequestInit) => {
    if (url === "/api/alert-test" && init?.method === "POST") {
      const b = JSON.parse(String(init.body));
      posted.push(b);
      mode = b.action === "start" ? { active: true, until_ms: END_AT, by: "alice" }
        : { active: false, until_ms: null, by: "", cleared: b.clear ? 3 : 0 };
      return Promise.resolve(json(mode));
    }
    if (url === "/api/alert-test") return Promise.resolve(json(mode));
    return Promise.resolve(json({}, 404));
  }) as typeof fetch);
});
afterEach(cleanup);
const btn = (root: Element | Document, text: string) => Array.from(root.querySelectorAll("button")).find((b) => b.textContent?.trim() === text) as HTMLButtonElement;

describe("告警测试模式", () => {
  it("外审 r1 #9:认识的种类换成译文,测试前缀也照样标出来", () => {
    expect(alertTitle("en", "stuck", "测试：被挡住了")).toMatch(/^TEST: /);
    expect(alertTitle("zh", "stuck", "测试：被挡住了")).toMatch(/^测试：/);
    expect(alertTitle("en", "stuck", "被挡住了")).not.toMatch(/TEST/);
  });
  it("管理员开 30 分钟 → 条幅写到几点;结束并清掉先确认,说删了几条", async () => {
    let cleared = 0;
    const { container: c } = render(<AlertTestBar role="admin" onCleared={() => cleared++} />);
    await waitFor(() => expect(btn(c, "开始报警演练")).toBeTruthy());
    fireEvent.click(btn(c, "开始报警演练"));
    await waitFor(() => expect(c.querySelector('[data-alert-test="on"]')?.textContent).toContain(`到 ${endHm()} 结束`));
    expect(posted).toEqual([{ action: "start", minutes: 30 }]);
    fireEvent.click(btn(c, "结束演练并删掉演练报警"));
    expect(posted.length).toBe(1);
    const dlg = await waitFor(() => { const x = document.querySelector("dialog"); expect(x).toBeTruthy(); return x!; });
    fireEvent.click(btn(dlg, "结束演练并删掉演练报警"));
    // 第 2 轮 P1-19:不写条数(站点数的含保安看不到的记录)
    await waitFor(() => expect(c.textContent).toContain("演练报警都已删掉"));
    expect(posted[1]).toEqual({ action: "end", clear: true });
    expect(cleared).toBe(1);
  });

  it("外审 r1 #10:别的管理员开了、到点了,条幅自己跟着变", async () => {
    const { container: c } = render(<AlertTestBar role="guard" onCleared={() => {}} pollMs={30} />);
    await new Promise((r) => setTimeout(r, 20));
    expect(c.querySelector("[data-alert-test]")).toBeNull();
    mode = { active: true, until_ms: Date.now() + 150, by: "alice" };
    await waitFor(() => expect(c.querySelector('[data-alert-test="on"]')).toBeTruthy());
    await waitFor(() => expect(c.querySelector("[data-alert-test]")).toBeNull(), { timeout: 1000 });
  });

  it("保安:没开什么都不显示;开着只看条幅,没有按钮", async () => {
    const { container: c } = render(<AlertTestBar role="guard" onCleared={() => {}} />);
    await new Promise((r) => setTimeout(r, 20));
    expect(c.querySelector("[data-alert-test]")).toBeNull();
    cleanup();
    mode = { active: true, until_ms: Date.now() + 60_000, by: "alice" };
    const { container: c2 } = render(<AlertTestBar role="guard" onCleared={() => {}} />);
    await waitFor(() => expect(c2.querySelector('[data-alert-test="on"]')).toBeTruthy());
    expect(c2.querySelectorAll("button").length).toBe(0);
    expect(c2.textContent).toContain("照常处理即可");                         // P1-21:只读、保安看一句人话
    cleanup();
    // 第 2 轮 duty N12:只读账号不能处理,不写「照常处理」
    const { container: c3 } = render(<AlertTestBar role="viewer" onCleared={() => {}} />);
    await waitFor(() => expect(c3.querySelector('[data-alert-test="on"]')).toBeTruthy());
    expect(c3.textContent).toContain("你不用做什么");
    expect(c3.textContent).not.toContain("照常处理");
  });

  it("P1-18/19:没开时收着、写清用途;开着时「只结束」在前,删记录的不是醒目的红按钮", async () => {
    const { container: c } = render(<AlertTestBar role="admin" onCleared={() => {}} />);
    await waitFor(() => expect(c.querySelector("details.at-off")).not.toBeNull());
    expect(c.textContent).toContain("不会自己造报警");
    cleanup();
    mode = { active: true, until_ms: Date.now() + 60_000, by: "alice" };
    const { container: c2 } = render(<AlertTestBar role="admin" onCleared={() => {}} />);
    await waitFor(() => expect(c2.querySelector('[data-alert-test="on"]')).toBeTruthy());
    const bs = Array.from(c2.querySelectorAll("button"));
    expect(bs[0].textContent).toBe("结束演练（保留记录）");
    expect(c2.querySelector("button.stop")).toBeNull();
  });
});


describe("第 3 轮 duty N10", () => {
  it("结束并删掉:确认框写共几条、列出标题", async () => {
    mode = { active: true, until_ms: END_AT, by: "alice", alarms: [{ key: "k1", title: "测试：卡住了" }, { key: "k2", title: "测试：看见人" }] };
    const { container: c } = render(<AlertTestBar role="admin" onCleared={() => {}} />);
    await waitFor(() => expect(c.querySelector('[data-alert-test="on"]')).not.toBeNull());
    fireEvent.click(btn(c, "结束演练并删掉演练报警"));
    const list = await waitFor(() => { const l = document.querySelector("[data-drill-list]"); expect(l).not.toBeNull(); return l!; });
    expect(list.querySelectorAll("li").length).toBe(2);
    expect(document.querySelector(".confirm-text")!.textContent).toContain("2 条");
  });
});
