// 第 2 轮 setup N16:英文界面列举不用中文顿号
import { afterEach, describe, expect, it } from "vitest";
import { joinList, lang } from "./i18n";

afterEach(() => { lang.value = "zh"; });

describe("joinList", () => {
  it("中文用顿号,英文用逗号", () => {
    lang.value = "zh";
    expect(joinList(["东区", "北区"])).toBe("东区、北区");
    lang.value = "en";
    expect(joinList(["East", "North"])).toBe("East, North");
  });
});
