// 第四档 #32(UIUX-015):叠在一起的路线点散开摆。
import { describe, expect, it } from "vitest";
import { spreadMarks } from "./markspread";

const R = 11;
const dist = (a: { x: number; y: number }, b: { x: number; y: number }) => Math.hypot(a.x - b.x, a.y - b.y);

describe("叠在一起的标记散开", () => {
  it("离得远的不动", () => {
    const s = spreadMarks([{ x: 0, y: 0 }, { x: 100, y: 0 }], R);
    expect(s.map((p) => p.moved)).toEqual([false, false]);
    expect(s[1]).toMatchObject({ x: 100, y: 0 });
  });

  it("三个点挤在一处(验收:相距不到一个标记直径也分得清):散开后两两不叠,各自记着真实位置", () => {
    const pts = [{ x: 50, y: 50 }, { x: 54, y: 51 }, { x: 52, y: 56 }];
    const s = spreadMarks(pts, R);
    for (let i = 0; i < 3; i++) for (let j = i + 1; j < 3; j++) expect(dist(s[i], s[j])).toBeGreaterThanOrEqual(2 * R);
    expect(s.every((p) => p.moved)).toBe(true);
    expect(s.map((p) => [p.x0, p.y0])).toEqual(pts.map((p) => [p.x, p.y]));
  });

  it("选中的那个不挪(要拖它),别的绕开它也不叠它", () => {
    const pts = [{ x: 50, y: 50 }, { x: 53, y: 50 }, { x: 56, y: 50 }, { x: 59, y: 50 }];
    const s = spreadMarks(pts, R, 1);
    expect(s[1]).toMatchObject({ x: 53, y: 50, moved: false });
    for (let i = 0; i < 4; i++) for (let j = i + 1; j < 4; j++) expect(dist(s[i], s[j])).toBeGreaterThanOrEqual(2 * R);
  });

  it("一串连着叠的算一组;别处单独的点照旧", () => {
    const pts = [{ x: 0, y: 0 }, { x: 15, y: 0 }, { x: 30, y: 0 }, { x: 300, y: 300 }];
    const s = spreadMarks(pts, R);
    expect(s.slice(0, 3).every((p) => p.moved)).toBe(true);
    expect(s[3]).toMatchObject({ x: 300, y: 300, moved: false });
  });

  it("十个点叠在一处也两两不叠", () => {
    const pts = Array.from({ length: 10 }, (_, i) => ({ x: 100 + i * 0.5, y: 100 }));
    const s = spreadMarks(pts, R);
    for (let i = 0; i < 10; i++) for (let j = i + 1; j < 10; j++) expect(dist(s[i], s[j])).toBeGreaterThanOrEqual(2 * R);
  });
});
