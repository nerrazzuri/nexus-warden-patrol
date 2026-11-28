import 'dart:async';
// 1.1-4 远程喊话：机器人报了 `talk` 才有「按住说话」；按住录、松开把录音传给站点（m4a）；点一下就松开的不发；
// 报了 `mic` 才有「听回话」，点了请机器人录 10 秒；最近的对讲能点开听。竖屏 390×1400。
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:nexwar_patrol/ui/site_deter.dart';
import 'package:nexwar_patrol/ui/site_talk.dart';

import 'site_page_test.dart' show FakeApi;

class _FakeRecorder implements TalkRecorder {
  bool allow = true;
  String? path;
  Completer<bool>? gate;
  int stops = 0;
  @override
  Future<bool> permitted() async => gate != null ? gate!.future : allow;
  @override
  Future<void> start(String p) async {
    path = p;
    File(p).writeAsBytesSync(List<int>.filled(4000, 7));
  }
  @override
  Future<String?> stop() async {
    stops++;
    return path;
  }
  @override
  Future<void> dispose() async {}
}

const Map<String, dynamic> _caps = <String, dynamic>{
  'outputs': <String>['speaker', 'mic'],
  'clips': <String>[],
  'tts': false,
  'talk': true,
  'max_s': 600.0,
};

void main() {
  late _FakeRecorder rec;
  late Directory tmp;
  setUp(() {
    rec = _FakeRecorder();
    makeTalkRecorder = () => rec;
    tmp = Directory.systemTemp.createTempSync('talk-test');
    talkTempDir = () async => tmp;
  });
  tearDown(() => tmp.deleteSync(recursive: true));

  Future<void> open(WidgetTester t, FakeApi api, {Map<String, dynamic> caps = _caps}) async {
    await t.binding.setSurfaceSize(const Size(390, 1400));
    addTearDown(() => t.binding.setSurfaceSize(null));
    await t.pumpWidget(MaterialApp(home: SiteDeterPage(api: api, robotId: 'A', caps: caps)));
    await t.pumpAndSettle();
  }

  testWidgets('按住说话：按住录、松开传给站点（m4a）；说正在放', (t) async {
    final api = FakeApi('guard');
    await open(t, api);
    expect(find.byKey(const Key('deter-mic')), findsNothing, reason: '麦克风不单列一行');
    final g = await t.startGesture(t.getCenter(find.byKey(SiteTalk.holdKey)));
    await t.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 50)));
    await t.pump();
    expect(find.textContaining('松开就发'), findsOneWidget);
    await t.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 700)));
    await g.up();
    await t.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 100)));
    await t.pumpAndSettle();
    expect(api.talked, [(4000, 'audio/mp4')]);
    expect(find.text('A：正在放你说的话。'), findsOneWidget);
    expect(File(rec.path!).existsSync(), isFalse, reason: '传完删掉本机的录音');
  });

  testWidgets('点一下就松开：不发，说太短', (t) async {
    final api = FakeApi('guard');
    await open(t, api);
    final g = await t.startGesture(t.getCenter(find.byKey(SiteTalk.holdKey)));
    await t.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 30)));
    await t.pump();
    await g.up();
    await t.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 50)));
    await t.pumpAndSettle();
    expect(api.talked, isEmpty);
    expect(find.textContaining('太短了'), findsOneWidget);
  });

  testWidgets('没有麦克风权限：说去手机设置里开', (t) async {
    final api = FakeApi('guard');
    rec.allow = false;
    await open(t, api);
    final g = await t.startGesture(t.getCenter(find.byKey(SiteTalk.holdKey)));
    await t.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 30)));
    await g.up();
    await t.pumpAndSettle();
    expect(find.textContaining('没有麦克风权限'), findsOneWidget);
    expect(api.talked, isEmpty);
  });

  testWidgets('听回话：请机器人录 10 秒；最近的对讲有回话能点开听；没报 mic 没有这个按钮', (t) async {
    final api = FakeApi('guard')
      ..talkList = <Map<String, dynamic>>[
        <String, dynamic>{'id': 'fedcba9876543210', 'direction': 'in', 'account': 'gina', 'created_ms': 1, 'state': 'recorded', 'bytes': 3200},
      ];
    String? played;
    playTalk = (b, id) async => played = id;
    await open(t, api);
    await t.tap(find.byKey(SiteTalk.listenKey));
    await t.pumpAndSettle();
    expect(api.calls, contains('listen A 10'));
    await t.tap(find.descendant(of: find.byKey(SiteTalk.rowKey('fedcba9876543210')), matching: find.byIcon(Icons.play_arrow_rounded)));
    await t.pumpAndSettle();
    expect(played, 'fedcba9876543210');
    await t.pumpWidget(const SizedBox());
    await open(t, FakeApi('guard'), caps: <String, dynamic>{..._caps, 'outputs': <String>['speaker']});
    expect(find.byKey(SiteTalk.listenKey), findsNothing);
    expect(find.byKey(SiteTalk.holdKey), findsOneWidget);
    await t.pumpWidget(const SizedBox());
    await open(t, FakeApi('guard'), caps: <String, dynamic>{..._caps, 'talk': false});
    expect(find.byKey(SiteTalk.holdKey), findsNothing, reason: '老机器人没有按住说话');
  });

  testWidgets('外审 1.1 #12：等麦克风权限的时候松了手 —— 不录、不发', (t) async {
    final api = FakeApi('guard');
    rec.gate = Completer<bool>();
    await open(t, api);
    final g = await t.startGesture(t.getCenter(find.byKey(SiteTalk.holdKey)));
    await t.pump();
    await g.up();
    await t.pump();
    rec.gate!.complete(true);
    await t.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 50)));
    await t.pumpAndSettle();
    expect(rec.path, isNull, reason: '松手以后不开始录');
    expect(api.talked, isEmpty);
    expect(find.textContaining('松开就发'), findsNothing);
  });

  testWidgets('外审 1.1 第 2 轮 #11：听回话一直问到站点标了结论（超过 32 秒也问）；过了 90 秒不再挡按钮', (t) async {
    final api = FakeApi('guard');
    await open(t, api);
    api.talkList = <Map<String, dynamic>>[
      <String, dynamic>{'id': 'aaaabbbbccccdddd', 'direction': 'in', 'account': 'gina',
        'created_ms': DateTime.now().millisecondsSinceEpoch, 'state': 'waiting', 'bytes': 0},
    ];
    await t.tap(find.byKey(SiteTalk.listenKey));
    await t.pump();
    await t.pump(const Duration(seconds: 2));
    await t.pump();
    expect(t.widget<ButtonStyleButton>(find.byKey(SiteTalk.listenKey)).onPressed, isNull,
        reason: '等回话的时候不能再按');
    await t.pump(const Duration(seconds: 40));
    api.talkList = <Map<String, dynamic>>[
      <String, dynamic>{..._first(api), 'state': 'failed', 'error': '超时'},
    ];
    await t.pump(const Duration(seconds: 2));
    await t.pump();
    expect(find.textContaining('没录到回话'), findsOneWidget);
    expect(t.widget<ButtonStyleButton>(find.byKey(SiteTalk.listenKey)).onPressed, isNotNull,
        reason: '站点标了没录到：按钮回来');
    // 站点没标、手机这边过了 90 秒：也不再挡
    api.talkList = <Map<String, dynamic>>[
      <String, dynamic>{..._first(api), 'state': 'waiting',
        'created_ms': DateTime.now().millisecondsSinceEpoch - 100000},
    ];
    await t.pump(const Duration(seconds: 2));
    await t.pumpWidget(const SizedBox());
    await open(t, api);
    expect(find.textContaining('没录到回话'), findsOneWidget);
    await t.pump(const Duration(seconds: 120));
  });
}

Map<String, dynamic> _first(FakeApi api) => api.talkList.first;
