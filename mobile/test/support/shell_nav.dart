// App V2 外壳里走到某一页:切到「现场」、滚到目录里那一行、点它。各页的测试都用这一份。
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:nexwar_patrol/ui/nw/nw_shell.dart';
import 'package:nexwar_patrol/ui/nw/nw_site_dir.dart';

/// 切到「现场」目录(已经在目录里就什么都不做)。
Future<void> openSite(WidgetTester t) async {
  if (find.byType(SiteDirectory).evaluate().isEmpty) {
    await t.tap(find.byKey(NwShell.siteKey));
    await t.pumpAndSettle();
  }
}

/// 目录里点某一行。目录是个列表、还记着上次滚到哪:先回到顶上,再往下滚到那一行。
Future<void> openDir(WidgetTester t, SiteDest d) async {
  final sc = find.descendant(of: find.byType(SiteDirectory), matching: find.byType(Scrollable)).first;
  t.state<ScrollableState>(sc).position.jumpTo(0);
  await t.pumpAndSettle();
  await t.scrollUntilVisible(find.byKey(SiteDirectory.itemKey(d)), 200, scrollable: sc);
  // 横屏矮窄时那一行可能只露了个头:滚到视口正中再点
  await Scrollable.ensureVisible(t.element(find.byKey(SiteDirectory.itemKey(d))), alignment: 0.5);
  await t.pumpAndSettle();
  await t.tap(find.byKey(SiteDirectory.itemKey(d)));
  await t.pumpAndSettle();
}

/// 从「现在」一路走到目录里的某一页。
Future<void> openSiteDir(WidgetTester t, SiteDest d) async {
  await openSite(t);
  await openDir(t, d);
}
