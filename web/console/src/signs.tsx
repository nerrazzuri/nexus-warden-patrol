// 标识(ISO 7010 那套,redesign 第二轮):红圈 = P1 / 出事,黄三角 = 提醒 / P2,绿方块 = 正常,空心方块 = 待命,蓝圆 = 信息。
import { Shape } from "./icons";
import type { RobotState } from "./model";

export type VideoLayout = "single" | "dual" | "quad" | "wall";

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

