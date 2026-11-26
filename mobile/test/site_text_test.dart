// 手机 App 测试 M05：站点、机器人的中文原文按 App 语言说（跟网页 sitetext.test.ts 同一套例子）。
import 'package:flutter_test/flutter_test.dart';
import 'package:nexwar_patrol/l10n.dart';
import 'package:nexwar_patrol/net/site_client.dart';
import 'package:nexwar_patrol/net/site_text.dart';

void main() {
  setUp(() => appLang.value = AppLang.en);
  tearDown(() => appLang.value = AppLang.zh);

  test('易用性 37 第八轮：值守日志每圈那几句、规划原因码开头、点名', () {
    expect(siteText('第 7 圈跑完,用时 60 秒'), 'Lap 7 done in 60 s');
    expect(siteText('第 7 圈接着跑:a→回待命点'), 'Lap 7 resumed: a → “Return to standby”');
    expect(RegExp(r'[\u4e00-\u9fff]').hasMatch(siteText('start_blocked: 起点在障碍或禁行区里')), isFalse);
    expect(wpName('回待命点'), '“Return to standby”');
  });

  test('用户 11-26：被困 90 秒换车、叫人遥控回来 整句英文', () {
    for (final s in [
      '规划失败(start_blocked):起点在障碍或禁行区里;请用遥控把 A 开回开阔、扫到过的地方',
      'A 被困 92 秒没脱开,换一台;请人遥控把它开回来',
      '第 3 圈跑不成:导航拒了: goto 被设备拒绝: 规划失败(start_blocked):起点在障碍或禁行区里;1 m 内没有能直线挪过去站的地方',
    ]) {
      final en = siteText(s);
      expect(RegExp(r'[\u4e00-\u9fff]').hasMatch(en), isFalse, reason: '$s => $en');
    }
    expect(alertTitle('guard_stuck', 'A 被困 92 秒没脱开:已换一台接着巡'), 'A stuck for 92 s: another robot took over');
  });

  test('易用性 37 复测第六轮：值守一圈 N 个航点未到达 整句英文', () {
    const one = '导航拒了: goto 被设备拒绝: 规划失败(start_blocked):起点在障碍或禁行区里';
    final en = siteText('3 个航点未到达(Drive-thru lane-3, Drive-thru lane-4, 回待命点):$one;回头补也没到:$one');
    expect(RegExp(r'[\u4e00-\u9fff]').hasMatch(en), isFalse, reason: en);
    expect(en, startsWith('3 waypoints not reached (Drive-thru lane-3, Drive-thru lane-4, “Return to standby”): '));
  });

  test('易用性 37 复测：设备那几行翻英文', () {
    expect(siteText('6 个线圈都确认过'), 'All 6 relay channels confirmed');
    expect(siteText('喇叭放警笛声'), 'Siren plays through the speaker');
    expect(siteText('仿真声卡'), 'Simulated sound card');
    expect(siteText('已用 81%,剩 41 GB:到 90% 就不接新的巡逻(没传完的不删)'), startsWith('81% used, 41 GB free'));
  });

  test('易用性 37 复测第四轮：标原点被拒英文（ackReasonText 兜底也翻）；回头补同一句不重复', () {
    expect(ackReasonText('A 现在站的地方不能当待命点:这里 在图上不是可通行的地方(墙、障碍或未扫到)。往开阔、扫到过的地方开 1 m 左右再标'),
        startsWith("A can't use this spot as its standby point"));
    const one = '导航拒了: goto 被设备拒绝: 规划失败(start_blocked):起点在障碍或禁行区里';
    final en = siteText('$one;回头补也没到:$one');
    expect(en.split('with Remote').length, 2, reason: en);
  });

  test('易用性 37 复测 P1-9：起点被挡 + 回头补也没到 整句英文、说用遥控挪', () {
    final en = siteText('导航拒了: goto 被设备拒绝: 规划失败(start_blocked):起点在障碍或禁行区里;回头补也没到:导航拒了: goto 被设备拒绝: 规划失败(start_blocked):起点在障碍或禁行区里');
    expect(RegExp(r'[\u4e00-\u9fff]').hasMatch(en), isFalse, reason: en);
    expect(en, contains('with Remote'));
    expect(en, contains('tried again after the lap'));
  });

  test('易用性 37 复测 P1-7：值守「A 没接:…」、点名（目标点、回待命点）都翻英文', () {
    expect(siteText('A 没接:回待命点 在图上不是可通行的地方(墙、障碍或未扫到)'),
        "A didn't take it: the standby point is not a walkable spot on the map (wall, obstacle or not scanned).");
    expect(siteText('目标点 在图上不是可通行的地方(墙、障碍或未扫到)'), startsWith('The target point is not'));
  });

  test('第 9 轮 W9-10：中文界面站点原话的半角标点换全角（前面是数字、字母也换）；报警标题也换', () {
    appLang.value = AppLang.zh;
    expect(zhPunct('已用 86%,剩 30 GB:到 90% 就不接新的巡逻(没传完的不删)'), '已用 86%，剩 30 GB：到 90% 就不接新的巡逻（没传完的不删）');
    expect(alertTitle('schedule_missed', '排程 route-1-2 本轮未执行:到点没有能派的机器人'), '排程 route-1-2 本轮未执行：到点没有能派的机器人');
    expect(zhPunct('10:30 在 home:3'), '10:30 在 home:3');
    expect(siteKnown('从 7 清了 337 处零星噪点(773 格)'), '从第 7 版清了 337 处零星噪点（773 格）');
    expect(siteKnown('一楼夜巡'), '一楼夜巡');
    appLang.value = AppLang.en;
    expect(siteKnown('从 7 清了 337 处零星噪点(773 格)'), 'Noise cleanup of version 7: removed 337 specks (773 cells)');
    // 第 10 轮 W10-01
    final back = siteText('遥控结束后没能回待命点:B 正在遥控');
    expect(back, startsWith('After remote control, the robot could not go back to its standby point: '));
    expect(hasChinese(back), isFalse, reason: back);
  });

  test('巡逻跳点 + 导航被拒 + 规划失败：整句英文', () {
    expect(siteText('跳过 1 个点(P2):导航拒了: goto 被设备拒绝: 规划失败(goal_blocked):终点在障碍、禁行区里或贴得太近'),
        'Skipped 1 point (P2): navigation refused: no path — the destination is inside or too close to an obstacle or no-go area');
    expect(siteText('导航拒了: goto 被设备拒绝: 规划失败(no_path)'), 'Navigation refused: no path to the destination');
  });

  test('出发前检查按检查项说人话；battery 按原因', () {
    expect(siteText("起飞前检查未通过: home(地图 'estate-1' 未标原点,先去标一个换电位); battery(算不出)"),
        'Pre-departure check failed: the map has no origin yet; battery too low to start');
    expect(siteText("起飞前检查未通过: home(地图 'm' 未标原点); battery(电量 98.8%,但算不出出发线:此地图的原点不可用)"),
        'Pre-departure check failed: the map has no origin yet; the turn-back battery level cannot be worked out (the map has no usable origin)');
  });

  test('App 上常见的：账号密码错、只读、剩多少、看见人、叫停了', () {
    expect(siteText('账号或密码错误'), 'Wrong account or password');
    expect(siteText('你的账号（只读）不能做这件事'), 'Your account is view-only and cannot do this');
    expect(siteText('剩 52 GB'), '52 GB free');
    expect(siteText('机器人看见人了:1 个人,最近 4.0 m'), 'The robot sees 1 person, nearest 4.0 m');
    expect(siteKnown('临时路线 1 个点'), 'One-off route (1 point)');
    expect(siteText('B 被 gina 叫停了:先点「恢复」再派'), 'B was stopped by gina: tap “Resume” before sending it');
  });

  test('认不出的不显示中文；人写的中文（siteKnown）原样', () {
    expect(siteText('某个没见过的中文原因'), startsWith('Site message in Chinese'));
    expect(siteKnown('临时路线 3 个点'), 'One-off route (3 points)');
    expect(siteKnown('东区巡逻'), '东区巡逻');
  });

  test('中文界面：机器人原话说人话，半角标点换全角', () {
    appLang.value = AppLang.zh;
    expect(siteText('跳过 1 个点(P2):导航拒了: goto 被设备拒绝: 规划失败(goal_blocked):终点在障碍、禁行区里或贴得太近'),
        '跳过 1 个点（P2）：去不了这个点：终点在障碍物、禁行区里或离得太近');
    expect(siteText("起飞前检查未通过: home(地图 'estate-1' 未标原点,先去标一个换电位); battery(电量 99.4%,但算不出出发线:此地图的原点不可用(见 home 项))"),
        '出发前检查未通过：地图还没标原点；算不出返航要留的电量（地图没有可用的原点）');
    expect(zhPunct('不能派(地图 home:3 没确认),10:30 再试'), '不能派（地图 home:3 没确认），10:30 再试');
  });

  test('用户 11-13：布防见人的说明，开了警灯喊话 / 没上装两种都是英文', () {
    expect(siteText('布防中,机器人已开警灯、喊话警告;看现场照片,要驱离就点「就地驱离」'),
        startsWith('The site is armed. The robot has turned on its warning light'));
    expect(siteText('布防中,机器人不在驱离;看现场照片,要驱离就点「就地驱离」'),
        startsWith('The site is armed and the robot is not deterring'));
  });

  test('第 13 轮：排程没跑的说明（新写法、老写法）英文界面整句翻', () {
    expect(siteText('迟了 2 分钟，过了时间窗，这一轮不跑了；之前没派出去：A 站点设成只许手动派，不接排程'),
        '2 min late and past the time window, so this round was skipped. Before that, no robot could be sent: '
        'A is set to manual dispatch only, so schedules do not send it');
    expect(siteText('迟了 31 分钟,按 on_missed=skip;之前没派出去:A 要人监护,不接排程'),
        '31 min late and past the time window, so this round was skipped. Before that, no robot could be sent: '
        'A needs a person present, so schedules do not send it');
    expect(siteText('迟了 5 分钟，过了时间窗，已报警（站点那时没在运行，事后补记）'),
        '5 min late and past the time window, so an alarm was raised; recorded afterwards because the site was not running then');
  });

  test('易用性 build 36 P3-6：看见人那一条后来改的标题翻成英文', () {
    appLang.value = AppLang.en;
    addTearDown(() => appLang.value = AppLang.zh);
    expect(siteText('又看见人了(这一回还没处理完)'), 'Person seen again (this alarm is still open)');
    expect(siteText('看不到了,去向不明,最后在防区 1'), 'Lost sight of the person, last seen at zone 1');
    expect(siteText('人离开防区:北区'), 'Person left the zone: 北区');
  });
}
