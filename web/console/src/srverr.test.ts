// 网页易用性第 1 轮 P1-01:英文界面不夹站点的中文原话
import { afterEach, describe, expect, it } from "vitest";
import { api, ApiError, setFetch } from "./api";
import { lang } from "./i18n";
import { englishError } from "./srverr";

const json = (body: unknown, status: number) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
afterEach(() => { lang.value = "zh"; });

describe("englishError", () => {
  it("常见的翻成英文;机器人回的英文原因接上;认不出的按类型说", () => {
    expect(englishError(409, "此站点未安装特权执行器(装机脚本会装):只能上主机操作")).toContain("system helper");
    expect(englishError(409, "机器人未执行:estop_active")).toBe("The robot did not do it: estop_active.");
    expect(englishError(409, "机器人未执行:急停没松")).toBe("The robot did not do it.");
    // 第 2 轮 P1-01:认不出的不接中文原话
    expect(englishError(400, "某个没见过的中文错")).toBe("The site could not accept this. Check what you entered.");
    expect(englishError(409, "estate:1 还有机器人在用(A):先切到别的版本")).toContain("(A)");
    expect(englishError(500, "内部错")).toContain("support bundle");
    expect(englishError(400, "already English")).toBe("already English");
  });
});

describe("api 的报错", () => {
  it("英文界面:中文原话翻掉,原话留在 data.error;中文界面照原话", async () => {
    setFetch((async () => json({ error: "路线 loop 已经被改过(现在是第 5 版)" }, 409)) as never);
    lang.value = "en";
    const e = await api("POST", "/x", {}).catch((x) => x) as ApiError;
    expect(e.message).toBe("Someone else changed this first. Reload the page and try again.");
    expect((e.data as { error: string }).error).toContain("已经被改过");
    lang.value = "zh";
    const z = await api("POST", "/x", {}).catch((x) => x) as ApiError;
    expect(z.message).toContain("已经被改过");
  });

  it("站点给了 reason_en 就用它", async () => {
    setFetch((async () => json({ error: "电量不够", reason_en: "battery too low" }, 409)) as never);
    lang.value = "en";
    expect((await api("POST", "/x", {}).catch((x) => x) as ApiError).message).toBe("battery too low");
  });

  it("易用性 37 第十轮 P2:名字太长 —— 英文界面说清楚上限,不再只说「站点不接受」", () => {
    expect(englishError(400, "显示名要是 0–40 个字的文字(不能有换行)")).toBe("The display name must be at most 40 characters, on one line.");
    expect(englishError(400, "显示名最多 64 个字符,不许有控制字符")).toBe("The display name must be at most 64 characters, on one line.");
    expect(englishError(400, "名字要 1–32 个字")).toBe("The name must be 1–32 characters, on one line.");
    expect(englishError(400, "名字最多 32 个字,不许有控制字符")).toBe("The name must be at most 32 characters, on one line.");
    expect(englishError(400, "区域要有名字(1–64 个字)")).toBe("The area needs a name (1–64 characters).");
    // 「个字母」那条是另一回事(只许字母数字),不能被当成长度
    expect(englishError(400, "名字要是 1–64 个字母、数字、点、下划线、减号(字母或数字开头)")).not.toMatch(/must be/);
  });
});
