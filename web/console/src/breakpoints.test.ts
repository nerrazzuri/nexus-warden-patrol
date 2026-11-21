// UIUX-007(第四档 #28,用户 11-21):全站只用四个宽度断点,不再各写各的。
//   手机 ≤760 · 平板 761–1099 · 笔记本 1100–1279 · 台式 1280–1439 · 宽屏 ≥1440
// 最窄支持 360(手机);1280 以上是完整布局,1100–1279 收紧,1099 以下叠成一列。
// 容器查询(@container)按那一块自己的宽度,不算在内。
import { readFileSync, readdirSync } from "node:fs";
import { describe, expect, it } from "vitest";

const dir = `${process.cwd()}/src`;
const files = readdirSync(dir).filter((f) => f.endsWith(".css"));
const MAX = new Set([760, 1099, 1279, 1439]);
const MIN = new Set([761, 1100, 1280, 1440]);

describe("宽度断点只用四个", () => {
  it.each(files)("%s", (f) => {
    const css = readFileSync(`${dir}/${f}`, "utf-8").replace(/\/\*[\s\S]*?\*\//g, "");
    const bad: string[] = [];
    for (const m of css.matchAll(/@media([^{]*)\{/g)) {
      for (const w of m[1].matchAll(/\((max|min)-width:\s*(\d+)px\)/g)) {
        const v = Number(w[2]);
        if (!(w[1] === "max" ? MAX : MIN).has(v)) bad.push(`@media${m[1].trim()}`);
      }
    }
    expect(bad).toEqual([]);
  });
});
