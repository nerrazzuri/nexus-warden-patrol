// @vitest-environment happy-dom
// 报警记录页(W44;redesign 第五期 G-records 三栏):左 筛选 + 本班三个数,中 表格(抓拍、时间、事件、位置、负责人、结果),
// 右 选中那条(录像、经过、重新打开);没关的「去处理」跳值班页;截了写明;技术类不列。交班留言页在 notes.tsx。
import { cleanup, fireEvent, render, waitFor } from "@testing-library/preact";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { setFetch } from "./api";
import { AlarmLogPage, alarmsCsv } from "./alarmlog";
import { NotesPage } from "./notes";
import { alertTitle, lang } from "./i18n";
import type { Alert } from "./model";

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
const at = (h: number, m = 0) => new Date(2026, 9, 27, h, m).getTime();
const NOW = at(23, 10);

const alert = (o: Partial<Alert>): Alert => ({
  key: "k", kind: "intrusion", level: "P1", robot: "A", title: "北区有人闯入", detail: "3 号摄像头", first_ms: at(21, 46), last_ms: at(21, 46),
  count: 1, acked_by: "", acked_ms: null, resolved_ms: null, audience: "intrusion", ...o,
});

let alerts: Alert[] = [];
let dayCalls: string[] = [];
let dayTotal: number | null = null;
let truncated = false;
let note: unknown = null;
let posted: unknown[] = [];
let duty: unknown = null;

beforeEach(() => {
  for (const k of ["nexwar.alarms.scope", "nexwar.alarms.kinds", "nexwar.alarms.status"]) localStorage.removeItem(k);
  lang.value = "zh";
  alerts = [];
  dayCalls = [];
  dayTotal = null;
  truncated = false;
  note = null;
  posted = [];
  duty = null;
  setFetch(((url: string, init?: RequestInit) => {
    if (url.startsWith("/api/recordings")) return Promise.resolve(json({ recordings: [], segment_s: 60 }));
    if (url.startsWith("/api/shift-notes")) {
      if (init?.method === "POST") {
        const b = JSON.parse(String(init.body));
        posted.push(b);
        note = { id: 9, at_ms: NOW, author: "wang", text: b.text };
        return Promise.resolve(json({ note }));
      }
      return Promise.resolve(json({ latest: note, recent: note ? [note] : [] }));
    }
    if (url.startsWith("/api/duty-settings")) return Promise.resolve(duty ? json(duty) : json({}, 404));
    if (url.startsWith("/api/alerts?since=")) {
      // 按日期查(站点那边):只回那天的,带总数;记下来给翻页的测试看
      const q = new URLSearchParams(url.split("?")[1]);
      dayCalls.push(url);
      const got = alerts.filter((a) => a.first_ms >= Number(q.get("since")) && a.first_ms < Number(q.get("until")));
      const off = Number(q.get("offset") ?? 0), lim = Number(q.get("limit") ?? 500);
      return Promise.resolve(json({ alerts: got.slice(off, off + lim), total: dayTotal ?? got.length }));
    }
    if (url.startsWith("/api/alerts")) return Promise.resolve(json({ alerts, limit: 500, truncated }));
    return Promise.resolve(json({}, 404));
  }) as typeof fetch);
});
afterEach(cleanup);

const page = (role = "guard") => render(<AlarmLogPage now={NOW} role={role} />);
const rows = (c: Element) => Array.from(c.querySelectorAll("tr.it"));
const scopeTo = (c: Element, v: string) => fireEvent.change(c.querySelector("select[data-scope]")!, { target: { value: v } });
const panel = (c: Element) => c.querySelector(".ev-side")!;

describe("报警记录页", () => {
  it("UIUX-E003:本班 0 条但之前还有没处理的,写出来,点「显示出来」切到那天并只看未关闭的", async () => {
    alerts = [alert({ key: "old", first_ms: at(17, 0) }), alert({ key: "done", first_ms: at(16, 0), resolved_ms: at(16, 5) })];
    const { container: c } = page();
    const hint = await waitFor(() => { const x = c.querySelector("[data-al-older]"); expect(x).not.toBeNull(); return x!; });
    expect(hint.textContent).toContain("本班之前还有 1 条没处理");
    expect(rows(c).length).toBe(0);
    fireEvent.click(hint.querySelector("button")!);
    await waitFor(() => expect(rows(c).length).toBe(1));
    expect((c.querySelector('[data-status="open"]') as HTMLInputElement).checked).toBe(true);
    expect(c.querySelector("[data-al-older]")).toBeNull();
  });

  it("实测查出:站点给的「在哪」写在位置一栏", async () => {
    alerts = [alert({ key: "w", kind: "robot_offline_idle", audience: "offline", robot: "A", title: "机器人离线", detail: "", context: { where: "A区" } as never, first_ms: at(21, 50) })];
    const { container: c } = page();
    await waitFor(() => expect(rows(c).length).toBe(1));
    expect(rows(c)[0].children[3].textContent).toBe("A区");
  });

  it("交班时间按站点设置", async () => {
    duty = { shift_hours: [8, 20], stale_hours: 2 };
    alerts = [alert({ key: "a", first_ms: at(19, 30) }), alert({ key: "b", first_ms: at(20, 30) })];
    const { container: c } = page();
    await waitFor(() => expect(c.querySelector("select[data-scope] option")!.textContent).toContain("20:00"));
    await waitFor(() => expect(rows(c).length).toBe(1));
  });

  it("本班按19点算;标题、本班数跟着", async () => {
    alerts = [alert({ key: "a", first_ms: at(19, 30) }), alert({ key: "b", first_ms: at(18, 0), resolved_ms: at(18, 5) })];
    const { container: c } = page();
    await waitFor(() => expect(rows(c).length).toBe(1));
    expect(c.querySelector(".ev-head h1")!.textContent).toBe("本班 1 条报警");
    expect(c.querySelector(".ev-sum b")!.textContent).toBe("1");
    scopeTo(c, "today");
    await waitFor(() => expect(rows(c).length).toBe(2));
    expect(c.querySelector(".ev-head h1")!.textContent).toBe("今天 2 条报警");
  });

  it("liang-d5 第 5 轮前:选日期去站点按那天查;一天超过 500 条能翻页", async () => {
    alerts = [alert({ key: "a", first_ms: at(19, 30) })];
    dayTotal = 1234;
    const { container: c } = page();
    await waitFor(() => expect(rows(c).length).toBe(1));
    scopeTo(c, "today");
    await waitFor(() => expect(c.querySelector("[data-al-pages]")).not.toBeNull());
    expect(dayCalls.at(-1)).toContain("offset=0");
    expect(c.querySelector("[data-al-pages]")!.textContent).toContain("共 1234 条");
    fireEvent.click([...c.querySelectorAll<HTMLButtonElement>("[data-al-pages] button")].find((b) => b.textContent === "下一页")!);
    await waitFor(() => expect(dayCalls.at(-1)).toContain("offset=500"));
  });

  it("状态:未关闭 / 已关闭", async () => {
    alerts = [alert({ key: "a" }), alert({ key: "b", first_ms: at(20, 0), resolved_ms: at(20, 5), verdict: "handled" })];
    const { container: c } = page();
    await waitFor(() => expect(rows(c).length).toBe(2));
    fireEvent.click(c.querySelector('[data-status="open"]')!);
    expect(rows(c).length).toBe(1);
    expect(rows(c)[0].classList.contains("open")).toBe(true);
    fireEvent.click(c.querySelector('[data-status="closed"]')!);
    expect(rows(c).map((r) => r.getAttribute("data-key"))).toEqual(["b"]);
  });

  it("按类型筛(带条数);清除筛选回全部", async () => {
    alerts = [alert({ key: "a" }), alert({ key: "b", kind: "stuck", audience: "help", title: "C 被挡住了", first_ms: at(22, 58) }),
      alert({ key: "c", kind: "robot_offline", audience: "offline", title: "B 掉线", first_ms: at(19, 31) })];
    const { container: c } = page();
    await waitFor(() => expect(rows(c).length).toBe(3));
    expect(c.querySelector('[data-kind="help"]')!.parentElement!.textContent).toContain("· 1");
    const titles = () => rows(c).map((r) => r.querySelector(".ev-what")!.textContent);
    fireEvent.click(c.querySelector('[data-kind="help"]')!);
    expect(titles()).toEqual([alertTitle("zh", "stuck", "C 被挡住了")]);
    fireEvent.click(Array.from(c.querySelectorAll("button")).find((b) => b.textContent === "清除筛选")!);
    expect(rows(c).length).toBe(3);
  });

  it("机器人 / 摄像头筛", async () => {
    alerts = [alert({ key: "a" }), alert({ key: "b", robot: "B", first_ms: at(22, 0) }), alert({ key: "g", robot: "cctv:北门", first_ms: at(22, 30) })];
    const { container: c } = page();
    await waitFor(() => expect(rows(c).length).toBe(3));
    const sel = c.querySelector("select[data-source]") as HTMLSelectElement;
    expect(Array.from(sel.options).map((o) => o.textContent)).toContain("北门");
    fireEvent.change(sel, { target: { value: "B" } });
    expect(rows(c).map((r) => r.getAttribute("data-key"))).toEqual(["b"]);
  });

  it("误报:结果写误报,负责人写谁关的;右栏写几点关的", async () => {
    alerts = [alert({ resolved_ms: at(21, 49), resolved_by: "wang", verdict: "false_alarm" } as Partial<Alert>)];
    const { container: c } = page();
    await waitFor(() => expect(c.querySelector(".it .res")!.textContent).toContain("误报"));
    expect(rows(c)[0].children[4].textContent).toBe("wang");
    expect(panel(c).textContent).toContain("21:49");
  });

  it("没关、没人管的:负责人「无人」、结果「去处理」跳值班页那一件;只读账号写「未处理」", async () => {
    alerts = [alert({ key: "a" }), alert({ key: "b", first_ms: at(20, 0), acked_by: "gina", acked_ms: at(20, 1) })];
    const { container: c } = page();
    await waitFor(() => expect(rows(c).length).toBe(2));
    const [open, mine] = rows(c);
    expect(open.children[4].textContent).toBe("无人");
    expect(open.querySelector("a.ev-respond")!.getAttribute("href")).toBe("#/duty?alarm=a");
    expect(mine.querySelector(".res")!.textContent).toBe("处理中");
    cleanup();
    const v = render(<AlarmLogPage now={NOW} role="viewer" />);
    await waitFor(() => expect(rows(v.container).length).toBe(2));
    expect(rows(v.container)[0].querySelector("a.ev-respond")).toBeNull();
    expect(rows(v.container)[0].querySelector(".res")!.textContent).toBe("未处理");
  });

  it("右栏:默认最新一条,点哪行看哪行(不弹窗)", async () => {
    alerts = [alert({ key: "a", title: "北区有人闯入" }), alert({ key: "b", first_ms: at(20, 0), resolved_ms: at(20, 1), verdict: "intruder" })];
    const { container: c } = page();
    await waitFor(() => expect(rows(c).length).toBe(2));
    expect(panel(c).querySelector(".evp")!.getAttribute("data-key")).toBe("a");
    fireEvent.click(rows(c)[1]);
    expect(panel(c).querySelector(".evp")!.getAttribute("data-key")).toBe("b");
    expect(rows(c)[1].getAttribute("aria-selected")).toBe("true");
    expect(c.ownerDocument.querySelector(".modal")).toBeNull();
  });

  it("抓拍用录像那一刻的一帧", async () => {
    alerts = [alert({})];
    const { container: c } = page();
    await waitFor(() => expect(c.querySelector(".it img")).not.toBeNull());
    expect(c.querySelector(".it img")!.getAttribute("src")).toBe(`/api/recordings/frame?robot=A&camera=front&t=${at(21, 46)}`);
  });

  it("技术类不列", async () => {
    alerts = [alert({ key: "a" }), alert({ key: "t", kind: "cert_expiring", audience: "owner", title: "证书快到期" })];
    const { container: c } = page();
    await waitFor(() => expect(rows(c).length).toBe(1));
    expect(c.textContent).not.toContain("证书");
  });

  it("截了写明", async () => {
    alerts = [alert({})];
    truncated = true;
    const { container: c } = page();
    await waitFor(() => expect(c.textContent).toContain("仅显示最近 500 条"));
  });

  it("导出表格:筛完的那些行,表头、负责人、结果、备注", () => {
    const csv = alarmsCsv([alert({ key: "a" }), alert({ key: "b", resolved_ms: at(22, 0), resolved_by: "gina", verdict: "false_alarm", context: { note: "风吹的, 纸箱" } } as Partial<Alert>)]);
    const lines = csv.replace(/^\ufeff/, "").split("\r\n");
    expect(lines[0]).toBe("时间,事件,位置,负责人,结果,备注");
    expect(lines[1]).toContain(",无人,未处理,");
    expect(lines[2]).toContain(",gina,误报,风吹的，纸箱");
    lang.value = "en";
    try {
      const en = alarmsCsv([alert({ resolved_ms: at(22, 0), resolved_by: "gina", verdict: "false_alarm", context: { note: 'a "box", wind' } } as Partial<Alert>)]);
      expect(en).toContain(',gina,False alarm,"a ""box"", wind"');
    } finally { lang.value = "zh"; }
  });

  it("左栏三个标签:报警 / 录像 / 交班留言", async () => {
    const { container: c } = page();
    expect(Array.from(c.querySelectorAll(".ev-tabs a")).map((a) => a.getAttribute("href"))).toEqual(["#/alarms", "#/recordings", "#/notes"]);
  });
});

describe("交班留言页(第五期从报警记录页搬过来)", () => {
  it("列出留言,写一条进去", async () => {
    note = { id: 1, at_ms: at(19, 2), author: "li", text: "北区东边的灯坏了" };
    const { container: c } = render(<NotesPage role="guard" me="wang" />);
    await waitFor(() => expect(c.querySelector(".notes-list")!.textContent).toContain("北区东边的灯坏了"));
    expect(c.querySelector(".notes-list")!.textContent).toContain("li");
    expect(c.querySelector(".notes-list")!.textContent).toContain("19:02");
    fireEvent.input(c.querySelector("textarea")!, { target: { value: "3 号摄像头误报多" } });
    fireEvent.click(Array.from(c.querySelectorAll("button")).find((b) => b.textContent === "留言")!);
    await waitFor(() => expect(c.querySelector(".notes-list")!.textContent).toContain("3 号摄像头误报多"));
    expect(posted).toEqual([{ text: "3 号摄像头误报多" }]);
  });

  it("自己写的标「你」", async () => {
    note = { id: 9, at_ms: NOW, author: "wang", text: "东门锁坏了" };
    const { container: c } = render(<NotesPage role="guard" me="wang" />);
    await waitFor(() => expect(c.querySelector(".notes-list")!.textContent).toContain("wang (你)"));
  });

  it("只读账号不能留话", async () => {
    const { container: c } = render(<NotesPage role="viewer" />);
    expect(c.querySelector("textarea")).toBeNull();
    expect(c.textContent).toContain("不能写");
  });
});

describe("第 3 轮 duty N8", () => {
  it("有人接手的写谁在处理;处理完的经过里带备注", async () => {
    alerts = [
      alert({ key: "a", resolved_ms: null, acked_by: "gina" }),
      alert({ key: "b", first_ms: at(20, 0), resolved_ms: NOW - 1000, resolved_by: "gina", verdict: "handled", context: { note: "门没锁好" } } as Partial<Alert>),
    ];
    const { container: c } = page();
    await waitFor(() => expect(rows(c).length).toBe(2));
    expect(rows(c)[0].children[4].textContent).toBe("gina");
    fireEvent.click(rows(c)[1]);
    expect(panel(c).querySelector(".evp-log")!.textContent).toContain("门没锁好");
  });

  it("UIUX-032:英文界面里站点写的备注(「B 补跑了」)翻成英文", async () => {
    lang.value = "en";
    try {
      alerts = [
        alert({ key: "b", resolved_ms: NOW - 1000, resolved_by: "system", verdict: "handled", context: { note: "B 补跑了" } } as Partial<Alert>),
      ];
      const { container: c } = page();
      await waitFor(() => expect(panel(c).querySelector(".evp-log")).not.toBeNull());
      expect(panel(c).querySelector(".evp-log")!.textContent).toContain("B ran it late");
    } finally { lang.value = "zh"; }
  });
});

describe("第 4 轮 layout r3-N3 / N6", () => {
  it("读不到报警:计数写「–」,列表写正在重试,不写「没有」", async () => {
    setFetch(((url: string) => url.startsWith("/api/alerts")
      ? Promise.reject(new TypeError("Failed to fetch")) : Promise.resolve(json({}))) as typeof fetch);
    const { container: c } = page();
    await waitFor(() => expect(c.querySelector("[data-load-failed]")).not.toBeNull());
    expect([...c.querySelectorAll(".ev-sum b")].map((b) => b.textContent)).toEqual(["–", "–", "–"]);
    expect(c.textContent).not.toContain("没有");
  });
});

// 网页第 5 轮 r5-layout-N1:断网恢复后报警记录页要 10–20 秒才回来(读不到要等下一次 30 秒的轮询)
describe("minor #30 断网恢复", () => {
  it("读不到时 3 秒再试,网一通马上回来", async () => {
    let down = true;
    setFetch(((url: string) => {
      if (url.startsWith("/api/alerts")) return down ? Promise.reject(new TypeError("Failed to fetch")) : Promise.resolve(json({ alerts: [], limit: 500 }));
      return Promise.resolve(json({}));
    }) as typeof fetch);
    const { container: c } = page();
    await waitFor(() => expect(c.querySelector("[data-load-failed]")).not.toBeNull());
    await new Promise((r) => setTimeout(r, 3500));              // 第一次重试还是断的
    expect(c.querySelector("[data-load-failed]")).not.toBeNull();
    down = false;
    await waitFor(() => expect(c.querySelector("[data-load-failed]")).toBeNull(), { timeout: 4500 });
  }, 12000);
});

describe("第 4 轮 r3-duty-N7", () => {
  it("摄像头、站点的报警不给「看录像」", async () => {
    const { hasRecording } = await import("./alarmlog");
    expect(hasRecording({ robot: "cctv:gate", kind: "cctv_offline" })).toBe(false);
    expect(hasRecording({ robot: "site", kind: "backup_stale" })).toBe(false);
    expect(hasRecording({ robot: "A", kind: "fallen" })).toBe(true);
  });
});
