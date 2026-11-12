// 第 8 轮 W8-04:机器人卡片上状态后面那一小段 —— 不重复「巡逻中」;几圈的巡逻写第几圈
import { beforeEach, describe, expect, it } from "vitest";
import { lang } from "./i18n";
import { taskNote } from "./live";
import type { Robot } from "./model";

const r = (o: Partial<Robot> & Record<string, unknown> = {}) => ({ robot_id: "B", active: true, fresh: true, revoked: false, held: null, ...o }) as Robot;

describe("taskNote", () => {
  beforeEach(() => { lang.value = "zh"; });
  it("巡逻:没有圈数就不写(状态已经写了巡逻中),有圈数写第几圈", () => {
    expect(taskNote(r(), "patrol", "patrolling")).toBe("");
    expect(taskNote(r({ lap: { n: 2, of: 3 } }), "patrol", "patrolling")).toBe("第 2 / 3 圈");
    expect(taskNote(r({ lap: { n: 6, of: 0 } }), "patrol", "patrolling")).toBe("一直巡逻 · 第 6 圈");
  });
  it("跟状态说的不一样才写", () => {
    expect(taskNote(r(), "standby", "returning")).toBe("");
    expect(taskNote(r(), "goto", "idle")).toBe("巡逻中");
    expect(taskNote(r(), "", "idle")).toBe("");
  });
});
