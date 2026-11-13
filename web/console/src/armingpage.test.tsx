// @vitest-environment happy-dom
// W44 第二期 布防时间页(设计 §5.1):一周七行色块、全部一样 / 每个防区单独设、例外、交班时间、保存、没存提醒、谁说了算。
import { cleanup, fireEvent, render, waitFor } from "@testing-library/preact";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { setFetch } from "./api";
import { armedAt, fromWire, type WireSlot } from "./armgrid";
import { ArmingPage } from "./armingpage";
import { lang } from "./i18n";

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
const at = (h: number, m = 0) => new Date(2026, 9, 26, h, m).getTime();

let schedule: Record<string, unknown>;
let mode: Record<string, unknown>;
let posted: { url: string; body: Record<string, unknown> }[];

beforeEach(() => {
  lang.value = "zh";
  posted = [];
  schedule = { enabled: true, slots: [{ zone: "", day: 0, start: "22:00", end: "24:00" }], exceptions: [], today: [] };
  // 中午 12 点:时间表(周一 22–24 点)此刻是撤防
  mode = { mode: "home", label: "按时间表:撤防", source: "schedule", state: "disarmed", next_change_ms: at(22), manual_until_ms: null,
    zones: [{ zone: "北区", armed: true, home_armed: true }] };
  setFetch(((url: string, init?: RequestInit) => {
    if (init?.method === "POST") {
      const body = JSON.parse(String(init.body ?? "{}"));
      posted.push({ url, body });
      if (url === "/api/arming/exceptions") {
        schedule = { ...schedule, exceptions: [{ id: 1, ...body }] };
        return Promise.resolve(json(schedule));
      }
      if (url === "/api/arming/schedule") return Promise.resolve(json({ ...schedule, ...body }));
      if (url === "/api/arming/schedule/preview") return Promise.resolve(json(fakePreview(body)));
      return Promise.resolve(json(body));
    }
    if (url.startsWith("/api/arming/schedule")) return Promise.resolve(json(schedule));
    if (url.startsWith("/api/duty-settings")) return Promise.resolve(json({ shift_hours: [7, 19], stale_hours: 2 }));
    if (url.startsWith("/api/mode")) return Promise.resolve(json(mode));
    if (url.startsWith("/api/routes")) return Promise.resolve(json({ revision: 1, timezone: "Asia/Kuala_Lumpur",
      routes: [{ id: "night", waypoints: [] }, { id: "day", waypoints: [] }],
      schedules: [{ id: "n22", mission: "night", at: "22:00", days: ["mon"], window_min: 30, on_missed: "skip", revision: 1 }] }));
    return Promise.resolve(json({}, 404));
  }) as typeof fetch);
});
afterEach(cleanup);

/** 假站点的预演:照草稿日程算此刻(12 点)每个防区(真站点按站点的钟,见 modes.preview)。 */
function fakePreview(body: { enabled: boolean; slots: WireSlot[] }) {
  type Z = { zone: string; armed?: boolean; home_armed?: boolean };
  const m = mode as { state: string; source: string; mode: string; manual_until_ms?: number | null; zones?: Z[] };
  const fix = (z: Z) => ({ ...z, armed: m.source !== "schedule" ? z.armed : m.state === "armed" ? true : m.state === "disarmed" ? false : z.armed });
  const before = { ...m, zones: (m.zones ?? []).map(fix) };
  if (!body.enabled || (m.source === "manual" && m.manual_until_ms && schedule.enabled)) return { before, after: before };
  const sl = fromWire(body.slots), now = new Date(at(12));
  const names = Array.from(new Set([...(m.zones ?? []).map((z) => z.zone), ...body.slots.filter((x) => x.zone).map((x) => x.zone)]));
  const zones = names.map((zone) => ({ zone, armed: armedAt(sl, zone, now) }));
  const def = armedAt(sl, "", now);
  const parts = [...zones.map((z) => z.armed), def];
  const state = parts.every(Boolean) ? "armed" : parts.some(Boolean) ? "partial" : "disarmed";
  return { before, after: { mode: state === "armed" ? "armed" : "home", source: "schedule", state, zones, default_armed: def } };
}

const page = () => render(<ArmingPage say={() => {}} now={at(12)} />);
const row = (c: Element, day: number) => c.querySelector(`.armrow[data-day="${day}"]`)!;
const btn = (c: Element, text: string) => Array.from(c.querySelectorAll("button")).find((b) => b.textContent?.trim() === text) as HTMLButtonElement;
function wide(track: Element) {
  (track as HTMLElement).getBoundingClientRect = () => ({ left: 0, width: 1440, top: 0, height: 20, right: 1440, bottom: 20, x: 0, y: 0, toJSON() {} }) as DOMRect;
}
function drag(track: Element, from: number, to: number) {
  wide(track);
  fireEvent.pointerDown(track, { clientX: from, pointerId: 1 });
  fireEvent.pointerMove(track, { clientX: to, pointerId: 1 });
  fireEvent.pointerUp(track, { clientX: to, pointerId: 1 });
}

describe("布防时间页", () => {
  it("读出来画色块", async () => {
    const { container: c } = page();
    await waitFor(() => expect(row(c, 0).querySelectorAll(".armblock").length).toBe(1));
    const b = row(c, 0).querySelector(".armblock") as HTMLElement;
    expect(parseFloat(b.style.left)).toBeCloseTo(91.667, 2);
    expect(parseFloat(b.style.width)).toBeCloseTo(8.333, 2);
    expect(row(c, 1).querySelectorAll(".armblock").length).toBe(0);
  });

  it("拖出一段再保存,发整份", async () => {
    const { container: c } = page();
    await waitFor(() => expect(row(c, 0).querySelector(".armblock")).not.toBeNull());
    drag(row(c, 1).querySelector(".armtrack")!, 600, 720);
    expect(row(c, 1).querySelectorAll(".armblock").length).toBe(1);
    fireEvent.click(c.querySelector(".arm-save")!);
    await waitFor(() => expect(posted.some((p) => p.url === "/api/arming/schedule")).toBe(true));
    const body = posted.find((p) => p.url === "/api/arming/schedule")!.body;
    expect(body.enabled).toBe(true);
    expect(body.slots).toContainEqual({ zone: "", day: 1, start: "10:00", end: "12:00" });
    expect(body.slots).toContainEqual({ zone: "", day: 0, start: "22:00", end: "24:00" });
  });

  it("W53 经理:能排布防时间,交班那一块不显示、也不提交(外审 W53-1 #10)", async () => {
    const { container: c } = render(<ArmingPage say={() => {}} now={at(12)} role="owner" />);
    await waitFor(() => expect(row(c, 0).querySelector(".armblock")).not.toBeNull());
    expect(c.querySelector(".arm-duty")).toBeNull();
    expect(c.textContent).toContain("由管理员修改");                             // P1-61:说清哪块不能改
    drag(row(c, 1).querySelector(".armtrack")!, 600, 720);
    fireEvent.click(c.querySelector(".arm-save")!);
    await waitFor(() => expect(posted.some((p) => p.url === "/api/arming/schedule")).toBe(true));
    await new Promise((r) => setTimeout(r, 20));
    expect(posted.some((p) => p.url === "/api/duty-settings")).toBe(false);
  });

  it("点色块能删", async () => {
    const { container: c } = page();
    await waitFor(() => expect(row(c, 0).querySelector(".armblock")).not.toBeNull());
    fireEvent.click(row(c, 0).querySelector(".armblock")!);
    fireEvent.click(btn(c, "删除此时段"));
    expect(row(c, 0).querySelectorAll(".armblock").length).toBe(0);
  });

  it("复制到别的天", async () => {
    const { container: c } = page();
    await waitFor(() => expect(row(c, 0).querySelector(".armblock")).not.toBeNull());
    const seen = vi.fn();
    (HTMLElement.prototype as unknown as { scrollIntoView: () => void }).scrollIntoView = seen;
    fireEvent.click(row(c, 0).querySelector(".arm-copy")!);
    await waitFor(() => expect(seen).toHaveBeenCalled());               // 第 2 轮 config N7:滚到看得见
    fireEvent.click(c.querySelector('.arm-copyto input[value="1"]')!);
    fireEvent.click(c.querySelector('.arm-copyto input[value="2"]')!);
    fireEvent.click(btn(c, "复制"));
    expect(row(c, 1).querySelectorAll(".armblock").length).toBe(1);
    expect(row(c, 2).querySelectorAll(".armblock").length).toBe(1);
  });

  it("单独设防区只改那个防区", async () => {
    const { container: c } = page();
    await waitFor(() => expect(row(c, 0).querySelector(".armblock")).not.toBeNull());
    fireEvent.click(btn(c, "每个防区单独设"));
    fireEvent.click(btn(c, "北区"));
    expect(c.textContent).toContain("与全部防区一致");
    fireEvent.click(btn(c, "单独设这个防区"));
    drag(row(c, 2).querySelector(".armtrack")!, 480, 600);
    fireEvent.click(c.querySelector(".arm-save")!);
    await waitFor(() => expect(posted.some((p) => p.url === "/api/arming/schedule")).toBe(true));
    const slots = posted.find((p) => p.url === "/api/arming/schedule")!.body.slots as { zone: string; day: number }[];
    expect(slots).toContainEqual({ zone: "北区", day: 0, start: "22:00", end: "24:00" });
    expect(slots).toContainEqual({ zone: "北区", day: 2, start: "08:00", end: "10:00" });
    expect(slots.filter((x) => x.zone === "")).toEqual([{ zone: "", day: 0, start: "22:00", end: "24:00" }]);
  });

  it("加例外", async () => {
    const { container: c } = page();
    await waitFor(() => expect(c.querySelector(".arm-ex")).not.toBeNull());
    fireEvent.input(c.querySelector('.arm-ex input[name="first"]')!, { target: { value: "2099-10-30" } });
    fireEvent.input(c.querySelector('.arm-ex input[name="last"]')!, { target: { value: "2099-11-02" } });
    fireEvent.input(c.querySelector('.arm-ex input[name="note"]')!, { target: { value: "出远门" } });
    fireEvent.click(btn(c, "添加例外"));
    await waitFor(() => expect(posted.find((p) => p.url === "/api/arming/exceptions")?.body).toEqual(
      { first_day: "2099-10-30", last_day: "2099-11-02", state: "armed", note: "出远门" }));
    await waitFor(() => expect(c.querySelector(".arm-ex")!.textContent).toContain("出远门"));
  });

  it("第 2 轮 P1-58:删例外先确认,删完说一声;说明里写加删马上生效", async () => {
    schedule = { ...schedule, exceptions: [{ id: 7, first_day: "2099-10-30", last_day: "2099-10-30", state: "armed", note: "" }] };
    const said: string[] = [];
    const { container: c } = render(<ArmingPage say={(m: string) => said.push(m)} now={at(12)} />);
    await waitFor(() => expect(c.querySelector(".arm-ex li")).not.toBeNull());
    expect(c.querySelector(".arm-ex")!.textContent).toContain("马上生效");
    fireEvent.click(btn(c.querySelector(".arm-ex")!, "删除"));
    expect(posted.some((p) => p.url.includes("/remove"))).toBe(false);
    await waitFor(() => expect(document.querySelector("dialog")?.textContent).toContain("2099-10-30"));
    fireEvent.click([...document.querySelectorAll("dialog button")].find((b) => b.textContent === "删除")!);
    await waitFor(() => expect(posted.some((p) => p.url === "/api/arming/exceptions/7/remove")).toBe(true));
    await waitFor(() => expect(said.join(" ")).toContain("已删除例外"));
  });

  it("P1-60:过去的日子、结束早于开始,当场说,不发", async () => {
    const { container: c } = page();
    await waitFor(() => expect(c.querySelector(".arm-ex")).not.toBeNull());
    fireEvent.input(c.querySelector('.arm-ex input[name="first"]')!, { target: { value: "2020-01-01" } });
    expect(c.querySelector(".arm-ex")!.textContent).toContain("开始日期已经过去了");
    expect(btn(c, "添加例外").disabled).toBe(true);
    fireEvent.input(c.querySelector('.arm-ex input[name="first"]')!, { target: { value: "2099-05-02" } });
    fireEvent.input(c.querySelector('.arm-ex input[name="last"]')!, { target: { value: "2099-05-01" } });
    expect(c.querySelector(".arm-ex")!.textContent).toContain("结束日期早于开始日期");
    expect(btn(c, "添加例外").disabled).toBe(true);
    expect(posted.some((p) => p.url === "/api/arming/exceptions")).toBe(false);
  });

  it("改交班时间", async () => {
    const { container: c } = page();
    await waitFor(() => expect(c.querySelector('select[name="shiftA"]')).not.toBeNull());
    await waitFor(() => expect((c.querySelector('select[name="shiftA"]') as HTMLSelectElement).value).toBe("7"));
    fireEvent.change(c.querySelector('select[name="shiftA"]')!, { target: { value: "8" } });
    fireEvent.change(c.querySelector('select[name="shiftB"]')!, { target: { value: "20" } });
    fireEvent.click(c.querySelector(".arm-save")!);
    await waitFor(() => expect(posted.find((p) => p.url === "/api/duty-settings")?.body).toEqual({ shift_hours: [8, 20], stale_hours: 2 }));
  });

  it("W74 四期:被遮挡、推倒时只开灯不鸣笛", async () => {
    const { container: c } = page();
    await waitFor(() => expect(c.querySelector('input[name="siren"]')).not.toBeNull());
    await new Promise((r) => setTimeout(r, 20));          // 等站点的设置读回来
    const box = c.querySelector('input[name="siren"]') as HTMLInputElement;
    expect(box.checked).toBe(true);
    fireEvent.click(box);
    fireEvent.click(c.querySelector(".arm-save")!);
    await waitFor(() => expect(posted.find((p) => p.url === "/api/duty-settings")?.body).toEqual(
      { shift_hours: [7, 19], stale_hours: 2, self_protect_siren: false }));
  });

  // 第 8 轮 W8-05:电量线挪到「巡逻日程」页签、叫「巡逻电量线」、自己存;填错了框标红、说原因、存不了
  it("W8-05 巡逻电量线:在巡逻日程页签,填错标红,自己存", async () => {
    const { container: c } = page();
    await waitFor(() => expect(c.querySelector('select[name="shiftA"]')).not.toBeNull());
    expect(c.querySelector('input[name="patrolReturn"]')).toBeNull();
    fireEvent.click(c.querySelector('[data-arm-tab="patrols"]')!);
    const box = await waitFor(() => c.querySelector('input[name="patrolReturn"]') as HTMLInputElement);
    await waitFor(() => expect(box.value).toBe("25"));
    expect(c.textContent).toContain("巡逻电量线");
    fireEvent.input(box, { target: { value: "70" } });
    expect(box.getAttribute("aria-invalid")).toBe("true");
    expect(c.textContent).toContain("20–60");
    const save = c.querySelector("[data-patrol-line-save]") as HTMLButtonElement;
    expect(save.disabled).toBe(true);
    fireEvent.input(box, { target: { value: "40" } });
    expect(box.getAttribute("aria-invalid")).toBe("false");
    fireEvent.click(save);
    await waitFor(() => expect(posted.find((p) => p.url === "/api/duty-settings")?.body).toEqual({ patrol_return_pct: 40 }));
  });

  it("没存离开有提示", async () => {
    const { container: c } = page();
    await waitFor(() => expect(row(c, 0).querySelector(".armblock")).not.toBeNull());
    expect(c.querySelector(".ly-dirty")).toBeNull();
    drag(row(c, 3).querySelector(".armtrack")!, 60, 120);
    expect(c.querySelector(".ly-dirty")).not.toBeNull();
    const ev = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(ev);
    expect(ev.defaultPrevented).toBe(true);
  });

  it("写明现在谁说了算", async () => {
    mode = { ...mode, source: "manual", label: "留守", mode: "home", manual_until_ms: at(22) };
    const { container: c } = page();
    await waitFor(() => expect(c.querySelector(".arm-who")!.textContent).toContain("22:00"));
    expect(c.querySelector(".arm-who")!.textContent).toContain("留守");
    expect(c.querySelector(".arm-who")!.textContent).toContain("恢复按时间表");
  });

  it("W72 页顶「现在」:直接切布防、留守(要确认),临时撤防指到授权页", async () => {
    const { container: c } = page();
    const now = () => c.querySelector(".arm-now")!;
    await waitFor(() => expect(now().textContent).toContain("按时间表"));
    fireEvent.click(btn(now(), "留守"));
    expect(posted.some((p) => p.url === "/api/mode")).toBe(false);
    fireEvent.click(btn(document.querySelector(".modal")!, "留守"));
    await waitFor(() => expect(posted.find((p) => p.url === "/api/mode")?.body).toEqual({ mode: "home" }));
    fireEvent.click(btn(now(), "布防"));
    fireEvent.click(btn(document.querySelector(".modal")!, "布防"));
    await waitFor(() => expect(posted.filter((p) => p.url === "/api/mode").map((p) => p.body.mode)).toEqual(["home", "armed"]));
    expect(now().querySelector('a[href="#/admin/access"]')!.textContent).toContain("临时撤防");
  });

  describe("网页易用性第 1 轮 P0-08:存下去立刻撤防 / 布防,先确认", () => {
    it("现在布防着,新日程此刻没有布防时段:先说会马上撤防,确认了才存", async () => {
      mode = { ...mode, mode: "armed", state: "armed" };
      schedule = { ...schedule, slots: [] , enabled: false };
      const { container: c } = page();
      await waitFor(() => expect(c.querySelector(".arm-who")?.textContent).toContain("22:00"));
      await new Promise((ok) => setTimeout(ok, 20));
      fireEvent.click(c.querySelector("#arm-enabled")!);
      drag(row(c, 2).querySelector(".armtrack")!, 600, 720);
      fireEvent.click(c.querySelector(".arm-save")!);
      await waitFor(() => expect(c.ownerDocument.querySelector(".modal")?.textContent).toContain("全站会马上撤防"));
      expect(posted.some((p) => p.url === "/api/arming/schedule")).toBe(false);
      fireEvent.click(btn(c.ownerDocument.querySelector(".modal")!, "保存"));
      await waitFor(() => expect(posted.some((p) => p.url === "/api/arming/schedule")).toBe(true));
    });

    it("此刻正落在新画的布防时段里:先说会马上布防", async () => {
      const { container: c } = page();
      await waitFor(() => expect(row(c, 0).querySelector(".armblock")).not.toBeNull());
      drag(row(c, 0).querySelector(".armtrack")!, 600, 780);
      fireEvent.click(c.querySelector(".arm-save")!);
      await waitFor(() => expect(c.ownerDocument.querySelector(".modal")?.textContent).toContain("全站会马上布防"));
    });

    it("一段都没有还勾着使用:说整周撤防", async () => {
      const { container: c } = page();
      await waitFor(() => expect(row(c, 0).querySelector(".armblock")).not.toBeNull());
      fireEvent.click(row(c, 0).querySelector(".armblock")!);
      fireEvent.click(btn(c, "删除此时段"));
      fireEvent.click(c.querySelector(".arm-save")!);
      await waitFor(() => expect(c.ownerDocument.querySelector(".modal")?.textContent).toContain("整周都是撤防"));
    });

    // 第 2 轮 N1:手动布防、日程关着,打开日程一存就按日程接管 —— 原来 source==="manual" 直接不确认
    it("手动布防、日程关着:新日程此刻不布防 → 也要先说会马上撤防", async () => {
      mode = { ...mode, mode: "armed", label: "布防", source: "manual", state: "armed", manual_until_ms: null };
      schedule = { ...schedule, slots: [], enabled: false };
      const { container: c } = page();
      await new Promise((ok) => setTimeout(ok, 20));
      fireEvent.click(c.querySelector("#arm-enabled")!);
      drag(row(c, 2).querySelector(".armtrack")!, 600, 720);
      fireEvent.click(c.querySelector(".arm-save")!);
      await waitFor(() => expect(c.ownerDocument.querySelector(".modal")?.textContent).toContain("全站会马上撤防"));
      expect(posted.some((p) => p.url === "/api/arming/schedule")).toBe(false);
    });

    it("手动布防、日程关着:勾上使用但一段都没画 → 说整周撤防", async () => {
      mode = { ...mode, mode: "armed", label: "布防", source: "manual", state: "armed", manual_until_ms: null };
      schedule = { ...schedule, slots: [], enabled: false };
      const { container: c } = page();
      await new Promise((ok) => setTimeout(ok, 20));
      fireEvent.click(c.querySelector("#arm-enabled")!);
      fireEvent.click(c.querySelector(".arm-save")!);
      await waitFor(() => expect(c.ownerDocument.querySelector(".modal")?.textContent).toContain("整周都是撤防"));
      expect(posted.some((p) => p.url === "/api/arming/schedule")).toBe(false);
    });

    it("第 3 轮 config N1:此刻按日程撤防,停用日程 → 确认框写会变成「留守」", async () => {
      const { container: c } = page();
      await waitFor(() => expect(row(c, 0).querySelector(".armblock")).not.toBeNull());
      await new Promise((ok) => setTimeout(ok, 20));
      fireEvent.click(c.querySelector("#arm-enabled")!);
      fireEvent.click(c.querySelector(".arm-save")!);
      await waitFor(() => expect(c.ownerDocument.querySelector(".modal")?.textContent).toContain("这些外围防区会马上布防：北区"));
    });

    it("第 3 轮 config N2:手动留守(外围布防)、日程关着,新日程此刻不布防 → 要确认会撤防", async () => {
      mode = { ...mode, mode: "home", label: "留守", source: "manual", state: "partial", manual_until_ms: null };
      schedule = { ...schedule, slots: [], enabled: false };
      const { container: c } = page();
      await new Promise((ok) => setTimeout(ok, 20));
      fireEvent.click(c.querySelector("#arm-enabled")!);
      drag(row(c, 2).querySelector(".armtrack")!, 600, 720);
      fireEvent.click(c.querySelector(".arm-save")!);
      await waitFor(() => expect(c.ownerDocument.querySelector(".modal")?.textContent).toContain("全站会马上撤防"));
    });

    it("第 3 轮 config N3:临时撤防进行中打开日程 → 说会结束临时撤防", async () => {
      mode = { ...mode, mode: "visitor", label: "临时撤防", source: "manual", state: "partial", manual_until_ms: null, until_ms: at(13) };
      schedule = { ...schedule, slots: [], enabled: false };
      const { container: c } = page();
      await new Promise((ok) => setTimeout(ok, 20));
      fireEvent.click(c.querySelector("#arm-enabled")!);
      drag(row(c, 2).querySelector(".armtrack")!, 600, 720);
      fireEvent.click(c.querySelector(".arm-save")!);
      await waitFor(() => expect(c.ownerDocument.querySelector(".modal")?.textContent).toContain("结束临时撤防"));
    });

    it("第 3 轮 config N4:日程开着、手动期里删光时段 → 也说整周撤防", async () => {
      mode = { ...mode, mode: "armed", label: "布防", source: "manual", state: "armed", manual_until_ms: at(22) };
      const { container: c } = page();
      await waitFor(() => expect(row(c, 0).querySelector(".armblock")).not.toBeNull());
      fireEvent.click(row(c, 0).querySelector(".armblock")!);
      fireEvent.click(btn(c, "删除此时段"));
      fireEvent.click(c.querySelector(".arm-save")!);
      await waitFor(() => expect(c.ownerDocument.querySelector(".modal")?.textContent).toContain("整周都是撤防"));
      expect(posted.some((p) => p.url === "/api/arming/schedule")).toBe(false);
    });

    it("第 3 轮 config N5:今天的「全天撤防」例外会马上撤防 → 先确认;加完刷新「现在」", async () => {
      mode = { ...mode, mode: "armed", label: "按时间表:布防", source: "schedule", state: "armed" };
      const d = new Date();
      const today = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
      const { container: c } = page();
      await waitFor(() => expect(c.querySelector(".arm-ex")).not.toBeNull());
      await new Promise((ok) => setTimeout(ok, 20));
      fireEvent.input(c.querySelector('.arm-ex input[name="first"]')!, { target: { value: today } });
      fireEvent.change(c.querySelector('.arm-ex select[name="state"]')!, { target: { value: "disarmed" } });
      fireEvent.click(btn(c, "添加例外"));
      await waitFor(() => expect(c.ownerDocument.querySelector(".modal")?.textContent).toContain("马上撤防"));
      expect(posted.some((p) => p.url === "/api/arming/exceptions")).toBe(false);
    });

    it("日程开着、手动切换还管着(到下一个变化点):改日程此刻不变,不用确认", async () => {
      mode = { ...mode, mode: "armed", label: "布防", source: "manual", state: "armed", manual_until_ms: at(22) };
      const { container: c } = page();
      await waitFor(() => expect(row(c, 0).querySelector(".armblock")).not.toBeNull());
      drag(row(c, 2).querySelector(".armtrack")!, 600, 720);
      fireEvent.click(c.querySelector(".arm-save")!);
      await waitFor(() => expect(posted.some((p) => p.url === "/api/arming/schedule")).toBe(true));
      expect(c.ownerDocument.querySelector(".modal")).toBeNull();
    });
  });
});


describe("网页易用性第 1 轮 P1-59", () => {
  it("单击不拖:说要按住拖;有图例", async () => {
    const { container: c } = page();
    await waitFor(() => expect(row(c, 0).querySelectorAll(".armblock").length).toBe(1));
    expect(c.querySelector("[data-arm-legend]")!.textContent).toContain("布防");
    drag(row(c, 1).querySelector(".armtrack")!, 600, 605);
    await waitFor(() => expect(c.querySelector("[data-arm-hint]")!.textContent).toContain("按住拖动"));
    expect(row(c, 1).querySelectorAll(".armblock").length).toBe(0);
  });
});

describe("网页易用性第 1 轮 P1-57", () => {
  it("分三个标签:布防时间有顶上保存,另外两个没有", async () => {
    const { container: c } = page();
    await waitFor(() => expect(row(c, 0).querySelector(".armblock")).not.toBeNull());
    expect(c.querySelector(".arm-save")).not.toBeNull();
    expect(c.querySelector(".arm-guard")).toBeNull();
    fireEvent.click(c.querySelector('[data-arm-tab="guard"]')!);
    expect(c.querySelector(".arm-save")).toBeNull();
    expect(c.querySelector(".armgrid")).toBeNull();
  });
});

describe("网页易用性第 1 轮 P2-20", () => {
  it("打开日程却没有时段:当场提醒", async () => {
    schedule = { ...schedule, slots: [], enabled: false };
    const { container: c } = page();
    await waitFor(() => expect(c.querySelector("#arm-enabled")).not.toBeNull());
    await new Promise((ok) => setTimeout(ok, 20));
    expect(c.querySelector("[data-arm-noslots]")).toBeNull();
    fireEvent.click(c.querySelector("#arm-enabled")!);
    expect(c.querySelector("[data-arm-noslots]")!.textContent).toContain("全天都会是撤防");
  });
});

describe("网页易用性第 1 轮 P2-39", () => {
  it("经理在布防页「巡逻日程」里给路线排日程(网页上也能排)", async () => {
    const { container: c } = render(<ArmingPage say={() => {}} now={at(12)} role="owner" />);
    fireEvent.click(c.querySelector('[data-arm-tab="patrols"]')!);
    await waitFor(() => expect(c.querySelector('.arm-patrols select[name="route"]')).not.toBeNull());
    expect(c.querySelector(".arm-patrols")!.textContent).toContain("22:00");
    fireEvent.change(c.querySelector('.arm-patrols select[name="route"]')!, { target: { value: "day" } });
    await waitFor(() => expect(c.querySelector(".arm-patrols")!.textContent).not.toContain("22:00"));
  });
});

describe("第 2 轮 config N4", () => {
  it("经理:没有「临时撤防…」入口(那页打不开),写由管理员设置", async () => {
    const { container: c } = render(<ArmingPage say={() => {}} now={Date.now()} role="owner" />);
    await waitFor(() => expect(c.querySelector("[data-no-visitor]")).not.toBeNull());
    expect(c.querySelector('a[href="#/admin/access"]')).toBeNull();
  });
});

describe("第 4 轮 config N1 / N2:保存前问站点此刻会变成什么", () => {
  it("只给一个防区单独设、此刻那个防区会布防:列出防区再确认(原来只看「全部防区」那份,不问)", async () => {
    const { container: c } = page();
    await waitFor(() => expect(row(c, 0).querySelector(".armblock")).not.toBeNull());
    fireEvent.click(btn(c, "每个防区单独设"));
    fireEvent.click(btn(c, "北区"));
    fireEvent.click(btn(c, "单独设这个防区"));
    drag(row(c, 0).querySelector(".armtrack")!, 600, 840);        // 北区星期一 10–14 点,此刻 12 点
    fireEvent.click(c.querySelector(".arm-save")!);
    await waitFor(() => expect(c.ownerDocument.querySelector(".modal")?.textContent).toContain("北区：撤防 → 布防"));
    expect(posted.some((p) => p.url === "/api/arming/schedule/preview")).toBe(true);
    expect(posted.some((p) => p.url === "/api/arming/schedule")).toBe(false);
  });

  it("previewChanges:逐个防区列出,其余地方单列;全站一样就说全站", async () => {
    const { previewChanges } = await import("./armingpage");
    const before = { mode: "armed", source: "schedule" as const, state: "armed", default_armed: true,
      zones: [{ zone: "东区", armed: true }, { zone: "北区", armed: true }] };
    expect(previewChanges(before, before)).toBeNull();
    const after = { ...before, state: "partial", zones: [{ zone: "东区", armed: false }, { zone: "北区", armed: true }] };
    expect(previewChanges(before, after)).toBe("存下立刻生效：东区：布防 → 撤防。仍要保存？");
    const off = { ...before, state: "disarmed", default_armed: false, zones: [{ zone: "东区", armed: false }, { zone: "北区", armed: false }] };
    expect(previewChanges(before, off)).toContain("全站会马上撤防");
    lang.value = "en";
    const def = { ...before, state: "partial", default_armed: false };
    expect(previewChanges(before, def)).toBe("Saving takes effect right away: everywhere else armed → disarmed. Save anyway?");
    lang.value = "zh";
  });
});

describe("第 4 轮 config N3:删今天的例外", () => {
  it("日程开着、今天有全天撤防:确认框写全站会马上布防;日程关着说不起作用", async () => {
    const today = new Date();
    const d = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}-${String(today.getDate()).padStart(2, "0")}`;
    schedule = { ...schedule, slots: [{ zone: "", day: 0, start: "00:00", end: "24:00" }, ...[1, 2, 3, 4, 5, 6].map((day) => ({ zone: "", day, start: "00:00", end: "24:00" }))],
      exceptions: [{ id: 7, first_day: d, last_day: d, state: "disarmed", note: "" }] };
    mode = { ...mode, state: "disarmed" };
    const { container: c } = page();
    await waitFor(() => expect(c.querySelector(".arm-ex li")).not.toBeNull());
    fireEvent.click(btn(c.querySelector(".arm-ex")!, "删除"));
    await waitFor(() => expect(c.ownerDocument.querySelector(".modal")?.textContent).toContain("全站会马上布防"));
    expect(posted.find((p) => p.url === "/api/arming/schedule/preview")?.body.skip_exception).toBe(7);
  });
});
