// 上传日志（日志设计 第 6 条）：谁都能传；站点给编号；登录着的能下载整包分享；连不上也能只分享 App 日志。
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:nexwar_patrol/net/app_log.dart';
import 'package:nexwar_patrol/ui/problem_report.dart';
import 'package:nexwar_patrol/ui/site_tabs.dart';
import 'package:nexwar_patrol/ui/nw/nw_theme.dart';

import 'site_page_test.dart' show FakeApi;

Widget _wrap(Widget w) => MaterialApp(theme: nwTheme(Brightness.dark), home: w);

void main() {
  test('App 日志：打码令牌口令，打包是 gzip，开头写手机情况', () {
    final dir = Directory.systemTemp.createTempSync('applog');
    final log = AppLog(maxBytes: 200)..open(dir);
    log.line('W', 'GET /api/x Bearer abc.def token=zzz {"password": "pw1"}');
    for (var i = 0; i < 20; i++) {
      log.line('I', 'line $i');
    }
    expect(File('${dir.path}/app.log.1').existsSync(), isTrue, reason: '超了换一份');
    final text = utf8.decode(gzip.decode(log.pack(header: 'HEAD')));
    expect(text.startsWith('HEAD'), isTrue);
    expect(text, isNot(contains('abc.def')));
    expect(text, isNot(contains('zzz')));
    expect(text, isNot(contains('pw1')));
    expect(text, contains('line 19'));
  });

  testWidgets('上传：拿到编号；登录着的能下载整包分享', (tester) async {
    final api = FakeApi('guard');
    final shared = <String>[];
    await tester.pumpWidget(_wrap(ProblemReportPage(
        api: api,
        robots: const ['A'],
        log: AppLog(),
        share: (name, bytes) async {
          shared.add(name);
          return true;
        })));
    await tester.enterText(find.byKey(ProblemReportPage.noteKey), '大门口停住');
    await tester.tap(find.byKey(ProblemReportPage.otherKey));     // A6-07：「只传到站点」收在「其他方式」里
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(ProblemReportPage.sendKey));
    await tester.pumpAndSettle();
    expect(find.text('NW-1110-7F3A'), findsOneWidget);
    expect(api.calls, contains('problem:大门口停住:'));
    await tester.tap(find.byKey(ProblemReportPage.shareBundleKey));
    await tester.pumpAndSettle();
    expect(api.calls, contains('problem-bundle:NW-1110-7F3A:tk'));
    expect(shared, ['nexwar_NW-1110-7F3A.tar.gz']);
  });

  testWidgets('发给工程师：一按就传站点开单、取整包、弹分享', (tester) async {
    final api = FakeApi('guard');
    final shared = <String>[];
    await tester.pumpWidget(_wrap(ProblemReportPage(
        api: api,
        log: AppLog(),
        share: (name, bytes) async {
          shared.add(name);
          return true;
        })));
    await tester.tap(find.byKey(ProblemReportPage.engineerKey));
    await tester.pumpAndSettle();
    expect(api.calls, containsAllInOrder(<String>['problem::', 'problem-bundle:NW-1110-7F3A:tk']));
    expect(shared, ['nexwar_NW-1110-7F3A.tar.gz']);
    expect(find.text('NW-1110-7F3A'), findsOneWidget);
  });

  testWidgets('连站点都没有：没有上传按钮，只分享 App 日志', (tester) async {
    Uint8List? got;
    await tester.pumpWidget(_wrap(ProblemReportPage(
        api: null,
        log: AppLog(),
        share: (name, bytes) async {
          got = bytes;
          return true;
        })));
    expect(find.byKey(ProblemReportPage.sendKey), findsNothing);
    await tester.tap(find.byKey(ProblemReportPage.engineerKey));
    await tester.pumpAndSettle();
    expect(gzip.decode(got!).isNotEmpty, isTrue);
  });

  testWidgets('易用性第 6 轮 A6-07：只有一个主按钮「发送」，说明跟按钮对得上；别的方式收在「其他方式」里', (tester) async {
    await tester.pumpWidget(_wrap(ProblemReportPage(api: FakeApi('guard'), log: AppLog(), share: (_, _) async => true)));
    expect(find.textContaining('按「发送」'), findsOneWidget);
    expect(find.textContaining('按「上传」'), findsNothing);
    expect(find.descendant(of: find.byKey(ProblemReportPage.engineerKey), matching: find.text('发送')), findsOneWidget);
    expect(find.byKey(ProblemReportPage.sendKey), findsNothing, reason: '收起来');
    expect(find.byKey(ProblemReportPage.shareAppKey), findsNothing, reason: '收起来');
    await tester.tap(find.byKey(ProblemReportPage.otherKey));
    await tester.pumpAndSettle();
    expect(find.byKey(ProblemReportPage.sendKey), findsOneWidget);
    expect(find.byKey(ProblemReportPage.shareAppKey), findsOneWidget);
  });

  testWidgets('A7-02：没登录站点时说明不提「站点开单」，按钮还是「发送」（发 App 日志），没有「其他方式」', (tester) async {
    await tester.pumpWidget(_wrap(ProblemReportPage(api: null, log: AppLog(), share: (_, _) async => true)));
    expect(find.textContaining('按「发送」'), findsOneWidget);
    expect(find.textContaining('问题单'), findsNothing);
    expect(find.descendant(of: find.byKey(ProblemReportPage.engineerKey), matching: find.text('发送')), findsOneWidget);
    expect(find.byKey(ProblemReportPage.otherKey), findsNothing);
  });

  testWidgets('A6-07：保安在「我的」页直接点「报问题」就到上传页（不用再进设置）', (tester) async {
    await tester.pumpWidget(_wrap(MeTab(api: FakeApi('guard'))));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(MeTab.reportKey));
    await tester.pumpAndSettle();
    expect(find.byType(ProblemReportPage), findsOneWidget);
  });
}
