// @vitest-environment happy-dom
// 第四档 #44(用户 11-21):客户自己导出、导入路线。
import { cleanup, fireEvent, render, waitFor } from "@testing-library/preact";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { setFetch } from "./api";
import { lang } from "./i18n";
import { buildRouteFile, parseRouteFile, planImport, routeFileName } from "./routeio";
import { RouteIO } from "./routeiopanel";
import type { Route } from "./routes";

beforeEach(() => { lang.value = "en"; });
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
const R = (id: string, rev = 1, extra: Partial<Route> = {}): Route => ({
  id, map_id: "m1", map_version: "3", revision: rev, bound: true, updated_by: "a", updated_ms: 0, policy: {},
  waypoints: [{ name: "W1", x: 1, y: 2, yaw: 0.5, actions: [{ type: "photo", camera: "front" }] as never }], ...extra,
});
const MAP = { map_id: "m1", version: "3" };

describe("文件格式", () => {
  it("导出再读回来一样;文件名带图、版本、日期", () => {
    const f = buildRouteFile([R("night", 4, { title: "一楼夜巡" })], MAP, "patrol", Date.UTC(2026, 10, 21, 3));
    const back = parseRouteFile(JSON.stringify(f));
    expect(back).toEqual(f);
    expect(f.routes[0]).toEqual({ id: "night", title: "一楼夜巡", policy: {}, waypoints: R("night").waypoints });
    expect(routeFileName(f)).toMatch(/^routes-m1-v3-2026112\d\.json$/);
  });
  it.each([
    ["{", "notJson"],
    [JSON.stringify({ hello: 1 }), "notRouteFile"],
    [JSON.stringify({ ...buildRouteFile([R("a")], MAP, "patrol"), v: 99 }), "newerVersion"],
    [JSON.stringify(buildRouteFile([], MAP, "patrol")), "empty"],
    [JSON.stringify(buildRouteFile([R("../x")], MAP, "patrol")), "badRoute"],
    [JSON.stringify(buildRouteFile([R("a", 1, { waypoints: [{ name: "W1", x: 1, y: "2", yaw: 0 } as never] })], MAP, "patrol")), "badRoute"],
  ])("读不了的说清楚:%s → %s", (text, why) => {
    expect(parseRouteFile(text)).toEqual({ error: why });
  });
});

describe("导进来每条怎么办", () => {
  const f = buildRouteFile([R("night"), R("day"), R("east")], MAP, "patrol");
  it("这一版上有的 = 盖掉(带现在的修订号);别处用过 / 删掉过 = 换编号;都没有 = 新建", () => {
    const rows = planImport(f, [R("night", 7)], ["day", "day-2"]);
    expect(rows.map((r) => [r.from.id, r.action, r.id, r.base])).toEqual([
      ["night", "replace", "night", 7], ["day", "rename", "day-3", 0], ["east", "new", "east", 0],
    ]);
  });
  it("换出来的编号不跟同一个文件里的撞", () => {
    const g = buildRouteFile([R("a"), R("a-2")], MAP, "patrol");
    const rows = planImport(g, [], ["a"]);
    expect(new Set(rows.map((r) => r.id)).size).toBe(2);
    expect(rows.map((r) => r.id)).not.toContain("a");
  });
});

function pickFile(c: Element, text: string) {
  const input = c.querySelector<HTMLInputElement>("[data-route-import]")!;
  const file = new File([text], "routes.json", { type: "application/json" });
  Object.defineProperty(input, "files", { value: [file], configurable: true });
  fireEvent.change(input);
}

describe("面板", () => {
  it("导出:下载一个文件,里面是这一版的路线", async () => {
    let blob: Blob | null = null;
    vi.spyOn(URL, "createObjectURL").mockImplementation((b) => { blob = b as Blob; return "blob:x"; });
    vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => {});
    const said: string[] = [];
    const r = render(<RouteIO sel={MAP} kind="patrol" routes={[R("night"), R("day")]} say={(m) => said.push(m)} onDone={() => {}} />);
    fireEvent.click(r.container.querySelector("[data-route-export]")!);
    expect(blob).not.toBeNull();
    const f = parseRouteFile(await blob!.text());
    expect("error" in f ? f : f.routes.map((x) => x.id)).toEqual(["night", "day"]);
    expect(said).toEqual(["Exported 2 routes to a file."]);
  });

  it("这一版上没路线:导出按钮灰着并说为什么", () => {
    const r = render(<RouteIO sel={MAP} kind="patrol" routes={[]} say={() => {}} onDone={() => {}} />);
    const b = r.container.querySelector<HTMLButtonElement>("[data-route-export]")!;
    expect(b.disabled).toBe(true);
    expect(b.title).toBe("No routes on this map version to export.");
  });

  it("导入:列出每条怎么办,盖掉的默认不勾;存下去的是文件里的点,换编号的按新编号存;存不下的说原因", async () => {
    const posted: { path: string; body: any }[] = [];
    setFetch((async (url: RequestInfo | URL, init?: RequestInit) => {
      const u = String(url);
      if (u.endsWith("/api/routes") && init?.method !== "POST") return json({ revision: 1, timezone: null, routes: [R("day", 1, { map_version: "1" })], schedules: [], retired_routes: ["old"] });
      if (init?.method === "POST") {
        const body = JSON.parse(String(init.body));
        posted.push({ path: u, body });
        if (u.endsWith("/east")) return json({ error: "W1 在墙里", errors: [{ index: 0, name: "W1", problem: "点在墙里" }] }, 400);
        return json({ ...R(u.split("/").pop()!), waypoints: body.waypoints });
      }
      return json({ error: "nope" }, 404);
    }) as never);
    const done = vi.fn();
    const said: string[] = [];
    const r = render(<RouteIO sel={MAP} kind="patrol" routes={[R("night", 5)]} say={(m) => said.push(m)} onDone={done} />);
    const file = buildRouteFile([R("night"), R("day", 1, { title: "白天" }), R("east"), R("old")], { map_id: "m1", version: "2" }, "patrol");
    pickFile(r.container, JSON.stringify(file));
    await waitFor(() => expect(r.container.querySelector("[data-routeio-plan]")).not.toBeNull());
    expect(r.container.textContent).toContain("This page shows version 3");
    const acts = [...r.container.querySelectorAll("[data-import-row]")].map((e) => [e.getAttribute("data-import-row"),
      e.querySelector("[data-action]")!.getAttribute("data-action"), e.querySelector<HTMLInputElement>("input")!.checked]);
    expect(acts).toEqual([["night", "replace", false], ["day", "rename", true], ["east", "new", true], ["old", "rename", true]]);
    expect(r.container.querySelector("[data-import-run]")!.textContent).toBe("Import 3 routes");
    fireEvent.click(r.container.querySelector("[data-import-run]")!);
    await waitFor(() => expect(done).toHaveBeenCalled());
    expect(posted.map((p) => p.path.split("/").pop())).toEqual(["day-2", "east", "old-2"]);
    expect(posted[0].body).toMatchObject({ map_id: "m1", map_version: "3", base_revision: 0, kind: "patrol", title: "白天",
      waypoints: R("day").waypoints });
    expect(said).toEqual(["Imported 2 of 3."]);
    expect(r.container.querySelector("[data-routeio-failed]")!.textContent).toContain("east");
    expect(r.container.querySelector("[data-routeio-failed]")!.textContent).toContain("W1");
  });

  it("盖掉现有的那条:勾上才存,带着它现在的修订号", async () => {
    const posted: { path: string; body: any }[] = [];
    setFetch((async (url: RequestInfo | URL, init?: RequestInit) => {
      if (init?.method !== "POST") return json({ revision: 1, timezone: null, routes: [], schedules: [] });
      posted.push({ path: String(url), body: JSON.parse(String(init.body)) });
      return json(R("night"));
    }) as never);
    const r = render(<RouteIO sel={MAP} kind="patrol" routes={[R("night", 5)]} say={() => {}} onDone={() => {}} />);
    pickFile(r.container, JSON.stringify(buildRouteFile([R("night")], MAP, "patrol")));
    await waitFor(() => expect(r.container.querySelector("[data-routeio-plan]")).not.toBeNull());
    expect(r.container.querySelector<HTMLButtonElement>("[data-import-run]")!.disabled).toBe(true);
    fireEvent.click(r.container.querySelector("[data-import-row] input")!);
    fireEvent.click(r.container.querySelector("[data-import-run]")!);
    await waitFor(() => expect(posted.length).toBe(1));
    expect(posted[0].body.base_revision).toBe(5);
  });

  it.each([
    [buildRouteFile([R("a")], { map_id: "other", version: "1" }, "patrol"), "This file is for map other. This page shows map m1: choose that map first."],
    [buildRouteFile([R("a")], MAP, "guard"), "This file holds zone guard routes. Import it on the guard routes page."],
  ])("别的图 / 别的种类的文件:不导,说清楚", async (file, msg) => {
    const r = render(<RouteIO sel={MAP} kind="patrol" routes={[]} say={() => {}} onDone={() => {}} />);
    pickFile(r.container, JSON.stringify(file));
    await waitFor(() => expect(r.container.querySelector("[data-routeio-err]")?.textContent).toBe(msg));
    expect(r.container.querySelector("[data-routeio-plan]")).toBeNull();
  });

  it("中英词条一一对应", async () => {
    const { RDICTS } = await import("./routes_i18n");
    const ks = Object.keys(RDICTS.en).filter((k) => k.startsWith("io"));
    expect(ks.length).toBeGreaterThan(20);
    for (const k of ks) expect((RDICTS.zh as Record<string, string>)[k], k).toBeTruthy();
  });
});
