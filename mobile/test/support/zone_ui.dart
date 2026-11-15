// 区域页（App V2 稿 S-zones）：图在上（横屏在左），一栏常开：工具一排、正在画的、区域列表、确认、说明。
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';

/// 说明栏一直开着：没事做（留着给老测试）。
Future<void> openZonePanel(WidgetTester t) async {}

/// 说明栏一直开着、不盖图：没事做。
Future<void> closeZonePanel(WidgetTester t) async {}

/// 工具一排里的一样（画禁行区、限速……）：滚到看得见再点。
Future<void> tapZoneMenu(WidgetTester t, Key item) async {
  await t.ensureVisible(find.byKey(item));
  await t.pump();
  await t.tap(find.byKey(item));
}
