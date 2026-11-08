// 生成的文件,别手改:改 nexwar_contract.navcodes,再跑 python3 tools/gen_mobile_design.py。

/** 导航失败原因码:[英文, 中文, 英文处理建议, 中文处理建议]。 */
export const NAV_FAIL_CODES: Record<string, readonly [string, string, string, string]> = {
  "route_too_narrow": ["Route too narrow to pass", "路线太窄,过不去", "Change the route, or mark this passage impassable on the map", "改路线,或在地图上把这段标成不可通行"],
  "goal_too_close_to_wall": ["Goal too close to a wall to stand or turn", "目标点贴墙,站不下或转不开", "Move the waypoint into open space", "把这个航点往空处挪一点"],
  "goal_occupied": ["Goal is occupied by an object", "目标点被东西占住", "Remove the object and dispatch again", "把东西挪开后再派一次"],
  "goal_unreachable": ["No route to the goal", "规划不出到目标的路线", "Check the map and no-go zones for a blocked route", "查地图和禁行区是不是把路堵死了"],
  "dynamic_obstacle_blocked": ["Blocked too long by people, vehicles or unmapped objects", "被人、车或地图上没有的东西挡住太久", "Check on site what is blocking", "去现场看是什么挡住了"],
  "robot_trapped": ["Robot trapped: blocked front and back, or standing in an obstacle", "机器人被困:前后都被挡,或脚下被判成障碍", "Move the robot a little, or drive it out by remote, then dispatch again", "把机器人挪开一点,或遥控出来再派"],
  "controller_stalled": ["Stalled or oscillating; automatic recovery exhausted", "原地打转或长时间没进展,自动恢复都试过了", "Take over by remote control", "遥控接管"],
  "localization_unreliable": ["Localization unreliable", "定位不可信,不敢走", "Relocalize the robot", "重新定位"],
  "sensor_lost": ["Lidar or obstacle data lost", "雷达或障碍数据断了", "Check the lidar and restart perception", "查雷达,重启感知"],
  "robot_not_ready": ["Robot not accepting navigation: e-stop, control held elsewhere, fault or unknown heading", "机器人不接受导航命令:急停、控制权在别处、故障或头尾方向不明", "Restore control first (release e-stop, take back control, clear the fault)", "先让机器人恢复可控(松急停、收回控制权、处理故障)"],
  "nav_unavailable": ["Navigation service unavailable", "导航服务没起来或中途掉了", "Restart navigation; contact support if it repeats", "重启导航服务;反复出现请联系工程师"],
  "nav2_plan_failed": ["Navigation failed for an unclassified reason", "导航失败,细分不出原因", "Check the logs; frequent occurrences mean classification needs work", "看日志;这个码出现多了说明分类还要补"],
};
