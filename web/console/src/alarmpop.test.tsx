// @vitest-environment happy-dom
// 第三档 #40(用户 11-14):网页的报警弹窗和声音。跟站点的升档走:新来一条 P1 / P2 弹卡片、响一声;
// 升到「声音」档(入侵一来就是,别的 P1 没人确认 5 分钟)一直响到有人确认。P3 不弹不响。
import { cleanup, fireEvent, render } from "@testing-library/preact";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { AlarmPop, alarmSound, setAlarmSound, type Beeper } from "./alarmpop";
import { lang } from "./i18n";
import type { Me } from "./app";
import type { Alert } from "./model";
import { TopBar } from "./shell";

const alert = (o: Partial<Alert> = {}): Alert => ({
  key: "k1", kind: "robot_fell", level: "P1", robot: "A", title: "A 摔倒了", detail: "", first_ms: 1, last_ms: 1, count: 1,
  acked_by: "", acked_ms: null, resolved_ms: null, audience: "help", context: {}, ...o,
});

class FakeBeeper implements Beeper {
  chimes: string[] = [];
  ringing = false;
  rings: boolean[] = [];
  blocked = false;
  unlocks = 0;
  chime(level: "P1" | "P2") { this.chimes.push(level); }
  ring(on: boolean) { if (on !== this.ringing) this.rings.push(on); this.ringing = on; }
  ready() { return !this.blocked; }
  unlock() { this.unlocks++; this.blocked = false; }
}

let b: FakeBeeper;
let acks: string[];
let gone: number;
const pop = (alerts: Alert[], o: { role?: string; onDuty?: boolean } = {}) => (
  <AlarmPop alerts={alerts} role={o.role ?? "guard"} onDuty={o.onDuty ?? false} beeper={b}
    onAck={(a) => acks.push(a.key)} onGo={() => gone++} />
);

beforeEach(() => {
  lang.value = "zh";
  b = new FakeBeeper();
  acks = [];
  gone = 0;
  try { localStorage.clear(); } catch { /* 没有 */ }
  alarmSound.value = true;
});
afterEach(() => cleanup());

describe("报警弹窗", () => {
  it("新来一条 P1:弹卡片写标题,响一声高音;同一条再刷新不再响", () => {
    const r = render(pop([alert()]));
    const card = r.container.querySelector("[data-alarm-pop]");
    expect(card?.textContent).toContain("A 摔倒了");
    expect(card?.getAttribute("data-level")).toBe("P1");
    expect(card?.textContent).toContain("A · ");   // 哪台机器人(截图核对:原来只写「发现人员」)
    expect(b.chimes).toEqual(["P1"]);
    r.rerender(pop([alert({ last_ms: 5, count: 2 })]));
    expect(b.chimes).toEqual(["P1"]);
  });

  it("P2 弹琥珀卡片、响一声低音;P3、已确认的、解决了的、不给保安看的不弹不响", () => {
    const r = render(pop([alert({ key: "p3", level: "P3" }), alert({ key: "ok", acked_ms: 9, acked_by: "gina" }),
      alert({ key: "done", resolved_ms: 9 }), alert({ key: "own", audience: "owner" })]));
    expect(r.container.querySelector("[data-alarm-pop]")).toBeNull();
    expect(b.chimes).toEqual([]);
    r.rerender(pop([alert({ key: "p2", level: "P2", title: "B 离线" })]));
    expect(r.container.querySelector("[data-alarm-pop]")?.getAttribute("data-level")).toBe("P2");
    expect(b.chimes).toEqual(["P2"]);
  });

  it("「我来处理」确认这一条;「去值守页」跳过去;「关闭」只关这一条,再来一条新的照样弹", () => {
    const r = render(pop([alert()]));
    fireEvent.click(r.getByText("我来处理"));
    expect(acks).toEqual(["k1"]);
    fireEvent.click(r.getByText("去值守页"));
    expect(gone).toBe(1);
    fireEvent.click(r.getByLabelText("关闭"));
    expect(r.container.querySelector("[data-alarm-pop]")).toBeNull();
    r.rerender(pop([alert(), alert({ key: "k2", title: "B 摔倒了" })]));
    expect(r.container.querySelector("[data-alarm-pop]")?.textContent).toContain("B 摔倒了");
    expect(b.chimes).toEqual(["P1", "P1"]);
  });

  it("好几条:先给最要紧的(没确认的 P1 在 P2 前),写「另有 N 件」", () => {
    const r = render(pop([alert({ key: "p2", level: "P2", title: "B 离线", last_ms: 9 }), alert({ title: "A 摔倒了" })]));
    const card = r.container.querySelector("[data-alarm-pop]")!;
    expect(card.textContent).toContain("A 摔倒了");
    expect(card.textContent).toContain("另有 1 件");
  });

  it("在值守页不弹(那里有横幅),但照样响", () => {
    const r = render(pop([alert()], { onDuty: true }));
    expect(r.container.querySelector("[data-alarm-pop]")).toBeNull();
    expect(b.chimes).toEqual(["P1"]);
  });

  it("只读账号:卡片照弹、没有「我来处理」、不响", () => {
    const r = render(pop([alert({ channel: "sound" })], { role: "viewer" }));
    expect(r.container.querySelector("[data-alarm-pop]")).not.toBeNull();
    expect(r.queryByText("我来处理")).toBeNull();
    expect(b.chimes).toEqual([]);
    expect(b.ringing).toBe(false);
  });
});

describe("报警声音", () => {
  it("升到声音档、没人确认:一直响;有人确认了就停", () => {
    const r = render(pop([alert({ channel: "screen" })]));
    expect(b.ringing).toBe(false);
    r.rerender(pop([alert({ channel: "sound" })]));
    expect(b.ringing).toBe(true);
    r.rerender(pop([alert({ channel: "sound", acked_ms: 9, acked_by: "gina" })]));
    expect(b.ringing).toBe(false);
    expect(b.rings).toEqual([true, false]);
  });

  it("关了卡片照样响(要有人确认才停);离开页面停", () => {
    const r = render(pop([alert({ channel: "sound" })]));
    fireEvent.click(r.getByLabelText("关闭"));
    expect(b.ringing).toBe(true);
    r.unmount();
    expect(b.ringing).toBe(false);
  });

  it("这台浏览器关了声音:不响一声、也不一直响;卡片上说声音关着", () => {
    setAlarmSound(false);
    const r = render(pop([alert({ channel: "sound" })]));
    expect(b.chimes).toEqual([]);
    expect(b.ringing).toBe(false);
    expect(r.container.querySelector("[data-alarm-pop]")?.textContent).toContain("这台电脑的报警声音关着");
  });

  it("记在这台浏览器上:关了刷新还是关的", () => {
    setAlarmSound(false);
    expect(localStorage.getItem("nexwar.alarmSound")).toBe("off");
    setAlarmSound(true);
    expect(localStorage.getItem("nexwar.alarmSound")).toBeNull();
  });

  it("浏览器还不让出声(刷新后没点过页面):卡片上一个「点这里开声音」,点了解锁", () => {
    b.blocked = true;
    const r = render(pop([alert({ channel: "sound" })]));
    fireEvent.click(r.getByText("点这里开声音"));
    expect(b.unlocks).toBe(1);
    expect(r.queryByText("点这里开声音")).toBeNull();
  });
});

describe("账号菜单里的报警声音开关", () => {
  const me = (role: string) => ({ name: "gina", display_name: "", role }) as unknown as Me;
  const bar = (role: string) => render(<TopBar me={me(role)} page="alarms" mode={null} alarms={0} now={0} pref="auto" onPref={() => {}}
    onStop={() => {}} onSignOut={() => {}} onSay={() => {}} />);

  it("能处理报警的:开 / 关两个键,点「关」记下来", () => {
    const { container: c } = bar("guard");
    fireEvent.click(c.querySelector(".usermenu > .who")!);
    expect(c.querySelector('[data-alarm-sound="on"]')?.getAttribute("aria-pressed")).toBe("true");
    fireEvent.click(c.querySelector('[data-alarm-sound="off"]')!);
    expect(alarmSound.value).toBe(false);
    expect(c.querySelector('[data-alarm-sound="off"]')?.getAttribute("aria-pressed")).toBe("true");
  });

  it("只读账号不响,菜单里没有这个开关", () => {
    const { container: c } = bar("viewer");
    fireEvent.click(c.querySelector(".usermenu > .who")!);
    expect(c.querySelector("[data-alarm-sound]")).toBeNull();
  });
});
