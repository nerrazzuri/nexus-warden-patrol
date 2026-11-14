// 顶栏在 1280、1024 宽也是一行(C-B6 收尾):happy-dom 量不了排版,这里只看样式表里那几条规矩还在 ——
// Stop all 不缩、≥ 1024 不折行、站点名能省略号截断;往窄了收的时候从来不藏 Stop all、页签、模式、报警数、时钟。
// 真的排得下没有,靠截图核对(1920 / 1280 / 1024,中英文、浅深色)。
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const sheet = readFileSync(`${process.cwd()}/src/styles.css`, "utf-8"); // vitest 在 web/console 里跑
const flat = sheet.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\s+/g, " ");

/** 某个选择器(原样)那条规则的声明;没有返回 ""。 */
function rule(sel: string, within = flat): string {
  const esc = sel.replace(/[.*+?^${}()|[\]\\>]/g, "\\$&");
  const m = within.match(new RegExp(`(?:^|[}{;,]) ?${esc} ?\\{([^}]*)\\}`));
  return m ? m[1] : "";
}

/** 某个 @media 条件里的内容。 */
function media(cond: string): string {
  const i = flat.indexOf(`@media ${cond} {`);
  if (i < 0) return "";
  let depth = 0;
  for (let j = flat.indexOf("{", i); j < flat.length; j++) {
    if (flat[j] === "{") depth++;
    if (flat[j] === "}" && --depth === 0) return flat.slice(flat.indexOf("{", i) + 1, j);
  }
  return "";
}

describe("顶栏一行放得下(样式表)", () => {
  it("顶栏里的东西默认都不缩;站点名能缩、省略号", () => {
    expect(rule(".topbar > *")).toMatch(/flex-shrink: 0/);
    const r = rule(".topbar-site");
    expect(r).toMatch(/flex-shrink: 1/);
    expect(r).toMatch(/text-overflow: ellipsis/);
  });

  it("≥ 900 顶栏一行(只有窄屏才折行)", () => {
    expect(rule(".topbar")).not.toMatch(/flex-wrap: wrap/);
    expect(rule(".topbar", media("(max-width: 899px)"))).toMatch(/flex-wrap: wrap/);
  });

  it("往窄了收只藏站点名、角色、日期;全部急停、布防、未处理数、时钟、大块导航从来不藏", () => {
    expect(media("(max-width: 1279px)")).toMatch(/\.topbar-site, \.who-role, \.clock-date \{ display: none; \}/);
    for (const m of flat.matchAll(/([^{}]+)\{[^{}]*display: none[^{}]*\}/g)) {
      const sel = m[1];
      for (const keep of [".btn.stop", ".alarmcount", ".armstate", ".chip-top", ".topnav", ".clock "]) {
        if (!sel.includes(keep)) continue;
        // 只有打印的时候整个顶栏不印;别的地方不许藏这些
        expect(sel, `藏了 ${keep}`).toMatch(/\.topbar, \.subnav/);
      }
    }
  });
});
