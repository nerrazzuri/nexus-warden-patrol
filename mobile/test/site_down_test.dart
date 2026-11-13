// 11-05 现场第 36 条：笔记本当站点主机自己重启了，机器人掉线 20 多分钟才发现。值守页连不上站点要
// 一眼看得出（横幅写从几点起、数据是旧的），连回来自己消失；别的错误也不该一直挂着。
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:nexwar_patrol/net/site_client.dart';
import 'package:nexwar_patrol/ui/site_duty_page.dart';

import 'site_page_test.dart' show FakeApi;

void main() {
  testWidgets('连不上站点：值守页顶上横幅说站点主机连不上、数据是旧的；连回来横幅消失', (t) async {
    await t.binding.setSurfaceSize(const Size(800, 900));
    addTearDown(() => t.binding.setSurfaceSize(null));
    final api = FakeApi('guard');
    await t.pumpWidget(MaterialApp(home: SiteDutyPage(api: api)));
    await t.pumpAndSettle();
    expect(find.byKey(SiteDutyPage.siteDownKey), findsNothing);
    api.robotsError = const SiteError(0, '无法连接站点：Connection refused');
    await t.pump(const Duration(seconds: 31));
    await t.pumpAndSettle();
    expect(find.byKey(SiteDutyPage.siteDownKey), findsNothing, reason: 'A6-08：一次没连上先不挂');
    await t.pump(kSiteDownGrace);
    await t.pumpAndSettle();
    expect(find.byKey(SiteDutyPage.siteDownKey), findsOneWidget);
    expect(find.descendant(of: find.byKey(SiteDutyPage.siteDownKey), matching: find.textContaining('连不上站点主机')),
        findsOneWidget);
    api.robotsError = null;
    await t.pump(const Duration(seconds: 31));
    await t.pumpAndSettle();
    expect(find.byKey(SiteDutyPage.siteDownKey), findsNothing);
    expect(find.textContaining('Connection refused'), findsNothing, reason: '连回来以后旧的错误不留着');
    await t.pumpWidget(Container());
  });

  testWidgets('A6-08：一次没连上、15 秒内又连上了 —— 不闪「连不上站点主机」红条', (t) async {
    await t.binding.setSurfaceSize(const Size(800, 900));
    addTearDown(() => t.binding.setSurfaceSize(null));
    final api = FakeApi('guard');
    await t.pumpWidget(MaterialApp(home: SiteDutyPage(api: api)));
    await t.pumpAndSettle();
    api.robotsError = const SiteError(0, '无法连接站点：Connection reset');
    await t.pump(const Duration(seconds: 31));            // 30 秒那一轮没连上
    await t.pumpAndSettle();
    expect(find.byKey(SiteDutyPage.siteDownKey), findsNothing);
    api.robotsError = null;                               // 网络其实是好的
    await t.pump(kSiteDownGrace);                         // 满 15 秒再试一次：连上了
    await t.pumpAndSettle();
    expect(find.byKey(SiteDutyPage.siteDownKey), findsNothing);
    await t.pump(const Duration(seconds: 31));
    await t.pumpAndSettle();
    expect(find.byKey(SiteDutyPage.siteDownKey), findsNothing);
    await t.pumpWidget(Container());
  });
}
