// App V2 稿 N-refuse：派单被拒不弹框 —— 顶上一条琥珀说明，「去处理」「知道了」一排等宽；知道了就收、才返回。
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:nexwar_patrol/net/site_client.dart';
import 'package:nexwar_patrol/ui/nw/nw_theme.dart';
import 'package:nexwar_patrol/ui/refusal.dart';

import 'site_page_test.dart' show FakeApi;

void main() {
  testWidgets('不弹框；两个按钮等宽；「知道了」收掉说明、调用方才往下走', (t) async {
    final api = FakeApi('guard');
    var back = false;
    const e = SiteError(409, 'A 被叫停了', body: <String, dynamic>{'reason_code': 'held'});
    await t.pumpWidget(MaterialApp(
        home: Scaffold(
            body: Builder(
                builder: (c) => TextButton(
                    onPressed: () async {
                      await showRefusal(c, api, e, robotId: 'A');
                      back = true;
                    },
                    child: const Text('go'))))));
    await t.tap(find.text('go'));
    await t.pumpAndSettle();
    expect(find.byType(AlertDialog), findsNothing);
    expect(find.byKey(refusalDialogKey), findsOneWidget);
    expect(find.text('没派出去'), findsOneWidget);
    expect(t.getSize(find.byKey(refusalActionKey)).width, t.getSize(find.byKey(refusalAckKey)).width);
    expect(back, isFalse);
    await t.tap(find.byKey(refusalAckKey));
    await t.pumpAndSettle();
    expect(find.byKey(refusalDialogKey), findsNothing);
    expect(back, isTrue);
    expect(api.calls.where((c) => c.startsWith('resume')), isEmpty);
  });

  for (final (outer, page) in [(Brightness.dark, Brightness.light), (Brightness.light, Brightness.dark)]) {
    testWidgets('易用性 build 37 复测 P1：页面主题跟外面不一样（外面 ${outer.name}、页 ${page.name}），横幅底色和字是同一套', (t) async {
      final api = FakeApi('guard');
      const e = SiteError(409, 'A 正在执行任务 p1', body: <String, dynamic>{'reason_code': 'busy'});
      await t.pumpWidget(MaterialApp(
          theme: nwTheme(Brightness.light),
          darkTheme: nwTheme(Brightness.dark),
          themeMode: outer == Brightness.dark ? ThemeMode.dark : ThemeMode.light,
          home: Scaffold(
              body: Theme(
                  data: nwTheme(page),
                  child: Builder(
                      builder: (c) => TextButton(
                          onPressed: () => showRefusal(c, api, e, robotId: 'A', title: '趴下'),
                          child: const Text('go')))))));
      await t.tap(find.text('go'));
      await t.pumpAndSettle();
      final want = page == Brightness.dark ? NwColors.dark : NwColors.light;
      final banner = t.widget<MaterialBanner>(find.byKey(refusalDialogKey));
      expect(banner.backgroundColor, want.warningSoft);
      final head = t.widget<Text>(find.text('趴下：没成'));
      expect(head.style?.color, want.text, reason: '字跟底色同一套主题，不会米色底白字');
      final ack = t.widget<Text>(find.text('知道了'));
      final ackColor = DefaultTextStyle.of(t.element(find.text('知道了'))).style.color ?? ack.style?.color;
      expect(ackColor, isNot(want.warningSoft));
    });
  }
}
