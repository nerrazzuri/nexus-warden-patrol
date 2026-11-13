// @vitest-environment happy-dom
// W44 第四期 地图编辑器:橡皮擦一笔发出去的点和粗细、另存前列出面积要确认、特殊地面楼梯默认放慢、摆正只改显示、
// 栅格换了说有人改过、只改显示的不另存新版本。
import { act, cleanup, fireEvent, render, waitFor } from "@testing-library/preact";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { setFetch } from "./api";
import { lang } from "./i18n";
import type { OwnLayer } from "./layoutpage";
import { editTarget, MapEditPage } from "./mapedit";

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
const META = { width: 100, height: 100, m_per_px: 0.1, left_x: 0, top_y: 10, zones: [], rotation_deg: 5 };

let posted: { url: string; body: Record<string, unknown> }[];
let editReply: number;
let editBody: Record<string, unknown>;
let zones: Record<string, unknown>;
let draftState: { draft: boolean; from: string | null; zones_removed?: string[] };
const POOL = { id: "n1", kind: "nogo", label: "泳池", polygon: [[1, 1], [3, 1], [3, 3]] };
beforeEach(() => {
  lang.value = "zh";
  posted = [];
  editReply = 200;
  editBody = { version: "4", erased_m2: 1, from: "3", draft: true };
  draftState = { draft: false, from: null };
  zones = { revision: 2, zones: [], confirmed: { revision: 2, by: "olga", at_ms: 1, current: true, how: "confirm" }, held: [] };
  location.hash = "#/admin/mapedit?map=home&version=3";
  setFetch(((url: string, init?: RequestInit) => {
    if (init?.method === "POST") {
      const body = JSON.parse(String(init.body ?? "{}"));
      posted.push({ url, body });
      if (url.endsWith("/edit")) return Promise.resolve(editReply === 200 ? json(editBody) : json({ error: "换了" }, editReply));
      return Promise.resolve(json(body));
    }
    if (url.endsWith("/draft")) return Promise.resolve(json(draftState));
    if (url.endsWith("/zones")) return Promise.resolve(json(url.includes("/home/4/") ? { ...zones, revision: 7 } : zones));
    if (url.startsWith("/api/robots")) return Promise.resolve(json({ robots: [] }));
    if (url.endsWith("/preview")) return Promise.resolve(json(META));
    if (url.endsWith("/noise")) return Promise.resolve(json({ digest: "abc", specks: [] }));
    if (url.endsWith("/display")) return Promise.resolve(json({ rotate_deg: null, basemap: null, regions: [], terrain: [] }));
    return Promise.resolve(json({}, 404));
  }) as typeof fetch);
});
afterEach(cleanup);

let fakeK = 1;
const Fake = (o: OwnLayer) => <div class="fakemap"><button type="button" class="pick" onClick={() => o.onPick?.(40, 30)}>pick</button><svg>{o.world}{o.marks?.({ map: (x, y) => [x, y], px: (x, y) => [x * fakeK, y * fakeK], k: fakeK })}</svg></div>;
let said: string[] = [];
const page = () => { said = []; return render(<MapEditPage say={(m: string) => said.push(m)} target={{ map_id: "home", version: "3" }} Canvas={Fake} />); };
const btn = (root: Element, text: string) => Array.from(root.querySelectorAll("button")).find((b) => b.textContent?.trim() === text) as HTMLButtonElement;

describe("地图编辑器", () => {
  it("地址里拿图和版本", () => {
    expect(editTarget("#/admin/mapedit?map=home&version=3")).toEqual({ map_id: "home", version: "3" });
    expect(editTarget("#/admin/mapedit")).toBeNull();
    expect(editTarget("#/admin/mapedit?map=home&version=4&from=3")).toEqual({ map_id: "home", version: "4", from: "3" });
  });

  it("11-10:正式版本上写「保存会存成草稿,这一版不动」;草稿上有预览、对比、发布", async () => {
    const { container: c } = page();
    await waitFor(() => expect(c.querySelector(".mapedit[data-ready]")).not.toBeNull());
    expect(c.querySelector("[data-published]")!.textContent).toContain("保存会存成草稿");
    expect(c.querySelector("[data-draft]")).toBeNull();
    expect(c.querySelector(".me-save")!.textContent).toBe("保存草稿");
    cleanup();
    draftState = { draft: true, from: "2" };
    const ui = page();
    await waitFor(() => expect(ui.container.querySelector("[data-draft]")).not.toBeNull());
    expect(ui.container.querySelector("[data-draft]")!.textContent).toContain("草稿 v3（从 v2 编辑）");
    expect(ui.container.querySelector("[data-compare]")!.textContent).toBe("和 v2 对比");
  });

  it("橡皮擦一笔,另存前列出面积要确认,发出去的点和粗细对", async () => {
    const { container: c } = page();
    await waitFor(() => expect(c.querySelector('.mapedit[data-ready]')).not.toBeNull());
    fireEvent.click(c.querySelector('[data-tool="erase"]')!);                // P1-53:不默认选工具
    fireEvent.click(btn(c, "画笔"));                         // W6-11:默认方框,这里用画笔
    fireEvent.click(c.querySelector(".pick")!);
    fireEvent.click(c.querySelector(".pick")!);
    fireEvent.click(btn(c, "完成绘制"));
    expect(c.querySelector("polyline.me-op.erase")).not.toBeNull();
    expect(c.querySelector("[data-unsaved]")!.textContent).toContain("平方米");
    fireEvent.click(c.querySelector(".me-save")!);
    expect(document.querySelector(".modal")).toBeNull();
    await waitFor(() => expect(posted.find((p) => p.url.endsWith("/edit"))).toBeTruthy());
    const b = posted.find((p) => p.url.endsWith("/edit"))!.body;
    expect(b.digest).toBe("abc");
    expect(b.ops).toEqual([{ op: "erase", shape: "stroke", points: [[4, 7], [4, 7]], width_m: 0.3 }]);
    await waitFor(() => expect(posted.some((p) => p.url === "/api/admin/maps/home/4/display")).toBe(true));
    // 第 2 轮 P1-55:提示里报站点算的实际面积;跳到新版本时带上从哪版来的
    await waitFor(() => expect(said.join(" ")).toContain("已存成草稿 v4：实际擦掉 1 平方米"));
    expect(location.hash).toContain("&from=3");
  });

  it("第 9 轮 W9-13:橡皮擦 / 画障碍点第一下就画出笔刷大小的圆(以前第二下才看得到)", async () => {
    const { container: c } = page();
    await waitFor(() => expect(c.querySelector('.mapedit[data-ready]')).not.toBeNull());
    for (const tool of ["erase", "obstacle"]) {
      fireEvent.click(c.querySelector(`[data-tool="${tool}"]`)!);
      fireEvent.click(btn(c, "画笔"));
      fireEvent.click(c.querySelector(".pick")!);
      const dot = c.querySelectorAll(`circle.me-brush.${tool}`);
      expect(dot.length, tool).toBe(1);
      // 半径 = 笔刷粗细的一半(默认 0.3 m,图上一像素 0.1 m → 1.5 像素)× 屏幕缩放;第 10 轮 W10-06:至少 5 像素
      expect(Number(dot[0].getAttribute("r"))).toBeCloseTo(5);
      fireEvent.click(btn(c, "取消"));
    }
  });

  it("第 10 轮 W10-06:放大了笔刷圆跟着变大(屏幕上 = 笔刷宽 × 缩放)", async () => {
    fakeK = 10;
    try {
      const { container: c } = page();
      await waitFor(() => expect(c.querySelector('.mapedit[data-ready]')).not.toBeNull());
      fireEvent.click(c.querySelector('[data-tool="erase"]')!);
      fireEvent.click(btn(c, "画笔"));
      fireEvent.click(c.querySelector(".pick")!);
      expect(Number(c.querySelector("circle.me-brush")!.getAttribute("r"))).toBeCloseTo(15);
    } finally { fakeK = 1; }
  });

  it("W61 画笔首尾接上:预览里圈内填满(跟站点一样整块擦)", async () => {
    const seq: [number, number][] = [[10, 10], [60, 10], [60, 60], [10, 60], [11, 11]];
    let i = 0;
    const Seq = (o: OwnLayer) => <div class="fakemap"><button type="button" class="pick" onClick={() => { const [x, y] = seq[i++ % seq.length]; o.onPick?.(x, y); }}>pick</button><svg>{o.world}</svg></div>;
    const { container: c } = render(<MapEditPage say={() => {}} target={{ map_id: "home", version: "3" }} Canvas={Seq} />);
    await waitFor(() => expect(c.querySelector('.mapedit[data-ready]')).not.toBeNull());
    fireEvent.click(c.querySelector('[data-tool="erase"]')!);                // P1-53:不默认选工具
    fireEvent.click(btn(c, "画笔"));                         // W6-11:默认方框,这里用画笔
    for (let k = 0; k < seq.length; k++) fireEvent.click(c.querySelector(".pick")!);
    fireEvent.click(btn(c, "完成绘制"));
    expect(c.querySelector("polygon.me-op.loop.erase")).not.toBeNull();
    expect(c.querySelector("polyline.me-op.erase")).toBeNull();
  });

  it("方框两个对角就画完", async () => {
    const { container: c } = page();
    await waitFor(() => expect(c.querySelector('.mapedit[data-ready]')).not.toBeNull());
    fireEvent.click(c.querySelector('[data-tool="erase"]')!);                // P1-53:不默认选工具
    fireEvent.click(c.querySelector('[data-tool="obstacle"]')!);
    fireEvent.click(btn(c, "方框"));
    fireEvent.click(c.querySelector(".pick")!);
    fireEvent.click(c.querySelector(".pick")!);
    expect(c.querySelector("polygon.me-op.obstacle")).not.toBeNull();
  });

  it("第 2 轮 P1-53:方框按住拖着画 —— 拖的时候先出虚框,松手才算", async () => {
    let drag: OwnLayer["onDragRect"];
    const D = (o: OwnLayer) => { drag = o.onDragRect; return <div class="fakemap"><svg>{o.world}</svg></div>; };
    const { container: c } = render(<MapEditPage say={() => {}} target={{ map_id: "home", version: "3" }} Canvas={D} />);
    await waitFor(() => expect(c.querySelector('.mapedit[data-ready]')).not.toBeNull());
    fireEvent.click(c.querySelector('[data-tool="erase"]')!);
    fireEvent.click(btn(c, "画笔"));                         // W6-11:默认方框,这里用画笔
    expect(drag).toBeUndefined();                                           // 画笔:拖还是平移
    fireEvent.click(btn(c, "方框"));
    await waitFor(() => expect(drag).toBeDefined());
    act(() => drag!([10, 10], [50, 40], false));
    await waitFor(() => expect(c.querySelector("[data-drag-rect]")).not.toBeNull());
    expect(c.querySelector("polygon.me-op.erase")).toBeNull();
    act(() => drag!([10, 10], [50, 40], true));
    await waitFor(() => expect(c.querySelector("polygon.me-op.erase")).not.toBeNull());
    expect(c.querySelector("[data-drag-rect]")).toBeNull();
  });

  it("特殊地面:楼梯默认放慢 0.3", async () => {
    const { container: c } = page();
    await waitFor(() => expect(c.querySelector('.mapedit[data-ready]')).not.toBeNull());
    fireEvent.click(c.querySelector('[data-tool="erase"]')!);                // P1-53:不默认选工具
    fireEvent.click(btn(c, "画笔"));                         // W6-11:默认方框,这里用画笔
    fireEvent.click(c.querySelector('[data-tool="terrain"]')!);
    for (let i = 0; i < 3; i++) fireEvent.click(c.querySelector(".pick")!);
    fireEvent.click(btn(c, "完成绘制"));
    expect((c.querySelector('[data-terrain] input') as HTMLInputElement).value).toBe("0.3");
  });

  it("11-10:正式版本上只改显示也先存成草稿(ops 空),显示存到草稿上,原版不动", async () => {
    const { container: c } = page();
    await waitFor(() => expect(c.querySelector('.mapedit[data-ready]')).not.toBeNull());
    fireEvent.click(c.querySelector('[data-tool="rotate"]')!);
    fireEvent.change(c.querySelector('input[name="rotate"]')!, { target: { value: "12" } });
    fireEvent.click(c.querySelector(".me-save")!);
    await waitFor(() => expect(posted.find((p) => p.url === "/api/admin/maps/home/4/display")?.body.rotate_deg).toBe(12));
    expect(posted.find((p) => p.url.endsWith("/edit"))!.body.ops).toEqual([]);
    expect(posted.some((p) => p.url === "/api/admin/maps/home/3/display")).toBe(false);
  });

  it("外审 POC C3:草稿比来源少了禁行区,发布对话框里点名", async () => {
    draftState = { draft: true, from: "2", zones_removed: ["配电房"] } as typeof draftState;
    const { container: c } = page();
    await waitFor(() => expect(c.querySelector('.mapedit[data-ready]')).not.toBeNull());
    fireEvent.click(c.querySelector("[data-release]")!);
    expect(document.querySelector(".modal")!.textContent).toContain("少了这些禁行区、虚拟墙等：配电房");
  });

  it("11-10:草稿上只改显示:不出新版本,直接存在草稿上", async () => {
    draftState = { draft: true, from: "2" };
    const { container: c } = page();
    await waitFor(() => expect(c.querySelector('.mapedit[data-ready]')).not.toBeNull());
    fireEvent.click(c.querySelector('[data-tool="rotate"]')!);
    fireEvent.change(c.querySelector('input[name="rotate"]')!, { target: { value: "12" } });
    fireEvent.click(c.querySelector(".me-save")!);
    await waitFor(() => expect(posted.find((p) => p.url === "/api/admin/maps/home/3/display")?.body.rotate_deg).toBe(12));
    expect(posted.some((p) => p.url.endsWith("/edit"))).toBe(false);
    await waitFor(() => expect(said.join(" ")).toContain("草稿 v3 已保存"));
  });

  it("11-10:草稿预览 —— 有没存的改动时不给预览、发布;预览时收起工具、画布换成结果样式;发布要输密码,发完回地图管理", async () => {
    draftState = { draft: true, from: "2" };
    const { container: c } = page();
    await waitFor(() => expect(c.querySelector('.mapedit[data-ready]')).not.toBeNull());
    fireEvent.click(c.querySelector('[data-tool="erase"]')!);
    fireEvent.click(btn(c, "画笔"));                         // W6-11:默认方框,这里用画笔
    fireEvent.click(c.querySelector(".pick")!);
    fireEvent.click(btn(c, "完成绘制"));
    expect((c.querySelector("[data-preview]") as HTMLButtonElement).disabled).toBe(true);
    expect((c.querySelector("[data-release]") as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(btn(c, "撤销"));
    fireEvent.click(c.querySelector("[data-preview]")!);
    expect(c.querySelector(".me-tools")).toBeNull();
    expect(c.querySelector(".me-canvas.result")).not.toBeNull();
    expect(c.querySelector("[data-preview-hint]")).not.toBeNull();
    expect(c.querySelector("[data-preview]")!.textContent).toBe("继续编辑");
    fireEvent.click(c.querySelector("[data-preview]")!);
    expect(c.querySelector(".me-tools")).not.toBeNull();
    fireEvent.click(c.querySelector("[data-release]")!);
    const m = document.querySelector(".modal")!;
    expect(m.textContent).toContain("发布后 v3 成为正式版本");
    expect(m.textContent).toContain("现在不会发给任何机器人");
    expect(m.textContent).not.toContain("少了这些禁行区");
    fireEvent.input(m.querySelector('input[type="password"]')!, { target: { value: "pw-pw-pw" } });
    fireEvent.submit(m.querySelector("form")!);
    await waitFor(() => expect(posted.find((p) => p.url === "/api/admin/maps/home/3/release")).toBeTruthy());
    expect(posted.find((p) => p.url === "/api/admin/maps/home/3/release")!.body).toEqual({ confirm_password: "pw-pw-pw" });
    await waitFor(() => expect(location.hash).toBe("#/admin/maps"));
    expect(said.join(" ")).toContain("发布到站点");
  });

  it("栅格换了说有人改过", async () => {
    editReply = 409;
    const { container: c } = page();
    await waitFor(() => expect(c.querySelector('.mapedit[data-ready]')).not.toBeNull());
    fireEvent.click(c.querySelector('[data-tool="erase"]')!);                // P1-53:不默认选工具
    fireEvent.click(btn(c, "画笔"));                         // W6-11:默认方框,这里用画笔
    fireEvent.click(c.querySelector(".pick")!);
    fireEvent.click(btn(c, "完成绘制"));
    fireEvent.click(c.querySelector(".me-save")!);
    await waitFor(() => expect(c.querySelector(".ly-conflict")!.textContent).toContain("已被修改"));
  });

  it("外审R5:换了图,旧图的草稿不带过去;三样都到了才能存", async () => {
    let resolveB!: (r: Response) => void;
    setFetch(((url: string, init?: RequestInit) => {
      if (init?.method === "POST") { posted.push({ url, body: JSON.parse(String(init.body ?? "{}")) }); return Promise.resolve(json({ version: "2" })); }
      if (url.endsWith("/preview")) return Promise.resolve(json(META));
      if (url.endsWith("/noise")) return Promise.resolve(json({ digest: url.includes("/B/") ? "digest-B" : "digest-A" }));
      if (url.includes("/B/") && url.endsWith("/display")) return new Promise<Response>((r) => { resolveB = r; });
      return Promise.resolve(json({ rotate_deg: null, basemap: null, regions: [], terrain: [] }));
    }) as typeof fetch);
    const ui = render(<MapEditPage say={() => {}} target={{ map_id: "A", version: "1" }} Canvas={Fake} />);
    await waitFor(() => expect(ui.container.querySelector(".mapedit[data-ready]")).not.toBeNull());
    fireEvent.click(ui.container.querySelector('[data-tool="erase"]')!);
    fireEvent.click(btn(ui.container, "画笔"));                         // W6-11:默认方框,这里用画笔
    fireEvent.click(ui.container.querySelector(".pick")!);
    fireEvent.click(btn(ui.container, "完成绘制"));
    expect((ui.container.querySelector(".me-save") as HTMLButtonElement).disabled).toBe(false);
    ui.rerender(<MapEditPage say={() => {}} target={{ map_id: "B", version: "1" }} Canvas={Fake} />);
    await new Promise((r) => setTimeout(r, 20));
    expect(ui.container.textContent).toContain("B:1");
    expect(ui.container.querySelector(".mapedit[data-ready]")).toBeNull();
    expect((ui.container.querySelector(".me-save") as HTMLButtonElement).disabled).toBe(true);
    expect(ui.container.querySelector(".me-op")).toBeNull();
    resolveB(json({ rotate_deg: null, basemap: null, regions: [], terrain: [] }));
    await waitFor(() => expect(ui.container.querySelector(".mapedit[data-ready]")).not.toBeNull());
    fireEvent.click(ui.container.querySelector('[data-tool="erase"]')!);
    fireEvent.click(btn(ui.container, "画笔"));                         // W6-11:默认方框,这里用画笔
    expect((ui.container.querySelector(".me-save") as HTMLButtonElement).disabled).toBe(true);   // B 上什么都没画
    expect(posted).toEqual([]);
  });

  it("外审R5:显示设置读不出来不当成空的,不能存(存了会把区域名全抹掉)", async () => {
    setFetch(((url: string, init?: RequestInit) => {
      if (init?.method === "POST") { posted.push({ url, body: {} }); return Promise.resolve(json({})); }
      if (url.endsWith("/preview")) return Promise.resolve(json(META));
      if (url.endsWith("/noise")) return Promise.resolve(json({ digest: "abc" }));
      return Promise.resolve(json({ error: "坏了" }, 500));
    }) as typeof fetch);
    const { container: c } = page();
    await waitFor(() => expect(c.querySelector(".me-loaderr")).not.toBeNull());
    expect(c.querySelector(".mapedit[data-ready]")).toBeNull();
    fireEvent.click(c.querySelector(".pick")!);
    expect(c.querySelector(".me-save")!.hasAttribute("disabled")).toBe(true);
  });

  it("外审R5:另存还没回来就换了图,回来以后不跳、不改新图", async () => {
    let finishEdit!: (r: Response) => void;
    setFetch(((url: string, init?: RequestInit) => {
      if (init?.method === "POST") {
        posted.push({ url, body: JSON.parse(String(init.body ?? "{}")) });
        if (url.endsWith("/edit")) return new Promise<Response>((r) => { finishEdit = r; });
        return Promise.resolve(json({}));
      }
      if (url.endsWith("/preview")) return Promise.resolve(json(META));
      if (url.endsWith("/noise")) return Promise.resolve(json({ digest: "abc" }));
      return Promise.resolve(json({ rotate_deg: null, basemap: null, regions: [], terrain: [] }));
    }) as typeof fetch);
    const ui = render(<MapEditPage say={() => {}} target={{ map_id: "A", version: "1" }} Canvas={Fake} />);
    await waitFor(() => expect(ui.container.querySelector(".mapedit[data-ready]")).not.toBeNull());
    fireEvent.click(ui.container.querySelector('[data-tool="erase"]')!);
    fireEvent.click(btn(ui.container, "画笔"));                         // W6-11:默认方框,这里用画笔
    fireEvent.click(ui.container.querySelector(".pick")!);
    fireEvent.click(btn(ui.container, "完成绘制"));
    fireEvent.click(ui.container.querySelector(".me-save")!);
    await waitFor(() => expect(posted.some((p) => p.url.endsWith("/A/1/edit"))).toBe(true));
    location.hash = "#/admin/mapedit?map=B&version=1";
    ui.rerender(<MapEditPage say={() => {}} target={{ map_id: "B", version: "1" }} Canvas={Fake} />);
    finishEdit(json({ version: "2" }));
    await new Promise((r) => setTimeout(r, 20));
    expect(location.hash).toBe("#/admin/mapedit?map=B&version=1");
    // 确认过的那次照样存完(A 的新版本 2 的显示设置),B 那边一个请求都没有
    await waitFor(() => expect(posted.map((p) => p.url)).toEqual(["/api/admin/maps/A/1/edit", "/api/admin/maps/A/2/display"]));
    expect(location.hash).toBe("#/admin/mapedit?map=B&version=1");
  });

  it("实测查出的用词:橡皮擦一笔写「已点 N 个点」,不写「点出各个角」", async () => {
    const { container: c } = page();
    await waitFor(() => expect(c.querySelector(".mapedit[data-ready]")).not.toBeNull());
    expect(c.textContent).toContain("先在上面选一个工具");                          // P1-53
    fireEvent.click(c.querySelector('[data-tool="erase"]')!);
    fireEvent.click(btn(c, "画笔"));                         // W6-11:默认方框,这里用画笔
    fireEvent.click(c.querySelector(".pick")!);
    expect(c.textContent).toContain("已选 1 个点");
    expect(c.textContent).not.toContain("各个角");
  });
});

describe("网页易用性第 1 轮 P1-52", () => {
  it("有图例;勾「看改完的样子」画布换成结果样式", async () => {
    const { container: c } = page();
    await waitFor(() => expect(c.querySelector('.mapedit[data-ready]')).not.toBeNull());
    expect(c.querySelector("[data-me-legend]")!.textContent).toContain("擦掉");
    expect(c.querySelector(".me-canvas.result")).toBeNull();
    fireEvent.click(c.querySelector('input[name="me-result"]')!);
    expect(c.querySelector(".me-canvas.result")).not.toBeNull();
  });
});

describe("网页易用性第 1 轮 P2-19", () => {
  it("Ctrl+Z 撤销、Ctrl+Y 重做", async () => {
    const { container: c } = page();
    await waitFor(() => expect(c.querySelector('.mapedit[data-ready]')).not.toBeNull());
    fireEvent.click(c.querySelector('[data-tool="obstacle"]')!);
    fireEvent.click(btn(c, "画笔"));                         // W6-11:默认方框,这里用画笔
    fireEvent.click(btn(c, "方框"));
    fireEvent.click(c.querySelector(".pick")!);
    fireEvent.click(c.querySelector(".pick")!);
    expect(c.querySelector("polygon.me-op.obstacle")).not.toBeNull();
    fireEvent.keyDown(window, { key: "z", ctrlKey: true });
    await waitFor(() => expect(c.querySelector("polygon.me-op.obstacle")).toBeNull());
    fireEvent.keyDown(window, { key: "y", ctrlKey: true });
    await waitFor(() => expect(c.querySelector("polygon.me-op.obstacle")).not.toBeNull());
  });
});

describe("第 3 轮 maps N2 / P1-53", () => {
  it("没注入假地图时(真 MapCanvas)重新渲染不重挂地图:拖框拖到一半不会丢", async () => {
    const { container: c } = render(<MapEditPage say={() => {}} target={{ map_id: "home", version: "3" }} />);
    await waitFor(() => expect(c.querySelector(".me-canvas .mapwrap, .me-canvas svg")).not.toBeNull());
    const before = c.querySelector(".me-canvas")!.firstElementChild;
    expect(before).not.toBeNull();
    fireEvent.click(c.querySelector('input[name="me-result"]')!);            // 随便一个会引起重新渲染的操作
    await act(async () => {});
    expect(c.querySelector(".me-canvas")!.firstElementChild).toBe(before);
  });
});

// 11-10 用户:「所有动作都要在编辑器中完成」—— 禁行区、虚拟墙、限速区、人员忽略区从「布置 → 禁行区」搬进编辑器,
// 跟橡皮擦一起撤销、一起保存;没发布过的草稿再擦,站点替换它(这里只看网页报的话)。
describe("编辑器里画禁行区(11-10)", () => {
  beforeEach(() => { draftState = { draft: true, from: "2" }; });
  const ready = async (c: Element) => waitFor(() => expect(c.querySelector(".mapedit[data-ready]")).not.toBeNull());
  function drawZone(c: Element, tool: string, n: number) {
    fireEvent.click(c.querySelector(`[data-tool="${tool}"]`)!);
    for (let i = 0; i < n; i++) fireEvent.click(c.querySelector(".pick")!);
    fireEvent.click(btn(c, "完成绘制"));
  }
  const saveAll = async (c: Element) => {
    fireEvent.click(c.querySelector(".me-save")!);
  };

  it("工具分组:改地图本身 / 机器人能去哪 / 人员检测 / 显示;没有「去布置」的链接", async () => {
    const { container: c } = page();
    await ready(c);
    expect(Array.from(c.querySelectorAll("[data-group] p")).map((p) => p.textContent)).toEqual(["改地图本身", "机器人能去哪", "人员检测", "显示"]);
    expect(c.querySelector('[data-group="meGroupMove"] [data-tool="nogo"]')!.textContent).toBe("画禁行区");
    expect(c.querySelector('a[href="#/admin/layout?tab=nogo"]')).toBeNull();
  });

  it("草稿上画禁行区:只存禁行区(不出新版本),带打开时的修订号", async () => {
    const { container: c } = page();
    await ready(c);
    drawZone(c, "nogo", 3);
    fireEvent.input(document.querySelector('.modal input[name="label"]')!, { target: { value: "高楼楼梯" } });
    fireEvent.submit(document.querySelector(".modal form")!);
    expect(c.querySelector(".me-zones")!.textContent).toContain("高楼楼梯");
    expect(c.querySelector("polygon.nogo-area")).not.toBeNull();
    expect(c.querySelector("[data-unsaved]")!.textContent).toContain("禁行区、虚拟墙等 1 处");
    await saveAll(c);
    await waitFor(() => expect(posted.find((p) => p.url === "/api/maps/home/3/zones")).toBeTruthy());
    const b = posted.find((p) => p.url === "/api/maps/home/3/zones")!.body;
    expect(b.base_revision).toBe(2);
    expect((b.zones as { label: string }[]).map((z) => z.label)).toEqual(["高楼楼梯"]);
    expect(posted.some((p) => p.url.endsWith("/edit"))).toBe(false);
  });

  it("正式版本上画禁行区:先另存成草稿(ops 空),禁行区存到草稿上(用草稿的修订号),原版不动", async () => {
    draftState = { draft: false, from: null };
    const { container: c } = page();
    await ready(c);
    drawZone(c, "nogo", 3);
    fireEvent.submit(document.querySelector(".modal form")!);
    await saveAll(c);
    await waitFor(() => expect(posted.find((p) => p.url === "/api/maps/home/4/zones")).toBeTruthy());
    expect(posted.find((p) => p.url.endsWith("/edit"))!.body.ops).toEqual([]);
    expect(posted.find((p) => p.url === "/api/maps/home/4/zones")!.body.base_revision).toBe(7);
    expect(posted.some((p) => p.url === "/api/maps/home/3/zones")).toBe(false);
    expect(location.hash).toContain("version=4&from=3");
  });

  it("草稿上又擦又画禁行区:保存一次 —— 换成新草稿,禁行区存到新草稿上(用它的修订号);说清楚替换了哪份", async () => {
    editBody = { version: "4", from: "2", erased_m2: 1, replaced: "3", draft: true };
    const { container: c } = page();
    await ready(c);
    fireEvent.click(c.querySelector('[data-tool="erase"]')!);
    fireEvent.click(btn(c, "画笔"));                         // W6-11:默认方框,这里用画笔
    fireEvent.click(c.querySelector(".pick")!);
    fireEvent.click(btn(c, "完成绘制"));
    drawZone(c, "wall", 2);
    fireEvent.submit(document.querySelector(".modal form")!);
    await saveAll(c);
    await waitFor(() => expect(posted.find((p) => p.url === "/api/maps/home/4/zones")).toBeTruthy());
    const order = posted.map((p) => p.url);
    expect(order.indexOf("/api/admin/maps/home/3/edit")).toBeLessThan(order.indexOf("/api/maps/home/4/zones"));
    const b = posted.find((p) => p.url === "/api/maps/home/4/zones")!.body;
    expect(b.base_revision).toBe(7);
    expect((b.zones as { kind: string; wall?: unknown }[])[0]).toMatchObject({ kind: "nogo", wall: [[4, 7], [4, 7]] });
    await waitFor(() => expect(said.join(" ")).toContain("替换了草稿 v3"));
    expect(location.hash).toContain("version=4&from=2");
  });

  it("临时的带天数;人员忽略区没有硬禁区那一项", async () => {
    const { container: c } = page();
    await ready(c);
    drawZone(c, "nogo", 3);
    fireEvent.click(document.querySelector('.modal input[name="temp"]')!);
    fireEvent.change(document.querySelector('.modal select[name="days"]')!, { target: { value: "3" } });
    fireEvent.submit(document.querySelector(".modal form")!);
    drawZone(c, "ignore", 3);
    expect(document.querySelector('.modal input[name="hard"]')).toBeNull();
    fireEvent.submit(document.querySelector(".modal form")!);
    await saveAll(c);
    await waitFor(() => expect(posted.find((p) => p.url === "/api/maps/home/3/zones")).toBeTruthy());
    const zs = posted.find((p) => p.url === "/api/maps/home/3/zones")!.body.zones as { kind: string; for_s?: number; hard?: boolean }[];
    expect(zs[0].for_s).toBe(3 * 86400);
    expect(zs[1].kind).toBe("ignore");
    expect(zs[1].hard).toBeUndefined();
  });

  it("撤销能撤掉刚画的禁行区", async () => {
    const { container: c } = page();
    await ready(c);
    drawZone(c, "slow", 3);
    fireEvent.submit(document.querySelector(".modal form")!);
    expect(c.querySelector(".me-zones")).not.toBeNull();
    fireEvent.click(btn(c, "撤销"));
    expect(c.querySelector(".me-zones")).toBeNull();
    expect((c.querySelector(".me-save") as HTMLButtonElement).disabled).toBe(true);
  });

  it("原有的禁行区:点图上选中、改名(重名不让)、删掉,存的时候带上", async () => {
    const big = { ...POOL, id: "n2", label: "花园", polygon: [[0, 6], [8, 6], [8, 10], [0, 10]] };
    zones = { ...zones, zones: [POOL, big] };
    const { container: c } = page();
    await ready(c);
    expect(c.querySelector('[data-pick-zone="n1"]')!.textContent).toBe("泳池");
    fireEvent.click(c.querySelector(".pick")!);                  // (4,7) 在花园里
    expect(c.querySelector('[data-pick-zone="n2"]')!.className).toContain("on");
    fireEvent.click(c.querySelector("[data-rename]")!);
    const inp = document.querySelector('.modal input[name="label"]') as HTMLInputElement;
    fireEvent.input(inp, { target: { value: "泳池" } });
    expect((document.querySelector('.modal button[type="submit"]') as HTMLButtonElement).disabled).toBe(true);
    fireEvent.input(inp, { target: { value: "后花园" } });
    fireEvent.submit(document.querySelector(".modal form")!);
    fireEvent.click(c.querySelector('[data-remove-zone="n1"]')!);
    await saveAll(c);
    await waitFor(() => expect(posted.find((p) => p.url === "/api/maps/home/3/zones")).toBeTruthy());
    const body = posted.find((x) => x.url === "/api/maps/home/3/zones")!.body as { zones: { id: string; label: string }[] };
    expect(body.zones.map((z) => [z.id, z.label])).toEqual([["n2", "后花园"]]);
  });

  it("禁行区的状态和「确认此版本」在编辑器里;有没存的改动时不给确认;草稿上不单独确认(发布时确认)", async () => {
    zones = { ...zones, zones: [POOL], confirmed: null };
    const d = page();
    await ready(d.container);
    expect(d.container.querySelector("[data-nogo-draft]")).not.toBeNull();
    expect(btn(d.container, "确认此版本")).toBeUndefined();
    cleanup();
    draftState = { draft: false, from: null };
    const { container: c } = page();
    await ready(c);
    expect(c.querySelector(".nogo-status")!.textContent).toContain("确认");
    expect(btn(c, "确认此版本")).toBeTruthy();
    drawZone(c, "nogo", 3);
    fireEvent.submit(document.querySelector(".modal form")!);
    expect(btn(c, "确认此版本")).toBeUndefined();
  });

  it("禁行区读不出来:不能存(存了会把禁行区抹掉)", async () => {
    setFetch(((url: string) => {
      if (url.endsWith("/preview")) return Promise.resolve(json(META));
      if (url.endsWith("/noise")) return Promise.resolve(json({ digest: "abc", specks: [] }));
      if (url.endsWith("/display")) return Promise.resolve(json({ rotate_deg: null, basemap: null, regions: [], terrain: [] }));
      return Promise.resolve(json({ error: "x" }, 500));
    }) as typeof fetch);
    const { container: c } = page();
    await waitFor(() => expect(c.querySelector(".me-loaderr")).not.toBeNull());
    expect(c.querySelector(".mapedit[data-ready]")).toBeNull();
  });

  // 易用性第 6 轮 W6-04:草稿上只一种说法(发布时确认);发布对话框点名这些禁行区,要勾「核过了」才能发
  it("W6-04 草稿:禁行区只说发布时一起确认,不说去点确认、只能遥控", async () => {
    draftState = { draft: true, from: "2" };
    zones = { ...zones, zones: [POOL], confirmed: null };
    const { container: c } = page();
    await ready(c);
    const st = c.querySelector(".nogo-status")!.textContent!;
    expect(st).toContain("发布");
    expect(st).not.toContain("确认此版本");
    expect(st).not.toContain("确认这一版");
    expect(st).not.toContain("只能遥控");
  });
  it("W6-04 发布对话框:列出要一起确认的禁行区,勾了核过了才能发布", async () => {
    draftState = { draft: true, from: "2" };
    zones = { ...zones, zones: [POOL], confirmed: null };
    const { container: c } = page();
    await ready(c);
    fireEvent.click(c.querySelector("[data-release]")!);
    const m = document.querySelector(".modal")!;
    expect(m.textContent).toContain("泳池");
    fireEvent.input(m.querySelector('input[type="password"]')!, { target: { value: "pw-pw-pw" } });
    const go = m.querySelector('button[type="submit"]') as HTMLButtonElement;
    expect(go.disabled).toBe(true);
    fireEvent.click(m.querySelector('input[type="checkbox"]')!);
    expect(go.disabled).toBe(false);
  });
});

// 网页第 5 轮遗留 minor #28:发布对话框单复数(「These 1 areas」);虚拟墙也叫成 no-go zones
describe("minor #28 发布对话框说法", () => {
  it("英文一个区域用单数;文字说禁行区、虚拟墙等", async () => {
    const { t, lang } = await import("./i18n");
    lang.value = "en";
    expect(t("meReleaseZones1")).toBe("This area is confirmed and starts to apply once robots use this version:");
    expect(t("meReleaseZones", { n: 2 })).toContain("These 2 areas");
    expect(t("meReleaseText", { v: "3", from: "2" })).toContain("no-go zones, virtual walls and slow zones");
    lang.value = "zh";
    expect(t("meReleaseZones1")).toBe("下面这个区域会确认，机器人用上这一版后就按它走：");
  });
  it("只有一个区域时对话框用单数那句", async () => {
    draftState = { draft: true, from: "2" };
    zones = { ...zones, zones: [POOL], confirmed: null };
    const { container: c } = page();
    await waitFor(() => expect(c.querySelector("[data-release]")).not.toBeNull());
    fireEvent.click(c.querySelector("[data-release]")!);
    const m = document.querySelector(".modal")!;
    expect(m.textContent).toContain("下面这个区域会确认");
    expect(m.textContent).not.toContain("这 1 个区域");
  });
});

// 易用性第 6 轮 W6-11:默认画笔点几下没反应、「画完」在屏幕外;常驻的绿色「已生效」看不懂指什么;页首说明 4 行
describe("W6-11 编辑器好上手", () => {
  it("选了改地图的工具默认是方框", async () => {
    const { container: c } = page();
    await waitFor(() => expect(c.querySelector(".mapedit[data-ready]")).not.toBeNull());
    fireEvent.click(c.querySelector('[data-tool="obstacle"]')!);
    expect(c.querySelector(".seg button[aria-pressed=true]")!.textContent).toBe("方框");
  });
  it("画笔画着的时候,「完成绘制 / 撤一点 / 取消」浮在地图上", async () => {
    const { container: c } = page();
    await waitFor(() => expect(c.querySelector(".mapedit[data-ready]")).not.toBeNull());
    fireEvent.click(c.querySelector('[data-tool="erase"]')!);
    fireEvent.click(btn(c, "画笔"));
    fireEvent.click(c.querySelector(".pick")!);
    const float = c.querySelector(".me-canvas [data-draw-float]")!;
    expect(float).not.toBeNull();
    expect(btn(float, "完成绘制")).toBeTruthy();
    expect(btn(float, "取消")).toBeTruthy();
    expect(btn(c.querySelector(".ly-side")!, "完成绘制")).toBeUndefined();
    fireEvent.click(btn(float, "取消"));
    expect(c.querySelector("[data-draw-float]")).toBeNull();
  });
  it("绿色「已生效」只在禁行区工具里出;预览时不写「先选工具」;页首说明一行,详细的收在「怎么用」", async () => {
    const { container: c } = page();
    await waitFor(() => expect(c.querySelector(".mapedit[data-ready]")).not.toBeNull());
    await waitFor(() => expect(c.querySelector(".nogo-status")).not.toBeNull());
    expect(c.querySelector(".nogo-status")!.textContent).not.toContain("已生效");
    fireEvent.click(c.querySelector('[data-tool="nogo"]')!);
    expect(c.querySelector(".nogo-status")!.textContent).toContain("已生效");
    const howto = c.querySelector("details[data-me-howto]")!;
    expect(howto.querySelector("summary")!.textContent).toBe("怎么用");
    expect(howto.textContent).toContain("定位用的三维地图不变");
    cleanup();
    draftState = { draft: true, from: "2" };
    const ui = page();
    await waitFor(() => expect(ui.container.querySelector("[data-preview]")).not.toBeNull());
    fireEvent.click(ui.container.querySelector("[data-preview]")!);
    expect(ui.container.textContent).not.toContain("先在上面选一个工具");
  });
});
