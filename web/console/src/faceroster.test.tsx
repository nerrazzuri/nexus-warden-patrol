// @vitest-environment happy-dom
// 1.1-1 认出保安:授权页下面的「人脸登记」—— 看谁登记了、能删;读不到(没管理权限)就不显示。
import { cleanup, fireEvent, render, waitFor } from "@testing-library/preact";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { FaceRoster } from "./accesspage";
import { setFetch } from "./api";
import { lang } from "./i18n";

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
let faces: Record<string, unknown>[];
let engine: boolean;
let status: number;
let posted: string[];

beforeEach(() => {
  lang.value = "zh";
  posted = [];
  status = 200;
  engine = true;
  faces = [{ account: "gina", consent_ms: Date.UTC(2026, 10, 28), photos: 3, updated_ms: 1 },
    { account: "hugo", consent_ms: Date.UTC(2026, 10, 28), photos: 1, updated_ms: 1 }];
  setFetch(((url: string, init?: RequestInit) => {
    if (init?.method === "POST") {
      posted.push(url);
      faces = faces.filter((f) => !url.includes(`/${f.account}/`));
      return Promise.resolve(json({ faces }));
    }
    if (url === "/api/faces") return Promise.resolve(status === 200 ? json({ faces, engine }) : json({ error: "forbidden" }, status));
    return Promise.resolve(json({}, 404));
  }) as typeof fetch);
});
afterEach(cleanup);

describe("人脸登记名单", () => {
  it("列出谁登记了几张;删要先确认,删完名单少一行", async () => {
    let said = "";
    const { container: c } = render(<FaceRoster say={(s) => { said = s; }} />);
    await waitFor(() => expect(c.querySelector('[data-face="gina"]')).not.toBeNull());
    expect(c.querySelector('[data-face="gina"]')!.textContent).toContain("3");
    fireEvent.click(c.querySelector('[data-face="hugo"] button')!);
    expect(posted).toEqual([]);
    const yes = Array.from(document.querySelectorAll("button")).filter((b) => b.textContent === "删掉人脸资料").pop()!;
    fireEvent.click(yes);
    await waitFor(() => expect(posted).toEqual(["/api/faces/hugo/remove"]));
    await waitFor(() => expect(c.querySelector('[data-face="hugo"]')).toBeNull());
    expect(said).toContain("hugo");
  });

  it("站点没装人脸模块:写明;没管理权限读不到:整块不显示", async () => {
    engine = false;
    faces = [];
    const a = render(<FaceRoster say={() => {}} />).container;
    await waitFor(() => expect(a.querySelector("[data-faces]")!.textContent).toContain("没装人脸识别模块"));
    cleanup();
    status = 403;
    const b = render(<FaceRoster say={() => {}} />).container;
    await new Promise((r) => setTimeout(r, 30));
    expect(b.querySelector("[data-faces]")).toBeNull();
  });
});
