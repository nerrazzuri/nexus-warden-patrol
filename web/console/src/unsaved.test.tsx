// @vitest-environment happy-dom
// 网页易用性第 1 轮 P0-12:页面报自己有没存的改动,路由换页前查。
import { cleanup, render } from "@testing-library/preact";
import { afterEach, expect, it } from "vitest";
import { anyUnsaved, dropUnsaved, useUnsaved } from "./unsaved";

afterEach(() => { cleanup(); dropUnsaved(); });

function Page({ d }: { d: boolean }) {
  useUnsaved("p", d);
  return <div />;
}

it("脏了算、存了 / 卸掉不算", () => {
  const r = render(<Page d={false} />);
  expect(anyUnsaved()).toBe(false);
  r.rerender(<Page d />);
  expect(anyUnsaved()).toBe(true);
  r.rerender(<Page d={false} />);
  expect(anyUnsaved()).toBe(false);
  r.rerender(<Page d />);
  r.unmount();
  expect(anyUnsaved()).toBe(false);
});

it("脏的时候关标签页浏览器会问", () => {
  render(<Page d />);
  const e = new Event("beforeunload", { cancelable: true });
  window.dispatchEvent(e);
  expect(e.defaultPrevented).toBe(true);
});
