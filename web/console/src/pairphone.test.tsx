// @vitest-environment happy-dom
// 网页易用性第 1 轮 P1-76:配对地址当场查、配对码能复制。
import { cleanup, fireEvent, render, waitFor } from "@testing-library/preact";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { PairPhone } from "./admin";
import { setFetch } from "./api";
import { lang } from "./i18n";

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

beforeEach(() => {
  lang.value = "zh";
  setFetch(((url: string) => {
    if (url === "/api/pairing/addresses") return Promise.resolve(json({ addresses: ["192.168.1.5"] }));
    if (url.startsWith("/api/pairing?")) return Promise.resolve(json({ name: "site", fingerprint: "ab:cd", code: "NWX-CODE-1" }));
    return Promise.resolve(json({}, 404));
  }) as typeof fetch);
});
afterEach(cleanup);

describe("P1-76 配对", () => {
  it("乱填的地址:当场说、更新灰着", async () => {
    const { container: c } = render(<PairPhone />);
    const input = c.querySelector('input[type="url"]') as HTMLInputElement;
    fireEvent.input(input, { target: { value: "abc" } });
    const update = Array.from(c.querySelectorAll("button")).find((b) => b.textContent === "更新二维码" || b.type === "submit") as HTMLButtonElement;
    expect(update.disabled).toBe(true);
    expect(c.querySelector("p.error")).not.toBeNull();
    fireEvent.input(input, { target: { value: "https://192.168.1.5:8443" } });
    expect(update.disabled).toBe(false);
  });

  it("配对码有复制按钮", async () => {
    const write = vi.fn(() => Promise.resolve());
    Object.defineProperty(navigator, "clipboard", { value: { writeText: write }, configurable: true });
    const { container: c } = render(<PairPhone />);
    const input = c.querySelector('input[type="url"]') as HTMLInputElement;
    fireEvent.input(input, { target: { value: "https://192.168.1.5:8443" } });
    fireEvent.submit(c.querySelector("form")!);
    await waitFor(() => expect(c.querySelector("[data-pair-code]")).not.toBeNull());
    fireEvent.click(Array.from(c.querySelectorAll("button")).find((b) => b.textContent === "复制")!);
    await waitFor(() => expect(write).toHaveBeenCalledWith("NWX-CODE-1"));
  });
});
