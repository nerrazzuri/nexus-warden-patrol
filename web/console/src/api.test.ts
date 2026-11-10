// 站点接口的报错(网页易用性第 1 轮 P1-80)。
import { describe, expect, it } from "vitest";
describe("网页易用性第 1 轮 P1-80 没权限", () => {
  it("站点标了 forbidden:用界面自己的话,不带内部权限名", async () => {
    const { api, ApiError, setFetch } = await import("./api");
    const { lang } = await import("./i18n");
    lang.value = "en";
    setFetch((() => Promise.resolve(new Response(JSON.stringify({ error: "你的账号（保安）不能做这件事", reason: "forbidden", need: "set_mode" }),
      { status: 403, headers: { "Content-Type": "application/json" } }))) as typeof fetch);
    const e = (await api("POST", "/api/mode", {}).catch((x: unknown) => x)) as Error;
    expect(e).toBeInstanceOf(ApiError);
    expect(e.message).toBe("Your account is not allowed to do this. Ask an administrator.");
    expect(e.message).not.toContain("set_mode");
  });
});
