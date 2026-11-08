// @vitest-environment happy-dom
// 第 3 轮 setup N5:摄像头名字的规则写在框下面,填中文变红(不靠浏览器自带气泡)。
import { cleanup, fireEvent, render } from "@testing-library/preact";
import { afterEach, describe, expect, it } from "vitest";
import { CameraForm } from "./camadmin";
import { lang } from "./i18n";

afterEach(() => { cleanup(); lang.value = "zh"; });

describe("摄像头名字规则", () => {
  it("规则写在框下面;填中文变红", () => {
    lang.value = "zh";
    render(<CameraForm initial={null} onClose={() => {}} onSaved={() => {}} say={() => {}} />);
    const rule = document.querySelector("[data-name-rule]")!;
    expect(rule.textContent).toContain("不能有空格、中文");
    expect(rule.className).not.toContain("bad");
    const inp = document.querySelector(".camform input") as HTMLInputElement;
    fireEvent.input(inp, { target: { value: "大门" } });
    expect(document.querySelector("[data-name-rule]")!.className).toContain("bad");
    fireEvent.input(inp, { target: { value: "gate-1" } });
    expect(document.querySelector("[data-name-rule]")!.className).not.toContain("bad");
  });
});
