// 用户 11-25：机器人看见人，打开 App 直接横屏整屏放看到人的那一路实时画面（像遥控页），不只是告警。
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:nexwar_patrol/model/alert.dart';
import 'package:nexwar_patrol/ui/nw/nw_now.dart';
import 'package:nexwar_patrol/ui/nw/nw_ring.dart';
import 'package:nexwar_patrol/ui/nw/nw_theme.dart';
import 'package:nexwar_patrol/ui/person_live.dart';
import 'package:nexwar_patrol/ui/site_alert_scene.dart';
import 'package:nexwar_patrol/ui/site_robots.dart';
import 'package:nexwar_patrol/ui/site_video.dart';

import 'site_page_test.dart' show FakeApi;

int get _now => DateTime.now().millisecondsSinceEpoch;

Map<String, dynamic> _seen(String key, {List<String> cams = const ['back'], int? lastMs, String ackedBy = ''}) =>
    <String, dynamic>{
      'key': key, 'level': 'P1', 'kind': 'dog_sees_person', 'audience': 'intrusion', 'robot': 'A',
      'title': '机器人看见人了:1 个人', 'detail': '', 'first_ms': lastMs ?? _now - 5000, 'last_ms': lastMs ?? _now - 5000,
      'count': 1, 'acked_by': ackedBy, 'acked_ms': ackedBy.isEmpty ? null : _now, 'resolved_ms': null,
      'escalated': 0, 'channel': 'sound',
      'context': <String, dynamic>{'zone': '北区', 'persons': <String, dynamic>{'count': 1, 'cams': cams},
        'follow': 'retreat'},
    };

void _landscape(WidgetTester t) {
  t.view.physicalSize = const Size(844 * 2, 390 * 2);
  t.view.devicePixelRatio = 2.0;
  addTearDown(t.view.reset);
}

/// 画面里有转圈，不能 pumpAndSettle
Future<void> _settle(WidgetTester t) async {
  for (var i = 0; i < 6; i++) {
    await t.pump(const Duration(milliseconds: 100));
  }
}

void main() {
  setUp(personLiveShown.clear);

  testWidgets('易用性 build 37 复测：不在「现在」页（比如在「站点」页）来了看见人，也整屏弹；同一条只弹一次', (t) async {
    _landscape(t);
    final api = FakeApi('guard');
    await t.pumpWidget(MaterialApp(theme: nwTheme(Brightness.dark), home: SiteRobotsPage(api: api, ring: () {})));
    await _settle(t);
    api.sse.add(<String, dynamic>{'kind': 'alert', 'alert': _seen('A/p#9')});
    await _settle(t);
    expect(find.byType(PersonLivePage), findsOneWidget);
    expect(personLiveShown, contains('A/p#9'));
    api.sse.add(<String, dynamic>{'kind': 'alert', 'alert': _seen('A/p#9')});
    await _settle(t);
    expect(find.byType(PersonLivePage), findsOneWidget, reason: '同一条不再弹');
    await t.pumpWidget(Container());
  });

  testWidgets('易用性 build 37 复测：旧的（10 分钟前）、已经有人接手的，不弹', (t) async {
    _landscape(t);
    final api = FakeApi('guard');
    await t.pumpWidget(MaterialApp(theme: nwTheme(Brightness.dark), home: SiteRobotsPage(api: api, ring: () {})));
    await _settle(t);
    api.sse.add(<String, dynamic>{'kind': 'alert', 'alert': _seen('A/p#10', lastMs: _now - 11 * 60 * 1000)});
    api.sse.add(<String, dynamic>{'kind': 'alert', 'alert': _seen('A/p#11', ackedBy: 'gina')});
    await _settle(t);
    expect(find.byType(PersonLivePage), findsNothing);
    await t.pumpWidget(Container());
  });

  test('先开哪一路：只有后相机看到 = 后，前后都看到 / 没报 = 前', () {
    expect(personLiveCam(<String, dynamic>{'persons': <String, dynamic>{'cams': ['back']}}), 'back');
    expect(personLiveCam(<String, dynamic>{'persons': <String, dynamic>{'cams': ['front', 'back']}}), 'front');
    expect(personLiveCam(const <String, dynamic>{}), 'front');
  });

  test('自动弹哪一条：刚发生、没人接手、没弹过的 P1「机器人看见人」；旧的、接手了的、别的报警不弹', () {
    final fresh = Alert.fromWire(_seen('A/p#1'));
    expect(personLiveToPop([fresh], nowMs: _now)?.key, 'A/p#1');
    expect(personLiveToPop([Alert.fromWire(_seen('A/p#2', lastMs: _now - 11 * 60 * 1000))], nowMs: _now), isNull,
        reason: '十分钟前的不弹');
    expect(personLiveToPop([Alert.fromWire(_seen('A/p#3', ackedBy: 'gina'))], nowMs: _now), isNull);
    expect(personLiveToPop([Alert.fromWire({..._seen('A/p#4'), 'kind': 'robot_fell'})], nowMs: _now), isNull);
    personLiveShown.add('A/p#1');
    expect(personLiveToPop([fresh], nowMs: _now), isNull, reason: '弹过一次不再弹');
  });

  testWidgets('来报警全屏页遇到「机器人看见人」：横屏整屏放后相机画面，写跟随状态；我来处理以后接着看画面', (t) async {
    _landscape(t);
    final api = FakeApi('guard')..alertRows = [_seen('A/p#1')];
    await t.pumpWidget(MaterialApp(
        theme: nwTheme(Brightness.dark),
        home: Builder(
            builder: (c) => TextButton(
                onPressed: () => Navigator.push(
                    c,
                    MaterialPageRoute<void>(
                        builder: (_) => RingPage(
                            api: api,
                            alert: Alert.fromWire(_seen('A/p#1')),
                            site: 'estate-1',
                            mute: (_) async => true,
                            done: () async {}))),
                child: const Text('home')))));
    await t.tap(find.text('home'));
    await _settle(t);
    expect(find.byKey(PersonLiveView.key_), findsOneWidget);
    final v = t.widget<SiteVideo>(find.byType(SiteVideo));
    expect((v.fullscreen, v.initialCamera, v.robotId), (true, 'back', 'A'));
    expect(find.byKey(const Key('person-live-follow')), findsOneWidget);
    expect(find.byKey(RingPage.muteKey), findsOneWidget);
    expect(personLiveShown, contains('A/p#1'));
    await t.tap(find.byKey(RingPage.takeKey));
    await _settle(t);
    expect(api.calls, contains('ack A/p#1'));
    expect(find.byType(PersonLivePage), findsOneWidget, reason: '接手了接着看画面，不跳去别的页');
    await t.tap(find.byKey(PersonLivePage.detailKey));
    await _settle(t);
    expect(find.byType(SiteAlertScenePage), findsOneWidget);
  });

  testWidgets('易用性 build 36 P1-1：外面正弹着「无人确认」提示条，横屏 844×390 上「我来处理」照样点得到', (t) async {
    _landscape(t);
    final api = FakeApi('guard')..alertRows = [_seen('A/p#1')];
    await t.pumpWidget(MaterialApp(
        theme: nwTheme(Brightness.dark),
        home: Scaffold(
            body: Builder(
                builder: (c) => TextButton(
                    onPressed: () {
                      ScaffoldMessenger.of(c).showSnackBar(const SnackBar(
                          content: Text('P1 A · Person detected (unacknowledged)'), duration: Duration(minutes: 5)));
                      Navigator.push(
                          c,
                          MaterialPageRoute<void>(
                              builder: (_) => RingPage(
                                  api: api,
                                  alert: Alert.fromWire(_seen('A/p#1')),
                                  site: 'estate-1',
                                  mute: (_) async => true,
                                  done: () async {})));
                    },
                    child: const Text('home'))))));
    await t.tap(find.text('home'));
    await _settle(t);
    expect(find.byKey(PersonLiveView.key_), findsOneWidget);
    expect(find.textContaining('unacknowledged'), findsNothing, reason: '提示条不进这一页');
    final take = find.byKey(RingPage.takeKey);
    final hit = t.hitTestOnBinding(t.getCenter(take));
    final btn = t.renderObject(take);
    expect(hit.path.any((e) => e.target is RenderObject && _isUnder(e.target as RenderObject, btn)), isTrue,
        reason: '按钮中心点要点得到按钮');
  });

  testWidgets('易用性 build 36 P2-14：自动弹的看见人页有「静音 2 分钟」，点了写静到几点、按钮变灰', (t) async {
    _landscape(t);
    final api = FakeApi('guard')..alertRows = [_seen('A/p#5')];
    final muted = <String>[];
    await t.pumpWidget(MaterialApp(
        theme: nwTheme(Brightness.dark),
        home: PersonLivePage(
            api: api,
            alert: Alert.fromWire(_seen('A/p#5')),
            now: () => DateTime(2026, 11, 27, 10, 0),
            mute: (k) async => muted.add(k))));
    await _settle(t);
    expect(find.byKey(PersonLivePage.muteKey), findsOneWidget);
    await t.tap(find.byKey(PersonLivePage.muteKey));
    await _settle(t);
    expect(muted, ['A/p#5']);
    expect(find.textContaining('10:02'), findsOneWidget);
    expect(t.widget<ButtonStyleButton>(find.byKey(PersonLivePage.muteKey)).onPressed, isNull);
  });

  testWidgets('App 开着在「现在」页：读到刚发生的「机器人看见人」直接弹整屏画面，关了不再弹', (t) async {
    _landscape(t);
    final api = FakeApi('guard')..alertRows = [_seen('A/p#9', cams: ['front'])];
    await t.pumpWidget(MaterialApp(theme: nwTheme(Brightness.dark), home: Scaffold(body: NowPage(api: api))));
    await _settle(t);
    expect(find.byType(PersonLivePage), findsOneWidget);
    expect(t.widget<SiteVideo>(find.byType(SiteVideo)).initialCamera, 'front');
    expect(find.byKey(PersonLivePage.takeKey), findsOneWidget);
    await t.tap(find.byKey(PersonLivePage.closeKey));
    await _settle(t);
    expect(find.byType(PersonLivePage), findsNothing);
    await t.pump(const Duration(seconds: 40));
    await _settle(t);
    expect(find.byType(PersonLivePage), findsNothing, reason: '同一条只弹一次');
  });
}

bool _isUnder(RenderObject o, RenderObject root) {
  for (RenderObject? x = o; x != null; x = x.parent) {
    if (identical(x, root)) return true;
  }
  return false;
}
