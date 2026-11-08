// 手机 App 测试 P2 一批：M31 吊销的收起来、M36 删正在跑的路线先说、M38 账号申请不是报警、只读标在页头。
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:nexwar_patrol/model/alert.dart';
import 'package:nexwar_patrol/net/site_client.dart';
import 'package:nexwar_patrol/store/site_store.dart';
import 'package:nexwar_patrol/ui/site_add.dart';
import 'package:nexwar_patrol/ui/nw/nw_p3_robots.dart';
import 'package:nexwar_patrol/ui/site_alert_scene.dart';
import 'package:nexwar_patrol/ui/site_duty_page.dart';

import 'site_page_test.dart' show FakeApi;

Alert _req() => Alert.fromWire(<String, dynamic>{
      'key': 'site/account_request#1', 'level': 'P2', 'kind': 'account_request', 'robot': 'site',
      'title': '账号申请', 'detail': '', 'first_ms': 1, 'last_ms': 1, 'count': 1, 'acked_by': '',
      'acked_ms': null, 'resolved_ms': null, 'escalated': 0, 'channel': 'screen'});

void main() {
  testWidgets('M31：吊销的机器人不算在「全部」里，收在最底下', (t) async {
    await t.pumpWidget(MaterialApp(
        home: Scaffold(
            body: SingleChildScrollView(
                child: NwFleet(robots: const [
      {'robot_id': 'A', 'status': {'online': true}, 'fresh': true},
      {'robot_id': 'T51', 'revoked': true},
    ], deterring: const {}, activityOf: (_) => '', onOpen: (_) {})))));
    await t.pumpAndSettle();
    expect(find.text('全部 1'), findsOneWidget);
    expect(find.text('已解绑（1）'), findsOneWidget);
    expect(find.byKey(const Key('robot-T51')), findsNothing, reason: '收着');
  });

  testWidgets('M38：账号申请没有「我来处理 / 误报」；管理员有去审批，经理说谁批', (t) async {
    await t.pumpWidget(MaterialApp(home: SiteAlertScenePage(api: FakeApi('admin'), alert: _req())));
    await t.pumpAndSettle();
    expect(find.byKey(SiteAlertScenePage.accountsKey), findsOneWidget);
    expect(find.byKey(SiteAlertScenePage.ackKey), findsNothing);
    await t.pumpWidget(Container());
    await t.pumpWidget(MaterialApp(home: SiteAlertScenePage(api: FakeApi('owner'), alert: _req())));
    await t.pumpAndSettle();
    expect(find.textContaining('由管理员审批'), findsOneWidget);
    expect(find.byKey(SiteAlertScenePage.ackKey), findsNothing);
  });

  testWidgets('M38：只读账号的值守页页头写「只读」', (t) async {
    await t.pumpWidget(MaterialApp(home: SiteDutyPage(api: FakeApi('viewer'))));
    await t.pumpAndSettle();
    expect(find.textContaining('只读'), findsWidgets);
  });

  test('M22：地址不带端口不让存', () {
    expect(checkSiteEntry('https://10.0.0.5', 'ab' * 32), contains('8443'));
    expect(checkSiteEntry('https://10.0.0.5:8520', 'ab' * 32), isNull);
  });

  testWidgets('M22：同一个站点不加第二次，原因留在页面上', (t) async {
    final have = SiteEntry(name: 'demo', url: 'https://10.0.0.5:8520', fingerprint: 'ab' * 32, username: '');
    await t.pumpWidget(MaterialApp(home: SiteAddPage(existing: [have])));
    await t.pumpAndSettle();
    await t.enterText(find.byKey(const Key('site-name')), 'demo 2');
    await t.enterText(find.byKey(const Key('site-url')), 'https://10.0.0.5:8520');
    await t.enterText(find.byKey(const Key('site-fp')), 'ab' * 32);
    await t.ensureVisible(find.byKey(const Key('site-save')));
    await t.tap(find.byKey(const Key('site-save')));
    await t.pumpAndSettle(const Duration(seconds: 6));
    expect(find.byKey(SiteAddPage.errorKey), findsOneWidget);
    expect(find.textContaining('已经在列表里'), findsOneWidget);
  });
}
