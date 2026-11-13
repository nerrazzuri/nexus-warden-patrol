// 站点模式的地图（W00c5d 第二部分）：管理员下发图、拿录包重建、录包开始停止；别的角色只看。
import 'package:nexwar_patrol/ui/site_mapping.dart';
import 'package:nexwar_patrol/ui/site_maps.dart';
import 'package:nexwar_patrol/ui/map_manage.dart' show mapSourceText;
import 'package:nexwar_patrol/ui/site_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'site_page_test.dart' show FakeApi;
import 'support/fake_site.dart';

void main() {
  testWidgets('这台机器人在这张图上没有原点（W13a）：说后果，确认了才照样下发', (t) async {
    final api = FakeApi('admin')..noHome = true;
    await t.pumpWidget(MaterialApp(home: SiteMapsPage(api: api)));
    await t.pumpAndSettle();
    await t.tap(find.byKey(SiteMapsPage.mapKey('estate-1', '8')));
    await t.pumpAndSettle();
    await t.tap(find.byKey(const Key('pick-A')));
    await t.pumpAndSettle();
    await t.tap(find.byKey(const Key('activate-go')));
    await t.pumpAndSettle();
    expect(api.calls, contains('map A estate-1:8'));
    expect(find.textContaining('尚未标原点'), findsWidgets);
    await t.tap(find.text('取消'));
    await t.pumpAndSettle();
    expect(api.calls.where((c) => c.endsWith('without_home')), isEmpty);
    expect(find.textContaining('未下发'), findsOneWidget);
    await t.tap(find.byKey(SiteMapsPage.mapKey('estate-1', '8')));
    await t.pumpAndSettle();
    await t.tap(find.byKey(const Key('pick-A')));
    await t.pumpAndSettle();
    await t.tap(find.byKey(const Key('activate-go')));
    await t.pumpAndSettle();
    await t.tap(find.byKey(const Key('activate-without-home')));
    await t.pumpAndSettle();
    expect(api.calls, contains('map A estate-1:8 without_home'));
    expect(find.textContaining('正在下载并加载'), findsOneWidget);
  });

  testWidgets('草稿（编辑、去噪出来的，11-11）：标「草稿」、说怎么发布，点了不下发', (t) async {
    final api = FakeApi('admin')
      ..catalog = <String, dynamic>{
        'maps': <dynamic>[
          <String, dynamic>{'map_id': 'estate-1', 'version': '9', 'source': 'draft:alice', 'draft': true,
            'note': '从 8 编辑:清了 2 处零星噪点(5 格)', 'files': <dynamic>[]},
          <String, dynamic>{'map_id': 'estate-1', 'version': '8', 'source': 'import', 'draft': false,
            'note': '', 'files': <dynamic>[]},
        ],
        'bags': <dynamic>[],
      };
    await t.pumpWidget(MaterialApp(home: SiteMapsPage(api: api)));
    await t.pumpAndSettle();
    expect(find.byKey(SiteMapsPage.draftKey('estate-1', '9')), findsOneWidget);
    expect(find.byKey(SiteMapsPage.draftKey('estate-1', '8')), findsNothing);
    expect(find.textContaining('发布到站点后才能下发'), findsOneWidget);
    await t.tap(find.byKey(SiteMapsPage.mapKey('estate-1', '9')));
    await t.pumpAndSettle();
    expect(find.byKey(const Key('pick-A')), findsNothing, reason: '草稿不能下发');
    await t.tap(find.byKey(SiteMapsPage.mapKey('estate-1', '8')));
    await t.pumpAndSettle();
    expect(find.byKey(const Key('pick-A')), findsOneWidget);
  });

  testWidgets('管理员点一张图、选机器人、下发', (t) async {
    final api = FakeApi('admin');
    await t.pumpWidget(MaterialApp(home: SiteMapsPage(api: api)));
    await t.pumpAndSettle();
    expect(find.textContaining('厂商图'), findsOneWidget);
    await t.tap(find.byKey(SiteMapsPage.mapKey('estate-1', '8')));
    await t.pumpAndSettle();
    await t.tap(find.byKey(const Key('pick-A')));
    await t.pumpAndSettle();
    expect(api.calls.where((c) => c.startsWith('map ')), isEmpty, reason: '换图先确认一次');
    await t.tap(find.byKey(const Key('activate-go')));
    await t.pumpAndSettle();
    expect(api.calls, contains('map A estate-1:8'));
    expect(find.textContaining('正在下载并加载'), findsOneWidget);
  });

  testWidgets('没报这种能力的机器人不列、不显示按钮', (t) async {
    final api = FakeApi('admin');
    api.robotsOverride = [
      for (final r in (siteFixture('site_robots')['robots'] as List).cast<Map<String, dynamic>>())
        {...r, 'capabilities': null},
    ];
    api.view = {...api.view, 'capabilities': null};
    await t.pumpWidget(MaterialApp(home: SiteMapsPage(api: api)));
    await t.pumpAndSettle();
    await t.tap(find.byKey(SiteMapsPage.mapKey('estate-1', '8')));
    await t.pumpAndSettle();
    expect(find.byKey(const Key('pick-A')), findsNothing);
    expect(find.textContaining('可换图的机器人'), findsOneWidget);
    await t.tap(find.byKey(SiteMapsPage.bagKey('A', 'yard-0925')));
    await t.pumpAndSettle();
    expect(find.byKey(SiteMapsPage.versionKey), findsNothing);
    expect(find.textContaining('当前无法重建'), findsOneWidget);
    await t.pumpWidget(MaterialApp(home: SiteRobotPage(key: UniqueKey(), api: api, robotId: 'A')));
    await t.pump();
    expect(find.byKey(const Key('btn-record-start')), findsNothing);
  });

  testWidgets('换图确认时点算了：不下发', (t) async {
    final api = FakeApi('admin');
    await t.pumpWidget(MaterialApp(home: SiteMapsPage(api: api)));
    await t.pumpAndSettle();
    await t.tap(find.byKey(SiteMapsPage.mapKey('estate-1', '8')));
    await t.pumpAndSettle();
    await t.tap(find.byKey(const Key('pick-A')));
    await t.pumpAndSettle();
    await t.tap(find.text('取消'));
    await t.pumpAndSettle();
    expect(api.calls.where((c) => c.startsWith('map ')), isEmpty);
  });

  testWidgets('管理员拿录包重建：给一个新版本号', (t) async {
    final api = FakeApi('admin');
    await t.pumpWidget(MaterialApp(home: SiteMapsPage(api: api)));
    await t.pumpAndSettle();
    await t.tap(find.byKey(SiteMapsPage.bagKey('A', 'yard-0925')));
    await t.pumpAndSettle();
    await t.enterText(find.byKey(SiteMapsPage.versionKey), '9');
    await t.tap(find.byKey(const Key('build-go')));
    await t.pumpAndSettle();
    expect(api.calls, contains('build A yard-0925 estate-1:9'));
  });

  test('第 11 轮 A11-01：地图从哪来写人话，不写 edit:demo、cli:liang', () {
    expect(mapSourceText('edit:demo'), 'demo 编辑');
    expect(mapSourceText('cli:liang'), 'liang 导入');
    expect(mapSourceText('import'), '导入');
    expect(mapSourceText('draft:demo'), 'demo 编辑（草稿）');
    expect(mapSourceText('A'), 'A 建图');
    expect(mapSourceText(''), '');
  });

  testWidgets('第 11 轮 A11-01：经理看的地图目录跟地图管理一个写法：第几版、谁编辑、哪几台在用，不写几个文件', (t) async {
    final api = FakeApi('manager')
      ..catalog = <String, dynamic>{
        'maps': <dynamic>[
          <String, dynamic>{'map_id': 'estate-1', 'version': '11', 'source': 'edit:demo',
            'note': '从 10 编辑:擦了 0.2 平方米', 'files': <dynamic>[1, 2, 3, 4, 5, 6, 7, 8],
            'loaded_on': <dynamic>['A', 'B'], 'draft': false},
          <String, dynamic>{'map_id': 'estate-1', 'version': '10', 'source': 'cli:liang', 'note': '',
            'files': <dynamic>[1], 'loaded_on': <dynamic>[], 'draft': false},
        ],
        'bags': <dynamic>[],
      };
    await t.pumpWidget(MaterialApp(home: SiteMapsPage(api: api)));
    await t.pumpAndSettle();
    expect(find.textContaining('第 11 版'), findsOneWidget);
    expect(find.textContaining('demo 编辑 · 从第 10 版编辑：擦了 0.2 平方米'), findsOneWidget);
    expect(find.text('A、B 在用'), findsOneWidget);
    expect(find.textContaining('liang 导入'), findsOneWidget);
    expect(find.textContaining('个文件'), findsNothing);
    expect(find.textContaining('edit:'), findsNothing);
    expect(find.textContaining('cli:'), findsNothing);
    expect(find.textContaining('estate-1:11'), findsNothing);
  });

  testWidgets('保安只看：点了不下发', (t) async {
    final api = FakeApi('guard');
    await t.pumpWidget(MaterialApp(home: SiteMapsPage(api: api)));
    await t.pumpAndSettle();
    await t.tap(find.byKey(SiteMapsPage.mapKey('estate-1', '8')));
    await t.pumpAndSettle();
    expect(find.byKey(const Key('pick-A')), findsNothing);
    expect(api.calls.where((c) => c.startsWith('map ')), isEmpty);
  });

  testWidgets('单机器人页：管理员有录包开始、停止；保安没有', (t) async {
    final admin = FakeApi('admin');
    await t.pumpWidget(MaterialApp(home: SiteRobotPage(api: admin, robotId: 'A')));
    await t.pump();
    await t.tap(find.byKey(const Key('btn-record-start')));
    await t.pumpAndSettle();
    await t.enterText(find.byKey(const Key('record-name')), 'yard');
    await t.tap(find.byKey(const Key('record-go')));
    await t.pumpAndSettle();
    expect(admin.calls, contains('mapping A start yard'));
    expect(find.byType(SiteMappingTrailPage), findsOneWidget, reason: '收下了就打开录包轨迹（W00c6h）');
    await t.pageBack();
    await t.pumpAndSettle();
    await t.tap(find.byKey(const Key('btn-record-stop')));
    await t.pumpAndSettle();
    expect(admin.calls, contains('mapping A stop '));
    final guard = FakeApi('guard');
    await t.pumpWidget(MaterialApp(home: SiteRobotPage(key: UniqueKey(), api: guard, robotId: 'A')));
    await t.pump();
    expect(find.byKey(const Key('btn-record-start')), findsNothing);
  });

  testWidgets('录包时填了地图号与版本就边走边建；只填一个不发、说清楚', (t) async {
    final admin = FakeApi('admin');
    await t.pumpWidget(MaterialApp(home: SiteRobotPage(api: admin, robotId: 'A')));
    await t.pump();
    await t.tap(find.byKey(const Key('btn-record-start')));
    await t.pumpAndSettle();
    await t.enterText(find.byKey(const Key('record-name')), 'yard');
    await t.enterText(find.byKey(const Key('record-map')), 'estate-1');
    await t.tap(find.byKey(const Key('record-go')));
    await t.pumpAndSettle();
    expect(admin.calls.where((c) => c.startsWith('mapping')), isEmpty);
    expect(find.textContaining('地图号和版本需同时填写'), findsOneWidget);
    await t.tap(find.byKey(const Key('btn-record-start')));
    await t.pumpAndSettle();
    await t.enterText(find.byKey(const Key('record-name')), 'yard');
    await t.enterText(find.byKey(const Key('record-map')), 'estate-1');
    await t.enterText(find.byKey(const Key('record-version')), '5');
    await t.tap(find.byKey(const Key('record-go')));
    await t.pumpAndSettle();
    expect(admin.calls, contains('mapping A start yard estate-1:5'));
  });

  // 2026-10-14 重做：入口从狗列表的顶栏挪到了底部导航的「地图」栏；第四批起地图栏是当前这张图
  // （SiteMapTab），这个列表页从它右上角进。
  testWidgets('进了站点有「地图」入口', (t) async {
    final api = FakeApi('owner');
    await t.pumpWidget(MaterialApp(home: NwShell(api: api, title: '庄园')));
    await t.pump();
    await t.tap(find.byKey(const Key('open-maps')));
    await t.pumpAndSettle();
    expect(find.byType(SiteMapTab), findsOneWidget);
    await t.tap(find.byKey(SiteMapTab.listKey));
    await t.pumpAndSettle();
    expect(find.byType(SiteMapsPage), findsOneWidget);
  });
}
