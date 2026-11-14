// UIUX-004 / UIUX-005(第二档 #25 #26):控件三档高 sm 32 / md 40 / lg 44,按钮字两档(sm 13、其余 14,都 600);
// 复选框一个尺寸 18px(触屏 22)。这里看样式表里每类控件「最后一条」规则用的是不是这几个变量。
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const flat = readFileSync(`${process.cwd()}/src/styles.css`, "utf-8").replace(/\/\*[\s\S]*?\*\//g, "").replace(/\s+/g, " ");
// 不在 @media 里的规则(媒体查询里的另算)
const top = flat.replace(/@media[^{]*\{(?:[^{}]*\{[^}]*\})*[^{}]*\}/g, "");

/** 选择器列表里正好有 sel 的规则,最后一条里 prop 的值。 */
function last(sel: string, prop: string): string | undefined {
  let v: string | undefined;
  for (const m of top.matchAll(/([^{}]+)\{([^}]*)\}/g)) {
    const sels = m[1].split(",").map((x) => x.trim());
    if (!sels.includes(sel)) continue;
    const d = new RegExp(`(?:^|;)\\s*${prop}:\\s*([^;]+)`).exec(m[2]);
    if (d) v = d[1].trim();
  }
  return v;
}

describe("控件高度三档", () => {
  it("变量:sm 32 / md 40 / lg 44", () => {
    expect(top).toMatch(/:root \{[^}]*--ctl-sm: 32px; ?--ctl-md: 40px; ?--ctl-lg: 44px/);
  });
  it.each([
    [".btn", "var(--ctl-md)"], [".btn.sm", "var(--ctl-sm)"], [".login-card .btn", "var(--ctl-lg)"], [".alarm-actions .btn", "var(--ctl-lg)"],
    ["select", "var(--ctl-md)"], [".field input", "var(--ctl-md)"], [".field select", "var(--ctl-md)"], [".login-card input", "var(--ctl-lg)"],
    [".field-inline select", "var(--ctl-sm)"], [".me-tools button", "var(--ctl-sm)"],
    // 截图核对:用户表里角色下拉 40、同一行按钮 32 —— 表格里的下拉跟行里按钮一样用 sm
    ["table select", "var(--ctl-sm)"],
    // 截图量出来的剩余:顶栏布防 / 报警胶囊 30、账号按钮 36、分段按钮 30、表单外的文字框 36
    [".armstate", "var(--ctl-sm)"], [".alarmcount", "var(--ctl-sm)"], [".usermenu > .who", "var(--ctl-sm)"], [".seg button", "var(--ctl-sm)"],
    ['input[type="text"]', "var(--ctl-md)"],
  ])("%s 高 %s", (sel, want) => {
    expect(last(sel, "height")).toBe(want);
  });
  it("按钮字两档:.btn 14 / .btn.sm 13,地图编辑工具条跟 .btn.sm 一样", () => {
    expect(last(".btn", "font-size")).toBe("14px");
    expect(last(".btn.sm", "font-size")).toBe("13px");
    expect(last(".me-tools button", "font-size")).toBe("13px");
    expect(last(".me-tools button", "font-weight")).toBe("600");
  });
  it("复选框、单选框一个尺寸 18px", () => {
    expect(last('input[type="checkbox"]', "width")).toBe("18px");
    expect(last('input[type="checkbox"]', "height")).toBe("18px");
  });
});

describe("输入框底子", () => {
  it("全站输入框的最小高是 sm(以前 36,把行内 32 的框撑成 36)", () => {
    expect(flat).toMatch(/:where\(input:not[^{]*\{[^}]*min-height: ?var\(--ctl-sm\)/);
  });
});
