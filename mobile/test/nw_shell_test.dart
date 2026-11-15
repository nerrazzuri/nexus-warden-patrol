// 登录之后的外壳（App V2，2026-11-15）：顶栏 + 「现在 | 现场」两段；「现在」深色、右下角「全部急停」方块；
// 「现场」浅色目录按角色四套，顶栏小红「急停」；机器人列表一直活着（事件流、响铃、登录过期退回）。
import 'package:nexwar_patrol/l10n.dart';
import 'package:nexwar_patrol/net/site_client.dart';
import 'package:nexwar_patrol/store/site_store.dart';
import 'package:nexwar_patrol/ui/alarm_log.dart';
import 'package:nexwar_patrol/ui/nw/nw_now.dart';
import 'package:nexwar_patrol/ui/nw/nw_site_dir.dart';
import 'package:nexwar_patrol/ui/nw/nw_theme.dart';
import 'package:nexwar_patrol/ui/site_page.dart';
import 'package:nexwar_patrol/ui/site_tabs.dart';
import 'package:nexwar_patrol/ui/widget/alarm_widgets.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'site_page_test.dart' show FakeApi;
import 'support/fake_site.dart';
import 'support/shell_nav.dart';

void _size(WidgetTester t, [Size size = const Size(390, 844)]) {
  t.view.physicalSize = size * 2;
  t.view.devicePixelRatio = 2.0;
  addTearDown(t.view.reset);
}

Future<void> _show(WidgetTester t, FakeApi api, {ThemeData? theme, void Function()? ring}) async {
  await t.pumpWidget(MaterialApp(theme: theme, home: NwShell(api: api, title: '庄园', ring: ring ?? () {}, updater: null)));
  await t.pumpAndSettle();
}

Future<void> _tap(WidgetTester t, Key key) async {
  await t.tap(find.byKey(key));
  await t.pumpAndSettle();
}

/// 目录是个列表：滚到那一行再点。
Future<void> _dir(WidgetTester t, SiteDest d) => openDir(t, d);

/// 狗列表的那个 State：切层前后得是同一个（没被拆了重建）。
State _robotsState(WidgetTester t) => t.state(find.byType(SiteRobotsPage, skipOffstage: false));

Color _bg(WidgetTester t) => t.widget<Scaffold>(find.byType(Scaffold).first).backgroundColor!;

void main() {
  group('两层', () {
    testWidgets('进来是「现在」：深色、顶栏站点名 + 布防状态 + 时钟、值班页、右下角「全部急停」；没有底部导航', (t) async {
      _size(t);
      await _show(t, FakeApi('admin'));
      expect(find.byKey(NwShell.nowKey), findsOneWidget);
      expect(find.byKey(NwShell.siteKey), findsOneWidget);
      expect(find.byType(NowPage), findsOneWidget);
      expect(find.byKey(NwShell.estopKey), findsOneWidget, reason: '「现在」的拇指区方块');
      expect(find.byKey(NwShell.estopSmallKey), findsNothing);
      expect(find.byKey(NwShell.clockKey), findsOneWidget);
      expect(find.text('庄园'), findsWidgets);
      expect(find.textContaining('临时撤防'), findsWidgets, reason: '顶栏布防那一行按 /api/mode 说话');
      expect(_bg(t), NwColors.dark.bg, reason: '「现在」永远深色');
      expect(find.byType(BottomNavigationBar), findsNothing);
      expect(find.byKey(const Key('open-dogs')), findsNothing, reason: '老五栏删了');
      final sq = t.getRect(find.byKey(NwShell.estopKey));
      expect(sq.right, 390 - 16);
      expect(sq.bottom, 844 - 16);
      expect(sq.width, greaterThanOrEqualTo(80));
      await t.pumpWidget(Container());
    });

    testWidgets('外审 App-V2-1 #7：只读账号哪一层都没有急停（方块、小红按钮都不给）', (t) async {
      _size(t);
      await _show(t, FakeApi('viewer'));
      expect(find.byKey(NwShell.estopKey), findsNothing);
      await _tap(t, NwShell.siteKey);
      expect(find.byKey(NwShell.estopSmallKey), findsNothing);
      await t.pumpWidget(Container());
    });

    testWidgets('切到「现场」：浅色目录、顶栏换成小红「急停」、方块没了；再切回来', (t) async {
      _size(t);
      await _show(t, FakeApi('admin'));
      await _tap(t, NwShell.siteKey);
      expect(find.byType(SiteDirectory), findsOneWidget);
      expect(find.byType(NowPage), findsNothing);
      expect(find.byKey(NwShell.estopSmallKey), findsOneWidget);
      expect(find.byKey(NwShell.estopKey), findsNothing);
      expect(_bg(t), NwColors.light.bg, reason: '「现场」浅色');
      await _tap(t, NwShell.nowKey);
      expect(find.byType(NowPage), findsOneWidget);
      expect(_bg(t), NwColors.dark.bg);
      await t.pumpWidget(Container());
    });

    testWidgets('目录按角色四套：没有的项不列（不放灰的）', (t) async {
      _size(t, const Size(390, 1600));
      const all = SiteDest.values;
      final want = <String, Set<SiteDest>>{
        'admin': all.toSet(),
        // 稿 S-mgr:日常(概况、机器人)、现场(布防与巡逻)、记录、本机
        'owner': {SiteDest.overview, SiteDest.robots, SiteDest.arming, SiteDest.alarms, SiteDest.events,
          SiteDest.recordings, SiteDest.runs, SiteDest.notes, SiteDest.settings, SiteDest.help, SiteDest.report},
        // 稿 S-guard / S-viewer:没有「日常」,机器人和地图在「现在」页上;
        // 保安多一行「布防」(外审 App-V2-2 N2:保安能布防、临时撤防,稿上没画入口)
        'guard': {SiteDest.arming, SiteDest.alarms, SiteDest.events, SiteDest.recordings, SiteDest.runs,
          SiteDest.notes, SiteDest.settings, SiteDest.help, SiteDest.report},
        'viewer': {SiteDest.alarms, SiteDest.recordings, SiteDest.runs, SiteDest.settings,
          SiteDest.help, SiteDest.report},
      };
      for (final e in want.entries) {
        await _show(t, FakeApi(e.key));
        await _tap(t, NwShell.siteKey);
        for (final d in all) {
          expect(find.byKey(SiteDirectory.itemKey(d)), e.value.contains(d) ? findsOneWidget : findsNothing,
              reason: '${e.key} ${d.name}');
        }
        expect(find.byKey(SiteDirectory.leaveKey), findsOneWidget, reason: '${e.key} 底部退出站点');
        await t.pumpWidget(Container());
      }
    });

    testWidgets('目录里点「机器人」切到机器人列表（带返回）；点「报警记录」推老页面', (t) async {
      _size(t);
      await _show(t, FakeApi('guard'));
      await _tap(t, NwShell.siteKey);
      await _dir(t, SiteDest.alarms);
      expect(find.byType(AlarmLogPage), findsOneWidget);
      await t.pageBack();
      await t.pumpAndSettle();
      expect(find.byType(SiteDirectory), findsOneWidget);
      await t.pumpWidget(Container());

      await _show(t, FakeApi('admin'));
      await _tap(t, NwShell.siteKey);
      await _dir(t, SiteDest.robots);
      expect(find.byKey(const Key('robot-A')), findsOneWidget);
      expect(find.byKey(NwShell.backKey), findsOneWidget);
      expect(find.byKey(NwShell.nowKey), findsNothing, reason: '子层不显示两段开关');
      await _tap(t, NwShell.backKey);
      expect(find.byType(SiteDirectory), findsOneWidget);
      await t.pumpWidget(Container());
    });
  });

  group('全部急停', () {
    testWidgets('方块按了先问一遍（英文 E-STOP ALL），确认后对每台在线的机器人发急停', (t) async {
      _size(t);
      appLang.value = AppLang.en;
      addTearDown(() => appLang.value = AppLang.zh);
      final api = FakeApi('guard');
      await _show(t, api);
      await _tap(t, NwShell.estopKey);
      expect(find.textContaining('E-stop all 1 robots now?'), findsOneWidget);
      expect(find.text('Stop all'), findsNothing, reason: '术语跟网页一致');
      await _tap(t, StopAllButton.confirmKey);
      expect(api.calls, contains('halt A'));
      await t.pumpWidget(Container());
    });

    testWidgets('「现场」顶栏的小急停走同一套', (t) async {
      _size(t);
      final api = FakeApi('owner');
      await _show(t, api);
      await _tap(t, NwShell.siteKey);
      await _tap(t, NwShell.estopSmallKey);
      expect(find.textContaining('全部 1 台机器人立即急停'), findsOneWidget);
      await _tap(t, StopAllButton.confirmKey);
      expect(api.calls, contains('halt A'));
      await t.pumpWidget(Container());
    });
  });

  group('机器人列表身上的站点级逻辑切层不断', () {
    testWidgets('在「现场」，事件来了照样刷新机器人列表；进机器人列表看到的是新的；它一直是同一个', (t) async {
      _size(t);
      final api = FakeApi('admin');
      await _show(t, api);
      final state = _robotsState(t);
      await _tap(t, NwShell.siteKey);
      final before = api.robotsCalls;
      api.robotsOverride = [
        <String, dynamic>{'robot_id': 'Z9', 'fresh': true, 'status': <String, dynamic>{'online': true}}
      ];
      api.sse.add(<String, dynamic>{'kind': 'robot', 'robot_id': 'Z9'});
      await t.pump();
      await t.pump(const Duration(milliseconds: 600)); // 狗列表半秒内的事件合成一次刷新
      await t.pump();
      expect(api.robotsCalls, greaterThan(before), reason: '不在眼前也收到了事件、重新读了机器人列表');
      expect(find.byKey(const Key('robot-Z9')), findsNothing, reason: '人还在目录');
      await _dir(t, SiteDest.robots);
      expect(find.byKey(const Key('robot-Z9')), findsOneWidget);
      expect(find.byKey(const Key('robot-A')), findsNothing);
      expect(_robotsState(t), same(state), reason: '没被拆了重建：订阅、响铃的计时器都还是原来那一份');
      expect(find.byKey(const Key('live-lost')), findsNothing, reason: '实时更新一直连着');
      await t.pumpWidget(Container());
    });

    testWidgets('人在「现场」：升到声音档的告警照样响铃、照样提示', (t) async {
      _size(t);
      final api = FakeApi('guard');
      var rang = 0;
      await _show(t, api, ring: () => rang++);
      await _tap(t, NwShell.siteKey);
      final f = siteFixture('site_alert_frame');
      api.sse.add(<String, dynamic>{
        ...f,
        'alert': <String, dynamic>{...(f['alert'] as Map<String, dynamic>), 'channel': 'sound'}
      });
      await t.pump();
      expect(rang, 1);
      await t.pump(const Duration(milliseconds: 100));
      expect(find.textContaining('无人确认'), findsOneWidget, reason: '提示条在外壳上，哪一层都看得见');
      expect(find.byType(SiteDirectory), findsOneWidget);
      await t.pumpWidget(Container());
    });

    testWidgets('登录过期（401）：不管在哪一层，整个外壳退回上一页并说明', (t) async {
      _size(t);
      final api = FakeApi('guard');
      String? why;
      await t.pumpWidget(MaterialApp(
          home: Builder(
              builder: (c) => TextButton(
                  onPressed: () async => why = await Navigator.push<String>(
                      c, MaterialPageRoute<String>(builder: (_) => NwShell(api: api, ring: () {}, updater: null))),
                  child: const Text('进')))));
      await t.tap(find.text('进'));
      await t.pumpAndSettle();
      await _tap(t, NwShell.siteKey);
      expect(find.byType(NwShell), findsOneWidget);
      api.robotsError = const SiteError(401, '没登录或登录已过期');
      api.sse.add(<String, dynamic>{'kind': 'robot'});
      await t.pump();
      await t.pump(const Duration(milliseconds: 600));
      await t.pumpAndSettle();
      expect(find.byType(NwShell), findsNothing);
      expect(why, contains('重新登录'));
      expect(find.text('进'), findsOneWidget);
    });

    testWidgets('手机 App 测试 M17：有 P1 开着，「现场」和机器人列表顶上都有红条，点了回「现在」', (t) async {
      _size(t);
      final api = FakeApi('admin');
      await t.pumpWidget(MaterialApp(home: NwShell(api: api, ring: () {}, updater: null)));
      await t.pumpAndSettle();
      expect(find.byKey(NwShell.p1BarKey), findsNothing, reason: '「现在」自己有 P1 卡');
      api.sse.add(<String, dynamic>{'kind': 'alert', 'alert': <String, dynamic>{
        'key': 'A/intrusion#9', 'level': 'P1', 'kind': 'intrusion', 'robot': 'A', 'title': 't', 'detail': '',
        'first_ms': 1, 'last_ms': 1, 'count': 1, 'acked_by': '', 'acked_ms': null, 'resolved_ms': null,
        'escalated': 0, 'channel': 'screen'}});
      await t.pump();
      await _tap(t, NwShell.siteKey);
      expect(find.byKey(NwShell.p1BarKey), findsOneWidget);
      await _dir(t, SiteDest.robots);
      expect(find.byKey(NwShell.p1BarKey), findsOneWidget);
      await t.tap(find.byKey(NwShell.p1BarKey));
      await t.pumpAndSettle();
      expect(find.byType(NowPage), findsOneWidget);
      expect(find.byKey(NwShell.p1BarKey), findsNothing);
      await t.pumpWidget(Container());
    });

    testWidgets('手机 App 测试 M01：系统返回键不退出登录——机器人列表回目录、目录回「现在」、「现在」退到后台', (t) async {
      _size(t);
      final api = FakeApi('admin');
      var toBack = 0;
      await t.pumpWidget(MaterialApp(
          home: Builder(
              builder: (c) => TextButton(
                  onPressed: () => Navigator.push<String>(
                      c,
                      MaterialPageRoute<String>(
                          builder: (_) => NwShell(api: api, ring: () {}, updater: null, toBackground: () async => toBack++))),
                  child: const Text('进')))));
      await t.tap(find.text('进'));
      await t.pumpAndSettle();
      expect(find.byType(BackButton), findsNothing);
      await _tap(t, NwShell.siteKey);
      await _dir(t, SiteDest.robots);
      await t.binding.handlePopRoute();
      await t.pumpAndSettle();
      expect(find.byType(SiteDirectory), findsOneWidget, reason: '机器人列表按返回回目录');
      await t.binding.handlePopRoute();
      await t.pumpAndSettle();
      expect(find.byType(NowPage), findsOneWidget, reason: '目录按返回回「现在」');
      expect(toBack, 0);
      await t.binding.handlePopRoute();
      await t.pumpAndSettle();
      expect(find.byType(NwShell), findsOneWidget);
      expect(toBack, 1, reason: '「现在」按返回：退到后台');
      expect(api.pushLog, isNot(contains('logout')));
    });

    testWidgets('从站点列表登录进来就是外壳；目录底部「退出站点」确认之后才离开（注销）', (t) async {
      _size(t, const Size(400, 1400));
      final api = FakeApi('guard');
      final store = MemorySiteStore([
        SiteEntry(name: '庄园', url: 'https://h:1', fingerprint: 'ab' * 32, username: 'gina')
      ]);
      await t.pumpWidget(MaterialApp(home: SiteListPage(store: store, apiFactory: (_) => api)));
      await t.pumpAndSettle();
      await t.tap(find.text('庄园'));
      await t.pumpAndSettle();
      await t.enterText(find.byKey(const Key('site-password')), 'pw');
      await t.tap(find.text('登录'));
      await t.pumpAndSettle();
      expect(find.byType(NwShell), findsOneWidget);
      expect(find.text('庄园'), findsWidgets, reason: '顶栏印站点名');
      await _tap(t, NwShell.siteKey);
      await t.ensureVisible(find.byKey(SiteDirectory.leaveKey));
      await t.tap(find.byKey(SiteDirectory.leaveKey));
      await t.pumpAndSettle();
      await t.tap(find.text('取消'));
      await t.pumpAndSettle();
      expect(find.byType(NwShell), findsOneWidget, reason: '取消就留下');
      await t.ensureVisible(find.byKey(SiteDirectory.leaveKey));
      await t.tap(find.byKey(SiteDirectory.leaveKey));
      await t.pumpAndSettle();
      expect(find.textContaining('收不到这个站点的报警'), findsOneWidget);
      await t.tap(find.byKey(leaveConfirmKey));
      await t.pumpAndSettle();
      expect(find.byType(NwShell), findsNothing);
      expect(api.pushLog, contains('logout'));
    });
  });

  group('版面', () {
    for (final th in <String, ThemeData?>{'light': nwTheme(Brightness.light), 'no theme': null}.entries) {
      for (final lang in AppLang.values) {
        for (final size in const [Size(390, 844), Size(360, 640), Size(800, 360)]) {
          for (final role in ['admin', 'owner', 'guard']) {
            testWidgets(
                '不溢出 [${th.key}] [${lang.name}] ${size.width.toInt()}×${size.height.toInt()} $role：现在、现场、机器人',
                (t) async {
              appLang.value = lang;
              addTearDown(() => appLang.value = AppLang.zh);
              _size(t, size);
              await _show(t, FakeApi(role), theme: th.value);
              expect(t.takeException(), isNull);
              expect(_bg(t), NwColors.dark.bg, reason: '外面给什么主题，「现在」都深色');
              await _tap(t, NwShell.siteKey);
              expect(t.takeException(), isNull, reason: 'site');
              expect(_bg(t), NwColors.light.bg);
              if (role == 'guard') {
                // 保安没有机器人列表:看地图层(「现在」小地图进的那一层)
                await openNowMap(t);
                expect(t.takeException(), isNull, reason: 'map');
              } else {
                await _dir(t, SiteDest.robots);
                expect(t.takeException(), isNull, reason: 'robots');
              }
              await _tap(t, NwShell.backKey);
              await _tap(t, NwShell.nowKey);
              expect(t.takeException(), isNull, reason: 'now again');
              await t.pumpWidget(Container());
            });
          }
        }
      }
    }
  });
}
