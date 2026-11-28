// @vitest-environment happy-dom
// 1.1-1 第 4 步:授权页下面的「保安经过」—— 按天拉、按人筛、并过的写 ×n;读不到就不显示。
import { cleanup, fireEvent, render, waitFor } from "@testing-library/preact";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { GuardPasses } from "./accesspage";
import { setFetch } from "./api";
import { lang } from "./i18n";

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
const NOW = new Date(2026, 10, 28, 15).getTime();
let urls: string[];
let status: number;

beforeEach(() => {
  lang.value = "zh";
  urls = [];
  status = 200;
  setFetch(((url: string) => {
    urls.push(url);
    if (status !== 200) return Promise.resolve(json({ error: "x" }, status));
    return Promise.resolve(json({ passes: [
      { id: 2, account: "hugo", robot: "A", zone: "C区", how: "face", first_ms: new Date(2026, 10, 28, 10).getTime(), last_ms: new Date(2026, 10, 28, 10).getTime(), n: 1 },
      { id: 1, account: "gina", robot: "A", zone: "B区", how: "face", first_ms: new Date(2026, 10, 28, 9).getTime(), last_ms: new Date(2026, 10, 28, 9, 4).getTime(), n: 3 },
    ] }));
  }) as typeof fetch);
});
afterEach(cleanup);

describe("保安经过", () => {
  it("拉今天的;并过的写时间段和 ×n;按人筛", async () => {
    const { container: c } = render(<GuardPasses now={NOW} />);
    await waitFor(() => expect(c.querySelector('[data-pass="1"]')).not.toBeNull());
    const since = new Date(2026, 10, 28).getTime();
    expect(urls[0]).toBe(`/api/guard-passes?since=${since}&until=${new Date(2026, 10, 29).getTime()}`);
    const g = c.querySelector('[data-pass="1"]')!.textContent!;
    expect(g).toContain("09:00–09:04");
    expect(g).toContain("B区");
    expect(g).toContain("人脸 ×3");
    fireEvent.change(c.querySelector('select[name="gp-who"]')!, { target: { value: "hugo" } });
    await waitFor(() => expect(c.querySelector('[data-pass="1"]')).toBeNull());
    expect(c.querySelector('[data-pass="2"]')).not.toBeNull();
  });

  it("读不到(没启用、没权限)就不显示", async () => {
    status = 404;
    const { container: c } = render(<GuardPasses now={NOW} />);
    await waitFor(() => expect(urls.length).toBe(1));
    await waitFor(() => expect(c.querySelector("[data-passes]")).toBeNull());
  });
});
