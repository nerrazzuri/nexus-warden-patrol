// 2026-10-14 重做的第四批：地图栏（当前这张图 + 图上的狗）、记录栏的数值格和巡检卡、管理栏（站点状态、
// 版本格子、诊断包、几个入口）。各页原来的行为测试还在各自的文件里；这里只测这一批新加的东西。
import 'dart:typed_data';

import 'package:nexwar_patrol/l10n.dart';
import 'package:nexwar_patrol/net/site_client.dart';
import 'package:nexwar_patrol/ui/nw/nw_shell.dart';
import 'package:nexwar_patrol/ui/nw/nw_theme.dart';
import 'package:nexwar_patrol/ui/nw/nw_widgets.dart';
import 'package:nexwar_patrol/ui/site_cameras.dart';
import 'package:nexwar_patrol/ui/site_health.dart';
import 'package:nexwar_patrol/ui/site_intercepts.dart';
import 'package:nexwar_patrol/ui/site_logs.dart';
import 'package:nexwar_patrol/ui/site_mapping.dart';
import 'package:nexwar_patrol/ui/site_maps.dart';
import 'package:nexwar_patrol/ui/alarm_log.dart';
import 'package:nexwar_patrol/ui/site_page.dart' show SiteIncidentsPage, SiteRobotPage, SiteSchedulePage;
import 'package:nexwar_patrol/ui/site_tabs.dart';
import 'package:nexwar_patrol/ui/site_releases.dart';
import 'package:nexwar_patrol/ui/site_runs.dart';
import 'package:nexwar_patrol/ui/site_weather.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'site_page_test.dart' show FakeApi, onePixelPng;
import 'support/fake_site.dart';
import 'support/shell_nav.dart';
import 'package:nexwar_patrol/ui/nw/nw_site_dir.dart';

void _size(WidgetTester t, [Size size = const Size(390, 844)]) {
  t.view.physicalSize = size * 2;
  t.view.devicePixelRatio = 2.0;
  addTearDown(t.view.reset);
}

/// 能换掉地图目录、巡检记录的假站点。
class _Api extends FakeApi {
  _Api(super.role);
  Map<String, dynamic>? mapsBody;
  SiteError? mapsError;
  List<Map<String, dynamic>>? runRows;

  @override
  Future<Map<String, dynamic>> maps() async {
    if (mapsError != null) throw mapsError!;
    return mapsBody ?? await super.maps();
  }

  @override
  Future<List<Map<String, dynamic>>> runs({String? robotId, String? mission}) async =>
      runRows ?? await super.runs(robotId: robotId, mission: mission);
}

/// 夹具里的那只狗，改成报着 [version] 这一版图、站在 ([x], [y])。
List<Map<String, dynamic>> _robotsOn(String version, {double x = 1.0, double y = 2.0, bool online = true}) => [
      for (final r in (siteFixture('site_robots')['robots'] as List).cast<Map<String, dynamic>>())
        <String, dynamic>{
          ...r,
          'loc': <String, dynamic>{
            ...(r['loc'] as Map).cast<String, dynamic>(),
            'pose': <String, dynamic>{'x': x, 'y': y, 'yaw': 0.0},
          },
          'status': <String, dynamic>{...(r['status'] as Map).cast<String, dynamic>(), 'online': online},
          'capabilities': <String, dynamic>{
            ...(r['capabilities'] as Map).cast<String, dynamic>(),
            'tasks': <String, dynamic>{
              ...((r['capabilities'] as Map)['tasks'] as Map).cast<String, dynamic>(),
              'patrol': <String, dynamic>{'autonomy': 'autonomous', 'map_id': 'estate-1', 'map_version': version},
            },
          },
        },
    ];

/// 当地时间 → 站点目录名那种 UTC 时刻（`20260925T010000Z`）。
String _stamp(DateTime local) {
  final u = local.toUtc();
  String two(int n) => n.toString().padLeft(2, '0');
  return '${u.year}${two(u.month)}${two(u.day)}T${two(u.hour)}${two(u.minute)}${two(u.second)}Z';
}

Map<String, dynamic> _run(int id, DateTime when, {int abnormal = 0, int normal = 1}) => <String, dynamic>{
      'id': id, 'mission': 'loop-$id', 'robot_id': 'A', 'stamp': _stamp(when), 'photos': abnormal + normal,
      'finished': true, 'judged_ms': 1, 'reviewed': 0,
      'verdicts': <String, dynamic>{if (abnormal > 0) 'abnormal': abnormal, if (normal > 0) 'normal': normal},
    };

Future<void> _pump(WidgetTester t, Widget page, {ThemeData? theme}) async {
  await t.pumpWidget(MaterialApp(theme: theme, home: Scaffold(body: page)));
  await t.pumpAndSettle();
}

void main() {
  group('地图栏', () {
    testWidgets('机器人报着的那张图当主体：画布、图上的机器人、图例、底下这张图上的机器人；右上进地图列表', (t) async {
      _size(t);
      // 第 9 轮 W8-04：几圈的巡逻在机器人列表里写第几圈
      final api = _Api('guard')
        ..robotsOverride = [
          for (final r in _robotsOn('8')) <String, dynamic>{...r, 'lap': <String, dynamic>{'n': 2, 'of': 3}}
        ];
      await _pump(t, SiteMapTab(api: api));
      expect(api.calls, containsAll(['mapPreview estate-1:8', 'mapPreviewPng estate-1:8']));
      expect(find.text('estate-1 · 第 8 版'), findsOneWidget);
      expect(find.byKey(SiteMapTab.canvasKey), findsOneWidget);
      expect(find.byType(InteractiveViewer), findsOneWidget, reason: '能缩放');
      // 待命点、区域还是原来那几个 painter 画的
      final standby = t.widget<CustomPaint>(find.byKey(SiteMapTab.standbyKey)).painter! as StandbyPainter;
      expect(standby.pixels.length, 1);
      expect(t.widget<CustomPaint>(find.byKey(SiteMapTab.zonesKey)).painter, isA<ZonesPainter>());
      // 狗：(1, 2) m；左边缘 x = -10、上边缘 y = 5、一像素 0.1 m → 图上 (110, 30)，按画出来的大小缩放
      final canvas = t.getRect(find.byKey(SiteMapTab.canvasKey));
      final k = canvas.width / 200;
      final marker = t.getRect(find.byKey(SiteMapTab.markerKey('A')));
      expect((marker.center - canvas.topLeft - const Offset(110, 30) * k).distance, lessThan(0.5));
      expect(find.byKey(SiteMapTab.legendKey), findsOneWidget);
      expect(find.descendant(of: find.byKey(SiteMapTab.legendKey), matching: find.text('待命点')), findsOneWidget);
      expect(find.descendant(of: find.byKey(SiteMapTab.legendKey), matching: find.text('禁行区')), findsNothing,
          reason: '这张图上没画的不列');
      expect(find.byKey(SiteMapTab.robotKey('A')), findsOneWidget);
      expect(find.descendant(of: find.byKey(SiteMapTab.robotKey('A')), matching: find.text('在线')), findsOneWidget);
      expect(find.descendant(of: find.byKey(SiteMapTab.robotKey('A')), matching: find.textContaining('第 2 / 3 圈 · 在 (1.0, 2.0) m')),
          findsOneWidget);
      await t.tap(find.byKey(SiteMapTab.listKey));
      await t.pumpAndSettle();
      expect(find.byType(SiteMapsPage), findsOneWidget);
      await t.pumpWidget(Container());
    });

    testWidgets('横屏 800×360：画布高过 150；图例、缩放按钮都在画布那一块里', (t) async {
      _size(t, const Size(800, 360));
      final api = _Api('admin')..robotsOverride = _robotsOn('8');
      await t.pumpWidget(MaterialApp(home: NwShell(api: api, ring: () {})));
      await t.pumpAndSettle();
      await openSiteDir(t, SiteDest.layout);
      expect(t.takeException(), isNull);
      expect(t.getRect(find.byKey(SiteMapTab.canvasKey)).height, greaterThan(150), reason: '图要占住大半屏');
      for (final key in [SiteMapTab.legendKey, SiteMapTab.zoomInKey, SiteMapTab.zoomOutKey, SiteMapTab.recenterKey]) {
        final r = t.getRect(find.byKey(key));
        expect(r.bottom, lessThanOrEqualTo(360), reason: '$key');
        expect(r.top, greaterThanOrEqualTo(0), reason: '$key');
      }
      await t.pumpWidget(Container());
    });

    testWidgets('缩放、回正：按钮动的是画布的变换', (t) async {
      _size(t);
      final api = _Api('guard')..robotsOverride = _robotsOn('8');
      await _pump(t, SiteMapTab(api: api));
      double scale() => t
          .widget<InteractiveViewer>(find.byType(InteractiveViewer))
          .transformationController!
          .value
          .getMaxScaleOnAxis();
      expect(scale(), 1.0);
      await t.tap(find.byKey(SiteMapTab.zoomInKey));
      await t.pump();
      expect(scale(), greaterThan(1.2));
      await t.tap(find.byKey(SiteMapTab.zoomOutKey));
      await t.pump();
      expect(scale(), closeTo(1.0, 1e-6));
      await t.tap(find.byKey(SiteMapTab.zoomOutKey));
      await t.pump();
      expect(scale(), closeTo(1.0, 1e-6), reason: '不缩到比整张图还小');
      await t.tap(find.byKey(SiteMapTab.zoomInKey));
      await t.tap(find.byKey(SiteMapTab.zoomInKey));
      await t.pump();
      await t.tap(find.byKey(SiteMapTab.recenterKey));
      await t.pump();
      expect(scale(), 1.0);
      await t.pumpWidget(Container());
    });

    testWidgets('机器人报的图站点上没有：摆站点上最新的那张，说清楚没有机器人在这张图上，不把机器人画上去', (t) async {
      _size(t);
      final api = _Api('guard'); // 夹具里的狗报的是 estate-1:7，站点上只有 estate-1:8
      await _pump(t, SiteMapTab(api: api));
      expect(find.text('estate-1 · 第 8 版'), findsOneWidget);
      expect(find.byKey(SiteMapTab.canvasKey), findsOneWidget);
      expect(find.byKey(SiteMapTab.markerKey('A')), findsNothing, reason: '坐标系不是这张图的');
      expect(find.textContaining('此地图上没有机器人'), findsOneWidget);
      expect(find.descendant(of: find.byKey(SiteMapTab.robotKey('A')), matching: find.textContaining('estate-1:7')),
          findsOneWidget, reason: '它在哪张图上照实写');
      await t.pumpWidget(Container());
    });

    testWidgets('站点上一张图都没有：空状态说清楚，给去地图列表的路；不是一片空白', (t) async {
      _size(t);
      final api = _Api('admin')..mapsBody = <String, dynamic>{'maps': <dynamic>[], 'bags': <dynamic>[]};
      await _pump(t, SiteMapTab(api: api));
      expect(find.byKey(SiteMapTab.emptyKey), findsOneWidget);
      expect(find.text('站点暂无地图'), findsOneWidget);
      expect(find.byKey(SiteMapTab.canvasKey), findsNothing);
      expect(api.calls.where((c) => c.startsWith('mapPreview')), isEmpty);
      expect(find.byKey(SiteMapTab.listKey), findsOneWidget);
      await t.pumpWidget(Container());
    });

    testWidgets('地图目录拿不到、这张图没有栅格：照实说，不画成「还没有图」；刷新再问一次', (t) async {
      _size(t);
      final api = _Api('guard')..mapsError = const SiteError(502, '站点忙');
      await _pump(t, SiteMapTab(api: api));
      expect(find.textContaining('无法加载地图目录'), findsOneWidget);
      expect(find.byKey(SiteMapTab.emptyKey), findsNothing);
      expect(find.text('站点暂无地图'), findsNothing);
      api
        ..mapsError = null
        ..previewMissing = true;
      await t.tap(find.byKey(SiteMapTab.refreshKey));
      await t.pumpAndSettle();
      expect(find.textContaining('地图目录拿不到'), findsNothing);
      expect(find.textContaining('无法预览'), findsOneWidget);
      expect(find.textContaining('没有栅格'), findsOneWidget);
      expect(find.byKey(SiteMapTab.canvasKey), findsNothing);
      expect(find.byKey(SiteMapTab.robotKey('A')), findsOneWidget, reason: '机器人的列表照样看');
      api.previewMissing = false;
      await t.tap(find.byKey(SiteMapTab.refreshKey));
      await t.pumpAndSettle();
      expect(find.byKey(SiteMapTab.canvasKey), findsOneWidget);
      await t.pumpWidget(Container());
    });

    testWidgets('底下的机器人点了进单机器人页', (t) async {
      _size(t);
      final api = _Api('guard')..robotsOverride = _robotsOn('8', online: false);
      await _pump(t, SiteMapTab(api: api));
      expect(find.descendant(of: find.byKey(SiteMapTab.robotKey('A')), matching: find.text('离线')), findsOneWidget);
      await t.tap(find.byKey(SiteMapTab.robotKey('A')));
      await t.pump();
      await t.pump(const Duration(milliseconds: 400));
      expect(find.byType(SiteRobotPage), findsOneWidget);
      await t.pumpWidget(Container());
    });

    testWidgets('图例、图上的机器人在浅色深色下都压在自己的底上（不靠栅格图的颜色）', (t) async {
      _size(t);
      for (final b in Brightness.values) {
        final c = b == Brightness.dark ? NwColors.dark : NwColors.light;
        final api = _Api('guard')..robotsOverride = _robotsOn('8');
        await _pump(t, SiteMapTab(key: UniqueKey(), api: api), theme: nwTheme(b));
        final legend = t.widget<Material>(find.byKey(SiteMapTab.legendKey));
        expect(legend.color, c.surface);
        final marker = t.widget<Container>(find.byKey(SiteMapTab.markerKey('A')));
        expect((marker.decoration! as BoxDecoration).color, c.surface);
        final label = t.widget<Text>(
            find.descendant(of: find.byKey(SiteMapTab.markerKey('A')), matching: find.byType(Text)));
        expect(label.style!.color, c.text);
        expect(label.style!.fontSize, greaterThanOrEqualTo(12));
      }
      await t.pumpWidget(Container());
    });
  });

  group('记录栏', () {
    test('数值格的数：今天几趟、其中几趟有异常（按当地日期）', () {
      final now = DateTime(2026, 9, 25, 12);
      final rows = [
        _run(1, DateTime(2026, 9, 25, 0, 5)),
        _run(2, DateTime(2026, 9, 25, 9), abnormal: 2),
        _run(3, DateTime(2026, 9, 25, 11, 59), abnormal: 1, normal: 0),
        _run(4, DateTime(2026, 9, 24, 23, 59), abnormal: 1),
        <String, dynamic>{'id': 5, 'stamp': 'not-a-stamp', 'verdicts': <String, dynamic>{'abnormal': 1}},
      ];
      expect(runStats(rows, now), (today: 3, anomalies: 2));
      expect(runStats(const [], now), (today: 0, anomalies: 0));
    });

    testWidgets('分段今天 / 异常 / 全部 + 一趟一行；有异常的标出来；点一行进这一趟', (t) async {
      _size(t);
      final api = _Api('guard')
        ..runRows = [
          _run(1, DateTime(2026, 9, 25, 8)),
          _run(2, DateTime(2026, 9, 25, 9), abnormal: 1),
          _run(3, DateTime(2026, 9, 24, 9), abnormal: 1),
        ];
      await _pump(t, SiteRunsPage(api: api, embedded: true, now: () => DateTime(2026, 9, 25, 12)));
      expect(find.byType(AppBar), findsNothing, reason: '嵌在记录栏里：页头是记录栏的');
      // App V2 稿 S-runs：分段「今天 2 / 异常 1 / 全部」，默认看今天
      expect(t.widget<Text>(find.byKey(SiteRunsPage.todayKey)).data, '今天 2');
      expect(t.widget<Text>(find.byKey(SiteRunsPage.anomalyKey)).data, '异常 1');
      expect(t.widget<Text>(find.byKey(SiteRunsPage.anomalyKey)).style?.color, isNotNull, reason: '有异常标色');
      expect(find.byKey(SiteRunsPage.runKey(3)), findsNothing, reason: '昨天那趟不在「今天」里');
      expect(find.byIcon(Icons.report), findsOneWidget);
      await t.tap(find.byKey(SiteRunsPage.allKey));
      await t.pumpAndSettle();
      expect(find.byKey(SiteRunsPage.runKey(3)), findsOneWidget);
      expect(find.byIcon(Icons.report), findsNWidgets(2));
      await t.tap(find.byKey(SiteRunsPage.anomalyKey));
      await t.pumpAndSettle();
      expect(find.byKey(SiteRunsPage.runKey(1)), findsNothing);
      expect(find.byKey(SiteRunsPage.runKey(2)), findsOneWidget);
      expect(api.calls.where((c) => c.startsWith('photo ') || c.startsWith('run ')), isEmpty,
          reason: '不为了缩略图多问站点');
      await t.tap(find.byKey(SiteRunsPage.runKey(2)));
      await t.pumpAndSettle();
      expect(find.byType(SiteRunPage), findsOneWidget);
      await t.pumpWidget(Container());
    });

    testWidgets('今天没有异常：那一格是 0、不上色', (t) async {
      _size(t);
      final api = _Api('owner')..runRows = [_run(1, DateTime(2026, 9, 25, 8))];
      await _pump(t, SiteRunsPage(api: api, embedded: true, now: () => DateTime(2026, 9, 25, 12)));
      expect(t.widget<Text>(find.byKey(SiteRunsPage.anomalyKey)).data, '异常 0');
      expect(t.widget<Text>(find.byKey(SiteRunsPage.anomalyKey)).style, isNull, reason: '不上色');
      expect(find.byIcon(Icons.report), findsNothing);
      await t.pumpWidget(Container());
    });

    testWidgets('App V2 目录的「记录」：巡逻记录、事件账（有摄像头、拦截点的入口）、报警记录各推一页', (t) async {
      _size(t);
      await t.pumpWidget(MaterialApp(home: NwShell(api: FakeApi('guard'), ring: () {}, updater: null)));
      await t.pumpAndSettle();
      await openSiteDir(t, SiteDest.runs);
      expect(find.byKey(SiteRunsPage.todayKey), findsOneWidget);
      await t.pageBack();
      await t.pumpAndSettle();
      await openSiteDir(t, SiteDest.events);
      expect(find.byType(SiteIncidentsPage), findsOneWidget);
      expect(find.byKey(const Key('btn-cameras')), findsOneWidget);
      expect(find.byKey(const Key('btn-intercepts')), findsOneWidget);
      await t.pageBack();
      await t.pumpAndSettle();
      await openSiteDir(t, SiteDest.alarms);
      expect(find.byType(AlarmLogPage), findsOneWidget);
      await t.pumpWidget(Container());
    });

    testWidgets('POC 告警测试模式：开着时报警记录页顶上挂条幅；没开不挂', (t) async {
      final api = FakeApi('guard');
      await t.pumpWidget(MaterialApp(home: Scaffold(body: AlarmLogPage(api: api))));
      await t.pumpAndSettle();
      expect(find.byKey(const Key('alarm-test-mode')), findsNothing);
      final end = DateTime.now().add(const Duration(hours: 1)); // 写死钟点过了那天就坏
      api.alertTestMode = <String, dynamic>{'active': true, 'until_ms': end.millisecondsSinceEpoch, 'by': 'alice'};
      await t.pumpWidget(Container());
      await t.pumpWidget(MaterialApp(home: Scaffold(body: AlarmLogPage(api: api))));
      await t.pumpAndSettle();
      expect(find.byKey(const Key('alarm-test-mode')), findsOneWidget);
      // 只在条幅里找：现在 +1 小时碰巧跟样例里哪条告警的钟点一样（CI 11-25 15:57 UTC → 16:57）就会找到两个
      expect(
          find.descendant(
              of: find.byKey(const Key('alarm-test-mode')),
              matching: find.textContaining(
                  '${end.hour.toString().padLeft(2, '0')}:${end.minute.toString().padLeft(2, '0')}')),
          findsOneWidget);
      await t.pumpWidget(Container());
    });

    testWidgets('第 12 轮 W12-02：报警和网页同一套规则 —— 管理员的事归「待处理事项」，不标「未处理」', (t) async {
      final base = Map<String, dynamic>.from((siteFixture('site_alerts')['alerts'] as List).first as Map);
      Map<String, dynamic> row(String key, String kind, String audience, String title) => <String, dynamic>{
            ...base, 'key': key, 'kind': kind, 'audience': audience, 'title': title, 'level': 'P2',
            'acked_by': '', 'acked_ms': null, 'resolved_ms': null, 'robot': 'A'};
      final api = FakeApi('admin')
        ..alertRows = [
          row('A/disk_80#7', 'disk_80', 'owner', '机器人存储空间不足'),
          row('A/offline#1', 'offline', 'offline', '机器人离线'),
        ];
      await t.pumpWidget(MaterialApp(home: Scaffold(body: AlarmLogPage(api: api))));
      await t.pumpAndSettle();
      expect(find.byKey(AlarmLogPage.todoKey), findsOneWidget);
      expect(find.byKey(AlarmLogPage.todoRowKey('A/disk_80#7')), findsOneWidget);
      expect(find.byKey(AlarmLogPage.rowKey('A/disk_80#7')), findsNothing);
      expect(find.byKey(AlarmLogPage.rowKey('A/offline#1')), findsOneWidget);
      expect(find.text('未处理'), findsOneWidget, reason: '只有离线那条是报警');
      await t.pumpWidget(Container());
    });

    testWidgets('第 13 轮 W13-02：保安不看管理员的待处理事项；同类合成一条；报警部分有标题和空状态', (t) async {
      final base = Map<String, dynamic>.from((siteFixture('site_alerts')['alerts'] as List).first as Map);
      Map<String, dynamic> row(String key, String kind, String audience, String title, {int? resolved, int first = 1}) =>
          <String, dynamic>{
            ...base, 'key': key, 'kind': kind, 'audience': audience, 'title': title, 'level': 'P2',
            'acked_by': '', 'acked_ms': null, 'resolved_ms': resolved, 'robot': 'A', 'first_ms': first};
      final rows = [
        for (var i = 0; i < 6; i++)
          row('A/schedule_blocked#$i', 'schedule_blocked', 'owner', '排程「demo-night」派不了：A 只许手动派', first: 1000 + i),
        row('-/account_request#1', 'account_request', 'admin', '王小明 申请账号，等你批准'),
        row('A/offline#1', 'offline', 'offline', '机器人离线', resolved: 5),
      ];
      final guard = FakeApi('guard')..alertRows = rows;
      await t.pumpWidget(MaterialApp(home: Scaffold(body: AlarmLogPage(api: guard))));
      await t.pumpAndSettle();
      expect(find.byKey(AlarmLogPage.todoKey), findsNothing, reason: '网页对保安不显示这些');
      expect(find.text('报警'), findsOneWidget);
      expect(find.text('没有未处理的报警。'), findsOneWidget);
      expect(find.byKey(AlarmLogPage.rowKey('A/offline#1')), findsOneWidget, reason: '已解决的照样列在下面');
      await t.pumpWidget(Container());
      final admin = FakeApi('admin')..alertRows = rows;
      await t.pumpWidget(MaterialApp(home: Scaffold(body: AlarmLogPage(api: admin))));
      await t.pumpAndSettle();
      expect(find.text('待处理事项（2 条，不是报警）'), findsOneWidget);
      expect(find.textContaining('共 6 次'), findsOneWidget);
      expect(find.byKey(AlarmLogPage.todoRowKey('A/schedule_blocked#5')), findsOneWidget, reason: '合成一条，点开最新那次');
      await t.pumpWidget(Container());
    });

    testWidgets('外审 r1 #10：页面开着时别人开了测试，过一会儿条幅自己出来；关了自己收', (t) async {
      final api = FakeApi('guard');
      await t.pumpWidget(MaterialApp(home: Scaffold(body: AlarmLogPage(api: api))));
      await t.pumpAndSettle();
      expect(find.byKey(const Key('alarm-test-mode')), findsNothing);
      api.alertTestMode = <String, dynamic>{
        'active': true,
        'until_ms': DateTime.now().add(const Duration(hours: 1)).millisecondsSinceEpoch,
        'by': 'alice'
      };
      await t.pump(AlarmLogPage.testPoll + const Duration(milliseconds: 100));
      await t.pump();
      expect(find.byKey(const Key('alarm-test-mode')), findsOneWidget);
      api.alertTestMode = <String, dynamic>{'active': false, 'until_ms': null, 'by': ''};
      await t.pump(AlarmLogPage.testPoll + const Duration(milliseconds: 100));
      await t.pump();
      expect(find.byKey(const Key('alarm-test-mode')), findsNothing);
      await t.pumpWidget(Container());
    });
  });

  group('管理栏', () {
    Future<void> health(WidgetTester t, FakeApi api, {ThemeData? theme}) async {
      _size(t);
      await t.pumpWidget(MaterialApp(
          theme: theme, home: SiteHealthPage(api: api, canShare: true, save: (n, b) async => '/x/$n')));
      await t.pumpAndSettle();
    }

    String line(WidgetTester t, String k) => t
        .widgetList<Text>(find.descendant(of: find.byKey(SiteHealthPage.versionKey(k)), matching: find.byType(Text)))
        .map((x) => x.data)
        .join(' | ');

    testWidgets('App V2 稿 S-health 版本对照：站点、每台机器人、每台登录着的客户端各一行，版本在右边', (t) async {
      final api = FakeApi('admin');
      await health(t, api);
      expect(line(t, 'site'), '站点 | 1.4.0');
      expect(line(t, 'robot-A'), 'A | 代理 1.4.0 · 级别 2 · 在线');
      expect(line(t, 'client-gina'), 'gina 的手机 App | 1.0.0 · android');
      expect(find.descendant(of: find.byKey(SiteHealthPage.versionKey('robot-A')), matching: find.byIcon(Icons.square)),
          findsOneWidget, reason: '配得上：绿方块');
      await t.pumpWidget(Container());
    });

    testWidgets('版本对照：机器人太老、App 太老是橙色三角 + 一句话；不清楚的不标橙', (t) async {
      final api = FakeApi('admin')
        ..versionsBody = <String, dynamic>{
          'site': <String, dynamic>{'version': '2', 'min_app_level': 2},
          'robots': <dynamic>[
            <String, dynamic>{'robot_id': 'A', 'online': false, 'agent': '0.9', 'level': 1, 'verdict': 'agent_too_old'},
            <String, dynamic>{'robot_id': 'B', 'online': true, 'verdict': 'unknown'},
          ],
          'clients': <dynamic>[
            <String, dynamic>{'name': 'gina', 'kind': 'app', 'version': '1.0.0', 'api_level': 1},
            <String, dynamic>{'name': 'alice', 'kind': 'web', 'api_level': 0},
          ],
        };
      await health(t, api);
      Finder warn(String k) =>
          find.descendant(of: find.byKey(SiteHealthPage.versionKey(k)), matching: find.byIcon(Icons.warning_rounded));
      expect(warn('robot-A'), findsOneWidget);
      expect(line(t, 'robot-A'), contains('机器人版本过旧'));
      expect(warn('robot-B'), findsNothing);
      expect(line(t, 'robot-B'), contains('未知'));
      expect(warn('client-gina'), findsOneWidget);
      expect(line(t, 'client-gina'), contains('比站点老'));
      expect(warn('client-alice'), findsNothing);
      expect(line(t, 'client-alice'), startsWith('alice 的网页值班台'));
      await t.pumpWidget(Container());
    });

    testWidgets('三个小节（站点、版本对照、诊断包）；没有「重启站点」（站点没有这个功能）；诊断包两个按钮一排等宽', (t) async {
      for (final lang in AppLang.values) {
        appLang.value = lang;
        addTearDown(() => appLang.value = AppLang.zh);
        await health(t, FakeApi('admin'));
        final labels = t.widgetList<NwSectionLabel>(find.byType(NwSectionLabel)).map((l) => l.text).toList();
        expect(labels, lang == AppLang.zh ? ['站点', '版本对照', '诊断包'] : ['Site', 'Version compatibility', 'Support bundle']);
        final save = t.getRect(find.byKey(SiteHealthPage.bundleKey)), share = t.getRect(find.byKey(SiteHealthPage.shareKey));
        expect((save.top, save.width), (share.top, share.width), reason: '一排等宽');
        expect(find.textContaining('重启'), findsNothing);
        expect(find.textContaining(RegExp('reboot', caseSensitive: false)), findsNothing);
        expect(find.byKey(SiteHealthPage.bundleKey), findsOneWidget);
        expect(find.byKey(SiteHealthPage.shareKey), findsOneWidget);
        await t.pumpWidget(Container());
      }
    });

    testWidgets('过了的是绿色的勾，没过的要紧项红、别的橙；浅色深色都从主题取', (t) async {
      for (final b in Brightness.values) {
        final c = b == Brightness.dark ? NwColors.dark : NwColors.light;
        final api = FakeApi('admin')
          ..healthBody = <String, dynamic>{
            'ok': false, 'critical_ok': false, 'version': '1',
            'checks': <String, dynamic>{
              'db': <String, dynamic>{'ok': false, 'detail': '库写不了'},
              'push': <String, dynamic>{'ok': false, 'detail': '没配'},
              'certs': <String, dynamic>{'ok': true, 'detail': 'x'},
            },
          };
        await health(t, api, theme: nwTheme(b));
        Color? trailing(String k) =>
            (t.widget<ListTile>(find.byKey(SiteHealthPage.checkKey(k))).trailing! as Text).style!.color;
        expect(trailing('db'), c.error);
        expect(trailing('push'), c.warning);
        expect(trailing('certs'), c.success);
        expect((t.widget<ListTile>(find.byKey(SiteHealthPage.checkKey('certs'))).leading! as Icon).color, c.success);
        await t.pumpWidget(Container());
      }
    });

    testWidgets('App V2 稿 S-home 概况：待处理、开站清单、今天、机器人；没有第二个顶栏', (t) async {
      _size(t);
      await t.pumpWidget(MaterialApp(home: NwShell(api: FakeApi('admin'), ring: () {})));
      await t.pumpAndSettle();
      await openSiteDir(t, SiteDest.overview);
      expect(find.byType(AppBar), findsNothing);
      expect(find.byKey(AdminHomeTab.todoKey), findsOneWidget, reason: '假站点的禁行区没确认');
      expect(find.byKey(SetupChecklist.cardKey), findsOneWidget);
      final card = t.getRect(find.byKey(SetupChecklist.cardKey));
      expect(t.getRect(find.byKey(AdminHomeTab.todoKey)).bottom, lessThanOrEqualTo(card.top), reason: '待处理在清单上面');
      expect(find.byKey(AdminHomeTab.entryKey('routes')), findsNothing, reason: '路线在「地图与布置」');
      await t.pumpWidget(Container());
    });
  });

  group('版面：桌面的窗口', () {
    for (final th in <String, ThemeData?>{
      'light': nwTheme(Brightness.light),
      'dark': nwTheme(Brightness.dark),
      'no theme': null,
    }.entries) {
      for (final lang in AppLang.values) {
        for (final size in const [Size(1280, 720), Size(1920, 1080)]) {
          testWidgets('不溢出 [${th.key}] [${lang.name}] ${size.width.toInt()}×${size.height.toInt()}：地图、记录、管理',
              (t) async {
            appLang.value = lang;
            addTearDown(() => appLang.value = AppLang.zh);
            t.view.physicalSize = size;
            t.view.devicePixelRatio = 1.0;
            addTearDown(t.view.reset);
            final api = _Api('admin')..robotsOverride = _robotsOn('8');
            await t.pumpWidget(MaterialApp(theme: th.value, home: NwShell(api: api, ring: () {})));
            await t.pumpAndSettle();
            for (final d in [SiteDest.layout, SiteDest.overview, SiteDest.robots]) {
              await openSiteDir(t, d);
              expect(t.takeException(), isNull, reason: '$d');
              await t.tap(find.byKey(NwShell.backKey));
              await t.pumpAndSettle();
            }
            for (final d in [SiteDest.runs, SiteDest.events, SiteDest.alarms]) {
              await openSiteDir(t, d);
              expect(t.takeException(), isNull, reason: '$d');
              await t.pageBack();
              await t.pumpAndSettle();
            }
            await t.pumpWidget(Container());
          });
        }
      }
    }

    testWidgets('推进去的那几页（地图列表、看图、一趟、照片、版本、拦截点、摄像头、天气、日志）桌面窗口下不溢出', (t) async {
      final run = siteFixture('site_run');
      final photo = ((run['photos'] as List).first as Map).cast<String, dynamic>();
      final pages = <Widget Function()>[
        () => SiteMapsPage(api: FakeApi('admin')),
        () => SiteMapPreviewPage(api: FakeApi('admin'), mapId: 'estate-1', version: '8'),
        () => SiteRunsPage(api: FakeApi('admin'), robotId: 'A'),
        () => SiteRunPage(api: FakeApi('admin'), runId: 1),
        () => SitePhotoPage(api: FakeApi('admin'), runId: 1, photo: photo, bytes: Future.value(onePixelPng)),
        () => SiteIncidentsPage(api: FakeApi('admin')),
        () => SiteSchedulePage(api: FakeApi('admin')),
        () => SiteReleasesPage(api: FakeApi('admin')),
        () => SiteInterceptsPage(api: FakeApi('admin')),
        () => SiteCamerasPage(api: FakeApi('admin')),
        () => SiteWeatherPage(api: FakeApi('admin')),
        () => SiteProcLogsPage(api: FakeApi('admin'), robotId: 'A'),
        () => SiteProcLogPage(api: FakeApi('admin'), robotId: 'A', name: 'slam'),
        () => SiteHealthPage(api: FakeApi('admin'), canShare: true, save: (n, b) async => n),
      ];
      for (final lang in AppLang.values) {
        appLang.value = lang;
        addTearDown(() => appLang.value = AppLang.zh);
        for (final size in const [Size(1280, 720), Size(1920, 1080)]) {
          t.view.physicalSize = size;
          t.view.devicePixelRatio = 1.0;
          addTearDown(t.view.reset);
          for (final b in Brightness.values) {
            for (var i = 0; i < pages.length; i++) {
              await t.pumpWidget(MaterialApp(theme: nwTheme(b), home: KeyedSubtree(key: UniqueKey(), child: pages[i]())));
              await t.pumpAndSettle();
              expect(t.takeException(), isNull, reason: '第 $i 页 ${lang.name} $size ${b.name}');
            }
          }
        }
      }
      await t.pumpWidget(Container());
    });

    testWidgets('这张图上没有栅格、没有图、读不到：三种样子在竖屏横屏、中英文下都不溢出', (t) async {
      for (final lang in AppLang.values) {
        appLang.value = lang;
        addTearDown(() => appLang.value = AppLang.zh);
        for (final size in const [Size(390, 844), Size(800, 360)]) {
          _size(t, size);
          for (final api in [
            _Api('admin')..previewMissing = true,
            _Api('admin')..mapsBody = <String, dynamic>{'maps': <dynamic>[], 'bags': <dynamic>[]},
            _Api('admin')..mapsError = const SiteError(502, '站点忙，一段很长很长的原因很长很长的原因很长很长的原因'),
            _Api('admin'),
          ]) {
            await _pump(t, SiteMapTab(key: UniqueKey(), api: api));
            expect(t.takeException(), isNull, reason: '${lang.name} $size');
          }
        }
      }
      await t.pumpWidget(Container());
    });
  });

  test('假站点的预览图是一张真的 PNG（画布测试靠它）', () {
    expect(fakePreviewPng, isA<Uint8List>());
    expect(fakePreviewPng.sublist(1, 4), [80, 78, 71]);
  });
}
