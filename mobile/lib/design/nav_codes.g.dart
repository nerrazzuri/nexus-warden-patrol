// 生成的文件,别手改:改 design/ 下的 JSON,再跑 python3 tools/gen_mobile_design.py。

/// 导航失败原因码:``(英文, 中文, 英文处理建议, 中文处理建议)``。
/// 来源 ``nexwar_contract.navcodes``。
const Map<String, (String, String, String, String)> navFailCodes = <String, (String, String, String, String)>{
  'route_too_narrow': ('Route too narrow to pass', '路线太窄,过不去',
      'Change the route, or mark this passage impassable on the map', '改路线,或在地图上把这段标成不可通行'),
  'goal_too_close_to_wall': ('Goal too close to a wall to stand or turn', '目标点贴墙,站不下或转不开',
      'Move the waypoint into open space', '把这个航点往空处挪一点'),
  'goal_occupied': ('Goal is occupied by an object', '目标点被东西占住',
      'Remove the object and dispatch again', '把东西挪开后再派一次'),
  'goal_unreachable': ('No route to the goal', '规划不出到目标的路线',
      'Check the map and no-go zones for a blocked route', '查地图和禁行区是不是把路堵死了'),
  'dynamic_obstacle_blocked': ('Blocked too long by people, vehicles or unmapped objects', '被人、车或地图上没有的东西挡住太久',
      'Check on site what is blocking', '去现场看是什么挡住了'),
  'robot_trapped': ('Robot trapped: blocked front and back, or standing in an obstacle', '机器人被困:前后都被挡,或脚下被判成障碍',
      'Move the robot a little, or drive it out by remote, then dispatch again', '把机器人挪开一点,或遥控出来再派'),
  'controller_stalled': ('Stalled or oscillating; automatic recovery exhausted', '原地打转或长时间没进展,自动恢复都试过了',
      'Take over by remote control', '遥控接管'),
  'localization_unreliable': ('Localization unreliable', '定位不可信,不敢走',
      'Set the robot\'s position again on the Localization page', '在「定位」页重新标一下机器人在哪儿'),
  'sensor_lost': ('Lidar or obstacle data lost', '雷达或障碍数据断了',
      'Check that the lidar on the robot\'s head is not covered and is spinning; if that does not help, restart the robot on the Diagnostics page', '看一下机器人头上的雷达有没有被挡住、在不在转;还不行就在「诊断」页重启这台机器人'),
  'robot_not_ready': ('Robot is not taking automatic driving commands: e-stop pressed, someone is driving it, a fault, or it is not standing yet', '机器人现在不听自动行走的命令:急停按着、有人在遥控、有故障,或还没站好',
      'Release the e-stop, leave remote control, make the robot stand up, then dispatch again; for a fault, see the Robots page', '松开急停、退出遥控、让机器人站起来,再派一次;有故障先看机器人页'),
  'nav_unavailable': ('The robot\'s self-driving is not ready or stopped', '机器人的自动行走功能没准备好或中途停了',
      'Wait a minute or two and dispatch again; if not, restart the robot on the Diagnostics page, and send a problem report from the App if it repeats', '等一两分钟再派;还不行就在「诊断」页重启这台机器人,反复出现请在 App 里提交问题单'),
  'nav2_plan_failed': ('Self-driving failed for a reason the robot could not tell', '自动行走失败,具体原因没分出来',
      'Dispatch again; if it keeps failing at the same place, send a problem report from the App', '再派一次;同一个地方反复失败,请在 App 里提交问题单'),
};
