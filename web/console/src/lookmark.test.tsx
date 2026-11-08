// @vitest-environment happy-dom
// 第 2 轮 duty N9:点地图派机器人,点的地方标出来(原来只弹确认框,看不出点在哪)
import { cleanup, fireEvent, render, waitFor } from "@testing-library/preact";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { setFetch } from "./api";
import { lang } from "./i18n";
import { MapPage } from "./mappage";

const RECT = { left: 40, top: 100, width: 900, height: 600 };
const META = { width: 100, height: 100, m_per_px: 0.05, left_x: 0, top_y: 5 };
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
const unitA = {
  robot: { robot_id: "A", active: true, fresh: true, revoked: false, held: null, status: { online: true, last_seen: 0 },
    loc: { pose: { x: 1, y: 1, yaw: 0 } }, capabilities: { tasks: { patrol: { map_id: "m", map_version: "1" } } } },
  state: "idle", battery: 80, task: "",
};

function installScreenCTM() {
  const parse = (s: string | null): DOMMatrix => {
    const m = s && /^matrix\(([^)]+)\)$/.exec(s.trim());
    return m ? new DOMMatrix(m[1].trim().split(/[\s,]+/).map(Number)) : new DOMMatrix();
  };
  const proto = (window as unknown as { SVGGraphicsElement: { prototype: { getScreenCTM: () => DOMMatrix } } }).SVGGraphicsElement.prototype;
  vi.spyOn(proto, "getScreenCTM").mockImplementation(function (this: Element) {
    let m = new DOMMatrix();
    let el: Element | null = this;
    while (el && el.tagName.toLowerCase() !== "svg") { m = parse(el.getAttribute("transform")).multiply(m); el = el.parentElement; }
    const [vx, vy, vw, vh] = el!.getAttribute("viewBox")!.split(/[\s,]+/).map(Number);
    const s = Math.min(RECT.width / vw, RECT.height / vh);
    return new DOMMatrix([s, 0, 0, s, RECT.left + (RECT.width - vw * s) / 2 - vx * s, RECT.top + (RECT.height - vh * s) / 2 - vy * s]).multiply(m);
  });
  vi.spyOn(Element.prototype, "getBoundingClientRect").mockReturnValue({
    ...RECT, x: RECT.left, y: RECT.top, right: RECT.left + RECT.width, bottom: RECT.top + RECT.height, toJSON: () => ({}),
  } as DOMRect);
}

beforeEach(() => {
  lang.value = "zh";
  setFetch(((url: string) => {
    if (url.endsWith("/preview")) return Promise.resolve(json(META));
    if (url.endsWith("/areas")) return Promise.resolve(json({ areas: [] }));
    return Promise.resolve(json({}, 404));
  }) as typeof fetch);
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

describe("点地图派机器人", () => {
  it("点的地方有标记", async () => {
    installScreenCTM();
    const { container: c } = render(<MapPage units={[unitA] as never} p1={[]} now={0} selected={null} onSelect={() => {}} onVideo={() => {}}
      role="admin" mode={null} onArm={() => {}} />);
    await waitFor(() => expect(c.querySelector("g.map-world")).not.toBeNull());
    expect(c.querySelector("[data-look-mark]")).toBeNull();
    const svg = c.querySelector("svg.map")!;
    const at = { clientX: RECT.left + RECT.width / 2, clientY: RECT.top + RECT.height / 2 };
    fireEvent.pointerDown(svg, { ...at, button: 0, pointerId: 1 });
    fireEvent.pointerUp(window, { ...at, pointerId: 1 });
    fireEvent.click(svg, at);
    await waitFor(() => expect(c.ownerDocument.querySelector(".golook")).not.toBeNull());
    expect(c.querySelector("[data-look-mark]")).not.toBeNull();
  });
});
