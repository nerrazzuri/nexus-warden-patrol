// 1.1-5 值班簿：列一天（手写的 + 站点记的）；写一条；更正另写一条带 corrects、原来那条划掉；只读不能写；
// 报警详情里分享事件报告（交给分享面板的是站点出的那一页）、写进值班簿带上报警号。竖屏 390×1400。
import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:nexwar_patrol/model/alert.dart';
import 'package:nexwar_patrol/ui/site_alert_scene.dart';
import 'package:nexwar_patrol/ui/site_ob.dart';

import 'site_page_test.dart' show FakeApi;
import 'support/scene.dart';

final _now = DateTime(2026, 11, 28, 15);
List<Map<String, dynamic>> _rows() => <Map<String, dynamic>>[
      <String, dynamic>{'at_ms': DateTime(2026, 11, 28, 9).millisecondsSinceEpoch, 'source': 'manual', 'category': 'visitor',
        'text': '送货车 WXY 1234 进', 'author': 'gina', 'robot': '', 'id': 3, 'corrected_by': 4},
      <String, dynamic>{'at_ms': DateTime(2026, 11, 28, 9, 5).millisecondsSinceEpoch, 'source': 'manual', 'category': 'visitor',
        'text': '车牌是 WXY 1243', 'author': 'gina', 'robot': '', 'id': 4, 'corrects': 3},
      <String, dynamic>{'at_ms': DateTime(2026, 11, 28, 10).millisecondsSinceEpoch, 'source': 'alarm', 'category': 'alarm',
        'text': 'P1 北区有人闯入', 'author': '', 'robot': 'A'},
    ];

Future<void> _open(WidgetTester t, FakeApi api) async {
  await t.binding.setSurfaceSize(const Size(390, 1400));
  addTearDown(() => t.binding.setSurfaceSize(null));
  await t.pumpWidget(MaterialApp(home: OccurrenceBookPage(api: api, now: () => _now)));
  await t.pumpAndSettle();
}

void main() {
  testWidgets('列这一天：更正过的划掉、写由哪条更正；只看手写的', (t) async {
    final api = FakeApi('guard')..obList = _rows();
    await _open(t, api);
    expect(find.text('今天 2026-11-28'), findsOneWidget);
    expect(find.text('已由 #4 更正'), findsOneWidget);
    expect(find.text('更正 #3：车牌是 WXY 1243'), findsOneWidget);
    expect(find.byKey(OccurrenceBookPage.fixKey(3)), findsNothing, reason: '更正过的不再更正');
    expect(find.text('P1 北区有人闯入'), findsOneWidget);
    await t.tap(find.byKey(const Key('ob-manual-only')));
    await t.pumpAndSettle();
    expect(find.text('P1 北区有人闯入'), findsNothing);
    expect(t.takeException(), isNull);
  });

  testWidgets('写一条、更正一条', (t) async {
    final api = FakeApi('guard')..obList = _rows();
    await _open(t, api);
    await t.tap(find.byKey(OccurrenceBookPage.writeKey));
    await t.pumpAndSettle();
    await t.enterText(find.byKey(const Key('ob-text')), '北区围栏查过');
    await t.tap(find.byKey(const Key('ob-save')));
    await t.pumpAndSettle();
    expect(api.calls, contains('ob observation 北区围栏查过 - - -'));
    await t.tap(find.byKey(OccurrenceBookPage.fixKey(4)));
    await t.pumpAndSettle();
    expect(find.text('更正第 #4 条'), findsOneWidget);
    await t.enterText(find.byKey(const Key('ob-text')), '车牌是 WXY 1248');
    await t.tap(find.byKey(const Key('ob-save')));
    await t.pumpAndSettle();
    expect(api.calls, contains('ob visitor 车牌是 WXY 1248 - 4 -'));
  });

  testWidgets('只读账号：不能写、不能更正', (t) async {
    final api = FakeApi('viewer')..obList = _rows();
    await _open(t, api);
    expect(find.byKey(OccurrenceBookPage.writeKey), findsNothing);
    expect(find.byKey(OccurrenceBookPage.fixKey(4)), findsNothing);
  });

  testWidgets('报警详情：分享事件报告、写进值班簿带上报警号', (t) async {
    await t.binding.setSurfaceSize(const Size(390, 1400));
    addTearDown(() => t.binding.setSurfaceSize(null));
    (String, Uint8List)? shared;
    shareHtml = (name, b) async {
      shared = (name, b);
      return true;
    };
    final api = FakeApi('guard');
    final a = Alert.fromWire(<String, dynamic>{
      'key': 'A/intrusion#1', 'level': 'P1', 'kind': 'intrusion', 'robot': 'A', 'title': '北区有人闯入', 'detail': '',
      'first_ms': 1, 'last_ms': 1, 'count': 1, 'acked_by': '', 'acked_ms': null, 'resolved_by': '', 'resolved_ms': null,
      'escalated': 0, 'context': <String, dynamic>{},
    });
    await t.pumpWidget(MaterialApp(home: SiteAlertScenePage(api: api, alert: a)));
    await t.pumpAndSettle();
    await sceneTap(t, SiteAlertScenePage.reportKey);
    expect(api.calls, contains('report A/intrusion#1'));
    expect(shared!.$1, 'incident-report-A_intrusion_1.html');
    expect(utf8.decode(shared!.$2), startsWith('<!doctype html>'));
    expect(find.textContaining('存成 PDF'), findsOneWidget);
    await sceneTap(t, SiteAlertScenePage.obKey);
    await t.enterText(find.byKey(const Key('ob-text')), '到北区看了，是猫');
    await t.tap(find.byKey(const Key('ob-save')));
    await t.pumpAndSettle();
    expect(api.calls, contains('ob incident 到北区看了，是猫 - - A/intrusion#1'));
    expect(find.textContaining('已写进值班簿'), findsOneWidget);
  });
}
