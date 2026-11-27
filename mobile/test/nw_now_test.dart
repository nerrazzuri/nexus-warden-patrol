// 「现在」页（App V2 第 2 期）：全场正常 / P1 事件条 / 急停后 / 没有地图；画面、机器人格、小地图、今晚巡逻、
// 设备与运营、上一班留言、最新活动；只读没有按钮；各尺寸不溢出。
import 'package:nexwar_patrol/l10n.dart';
import 'package:nexwar_patrol/net/app_update.dart';
import 'package:nexwar_patrol/net/person_names.dart';
import 'package:nexwar_patrol/ui/nw/nw_now.dart';
import 'package:nexwar_patrol/ui/nw/nw_shell.dart';
import 'package:nexwar_patrol/ui/nw/nw_theme.dart';
import 'package:nexwar_patrol/ui/site_alert_scene.dart';
import 'package:nexwar_patrol/ui/patrol_dispatch.dart' show TodayPatrolList;
import 'package:nexwar_patrol/ui/site_robot.dart';
import 'package:nexwar_patrol/ui/site_video.dart';
import 'package:flutter/material.dart';
import 'package:nexwar_patrol/ui/site_deterrence.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:nexwar_patrol/ui/site_standby.dart';

import 'site_page_test.dart' show FakeApi;
import 'support/fake_site.dart';

void _size(WidgetTester t, [Size size = const Size(390, 844)]) {
  t.view.physicalSize = size * 2;
  t.view.devicePixelRatio = 2.0;
  addTearDown(t.view.reset);
}

Map<String, dynamic> _p1(String key, {String ackedBy = '', String zone = '北区'}) => <String, dynamic>{
      'key': key, 'level': 'P1', 'kind': 'intrusion', 'robot': 'A', 'title': 't', 'detail': '',
      'first_ms': DateTime.now().millisecondsSinceEpoch - 60000, 'last_ms': 1, 'count': 1, 'acked_by': ackedBy,
      'acked_ms': ackedBy.isEmpty ? null : 1, 'resolved_ms': null, 'escalated': 0, 'channel': 'screen',
      'context': <String, dynamic>{'zone': zone},
    };

Map<String, dynamic> _robot(String id, {Map<String, dynamic>? held, num battery = 80}) => <String, dynamic>{
      'robot_id': id, 'fresh': true, 'battery_pct': battery, 'status': <String, dynamic>{'online': true},
      'held': ?held,
    };

Future<void> _show(WidgetTester t, FakeApi api, {VoidCallback? onMap, VoidCallback? onRecords}) async {
  await t.pumpWidget(MaterialApp(
      theme: nwTheme(Brightness.dark),
      home: Scaffold(body: NowPage(api: api, onOpenMap: onMap, onOpenRecords: onRecords))));
  await t.pumpAndSettle();
}

Future<void> _scrollTo(WidgetTester t, Key key) async {
  await t.scrollUntilVisible(find.byKey(key), 300, scrollable: find.byType(Scrollable).first);
  await t.pumpAndSettle();
}

void main() {
  testWidgets('易用性 37 第十一轮 P2：P1 开着时设备与运营不写「没有要处理的」，说 P1 在最上面', (t) async {
    _size(t, const Size(390, 2000));
    final api = FakeApi('guard')..alertRows = [_p1('k1')];
    await _show(t, api);
    await _scrollTo(t, NowPage.opsEmptyKey);
    expect(find.text('没有别的要处理的（P1 报警列在最上面）。'), findsOneWidget);
    await t.pumpWidget(Container());
  });

  testWidgets('易用性 37 第十一轮 P2：上一班留言写人名，不写登录名', (t) async {
    _size(t, const Size(390, 2000));
    addTearDown(() => personNames.value = const {});
    updatePersonNames({'guard1': 'Gina Tan'});
    final api = FakeApi('guard')
      ..alertRows = <Map<String, dynamic>>[]
      ..notes = [<String, dynamic>{'text': '门没锁', 'author': 'guard1', 'at_ms': DateTime.now().millisecondsSinceEpoch}];
    await _show(t, api);
    await _scrollTo(t, NowPage.noteKey);
    expect(find.textContaining('Gina Tan'), findsWidgets);
    expect(find.textContaining('guard1'), findsNothing);
    await t.pumpWidget(Container());
  });

  testWidgets('易用性 37 第十一轮 P2：A 在布防值守 —— 今晚巡逻列出「布防值守 · A」，不写今天没有巡逻', (t) async {
    _size(t, const Size(390, 2000));
    final api = FakeApi('guard')
      ..alertRows = <Map<String, dynamic>>[]
      ..robotsOverride = [
        <String, dynamic>{..._robot('A'), 'status': <String, dynamic>{'online': true,
          'task': <String, dynamic>{'kind': 'patrol', 'state': 'running', 'task_id': 'guard-g1-2'}}},
        _robot('B'),
      ];
    await _show(t, api);
    await _scrollTo(t, NowPage.tonightKey);
    expect(find.byKey(TodayPatrolList.guardKey('A')), findsOneWidget);
    expect(find.byKey(TodayPatrolList.guardKey('B')), findsNothing);
    expect(find.byKey(TodayPatrolList.emptyKey), findsNothing);
    expect(find.textContaining('布防值守 · A'), findsOneWidget);
    await t.pumpWidget(Container());
  });

  // 截图核对 11-15:A 急停着,顶上还写「全场正常」—— 急停、离线、吊销的机器人在,就换成琥珀「要看一下」一条
  testWidgets('有机器人急停 / 离线：不写全场正常，换成「要看一下」一条，列出是哪台', (t) async {
    _size(t, const Size(390, 2000));
    final api = FakeApi('guard')
      ..alertRows = <Map<String, dynamic>>[]
      ..robotsOverride = [
        <String, dynamic>{'robot_id': 'A', 'fresh': true, 'battery_pct': 80,
          'status': <String, dynamic>{'online': true, 'ready': <String, dynamic>{'estop_clear': false}}},
        <String, dynamic>{'robot_id': 'B', 'fresh': false, 'battery_pct': 80, 'status': <String, dynamic>{'online': false}},
        _robot('C'),
      ];
    await _show(t, api);
    expect(find.byKey(NowPage.okKey), findsNothing);
    expect(find.byKey(NowPage.attnKey), findsOneWidget);
    final txt = t.widgetList<Text>(find.descendant(of: find.byKey(NowPage.attnKey), matching: find.byType(Text))).map((w) => w.data).join(' ');
    expect(txt, contains('2'));
    expect(txt, contains('急停'));
    expect(txt, contains('离线'));
    await t.pumpWidget(Container());
  });

  testWidgets('易用性 37 复测 P1-7：默认待命点走不了 —— 不写全场正常，写哪台、要重新标', (t) async {
    _size(t, const Size(390, 2000));
    final api = FakeApi('guard')
      ..alertRows = <Map<String, dynamic>>[]
      ..robotsOverride = [<String, dynamic>{..._robot('A'), 'standby_bad': true}, _robot('B')];
    await _show(t, api);
    expect(find.byKey(NowPage.okKey), findsNothing);
    final txt = t.widgetList<Text>(find.descendant(of: find.byKey(NowPage.attnKey), matching: find.byType(Text))).map((w) => w.data).join(' ');
    expect(txt, contains('待命点走不了'));
    expect(txt, contains('默认待命点'));
    // 第五轮：点这一条直接到 A 的待命点页
    await t.tap(find.byKey(NowPage.attnStandbyKey));
    await t.pumpAndSettle();
    expect(find.byType(SiteStandbyPage), findsOneWidget);
    await t.pumpWidget(Container());
  });

  testWidgets('用户 11-27：没回到原点停在原地、原点离墙太近 —— 不写全场正常，写哪台怎么了', (t) async {
    _size(t, const Size(390, 2000));
    final api = FakeApi('guard')
      ..alertRows = <Map<String, dynamic>>[]
      ..robotsOverride = [
        <String, dynamic>{..._robot('A'), 'stranded': {'key': 'k', 'title': '回原点失败', 'detail': '', 'at_ms': 1}},
        <String, dynamic>{..._robot('B'), 'home_bad': true},
      ];
    await _show(t, api);
    expect(find.byKey(NowPage.okKey), findsNothing);
    final txt = t.widgetList<Text>(find.descendant(of: find.byKey(NowPage.attnKey), matching: find.byType(Text))).map((w) => w.data).join(' ');
    expect(txt, contains('2 台机器人要看一下'));
    expect(txt, contains('没回去，停在原地等'));
    expect(txt, contains('原点离墙太近'));
    await t.pumpWidget(Container());
  });

  testWidgets('外审 App-V2-3 I4：报警结案了驱离还在 —— 不说「全场正常」，一条红框写驱离到第几级，保安点进驱离页', (t) async {
    _size(t, const Size(390, 2000));
    final healthy = [
      for (final r in (siteFixture('site_robots')['robots'] as List).cast<Map<String, dynamic>>())
        <String, dynamic>{
          ...r,
          'status': <String, dynamic>{
            ...(r['status'] as Map).cast<String, dynamic>(),
            'ready': <String, dynamic>{...((r['status'] as Map)['ready'] as Map? ?? {}).cast<String, dynamic>(), 'estop_clear': true},
          },
        },
    ];
    final api = FakeApi('guard')
      ..alertRows = <Map<String, dynamic>>[]
      ..robotsOverride = healthy
      ..deterRows = <Map<String, dynamic>>[
        <String, dynamic>{'robot_id': 'A', 'level': 2, 'auto': true, 'next_in_s': 30, 'started_ms': 1, 'level_ms': 1},
      ];
    await _show(t, api);
    expect(find.byKey(NowPage.okKey), findsNothing);
    expect(find.byKey(NowPage.deterKey('A')), findsOneWidget);
    expect(find.textContaining('A 驱离中'), findsOneWidget);
    await t.tap(find.byKey(NowPage.deterKey('A')));
    await t.pumpAndSettle();
    expect(find.byType(SiteDeterrencePage), findsOneWidget);
    await t.pumpWidget(Container());
  });

  testWidgets('正常：全场正常一条、画面默认不播、每台一格带「控制」、小地图 + 三个入口、下面四段都在', (t) async {
    _size(t, const Size(390, 2000));
    // 真站点夹具里 A 按着急停:正常这一条把急停放开
    final healthy = [
      for (final r in (siteFixture('site_robots')['robots'] as List).cast<Map<String, dynamic>>())
        <String, dynamic>{
          ...r,
          'status': <String, dynamic>{
            ...(r['status'] as Map).cast<String, dynamic>(),
            'ready': <String, dynamic>{...((r['status'] as Map)['ready'] as Map? ?? {}).cast<String, dynamic>(), 'estop_clear': true},
          },
        },
    ];
    final api = FakeApi('guard')
      ..alertRows = <Map<String, dynamic>>[]
      ..robotsOverride = healthy;
    var mapOpened = 0, recordsOpened = 0;
    await _show(t, api, onMap: () => mapOpened++, onRecords: () => recordsOpened++);
    expect(find.byKey(NowPage.okKey), findsOneWidget);
    expect(find.text('全场正常'), findsOneWidget);
    expect(find.byKey(NowPage.playKey), findsOneWidget);
    expect(find.byType(SiteVideo), findsNothing, reason: '默认不拉流');
    expect(find.byKey(NowPage.tileKey('A')), findsOneWidget);
    expect(find.byKey(NowPage.controlKey('A')), findsOneWidget);
    expect(find.byKey(NowPage.mapKey), findsOneWidget);
    for (final k in [NowPage.lookKey, NowPage.routeKey, NowPage.fullMapKey]) {
      await t.tap(find.byKey(k));
    }
    expect(mapOpened, 3);
    for (final k in [NowPage.tonightKey, NowPage.opsKey, NowPage.noteKey, NowPage.activityKey]) {
      expect(find.byKey(k), findsOneWidget, reason: '$k');
    }
    await t.tap(find.byKey(NowPage.recordsKey));
    expect(recordsOpened, 1);
    // 点开画面才拉流，关掉又回到不播
    await t.tap(find.byKey(NowPage.playKey));
    await t.pumpAndSettle();
    expect(find.byType(SiteVideo), findsOneWidget);
    await t.tap(find.byKey(NowPage.closeKey));
    await t.pumpAndSettle();
    expect(find.byType(SiteVideo), findsNothing);
    // 「控制」进这台的页
    await t.tap(find.byKey(NowPage.controlKey('A')));
    await t.pumpAndSettle();
    expect(find.byType(SiteRobotPage), findsOneWidget);
    await t.pumpWidget(Container());
  });

  testWidgets('有 P1：红框事件条（在哪 · 几点、没人接手多久）、「我来处理」发确认、「打开这件事」进现场页；全场正常那一条没了', (t) async {
    _size(t, const Size(390, 1600));
    final api = FakeApi('guard')..alertRows = [_p1('A/intrusion#1')];
    await _show(t, api);
    expect(find.byKey(NowPage.okKey), findsNothing);
    expect(find.byKey(NowPage.p1Key('A/intrusion#1')), findsOneWidget);
    expect(find.textContaining('没人接手'), findsOneWidget);
    expect(find.textContaining('北区'), findsWidgets);
    await t.tap(find.byKey(NowPage.ackKey('A/intrusion#1')));
    await t.pumpAndSettle();
    expect(api.calls, contains('ack A/intrusion#1'));
    await t.tap(find.byKey(NowPage.openKey('A/intrusion#1')));
    await t.pumpAndSettle();
    expect(find.byType(SiteAlertScenePage), findsOneWidget);
    await t.pumpWidget(Container());
  });

  testWidgets('别人接手了：写谁在处理、只剩「打开这件事」；两件 P1 顶上一行「2 件安全事件同时在处理」', (t) async {
    _size(t, const Size(390, 1600));
    final api = FakeApi('guard')..alertRows = [_p1('A/intrusion#1', ackedBy: 'olga'), _p1('A/intrusion#2', zone: '南区')];
    await _show(t, api);
    expect(find.byKey(NowPage.multiKey), findsOneWidget);
    expect(find.textContaining('olga 在处理'), findsOneWidget);
    expect(find.byKey(NowPage.ackKey('A/intrusion#1')), findsNothing);
    expect(find.byKey(NowPage.openKey('A/intrusion#1')), findsOneWidget);
    expect(find.byKey(NowPage.ackKey('A/intrusion#2')), findsOneWidget);
    await t.pumpWidget(Container());
  });

  testWidgets('只读：事件条上没有按钮、只有一句说明；格子上没有「控制」；留言没有「给下一班留言」', (t) async {
    _size(t, const Size(390, 1600));
    final api = FakeApi('viewer')..alertRows = [_p1('A/intrusion#1')];
    await _show(t, api);
    expect(find.byKey(NowPage.viewerNoteKey), findsOneWidget);
    expect(find.byKey(NowPage.ackKey('A/intrusion#1')), findsNothing);
    expect(find.byKey(NowPage.openKey('A/intrusion#1')), findsNothing);
    expect(find.byKey(NowPage.controlKey('A')), findsNothing);
    await _scrollTo(t, NowPage.noteKey);
    expect(find.byKey(NowPage.noteWriteKey), findsNothing);
    await t.pumpWidget(Container());
  });

  testWidgets('全部急停之后：红框卡「N 台机器人已急停」，就地问「确认全部恢复？」，确认后逐台恢复；「先不恢复」收起', (t) async {
    _size(t, const Size(390, 1600));
    final api = FakeApi('guard')
      ..alertRows = <Map<String, dynamic>>[]
      ..robotsOverride = [_robot('A', held: {'by': 'gina'}), _robot('B', held: {'by': 'gina'}, battery: 18)];
    await _show(t, api);
    expect(find.byKey(NowPage.estopCardKey), findsOneWidget);
    expect(find.textContaining('2 台机器人已急停'), findsOneWidget);
    expect(find.byKey(NowPage.okKey), findsNothing);
    expect(find.byType(AlertDialog), findsNothing);
    await t.tap(find.byKey(NowPage.resumeAskKey));
    await t.pumpAndSettle();
    expect(find.text('确认全部恢复？'), findsOneWidget);
    expect(find.byType(AlertDialog), findsNothing, reason: '就地确认，不弹窗');
    await t.tap(find.byKey(NowPage.resumeLaterKey));
    await t.pumpAndSettle();
    expect(find.text('确认全部恢复？'), findsNothing);
    await t.tap(find.byKey(NowPage.resumeAskKey));
    await t.pumpAndSettle();
    await t.tap(find.byKey(NowPage.resumeAllKey));
    await t.pumpAndSettle();
    expect(api.calls, containsAll(['resume A', 'resume B']));
    // 格子：两台、18% 的那台电量是琥珀色
    expect(find.byKey(NowPage.tileKey('B')), findsOneWidget);
    expect(t.widget<Text>(find.text('18%')).style!.color, NwColors.dark.warning);
    await t.pumpWidget(Container());
  });

  testWidgets('还没有地图：管理员一张「站点还没有地图 · 开始建图」；保安只有说明没有按钮', (t) async {
    _size(t, const Size(390, 1600));
    final admin = FakeApi('admin')
      ..alertRows = <Map<String, dynamic>>[]
      ..mapsCount = 0;
    await _show(t, admin);
    expect(find.byKey(NowPage.noMapKey), findsOneWidget);
    expect(find.byKey(NowPage.mapWizardKey), findsOneWidget);
    await t.pumpWidget(Container());
    final guard = FakeApi('guard')
      ..alertRows = <Map<String, dynamic>>[]
      ..mapsCount = 0;
    await _show(t, guard);
    expect(find.byKey(NowPage.noMapKey), findsOneWidget);
    expect(find.byKey(NowPage.mapWizardKey), findsNothing);
    await t.pumpWidget(Container());
  });

  testWidgets('易用性 build 36 P2-2：站点在留守（Stay）时顶栏先写「留守」（以前只写「布防中」，跟网页对不上）', (t) async {
    _size(t);
    final api = FakeApi('guard')
      ..alertRows = <Map<String, dynamic>>[]
      ..modeView = <String, dynamic>{...FakeApi('guard').modeView, 'mode': 'home', 'state': 'armed', 'source': 'manual',
        'until_ms': null, 'next_change_ms': null};
    await t.pumpWidget(MaterialApp(home: NwShell(api: api, title: '庄园', ring: () {}, updater: null)));
    await t.pumpAndSettle();
    expect(find.descendant(of: find.byKey(NwShell.armKey), matching: find.textContaining('留守')), findsOneWidget);
    expect(find.descendant(of: find.byKey(NwShell.armKey), matching: find.textContaining('布防中')), findsOneWidget,
        reason: '留守 · 防区布防中');
  });

  testWidgets('用户 11-27：新站点还没人布过防 —— 顶栏写「还未布防」，不写「布防中」', (t) async {
    _size(t);
    final api = FakeApi('guard')
      ..alertRows = <Map<String, dynamic>>[]
      ..modeView = <String, dynamic>{...FakeApi('guard').modeView, 'mode': 'home', 'state': 'disarmed', 'source': 'manual',
        'until_ms': null, 'next_change_ms': null, 'unset': true, 'set_by': 'site:unset'};
    await t.pumpWidget(MaterialApp(home: NwShell(api: api, title: '庄园', ring: () {}, updater: null)));
    await t.pumpAndSettle();
    expect(find.descendant(of: find.byKey(NwShell.armKey), matching: find.textContaining('还未布防')), findsOneWidget);
    expect(find.descendant(of: find.byKey(NwShell.armKey), matching: find.textContaining('布防中')), findsNothing);
    expect(find.descendant(of: find.byKey(NwShell.armKey), matching: find.textContaining('留守')), findsNothing);
  });

  testWidgets('易用性 37 场景测试：手动布防后顶栏写「到点按时间表」，不写「到 19:00」（像到点撤防）', (t) async {
    _size(t);
    final at = DateTime(2026, 11, 26, 19).millisecondsSinceEpoch;
    final api = FakeApi('guard')
      ..alertRows = <Map<String, dynamic>>[]
      ..modeView = <String, dynamic>{...FakeApi('guard').modeView, 'mode': 'armed', 'state': 'armed', 'source': 'manual',
        'until_ms': null, 'manual_until_ms': at, 'next_change_ms': at};
    await t.pumpWidget(MaterialApp(home: NwShell(api: api, title: '庄园', ring: () {}, updater: null)));
    await t.pumpAndSettle();
    expect(find.descendant(of: find.byKey(NwShell.armKey), matching: find.textContaining('19:00 起按时间表')), findsOneWidget);
    expect(find.descendant(of: find.byKey(NwShell.armKey), matching: find.textContaining('到 19:00')), findsNothing);
  });

  testWidgets('外壳：「现在」段上有没关的 P1 计数；App 有新版本时底部一条，「以后」收起，急停方块让开', (t) async {
    _size(t);
    final api = FakeApi('guard')..alertRows = [_p1('A/intrusion#1')];
    await t.pumpWidget(MaterialApp(home: NwShell(api: api, title: '庄园', ring: () {}, updater: null)));
    await t.pumpAndSettle();
    expect(find.byKey(NwShell.badgeKey), findsOneWidget);
    expect(find.descendant(of: find.byKey(NwShell.nowKey), matching: find.text('1')), findsOneWidget);
    await t.pumpWidget(Container());
    // 有新版本:底条 + 急停方块让开;「以后」收起
    final api2 = FakeApi('guard')
      ..alertRows = <Map<String, dynamic>>[]
      ..appUpdateBody = <String, dynamic>{'available': true, 'version': '2.8.2', 'build': 99};
    await t.pumpWidget(MaterialApp(
        home: NwShell(api: api2, title: '庄园', ring: () {}, updater: (a) => AppUpdater(api: a, platform: 'android'))));
    await t.pumpAndSettle();
    expect(find.byKey(NwShell.updateBarKey), findsOneWidget);
    expect(find.textContaining('2.8.2'), findsOneWidget);
    final bar = t.getRect(find.byKey(NwShell.updateBarKey));
    expect(t.getRect(find.byKey(NwShell.estopKey)).bottom, lessThanOrEqualTo(bar.top));
    await t.tap(find.byKey(NwShell.updateLaterKey));
    await t.pumpAndSettle();
    expect(find.byKey(NwShell.updateBarKey), findsNothing);
    expect(t.getRect(find.byKey(NwShell.estopKey)).bottom, 844 - 16);
    await t.pumpWidget(Container());
  });

  group('版面', () {
    for (final lang in AppLang.values) {
      for (final size in const [Size(390, 844), Size(360, 640), Size(800, 360)]) {
        for (final role in ['guard', 'owner', 'viewer', 'admin']) {
          testWidgets('不溢出 [${lang.name}] ${size.width.toInt()}×${size.height.toInt()} $role：正常、有 P1、急停后', (t) async {
            appLang.value = lang;
            addTearDown(() => appLang.value = AppLang.zh);
            _size(t, size);
            for (final api in [
              FakeApi(role)..alertRows = <Map<String, dynamic>>[],
              FakeApi(role)..alertRows = [_p1('A/intrusion#1'), _p1('A/intrusion#2', ackedBy: 'olga')],
              FakeApi(role)
                ..alertRows = <Map<String, dynamic>>[]
                ..robotsOverride = [_robot('A', held: {'by': 'gina'}), _robot('B', battery: 18), _robot('C')],
            ]) {
              await _show(t, api);
              expect(t.takeException(), isNull);
              final sc = find.byType(Scrollable).first;
              await t.drag(sc, const Offset(0, -2000));
              await t.pumpAndSettle();
              expect(t.takeException(), isNull);
              await t.pumpWidget(Container());
            }
          });
        }
      }
    }
  });
}
