// UIUX-006(第二档 #27):删除这类不能撤回的按钮全站一个样子 —— 红字红框(.btn.danger);
// 实心红(.btn.stop)只给急停「全部叫停」。这里扫源码,新加的删除按钮忘了标 danger 就红。
import { readdirSync, readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const dir = `${process.cwd()}/src`;
const files = readdirSync(dir).filter((f) => f.endsWith(".tsx") && !f.includes(".test."));
const REMOVE = /<button\b((?:(?!<button)[\s\S])*?)>\s*\{(?:t|rt|dt)\("(?:remove|dRemove|routeDelete)"\)\}|<button\b((?:(?!<button)[\s\S])*?)>\s*\{L\("Remove", "删除"\)\}/g;

describe("UIUX-006 危险操作一个样子", () => {
  it("删除按钮都是 .btn.danger", () => {
    const bad: string[] = [];
    let n = 0;
    for (const f of files) {
      for (const m of readFileSync(`${dir}/${f}`, "utf-8").matchAll(REMOVE)) {
        n++;
        const attrs = m[1] ?? m[2] ?? "";
        const cls = /class=(?:"([^"]*)"|\{[^}]*\})/.exec(attrs)?.[0] ?? "";
        if (!/\bbtn\b/.test(cls) || !/\bdanger\b/.test(cls)) bad.push(`${f}: ${cls || "(没有 class)"}`);
      }
    }
    expect(n).toBeGreaterThan(3);
    expect(bad).toEqual([]);
  });

  it("删除的确认框也是红框按钮(Confirm 带 danger)", () => {
    const bad: string[] = [];
    for (const f of files) {
      for (const m of readFileSync(`${dir}/${f}`, "utf-8").matchAll(/<Confirm\b[^\n]*yes=\{(?:t|rt|dt|L)\("(?:remove|Remove|dRemove|schedRemove|routeDelete)"[^\n]*/g)) {
        if (!/\bdanger\b/.test(m[0])) bad.push(`${f}: ${m[0].slice(0, 80)}`);
      }
    }
    expect(bad).toEqual([]);
  });

  it("实心红 .btn.stop 只在急停(顶栏「全部叫停」)和叫停确认框里用", () => {
    const hits: string[] = [];
    for (const f of files) {
      const src = readFileSync(`${dir}/${f}`, "utf-8");
      for (const m of src.matchAll(/class=\{?["`][^"`]*\bbtn\b[^"`]*\bstop\b/g)) hits.push(`${f}:${src.slice(0, m.index).split("\n").length}`);
    }
    expect(hits.every((h) => h.startsWith("shell.tsx") || h.startsWith("dialogs.tsx"))).toBe(true);
  });
});
