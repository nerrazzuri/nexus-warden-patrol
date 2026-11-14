// 图标(redesign 11-14:ISO 7010 安全标识的几何):P1 红色粗圆环(「出事了」)、P2 黄色警告三角(深色描边)、P3 细的中性圆、
// 离线 = 禁止标志(圆环加斜杠,「没在工作」);指令 = 实心圆(放在主按钮里);正常 = 绿色方块(安全条件,样式表画在状态字前面,不进 DOM);
// 急停八边形,外加几个线条图标(Lucide 风格,ISC 许可的样子手画)。形状永远跟文字一起出现,不单独表意。
import type { JSX } from "preact";

export type ShapeKind = "P1" | "P2" | "P3" | "offline" | "mandatory";

export function Shape({ kind, size = 12 }: { kind: ShapeKind; size?: number }): JSX.Element {
  return (
    <svg class={`shape ${kind}`} width={size} height={size} viewBox="0 0 12 12" aria-hidden="true">
      {/* 圆环用挖空的路径画(evenodd):各处样式表照旧用 fill 上色 */}
      {kind === "P1" && <path fill-rule="evenodd" d="M6 .25a5.75 5.75 0 1 0 0 11.5a5.75 5.75 0 1 0 0-11.5zm0 2.9a2.85 2.85 0 1 1 0 5.7a2.85 2.85 0 1 1 0-5.7z" />}
      {kind === "P2" && <path stroke-linejoin="round" d="M6 1.1l5.2 9.4H.8z" />}
      {kind === "P3" && <circle cx="6" cy="6" r="4.5" fill="none" stroke-width="1.5" />}
      {/* 指令标志(ISO 7010 M 类的蓝圆):只放在「你要做的那一件事」的按钮上 */}
      {kind === "mandatory" && <circle cx="6" cy="6" r="5" />}
      {kind === "offline" && (
        <g fill="none" stroke-width="1.5" stroke-linecap="round">
          <circle cx="6" cy="6" r="4.5" />
          <path d="M2.8 9.2l6.4-6.4" />
        </g>
      )}
    </svg>
  );
}

const P: Record<string, string[]> = {
  // 四足机器人(侧面):身子、头、四条腿
  robot: ["M5 9h11a3 3 0 0 1 3 3v1H5z", "M19 10l2-2", "M6 13l-1 6", "M9 13l1 6", "M14 13l-1 6", "M17 13l1 6"],
  octagon: ["M7.9 2h8.2L22 7.9v8.2L16.1 22H7.9L2 16.1V7.9z"],
  x: ["M18 6L6 18", "M6 6l12 12"],
  expand: ["M15 3h6v6", "M9 21H3v-6", "M21 3l-7 7", "M3 21l7-7"],
  map: ["M9 4l-6 2v14l6-2 6 2 6-2V4l-6 2z", "M9 4v14", "M15 6v14"],
  eye: ["M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z", "M9 12a3 3 0 1 0 6 0a3 3 0 1 0-6 0"],
  eyeOff: ["M9.9 9.9a3 3 0 1 0 4.2 4.2", "M10.7 5.1A10.4 10.4 0 0 1 12 5c7 0 10 7 10 7a13.2 13.2 0 0 1-1.7 2.7",
    "M6.6 6.6A13.5 13.5 0 0 0 2 12s3 7 10 7a9.7 9.7 0 0 0 5.4-1.6", "M2 2l20 20"],
  logout: ["M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4", "M16 17l5-5-5-5", "M21 12H9"],
};

export function Icon({ name, size = 18 }: { name: keyof typeof P; size?: number }): JSX.Element {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
      stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
      {P[name].map((d) => <path key={d} d={d} />)}
    </svg>
  );
}
