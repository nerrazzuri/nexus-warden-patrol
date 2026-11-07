// @vitest-environment happy-dom
// 网页易用性第 2 轮(P0-18 残留):样式表没载上就重新载,不行就说一句。
import { afterEach, describe, expect, it } from "vitest";
import { failedSheets, reloadSheet } from "./stylecheck";

afterEach(() => { document.head.innerHTML = ""; document.body.innerHTML = ""; });

function sheet(href: string): HTMLLinkElement {
  const l = document.createElement("link");
  l.rel = "stylesheet";
  l.href = href;
  document.head.append(l);
  return l;
}

describe("样式表没载上", () => {
  it("挑出没载上的那张", () => {
    const a = sheet("/assets/a.css");
    sheet("/assets/b.css");
    const bad = failedSheets(document, (l) => !l.href.endsWith("/a.css"));
    expect(bad).toEqual([a]);
  });

  it("换个地址重新载:同一个文件带 retry,原来那个换掉", () => {
    const a = sheet("/assets/index-x.css");
    const n = reloadSheet(a, 1);
    expect(n.getAttribute("href")).toBe("/assets/index-x.css?retry=1");
    expect(document.querySelectorAll('link[rel="stylesheet"]').length).toBe(1);
    expect(a.isConnected).toBe(false);
  });
});
