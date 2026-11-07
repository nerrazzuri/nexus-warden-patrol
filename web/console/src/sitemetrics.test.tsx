// @vitest-environment happy-dom
// 网页易用性第 1 轮 P0-19:系统页放着不动,/api/metrics 不能一直请求。
import { cleanup, render } from "@testing-library/preact";
import { afterEach, expect, it } from "vitest";
import { setFetch } from "./api";
import { SiteMetrics } from "./remoteops";

afterEach(() => cleanup());

it("重画几次也只拉一次", async () => {
  const urls: string[] = [];
  setFetch(((url: string) => {
    urls.push(url);
    return Promise.resolve(new Response(JSON.stringify({ metrics: [] }), { status: 200, headers: { "Content-Type": "application/json" } }));
  }) as typeof fetch);
  const r = render(<SiteMetrics />);
  for (let i = 0; i < 5; i++) {
    await new Promise((ok) => setTimeout(ok, 5));
    r.rerender(<SiteMetrics />);
  }
  expect(urls.filter((u) => u.startsWith("/api/metrics")).length).toBe(1);
});
