// UIUX-027(第二档 #36):布置页各页签的「新建」按钮一个样子 —— 普通高(md)主按钮、左对齐、不撑满整宽。
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const src = (f: string) => readFileSync(`${process.cwd()}/src/${f}`, "utf-8");
const flat = src("styles.css").replace(/\/\*[\s\S]*?\*\//g, "").replace(/\s+/g, " ");

describe("UIUX-027 新建按钮一个样子", () => {
  it("添加摄像头、添加待命点、新建路线都是 btn primary ly-new(不是 sm)", () => {
    for (const [f, key] of [["layoutcams.tsx", "lyAddCam"], ["layoutstandby.tsx", "lyAddStandby"], ["routepage.tsx", "routeNewBtn"]]) {
      const m = new RegExp(`<button[^\\n]*class="([^"]*)"[^\\n]*\\{r?t\\("${key}"\\)\\}`).exec(src(f));
      expect(m?.[1].split(" ").sort(), f).toEqual(["btn", "ly-new", "primary"]);
    }
  });
  it(".ly-new 左对齐、按内容宽", () => {
    expect(flat).toMatch(/\.ly-new \{[^}]*align-self: ?flex-start[^}]*width: ?auto/);
  });
});

describe("UIUX-016 日程新增表单", () => {
  const routesCss = src("routes.css").replace(/\/\*[\s\S]*?\*\//g, "").replace(/\s+/g, " ");
  it("字段按网格排(一行放几个),星期 / 说明 / 按钮占整行;「加排程」是主按钮", () => {
    expect(routesCss).toMatch(/\.sched-form \{[^}]*display: ?grid[^}]*grid-template-columns: ?repeat\(auto-fit, ?minmax\(220px, ?1fr\)\)/);
    expect(routesCss).toMatch(/\.sched-form > fieldset, ?\.sched-form > p, ?\.sched-form > \.sched-add \{[^}]*grid-column: ?1 ?\/ ?-1/);
    expect(src("routepage.tsx")).toMatch(/class="btn primary sched-add"/);
  });
});

describe("UIUX-033 报表 KPI", () => {
  it("一组里的卡片按宽度自动折行(每张至少 200px),不硬塞 3 列", () => {
    expect(flat).toMatch(/\.kpi-row \{[^}]*grid-template-columns: ?repeat\(auto-fit, ?minmax\(200px, ?1fr\)\)/);
  });
});
