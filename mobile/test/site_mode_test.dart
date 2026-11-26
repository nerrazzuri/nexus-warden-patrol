// 布防模式（W20）：首页那一行；保安只能切到布防、管理员能切留守和临时撤防（挑防区、挑时长）、管理员改「留守时撤防」；
// 站点推「模式变了」当场换；事件页的「撤防中」说人话。横屏 800×360。
import 'dart:async';

import 'package:nexwar_patrol/net/site_client.dart';
import 'package:nexwar_patrol/ui/site_duty_page.dart';
import 'package:nexwar_patrol/ui/site_mode.dart';
import 'package:nexwar_patrol/l10n.dart';
import 'package:flutter/material.dart';
import 'package:nexwar_patrol/ui/nw/nw_button.dart';
import 'package:flutter_test/flutter_test.dart';

import 'site_page_test.dart' show FakeApi;
import 'support/fake_site.dart';

Future<void> _open(WidgetTester t, FakeApi api) async {
  await t.binding.setSurfaceSize(const Size(800, 360));
  addTearDown(() => t.binding.setSurfaceSize(null));
  await t.pumpWidget(const SizedBox()); // 同一个测试里开第二次：不复用上一次的页面状态
  await t.pumpWidget(MaterialApp(home: SiteModePage(api: api)));
  await t.pumpAndSettle();
}

void main() {
  test('站点夹具：临时撤防带结束时间、防区带现在布不布防', () {
    final m = siteFixture('site_mode');
    expect(m['mode'], 'visitor');
    expect(modeText(m), startsWith('临时撤防（到 '));
    expect(modeText(<String, dynamic>{'mode': 'armed'}), '布防');
    expect(modeText(<String, dynamic>{'mode': 'home'}), '留守');
    final z = (m['zones'] as List).first as Map;
    expect(z.keys, containsAll(<String>['zone', 'armed', 'home_armed']));
    expect(incidentOutcomeText('disarmed'), contains('撤防'));
  });

  test('按时间表管着时（W44 第二期）：写按时间表，不写留守', () {
    expect(modeText(<String, dynamic>{'mode': 'home', 'source': 'schedule', 'state': 'partial'}), '按时间表：部分布防');
    expect(modeText(<String, dynamic>{'mode': 'armed', 'source': 'schedule', 'state': 'armed'}), '按时间表：布防');
    expect(modeText(<String, dynamic>{'mode': 'home', 'source': 'schedule', 'state': 'disarmed'}), '按时间表：撤防');
    expect(modeText(<String, dynamic>{'mode': 'home', 'source': 'manual', 'state': 'partial'}), '留守');
  });

  testWidgets('按时间表管着时，副标题写按时间表切的', (t) async {
    final api = FakeApi('owner')..modeView = <String, dynamic>{
      ...siteFixture('site_mode'), 'mode': 'home', 'visitor_zones': <String>[], 'until_ms': null,
      'source': 'schedule', 'state': 'partial', 'set_by': 'olga'};
    await _open(t, api);
    expect(find.text('现在：按时间表：部分布防'), findsOneWidget);
    expect(find.textContaining('按时间表切换'), findsOneWidget);
  });

  // 用户 11-11（易用性第 6 轮 W6-05）：保安也能撤防；防区配置照旧只有管理员
  testWidgets('保安：布防、留守、临时撤防都能切，改不了防区', (t) async {
    final api = FakeApi('guard');
    await _open(t, api);
    expect(find.byKey(SiteModePage.homeKey), findsOneWidget);
    expect(find.byKey(SiteModePage.visitorKey), findsOneWidget);
    expect(find.text('撤防（留守、临时撤防）需管理员或经理操作'), findsNothing);
    expect(find.byKey(const Key('mode-zone-home-yard')), findsNothing);
    await t.tap(find.byKey(SiteModePage.armKey));
    await t.pumpAndSettle();
    expect(api.calls, contains('mode armed'));
    expect(find.text('现在：布防'), findsOneWidget);
  });

  testWidgets('管理员：开临时撤防，挑防区、挑时长', (t) async {
    final api = FakeApi('owner')..modeView = <String, dynamic>{
      ...siteFixture('site_mode'), 'mode': 'home', 'visitor_zones': <String>[], 'until_ms': null};
    await _open(t, api);
    expect(find.text('现在：留守'), findsOneWidget);
    await t.tap(find.byKey(SiteModePage.visitorKey));
    await t.pumpAndSettle();
    await t.tap(find.byKey(const Key('visitor-zone-yard')));
    await t.tap(find.byKey(const Key('visitor-hours')));
    await t.pumpAndSettle();
    await t.tap(find.text('2 小时').last);
    await t.pumpAndSettle();
    await t.tap(find.byKey(const Key('visitor-go')));
    await t.pumpAndSettle();
    expect(api.calls, contains('mode visitor yard 120'));
    expect(find.textContaining('现在：临时撤防（到 '), findsOneWidget);
  });

  testWidgets('管理员：临时撤防默认 4 小时；切到留守', (t) async {
    final api = FakeApi('owner')..modeView = <String, dynamic>{...siteFixture('site_mode'), 'mode': 'armed'};
    await _open(t, api);
    await t.tap(find.byKey(SiteModePage.visitorKey));
    await t.pumpAndSettle();
    // 手机 App 测试 M07：从布防切出去先确认
    expect(find.textContaining('退出布防？'), findsOneWidget);
    // 易用性 37 第十轮 P1：点的是临时撤防，这一句不讲留守
    expect(find.textContaining('下一步选要临时撤防的防区'), findsOneWidget);
    await t.tap(find.byKey(SiteModePage.leaveArmedKey));
    await t.pumpAndSettle();
    await t.tap(find.byKey(const Key('visitor-zone-drive')));
    await t.pumpAndSettle();
    await t.tap(find.byKey(const Key('visitor-go')));
    await t.pumpAndSettle();
    expect(api.calls, contains('mode visitor drive 240'));
    await t.tap(find.byKey(SiteModePage.homeKey));
    await t.pumpAndSettle();
    expect(api.calls.last, 'mode home');
  });

  testWidgets('易用性 37 第十轮 P1：有防区却一个没勾，不提交、说清楚；只有一个防区默认勾上', (t) async {
    final api = FakeApi('guard')..modeView = <String, dynamic>{
      ...siteFixture('site_mode'), 'mode': 'home', 'visitor_zones': <String>[], 'until_ms': null};
    await _open(t, api);
    await t.tap(find.byKey(SiteModePage.visitorKey));
    await t.pumpAndSettle();
    expect(find.byKey(const Key('visitor-pick-hint')), findsOneWidget);
    await t.tap(find.byKey(const Key('visitor-go')));
    await t.pumpAndSettle();
    expect(api.calls.where((c) => c.startsWith('mode visitor')), isEmpty);
    expect(find.textContaining('没有撤防'), findsOneWidget);
    expect(find.textContaining('现在：留守'), findsOneWidget);

    final one = FakeApi('guard')..modeView = <String, dynamic>{
      ...siteFixture('site_mode'), 'mode': 'home', 'visitor_zones': <String>[], 'until_ms': null,
      'zones': [<String, dynamic>{'zone': 'Whole site', 'home_armed': true, 'armed': true}]};
    await _open(t, one);
    await t.tap(find.byKey(SiteModePage.visitorKey));
    await t.pumpAndSettle();
    expect(find.byKey(const Key('visitor-pick-hint')), findsNothing);
    await t.tap(find.byKey(const Key('visitor-go')));
    await t.pumpAndSettle();
    expect(one.calls, contains('mode visitor Whole site 240'));
  });

  testWidgets('易用性 37 场景测试：窄屏两排（用户 11-27 加了撤防），临时撤防按钮用短写（以前「Temporary」从中间截成「Tempo rary …」）', (t) async {
    appLang.value = AppLang.en;
    addTearDown(() => appLang.value = AppLang.zh);
    await _open(t, FakeApi('guard'));
    await t.binding.setSurfaceSize(const Size(390, 844));
    await t.pumpAndSettle();
    expect(find.descendant(of: find.byKey(SiteModePage.visitorKey), matching: find.text('Temp. disarm')), findsOneWidget);
    // 用户 11-27 加了「撤防」：四个按钮窄屏两排各两个（一排四个放不下）
    expect(t.getTopLeft(find.byKey(SiteModePage.homeKey)).dy, t.getTopLeft(find.byKey(SiteModePage.armKey)).dy);
    expect(t.getTopLeft(find.byKey(SiteModePage.disarmKey)).dy, t.getTopLeft(find.byKey(SiteModePage.visitorKey)).dy);
    expect(t.getTopLeft(find.byKey(SiteModePage.visitorKey)).dy, greaterThan(t.getTopLeft(find.byKey(SiteModePage.armKey)).dy));
    // 易用性 37 第十一轮 P3：临时撤防是当前模式时也不折两行（窄屏不加打勾）
    final api = FakeApi('guard')..modeView = <String, dynamic>{...FakeApi('guard').modeView, 'mode': 'visitor'};
    await _open(t, api);
    await t.binding.setSurfaceSize(const Size(390, 844));
    await t.pumpAndSettle();
    // 测试字体比真机宽得多，量不了是不是一行；查窄屏用的是小号、没打勾（真机 390 宽一行放得下）
    expect(t.widget<NwButton>(find.ancestor(of: find.byKey(SiteModePage.visitorKey), matching: find.byType(NwButton))).size,
        NwButtonSize.small);
    expect(find.descendant(of: find.byKey(SiteModePage.visitorKey), matching: find.byIcon(Icons.check_rounded)), findsNothing);
  });

  testWidgets('用户 11-27：保安能整站撤防 —— 先问、说清后果；撤防了不再给临时撤防', (t) async {
    final api = FakeApi('guard');
    await _open(t, api);
    await t.ensureVisible(find.byKey(SiteModePage.disarmKey));
    await t.tap(find.byKey(SiteModePage.disarmKey));
    await t.pumpAndSettle();
    expect(find.textContaining('回到原点等待'), findsOneWidget);
    await t.tap(find.byKey(SiteModePage.disarmOkKey));
    await t.pumpAndSettle();
    expect(api.calls, contains('mode disarmed'));
    final off = FakeApi('guard')..modeView = <String, dynamic>{...FakeApi('guard').modeView, 'mode': 'disarmed',
      'state': 'disarmed', 'source': 'manual', 'label': '撤防'};
    await _open(t, off);
    expect(find.byKey(SiteModePage.visitorKey), findsNothing, reason: '整站撤防了：临时撤防没意义');
    expect(find.textContaining('现在：撤防'), findsOneWidget);
  });

  testWidgets('管理员改不了防区，管理员能改「留守时也布防」', (t) async {
    await _open(t, FakeApi('owner'));
    expect(find.byKey(const Key('mode-zone-home-yard')), findsNothing);
    final api = FakeApi('admin');
    await _open(t, api);
    expect(find.text('yard · 撤防中'), findsOneWidget);
    await t.tap(find.byKey(const Key('mode-zone-home-yard')));
    await t.pumpAndSettle();
    expect(api.calls, contains('zone-home yard true'));
    expect(find.descendant(of: find.byKey(const Key('mode-zone-yard')), matching: find.text('留守时也布防')),
        findsOneWidget);
  });

  testWidgets('切不成说原因；老站点没开说清楚', (t) async {
    final api = FakeApi('owner');
    await _open(t, api);
    api.modeError = const SiteError(403, 'owner 没有 set_mode 权限');
    await t.tap(find.byKey(SiteModePage.homeKey));
    await t.pumpAndSettle();
    expect(find.textContaining('切换为留守失败'), findsOneWidget);
    await _open(t, FakeApi('owner')..modeError = const SiteError(404, '没开'));
    expect(find.text('此站点未启用布防模式'), findsOneWidget);
  });

  testWidgets('模式页：别的手机撤防了，站点推一帧，当场换、布防按钮能按了（W20 外审）', (t) async {
    final api = FakeApi('guard')..modeView = <String, dynamic>{...siteFixture('site_mode'), 'mode': 'armed'};
    await _open(t, api);
    expect(find.text('现在：布防'), findsOneWidget);
    // 手机 App 测试 M07：当前模式是选中样式（打勾），点了不再发
    expect(find.descendant(of: find.byKey(SiteModePage.armKey), matching: find.byIcon(Icons.check_rounded)), findsOneWidget);
    await t.tap(find.byKey(SiteModePage.armKey));
    await t.pump();
    expect(api.calls.where((c) => c == 'mode armed'), isEmpty);
    api.sse.add(<String, dynamic>{'kind': 'mode', 'mode': <String, dynamic>{...api.modeView, 'mode': 'home'}});
    await t.pump(const Duration(milliseconds: 50));
    expect(find.text('现在：留守'), findsOneWidget);
    expect(find.descendant(of: find.byKey(SiteModePage.armKey), matching: find.byIcon(Icons.check_rounded)), findsNothing);
    await t.tap(find.byKey(SiteModePage.armKey));
    await t.pump();
    expect(api.calls, contains('mode armed'));
  });

  testWidgets('模式页：断线重连后重新拉一次（断线期间错过的切换补上）', (t) async {
    final api = FakeApi('guard')..modeView = <String, dynamic>{...siteFixture('site_mode'), 'mode': 'armed'};
    await _open(t, api);
    final opened = api.eventsOpened;
    final old = api.sse;
    api.sse = StreamController<Map<String, dynamic>>.broadcast();
    api.modeView = <String, dynamic>{...api.modeView, 'mode': 'home'}; // 断线期间管理员撤防了
    await old.close();
    await t.pump(const Duration(seconds: 6));
    expect(api.eventsOpened, greaterThan(opened));
    expect(find.text('现在：留守'), findsOneWidget);
  });

  testWidgets('值守页（W53）：模式那一行；站点推「模式变了」就重读；点「切换」是模式页', (t) async {
    final api = FakeApi('guard');
    await t.binding.setSurfaceSize(const Size(800, 600));
    addTearDown(() => t.binding.setSurfaceSize(null));
    await t.pumpWidget(MaterialApp(home: SiteDutyPage(api: api)));
    await t.pumpAndSettle();
    expect(find.textContaining('临时撤防（到 '), findsOneWidget);
    api.modeView = <String, dynamic>{...api.modeView, 'mode': 'armed', 'until_ms': null};
    api.sse.add(<String, dynamic>{'kind': 'mode', 'mode': api.modeView});
    await t.pump(const Duration(milliseconds: 600));
    await t.pumpAndSettle();
    expect(find.text('布防'), findsOneWidget);
    await t.tap(find.byKey(SiteDutyPage.modeChangeKey));
    await t.pumpAndSettle();
    expect(find.byType(SiteModePage), findsOneWidget);
  });

  testWidgets('值守页：老站点没有布防模式就没有「切换」', (t) async {
    final api = FakeApi('guard')..modeError = const SiteError(404, '没开');
    await t.binding.setSurfaceSize(const Size(800, 600));
    addTearDown(() => t.binding.setSurfaceSize(null));
    await t.pumpWidget(MaterialApp(home: SiteDutyPage(api: api)));
    await t.pumpAndSettle();
    expect(find.byKey(SiteDutyPage.modeChangeKey), findsNothing);
  });

  test('权限：管理员能确认告警、能切模式；保安也能撤防（11-11）；管理员不能标录像留着', () {
    const owner = SiteSession('t', 'o', 'owner', displayName: '张三');
    const guard = SiteSession('t', 'g', 'guard');
    expect(owner.canHandleAlerts && owner.canSetMode && owner.canArm, isTrue);
    expect(owner.canReview, isFalse);
    expect(guard.canArm && guard.canSetMode, isTrue);
    expect(owner.displayName, '张三');
  });
}
