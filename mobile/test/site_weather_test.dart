// 天气（W29）：首页一行说人话、点进去手动切（带时长）、回到自动、站点推了当场换；横屏 800x360。
import 'package:nexwar_patrol/ui/site_duty_page.dart';
import 'package:nexwar_patrol/ui/site_weather.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'site_page_test.dart' show FakeApi;
import 'support/fake_site.dart';

Future<void> _home(WidgetTester t, FakeApi api) async {
  await t.binding.setSurfaceSize(const Size(800, 600));
  addTearDown(() => t.binding.setSurfaceSize(null));
  await t.pumpWidget(MaterialApp(home: SiteDutyPage(api: api)));
  await t.pumpAndSettle();
}

void main() {
  test('站点夹具：天气说人话', () {
    final w = siteFixture('site_weather');
    expect(weatherText(w), '天气：下雨（手动，alice） · 限速 0.3 m/s');
    expect(weatherText(<String, dynamic>{'condition': 'storm', 'label': '雷暴', 'source': 'auto',
      'patrols_paused': true, 'speed_cap_mps': 0.3}), '天气：雷暴 · 排程巡逻暂停 · 限速 0.3 m/s');
    expect(weatherText(<String, dynamic>{'condition': 'unknown', 'label': '未知', 'source': 'none',
      'auto': <String, dynamic>{'enabled': true}}), '天气：未知 · 无法获取天气，按正常天气处理');
    expect(weatherText(<String, dynamic>{'condition': 'unknown', 'label': '未知', 'source': 'none',
      'auto': <String, dynamic>{'enabled': false}}), '天气：未知 · 未设置站点坐标，仅可手动切换');
  });

  testWidgets('首页有天气一行，点进去切雷暴 6 小时、再回到自动', (t) async {
    final api = FakeApi('guard');
    await _home(t, api);
    // W53：天气在值守页最上面那一行
    expect(find.descendant(of: find.byKey(SiteDutyPage.modeKey), matching: find.textContaining('下雨')),
        findsOneWidget);
    // 手机 App 测试 M16：首页只写短的（天气名、限速），图标说明是天气
    await t.tap(find.descendant(of: find.byKey(SiteDutyPage.modeKey), matching: find.textContaining('下雨')));
    await t.pumpAndSettle();
    await t.tap(find.byKey(SiteWeatherPage.hoursKey(6)));
    await t.pumpAndSettle();
    await t.ensureVisible(find.byKey(SiteWeatherPage.setKey('storm')));
    await t.tap(find.byKey(SiteWeatherPage.setKey('storm')));
    await t.pumpAndSettle();
    expect(api.calls, contains('weather storm 6'));
    expect(find.textContaining('天气：雷暴（手动，'), findsOneWidget);
    await t.ensureVisible(find.byKey(SiteWeatherPage.setKey('auto')));
    await t.tap(find.byKey(SiteWeatherPage.setKey('auto')));
    await t.pumpAndSettle();
    expect(api.calls.last, 'weather auto');
    await t.ensureVisible(find.byKey(SiteWeatherPage.msgKey));
    expect(find.textContaining('回到自动'), findsWidgets);
  });

  testWidgets('手机 App 测试 M15：只读账号看不到改天气的按钮，说找谁', (t) async {
    await t.pumpWidget(MaterialApp(home: SiteWeatherPage(api: FakeApi('viewer'))));
    await t.pumpAndSettle();
    expect(find.byKey(SiteWeatherPage.readOnlyKey), findsOneWidget);
    expect(find.byKey(SiteWeatherPage.setKey('storm')), findsNothing);
  });

  testWidgets('手机 App 测试 M40：现在的天气那个按钮带勾', (t) async {
    await t.pumpWidget(MaterialApp(home: SiteWeatherPage(api: FakeApi('guard'))));
    await t.pumpAndSettle();
    expect(find.descendant(of: find.byKey(SiteWeatherPage.setKey('rain')), matching: find.byIcon(Icons.check_rounded)),
        findsOneWidget);
    expect(find.descendant(of: find.byKey(SiteWeatherPage.setKey('storm')), matching: find.byIcon(Icons.check_rounded)),
        findsNothing);
  });

  testWidgets('站点推了天气：首页当场换', (t) async {
    final api = FakeApi('owner');
    await _home(t, api);
    api.sse.add(<String, dynamic>{'kind': 'weather', 'weather': <String, dynamic>{
      'condition': 'storm', 'label': '雷暴', 'source': 'auto', 'patrols_paused': true, 'speed_cap_mps': 0.3}});
    await t.pumpAndSettle();
    expect(find.text('雷暴 · 0.3 m/s'), findsOneWidget);
    expect(weatherText(<String, dynamic>{
      'condition': 'storm', 'label': '雷暴', 'source': 'auto', 'patrols_paused': true, 'speed_cap_mps': 0.3}),
        '天气：雷暴 · 排程巡逻暂停 · 限速 0.3 m/s');
  });
}
