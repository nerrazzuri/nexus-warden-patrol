// @vitest-environment happy-dom
// W44 第二期 布防时间页(设计 §5.1):一周七行色块、全部一样 / 每个防区单独设、例外、交班时间、保存、没存提醒、谁说了算。
import { cleanup, fireEvent, render, waitFor } from "@testing-library/preact";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { setFetch } from "./api";
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
    fireEvent.click(row(c, 0).querySelector(".arm-copy")!);
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
