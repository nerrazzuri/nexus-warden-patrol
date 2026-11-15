// App V2 稿 N-refuse：派单被拒不弹框 —— 顶上一条琥珀说明，「去处理」「知道了」一排等宽；知道了就收、才返回。
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:nexwar_patrol/net/site_client.dart';
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
}
