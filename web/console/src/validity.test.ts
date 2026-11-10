// @vitest-environment happy-dom
// 网页易用性第 1 轮 P2-30
import { describe, expect, it } from "vitest";
import { lang } from "./i18n";
import { validityText } from "./validity";

const v = (o: Partial<ValidityState>) => ({ valueMissing: false, typeMismatch: false, patternMismatch: false, badInput: false,
  rangeUnderflow: false, rangeOverflow: false, stepMismatch: false, tooLong: false, tooShort: false, ...o }) as ValidityState;

describe("表单提示跟页面语言", () => {
  it("空着:中文说「请填写这一项」,英文说 Please fill this in", () => {
    lang.value = "zh";
    expect(validityText(v({ valueMissing: true }))).toBe("请填写这一项。");
    lang.value = "en";
    expect(validityText(v({ valueMissing: true }))).toBe("Please fill this in.");
    expect(validityText(v({ rangeOverflow: true }))).toBe("This value is out of range.");
    lang.value = "zh";
  });
});
