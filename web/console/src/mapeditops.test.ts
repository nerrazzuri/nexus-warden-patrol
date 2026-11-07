// W44 第四期 地图编辑器的操作栈:撤销重做、面积估算、特殊地面默认放慢。
import { describe, expect, it } from "vitest";
import { apply, areaOf, closedLoop, newTerrain, redo, start, summary, undo, type GridOp } from "./mapeditops";

const D = { rotate_deg: null, basemap: null, regions: [], terrain: [] };
const erase: GridOp = { op: "erase", shape: "stroke", points: [[0, 0], [2, 0]], width_m: 0.2 };
const box: GridOp = { op: "obstacle", shape: "rect", points: [[0, 0], [1, 2]], width_m: 0.2 };

describe("操作栈", () => {
  it("撤销重做", () => {
    let h = start(D);
    h = apply(h, (s) => ({ ...s, ops: [...s.ops, erase] }));
    h = apply(h, (s) => ({ ...s, ops: [...s.ops, box] }));
    expect(h.now.ops.length).toBe(2);
    h = undo(h);
    expect(h.now.ops).toEqual([erase]);
    h = redo(h);
    expect(h.now.ops.length).toBe(2);
    h = undo(undo(h));
    expect(h.now.ops).toEqual([]);
    expect(undo(h)).toBe(h);
    h = apply(h, (s) => ({ ...s, display: { ...s.display, rotate_deg: 10 } }));
    expect(h.future).toEqual([]);
  });
  it("面积估算", () => {
    expect(areaOf(box)).toBe(2);
    expect(areaOf(erase)).toBeCloseTo(2 * 0.2 + Math.PI * 0.01, 5);
    const s = summary({ ops: [erase, box], display: D });
    expect(s).toEqual({ erased: 0.4, obstacle: 2 });
  });
  it("特殊地面:楼梯默认放慢,草地不放慢,id 不重", () => {
    const a = newTerrain([], "stairs", [[0, 0], [1, 0], [1, 1]]);
    expect(a.slow_mps).toBe(0.3);
    const b = newTerrain([a], "grass", [[0, 0], [1, 0], [1, 1]]);
    expect(b.slow_mps).toBeNull();
    expect(b.id).not.toBe(a.id);
  });
});

describe("W61 画笔首尾接上就是圈(跟站点 map_edit.closed_loop 同一条规矩)", () => {
  const loop: GridOp = { op: "erase", shape: "stroke", width_m: 0.1, points: [[1, 1], [2.6, 1], [2.6, 2.6], [1, 2.6], [1.1, 1.05]] };
  it("至少 3 个点、终点离起点 ≤ max(0.5 m, 3 倍粗细)", () => {
    expect(closedLoop(loop)).toBe(true);
    expect(closedLoop({ ...loop, points: loop.points.slice(0, -1) })).toBe(false);
    expect(closedLoop({ ...loop, points: [[0, 0], [0.2, 0]] })).toBe(false);
    expect(closedLoop({ ...loop, shape: "line", points: [[0, 0], [0, 0.1]] })).toBe(false);
    expect(closedLoop({ ...loop, width_m: 1, points: [[0, 0], [5, 0], [5, 5], [2, 2.5]] })).toBe(false);
  });
  it("估面积按圈里面算(不是笔划长 × 粗细)", () => {
    expect(areaOf(loop)).toBeGreaterThan(2.4);
    expect(areaOf(loop)).toBeLessThan(3.2);
  });
});

describe("网页易用性第 1 轮 P2-19 摆正后的方框", () => {
  it("转了 -4° 显示:屏幕上看是正的方框(四条边跟屏幕横竖平行),首尾相接", async () => {
    const { screenRect } = await import("./mapeditops");
    const { worldMatrix, applyMat } = await import("./mapview");
    const meta = { width: 100, height: 100, m_per_px: 0.1, left_x: 0, top_y: 10, rotation_deg: -4 } as never;
    const M = worldMatrix(meta, { k: 1, cx: 50, cy: 50 } as never);
    const scr = ([x, y]: [number, number]) => applyMat(M, (x - 0) / 0.1, (10 - y) / 0.1);
    const pts = screenRect([2, 3], [6, 7], -4);
    expect(pts.length).toBe(5);
    expect(pts[4]).toEqual(pts[0]);
    const s = pts.map((p) => scr(p as [number, number]));
    expect(Math.abs(s[0][1] - s[1][1])).toBeLessThan(0.05);    // 上边水平
    expect(Math.abs(s[1][0] - s[2][0])).toBeLessThan(0.05);    // 右边竖直
    expect(Math.abs(s[2][1] - s[3][1])).toBeLessThan(0.05);
    expect(Math.abs(s[3][0] - s[0][0])).toBeLessThan(0.05);
    expect(screenRect([2, 3], [6, 7], 0).slice(0, 4)).toEqual([[2, 3], [6, 3], [6, 7], [2, 7]]);
  });
});
