// UIUX-015(第四档 #32,用户 11-21):地图缩小时路线点的标记叠在一起,只看得到最上面那个序号。
// 标记是按屏上像素画的(不跟着缩放),点挨得近就会叠。这里按屏上距离找出叠在一起的几组,
// 一组里的标记绕着这一组摆成一圈,各自拉一根细线回到真实位置;选中的那个不挪(要拖它)。
// 只挪画的位置,点本身的坐标不动。

export interface Spot { x: number; y: number }
export interface Spread extends Spot {
  /** 被挪开了:画一根线回 (x0, y0)。 */
  moved: boolean;
  x0: number;
  y0: number;
}

/**
 * pts:屏上圆心;r:标记半径(屏上像素);keep:不许挪的那一个(选中的点)。
 * 两个圆心距离小于 2r + gap 算叠在一起(连着叠的算一组)。
 */
export function spreadMarks(pts: readonly Spot[], r: number, keep: number | null = null, gap = 2): Spread[] {
  const n = pts.length;
  const out: Spread[] = pts.map((p) => ({ x: p.x, y: p.y, x0: p.x, y0: p.y, moved: false }));
  if (n < 2) return out;
  const parent = pts.map((_, i) => i);
  const find = (i: number): number => (parent[i] === i ? i : (parent[i] = find(parent[i])));
  const near = 2 * r + gap;
  for (let i = 0; i < n; i++) {
    for (let j = i + 1; j < n; j++) {
      if (Math.hypot(pts[i].x - pts[j].x, pts[i].y - pts[j].y) < near) parent[find(i)] = find(j);
    }
  }
  const groups = new Map<number, number[]>();
  for (let i = 0; i < n; i++) {
    const g = find(i);
    groups.set(g, [...(groups.get(g) ?? []), i]);
  }
  for (const members of groups.values()) {
    if (members.length < 2) continue;
    const pinned = keep !== null && members.includes(keep) ? keep : null;
    const ring = members.filter((i) => i !== pinned);
    const cx = pinned !== null ? pts[pinned].x : members.reduce((s, i) => s + pts[i].x, 0) / members.length;
    const cy = pinned !== null ? pts[pinned].y : members.reduce((s, i) => s + pts[i].y, 0) / members.length;
    // 圈上相邻两个之间至少隔一个标记宽;中间钉着一个时圈要让开它
    const k = ring.length;
    const rad = Math.max(pinned !== null ? near + r : near * 0.75, (k * (near + 2)) / (2 * Math.PI));
    ring.forEach((i, j) => {
      const a = -Math.PI / 2 + (2 * Math.PI * j) / k;
      out[i] = { x: cx + Math.cos(a) * rad, y: cy + Math.sin(a) * rad, x0: pts[i].x, y0: pts[i].y, moved: true };
    });
  }
  return out;
}
