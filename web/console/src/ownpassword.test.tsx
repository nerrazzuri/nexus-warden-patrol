// @vitest-environment happy-dom
// 网页易用性第 1 轮 P1-67:改自己的密码 —— 规则写出来、当场查,新旧一样不改,先确认,改完回登录页写清楚。
import { cleanup, fireEvent, render, waitFor } from "@testing-library/preact";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { setFetch } from "./api";
import { lang } from "./i18n";
import { TopBar } from "./shell";

let posts: { url: string; body: unknown }[] = [];
beforeEach(() => {
  lang.value = "zh";
  posts = [];
  setFetch(((url: string, init?: RequestInit) => {
    posts.push({ url, body: JSON.parse(String(init?.body ?? "{}")) });
    return Promise.resolve(new Response("{}", { status: 200, headers: { "Content-Type": "application/json" } }));
  }) as typeof fetch);
});
afterEach(() => cleanup());

const me = { name: "gina", display_name: "Gina", role: "guard", site_name: "s" } as never;
const btn = (root: ParentNode, text: string) => Array.from(root.querySelectorAll("button")).find((b) => b.textContent?.includes(text)) as HTMLButtonElement;

it("太短、新旧一样都当场说;确认后改,改完带说明退出", async () => {
  const out = vi.fn();
  const { container: c } = render(<TopBar me={me} page="duty" mode={null} alarms={0} now={0} pref="auto" onPref={() => {}}
    onStop={() => {}} onSignOut={out} onSay={() => {}} />);
  fireEvent.click(c.querySelector(".usermenu > .who")!);
  fireEvent.click(btn(c, "修改密码"));
  const form = c.ownerDocument.querySelector(".modal form")!;
  expect(form.textContent).toContain("至少 10 个字符");
  const [oldI, newI] = Array.from(form.querySelectorAll("input"));
  fireEvent.input(oldI, { target: { value: "old-password-1" } });
  fireEvent.input(newI, { target: { value: "short" } });
  fireEvent.submit(form);
  expect(form.querySelector(".error")!.textContent).toContain("至少 10 个字符");
  fireEvent.input(newI, { target: { value: "old-password-1" } });
  fireEvent.submit(form);
  expect(form.querySelector(".error")!.textContent).toContain("一样");
  expect(posts).toEqual([]);
  fireEvent.input(newI, { target: { value: "new-password-22" } });
  fireEvent.submit(form);
  const confirm = Array.from(c.ownerDocument.querySelectorAll(".modal")).pop()!;
  expect(confirm.textContent).toContain("重新登录");
  fireEvent.click(btn(confirm, "保存"));
  await waitFor(() => expect(out).toHaveBeenCalledWith("密码已修改，请用新密码登录。"));
  expect(posts).toEqual([{ url: "/api/me/password", body: { old: "old-password-1", new: "new-password-22" } }]);
});
