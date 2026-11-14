// UIUX-010(第二档 #29):圆角、间距走变量,不写字面量。
// 圆角:--r-r2 / r4 / r8 / r12 / rPill(theme.ts 从 design/mobile.json 挂上);圆点、圆形用 50%。
// 间距(gap):--sp-1…6 = 4 / 8 / 12 / 16 / 24 / 32;图标和字之间的 2px、0 例外。
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const css = ["styles.css", "routes.css", "mapmgmt.css"].map((f) =>
  [f, readFileSync(`${process.cwd()}/src/${f}`, "utf-8").replace(/\/\*[\s\S]*?\*\//g, "")] as const);

describe("UIUX-010 圆角、间距走变量", () => {
  it("间距刻度变量 4 / 8 / 12 / 16 / 24 / 32", () => {
    expect(css[0][1].replace(/\s+/g, " ")).toMatch(/--sp-1: 4px; ?--sp-2: 8px; ?--sp-3: 12px; ?--sp-4: 16px; ?--sp-5: 24px; ?--sp-6: 32px/);
  });
  it("border-radius 不写 px 字面量(圆形 50%、直角 0 除外)", () => {
    const bad = css.flatMap(([f, s]) => [...s.matchAll(/border-radius:\s*([^;}]+)/g)].map((m) => m[1].trim())
      .filter((v) => /\d+px/.test(v)).map((v) => `${f}: ${v}`));
    expect(bad).toEqual([]);
  });
  it("gap 只用 --sp-* 变量(0、2px 例外)", () => {
    const bad = css.flatMap(([f, s]) => [...s.matchAll(/(?<![-\w])(?:row-|column-)?gap:\s*([^;}]+)/g)].map((m) => m[1].trim())
      .filter((v) => v.split(/\s+/).some((x) => !/^(var\(--sp-[1-6]\)|0|2px)$/.test(x))).map((v) => `${f}: ${v}`));
    expect(bad).toEqual([]);
  });
  // liang-d5 复测 29aa88b2:002 / 031 / 004 还剩的几处
  const rule = (sel: string) => {
    for (const [, s] of css) {
      const m = s.match(new RegExp(`(?:^|[}\\s])${sel.replace(/[.()]/g, "\\$&")}\\s*\\{([^}]*)\\}`));
      if (m) return m[1];
    }
    return "";
  };
  it("卡片、分组、小节标题都是 15px;「现在」是 h2 17px;状态小字 12px", () => {
    for (const sel of [".dcard-h", ".kpi-group-h", ".today-h", ".mm-mapid"]) expect(rule(sel), sel).toMatch(/font-size:\s*15px/);
    expect(rule(".arm-now-text h2")).toMatch(/font-size:\s*17px/);
    expect(rule(".rd-facts dd small")).toMatch(/font-size:\s*12px/);
  });
  it("视频卡按钮用控件小档高", () => {
    expect(rule(".slot-btn")).toMatch(/height:\s*var\(--ctl-sm\)/);
  });
});
