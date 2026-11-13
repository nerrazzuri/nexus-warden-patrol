// 路线、日程的编号
import { describe, expect, it } from "vitest";
import { freeId } from "./routes";

describe("第 11 轮 W11-01:新建自动给编号跳过删掉过的", () => {
  it("用过的(在的、删掉过的)都跳过", () => {
    expect(freeId("route", [])).toBe("route-1");
    expect(freeId("route", ["route-1"], { retired_routes: ["route-2"] } as never, "route")).toBe("route-3");
    expect(freeId("evening", ["evening-1"], { retired_schedules: ["evening-2", "x-1"] } as never, "schedule")).toBe("evening-3");
  });
});
