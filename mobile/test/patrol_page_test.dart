// App V2 稿 N-dispatch：派巡逻是整页（深色），上面这台的画面，写明临时巡逻不进日程；派出 / 取消钉在底下一排等宽。
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:nexwar_patrol/ui/patrol_dispatch.dart';
import 'package:nexwar_patrol/ui/site_video.dart';

import 'site_page_test.dart' show FakeApi;

void main() {
  testWidgets('整页、深色、有画面、写不进日程；两个按钮等宽；取消回 null', (t) async {
    final api = FakeApi('guard');
    String? got = 'x';
    await t.pumpWidget(MaterialApp(
        home: Scaffold(
            body: Builder(
                builder: (c) => TextButton(
                    onPressed: () async => got = await showPatrolSheet(c, api, 'A'), child: const Text('go'))))));
    await t.tap(find.text('go'));
    await t.pumpAndSettle();
    expect(find.byType(BottomSheet), findsNothing);
    expect(find.text('派 A 巡逻'), findsOneWidget);
    expect(find.text('临时巡逻，不进日程'), findsOneWidget);
    expect(find.byType(SiteVideo), findsOneWidget);
    expect(Theme.of(t.element(find.text('临时巡逻，不进日程'))).brightness, Brightness.dark);
    final send = find.byKey(patrolSendKey), cancel = find.text('取消');
    expect(t.getSize(send).width, closeTo(t.getSize(find.ancestor(of: cancel, matching: find.byType(Expanded)).first).width, 1));
    await t.tap(cancel);
    await t.pumpAndSettle();
    expect(got, isNull);
    await t.pumpWidget(Container());
  });
}
