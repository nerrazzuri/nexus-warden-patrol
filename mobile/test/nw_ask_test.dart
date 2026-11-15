// App V2「不弹窗」：页内就地问一句（NwAsk）。
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:nexwar_patrol/ui/nw/nw_ask.dart';
import 'package:nexwar_patrol/ui/nw/nw_theme.dart';

class _Page extends StatefulWidget {
  final List<String> log;
  const _Page(this.log);
  @override
  State<_Page> createState() => _PageState();
}

class _PageState extends State<_Page> with NwAsk {
  @override
  Widget build(BuildContext context) => Scaffold(
      body: ListView(children: [
        askStrip(),
        for (var i = 0; i < 30; i++) SizedBox(height: 60, child: Text('row $i')),
        TextButton(
            key: const Key('del'),
            onPressed: () async => widget.log.add('yes=${await askYes('Delete?', ok: 'Delete', okKey: const Key('ok'), danger: true)}'),
            child: const Text('delete')),
        TextButton(
            key: const Key('pick'),
            onPressed: () async => widget.log.add('pick=${await ask<String>(title: 'Which', choices: const [
                  AskChoice('A', 'a', key: Key('a')),
                  AskChoice('B', 'b', key: Key('b')),
                  AskChoice('C', 'c', key: Key('c')),
                ])}'),
            child: const Text('pick')),
      ]));
}

void main() {
  testWidgets('不弹窗：页里一条，滚到看得见；确认回 true，取消回 false；再问一句顶掉上一句', (t) async {
    final log = <String>[];
    await t.pumpWidget(MaterialApp(theme: nwTheme(Brightness.light), home: _Page(log)));
    await t.scrollUntilVisible(find.byKey(const Key('del')), 300);
    await t.tap(find.byKey(const Key('del')));
    await t.pumpAndSettle();
    expect(find.byType(Dialog), findsNothing);
    expect(find.byKey(const Key('ok')), findsOneWidget);
    expect(t.getRect(find.byKey(const Key('ok'))).top, lessThan(600), reason: '滚到看得见');
    await t.tap(find.byKey(const Key('ok')));
    await t.pumpAndSettle();
    expect(log, ['yes=true']);
    expect(find.byKey(const Key('ok')), findsNothing);

    await t.scrollUntilVisible(find.byKey(const Key('del')), 300);
    await t.tap(find.byKey(const Key('del')));
    await t.pumpAndSettle();
    await t.tap(find.text('取消'));
    await t.pumpAndSettle();
    expect(log.last, 'yes=false');

    await t.scrollUntilVisible(find.byKey(const Key('del')), 300);
    await t.tap(find.byKey(const Key('del')));
    await t.pumpAndSettle();
    await t.scrollUntilVisible(find.byKey(const Key('pick')), 300);
    await t.tap(find.byKey(const Key('pick')));
    await t.pumpAndSettle();
    expect(log.last, 'yes=false', reason: '上一句被顶掉算取消');
    await t.tap(find.byKey(const Key('c')));
    await t.pumpAndSettle();
    expect(log.last, 'pick=c');
  });

  testWidgets('页面关了：在问的那句回 false', (t) async {
    final log = <String>[];
    await t.pumpWidget(MaterialApp(theme: nwTheme(Brightness.light), home: _Page(log)));
    await t.scrollUntilVisible(find.byKey(const Key('del')), 300);
    await t.tap(find.byKey(const Key('del')));
    await t.pumpAndSettle();
    await t.pumpWidget(const SizedBox());
    await t.pump();
    expect(log, ['yes=false']);
  });
}
