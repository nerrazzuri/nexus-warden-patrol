// 第 9 轮 W9-10:中文界面的句子统一用全角「，：；（）」—— 挨着汉字的半角标点不许再进来。
import { describe, expect, it } from "vitest";
import { DICTS } from "./i18n";
import { RDICTS } from "./routes_i18n";

const H = "[\\u3400-\\u9fff「」（）]";
const BAD = new RegExp(`(${H}) ?[(,:;]|[,:;)] ?(?=${H})|${H}\\)`);
/** 故意用半角的:时间格式占位、网址。 */
const OK = new Set(["recTimePh", "pairBadUrl"]);

describe("中文标点", () => {
  it("中文词表里挨着汉字的都是全角", () => {
    const bad = [...Object.entries(DICTS.zh), ...Object.entries(RDICTS.zh)]
      .filter(([k, v]) => !OK.has(k) && typeof v === "string" && BAD.test(v))
      .map(([k, v]) => `${k}: ${v}`);
    expect(bad).toEqual([]);
  });
});
