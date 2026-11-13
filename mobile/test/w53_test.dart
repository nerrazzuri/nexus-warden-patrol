// W53（用户 2026-10-30 / 10-31）：值守页跟着一台机器人走、画面手动开、按角色的按钮、派巡逻弹框
// （估时、撞日程排队、被拒说原因）、今天的巡逻、管理栏（要你处理、开站清单）、账号审批、日程、申请账号、
// 上手导览和报警练习。
import 'dart:convert';

import 'package:nexwar_patrol/l10n.dart';
import 'package:nexwar_patrol/net/site_client.dart';
import 'package:nexwar_patrol/store/site_store.dart';
import 'package:nexwar_patrol/ui/guide.dart';
import 'package:nexwar_patrol/ui/nw/nw_shell.dart';
import 'package:nexwar_patrol/ui/nw/nw_widgets.dart';
import 'package:nexwar_patrol/ui/patrol_dispatch.dart';
import 'package:nexwar_patrol/ui/refusal.dart';
import 'package:nexwar_patrol/ui/site_duty_page.dart';
import 'package:nexwar_patrol/ui/site_list.dart';
import 'package:nexwar_patrol/ui/site_robot.dart' show SiteRobotPage;
import 'package:nexwar_patrol/ui/site_tabs.dart';
import 'package:nexwar_patrol/ui/site_video.dart';
import 'package:nexwar_patrol/ui/site_watch_page.dart';
import 'package:nexwar_patrol/ui/stop_failed.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'site_page_test.dart' show FakeApi;
import 'support/fake_site.dart';

void _size(WidgetTester t, [Size size = const Size(400, 1600)]) {
  t.view.physicalSize = size * 2;
  t.view.devicePixelRatio = 2.0;
  addTearDown(t.view.reset);
}

Map<String, dynamic> _robot(String id, int enrolled, {String name = ''}) => <String, dynamic>{
      'robot_id': id, 'name': name, 'enrolled_at': enrolled, 'revoked': false, 'fresh': true,
      'battery_pct': 80,
      'status': <String, dynamic>{'online': true, 'task': null,
        'ready': <String, dynamic>{'estop_clear': true}},
    };

Future<void> _duty(WidgetTester t, FakeApi api) async {
  _size(t);
  await t.pumpWidget(MaterialApp(home: SiteDutyPage(api: api, title: '站点')));
  await t.pumpAndSettle();
}

void main() {
  setUp(() => appLang.value = AppLang.zh);

  group('值守页', () {
    testWidgets('默认跟第一台加入的；点「名字 ▾」从底部列表切；画面点了才播、✕ 关；切台就关', (t) async {
      final api = FakeApi('guard')
        ..robotsOverride = [_robot('B', 2000), _robot('A', 1000, name: '北门')];
      await _duty(t, api);
      // W60：「名字 ▾」显示当前这台；点开底部列表选
      expect(find.descendant(of: find.byKey(SiteDutyPage.selectorKey), matching: find.text('北门')), findsOneWidget,
          reason: 'A 先加入（enrolled_at 小）');
      expect(find.byType(SiteVideo), findsNothing, reason: '默认不播');
      await t.tap(find.byKey(SiteDutyPage.playKey));
      await t.pump();
      expect(find.byType(SiteVideo), findsOneWidget);
      await t.tap(find.byKey(SiteDutyPage.closeKey));
      await t.pump();
      expect(find.byType(SiteVideo), findsNothing);
      await t.tap(find.byKey(SiteDutyPage.playKey));
      await t.pump();
      await t.tap(find.byKey(SiteDutyPage.selectorKey));
      await t.pumpAndSettle();
      expect(t.widget<ListTile>(find.byKey(SiteDutyPage.chipKey('A'))).selected, isTrue);
      await t.tap(find.byKey(SiteDutyPage.chipKey('B')));
      await t.pumpAndSettle();
      expect(find.descendant(of: find.byKey(SiteDutyPage.selectorKey), matching: find.text('B')), findsOneWidget);
      expect(find.byType(SiteVideo), findsNothing, reason: '切台：原来那路关掉');
    });

    testWidgets('按钮按角色：保安 派巡逻 / 遥控 / 叫停；经理 派巡逻 / 叫停；只看的什么都没有', (t) async {
      for (final (role, patrol, teleop, stop) in [
        ('guard', true, true, true),
        ('owner', true, false, true),
        ('viewer', false, false, false),
      ]) {
        await _duty(t, FakeApi(role));
        expect(find.byKey(SiteDutyPage.patrolKey), patrol ? findsOneWidget : findsNothing, reason: role);
        expect(find.byKey(SiteDutyPage.teleopKey), teleop ? findsOneWidget : findsNothing, reason: role);
        expect(find.byKey(SiteDutyPage.stopKey), stop ? findsOneWidget : findsNothing, reason: role);
        await t.pumpWidget(Container());
      }
    });

    testWidgets('手机 App 测试 M02：叫停失败弹醒目的框，叫人按机身急停，不自动消失', (t) async {
      final busy = <String, dynamic>{
        ...siteFixture('site_robot'),
        'status': <String, dynamic>{
          ...(siteFixture('site_robot')['status'] as Map<String, dynamic>),
          'task': <String, dynamic>{'task_id': 'task-1', 'type': 'patrol'},
        },
      };
      final api = FakeApi('guard', robotView: busy)..abortError = const SiteError(0, '站点无响应（超时）');
      await _duty(t, api);
      await t.ensureVisible(find.byKey(SiteDutyPage.stopKey));
      await t.tap(find.byKey(SiteDutyPage.stopKey));
      await t.pumpAndSettle();
      expect(api.calls, contains('abort A task-1'));
      expect(find.byKey(stopFailedKey), findsOneWidget);
      expect(find.textContaining('请立刻按机身上的急停按钮'), findsOneWidget);
      expect(find.textContaining('站点无响应'), findsOneWidget);
      await t.pump(const Duration(seconds: 30));
      expect(find.byKey(stopFailedKey), findsOneWidget, reason: '不自动消失');
      await t.tap(find.text('知道了'));
      await t.pumpAndSettle();
      expect(find.byKey(stopFailedKey), findsNothing);
    });

    testWidgets('手机 App 测试 M13：经理派巡逻前就说机器人被叫停了、谁能恢复；派的按钮灰着', (t) async {
      final v = <String, dynamic>{...siteFixture('site_robot'), 'held': <String, dynamic>{'by': 'gina', 'at_ms': 1}};
      final api = FakeApi('owner', robotView: v);
      await t.pumpWidget(MaterialApp(home: Builder(builder: (c) => TextButton(
          onPressed: () => showPatrolSheet(c, api, 'A'), child: const Text('go')))));
      await t.tap(find.text('go'));
      await t.pumpAndSettle();
      expect(find.byKey(const Key('patrol-held')), findsOneWidget);
      expect(find.textContaining('保安或管理员点「恢复」之前'), findsOneWidget);
      expect(refusalHint('held', api.session), contains('保安或管理员'));
    });

    // 易用性第 6 轮 A6-02 / A6-03：未就绪按原因说；对管理员不说「请找管理员」
    test('A6-02/03 被拒提示：蹲着说站起来、急停说松开；管理员地图不对说去地图页下发', () {
      final guard = FakeApi('guard').session;
      final admin = FakeApi('admin').session;
      expect(refusalHint('not_standing', guard), contains('「站起」'));
      expect(refusalHint('not_standing', guard), isNot(contains('遥控')), reason: 'A7-01：蹲着时开不了遥控');
      expect(refusalHint('estop', guard), contains('急停'));
      expect(refusalHint('no_control', guard), contains('控制权'));
      expect(refusalHint('map_mismatch', guard), contains('请管理员'));
      expect(refusalHint('map_mismatch', admin), isNot(contains('请管理员')));
      expect(refusalHint('map_mismatch', admin), contains('地图'));
    });

    testWidgets('手机 App 测试 M09：开始、结束巡逻这类日常记录不算「其他未处理」；顶上写 P1 几条、在线几台', (t) async {
      Map<String, dynamic> row(String kind, String level) => <String, dynamic>{
            'key': 'A/$kind#1', 'level': level, 'kind': kind, 'robot': 'A', 'title': 't', 'detail': '',
            'first_ms': 1, 'last_ms': 1, 'count': 1, 'acked_by': '', 'acked_ms': null, 'resolved_ms': null,
            'escalated': 0, 'channel': 'screen',
          };
      final api = FakeApi('guard')
        ..alertRows = [row('run_start', 'P3'), row('run_done', 'P2'), row('adhoc_patrol', 'P2'), row('stuck', 'P2'),
          // 第 12 轮 W12-02：管理员的事（存储不足）不算保安的「其他未处理」，跟网页值班页一样
          <String, dynamic>{...row('disk_80', 'P2'), 'audience': 'owner'}];
      await _duty(t, api);
      expect(find.text('其他未处理 1 条'), findsOneWidget);
      expect(find.textContaining('没有紧急报警'), findsOneWidget, reason: 'A6-04：不写客户看不懂的「P1：无」');
      expect(find.textContaining('P1'), findsNothing);
      expect(find.byKey(SiteDutyPage.safetyKey), findsOneWidget);
    });

    testWidgets('A6-04：新登记的机器人「只许手动派」写人话，不露 enroll 和站点原话', (t) async {
      final v = Map<String, dynamic>.of(siteFixture('site_robot'))
        ..['manual_only'] = <String, dynamic>{'by': 'enroll', 'at_ms': 1, 'note': '新登记:确认之前只许手动派'};
      final api = FakeApi('guard', robotView: v)..robotsOverride = <Map<String, dynamic>>[v];
      await _duty(t, api);
      final txt = t.widget<Text>(find.byKey(SiteDutyPage.manualKey)).data!;
      expect(txt, contains('新加入的机器人，管理员确认前只许手动派'));
      expect(txt, isNot(contains('enroll')));
      expect(txt, isNot(contains('新登记:')));
      appLang.value = AppLang.en;
      await t.pumpWidget(Container());                  // 换语言整个 App 重建
      await _duty(t, api);
      final en = t.widget<Text>(find.byKey(SiteDutyPage.manualKey)).data!;
      expect(en, contains('New robot'));
      expect(en, isNot(contains('enroll')));
      expect(en, isNot(contains('新')));
      appLang.value = AppLang.zh;
    });

    testWidgets('A6-04：人设的「只许手动派」照旧写谁设的、为什么', (t) async {
      final v = Map<String, dynamic>.of(siteFixture('site_robot'))
        ..['manual_only'] = <String, dynamic>{'by': 'olga', 'at_ms': 1, 'note': '在修腿'};
      final api = FakeApi('guard', robotView: v)..robotsOverride = <Map<String, dynamic>>[v];
      await _duty(t, api);
      expect(t.widget<Text>(find.byKey(SiteDutyPage.manualKey)).data, contains('olga 设的：在修腿'));
    });

    testWidgets('今天的巡逻：一行一趟；排队中的临时巡逻派的人能取消', (t) async {
      final api = FakeApi('guard')
        ..session = const SiteSession('t', 'gina', 'guard')
        ..today = <String, dynamic>{'date': 'x', 'timezone': 'UTC', 'items': <dynamic>[
          <String, dynamic>{'at_ms': 1800000000000, 'kind': 'schedule', 'label': '外围一圈', 'robot': 'A',
            'by': '', 'state': 'done', 'reason': '', 'end_ms': null, 'adhoc_id': ''},
          <String, dynamic>{'at_ms': 1800001000000, 'kind': 'adhoc', 'label': '临时路线 2 个点', 'robot': 'A',
            'by': 'gina', 'state': 'queued', 'reason': '', 'end_ms': 1800001600000, 'adhoc_id': 'q1'},
        ]};
      await _duty(t, api);
      expect(find.text('完成'), findsOneWidget);
      expect(find.text('排队中'), findsOneWidget);
      await t.ensureVisible(find.byKey(todayRowKey(1)));
      await t.tap(find.byKey(todayRowKey(1)));
      await t.pumpAndSettle();
      await t.tap(find.byKey(const Key('today-cancel')));
      await t.pumpAndSettle();
      expect(api.calls, contains('cancelAdhoc q1'));
    });

    // 第 8 轮 W8-03 / A8-01 / W8-04：被日程接替的一直巡逻不写「未完成」「preempted」「预计…结束」；
    // 在跑的一直巡逻首页写第几圈，不写预计结束时间
    testWidgets('第 8 轮：被接替的一趟写跑了几圈、谁接的；在跑的一直巡逻写第几圈、不写预计结束', (t) async {
      final v = jsonDecode(jsonEncode(siteFixture('site_robot'))) as Map<String, dynamic>;
      (v['status'] as Map)['task'] = {'kind': 'patrol', 'state': 'running', 'task_id': 'adhoc-forever-f2'};
      v['lap'] = {'n': 6, 'of': 0};
      final api = FakeApi('guard', robotView: v)
        ..session = const SiteSession('t', 'gina', 'guard')
        ..today = <String, dynamic>{'date': 'x', 'timezone': 'UTC', 'items': <dynamic>[
          <String, dynamic>{'at_ms': 1800000000000, 'kind': 'adhoc', 'label': 'loop-test', 'robot': 'A',
            'by': 'demo', 'state': 'handed_over', 'reason': '', 'end_ms': 1800000600000, 'adhoc_id': 'f1',
            'forever': true, 'handover': {'by': 'schedule', 'name': 'cut-test', 'laps': 6}},
          <String, dynamic>{'at_ms': 1800001000000, 'kind': 'adhoc', 'label': 'loop-test', 'robot': 'A',
            'by': 'gina', 'state': 'running', 'reason': '', 'end_ms': null, 'adhoc_id': 'f2',
            'task_id': 'adhoc-forever-f2', 'forever': true, 'lap': {'n': 6, 'of': 0}},
        ]};
      await _duty(t, api);
      expect(find.text('被接替'), findsOneWidget);
      expect(find.text('未完成'), findsNothing);
      expect(find.textContaining('一直巡逻 · 第 6 圈'), findsWidgets);
      expect(find.textContaining('预计'), findsNothing, reason: '一直巡逻没有固定结束时间');
      await t.ensureVisible(find.byKey(todayRowKey(0)));
      await t.tap(find.byKey(todayRowKey(0)));
      await t.pumpAndSettle();
      expect(find.textContaining('已跑 6 圈，由日程 cut-test 接替'), findsOneWidget);
      expect(find.textContaining('preempted'), findsNothing);
      expect(find.textContaining('预计'), findsNothing, reason: '跑完了的写几点结束，不写预计');
    });

    // 第 8 轮 A8-06：在别的页（机器人页、路线页）派出去，首页「今天的巡逻」马上刷新，不等 30 秒那一轮
    testWidgets('第 8 轮 A8-06：别处派出巡逻后首页今天的巡逻马上重读', (t) async {
      final api = FakeApi('guard')..session = const SiteSession('t', 'gina', 'guard');
      await _duty(t, api);
      int n() => api.calls.where((c) => c == 'patrolsToday').length;
      final before = n();
      patrolSent.value++;
      await t.pump();
      expect(n(), before + 1, reason: '马上读一次');
      await t.pump(const Duration(seconds: 3));
      expect(n(), greaterThanOrEqualTo(before + 3), reason: '站点记下来可能慢一点：1 秒、3 秒再读');
    });

    // 第 8 轮 W8-11：今天的巡逻写路线显示名
    testWidgets('第 8 轮 W8-11：今天的巡逻写显示名', (t) async {
      final api = FakeApi('guard')
        ..session = const SiteSession('t', 'gina', 'guard')
        ..today = <String, dynamic>{'date': 'x', 'timezone': 'UTC', 'items': <dynamic>[
          <String, dynamic>{'at_ms': 1800000000000, 'kind': 'schedule', 'label': 'route-1', 'title': '一楼夜巡', 'robot': 'A',
            'by': '', 'state': 'later', 'reason': '', 'end_ms': null, 'adhoc_id': ''},
        ]};
      await _duty(t, api);
      expect(find.textContaining('一楼夜巡'), findsWidgets);
      expect(find.textContaining('route-1'), findsNothing);
    });

    testWidgets('其他没处理的报警收成一行，点开是原来的告警总览', (t) async {
      final api = FakeApi('guard');
      await _duty(t, api);
      final others = find.byKey(SiteDutyPage.othersKey);
      if (others.evaluate().isEmpty) return; // 夹具里只有 P1 的时候没有这一行
      await t.ensureVisible(others);
      await t.tap(others);
      await t.pumpAndSettle();
      expect(find.byType(SiteWatchPage), findsOneWidget);
    });
  });

  group('派巡逻', () {
    testWidgets('每条路线写估时；撞日程先说清楚、按钮是「排队派出」；派出去说排到几点', (t) async {
      final api = FakeApi('guard')
        ..plans = <String, Map<String, dynamic>>{
          'loop': <String, dynamic>{'estimate_s': 1080, 'queued': true, 'start_ms': 1800001200000,
            'because': '22:00 日程「loop」'},
        }
        ..patrolReply = <String, dynamic>{'queued': true, 'start_after_ms': 1800001200000,
          'estimate_s': 1080, 'because': '22:00 日程「loop」', 'adhoc_id': 'a1'};
      await _duty(t, api);
      await t.tap(find.byKey(SiteDutyPage.patrolKey));
      await t.pumpAndSettle();
      expect(find.text('约 18 分钟'), findsOneWidget);
      await t.tap(find.byKey(patrolRouteKey('loop')));
      await t.pumpAndSettle();
      expect(find.byKey(patrolQueuedKey), findsOneWidget);
      expect(find.text('排队派出'), findsOneWidget);
      await t.tap(find.byKey(patrolSendKey));
      await t.pumpAndSettle();
      expect(api.calls.where((c) => c.startsWith('patrol ')), isNotEmpty);
      expect(find.textContaining('已排队'), findsOneWidget);
    });

    testWidgets('被拒（叫停了）：弹框说原因，「恢复」就恢复', (t) async {
      final api = FakeApi('guard')
        ..patrolError = const SiteError(409, 'A 被 olga 叫停了:先点「恢复」再派',
            body: <String, dynamic>{'reason_code': 'held', 'reason_en': 'This robot was stopped by someone.'});
      await _duty(t, api);
      await t.tap(find.byKey(SiteDutyPage.patrolKey));
      await t.pumpAndSettle();
      await t.tap(find.byKey(patrolRouteKey('loop')));
      await t.pumpAndSettle();
      await t.tap(find.byKey(patrolSendKey));
      await t.pumpAndSettle();
      expect(find.byKey(refusalDialogKey), findsOneWidget);
      expect(find.textContaining('叫停'), findsWidgets);
      await t.tap(find.byKey(refusalActionKey));
      await t.pumpAndSettle();
      expect(api.calls, contains('resume A'));
    });

    testWidgets('机器人明确没收（忙）：不说「派出去了」，框里写原因（外审 W53-1 #4）', (t) async {
      final api = FakeApi('guard')
        ..patrolReply = <String, dynamic>{'queued': false, 'ack': <String, dynamic>{'result': 'rejected', 'reason': 'busy'}};
      await _duty(t, api);
      await t.tap(find.byKey(SiteDutyPage.patrolKey));
      await t.pumpAndSettle();
      await t.tap(find.byKey(patrolRouteKey('loop')));
      await t.pumpAndSettle();
      await t.tap(find.byKey(patrolSendKey));
      await t.pumpAndSettle();
      expect(find.textContaining('机器人未接受'), findsOneWidget);
      expect(find.textContaining('派出去了'), findsNothing);
    });

    testWidgets('派巡逻框里能改成「在地图上点点位」', (t) async {
      await _duty(t, FakeApi('guard'));
      await t.tap(find.byKey(SiteDutyPage.patrolKey));
      await t.pumpAndSettle();
      expect(find.byKey(patrolCustomKey), findsOneWidget);
    });

    test('时刻按站点的钟：给了偏移就不看手机时区', () {
      const ms = 1800000000000; // 2027-01-15 08:00 UTC
      expect(hhmm(ms, 480), '16:00');
      expect(hhmm(ms, 0), '08:00');
    });

    test('被拒的原话按语言说：英文界面用 reason_en', () {
      const e = SiteError(409, 'A 不在线', body: <String, dynamic>{'reason_code': 'offline', 'reason_en': 'Offline.'});
      appLang.value = AppLang.en;
      expect(refusalText(e), 'Offline.');
      appLang.value = AppLang.zh;
      expect(refusalText(e), 'A 不在线');
      expect(zonesMapOf('estate-1:7 当前的区域修订还没做安全确认'), ('estate-1', '7'));
    });
  });

  group('管理栏、账号、日程', () {
    testWidgets('要你处理：禁行区没确认；开站清单能「不用了」、能收起', (t) async {
      final api = FakeApi('admin');
      _size(t);
      await t.pumpWidget(MaterialApp(home: AdminHomeTab(api: api, switchTab: (_) {})));
      await t.pumpAndSettle();
      expect(find.byKey(AdminHomeTab.todoKey), findsOneWidget);
      expect(find.textContaining('m1:3 的禁行区未确认'), findsOneWidget);
      await t.tap(find.byKey(SetupChecklist.skipKey('zones')));
      await t.pumpAndSettle();
      expect(api.calls, contains('setGuide skip'));
      await t.tap(find.byKey(SetupChecklist.hideKey));
      await t.pumpAndSettle();
      expect(api.calls, contains('setGuide setup_hidden'));
      expect(find.byKey(SetupChecklist.itemKey('robots')), findsNothing, reason: '收起来了');
    });

    // 第 8 轮 W8-08：路线画在别的版本上，清单说在哪一版；日程的路线跑不了，说哪条
    testWidgets('第 8 轮：开站清单说路线画在 v11 上、机器人用 v7；日程跑不了', (t) async {
      final api = FakeApi('admin')
        ..setupBody = <String, dynamic>{'done': 0, 'total': 2, 'items': <dynamic>[
          <String, dynamic>{'id': 'routes', 'done': false, 'skipped': false,
            'elsewhere': [{'route': 'demo-loop', 'map': 'm1', 'version': '11'}], 'using': [{'map': 'm1', 'version': '7'}]},
          <String, dynamic>{'id': 'schedule', 'done': false, 'skipped': false, 'blocked': ['demo-night']},
        ]};
      _size(t);
      await t.pumpWidget(MaterialApp(home: AdminHomeTab(api: api, switchTab: (_) {})));
      await t.pumpAndSettle();
      expect(find.textContaining('有 1 条路线（demo-loop）画在 v11 上，机器人在用 v7：在 v7 上重画'), findsOneWidget);
      expect(find.textContaining('日程 demo-night 要跑的路线跑不了'), findsOneWidget);
    });

    // minor #21（liang-d5 W7）：标原点时自动加了待命点，清单打勾 —— 写明待命点就是原点
    testWidgets('minor #21：待命点就是原点的，打勾也写一句', (t) async {
      final api = FakeApi('admin')
        ..setupBody = <String, dynamic>{'done': 1, 'total': 1, 'items': <dynamic>[
          <String, dynamic>{'id': 'standby', 'done': true, 'skipped': false, 'robots': <dynamic>[], 'at_home': ['A']},
        ]};
      _size(t);
      await t.pumpWidget(MaterialApp(home: AdminHomeTab(api: api, switchTab: (_) {})));
      await t.pumpAndSettle();
      expect(find.textContaining('A 的待命点就是原点（标原点时自动加的）'), findsOneWidget);
    });

    testWidgets('minor #40：没报在用哪张图的机器人，原点那一项写明是哪几台', (t) async {
      final api = FakeApi('admin')
        ..setupBody = <String, dynamic>{'done': 0, 'total': 1, 'items': <dynamic>[
          <String, dynamic>{'id': 'home', 'done': false, 'skipped': false, 'robots': <dynamic>[], 'no_map': ['B']},
        ]};
      _size(t);
      await t.pumpWidget(MaterialApp(home: AdminHomeTab(api: api, switchTab: (_) {})));
      await t.pumpAndSettle();
      expect(find.textContaining('B 还没报在用哪张图'), findsOneWidget);
    });

    testWidgets('账号审批：权限下拉默认只看，选保安、输密码批准', (t) async {
      final api = FakeApi('admin')
        ..acctReqs = <Map<String, dynamic>>[<String, dynamic>{'id': 'r1', 'name': 'wangxm', 'display': '王小明'}];
      _size(t);
      await t.pumpWidget(MaterialApp(home: AccountsPage(api: api)));
      await t.pumpAndSettle();
      expect(find.text('只看'), findsOneWidget);
      await t.tap(find.byKey(AccountsPage.roleKey('r1')));
      await t.pumpAndSettle();
      await t.tap(find.text('保安').last);
      await t.pumpAndSettle();
      await t.tap(find.byKey(AccountsPage.approveKey('r1')));
      await t.pumpAndSettle();
      await t.enterText(find.byKey(const Key('acct-confirm-pw')), 'my-password');
      await t.tap(find.byKey(const Key('acct-confirm-go')));
      await t.pumpAndSettle();
      expect(api.calls, contains('approveAccount r1 guard my-password'));
      expect(find.text('王小明 · wangxm'), findsNothing);
    });

    testWidgets('经理排日程：每周 → 加一条（路线、机器人、钟点、星期）→ 存', (t) async {
      final api = FakeApi('owner');
      _size(t);
      await t.pumpWidget(MaterialApp(home: SchedulePage(api: api)));
      await t.pumpAndSettle();
      await t.tap(find.byKey(SchedulePage.weekTabKey));
      await t.pumpAndSettle();
      await t.tap(find.byKey(SchedulePage.addKey));
      await t.pumpAndSettle();
      await t.tap(find.byKey(const Key('sched-day-sun')));
      await t.pump();
      await t.tap(find.byKey(const Key('sched-save')));
      await t.pumpAndSettle();
      final saved = api.calls.where((c) => c.startsWith('saveSchedule ')).toList();
      expect(saved, hasLength(1));
      expect(saved.single, contains(' loop 08:00'));
      expect(find.byKey(SchedulePage.rowKey(saved.single.split(' ')[1])), findsOneWidget);
    });

    testWidgets('改已有的日程：编辑器没有的字段（每隔几分钟、到几点、回哪个待命点）原样带回去（外审 #9）', (t) async {
      final api = FakeApi('owner')
        ..schedules = <String, dynamic>{'timezone': 'UTC', 'revision': 1, 'schedules': <dynamic>[
          <String, dynamic>{'id': 'night', 'mission': 'loop', 'at': '22:00', 'days': <dynamic>['mon', 'tue'],
            'robot': 'A', 'every_min': 30, 'until': '02:00', 'standby': 'gate', 'priority': 3, 'revision': 4,
            'window_min': 20, 'on_missed': 'alarm', 'updated_by': 'x'},
        ]};
      Map<String, dynamic>? sent;
      api.onSaveSchedule = (b) => sent = b;
      _size(t);
      await t.pumpWidget(MaterialApp(home: SchedulePage(api: api)));
      await t.pumpAndSettle();
      await t.tap(find.byKey(SchedulePage.weekTabKey));
      await t.pumpAndSettle();
      await t.tap(find.byKey(SchedulePage.rowKey('night')));
      await t.pumpAndSettle();
      await t.tap(find.byKey(const Key('sched-save')));
      await t.pumpAndSettle();
      expect(sent, isNotNull);
      expect(sent!['every_min'], 30);
      expect(sent!['until'], '02:00');
      expect(sent!['standby'], 'gate');
      expect(sent!['priority'], 3);
      expect(sent!['window_min'], 20);
      expect(sent!['on_missed'], 'alarm');
      expect(sent!['base_revision'], 4);
      expect(sent!.containsKey('updated_by'), isFalse);
    });

    testWidgets('第 9 轮 W9-01 / A9-01：日程写日程名和路线显示名；加日程默认选跑得了的、跑不了的灰掉；只许手动派的写明', (t) async {
      final api = FakeApi('owner')
        ..scheduleBody = <String, dynamic>{'missions': <dynamic>['old', 'route-1']}
        ..routesBody = <String, dynamic>{'revision': 1, 'timezone': 'UTC', 'schedules': <dynamic>[], 'routes': <dynamic>[
          <String, dynamic>{'id': 'old', 'title': '', 'map_id': 'estate-1', 'map_version': '11'},
          <String, dynamic>{'id': 'route-1', 'title': '一楼夜巡', 'map_id': 'estate-1', 'map_version': '7'},
        ]}
        // 第 10 轮：用真站点的 /api/robots 形状（站点测试生成的夹具）：在用的图在 running 里，
        // 只许手动派是 {by, at_ms, note} 对象（以前假数据写 map、manual_only: true，真站点没有）
        ..robotsOverride = <Map<String, dynamic>>[
          for (final id in ['A', 'B'])
            <String, dynamic>{
              ...((siteFixture('site_robots')['robots'] as List).first as Map).cast<String, dynamic>(),
              'robot_id': id,
              'manual_only': id == 'B' ? <String, dynamic>{'by': 'demo', 'at_ms': 1, 'note': ''} : null,
            },
        ]
        ..schedules = <String, dynamic>{'timezone': 'UTC', 'revision': 1, 'schedules': <dynamic>[
          <String, dynamic>{'id': 'route-1-1', 'title': '夜巡测试', 'mission': 'route-1', 'at': '10:05',
            'days': <dynamic>['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'], 'robot': 'B', 'revision': 1},
        ]};
      Map<String, dynamic>? sent;
      api.onSaveSchedule = (b) => sent = b;
      _size(t);
      await t.pumpWidget(MaterialApp(home: SchedulePage(api: api)));
      await t.pumpAndSettle();
      await t.tap(find.byKey(SchedulePage.weekTabKey));
      await t.pumpAndSettle();
      expect(find.textContaining('夜巡测试 · 一楼夜巡 · B'), findsOneWidget);
      expect(find.textContaining('route-1'), findsNothing);
      await t.tap(find.byKey(SchedulePage.addKey));
      await t.pumpAndSettle();
      expect(find.text('一楼夜巡'), findsWidgets, reason: '默认选跑得了的那条，写显示名');
      await t.tap(find.byKey(const Key('sched-route')));
      await t.pumpAndSettle();
      expect(find.textContaining('old（画在第 11 版地图上，没有机器人在用）'), findsWidgets);
      await t.tap(find.text('一楼夜巡').last);
      await t.pumpAndSettle();
      await t.tap(find.byKey(const Key('sched-robot')));
      await t.pumpAndSettle();
      expect(find.text('哪台空就哪台'), findsWidgets);
      expect(find.textContaining('B（只许手动派，日程不会派它）'), findsWidgets);
      await t.tap(find.text('哪台空就哪台').last);
      await t.pumpAndSettle();
      expect(find.textContaining('约约'), findsNothing);
      await t.enterText(find.byKey(const Key('sched-name')), '早巡');
      await t.tap(find.byKey(const Key('sched-day-sun')));
      await t.pump();
      await t.tap(find.byKey(const Key('sched-save')));
      await t.pumpAndSettle();
      expect(sent!['mission'], 'route-1');
      expect(sent!['title'], '早巡');
    });

    testWidgets('保安看日程：只看，不能加', (t) async {
      final api = FakeApi('guard');
      _size(t);
      await t.pumpWidget(MaterialApp(home: SchedulePage(api: api)));
      await t.pumpAndSettle();
      await t.tap(find.byKey(SchedulePage.weekTabKey));
      await t.pumpAndSettle();
      expect(find.byKey(SchedulePage.addKey), findsNothing);
    });
  });

  group('申请账号（W52）', () {
    testWidgets('登录页「申请账号」→ 填名字、账号、密码 → 交上去了', (t) async {
      final got = <String>[];
      _size(t);
      await t.pumpWidget(MaterialApp(
          home: SiteLoginPage(
              site: SiteEntry(name: '站点', url: 'https://x', fingerprint: 'ab' * 32, username: ''),
              signIn: (_, _) async => FakeApi('guard'),
              apply: (n, d, p) async => got.add('$n $d $p'))));
      await t.pumpAndSettle();
      await t.tap(find.byKey(SiteLoginPage.applyKey));
      await t.pumpAndSettle();
      await t.enterText(find.byKey(AccountApplyPage.nameKey), '王小明');
      await t.enterText(find.byKey(AccountApplyPage.accountKey), 'wangxm');
      await t.enterText(find.byKey(AccountApplyPage.passwordKey), 'short');
      await t.tap(find.byKey(AccountApplyPage.submitKey));
      await t.pumpAndSettle();
      expect(got, isEmpty, reason: '密码太短先在手机上拦');
      await t.enterText(find.byKey(AccountApplyPage.passwordKey), 'long-enough-pw');
      await t.tap(find.byKey(AccountApplyPage.submitKey));
      await t.pumpAndSettle();
      expect(got, ['wangxm 王小明 long-enough-pw']);
      expect(find.byKey(AccountApplyPage.doneKey), findsOneWidget);
    });

    test('登录失败时申请的状态按语言说', () {
      appLang.value = AppLang.en;
      expect(applyStateText('这个账号还在等管理员批准'), contains('waiting'));
      expect(applyStateText('这个账号的申请被管理员拒了'), contains('turned down'));
      appLang.value = AppLang.zh;
      expect(applyStateText('这个账号还在等管理员批准'), '这个账号还在等管理员批准');
    });
  });

  group('退出站点', () {
    testWidgets('每个角色的第 5 栏都有「退出站点」，点了回站点列表', (t) async {
      _size(t, const Size(400, 1400));
      for (final (role, tab) in [
        ('admin', NwShell.adminKey),
        ('owner', NwShell.planKey),
        ('guard', NwShell.moreKey),
      ]) {
        await t.pumpWidget(MaterialApp(
            home: Builder(builder: (c) => Scaffold(body: Center(child: TextButton(
                onPressed: () => Navigator.push(c, MaterialPageRoute<void>(
                    builder: (_) => NwShell(api: FakeApi(role), title: '站点', ring: () {}))),
                child: const Text('站点列表')))))));
        await t.tap(find.text('站点列表'));
        await t.pumpAndSettle();
        await t.tap(find.byKey(tab));
        await t.pumpAndSettle();
        final leave = role == 'guard' ? MeTab.leaveKey : leaveSiteKey;
        if (role == 'admin') {
          await t.scrollUntilVisible(find.byKey(leave), 200,
              scrollable: find.descendant(of: find.byType(AdminHomeTab), matching: find.byType(Scrollable)).first);
          await t.pumpAndSettle();
        }
        await t.tap(find.byKey(leave));
        await t.pumpAndSettle();
        await t.tap(find.byKey(leaveConfirmKey));
        await t.pumpAndSettle();
        expect(find.byType(NwShell), findsNothing, reason: role);
        expect(find.text('站点列表'), findsOneWidget, reason: role);
        await t.pumpWidget(Container());
      }
    });
  });

  group('上手向导', () {
    testWidgets('没看过导览的保安：进站点就开始，一步步走完记下来，最后练一次报警（不发给站点）', (t) async {
      final api = FakeApi('guard')..guide = <String, dynamic>{'tour': 0, 'setup_hidden': false, 'skip': <dynamic>[]};
      _size(t, const Size(400, 900));
      await t.pumpWidget(MaterialApp(home: NwShell(api: api, title: '站点', ring: () {})));
      await t.pumpAndSettle();
      expect(find.byKey(tourCardKey), findsOneWidget);
      var steps = 0;
      while (find.byKey(tourNextKey).evaluate().isNotEmpty && steps < 20) {
        await t.tap(find.byKey(tourNextKey));
        await t.pumpAndSettle();
        steps++;
      }
      expect(steps, tourSteps('guard', DutyTargets()).length);
      expect(api.calls, contains('setGuide tour'));
      expect(api.guide['tour'], kTourVersion);
      expect(find.byType(PracticeAlarmPage), findsOneWidget);
      final before = List<String>.of(api.calls);
      await t.tap(find.byKey(PracticeAlarmPage.respondKey));
      await t.pumpAndSettle();
      await t.tap(find.byKey(PracticeAlarmPage.takeKey));
      await t.pumpAndSettle();
      await t.tap(find.byKey(PracticeAlarmPage.outcomeKey('false')));
      await t.pumpAndSettle();
      expect(find.byKey(PracticeAlarmPage.doneKey), findsOneWidget);
      expect(api.calls.where((c) => !before.contains(c) && !c.startsWith('patrolsToday')), isEmpty,
          reason: '练习不发给站点');
    });

    testWidgets('看过了就不再弹；「跳过」也记下来', (t) async {
      final seen = FakeApi('admin');
      _size(t, const Size(400, 900));
      await t.pumpWidget(MaterialApp(home: NwShell(api: seen, title: '站点', ring: () {})));
      await t.pumpAndSettle();
      expect(find.byKey(tourCardKey), findsNothing);
    });

    testWidgets('「跳过」也记下来，跳过了就不练', (t) async {
      _size(t, const Size(400, 900));
      final fresh = FakeApi('owner')..guide = <String, dynamic>{'tour': 0};
      await t.pumpWidget(MaterialApp(home: NwShell(api: fresh, title: '站点', ring: () {})));
      await t.pumpAndSettle();
      await t.tap(find.byKey(tourSkipKey));
      await t.pumpAndSettle();
      expect(fresh.guide['tour'], kTourVersion);
      expect(find.byType(PracticeAlarmPage), findsNothing, reason: '跳过了就不练');
    });

    testWidgets('常见问题按角色：保安没有「怎么加账号」，管理员有', (t) async {
      await t.pumpWidget(const MaterialApp(home: HelpPage(role: 'guard')));
      expect(find.text('如何添加账号'), findsNothing);
      expect(find.text('收到报警如何处理'), findsOneWidget);
      await t.pumpWidget(const MaterialApp(home: HelpPage(role: 'admin')));
      expect(find.text('如何添加账号'), findsOneWidget);
    });
  });

  test('W71 今天的巡逻：跳过几个点也算完成，显示「完成（跳过 N 点）」', () {
    final (label, tone) = patrolStateText('done', 2);
    expect(label, anyOf('Done (2 skipped)', '完成（跳过 2 点）'));
    expect(tone, NwTone.warning);
    expect(patrolStateText('done').$2, NwTone.success);
  });

  // 易用性第 6 轮 W6-02：排给的那台只许手动派，到点也不会跑
  test('W6-02 不会跑：状态写清楚，原因说人话', () {
    final (label, tone) = patrolStateText('blocked');
    expect(label, anyOf("Won't run", '不会跑'));
    expect(tone, NwTone.warning);
    expect(patrolReasonText('manual_only', 'A'), contains('A'));
    expect(patrolReasonText('manual_only', 'A'), isNot(contains('manual_only')));
    expect(patrolReasonText('第 2 点被挡住', 'A'), '第 2 点被挡住');
  });

  // liang-d5 易用性第 7 轮：「不会跑」点开只写「A 只许手动派」—— 没有去改的入口，也没提路线画在 v11 上
  for (final role in ['guard', 'admin']) {
    testWidgets('第 7 轮 不会跑点开（$role）：写上两边的地图版本、去哪改，有「去机器人页」', (t) async {
      final it = <String, dynamic>{
        'at_ms': DateTime(2027, 3, 15, 22).millisecondsSinceEpoch, 'kind': 'schedule', 'label': 'loop',
        'robot': 'A', 'by': '', 'state': 'blocked', 'reason': 'manual_only', 'end_ms': null,
        'map': {'route': '11', 'robot': '12'},
      };
      await t.pumpWidget(MaterialApp(
          home: Scaffold(body: TodayPatrolList(api: FakeApi(role), items: [it]))));
      await t.tap(find.byKey(todayRowKey(0)));
      await t.pumpAndSettle();
      expect(find.textContaining('路线画在 v11 上，A 用的是 v12'), findsOneWidget);
      expect(find.textContaining(role == 'admin' ? '网页「管理 → 机器人」' : '找管理员'), findsOneWidget);
      await t.tap(find.byKey(const Key('today-robot')));
      await t.pumpAndSettle();
      expect(find.byType(SiteRobotPage), findsOneWidget);
      await t.pumpWidget(Container());
    });
  }
}
