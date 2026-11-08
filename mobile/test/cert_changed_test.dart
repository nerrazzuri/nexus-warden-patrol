// 手机 App 测试 M03：站点重签证书以后，App 不能说「连不上站点」「站点上没有机器人」「今天没巡逻」；
// 要说证书变了、该怎么办，读不到的数据显示「未知」；登录页密码框不标红；站点卡片上能直接换新的站点码。
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:nexwar_patrol/l10n.dart';
import 'package:nexwar_patrol/net/site_client.dart';
import 'package:nexwar_patrol/store/site_store.dart';
import 'package:nexwar_patrol/ui/nw/nw_p1_entry.dart';
import 'package:nexwar_patrol/ui/site_duty_page.dart';
import 'package:nexwar_patrol/ui/site_list.dart';

import 'site_page_test.dart' show FakeApi;

SiteError get _cert =>
    SiteError(0, certChangedText, body: const <String, dynamic>{'seen': 'cd'}, kind: 'cert');

String _code(String name, String url, String fp) =>
    'D1MAXSITE1.${base64Url.encode(utf8.encode(jsonEncode({'n': name, 'u': url, 'f': fp}))).replaceAll('=', '')}';

void main() {
  setUp(() => appLang.value = AppLang.zh);

  testWidgets('值守页：证书变了说证书变了、怎么办；机器人、今天的巡逻读不到写「未知」，不写「没有」', (t) async {
    await t.binding.setSurfaceSize(const Size(800, 1400));
    addTearDown(() => t.binding.setSurfaceSize(null));
    final api = FakeApi('guard')
      ..robotsError = _cert
      ..todayError = _cert;
    await t.pumpWidget(MaterialApp(home: SiteDutyPage(api: api)));
    await t.pumpAndSettle();
    expect(find.byKey(SiteDutyPage.certChangedKey), findsOneWidget);
    expect(find.byKey(SiteDutyPage.siteDownKey), findsNothing, reason: '不说「连不上站点主机」');
    expect(find.textContaining('站点证书变了'), findsOneWidget);
    expect(find.textContaining('更新站点码'), findsOneWidget);
    expect(find.byKey(SiteDutyPage.unknownKey), findsOneWidget);
    expect(find.byKey(SiteDutyPage.noRobotsKey), findsNothing);
    expect(find.byKey(SiteDutyPage.todayUnknownKey), findsOneWidget);
    expect(find.text('今天没有巡逻。'), findsNothing);
    await t.pumpWidget(Container());
  });

  testWidgets('站点关了（不是证书）：照旧说连不上；读到过机器人以后断了，列表照旧显示', (t) async {
    await t.binding.setSurfaceSize(const Size(800, 1400));
    addTearDown(() => t.binding.setSurfaceSize(null));
    final api = FakeApi('guard');
    await t.pumpWidget(MaterialApp(home: SiteDutyPage(api: api)));
    await t.pumpAndSettle();
    api.robotsError = const SiteError(0, '无法连接站点：Connection refused', kind: 'net');
    await t.pump(const Duration(seconds: 31));
    await t.pumpAndSettle();
    expect(find.byKey(SiteDutyPage.siteDownKey), findsOneWidget);
    expect(find.byKey(SiteDutyPage.certChangedKey), findsNothing);
    expect(find.byKey(SiteDutyPage.unknownKey), findsNothing, reason: '读到过，留着旧的（横幅说是旧的）');
    await t.pumpWidget(Container());
  });

  testWidgets('登录页：证书变了说人话、密码框不标红；「更新站点码」换好指纹、名字账号留着，再登录', (t) async {
    await t.binding.setSurfaceSize(const Size(500, 1200));
    addTearDown(() => t.binding.setSurfaceSize(null));
    final store = MemorySiteStore([
      SiteEntry(name: '庄园', url: 'https://h:1', fingerprint: 'ab' * 32, username: 'gina')
    ]);
    final made = <SiteEntry>[];
    await t.pumpWidget(MaterialApp(
        home: SiteListPage(
            store: store,
            apiFactory: (e) {
              made.add(e);
              return FakeApi('guard')..loginError = e.fingerprint == 'ab' * 32 ? _cert : null;
            })));
    await t.pumpAndSettle();
    await t.tap(find.text('庄园'));
    await t.pumpAndSettle();
    await t.enterText(find.byKey(const Key('site-password')), 'pw');
    await t.tap(find.text('登录'));
    await t.pumpAndSettle();
    expect(find.textContaining('站点证书变了'), findsOneWidget);
    expect(find.textContaining('fingerprint'), findsNothing);
    final pw = t.widget<NwField>(find.ancestor(of: find.byKey(const Key('site-password')), matching: find.byType(NwField)));
    expect(pw.error, isFalse, reason: '不是密码错了');
    await t.tap(find.byKey(SiteLoginPage.newCodeKey));
    await t.pumpAndSettle();
    await t.enterText(find.byKey(newCodeFieldKey), _code('庄园', 'https://h:1', 'cd' * 32));
    await t.tap(find.byKey(newCodeOkKey));
    await t.pumpAndSettle();
    final saved = (await store.load()).single;
    expect(saved.fingerprint, 'cd' * 32);
    expect(saved.username, 'gina');
    expect(saved.name, '庄园');
    // 换好码直接回到登录页
    expect(find.byKey(const Key('site-password')), findsOneWidget);
    await t.enterText(find.byKey(const Key('site-password')), 'pw');
    await t.tap(find.text('登录'));
    await t.pumpAndSettle();
    expect(made.last.fingerprint, 'cd' * 32);
    expect(find.textContaining('站点证书变了'), findsNothing);
    await t.pumpWidget(Container());
  });

  testWidgets('站点卡片菜单：有「更新站点码」，删除不再叫人删掉重加', (t) async {
    final store = MemorySiteStore([
      SiteEntry(name: '庄园', url: 'https://h:1', fingerprint: 'ab' * 32, username: 'gina')
    ]);
    await t.pumpWidget(MaterialApp(home: SiteListPage(store: store, apiFactory: (_) => FakeApi('guard'))));
    await t.pumpAndSettle();
    await t.tap(find.byKey(const Key('site-menu-庄园')));
    await t.pumpAndSettle();
    expect(find.byKey(const Key('site-code-庄园')), findsOneWidget);
    expect(find.textContaining('删除重加'), findsNothing);
  });
}
