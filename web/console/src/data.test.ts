// 第 2 轮 P1-49:下拉框里的长备注截短
import { describe, expect, it } from "vitest";
import { clip } from "./data";

describe("clip", () => {
  it("短的原样,长的截到 n 个字带省略号", () => {
    expect(clip("short")).toBe("short");
    const s = clip("x".repeat(200));
    expect(s.length).toBe(40);
    expect(s.endsWith("…")).toBe(true);
  });
});
