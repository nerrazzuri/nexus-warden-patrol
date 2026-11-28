// @vitest-environment happy-dom
// 1.1-4 远程喊话:按住说话 → 松开把录音传上去;点一下就松开的不发;听回话;最近的对讲能回放;录不了音说清楚为什么。
import { cleanup, fireEvent, render, waitFor } from "@testing-library/preact";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { setFetch } from "./api";
import { lang } from "./i18n";
import { TalkPanel } from "./talkpanel";

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
let calls: { url: string; init?: RequestInit }[];
let talks: Record<string, unknown>[];

class 假录音 {
  static last: 假录音 | null = null;
  state = "inactive";
  mimeType = "audio/webm;codecs=opus";
  ondataavailable: ((e: { data: Blob }) => void) | null = null;
  onstop: (() => void) | null = null;
  constructor() { 假录音.last = this; }
  start() { this.state = "recording"; }
  stop() {
    this.state = "inactive";
    this.ondataavailable?.({ data: new Blob(["opus-bytes"], { type: "audio/webm" }) });
    this.onstop?.();
  }
}

beforeEach(() => {
  lang.value = "en";
  calls = [];
  talks = [{ id: "0123456789abcdef", direction: "in", account: "gina", created_ms: 1, state: "recorded", bytes: 3200 }];
  vi.stubGlobal("MediaRecorder", 假录音);
  Object.defineProperty(navigator, "mediaDevices", {
    configurable: true,
    value: { getUserMedia: vi.fn(() => Promise.resolve({ getTracks: () => [{ stop() {} }] })) },
  });
  setFetch(((url: string, init?: RequestInit) => {
    calls.push({ url, init });
    if (url.endsWith("/talks")) return Promise.resolve(json({ talks }));
    if (url.endsWith("/talk") || url.endsWith("/listen")) return Promise.resolve(json({ ack: { result: "accepted" }, talk: { id: "fedcba9876543210" } }));
    return Promise.resolve(json({}, 404));
  }) as typeof fetch);
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.useRealTimers(); });

const hold = (c: Element) => c.querySelector<HTMLButtonElement>("[data-talk-hold]")!;

describe("远程喊话", () => {
  it("按住说话、松开:录音原样传上去,格式写在头里;回放用站点的地址", async () => {
    let said = "";
    const { container: c } = render(<TalkPanel robot="A" name="Robot A" listen={true} disabled={false} say={(s) => { said = s; }} />);
    await waitFor(() => expect(c.querySelector('[data-talk-row="0123456789abcdef"] audio')).not.toBeNull());
    expect(c.querySelector("audio")!.getAttribute("src")).toBe("/api/talk/0123456789abcdef");
    const t0 = Date.now();
    const now = vi.spyOn(Date, "now");
    now.mockReturnValue(t0);
    fireEvent.pointerDown(hold(c));
    await waitFor(() => expect(hold(c).getAttribute("aria-pressed")).toBe("true"));
    now.mockReturnValue(t0 + 2500);
    fireEvent.pointerUp(hold(c));
    await waitFor(() => expect(calls.some((x) => x.url === "/api/robots/A/talk")).toBe(true));
    const up = calls.find((x) => x.url === "/api/robots/A/talk")!;
    expect((up.init!.headers as Record<string, string>)["Content-Type"]).toBe("audio/webm");
    expect(up.init!.body).toBeInstanceOf(Blob);
    await waitFor(() => expect(said).toBe("Robot A: your message is playing."));
    now.mockRestore();
  });

  it("点一下就松开的不发", async () => {
    let said = "";
    const { container: c } = render(<TalkPanel robot="A" name="Robot A" listen={false} disabled={false} say={(s) => { said = s; }} />);
    fireEvent.pointerDown(hold(c));
    await waitFor(() => expect(hold(c).getAttribute("aria-pressed")).toBe("true"));
    fireEvent.pointerUp(hold(c));
    await waitFor(() => expect(said).toContain("Too short"));
    expect(calls.some((x) => x.url === "/api/robots/A/talk")).toBe(false);
    expect(c.querySelector("[data-talk-listen]")).toBeNull();
  });

  it("听回话:请机器人录 10 秒", async () => {
    const { container: c } = render(<TalkPanel robot="A" name="Robot A" listen={true} disabled={false} say={() => {}} />);
    fireEvent.click(c.querySelector("[data-talk-listen]")!);
    await waitFor(() => expect(calls.some((x) => x.url === "/api/robots/A/listen")).toBe(true));
    expect(JSON.parse(String(calls.find((x) => x.url === "/api/robots/A/listen")!.init!.body))).toEqual({ seconds: 10 });
  });

  it("浏览器录不了音:按钮灰着,说要 HTTPS", async () => {
    vi.stubGlobal("MediaRecorder", undefined);
    const { container: c } = render(<TalkPanel robot="A" name="Robot A" listen={true} disabled={false} say={() => {}} />);
    expect(hold(c).disabled).toBe(true);
    expect(c.textContent).toContain("HTTPS");
  });
  it("外审 1.1 #12:等麦克风权限的时候松了手 —— 不录、不发,麦克风关掉", async () => {
    let grant: (v: unknown) => void = () => {};
    let stopped = 0;
    (navigator.mediaDevices.getUserMedia as ReturnType<typeof vi.fn>).mockImplementation(
      () => new Promise((r) => { grant = r; }));
    假录音.last = null;
    const { container: c } = render(<TalkPanel robot="A" name="Robot A" listen={true} disabled={false} say={() => {}} />);
    await waitFor(() => expect(hold(c)).not.toBeNull());
    fireEvent.pointerDown(hold(c));
    fireEvent.pointerUp(hold(c));
    grant({ getTracks: () => [{ stop() { stopped++; } }] });
    await new Promise((r) => setTimeout(r, 20));
    expect(假录音.last).toBeNull();
    expect(stopped).toBe(1);
    expect(hold(c).getAttribute("aria-pressed")).toBe("false");
    expect(calls.some((x) => x.url.endsWith("/talk"))).toBe(false);
  });

  it("外审 1.1 #11:回话没录到写原因", async () => {
    talks = [{ id: "1111222233334444", direction: "in", account: "gina", created_ms: Date.now(), state: "failed", error: "麦克风忙", bytes: 0 }];
    const { container: c } = render(<TalkPanel robot="A" name="Robot A" listen={true} disabled={false} say={() => {}} />);
    await waitFor(() => expect(c.querySelector('[data-talk-row="1111222233334444"]')).not.toBeNull());
    expect(c.querySelector('[data-talk-row="1111222233334444"]')!.textContent).toContain("No reply recorded: 麦克风忙");
    expect(c.querySelector<HTMLButtonElement>("[data-talk-listen]")!.disabled).toBe(false);
  });

  it("外审 1.1 第 5 轮 #4:等权限的时候切了机器人 —— 授权以后不录,不发给原来那台", async () => {
    let grant: (v: unknown) => void = () => {};
    let stopped = 0;
    (navigator.mediaDevices.getUserMedia as ReturnType<typeof vi.fn>).mockImplementation(
      () => new Promise((r) => { grant = r; }));
    假录音.last = null;
    const { container: c, rerender } = render(<TalkPanel robot="A" name="Robot A" listen={true} disabled={false} say={() => {}} />);
    fireEvent.pointerDown(hold(c));
    rerender(<TalkPanel robot="B" name="Robot B" listen={true} disabled={false} say={() => {}} />);
    grant({ getTracks: () => [{ stop() { stopped++; } }] });
    await new Promise((r) => setTimeout(r, 20));
    expect(假录音.last).toBeNull();
    expect(stopped).toBe(1);
    expect(calls.some((x) => x.url.endsWith("/talk"))).toBe(false);
  });

  it("外审 1.1 第 5 轮 #4:录到一半切了机器人、关了面板 —— 这段丢掉,哪台都不发", async () => {
    const t0 = Date.now();
    const now = vi.spyOn(Date, "now");
    now.mockReturnValue(t0);
    const { container: c, rerender, unmount } = render(<TalkPanel robot="A" name="Robot A" listen={true} disabled={false} say={() => {}} />);
    fireEvent.pointerDown(hold(c));
    await waitFor(() => expect(hold(c).getAttribute("aria-pressed")).toBe("true"));
    now.mockReturnValue(t0 + 2500);
    rerender(<TalkPanel robot="B" name="Robot B" listen={true} disabled={false} say={() => {}} />);
    await waitFor(() => expect(hold(c).getAttribute("aria-pressed")).toBe("false"));
    fireEvent.pointerUp(hold(c));
    await new Promise((r) => setTimeout(r, 20));
    expect(calls.some((x) => x.url.endsWith("/talk"))).toBe(false);
    // 在 B 上重新按住说话、录到一半关掉面板
    now.mockReturnValue(t0 + 5000);
    fireEvent.pointerDown(hold(c));
    await waitFor(() => expect(hold(c).getAttribute("aria-pressed")).toBe("true"));
    now.mockReturnValue(t0 + 8000);
    unmount();
    await new Promise((r) => setTimeout(r, 20));
    expect(calls.some((x) => x.url.endsWith("/talk"))).toBe(false);
    now.mockRestore();
  });
});
