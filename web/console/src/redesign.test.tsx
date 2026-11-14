// @vitest-environment happy-dom
// redesign/console-v2(2026-11-14):审计 UIUX-E004 关对话框焦点回到打开它的按钮;E027 报警详情先聚焦「我来处理」。
import { cleanup, fireEvent, render } from "@testing-library/preact";
import { useState } from "preact/hooks";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { AlertDetail } from "./alertdetail";
import { setFetch } from "./api";
import { Modal } from "./dialogs";
import { lang } from "./i18n";
import type { Alert } from "./model";

beforeEach(() => {
  lang.value = "zh";
  setFetch((() => Promise.resolve(new Response("{}", { status: 200, headers: { "Content-Type": "application/json" } }))) as typeof fetch);
});
afterEach(() => cleanup());

function Opener() {
  const [open, setOpen] = useState(false);
  return <div>
    <button type="button" onClick={() => setOpen(true)}>打开</button>
    {open && <Modal label="设置" onClose={() => setOpen(false)}><input name="x" /></Modal>}
  </div>;
}

describe("redesign 焦点", () => {
  it("E004:关掉对话框,焦点回到打开它的按钮", async () => {
    const r = render(<Opener />);
    const b = r.getByText("打开");
    b.focus();
    fireEvent.click(b);
    await new Promise((x) => setTimeout(x, 0));
    const close = r.getByLabelText("关闭") as HTMLButtonElement;
    close.focus();
    expect(document.activeElement).toBe(close);
    fireEvent.click(close);
    await new Promise((x) => setTimeout(x, 0));
    expect(document.activeElement).toBe(r.getByText("打开"));
  });

  it("E027:没人接手的报警,打开详情焦点在「我来处理」,不在备注框", async () => {
    const a = { key: "A/intrusion#1", kind: "intrusion", level: "P1", robot: "A", title: "有人闯入", detail: "", first_ms: 1, last_ms: 1, count: 1,
      acked_by: "", acked_ms: null, resolved_ms: null, context: {} } as unknown as Alert;
    render(<AlertDetail a={a} role="guard" now={0} units={[]} onClose={() => {}} refresh={async () => {}} say={() => {}} />);
    await new Promise((x) => setTimeout(x, 0));
    expect(document.activeElement?.textContent).toBe("我来处理");
  });
});

describe("redesign 列表文字", () => {
  it("E021:名字里有种类就不重复", async () => {
    const { zoneSub } = await import("./mapedit");
    expect(zoneSub("禁行区 2", "禁行区")).toBe("");
    expect(zoneSub("禁行区", "禁行区 · 硬")).toBe("硬");
    expect(zoneSub("仓库门口", "禁行区 · 硬")).toBe("禁行区 · 硬");
  });
});
