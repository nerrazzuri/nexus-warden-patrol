// @vitest-environment happy-dom
// 单台机器人控制(redesign 第四期 G-robot):值班页右栏「Details」进,在中间那一块里切换(不弹窗)。
// 画面 + 云台 + 雨刷、喊话(常用话、打字、语言)、警示(警灯、警笛、录好的话)、当前任务(停下 / 回待命 / 回原点)、
// 派巡逻、姿态(当场确认)、重新定位、今天这台的事。经理只派巡逻、停下;只读只看。
import { cleanup, fireEvent, render, waitFor } from "@testing-library/preact";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { setFetch } from "./api";
import { lang } from "./i18n";
import type { UnitInfo } from "./live";
import type { Alert } from "./model";
import { RobotControl } from "./robotctl";
import type { RobotCard } from "./robotspage";

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
const NOW = Date.UTC(2026, 10, 15, 15, 40);
const DETER = { outputs: ["speaker", "strobe", "siren", "ptz", "wiper"], max_s: 300, tts: true, clips: ["restricted"], tts_langs: ["zh", "en"] };
const unit = (o: Partial<UnitInfo> = {}): UnitInfo => ({
  robot: {
    robot_id: "A", active: true, fresh: true, revoked: false, held: null,
    status: { online: true, last_seen: NOW / 1000 - 1, task: { task_id: "t1", kind: "patrol", state: "running" } },
    capabilities: { tasks: { video: { cameras: ["front", "back", "thermal"] }, relocalize: { global: true }, deter: DETER, posture: { modes: ["stand", "lie"] } } },
    loc: { pose: { x: 1, y: 2, yaw: 0 }, anchored: true },
  } as UnitInfo["robot"],
  state: "patrolling", battery: 62, task: "guard-1 · lap 3", ...o,
});
const CARD: Partial<RobotCard> = {
  robot_id: "A", name: "", revoked: false, online: true, ever_seen: true, battery_pct: 62,
  postures: ["stand", "lie"], task: "t1", task_what: { kind: "patrol", route: "guard-1", forever: false }, lap: { n: 3, of: 5 },
  held: null, home_set: true, standby_set: true, map: { id: "m1", version: "1", match: true },
  deter: DETER,
};
/** 空闲的(没有任务号)。 */
const idle = (o: Partial<UnitInfo> = {}) => { const x = unit({ state: "idle", task: "", ...o }); (x.robot.status as { task?: unknown }).task = null; return x; };
let card: Partial<RobotCard> | null = CARD;
let posts: { url: string; body: Record<string, unknown> }[] = [];

beforeEach(() => {
  lang.value = "en";
  card = { ...CARD };
  posts = [];
  vi.stubGlobal("IntersectionObserver", undefined);
  setFetch(((url: string, init?: RequestInit) => {
    if (init?.method === "POST") {
      posts.push({ url, body: JSON.parse(String(init.body ?? "{}")) });
      return Promise.resolve(json({ ack: { accepted: true } }));
    }
    if (url === "/api/robots/overview") return Promise.resolve(card ? json({ robots: [card] }) : json({ error: "forbidden" }, 403));
    if (url === "/api/robots/A") return Promise.resolve(json({ status: { task: { task_id: "t1" } } }));
    if (url === "/api/schedule") return Promise.resolve(json({ missions: ["guard-1", "guard-2"] }));
    if (url === "/api/routes") return Promise.resolve(json({ routes: [{ id: "guard-1", map_id: "m1", map_version: "1", title: "guard-1" }, { id: "guard-2", map_id: "m1", map_version: "1" }] }));
    if (url === "/api/voice-presets") return Promise.resolve(json({ presets: [{ lang: "en", text: "Private property. Please leave." }] }));
    return Promise.resolve(json({}, 404));
  }) as typeof fetch);
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

const alerts: Alert[] = [{
  key: "k1", kind: "obstructed", level: "P2", robot: "A", title: "Obstructed, east corridor", detail: "", first_ms: NOW - 3_600_000,
  last_ms: NOW - 3_600_000, count: 1, acked_by: "", acked_ms: null, resolved_ms: NOW - 3_500_000, audience: "help",
}];
const show = (role = "guard", u = unit(), o: { onBack?: () => void; onLook?: (id: string) => void; onFind?: (id: string) => void } = {}) =>
  render(<RobotControl u={u} role={role} now={NOW} alerts={alerts} patrols={[]} since={NOW - 5 * 3_600_000} say={vi.fn()}
    refresh={vi.fn(async () => {})} onBack={o.onBack ?? (() => {})} onLook={o.onLook ?? (() => {})} onFind={o.onFind} />).container;
const btn = (c: Element, text: string) => {
  const b = Array.from(c.querySelectorAll("button")).find((x) => x.textContent === text);
  if (!b) throw new Error(`no button ${text}: ${Array.from(c.querySelectorAll("button")).map((x) => x.textContent).join(" | ")}`);
  return b as HTMLButtonElement;
};
/** 等上一条命令发完(发的时候按钮灰着)再点。 */
const press = async (c: Element, text: string) => {
  await waitFor(() => expect(btn(c, text).disabled).toBe(false));
  fireEvent.click(btn(c, text));
};
const pressSel = async (c: Element, sel: string) => {
  await waitFor(() => expect((c.querySelector(sel) as HTMLButtonElement).disabled).toBe(false));
  fireEvent.click(c.querySelector(sel)!);
};
const posted = (path: string) => posts.filter((p) => p.url === path).map((p) => p.body);

describe("单台机器人控制 · 保安", () => {
  it("协助定位(对齐老值班页):回全场地图在地图上点它;经理、只读没有", () => {
    const onFind = vi.fn();
    const c = show("guard", unit(), { onFind });
    fireEvent.click(c.querySelector("[data-find]")!);
    expect(onFind).toHaveBeenCalledWith("A");
    cleanup();
    expect(show("owner", unit(), { onFind }).querySelector("[data-find]")).toBeNull();
    cleanup();
    expect(show("viewer", unit(), { onFind }).querySelector("[data-find]")).toBeNull();
  });

  it("页头:回全场、名字、状态、在做什么;画面按这台有的摄像头分前 / 后 / 热成像", async () => {
    const back = vi.fn();
    const c = show("guard", unit(), { onBack: back });
    await waitFor(() => expect(c.querySelector(".rc-task-now")).not.toBeNull());
    expect(c.querySelector(".rc-head")!.textContent).toContain("Patrolling");
    expect(c.querySelector(".rc-head")!.textContent).toContain("62%");
    expect(Array.from(c.querySelectorAll(".rc-cams button")).map((b) => b.textContent)).toEqual(["Front", "Rear", "Thermal"]);
    await press(c, "Site view");
    expect(back).toHaveBeenCalled();
    expect(c.querySelector(".modal")).toBeNull();
  });

  it("云台:点一下转 15°、读数跟着变;回正归零;雨刷 10 秒", async () => {
    const c = show();
    await waitFor(() => expect(c.querySelector(".rc-ptz")).not.toBeNull());
    await pressSel(c, ".rc-ptz [data-ptz=right]");
    await waitFor(() => expect(posted("/api/robots/A/deter")).toEqual([{ output: "ptz", on: true, pan: 15, tilt: 0 }]));
    expect(c.querySelector(".rc-ptz-read")!.textContent).toContain("15°");
    await pressSel(c, ".rc-ptz [data-ptz=center]");
    await waitFor(() => expect(posted("/api/robots/A/deter")[1]).toEqual({ output: "ptz", on: true, pan: 0, tilt: 0 }));
    await press(c, "Wiper 10 s");
    await waitFor(() => expect(posted("/api/robots/A/deter")[2]).toEqual({ output: "wiper", on: true, max_s: 10 }));
  });

  it("喊话:常用话一按就念;打字可选语言;停止", async () => {
    const c = show();
    await waitFor(() => expect(c.querySelector("[data-voice-presets]")).not.toBeNull());
    await press(c, "Private property. Please leave.");
    await waitFor(() => expect(posted("/api/robots/A/deter")[0]).toEqual({ output: "speaker", on: true, max_s: 60, clip: "tts:en:Private property. Please leave." }));
    fireEvent.change(c.querySelector("select[name=say_lang]")!, { target: { value: "en" } });
    fireEvent.input(c.querySelector("input[name=say]")!, { target: { value: "Security is on the way" } });
    await press(c, "Speak");
    await waitFor(() => expect(posted("/api/robots/A/deter")[1]).toEqual({ output: "speaker", on: true, max_s: 60, clip: "tts:en:Security is on the way" }));
    await press(c, "Stop");
    await waitFor(() => expect(posted("/api/robots/A/deter")[2]).toEqual({ output: "speaker", on: false }));
  });

  it("警示:警灯带时长、关;警笛;录好的话", async () => {
    const c = show();
    await waitFor(() => expect(c.querySelector(".rc-deter")).not.toBeNull());
    fireEvent.change(c.querySelector("select[name=strobe_s]")!, { target: { value: "30" } });
    await press(c, "Strobe on");
    await waitFor(() => expect(posted("/api/robots/A/deter")[0]).toEqual({ output: "strobe", on: true, max_s: 30 }));
    await press(c, "Off");
    await waitFor(() => expect(posted("/api/robots/A/deter")[1]).toEqual({ output: "strobe", on: false }));
    await press(c, "Sound siren");
    await waitFor(() => expect(posted("/api/robots/A/deter")[2]).toEqual({ output: "siren", on: true, max_s: 30 }));
    await press(c, "Restricted area (EN)");
    await waitFor(() => expect(posted("/api/robots/A/deter")[3]).toEqual({ output: "speaker", on: true, max_s: 60, clip: "restricted" }));
  });

  it("当前任务:写在跑什么、第几圈;停下(带任务号)、回待命点;忙的时候回原点要先当场确认", async () => {
    const c = show();
    await waitFor(() => expect(c.querySelector(".rc-task-now")!.textContent).toBe("Running guard-1 · Loop 3 of 5"));
    await press(c, "Stop in place");
    await waitFor(() => expect(posted("/api/robots/A/abort")).toEqual([{ task_id: "t1" }]));
    await press(c, "Return to standby");
    await waitFor(() => expect(posted("/api/robots/A/standby/return")).toEqual([{}]));
    await press(c, "Stop and return home");
    expect(c.querySelector(".modal")).toBeNull();
    expect(c.querySelector(".rc-ask")!.textContent).toContain("go back to the home point");
    fireEvent.click(c.querySelector(".rc-ask .btn.primary")!);
    await waitFor(() => expect(posted("/api/robots/A/home/return")).toEqual([{ abort: true }]));
  });

  it("派巡逻:选路线、几圈;正在跑的时候按钮叫「排队」并说排在当前这趟后面", async () => {
    const c = show();
    await waitFor(() => expect(c.querySelectorAll("select[name=route] option").length).toBe(3));
    expect(c.querySelector(".rc-dispatch")!.textContent).toContain("Starts after the current run");
    fireEvent.change(c.querySelector("select[name=route]")!, { target: { value: "guard-2" } });
    await press(c, "Queue");
    await waitFor(() => expect(posted("/api/robots/A/patrol")).toEqual([{ mission_id: "guard-2", loops: 1 }]));
  });

  it("空闲时按钮叫「开始巡逻」;「派去看一眼…」交给值班页的地图", async () => {
    card = { ...CARD, task: null, task_what: null, lap: null };
    const look = vi.fn();
    const c = show("guard", idle(), { onLook: look });
    await waitFor(() => expect(c.querySelector(".rc-task-now")!.textContent).toContain("No task running"));
    expect(btn(c, "Start patrol")).toBeTruthy();
    expect(btn(c, "Return home").disabled).toBe(false);
    await press(c, "Spot check…");
    expect(look).toHaveBeenCalledWith("A");
  });

  it("姿态:写现在的姿态;换姿态先在原地确认(不弹窗)", async () => {
    card = { ...CARD, task: null, task_what: null, lap: null };
    const c = show("guard", idle());
    await waitFor(() => expect(c.querySelector(".rc-posture")).not.toBeNull());
    await press(c, "Lie down");
    expect(c.querySelector(".modal")).toBeNull();
    expect(c.querySelector(".rc-ask")!.textContent).toContain("Make sure nobody is next to it");
    fireEvent.click(c.querySelector(".rc-ask .btn.primary")!);
    await waitFor(() => expect(posted("/api/robots/A/posture")).toEqual([{ mode: "lie" }]));
  });

  it("定位:写定位状态;重新定位(整张图上找)", async () => {
    const c = show();
    await waitFor(() => expect(c.querySelector(".rc-loc")!.textContent).toContain("Good"));
    await press(c, "Re-localize");
    await waitFor(() => expect(posted("/api/robots/A/relocalize")).toEqual([{ global: true }]));
  });

  it("被叫停的:先说谁什么时候叫停的、给「恢复」", async () => {
    const u = unit({ state: "manual" });
    u.robot.held = { by: "gina", at_ms: NOW - 60_000 };
    const c = show("guard", u);
    await waitFor(() => expect(c.querySelector(".rc-held")).not.toBeNull());
    expect(c.querySelector(".rc-held")!.textContent).toContain("gina");
    await press(c, "Resume");
    await waitFor(() => expect(posted("/api/robots/A/resume")).toEqual([{}]));
  });

  it("读不到机器人概况(保安):按实时数据照样能控制;任务写实时数据里的说法", async () => {
    card = null;
    const c = show();
    await waitFor(() => expect(c.querySelector("[data-voice-presets]")).not.toBeNull());
    expect(c.querySelector(".rc-task-now")!.textContent).toBe("guard-1 · lap 3");
    expect(c.querySelector(".rc-ptz")).not.toBeNull();
    expect(btn(c, "Lie down")).toBeTruthy();
    expect(btn(c, "Sound siren")).toBeTruthy();
  });

  it("今天:这台今天的事(告警、关掉)", async () => {
    const c = show();
    await waitFor(() => expect(c.querySelector(".rc-today")!.textContent).toContain("Obstructed, east corridor"));
  });

  it("离线:控制按钮都灰着,说为什么", async () => {
    const c = show("guard", unit({ state: "offline" }));
    await waitFor(() => expect(c.querySelector(".rc-off")).not.toBeNull());
    await waitFor(() => expect(btn(c, "Strobe on")).toBeTruthy());
    expect(btn(c, "Return to standby").disabled).toBe(true);
    expect(btn(c, "Strobe on").disabled).toBe(true);
  });
});

describe("单台机器人控制 · 经理、只读", () => {
  it("经理:能派巡逻、停下;没有云台、喊话、警示、姿态、定位按钮,写由值班保安操作", async () => {
    const c = show("owner");
    await waitFor(() => expect(c.querySelector(".rc-dispatch select[name=route]")).not.toBeNull());
    await waitFor(() => expect(c.querySelector(".rc-guard-only")).not.toBeNull());
    expect(btn(c, "Stop in place")).toBeTruthy();
    expect(c.querySelector(".rc-ptz")).toBeNull();
    expect(c.querySelector("[data-voice-presets]")).toBeNull();
    expect(c.querySelector(".rc-deter button")).toBeNull();
    expect(c.querySelector(".rc-posture button")).toBeNull();
    expect(Array.from(c.querySelectorAll("button")).some((b) => b.textContent === "Re-localize")).toBe(false);
    expect(Array.from(c.querySelectorAll("button")).some((b) => b.textContent === "Return to standby")).toBe(false);
    expect(c.querySelector(".rc-guard-only")!.textContent).toContain("guard on duty");
  });

  it("只读:只有回全场;别的都是文字", async () => {
    const c = show("viewer");
    await waitFor(() => expect(c.querySelector(".rc-task-now")).not.toBeNull());
    expect(Array.from(c.querySelectorAll("button")).map((b) => b.textContent).filter((x) => !["Front", "Rear", "Thermal"].includes(x ?? ""))).toEqual(["Site view"]);
  });
});

describe("单台机器人控制 · 从老机器人页搬过来的(第六期)", () => {
  it("W8-02 / UIUX-022:画在别的地图版本上的路线选不了,原因整句写在下拉外面", async () => {
    card = { ...CARD, map: { id: "m1", version: "2", match: true } };
    const c = show("guard", idle());
    await waitFor(() => expect(c.querySelector("[data-route-why]")).not.toBeNull());
    expect(c.querySelector("[data-route-why]")!.textContent).toContain("guard-1");
    expect((c.querySelector('select[name="route"] option[value="guard-1"]') as HTMLOptionElement).disabled).toBe(true);
  });

  it("第 2 轮 N2:没原点、没待命点 —— 写为什么灰着;管理员给去处理的链接,保安只有文字", async () => {
    card = { ...CARD, home_set: false, standby_set: false };
    const c = show("admin", idle());
    await waitFor(() => expect(c.querySelector("[data-setup-why]")).not.toBeNull());
    expect(c.querySelector('[data-setup-why] a[href="#/admin/localization"]')).not.toBeNull();
    expect(c.querySelector('[data-setup-why] a[href="#/admin/layout?tab=standby"]')).not.toBeNull();
    cleanup();
    const g = show("guard", idle());
    await waitFor(() => expect(g.querySelector("[data-setup-why]")).not.toBeNull());
    expect(g.querySelector("[data-setup-why] a")).toBeNull();
  });

  it("嵌在现场设置 → 机器人里:没有自己的页头、没有「派去看一眼」,右栏末尾接别的内容", async () => {
    const c = render(<RobotControl u={idle()} role="admin" now={NOW} alerts={[]} patrols={[]} since={NOW - 3_600_000} say={vi.fn()}
      refresh={vi.fn(async () => {})} onBack={() => {}} embedded sideExtra={<p data-extra="1">x</p>} />).container;
    await waitFor(() => expect(c.querySelector(".rc-dispatch")).not.toBeNull());
    expect(c.querySelector(".rc-head")).toBeNull();
    expect(c.querySelector(".rc-look")).toBeNull();
    expect(c.querySelector(".rc-side")!.lastElementChild!.getAttribute("data-extra")).toBe("1");
  });
});
