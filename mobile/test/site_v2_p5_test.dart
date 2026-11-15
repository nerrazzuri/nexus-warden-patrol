// App V2 第 5 期：现场各页按稿重排 —— 概况（S-home）、地图与布置（S-layout）、布防与巡逻（S-arming）。
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:nexwar_patrol/l10n.dart';
import 'package:nexwar_patrol/ui/alarm_log.dart';
import 'package:nexwar_patrol/net/site_client.dart' show SiteError;
import 'package:nexwar_patrol/ui/nw/nw_layout_hub.dart';
import 'package:nexwar_patrol/ui/nw/nw_site_dir.dart' show ChangePasswordPage;
import 'package:nexwar_patrol/ui/site_mode.dart';
import 'package:nexwar_patrol/ui/site_releases.dart';
import 'package:nexwar_patrol/ui/site_routes.dart';
import 'package:nexwar_patrol/ui/site_tabs.dart';

import 'site_page_test.dart' show FakeApi;

void main() {
  setUp(() => appLang.value = AppLang.zh);

  testWidgets('概况：今天三格（报警、跑完的巡逻、误报）和机器人一行一台', (t) async {
    final now = DateTime.now().millisecondsSinceEpoch;
    final api = FakeApi('admin')
      ..alertRows = <Map<String, dynamic>>[
        {'key': 'a', 'kind': 'intrusion', 'level': 'P1', 'robot': 'A', 'first_ms': now, 'last_ms': now, 'count': 1},
        {'key': 'b', 'kind': 'intrusion', 'level': 'P2', 'robot': 'A', 'first_ms': now, 'last_ms': now, 'count': 1,
          'resolved_ms': now, 'verdict': 'false_alarm'},
      ];
    await t.binding.setSurfaceSize(const Size(390, 1400));
    addTearDown(() => t.binding.setSurfaceSize(null));
    await t.pumpWidget(MaterialApp(home: AdminHomeTab(api: api, switchTab: (_) {})));
    await t.pumpAndSettle();
    expect(find.text('概况'), findsOneWidget);
    expect(find.descendant(of: find.byKey(const Key('overview-alarms')), matching: find.text('2')), findsOneWidget);
    expect(find.text('报警（1 条没结）'), findsOneWidget);
    expect(find.descendant(of: find.byKey(const Key('overview-false')), matching: find.text('1')), findsOneWidget);
    expect(find.byKey(const Key('overview-robot-A')), findsOneWidget);
  });

  testWidgets('地图与布置：管理员有路线、摄像头、拦截点、地图管理；点路线进路线页；点防区回外壳的全屏地图', (t) async {
    var map = 0;
    await t.binding.setSurfaceSize(const Size(390, 1400));
    addTearDown(() => t.binding.setSurfaceSize(null));
    await t.pumpWidget(MaterialApp(
        home: Builder(
            builder: (c) => TextButton(
                onPressed: () => Navigator.push(c, MaterialPageRoute<void>(
                    builder: (_) => SiteLayoutPage(api: FakeApi('admin'), onRobots: () {}, onMap: () => map++))),
                child: const Text('go')))));
    await t.tap(find.text('go'));
    await t.pumpAndSettle();
    for (final id in ['zones', 'nogo', 'routes', 'standby', 'cameras', 'intercepts', 'maps']) {
      expect(find.byKey(SiteLayoutPage.rowKey(id)), findsOneWidget, reason: id);
    }
    await t.tap(find.byKey(SiteLayoutPage.rowKey('routes')));
    await t.pumpAndSettle();
    expect(find.byType(SiteRoutesPage), findsOneWidget);
    await t.pageBack();
    await t.pumpAndSettle();
    await t.tap(find.byKey(SiteLayoutPage.rowKey('zones')));
    await t.pumpAndSettle();
    expect(map, 1);
    expect(find.byType(SiteLayoutPage), findsNothing, reason: '回到外壳');
  });

  testWidgets('地图与布置：保安没有路线、摄像头、拦截点、地图管理', (t) async {
    await t.pumpWidget(MaterialApp(home: SiteLayoutPage(api: FakeApi('guard'), onRobots: () {}, onMap: () {})));
    await t.pumpAndSettle();
    for (final id in ['routes', 'cameras', 'intercepts', 'maps']) {
      expect(find.byKey(SiteLayoutPage.rowKey(id)), findsNothing, reason: id);
    }
    expect(find.byKey(SiteLayoutPage.rowKey('zones')), findsOneWidget);
  });

  testWidgets('布防与巡逻：布防时间只读汇总（同一时段的几天并一行、例外），三个模式一排等宽；有天气、巡逻日程', (t) async {
    final api = FakeApi('admin')
      ..armingScheduleView = <String, dynamic>{
        'enabled': true,
        'slots': [
          for (final d in [0, 1, 2, 3, 4]) {'zone': '', 'day': d, 'start': '19:00', 'end': '24:00'},
        ],
        'exceptions': [
          {'date': '11-20', 'note': '施工，22:00 布防'},
        ],
      };
    await t.binding.setSurfaceSize(const Size(390, 1600));
    addTearDown(() => t.binding.setSurfaceSize(null));
    await t.pumpWidget(MaterialApp(home: SiteModePage(api: api)));
    await t.pumpAndSettle();
    expect(find.text('布防与巡逻'), findsOneWidget);
    expect(find.text('周一、周二、周三、周四、周五'), findsOneWidget);
    expect(find.text('19:00 → 24:00'), findsOneWidget);
    expect(find.text('施工，22:00 布防'), findsOneWidget);
    final a = t.getRect(find.byKey(SiteModePage.armKey)), h = t.getRect(find.byKey(SiteModePage.homeKey));
    expect(a.top, h.top, reason: '一排');
    expect(a.width, h.width, reason: '等宽');
    expect(find.byKey(SiteModePage.weatherKey), findsOneWidget);
    expect(find.byKey(SiteModePage.schedulesKey), findsOneWidget);
  });

  testWidgets('报警记录：右边写状态（未处理 / 误报 / 确认入侵），顶上筛「未处理」「P1」', (t) async {
    final now = DateTime.now().millisecondsSinceEpoch;
    Map<String, dynamic> row(String key, String level, {String? verdict}) => {
          'key': key, 'kind': 'intrusion', 'level': level, 'robot': 'A', 'first_ms': now, 'last_ms': now, 'count': 1,
          if (verdict != null) ...{'resolved_ms': now, 'verdict': verdict},
        };
    final api = FakeApi('guard')
      ..alertRows = [row('a', 'P1'), row('b', 'P2', verdict: 'false_alarm'), row('c', 'P1', verdict: 'intruder')];
    await t.binding.setSurfaceSize(const Size(390, 1200));
    addTearDown(() => t.binding.setSurfaceSize(null));
    await t.pumpWidget(MaterialApp(home: Scaffold(body: AlarmLogPage(api: api))));
    await t.pumpAndSettle();
    Text st(String k) => t.widget<Text>(find.descendant(of: find.byKey(AlarmLogPage.stateKey(k)), matching: find.byType(Text)));
    expect(st('a').data, '未处理');
    expect(st('b').data, '误报');
    expect(st('c').data, '确认入侵');
    await t.tap(find.byKey(AlarmLogPage.filterKey('open')));
    await t.pumpAndSettle();
    expect(find.byKey(AlarmLogPage.rowKey('a')), findsOneWidget);
    expect(find.byKey(AlarmLogPage.rowKey('b')), findsNothing);
    await t.tap(find.byKey(AlarmLogPage.filterKey('p1')));
    await t.pumpAndSettle();
    expect(find.byKey(AlarmLogPage.rowKey('c')), findsOneWidget);
    expect(find.byKey(AlarmLogPage.rowKey('b')), findsNothing);
  });

  testWidgets('软件升级：站点上的版本写哪台在跑 / 没装；每台机器人四个按钮一排等宽；有手机 App 一段', (t) async {
    await t.binding.setSurfaceSize(const Size(390, 1200));
    addTearDown(() => t.binding.setSurfaceSize(null));
    await t.pumpWidget(MaterialApp(home: SiteReleasesPage(api: FakeApi('admin'))));
    await t.pumpAndSettle();
    expect(find.text('软件升级'), findsOneWidget);
    expect(find.textContaining('没装'), findsOneWidget);
    final w = {
      for (final a in ['install', 'precheck', 'activate', 'rollback']) t.getRect(find.byKey(SiteReleasesPage.actionKey('A', a))),
    };
    expect(w.map((r) => r.width.round()).toSet().length, 1, reason: '等宽');
    expect(w.map((r) => r.top).toSet().length, 1, reason: '一排');
    expect(find.byKey(SiteReleasesPage.appKey), findsOneWidget);
  });

  testWidgets('改密码：两遍不一样不发；旧密码错写原因；改好了说要重新登录、给回去的按钮', (t) async {
    final api = FakeApi('owner');
    await t.pumpWidget(MaterialApp(home: ChangePasswordPage(api: api)));
    await t.enterText(find.byKey(ChangePasswordPage.oldKey), 'a');
    await t.enterText(find.byKey(ChangePasswordPage.newKey), 'b1234567');
    await t.enterText(find.byKey(ChangePasswordPage.againKey), 'b7654321');
    await t.tap(find.byKey(ChangePasswordPage.goKey));
    await t.pumpAndSettle();
    expect(find.text('两次新密码不一样。'), findsOneWidget);
    expect(api.calls.where((c) => c.startsWith('password')), isEmpty);
    api.passwordError = SiteError(400, '旧密码不对');
    await t.enterText(find.byKey(ChangePasswordPage.againKey), 'b1234567');
    await t.tap(find.byKey(ChangePasswordPage.goKey));
    await t.pumpAndSettle();
    expect(find.textContaining('没改成'), findsOneWidget);
    api.passwordError = null;
    await t.tap(find.byKey(ChangePasswordPage.goKey));
    await t.pumpAndSettle();
    expect(api.calls, contains('password a b1234567'));
    expect(find.textContaining('重新登录'), findsWidgets);
    expect(find.byKey(ChangePasswordPage.reloginKey), findsOneWidget);
  });

  testWidgets('经理的概况（稿 S-home-m）：只看；24 小时报警写谁处理、结论；最新交班留言；今天的安排', (t) async {
    final now = DateTime.now().millisecondsSinceEpoch;
    final api = FakeApi('owner')
      ..alertRows = <Map<String, dynamic>>[
        {'key': 'a', 'kind': 'intrusion', 'level': 'P1', 'robot': 'A', 'first_ms': now, 'last_ms': now, 'count': 1,
          'acked_by': 'gina', 'resolved_ms': now, 'verdict': 'intruder'},
        {'key': 'old', 'kind': 'intrusion', 'level': 'P1', 'robot': 'A', 'first_ms': now - 2 * 86400000, 'last_ms': now, 'count': 1},
      ];
    await t.binding.setSurfaceSize(const Size(390, 1400));
    addTearDown(() => t.binding.setSurfaceSize(null));
    await t.pumpWidget(MaterialApp(home: AdminHomeTab(api: api, switchTab: (_) {})));
    await t.pumpAndSettle();
    expect(find.text('只看'), findsOneWidget);
    expect(find.byKey(const Key('overview-alarm-a')), findsOneWidget);
    expect(find.byKey(const Key('overview-alarm-old')), findsNothing, reason: '超过 24 小时');
    expect(find.text('gina · 确认入侵'), findsOneWidget);
    expect(find.byKey(AdminHomeTab.todoKey), findsNothing, reason: '经理不处理待办');
  });
}
