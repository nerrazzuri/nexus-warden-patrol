// App V2 稿 N-refuse 下半：全部急停有一台没回执 → 红框「急停没确认」+ 再发一次 / 看画面；再发成了红框就没了。
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:nexwar_patrol/net/site_client.dart';
import 'package:nexwar_patrol/ui/nw/nw_estop_miss.dart';
import 'package:nexwar_patrol/ui/site_robot.dart';
import 'package:nexwar_patrol/ui/widget/alarm_widgets.dart';

import 'site_page_test.dart' show FakeApi;

class _Api extends FakeApi {
  _Api() : super('guard');
  final fail = <String>{'B'};
  @override
  Future<List<Map<String, dynamic>>> robots() async => [
        for (final id in ['A', 'B'])
          <String, dynamic>{'robot_id': id, 'fresh': true, 'status': <String, dynamic>{'online': true}},
      ];
  @override
  Future<Map<String, dynamic>> halt(String robotId) async {
    calls.add('halt $robotId');
    if (fail.contains(robotId)) throw const SiteError(504, '机器人未返回停车的回执');
    return <String, dynamic>{'ack': <String, dynamic>{'result': 'accepted'}};
  }
}

void main() {
  tearDown(() => estopMisses.value = const []);

  testWidgets('B 没回执：红框写站点几点发的、B 可能还在动；两个按钮等宽；再发成了红框没了', (t) async {
    final api = _Api();
    var said = '';
    await t.pumpWidget(MaterialApp(
        home: Scaffold(
            body: Builder(
                builder: (c) => ListView(children: [
                      TextButton(onPressed: () => StopAllButton.press(c, api, (m) => said = m), child: const Text('stop')),
                      EstopMissCards(api: api),
                    ])))));
    await t.tap(find.text('stop'));
    await t.pumpAndSettle();
    await t.tap(find.byKey(StopAllButton.confirmKey));
    await t.pumpAndSettle();
    expect(api.calls, containsAll(<String>['halt A', 'halt B']));
    expect(said, contains('B'));
    expect(find.byKey(EstopMissCards.cardKey('A')), findsNothing);
    expect(find.byKey(EstopMissCards.cardKey('B')), findsOneWidget);
    expect(find.text('急停没确认'), findsOneWidget);
    expect(find.textContaining('B 没有回执'), findsOneWidget);
    expect(t.getSize(find.byKey(EstopMissCards.againKey('B'))).width, t.getSize(find.byKey(EstopMissCards.videoKey('B'))).width);

    await t.tap(find.byKey(EstopMissCards.againKey('B')));
    await t.pumpAndSettle();
    expect(find.byKey(EstopMissCards.cardKey('B')), findsOneWidget, reason: '还是没回执：红框留着');
    api.fail.clear();
    await t.tap(find.byKey(EstopMissCards.againKey('B')));
    await t.pumpAndSettle();
    expect(api.calls.where((c) => c == 'halt B').length, 3);
    expect(find.byKey(EstopMissCards.cardKey('B')), findsNothing);
  });

  testWidgets('看画面：去 B 的机器人页', (t) async {
    final api = _Api();
    estopMisses.value = [EstopMiss('B', DateTime(2026, 11, 15, 23, 41, 5), const SiteError(504, 'x'))];
    await t.pumpWidget(MaterialApp(home: Scaffold(body: ListView(children: [EstopMissCards(api: api)]))));
    expect(find.textContaining('23:41:05'), findsOneWidget);
    await t.tap(find.byKey(EstopMissCards.videoKey('B')));
    await t.pumpAndSettle();
    expect(find.byType(SiteRobotPage), findsOneWidget);
  });
}
