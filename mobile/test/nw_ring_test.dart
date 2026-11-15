// App V2 来报警全屏页（稿 N-ring）：我来处理 / 只看画面 / 静音 2 分钟；别人接手了自己关；外壳接住后台值守拉起来的那一条。
import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:nexwar_patrol/model/alert.dart';
import 'package:nexwar_patrol/net/background_watch.dart';
import 'package:nexwar_patrol/ui/nw/nw_ring.dart';
import 'package:nexwar_patrol/store/site_store.dart';
import 'package:nexwar_patrol/ui/nw/nw_shell.dart';
import 'package:nexwar_patrol/ui/site_list.dart';
import 'package:nexwar_patrol/ui/site_alert_scene.dart';

import 'site_page_test.dart' show FakeApi;

final _t0 = DateTime(2026, 11, 15, 23, 47).millisecondsSinceEpoch;

Map<String, dynamic> _wire({String ackedBy = '', int? ackedMs}) => <String, dynamic>{
      'key': 'cctv:3/intrusion#9', 'level': 'P1', 'kind': 'intrusion', 'audience': 'intrusion', 'robot': 'A',
      'title': '北门翻越', 'first_ms': _t0, 'last_ms': _t0, 'count': 1, 'acked_by': ackedBy, 'acked_ms': ackedMs,
      'channel': 'sound', 'escalated': 2,
      'context': <String, dynamic>{'camera': 'Camera 3', 'zone': 'North gate', 'exit': 'Building 2',
        'intercept': <String, dynamic>{'name': 'North gate', 'map_id': 'm', 'map_version': '1', 'x': 1.0, 'y': 1.0}},
    };

class _Calls {
  final muted = <String>[];
  var done = 0;
  bool canMute = true;
}

Future<_Calls> _open(WidgetTester t, FakeApi api, {bool canMute = true}) async {
  t.view.physicalSize = const Size(390 * 2, 844 * 2);
  t.view.devicePixelRatio = 2;
  addTearDown(t.view.reset);
  final calls = _Calls()..canMute = canMute;
  api.alertRows = [_wire()];
  await t.pumpWidget(MaterialApp(
      home: Builder(
          builder: (c) => TextButton(
              onPressed: () => Navigator.push(
                  c,
                  MaterialPageRoute<void>(
                      builder: (_) => RingPage(
                          api: api,
                          alert: Alert.fromWire(_wire()),
                          site: 'estate-1',
                          now: () => DateTime.fromMillisecondsSinceEpoch(_t0 + 60000),
                          every: const Duration(seconds: 3),
                          mute: (k) async {
                            calls.muted.add(k);
                            return calls.canMute;
                          },
                          done: () async => calls.done++))),
              child: const Text('home')))));
  await t.tap(find.text('home'));
  await t.pumpAndSettle();
  return calls;
}

void main() {
  test('外审 App-V2-3 I6：认站点按证书指纹（同名不算），没有指纹按地址，都没有才按名字', () {
    final fa = 'ab' * 32, fb = 'cd' * 32;
    final r = RingRequest('k', const <String, dynamic>{}, '庄园', url: 'https://a:8443', fingerprint: fa);
    expect(r.isFor(name: '庄园', urls: ['https://b:8443'], fingerprint: fb), isFalse, reason: '同名的另一个站点');
    expect(r.isFor(name: '别的名字', urls: ['https://x'], fingerprint: fa.toUpperCase()), isTrue, reason: '指纹一样就是它');
    final noFp = RingRequest('k', const <String, dynamic>{}, '庄园', url: 'https://a:8443/');
    expect(noFp.isFor(name: '庄园', urls: ['https://b:8443'], fingerprint: fa), isFalse);
    expect(noFp.isFor(name: '庄园', urls: ['https://b:8443', 'https://A:8443'], fingerprint: fa), isTrue, reason: '备用地址也算');
    const legacy = RingRequest('k', <String, dynamic>{}, '庄园');
    expect(legacy.isFor(name: '庄园', urls: ['https://a'], fingerprint: fa), isTrue);
    expect(legacy.isFor(name: '别的', urls: ['https://a'], fingerprint: fa), isFalse);
  });

  testWidgets('外审 App-V2-4 N4：没登录时「登录后处理」：先收锁屏显示（登录页不在锁屏上），再去登录', (t) async {
    var done = 0, signIn = 0;
    await t.pumpWidget(MaterialApp(
        home: Builder(
            builder: (c) => TextButton(
                onPressed: () => Navigator.push(
                    c,
                    MaterialPageRoute<void>(
                        builder: (_) => RingPage(
                            api: null,
                            alert: Alert.fromWire(_wire()),
                            site: '庄园',
                            onSignIn: () => signIn++,
                            mute: (_) async => true,
                            done: () async => done++))),
                child: const Text('home')))));
    await t.tap(find.text('home'));
    await t.pumpAndSettle();
    await t.tap(find.byKey(RingPage.signInKey));
    await t.pumpAndSettle();
    expect(find.byType(RingPage), findsNothing);
    expect((done, signIn), (1, 1));
  });

  testWidgets('外审 App-V2-3 I5：没登录（冷启动）来报警也整屏弹；「登录后处理」去那个站点的登录页', (t) async {
    t.view.physicalSize = const Size(390 * 2, 844 * 2);
    t.view.devicePixelRatio = 2;
    addTearDown(t.view.reset);
    final store = MemorySiteStore([
      SiteEntry(name: '庄园', url: 'https://a:8443', fingerprint: 'ab' * 32, username: 'gina'),
      SiteEntry(name: '庄园', url: 'https://b:8443', fingerprint: 'cd' * 32, username: 'olga'),
    ]);
    pendingRing.value = RingRequest('cctv:3/intrusion#9', _wire(), '庄园', url: 'https://b:8443', fingerprint: 'cd' * 32);
    addTearDown(() => pendingRing.value = null);
    await t.pumpWidget(MaterialApp(home: SiteListPage(store: store, apiFactory: (_) => FakeApi('guard'))));
    await t.pumpAndSettle();
    expect(find.byType(RingPage), findsOneWidget);
    expect(find.byKey(RingPage.takeKey), findsNothing, reason: '没登录不能接手');
    expect(find.byKey(RingPage.muteKey), findsOneWidget, reason: '能静音');
    await t.tap(find.byKey(RingPage.signInKey));
    await t.pumpAndSettle();
    expect(find.byType(RingPage), findsNothing);
    expect(find.byType(SiteLoginPage), findsOneWidget);
    expect(t.widget<SiteLoginPage>(find.byType(SiteLoginPage)).site.username, 'olga', reason: '同名的两个里按指纹挑对的那个');
    expect(pendingRing.value, isNotNull, reason: '留着：登上了外壳接着弹');
    await t.pumpWidget(Container());
  });

  testWidgets('照稿：站点 · 几点、标题、P1 · 摄像头 · 防区 · 往哪去、派了谁、一直响到有人接手；三个按钮', (t) async {
    await _open(t, FakeApi('guard'));
    expect(find.text('estate-1 · 23:47'), findsOneWidget);
    expect(find.text('P1 · Camera 3 · North gate · 往 Building 2 去'), findsOneWidget);
    expect(find.text('A 已派去 North gate'), findsOneWidget);
    expect(find.textContaining('一直响到有人接手'), findsOneWidget);
    for (final k in [RingPage.takeKey, RingPage.videoKey, RingPage.muteKey]) {
      expect(find.byKey(k), findsOneWidget);
    }
    // 下面两个一排等宽
    expect(t.getSize(find.byKey(RingPage.videoKey)).width, t.getSize(find.byKey(RingPage.muteKey)).width);
    await t.pumpWidget(Container());
  });

  testWidgets('我来处理：确认这一条，换成「这件事」，锁屏上不再显示', (t) async {
    final api = FakeApi('guard');
    final calls = await _open(t, api);
    await t.tap(find.byKey(RingPage.takeKey));
    await t.pumpAndSettle();
    expect(api.calls, contains('ack cctv:3/intrusion#9'));
    expect(find.byType(SiteAlertScenePage), findsOneWidget);
    expect(find.byType(RingPage), findsNothing);
    expect(calls.done, 1);
    await t.pumpWidget(Container());
  });

  testWidgets('只看画面：不确认，进「这件事」', (t) async {
    final api = FakeApi('guard');
    await _open(t, api);
    await t.tap(find.byKey(RingPage.videoKey));
    await t.pumpAndSettle();
    expect(api.calls.where((c) => c.startsWith('ack')), isEmpty);
    expect(find.byType(SiteAlertScenePage), findsOneWidget);
    await t.pumpWidget(Container());
  });

  testWidgets('静音 2 分钟：交给后台值守、前台的铃也静（同一个截止时间）、说静到几点、按钮灰掉', (t) async {
    ringMutedUntil.clear();
    final calls = await _open(t, FakeApi('guard'));
    await t.tap(find.byKey(RingPage.muteKey));
    await t.pumpAndSettle();
    expect(calls.muted, ['cctv:3/intrusion#9']);
    expect(find.textContaining('静音到 23:50'), findsOneWidget);
    expect(t.widget<OutlinedButton>(find.byKey(RingPage.muteKey)).onPressed, isNull);
    expect(ringMutedUntil['cctv:3/intrusion#9'], _t0 + 60000 + 120000, reason: '外审 App-V2-1 #5：前台铃看同一个截止时间');
    expect(ringMuted('cctv:3/intrusion#9', () => DateTime.fromMillisecondsSinceEpoch(_t0 + 61000)), isTrue);
    expect(ringMuted('cctv:3/intrusion#9', () => DateTime.fromMillisecondsSinceEpoch(_t0 + 181000)), isFalse);
    await t.pumpWidget(Container());
    // 没开后台值守：前台的铃照样静
    ringMutedUntil.clear();
    await _open(t, FakeApi('guard'), canMute: false);
    await t.tap(find.byKey(RingPage.muteKey));
    await t.pumpAndSettle();
    expect(find.textContaining('静音到 23:50'), findsOneWidget);
    expect(ringMutedUntil, contains('cctv:3/intrusion#9'));
    ringMutedUntil.clear();
    await t.pumpWidget(Container());
  });

  testWidgets('外审 App-V2-1 #6：别人接手了，只关自己这一页，不弹掉压在上面的另一件', (t) async {
    final api = FakeApi('guard');
    final calls = await _open(t, api);
    final nav = t.state<NavigatorState>(find.byType(Navigator));
    unawaited(nav.push(MaterialPageRoute<void>(builder: (_) => const Scaffold(body: Text('another ring')))));
    await t.pumpAndSettle();
    api.alertRows = [_wire(ackedBy: 'olga', ackedMs: _t0 + 70000)];
    await t.pump(const Duration(seconds: 3));
    await t.pumpAndSettle();
    expect(find.text('another ring'), findsOneWidget, reason: '上面那一页还在');
    expect(find.byType(RingPage, skipOffstage: false), findsNothing, reason: '自己这一页移走了');
    expect(calls.done, 1);
    nav.pop();
    await t.pumpAndSettle();
    expect(find.text('home'), findsOneWidget);
    await t.pumpWidget(Container());
  });

  testWidgets('别人接手了：这一页自己关', (t) async {
    final api = FakeApi('guard');
    final calls = await _open(t, api);
    api.alertRows = [_wire(ackedBy: 'olga', ackedMs: _t0 + 70000)];
    await t.pump(const Duration(seconds: 3));
    await t.pumpAndSettle();
    expect(find.byType(RingPage), findsNothing);
    expect(find.text('home'), findsOneWidget);
    expect(calls.done, 1);
  });

  testWidgets('只读账号：没有「我来处理」', (t) async {
    await _open(t, FakeApi('viewer'));
    expect(find.byKey(RingPage.takeKey), findsNothing);
    expect(find.byKey(RingPage.videoKey), findsOneWidget);
    await t.pumpWidget(Container());
  });

  test('原生交过来的：键、报文、站点；报文坏了也不丢那一条', () {
    final r = RingRequest.fromChannel(<String, String>{'key': 'k', 'alert': '{"level":"P1"}', 'site': 's'})!;
    expect((r.key, r.alert['level'], r.site), ('k', 'P1', 's'));
    expect(RingRequest.fromChannel(<String, String>{'key': 'k', 'alert': 'not json'})!.alert, isEmpty);
    expect(RingRequest.fromChannel(<String, String>{'alert': '{}'}), isNull);
    expect(RingRequest.fromChannel(null), isNull);
  });

  testWidgets('外壳：后台值守拉起来的是这个站点的，整屏弹出来；别的站点的也弹（外审 App-V2-4 N3），只能看、静音', (t) async {
    addTearDown(() => pendingRing.value = null);
    final api = FakeApi('guard');
    pendingRing.value = RingRequest('cctv:3/intrusion#9', _wire(), '别的站点');
    await t.pumpWidget(MaterialApp(home: NwShell(api: api, title: '庄园', ring: () {}, updater: null)));
    await t.pump();
    await t.pump(const Duration(milliseconds: 400));
    expect(find.byType(RingPage), findsOneWidget);
    expect(t.widget<RingPage>(find.byType(RingPage)).api, isNull, reason: '不用这个站点的连接');
    expect(find.byKey(RingPage.takeKey), findsNothing);
    expect(find.byKey(RingPage.muteKey), findsOneWidget);
    expect(find.textContaining('没登录 别的站点'), findsOneWidget);
    expect(pendingRing.value, isNull);
    t.state<NavigatorState>(find.byType(Navigator).first).pop();
    await t.pumpAndSettle();
    expect(find.byType(RingPage), findsNothing);
    pendingRing.value = RingRequest('cctv:3/intrusion#9', _wire(), '庄园');
    await t.pump();
    await t.pump(const Duration(milliseconds: 400));
    expect(find.byType(RingPage), findsOneWidget);
    expect(pendingRing.value, isNull, reason: '接走了');
    await t.pumpWidget(Container());
  });
}
