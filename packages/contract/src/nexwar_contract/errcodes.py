# ruff: noqa: E501 —— 码表一行一个码，中英文说明并排，拆行反而难查
"""错误码总表(日志设计 第 7 条，用户 11-10 定:十六进制 ``0xMMRR``)。

- 高两位 ``MM`` 是模块，低两位 ``RR`` 是这个模块里的第几种原因。码一旦定下**不改、不重复用**;
  不用了标 ``retired``,留在表里。
- 每个码有英文名(``dispatch.offline``,日志里跟十六进制写在一起)、中英文的「怎么回事」和
  「该做什么」、级别(提示 / 警告 / 严重，单独一栏，不编进码里)、谁来处理(用户自己 / 工程师)。
- 界面、手册显示十六进制;日志写 ``code=0x0201 dispatch.offline``(:func:`tag`)。
- 告警种类、派单被拒的代号、导航失败码都在这里有对应的码(``ALERT``、``REFUSAL``、``NAV``),
  测试看着每一种都有。
- 《错误码手册》(``docs/错误码手册.md``)、网页、App 的码表由 ``tools/gen_mobile_design.py`` 从这里生成。
"""

from __future__ import annotations

from dataclasses import dataclass

#: 模块:高两位 → (英文前缀, 中文名, 英文名)。
MODULES: dict[int, tuple[str, str, str]] = {
    0x01: ("site", "站点系统", "Site system"),
    0x02: ("dispatch", "派单与任务", "Dispatch and tasks"),
    0x03: ("sched", "巡逻日程", "Patrol schedule"),
    0x04: ("nav", "导航", "Navigation"),
    0x05: ("robot", "机器人本体(运控、急停、电池、充电)", "Robot body (motion, e-stop, battery, charging)"),
    0x06: ("loc", "定位与建图", "Localization and mapping"),
    0x07: ("net", "网络、证书、连接", "Network, certificates, connections"),
    0x08: ("sense", "告警来源(入侵、看见人、摄像头、传感器)", "Alarm sources (intrusion, people, cameras, sensors)"),
    0x09: ("update", "升级与配置", "Upgrades and configuration"),
    0x0A: ("app", "App", "App"),
    0x0B: ("evidence", "证据、录像、存储", "Evidence, recordings, storage"),
}

LEVELS = ("info", "warn", "error")
WHO = ("user", "engineer")


@dataclass(frozen=True, slots=True)
class ErrCode:
    num: int
    name: str
    level: str
    who: str
    zh: str
    en: str
    do_zh: str = ""
    do_en: str = ""
    retired: bool = False

    @property
    def hex(self) -> str:
        return f"0x{self.num:04X}"

    @property
    def module(self) -> int:
        return self.num >> 8


# (码, 英文名, 级别, 谁处理, 怎么回事 中/英, 该做什么 中/英)。按码排;新码加在模块最后。
_T: tuple[tuple[int, str, str, str, str, str, str, str], ...] = (
    # ---- 0x01 站点系统
    (0x0101, "site.disk_low", "warn", "engineer", "站点硬盘快满了", "Site disk is nearly full",
     "到诊断页看哪些占地方;删旧录像或加硬盘", "Check usage on the Diagnostics page; delete old recordings or add disk"),
    (0x0102, "site.disk_80", "warn", "engineer", "站点硬盘用了八成", "Site disk is 80% used",
     "留意空间，必要时清理", "Keep an eye on space; clean up if needed"),
    (0x0103, "site.backup_verify_failed", "warn", "engineer", "站点备份校验没通过", "Site backup failed verification",
     "到系统页重新做一次备份", "Run a new backup on the System page"),
    (0x0104, "site.backup_stale", "warn", "engineer", "站点很久没备份了", "Site has not been backed up for a long time",
     "检查备份设置", "Check the backup settings"),
    (0x0105, "site.push_failed", "warn", "engineer", "告警推送发不出去", "Alarm notifications could not be sent",
     "检查推送设置和网络", "Check notification settings and the network"),
    (0x0106, "site.watchdog_died", "error", "engineer", "站点内部的一个后台任务停了", "A site background job stopped",
     "重启站点服务;仍出现就把诊断包发给工程师", "Restart the site service; if it recurs send a diagnostics bundle"),
    (0x0107, "site.too_old", "warn", "engineer", "站点版本比机器人旧", "Site software is older than the robot's",
     "升级站点", "Upgrade the site"),
    (0x0108, "site.incident_flood", "warn", "user", "短时间内事件太多，已合并", "Too many events in a short time; merged",
     "看活动日志里是什么在反复触发", "See what keeps triggering in the activity log"),
    (0x0109, "site.lease_expired", "error", "engineer", "控制权租约过期", "Control lease expired",
     "检查站点和机器人的连接", "Check the site–robot connection"),
    (0x010A, "site.suspend_stale", "error", "engineer", "暂停状态太久没刷新", "Suspend state not refreshed for too long",
     "检查站点服务是否正常", "Check that the site service is running normally"),
    (0x010B, "site.clock_untrusted", "warn", "engineer", "站点的钟不可信", "Site clock is not trusted",
     "检查对时(chrony)", "Check time sync (chrony)"),
    (0x010C, "site.account_request", "info", "user", "有人申请账号", "Someone requested an account",
     "到用户页批准或拒绝", "Approve or reject it on the Users page"),
    # ---- 0x02 派单与任务
    (0x0201, "dispatch.offline", "warn", "user", "机器人不在线或很久没上报", "Robot is offline or has not reported recently",
     "看机器人是否开机、网络是否通", "Check the robot is on and connected"),
    (0x0202, "dispatch.held", "warn", "user", "机器人被人叫停了", "Robot was stopped by someone",
     "先点「恢复」再派", "Press Resume before sending it"),
    (0x0203, "dispatch.manual_only", "warn", "user", "机器人设成只许手动派", "Robot is set to manual dispatch only",
     "要排程能派，到机器人页关掉「只许手动派」", "Turn off manual-only on the Robots page to let schedules send it"),
    (0x0204, "dispatch.supervision", "warn", "user", "机器人要人在现场监护", "Robot needs a person present",
     "先打开「我在监护」", "Turn on \"I'm supervising\" first"),
    (0x0205, "dispatch.teleop", "warn", "user", "机器人正在遥控", "Robot is being driven by hand",
     "等遥控结束", "Wait until remote control ends"),
    (0x0206, "dispatch.not_localized", "warn", "user", "机器人不知道自己在哪", "Robot does not know where it is",
     "到定位页帮它设位置", "Set its position on the Localization page"),
    (0x0207, "dispatch.not_ready", "warn", "user", "机器人还没准备好", "Robot is not ready yet",
     "等它站起来、启动完或充完电", "Wait until it has stood up, finished starting or charging"),
    (0x0208, "dispatch.map_mismatch", "warn", "user", "路线画在另一张图(或旧版本)上", "Route was drawn on a different map or version",
     "换成机器人现在用的图，或重画路线", "Switch to the robot's current map, or redraw the route"),
    (0x0209, "dispatch.obstacles", "error", "engineer", "机器人避障不可用", "Robot obstacle avoidance is not working",
     "到诊断页看避障", "Check obstacle avoidance on the Diagnostics page"),
    (0x020A, "dispatch.clock", "warn", "engineer", "机器人和站点的钟对不上", "Robot and site clocks disagree",
     "等一分钟再派;仍不行检查对时", "Wait a minute and retry; if it persists check time sync"),
    (0x020B, "dispatch.zones_sync", "warn", "engineer", "机器人还没收到最新的区域和地图", "Robot has not received the latest zones and map",
     "等同步完;仍不行重启机器人软件", "Wait for sync; if it persists restart the robot software"),
    (0x020C, "dispatch.deterring", "info", "user", "机器人正在驱离", "Robot is deterring someone", "", ""),
    (0x020D, "dispatch.heading", "error", "engineer", "机器人头尾方向没设对", "Robot front/back direction is wrong",
     "工程师重新设头尾方向", "An engineer re-sets the front/back direction"),
    (0x020E, "dispatch.unreachable", "warn", "user", "有一个点机器人到不了", "Robot cannot reach one of the points",
     "把点挪到空处，或改路线", "Move the point into open space or change the route"),
    (0x020F, "dispatch.zones_unconfirmed", "warn", "user", "地图上的禁行区还没确认", "No-go zones on this map are not confirmed",
     "管理员到地图页确认禁行区", "An administrator confirms the zones on the Map page"),
    (0x0210, "dispatch.busy", "info", "user", "机器人正在执行别的任务", "Robot is busy with another task",
     "等它做完，或先叫停", "Wait until it finishes, or stop it first"),
    (0x0211, "dispatch.unregistered", "error", "engineer", "机器人没登记或登记已吊销", "Robot is not registered or was revoked",
     "到机器人页重新添加", "Add it again on the Robots page"),
    (0x0212, "dispatch.bad_mission", "error", "engineer", "任务定义不对(太多点、太大或格式错)", "Mission definition is invalid (too many points, too large, malformed)",
     "检查路线", "Check the route"),
    (0x0213, "dispatch.refused", "warn", "user", "派单被拒(其他原因)", "Dispatch refused (other reason)",
     "看原因说明", "See the reason text"),
    (0x0214, "dispatch.preflight_refused", "warn", "user", "出发前检查没通过，机器人没出发", "Pre-departure check failed; the robot did not leave",
     "按说明处理(标原点、定位、电量…)", "Fix what the message says (origin, localization, battery…)"),
    (0x0215, "dispatch.run_abort", "error", "user", "巡逻中途中止", "Patrol aborted part-way",
     "看原因;去现场看看机器人", "See the reason; check the robot on site"),
    (0x0216, "dispatch.stuck", "error", "user", "机器人卡住动不了", "Robot is stuck",
     "去现场看看", "Go and check on site"),
    (0x0217, "dispatch.waypoint_missed", "warn", "user", "巡逻点没到达，已跳过", "Patrol point not reached; skipped",
     "看路上是否被挡;连续几趟到不了要改路线", "Check if the way is blocked; change the route if it keeps happening"),
    (0x0218, "dispatch.lane_stuck", "warn", "user", "机器人在通道里卡住", "Robot stuck in a passage", "去现场看看", "Go and check on site"),
    (0x0219, "dispatch.standby_failed", "warn", "user", "回不到待命点", "Could not return to the standby point",
     "看路上是否被挡", "Check if the way is blocked"),
    (0x021A, "dispatch.run_start", "info", "user", "巡逻开始", "Patrol started", "", ""),
    (0x021B, "dispatch.run_done", "info", "user", "巡逻完成", "Patrol finished", "", ""),
    (0x021C, "dispatch.adhoc_patrol", "info", "user", "临时巡逻", "One-off patrol", "", ""),
    (0x021D, "dispatch.adhoc_queue", "info", "user", "临时巡逻排队中", "One-off patrol queued", "", ""),
    (0x021E, "dispatch.guard_stuck", "warn", "user", "值守路线连着几圈跑不成", "Guard route failed several laps in a row",
     "看路线上是否被挡", "Check if the route is blocked"),
    (0x021F, "dispatch.guard_prep", "warn", "user", "值守准备中", "Preparing for guard duty", "", ""),
    (0x0220, "dispatch.zone_unwatched", "warn", "user", "防区超时没看", "Zone has not been checked in time",
     "看机器人是否在路上", "Check whether a robot is on the way"),
    # ---- 0x03 巡逻日程
    (0x0301, "sched.started", "info", "user", "日程到点开始巡逻", "Schedule started a patrol", "", ""),
    (0x0302, "sched.missed", "warn", "user", "日程这一轮没跑(过了时间窗)", "Scheduled round did not run (window passed)",
     "看「之前没派出去」的原因", "See why no robot could be sent earlier"),
    (0x0303, "sched.missed_alarm", "error", "user", "日程这一轮没跑，按设置报警", "Scheduled round did not run; alarm as configured",
     "看原因，必要时手动派", "See the reason; dispatch by hand if needed"),
    (0x0304, "sched.no_robot", "warn", "user", "到点没有能派的机器人", "No robot could be sent when due",
     "看各机器人的原因", "See each robot's reason"),
    (0x0305, "sched.busy", "info", "user", "到点机器人在忙，等它", "Robot busy when due; waiting", "", ""),
    (0x0306, "sched.supervised", "warn", "user", "机器人只许手动派或要人监护，不接排程", "Robot is manual-only or needs supervision; schedules do not send it",
     "到机器人页改设置", "Change the setting on the Robots page"),
    (0x0307, "sched.dispatch_failed", "error", "user", "日程派出去被机器人拒了", "Robot refused the scheduled patrol",
     "看原因", "See the reason"),
    (0x0308, "sched.displaced", "info", "user", "这一拍给了更优先的日程", "Given to a higher-priority schedule", "", ""),
    (0x0309, "sched.weather", "info", "user", "雷暴，排程巡逻暂停", "Thunderstorm; scheduled patrols paused", "", ""),
    (0x030A, "sched.clock", "error", "engineer", "站点的钟不可信，日程不起", "Site clock not trusted; schedules held",
     "检查对时", "Check time sync"),
    (0x030B, "sched.died", "error", "engineer", "日程执行器停了", "The scheduler stopped",
     "重启站点服务", "Restart the site service"),
    (0x030C, "sched.interrupted", "warn", "user", "日程巡逻被打断", "Scheduled patrol was interrupted", "看原因", "See the reason"),
    (0x030D, "sched.bundle_lag", "warn", "engineer", "任务包没同步到机器人", "Mission bundle not synced to the robot",
     "检查连接", "Check the connection"),
    # ---- 0x04 导航(与 navcodes.FAIL_CODES 一一对应，另加过程事件)
    (0x0401, "nav.route_too_narrow", "warn", "user", "路线太窄，过不去", "Route too narrow to pass",
     "改路线，或在地图上把这段标成不可通行", "Change the route, or mark this passage impassable"),
    (0x0402, "nav.goal_too_close_to_wall", "warn", "user", "目标点贴墙，站不下或转不开", "Goal too close to a wall",
     "把这个点往空处挪一点", "Move the waypoint into open space"),
    (0x0403, "nav.goal_occupied", "warn", "user", "目标点被东西占住", "Goal is occupied", "清走东西或挪点", "Clear it or move the point"),
    (0x0404, "nav.goal_unreachable", "warn", "user", "到不了目标点", "Goal unreachable", "改路线", "Change the route"),
    (0x0405, "nav.dynamic_obstacle_blocked", "warn", "user", "路被临时的东西挡住", "Blocked by a temporary obstacle",
     "清走障碍", "Clear the obstacle"),
    (0x0406, "nav.robot_trapped", "error", "user", "机器人被困住", "Robot is trapped", "去现场把它带出来", "Go and free it"),
    (0x0407, "nav.controller_stalled", "warn", "engineer", "控制器卡住不动", "Controller stalled", "看诊断", "Check diagnostics"),
    (0x0408, "nav.localization_unreliable", "error", "user", "定位不可靠，停下了", "Localization unreliable; stopped",
     "帮它重新定位", "Re-localize it"),
    (0x0409, "nav.sensor_lost", "error", "engineer", "传感器数据断了", "Sensor data lost", "检查雷达、相机", "Check lidar and cameras"),
    (0x040A, "nav.robot_not_ready", "warn", "user", "机器人没准备好", "Robot not ready", "等它准备好", "Wait until it is ready"),
    (0x040B, "nav.nav_unavailable", "error", "engineer", "导航没起来", "Navigation unavailable", "看诊断页的导航", "Check navigation on Diagnostics"),
    (0x040C, "nav.nav2_plan_failed", "warn", "engineer", "Nav2 规划失败", "Nav2 planning failed", "看诊断", "Check diagnostics"),
    (0x040D, "nav.blocked", "warn", "user", "机器人被挡在原地超过一分钟", "Robot blocked in place over a minute",
     "看路上是不是有东西", "Check the way for obstacles"),
    (0x040E, "nav.nogo", "error", "user", "机器人进了禁行区", "Robot entered a no-go zone", "去现场看看", "Go and check on site"),
    (0x040F, "nav.fallback_planner", "info", "engineer", "Nav2 没就绪，退回备用规划", "Nav2 not ready; using the fallback planner", "", ""),
    # ---- 0x05 机器人本体
    (0x0501, "robot.estop_pressed", "error", "user", "急停按下了", "Emergency stop pressed", "确认安全后松开急停", "Release it once safe"),
    (0x0502, "robot.fallen", "error", "user", "机器人倒了", "Robot has fallen", "去现场扶起来", "Go and help it up"),
    (0x0503, "robot.battery_abort", "error", "user", "电量低，中止巡逻", "Battery low; patrol aborted", "去充电", "Charge it"),
    (0x0504, "robot.charge_failed", "error", "user", "自动回充没成", "Auto-charging failed", "去看充电桩", "Check the charging dock"),
    (0x0505, "robot.dock_stuck", "error", "user", "可能还在充电桩上，动不了", "May still be on the dock and locked", "去现场挪开", "Move it by hand"),
    (0x0506, "robot.charge_overlap", "warn", "user", "两台同时去充电，区域没机器人守", "Two robots charging; area unguarded", "", ""),
    (0x0507, "robot.offline", "error", "user", "机器人离线", "Robot went offline", "看机器人是否开机、网络是否通", "Check power and network"),
    (0x0508, "robot.offline_idle", "warn", "user", "空闲的机器人离线", "Idle robot went offline", "看机器人是否开机", "Check it is on"),
    (0x0509, "robot.online", "info", "user", "机器人上线", "Robot came online", "", ""),
    (0x050A, "robot.board_hot", "warn", "engineer", "上装主板偏热", "Payload board running hot", "检查风扇和散热", "Check fans and cooling"),
    (0x050B, "robot.board_overheat", "error", "engineer", "上装主板过热", "Payload board overheating", "停用并检查散热", "Stop and check cooling"),
    (0x050C, "robot.fault", "error", "engineer", "机器人报故障", "Robot reported a fault", "看故障说明", "See the fault text"),
    (0x050D, "robot.swap_soon", "warn", "user", "快要换电池了", "Battery swap soon", "准备电池", "Get a battery ready"),
    (0x050E, "robot.swap_needed", "error", "user", "到换电位了，请来换电池", "At the swap point; please swap the battery", "去换电池", "Swap the battery"),
    (0x050F, "robot.swap_overdue", "error", "user", "等换电池超过 30 分钟", "Battery swap overdue", "马上去换", "Swap it now"),
    (0x0510, "robot.swap_stuck", "error", "user", "拔着一块电池机器人还在走", "Robot moving with a battery out", "别靠近，用遥控器或急停", "Keep clear; use the remote or e-stop"),
    (0x0511, "robot.battery_swap", "info", "user", "换了电池", "Battery swapped", "", ""),
    (0x0512, "robot.force_flipped", "error", "user", "机器人被掀翻", "Robot was flipped", "去现场", "Go on site"),
    (0x0513, "robot.force_lifted", "error", "user", "机器人被抬起", "Robot was lifted", "去现场", "Go on site"),
    (0x0514, "robot.force_covered", "error", "user", "机器人被罩住", "Robot was covered", "去现场", "Go on site"),
    (0x0515, "robot.force_bump", "warn", "user", "机器人被撞了一下", "Robot was bumped", "", ""),
    (0x0516, "robot.force_config_bad", "warn", "engineer", "受力检测配置不对", "Force detection misconfigured", "工程师检查配置", "An engineer checks the config"),
    (0x0517, "robot.payload_strobe", "error", "engineer", "爆闪灯坏了", "Strobe light failed", "检查上装", "Check the payload"),
    (0x0518, "robot.payload_siren", "error", "engineer", "警笛坏了", "Siren failed", "检查上装", "Check the payload"),
    (0x0519, "robot.payload_spotlight", "error", "engineer", "探照灯坏了", "Spotlight failed", "检查上装", "Check the payload"),
    (0x051A, "robot.payload_amp", "warn", "engineer", "功放坏了", "Amplifier failed", "检查上装", "Check the payload"),
    # ---- 0x06 定位与建图
    (0x0601, "loc.degraded", "warn", "user", "定位变差，原地等恢复", "Localization degraded; waiting", "", ""),
    (0x0602, "loc.lost_paused", "error", "user", "定位丢了，暂停", "Localization lost; paused", "帮它重新定位", "Re-localize it"),
    (0x0603, "loc.lost_idle", "warn", "user", "空闲时定位不可信", "Localization untrusted while idle", "到定位页设位置", "Set its position"),
    (0x0604, "loc.rtk", "warn", "engineer", "RTK 不可用", "RTK unavailable", "检查 RTK 和改正数据", "Check RTK and corrections"),
    (0x0605, "loc.map_failed", "warn", "engineer", "地图下发或切换失败", "Map delivery or switch failed", "重试", "Retry"),
    (0x0606, "loc.map_integrity", "warn", "engineer", "地图文件不完整", "Map files incomplete", "重新下发地图", "Push the map again"),
    (0x0607, "loc.map_build_failed", "warn", "engineer", "建图失败", "Map building failed", "看建图日志", "Check the mapping log"),
    (0x0608, "loc.map_ready", "info", "engineer", "地图已建成", "Map built", "在建图向导里看结论", "Check the result in the mapping wizard"),
    # ---- 0x07 网络、证书、连接
    (0x0701, "net.tls_handshake", "info", "engineer", "TLS 握手失败(对方没信站点证书或证书不对)", "TLS handshake failed (client does not trust the site certificate)",
     "核对手机、浏览器装的站点证书", "Check the site certificate on the phone or browser"),
    (0x0702, "net.cert_expiring", "warn", "engineer", "证书快到期", "Certificate expiring", "续签", "Renew it"),
    (0x0703, "net.cert_renew_failed", "warn", "engineer", "证书自动续签失败", "Certificate auto-renewal failed", "明天会再试;仍不行手动续签", "Retries tomorrow; renew by hand if it persists"),
    (0x0704, "net.clock_skew", "warn", "engineer", "机器人和站点的钟差太多", "Robot–site clock difference too large", "检查对时", "Check time sync"),
    (0x0705, "net.wifi_change", "warn", "engineer", "机器人的 Wi-Fi 变了", "Robot Wi-Fi changed", "确认是不是有人改的", "Confirm the change was intended"),
    (0x0706, "net.bind_request", "info", "user", "有机器人申请加入", "A robot asked to join", "到机器人页批准", "Approve it on the Robots page"),
    (0x0707, "net.mqtt_lost", "warn", "engineer", "站点和机器人的消息连接断了", "Site–robot message link lost", "检查网络", "Check the network"),
    # ---- 0x08 告警来源
    (0x0801, "sense.intrusion", "error", "user", "防区有入侵", "Intrusion in a zone", "看现场画面", "Check the live view"),
    (0x0802, "sense.intrusion_unanswered", "error", "user", "入侵没有机器人去", "Intrusion with no robot responding", "派人去", "Send a person"),
    (0x0803, "sense.intrusion_person", "error", "user", "拦截点看到人", "Person seen at the intercept point", "看现场画面", "Check the live view"),
    (0x0804, "sense.deter_cornered", "error", "user", "驱离中无路可退", "Cornered while deterring", "派人去", "Send a person"),
    (0x0805, "sense.robot_sees_person", "error", "user", "机器人看见人", "Robot sees a person", "看现场，决定要不要驱离", "Check and decide whether to deter"),
    (0x0806, "sense.person_overdue", "error", "user", "看见人 10 分钟没人到场", "Person seen; nobody arrived in 10 min", "马上派人", "Send someone now"),
    (0x0807, "sense.person_left", "error", "user", "被跟的人越过出口线", "Followed person crossed the exit line", "", ""),
    (0x0808, "sense.authorized_person", "info", "user", "看见的是授权人员", "Authorized person seen", "", ""),
    (0x0809, "sense.cctv_offline", "warn", "engineer", "摄像头连不上", "Camera unreachable", "检查摄像头电源和网线", "Check camera power and cable"),
    (0x080A, "sense.lens_blocked", "warn", "user", "相机镜头被挡", "Camera lens blocked", "擦镜头", "Clean the lens"),
    (0x080B, "sense.finding", "warn", "user", "巡逻发现异常", "Patrol finding", "看照片", "See the photo"),
    # ---- 0x09 升级与配置
    (0x0901, "update.release_failed", "warn", "engineer", "机器人升级失败", "Robot upgrade failed", "看升级页的原因", "See the reason on the Upgrades page"),
    (0x0902, "update.agent_too_old", "warn", "engineer", "机器人软件比站点旧", "Robot software older than the site", "升级机器人", "Upgrade the robot"),
    (0x0903, "update.agent_args_skipped", "warn", "engineer", "机器人有配置项没生效", "Some robot settings were not applied", "看诊断", "Check diagnostics"),
    # ---- 0x0A App
    (0x0A01, "app.crash", "error", "engineer", "App 出错", "App error", "把诊断信息导出发给工程师", "Export diagnostics and send to an engineer"),
    # ---- 0x0B 证据、录像、存储
    (0x0B01, "evidence.archive_failed", "error", "engineer", "机器人上归档写不进去", "Robot could not write its archive", "看机器人存储", "Check robot storage"),
    (0x0B02, "evidence.plain", "warn", "engineer", "机器人上的照片录像没加密", "Robot photos and video unencrypted", "装证据公钥", "Install the evidence key"),
    (0x0B03, "evidence.unopened", "warn", "engineer", "站点解不开机器人封好的证据", "Site cannot open sealed evidence", "检查证据私钥", "Check the evidence private key"),
    (0x0B04, "evidence.seal_failed", "warn", "engineer", "证据加密失败", "Evidence sealing failed", "看诊断", "Check diagnostics"),
    (0x0B05, "evidence.purged_incoming_stuck", "warn", "engineer", "删过的证据还在往上传", "Deleted evidence still being uploaded", "", ""),
    (0x0B06, "evidence.upload_refused", "warn", "engineer", "站点不收机器人传的文件", "Site refused an upload", "看原因", "See the reason"),
    (0x0B07, "evidence.upload_backlog", "warn", "engineer", "机器人上待传的东西积压", "Upload backlog on the robot", "检查网络", "Check the network"),
    (0x0B08, "evidence.recording_failed", "warn", "engineer", "录像失败", "Recording failed", "看诊断", "Check diagnostics"),
    (0x0B09, "evidence.recording_dropped", "warn", "engineer", "录像丢了一段", "Part of a recording was dropped", "", ""),
    (0x0B0A, "evidence.recording_trimmed", "warn", "user", "录像空间满，删了最旧的", "Recording space full; oldest removed", "", ""),
    (0x0B0B, "evidence.recording_delete_failed", "error", "engineer", "录像删不掉", "Recording could not be deleted", "看诊断", "Check diagnostics"),
)

CODES: dict[str, ErrCode] = {n: ErrCode(c, n, lv, w, zh, en, dz, de)
                             for c, n, lv, w, zh, en, dz, de in _T}
BY_NUM: dict[int, ErrCode] = {c.num: c for c in CODES.values()}

#: 告警种类 → 码名(``alerts.LEVEL_OF`` 里每一种都要有，测试看着)。
ALERT: dict[str, str] = {
    "stuck": "dispatch.stuck", "intrusion": "sense.intrusion",
    "intrusion_unanswered": "sense.intrusion_unanswered", "intrusion_person": "sense.intrusion_person",
    "deter_cornered": "sense.deter_cornered", "battery_abort": "robot.battery_abort",
    "preflight_refused": "dispatch.preflight_refused", "run_abort": "dispatch.run_abort",
    "archive_failed": "evidence.archive_failed", "fallen": "robot.fallen",
    "loc_lost_paused": "loc.lost_paused", "charge_failed": "robot.charge_failed",
    "dock_stuck": "robot.dock_stuck", "charge_overlap": "robot.charge_overlap",
    "zone_unwatched": "dispatch.zone_unwatched", "swap_soon": "robot.swap_soon",
    "guard_prep": "dispatch.guard_prep", "swap_needed": "robot.swap_needed",
    "swap_overdue": "robot.swap_overdue", "guard_stuck": "dispatch.guard_stuck",
    "swap_stuck": "robot.swap_stuck", "dog_sees_person": "sense.robot_sees_person",
    "person_overdue": "sense.person_overdue", "person_left": "sense.person_left",
    "evidence_plain": "evidence.plain", "evidence_unopened": "evidence.unopened",
    "evidence_seal_failed": "evidence.seal_failed", "force_flipped": "robot.force_flipped",
    "force_lifted": "robot.force_lifted", "force_covered": "robot.force_covered",
    "force_bump": "robot.force_bump", "force_config_bad": "robot.force_config_bad",
    "purged_incoming_stuck": "evidence.purged_incoming_stuck",
    "backup_verify_failed": "site.backup_verify_failed", "push_failed": "site.push_failed",
    "cert_expiring": "net.cert_expiring", "cert_renew_failed": "net.cert_renew_failed",
    "site_disk_low": "site.disk_low", "lane_stuck": "dispatch.lane_stuck",
    "agent_too_old": "update.agent_too_old", "site_too_old": "site.too_old",
    "loc_degraded": "loc.degraded", "loc_lost_idle": "loc.lost_idle", "nav_blocked": "nav.blocked",
    "estop_pressed": "robot.estop_pressed", "lease_expired": "site.lease_expired",
    "suspend_stale": "site.suspend_stale", "watchdog_died": "site.watchdog_died",
    "schedule_died": "sched.died", "schedule_missed": "sched.missed_alarm",
    "robot_offline": "robot.offline", "nogo": "nav.nogo",
    "recording_delete_failed": "evidence.recording_delete_failed",
    "payload_strobe": "robot.payload_strobe", "payload_siren": "robot.payload_siren",
    "payload_spotlight": "robot.payload_spotlight", "payload_amp": "robot.payload_amp",
    "board_hot": "robot.board_hot", "board_overheat": "robot.board_overheat",
    "lens_blocked": "sense.lens_blocked", "finding": "sense.finding",
    "recording_failed": "evidence.recording_failed", "agent_args_skipped": "update.agent_args_skipped",
    "recording_dropped": "evidence.recording_dropped", "recording_trimmed": "evidence.recording_trimmed",
    "cctv_offline": "sense.cctv_offline", "disk_80": "site.disk_80", "backup_stale": "site.backup_stale",
    "map_failed": "loc.map_failed", "map_ready": "loc.map_ready", "map_integrity": "loc.map_integrity", "rtk": "loc.rtk",
    "standby_failed": "dispatch.standby_failed", "upload_refused": "evidence.upload_refused",
    "release_failed": "update.release_failed", "upload_backlog": "evidence.upload_backlog",
    "bundle_lag": "sched.bundle_lag", "clock_skew": "net.clock_skew",
    "schedule_skipped": "sched.missed", "schedule_blocked": "sched.no_robot",
    "schedule_waiting": "sched.no_robot",
    "schedule_interrupted": "sched.interrupted", "incident_flood": "site.incident_flood",
    "robot_offline_idle": "robot.offline_idle", "bind_request": "net.bind_request",
    "wifi_change": "net.wifi_change", "account_request": "site.account_request",
    "run_done": "dispatch.run_done", "run_start": "dispatch.run_start",
    "battery_swap": "robot.battery_swap", "authorized_person": "sense.authorized_person",
    "adhoc_patrol": "dispatch.adhoc_patrol", "adhoc_queue": "dispatch.adhoc_queue",
    "patrol_waypoint": "dispatch.waypoint_missed", "robot_fault": "robot.fault",
    "map_build_failed": "loc.map_build_failed",
}

#: 派单被拒的代号(``nexwar_site.refusals.CODES``)→ 码名。
REFUSAL: dict[str, str] = {
    "held": "dispatch.held", "zones_unconfirmed": "dispatch.zones_unconfirmed",
    "supervision": "dispatch.supervision", "teleop": "dispatch.teleop", "offline": "dispatch.offline",
    "not_localized": "dispatch.not_localized", "not_ready": "dispatch.not_ready",
    "estop": "dispatch.not_ready", "no_control": "dispatch.not_ready",
    "not_standing": "dispatch.not_ready",
    "map_mismatch": "dispatch.map_mismatch", "obstacles": "dispatch.obstacles", "clock": "dispatch.clock",
    "zones_sync": "dispatch.zones_sync", "deterring": "dispatch.deterring",
    "manual_only": "dispatch.manual_only", "heading": "dispatch.heading",
    "unreachable": "dispatch.unreachable", "busy": "dispatch.busy",
    "unregistered": "dispatch.unregistered", "bad_mission": "dispatch.bad_mission",
}

#: 日程结果(``schedule_runs.outcome``)→ 码名。
SCHEDULE: dict[str, str] = {
    "started": "sched.started", "skip": "sched.missed", "alarm": "sched.missed_alarm",
    "no_robot": "sched.no_robot", "busy": "sched.busy", "supervised": "sched.supervised",
    "dispatch_failed": "sched.dispatch_failed", "displaced": "sched.displaced",
    "weather": "sched.weather", "skew": "sched.clock",
}


def nav(code: str) -> str:
    """导航失败码(``navcodes.FAIL_CODES``)→ 码名。"""
    return f"nav.{code}"


def get(name_or_hex: str | int | None) -> ErrCode | None:
    """按英文名、``0x0201``、整数认;认不得 ``None``。"""
    if name_or_hex is None:
        return None
    if isinstance(name_or_hex, int) and not isinstance(name_or_hex, bool):
        return BY_NUM.get(name_or_hex)
    s = str(name_or_hex).strip()
    if s.lower().startswith("0x"):
        try:
            return BY_NUM.get(int(s, 16))
        except ValueError:
            return None
    return CODES.get(s)


def for_alert(kind: str) -> ErrCode | None:
    return get(ALERT.get(kind))


def tag(name: str | None) -> str:
    """日志里写的样子:``0x0201 dispatch.offline``;不在表里的原样(``?`` 前缀),空给 ``-``。"""
    if not name:
        return "-"
    c = get(name)
    return f"{c.hex} {c.name}" if c is not None else f"?{name}"


def wire(name: str | None) -> dict[str, str]:
    """回复、记录里带的字段:``{"err": "0x0201", "err_name": "dispatch.offline"}``;不认得给空。
    (不叫 ``code``:导航失败码、拒绝代号早就占了那个名字。)"""
    c = get(name)
    return {"err": c.hex, "err_name": c.name} if c is not None else {}
