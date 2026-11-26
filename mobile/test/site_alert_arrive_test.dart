// W74 一期：看见人以后 —— 保安点「已到场」才能处置完成 / 标误报；去向不明、最后看见的位置。
import 'package:nexwar_patrol/model/alert.dart';
import 'package:nexwar_patrol/ui/site_alert_scene.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'site_page_test.dart' show FakeApi;
import 'support/scene.dart';

Alert _person({Map<String, dynamic> extra = const <String, dynamic>{}}) =>
    Alert.fromWire(<String, dynamic>{
      'key': 'A/dog_sees_person#1', 'level': 'P1', 'kind': 'dog_sees_person', 'robot': 'A',
      'title': '机器人看见人了:1 个人', 'detail': '', 'first_ms': 1, 'last_ms': 1, 'count': 1,
      'acked_by': '', 'acked_ms': null, 'resolved_by': '', 'resolved_ms': null, 'escalated': 0,
      'channel': 'screen',
      'context': <String, dynamic>{
        'task_id': 'persons',
        'pose': <String, dynamic>{'map_id': 'm', 'map_version': '1', 'x': 1.0, 'y': 1.0, 'at_ms': 1},
        'last_seen': <String, dynamic>{'map_id': 'm', 'map_version': '1', 'x': 5.0, 'y': 6.0,
          'yaw': 0.0, 'at_ms': 2000},
        ...extra,
      },
    });

Future<void> _tall(WidgetTester t) async {
  await t.binding.setSurfaceSize(const Size(420, 900));
  addTearDown(() => t.binding.setSurfaceSize(null));
}

void main() {
  m04Tests();
  testWidgets('我来处理、已到场都在；没到场没有结论可选；点了发 arrive，结论才出来', (t) async {
    await _tall(t);
    final api = FakeApi('guard');
    await t.pumpWidget(MaterialApp(home: SiteAlertScenePage(api: api, alert: _person())));
    await t.pumpAndSettle();
    expect(find.byKey(SiteAlertScenePage.ackKey), findsOneWidget);
    expect(await sceneShow(t, find.byKey(SiteAlertScenePage.arriveKey)), findsOneWidget);
    expect(await sceneShow(t, find.textContaining('有人到场后才能结案')), findsOneWidget);
    expect(find.byKey(SiteAlertScenePage.falseKey), findsNothing, reason: '误报要先到场');
    expect(find.byKey(SiteAlertScenePage.doneKey), findsNothing);
    await sceneTap(t, SiteAlertScenePage.arriveKey);
    expect(api.calls, contains('arrive A/dog_sees_person#1'));
    expect(await sceneShow(t, find.byKey(SiteAlertScenePage.doneKey)), findsOneWidget, reason: '到场了：能定结论结案');
    expect(find.byKey(SiteAlertScenePage.falseKey), findsOneWidget);
    // 易用性 37 第十三轮 P3：「已到场」留在原处变灰，「请求支援」不挪到手指下
    expect(await sceneShow(t, find.byKey(SiteAlertScenePage.arrivedDoneKey)), findsOneWidget);
    final done = t.widget<ButtonStyleButton>(find.byKey(SiteAlertScenePage.arrivedDoneKey));
    expect(done.onPressed, isNull);
    // 第十四轮 P3：请求支援以后它也留在原处（变灰），「已到场」不挪到手指下
    await sceneTap(t, SiteAlertScenePage.backupKey);
    await t.pumpAndSettle();
    expect(await sceneShow(t, find.byKey(SiteAlertScenePage.backupSentKey)), findsOneWidget);
    expect(t.widget<ButtonStyleButton>(find.byKey(SiteAlertScenePage.backupSentKey)).onPressed, isNull);
  });

  testWidgets('到场了：先选结论才能结案；备注一起发', (t) async {
    await _tall(t);
    final api = FakeApi('guard');
    await t.pumpWidget(MaterialApp(
        home: SiteAlertScenePage(
            api: api, alert: _person(extra: <String, dynamic>{'arrived_by': '张三', 'arrived_ms': 3000}))));
    await t.pumpAndSettle();
    expect(await sceneShow(t, find.textContaining('张三 已到场')), findsOneWidget);
    await sceneShow(t, find.byKey(SiteAlertScenePage.doneKey));
    final done = t.widget<FilledButton>(find.descendant(of: find.byKey(SiteAlertScenePage.doneKey), matching: find.byType(FilledButton), matchRoot: true));
    expect(done.onPressed, isNull, reason: '没选结论，结案按不了');
    await sceneTap(t, SiteAlertScenePage.handledKey);
    await t.enterText(find.byKey(SiteAlertScenePage.noteKey), '外卖员找错门');
    await sceneTap(t, SiteAlertScenePage.doneKey);
    expect(api.calls, contains('resolve A/dog_sees_person#1 handled note=外卖员找错门'));
  });

  testWidgets('去向不明：写出几点起看不到；最后位置用最后看见的那一处', (t) async {
    await _tall(t);
    final api = FakeApi('guard');
    await t.pumpWidget(MaterialApp(
        home: SiteAlertScenePage(api: api, alert: _person(extra: <String, dynamic>{'lost_ms': 4000}))));
    await t.pumpAndSettle();
    expect(await sceneShow(t, find.textContaining('看不到人了，去向不明')), findsWidgets);
    // 易用性 37 场景测试：坐标只给管理员、工程师看；保安看图上的标记（下面）
    expect(find.textContaining('(5.0, 6.0)'), findsNothing);
    final (_, _, marks) = sceneMarks(_person())!;
    expect((marks.first.x, marks.first.y), (5.0, 6.0));
  });

  testWidgets('W74 二期：在跟写「正跟着」；跟丢了写最后在哪，图上标人最后的位置', (t) async {
    await _tall(t);
    final api = FakeApi('guard');
    await t.pumpWidget(MaterialApp(
        home: SiteAlertScenePage(api: api, alert: _person(extra: <String, dynamic>{
      'follow': 'follow', 'person': <String, dynamic>{'x': 7.0, 'y': 8.0, 'at_ms': 3000}}))));
    await t.pumpAndSettle();
    expect(await sceneShow(t, find.textContaining('机器人正跟着这个人')), findsOneWidget);
    final lost = _person(extra: <String, dynamic>{
      'follow': 'lost', 'lost_ms': 4000,
      'person': <String, dynamic>{'x': 7.0, 'y': 8.0, 'at_ms': 3500, 'where': '东门附近'}});
    await t.pumpWidget(MaterialApp(home: SiteAlertScenePage(api: api, alert: lost)));
    await t.pumpAndSettle();
    expect(find.textContaining('机器人正跟着这个人'), findsNothing);
    expect(await sceneShow(t, find.textContaining('跟丢了，人最后在 东门附近')), findsOneWidget);
    final (_, _, marks) = sceneMarks(lost)!;
    expect(marks.map((m) => (m.x, m.y)), contains((7.0, 8.0)));
  });

  testWidgets('真机 11-25：退不了原地站定、人离开防区 —— 写清它为什么停', (t) async {
    await _tall(t);
    final api = FakeApi('guard');
    await t.pumpWidget(MaterialApp(
        home: SiteAlertScenePage(api: api, alert: _person(extra: <String, dynamic>{
      'follow': 'cornered', 'follow_why': '身后有东西', 'person': <String, dynamic>{'x': 7.0, 'y': 8.0, 'at_ms': 3000}}))));
    await t.pumpAndSettle();
    expect(await sceneShow(t, find.textContaining('身后有东西退不了，原地站定')), findsWidgets);
    expect(find.textContaining('跟随中'), findsWidgets);
    await t.pumpWidget(MaterialApp(
        home: SiteAlertScenePage(api: api, alert: _person(extra: <String, dynamic>{
      'follow': 'ended', 'follow_left': true, 'person': <String, dynamic>{'x': 7.0, 'y': 8.0, 'at_ms': 3000}}))));
    await t.pumpAndSettle();
    expect(await sceneShow(t, find.textContaining('人离开了防区')), findsWidgets);
    expect(find.textContaining('跟随中'), findsNothing);
  });

  test('真机 11-25：写清是前相机还是后相机看到的', () {
    expect(seenByText(<String, dynamic>{'persons': <String, dynamic>{'cams': <String>['back']}}), '后相机看到的');
    expect(seenByText(<String, dynamic>{'persons': <String, dynamic>{'cams': <String>['front', 'back']}}), '前、后相机看到的');
    expect(seenByText(<String, dynamic>{'persons': <String, dynamic>{}}), '');
  });

  testWidgets('别的告警照旧：我来处理、误报', (t) async {
    await _tall(t);
    final api = FakeApi('guard');
    final other = Alert.fromWire(<String, dynamic>{
      'key': 'A/stuck#1', 'level': 'P1', 'kind': 'stuck', 'robot': 'A', 'title': '卡住了',
      'first_ms': 1, 'last_ms': 1, 'count': 1, 'context': <String, dynamic>{}});
    await t.pumpWidget(MaterialApp(home: SiteAlertScenePage(api: api, alert: other)));
    await t.pumpAndSettle();
    expect(find.byKey(SiteAlertScenePage.ackKey), findsOneWidget);
    expect(find.byKey(SiteAlertScenePage.arriveKey), findsNothing);
  });
}

/// 手机 App 测试 M04：机器人故障、派单被拒这类真事只给「已处理」；可能误报的才有「误报」。
void m04Tests() {
  Alert fault(String kind, String audience) => Alert.fromWire(<String, dynamic>{
        'key': 'A/$kind#1', 'level': 'P2', 'kind': kind, 'audience': audience, 'robot': 'A',
        'title': 't', 'detail': '', 'first_ms': 1, 'last_ms': 1, 'count': 1, 'acked_by': '',
        'acked_ms': null, 'resolved_ms': null, 'escalated': 0, 'channel': 'screen',
      });

  testWidgets('M04：出发前检查失败只有「已处理」，点了带 handled 结论；入侵有「误报」', (t) async {
    await _tall(t);
    final api = FakeApi('guard');
    await t.pumpWidget(MaterialApp(home: SiteAlertScenePage(api: api, alert: fault('preflight_refused', 'owner'))));
    await t.pumpAndSettle();
    await sceneShow(t, find.byKey(SiteAlertScenePage.doneKey));
    expect(find.byKey(SiteAlertScenePage.falseKey), findsNothing);
    expect(find.byKey(SiteAlertScenePage.intruderKey), findsNothing);
    expect(find.text('对讲：暂不支持'), findsNothing);
    await sceneTap(t, SiteAlertScenePage.handledKey);
    await sceneTap(t, SiteAlertScenePage.doneKey);
    expect(api.calls, contains('resolve A/preflight_refused#1 handled'));
    await t.pumpWidget(const SizedBox());
    await t.pumpWidget(MaterialApp(home: SiteAlertScenePage(api: FakeApi('guard'), alert: fault('cctv_motion', 'intrusion'))));
    await t.pumpAndSettle();
    await sceneShow(t, find.byKey(SiteAlertScenePage.doneKey));
    expect(find.byKey(SiteAlertScenePage.falseKey), findsOneWidget);
    expect(find.byKey(SiteAlertScenePage.intruderKey), findsOneWidget, reason: '入侵三种结论');
    expect(find.byKey(SiteAlertScenePage.doneKey), findsOneWidget);
  });
}
