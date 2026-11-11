"""导航失败原因码和过程事件(导航 V1 第 5 节,``docs/导航V1-设计.md``)。

两类分开,同一件事不报两个互相竞争的码:

- **失败原因码**(:data:`FAIL_CODES`):任务这一段最终失败时报一个。代理写进导航后端的
  ``fail_code``、点位结果、任务结束原因;站点、手机按码显示「怎么回事 + 操作员该做什么」。
- **过程事件**(:data:`EVENTS`):过程中发生、不代表失败,可以发很多次。

中文说明、处理建议跟着码走;代理那句具体的中文原因(带位置、距离)照旧一起发,界面两样都显示。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class FailCode:
    zh: str
    en: str
    action_zh: str
    action_en: str


FAIL_CODES: dict[str, FailCode] = {
    "route_too_narrow": FailCode(
        "路线太窄,过不去",
        "Route too narrow to pass",
        "改路线,或在地图上把这段标成不可通行",
        "Change the route, or mark this passage impassable on the map",
    ),
    "goal_too_close_to_wall": FailCode(
        "目标点贴墙,站不下或转不开",
        "Goal too close to a wall to stand or turn",
        "把这个航点往空处挪一点",
        "Move the waypoint into open space",
    ),
    "goal_occupied": FailCode(
        "目标点被东西占住",
        "Goal is occupied by an object",
        "把东西挪开后再派一次",
        "Remove the object and dispatch again",
    ),
    "goal_unreachable": FailCode(
        "规划不出到目标的路线",
        "No route to the goal",
        "查地图和禁行区是不是把路堵死了",
        "Check the map and no-go zones for a blocked route",
    ),
    "dynamic_obstacle_blocked": FailCode(
        "被人、车或地图上没有的东西挡住太久",
        "Blocked too long by people, vehicles or unmapped objects",
        "去现场看是什么挡住了",
        "Check on site what is blocking",
    ),
    "robot_trapped": FailCode(
        "机器人被困:前后都被挡,或脚下被判成障碍",
        "Robot trapped: blocked front and back, or standing in an obstacle",
        "把机器人挪开一点,或遥控出来再派",
        "Move the robot a little, or drive it out by remote, then dispatch again",
    ),
    "controller_stalled": FailCode(
        "原地打转或长时间没进展,自动恢复都试过了",
        "Stalled or oscillating; automatic recovery exhausted",
        "遥控接管",
        "Take over by remote control",
    ),
    "localization_unreliable": FailCode(
        "定位不可信,不敢走",
        "Localization unreliable",
        "在「定位」页重新标一下机器人在哪儿",
        "Set the robot's position again on the Localization page",
    ),
    "sensor_lost": FailCode(
        "雷达或障碍数据断了",
        "Lidar or obstacle data lost",
        "看一下机器人头上的雷达有没有被挡住、在不在转;"
        "还不行就在「诊断」页重启这台机器人",
        "Check that the lidar on the robot's head is not covered and is spinning; "
        "if that does not help, restart the robot on the Diagnostics page",
    ),
    "robot_not_ready": FailCode(
        "机器人现在不听自动行走的命令:"
        "急停按着、有人在遥控、有故障,或还没站好",
        "Robot is not taking automatic driving commands: e-stop pressed, "
        "someone is driving it, a fault, or it is not standing yet",
        "松开急停、退出遥控、让机器人站起来,再派一次;有故障先看机器人页",
        "Release the e-stop, leave remote control, make the robot stand up, "
        "then dispatch again; for a fault, see the Robots page",
    ),
    "nav_unavailable": FailCode(
        "机器人的自动行走功能没准备好或中途停了",
        "The robot's self-driving is not ready or stopped",
        "等一两分钟再派;还不行就在「诊断」页重启这台机器人,"
        "反复出现请在 App 里提交问题单",
        "Wait a minute or two and dispatch again; if not, restart the robot on the "
        "Diagnostics page, and send a problem report from the App if it repeats",
    ),
    "nav2_plan_failed": FailCode(
        "自动行走失败,具体原因没分出来",
        "Self-driving failed for a reason the robot could not tell",
        "再派一次;同一个地方反复失败,请在 App 里提交问题单",
        "Dispatch again; if it keeps failing at the same place, send a problem report from the App",
    ),
}

#: 过程事件(不当失败码):守卫一次瞬时叫停、被挡 / 解除、恢复链走到哪一级。
EVENTS: frozenset[str] = frozenset({"guard_emergency_stop", "nav_blocked", "nav_unblocked",
                                    "recovery_step"})


def fail_code(raw: Any) -> str | None:
    """收到的码:表里有就原样返回,别的(拼错、空、不是字符串、过程事件)一律 None。"""
    return raw if isinstance(raw, str) and raw in FAIL_CODES else None
