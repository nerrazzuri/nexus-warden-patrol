// @vitest-environment happy-dom
// 网页易用性第 1 轮 P2-04/05/06:登录页
import { cleanup, fireEvent, render, waitFor } from "@testing-library/preact";
import { afterEach, describe, expect, it } from "vitest";
import { setFetch } from "./api";
import { lang } from "./i18n";
import { Login } from "./login";

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
afterEach(() => { cleanup(); lang.value = "zh"; });

describe("第 2 轮 admin N8", () => {
  it("站点说 disabled:写账号已停用,不写密码错", async () => {
    setFetch((async () => json({ error: "这个账号已停用,请找管理员", disabled: true }, 401)) as never);
    const { container: c } = render(<Login onIn={() => {}} expired={false} />);
    const [name, pw] = Array.from(c.querySelectorAll("input"));
    fireEvent.input(name, { target: { value: "r2" } });
    fireEvent.input(pw, { target: { value: "pw" } });
    fireEvent.submit(c.querySelector("form")!);
    await waitFor(() => expect(c.querySelector(".login-err")!.textContent).toMatch(/已停用|disabled/));
  });
});

describe("登录页", () => {
  it("账号首尾空格不算;错了提示跟着语言换;能显示密码", async () => {
    const sent: unknown[] = [];
    setFetch((async (_u: string, init?: RequestInit) => { sent.push(JSON.parse(String(init?.body ?? "{}"))); return json({ error: "x" }, 401); }) as never);
    lang.value = "en";
    const { container: c } = render(<Login onIn={() => {}} expired={false} />);
    const [name, pw] = Array.from(c.querySelectorAll("input"));
    expect(c.querySelector(".login-err")).not.toBeNull();          // 错误行先占着位置
    fireEvent.input(name, { target: { value: "  olga " } });
    fireEvent.input(pw, { target: { value: "pw" } });
    fireEvent.click(c.querySelector(".pw-show")!);
    expect(pw.getAttribute("type")).toBe("text");
    fireEvent.submit(c.querySelector("form")!);
    await waitFor(() => expect(c.querySelector(".login-err")!.textContent).not.toBe(""));
    expect((sent[0] as { name: string }).name).toBe("olga");
    const en = c.querySelector(".login-err")!.textContent;
    lang.value = "zh";
    await waitFor(() => expect(c.querySelector(".login-err")!.textContent).not.toBe(en));
  });
});

describe("第 2 轮 P1-04:登录页标题", () => {
  it("跟着语言变,不停在上一页的标题", async () => {
    document.title = "Alarm log · Nexus Warden";
    lang.value = "en";
    const r = render(<Login onIn={() => {}} expired={false} />);
    expect(document.title).toBe("Sign in · Nexus Warden");
    lang.value = "zh";
    await waitFor(() => expect(document.title).toBe("登录 · Nexus Warden"));
    r.unmount();
  });
});
