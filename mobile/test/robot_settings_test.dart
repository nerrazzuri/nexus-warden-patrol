// App V2 第 4 期：机器人页（稿 N-robot / M-robot / S-robot-set）。深色页 ⋮ 去设置；浅色页「操作 | 设置」；
// 改名、派遣方式、解绑（再输一次密码）都在设置页签里就地做，不弹窗。
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:nexwar_patrol/l10n.dart';
import 'package:nexwar_patrol/net/site_client.dart';
import 'package:nexwar_patrol/ui/site_robot.dart';
import 'package:nexwar_patrol/ui/stop_failed.dart';

import 'site_page_test.dart' show FakeApi, busyView;

Future<void> _open(WidgetTester t, FakeApi api, {bool light = true, bool settings = true}) async {
  await t.binding.setSurfaceSize(const Size(390, 1400));
  addTearDown(() => t.binding.setSurfaceSize(null));
  await t.pumpWidget(const SizedBox());
  await t.pumpWidget(MaterialApp(home: SiteRobotPage(api: api, robotId: 'A', light: light, settings: settings)));
  await t.pumpAndSettle();
}

void main() {
  setUp(() => appLang.value = AppLang.zh);

  testWidgets('改名：管理员点「改」就地出输入框，保存发出去', (t) async {
    final api = FakeApi('admin', robotView: busyView());
    await _open(t, api);
    await t.tap(find.byKey(SiteRobotPage.renameKey));
    await t.pump();
    await t.enterText(find.byKey(SiteRobotPage.nameFieldKey), '北门');
    await t.tap(find.byKey(SiteRobotPage.nameSaveKey));
    await t.pumpAndSettle();
    expect(api.calls, contains('rename A 北门'));
    expect(find.byType(AlertDialog), findsNothing);
  });

  testWidgets('保安：没有改名、没有解绑；能设成只许手动派', (t) async {
    final api = FakeApi('guard', robotView: busyView());
    await _open(t, api);
    expect(find.byKey(SiteRobotPage.renameKey), findsNothing);
    expect(find.byKey(SiteRobotPage.unbindKey), findsNothing);
    await t.tap(find.byKey(SiteRobotPage.manualKey));
    await t.pumpAndSettle();
    expect(api.calls, contains('manual A true'));
  });

  testWidgets('只许手动派的：保安接不回自动派遣（要管理员），管理员能', (t) async {
    final v = Map<String, dynamic>.of(busyView())..['manual_only'] = <String, dynamic>{'by': 'olga'};
    await _open(t, FakeApi('guard', robotView: v));
    expect(find.text('只许手动派'), findsOneWidget);
    expect(find.byKey(SiteRobotPage.manualKey), findsNothing);
    final admin = FakeApi('admin', robotView: v);
    await _open(t, admin);
    await t.tap(find.byKey(SiteRobotPage.manualKey));
    await t.pumpAndSettle();
    expect(admin.calls, contains('manual A false'));
  });

  testWidgets('解绑（管理员）：要再输一次密码；没输不发；输错了说原因、留在这页', (t) async {
    final api = FakeApi('admin', robotView: busyView());
    await _open(t, api);
    await t.ensureVisible(find.byKey(SiteRobotPage.unbindKey));
    await t.tap(find.byKey(SiteRobotPage.unbindKey));
    await t.pump();
    await t.tap(find.byKey(SiteRobotPage.unbindGoKey));
    await t.pump();
    expect(api.calls.where((c) => c.startsWith('revoke')), isEmpty);
    api.revokeError = SiteError(403, '密码不对');
    await t.enterText(find.byKey(SiteRobotPage.unbindPwKey), 'x');
    await t.tap(find.byKey(SiteRobotPage.unbindGoKey));
    await t.pumpAndSettle();
    expect(api.calls, contains('revoke A'));
    expect(find.textContaining('没解绑'), findsOneWidget);
    expect(find.byType(SiteRobotPage), findsOneWidget);
  });

  testWidgets('深色页：⋮ →「机器人设置」打开浅色页的设置页签；经理（看不了设置）没有 ⋮', (t) async {
    await _open(t, FakeApi('admin', robotView: busyView()), light: false, settings: false);
    expect(find.byKey(SiteRobotPage.operateTabKey), findsNothing);
    await t.tap(find.byKey(SiteRobotPage.menuKey));
    await t.pumpAndSettle();
    await t.tap(find.text('机器人设置'));
    await t.pumpAndSettle();
    expect(find.byKey(const Key('robot-general')), findsOneWidget);
    await _open(t, FakeApi('owner', robotView: busyView()), light: false, settings: false);
    expect(find.text('经理看状态、派巡逻'), findsOneWidget);
    expect(find.byKey(SiteRobotPage.tonightKey), findsOneWidget);
    expect(find.textContaining('由保安、管理员操作'), findsOneWidget);
    expect(find.byKey(const Key('btn-teleop')), findsNothing);
  });

  testWidgets('原地停下没成功：页顶红框（不弹窗），叫人按机身急停；「再停一次」重发，「知道了」才收', (t) async {
    final api = FakeApi('guard', robotView: busyView())..abortError = const SiteError(0, '站点无响应（超时）');
    await _open(t, api, light: false, settings: false);
    await t.ensureVisible(find.byKey(const Key('btn-abort')));
    await t.tap(find.byKey(const Key('btn-abort')));
    await t.pumpAndSettle();
    expect(find.byType(AlertDialog), findsNothing);
    expect(find.byKey(stopFailedCardKey), findsOneWidget);
    expect(find.textContaining('请立刻按机身上的急停按钮'), findsOneWidget);
    expect(find.textContaining('原因：站点无响应'), findsOneWidget);
    final n = api.calls.where((c) => c.startsWith('abort')).length;
    await t.pump(const Duration(seconds: 30));
    expect(find.byKey(stopFailedCardKey), findsOneWidget, reason: '不自动消失');
    await t.ensureVisible(find.byKey(stopAgainKey));
    await t.tap(find.byKey(stopAgainKey));
    await t.pumpAndSettle();
    expect(api.calls.where((c) => c.startsWith('abort')).length, n + 1);
    await t.tap(find.byKey(stopAckKey));
    await t.pumpAndSettle();
    expect(find.byKey(stopFailedCardKey), findsNothing);
  });
}
