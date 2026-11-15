// 标识(ISO 7010 那套,redesign 第二轮):红圈 = P1 / 出事,黄三角 = 提醒 / P2,绿方块 = 正常,空心方块 = 待命,蓝圆 = 信息。
import { Shape } from "./icons";
import type { RobotState } from "./model";

/**
 * 画面布局(用户 11-15):大多数客户只买一台机器人,先照一台来。按登记的机器人台数只给一种:
 * 一台 = 单(前、后两路分开放);两台 = 双(每台大画面 + 右下角小画面);三台以上 = 多(跟双一样每台一格,能滚)。
 * 监控墙一直在。
 */
export type VideoLayout = "single" | "dual" | "multi" | "wall";

/** 这么多台机器人能选哪几种布局(第一个是默认)。 */
export function videoLayoutsFor(robots: number): VideoLayout[] {
  return [robots <= 1 ? "single" : robots === 2 ? "dual" : "multi", "wall"];
}

/** 存着的布局换成这个台数能用的那一种(监控墙照旧)。 */
export function fitLayout(l: VideoLayout, robots: number): VideoLayout {
  return l === "wall" ? "wall" : videoLayoutsFor(robots)[0];
}

/** 机器人状态的标识(ISO 7010 那套):正常绿方块、待命/充电空心方块、要注意黄三角、出事红圈。 */
export function stateSign(s: RobotState): "ok" | "idle" | "warn" | "bad" {
  if (s === "offline" || s === "estop" || s === "fell") return "bad";
  if (s === "patrolling" || s === "returning" || s === "deterring" || s === "manual") return "ok";
  if (s === "idle" || s === "charging") return "idle";
  return "warn";
}

export function Sign({ kind }: { kind: "ok" | "idle" | "warn" | "bad" | "info" }) {
  return kind === "bad" ? <Shape kind="P1" size={12} /> : kind === "warn" ? <Shape kind="P2" size={13} />
    : <i class={`sign ${kind}`} aria-hidden="true" />;
}

