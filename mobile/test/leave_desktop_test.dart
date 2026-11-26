// 易用性 37 第十二轮 P2-4：测试反映 Linux 正式版点「退出」后站点列表被一层暗色盖住、什么都点不动。
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:nexwar_patrol/store/site_store.dart';
import 'package:nexwar_patrol/ui/nw/nw_shell.dart';
import 'package:nexwar_patrol/ui/nw/nw_site_dir.dart';
import 'package:nexwar_patrol/ui/site_list.dart';
import 'package:nexwar_patrol/ui/site_tabs.dart' show leaveConfirmKey;

import 'site_page_test.dart' show FakeApi;

void main() {
  for (final size in const [Size(1280, 800), Size(400, 1400)]) {
    for (final role in ['admin', 'guard']) {
      testWidgets('易用性 37 第十二轮 P2：Linux 上「退出站点」回站点列表，不留暗层、列表能点 [$role] $size', (t) async {
        debugDefaultTargetPlatformOverride = TargetPlatform.linux;
        await t.binding.setSurfaceSize(size);
        final api = FakeApi(role);
        final store = MemorySiteStore([
          SiteEntry(name: '庄园', url: 'https://h:1', fingerprint: 'ab' * 32, username: 'gina')
        ]);
        await t.pumpWidget(MaterialApp(home: SiteListPage(store: store, apiFactory: (_) => api)));
        await t.pumpAndSettle();
        await t.tap(find.text('庄园'));
        await t.pumpAndSettle();
        await t.enterText(find.byKey(const Key('site-password')), 'pw');
        await t.tap(find.text('登录'));
        await t.pumpAndSettle();
        expect(find.byType(NwShell), findsOneWidget);
        await t.tap(find.byKey(NwShell.siteKey));
        await t.pumpAndSettle();
        await t.scrollUntilVisible(find.byKey(SiteDirectory.leaveKey), 200,
            scrollable: find.descendant(of: find.byType(SiteDirectory), matching: find.byType(Scrollable)).first);
        await t.pumpAndSettle();
        await t.tap(find.byKey(SiteDirectory.leaveKey));
        await t.pumpAndSettle();
        await t.scrollUntilVisible(find.byKey(leaveConfirmKey), 200,
            scrollable: find.descendant(of: find.byType(SiteDirectory), matching: find.byType(Scrollable)).first);
        await t.pumpAndSettle();
        await t.tap(find.byKey(leaveConfirmKey));
        for (var i = 0; i < 40; i++) {
          await t.pump(const Duration(milliseconds: 50));
        }
        await t.pumpAndSettle();
        expect(t.takeException(), isNull);
        expect(find.byType(NwShell), findsNothing);
        final barriers = t.widgetList<ModalBarrier>(find.byType(ModalBarrier)).where((b) => b.color != null && b.color!.a > 0);
        expect(barriers, isEmpty);
        await t.tap(find.text('庄园'));
        await t.pumpAndSettle();
        expect(find.byKey(const Key('site-password')), findsOneWidget, reason: '站点列表还能点');
        debugDefaultTargetPlatformOverride = null;
        await t.binding.setSurfaceSize(null);
      });
    }
  }
}
