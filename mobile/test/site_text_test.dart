// 手机 App 测试 M05：站点、机器人的中文原文按 App 语言说（跟网页 sitetext.test.ts 同一套例子）。
import 'package:flutter_test/flutter_test.dart';
import 'package:nexwar_patrol/l10n.dart';
import 'package:nexwar_patrol/net/site_text.dart';

void main() {
  setUp(() => appLang.value = AppLang.en);
  tearDown(() => appLang.value = AppLang.zh);

  test('第 9 轮 W9-10：中文界面站点原话的半角标点换全角（前面是数字、字母也换）；报警标题也换', () {
    appLang.value = AppLang.zh;
    expect(zhPunct('已用 86%,剩 30 GB:到 90% 就不接新的巡逻(没传完的不删)'), '已用 86%，剩 30 GB：到 90% 就不接新的巡逻（没传完的不删）');
    expect(alertTitle('schedule_missed', '排程 route-1-2 本轮未执行:到点没有能派的机器人'), '排程 route-1-2 本轮未执行：到点没有能派的机器人');
    expect(zhPunct('10:30 在 home:3'), '10:30 在 home:3');
    expect(siteKnown('从 7 清了 337 处零星噪点(773 格)'), '从第 7 版清了 337 处零星噪点（773 格）');
    expect(siteKnown('一楼夜巡'), '一楼夜巡');
    appLang.value = AppLang.en;
    expect(siteKnown('从 7 清了 337 处零星噪点(773 格)'), 'Noise cleanup of version 7: removed 337 specks (773 cells)');
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
}
