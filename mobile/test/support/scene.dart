// App V2「这件事」页是一条长列表：要点的东西可能还没建出来，先滚到它、放到视口中间。
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:nexwar_patrol/ui/site_alert_scene.dart';

Finder _list() => find.descendant(of: find.byType(SiteAlertScenePage), matching: find.byType(Scrollable)).first;

/// 滚到 [f]（找到为止；整页滚完都没有就照旧返回，让调用方的 expect 去说）。
Future<Finder> sceneShow(WidgetTester t, Finder f) async {
  final sc = _list();
  t.state<ScrollableState>(sc).position.jumpTo(0);
  await t.pump();
  try {
    await t.scrollUntilVisible(f, 200, scrollable: sc, maxScrolls: 40);
  } on StateError {
    return f;
  }
  if (f.evaluate().isNotEmpty) {
    await Scrollable.ensureVisible(t.element(f.first), alignment: 0.5);
    await t.pump();
  }
  return f;
}

/// 滚到那个键、点它、等完。
Future<void> sceneTap(WidgetTester t, Key k) async {
  await sceneShow(t, find.byKey(k));
  await t.tap(find.byKey(k));
  await t.pumpAndSettle();
}
