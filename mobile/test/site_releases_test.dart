// 站点模式的版本（W00c5d 第三部分）：管理员给狗装、切、退；切、退要确认；别的角色只看。
import 'package:nexwar_patrol/ui/site_page.dart';
import 'package:nexwar_patrol/ui/site_releases.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'site_page_test.dart' show FakeApi;
import 'support/shell_nav.dart';
import 'package:nexwar_patrol/ui/nw/nw_site_dir.dart';

void main() {
  testWidgets('每台机器人在跑哪一版；管理员装一版、切过去（要确认）、退回', (t) async {
    final api = FakeApi('admin');
    await t.pumpWidget(MaterialApp(home: SiteReleasesPage(api: api)));
    await t.pumpAndSettle();
    expect(find.text('2026-09-20-aaaaaa'), findsOneWidget);
    expect(find.textContaining('夜巡修了一个 bug'), findsOneWidget);
    await t.tap(find.byKey(SiteReleasesPage.actionKey('A', 'install')));
    await t.pumpAndSettle();
    await t.tap(find.byKey(const Key('pick-rel-2026-09-25-bbbbbb')));
    await t.pumpAndSettle();
    expect(api.calls, contains('release A install 2026-09-25-bbbbbb'));
    await t.tap(find.byKey(SiteReleasesPage.actionKey('A', 'activate')));
    await t.pumpAndSettle();
    await t.tap(find.byKey(const Key('pick-rel-2026-09-25-bbbbbb')));
    await t.pumpAndSettle();
    expect(api.calls.where((c) => c.contains('activate')), isEmpty, reason: '没确认之前不发');
    await t.tap(find.byKey(const Key('rel-confirm')));
    await t.pumpAndSettle();
    expect(api.calls, contains('release A activate 2026-09-25-bbbbbb'));
    await t.tap(find.byKey(SiteReleasesPage.actionKey('A', 'rollback')));
    await t.pumpAndSettle();
    await t.tap(find.byKey(const Key('rel-confirm')));
    await t.pumpAndSettle();
    expect(api.calls, contains('release A rollback '));
  });

  testWidgets('查：选一版，清单里拦的在前、提示标出来，什么都不切', (t) async {
    final api = _PrecheckApi();
    await t.pumpWidget(MaterialApp(home: SiteReleasesPage(api: api)));
    await t.pumpAndSettle();
    await t.tap(find.byKey(SiteReleasesPage.actionKey('A', 'precheck')));
    await t.pumpAndSettle();
    await t.tap(find.byKey(const Key('pick-rel-2026-09-25-bbbbbb')));
    await t.pumpAndSettle();
    expect(api.calls, ['release A precheck 2026-09-25-bbbbbb'], reason: '不用确认，也不发别的');
    expect(find.text('不能切换：1 项阻断检查未通过'), findsOneWidget);
    expect(find.text('双槽所在的盘不够'), findsOneWidget);
    expect(find.text('站点备份（仅提示，不阻断）'), findsOneWidget);
    expect(find.text('定位器'), findsOneWidget, reason: '过了的、不拦的不标「提示」');
    final disk = t.getTopLeft(find.byKey(const Key('precheck-item-disk'))).dy;
    final busy = t.getTopLeft(find.byKey(const Key('precheck-item-busy'))).dy;
    expect(disk < busy, isTrue, reason: '拦住的排在过了的前面');
  });

  testWidgets('切被机器人拒：把回执里的清单摆出来', (t) async {
    final api = _PrecheckApi();
    await t.pumpWidget(MaterialApp(home: SiteReleasesPage(api: api)));
    await t.pumpAndSettle();
    await t.tap(find.byKey(SiteReleasesPage.actionKey('A', 'activate')));
    await t.pumpAndSettle();
    await t.tap(find.byKey(const Key('pick-rel-2026-09-25-bbbbbb')));
    await t.pumpAndSettle();
    await t.tap(find.byKey(const Key('rel-confirm')));
    await t.pumpAndSettle();
    expect(find.byKey(const Key('precheck-verdict')), findsOneWidget);
    expect(find.text('双槽所在的盘不够'), findsOneWidget);
  });

  testWidgets('机器人没报在跑哪一版（不支持或不在线）：没有装切退按钮', (t) async {
    final api = _TwoDogsApi();
    await t.pumpWidget(MaterialApp(home: SiteReleasesPage(api: api)));
    await t.pumpAndSettle();
    expect(find.byKey(SiteReleasesPage.actionKey('A', 'install')), findsOneWidget);
    expect(find.byKey(SiteReleasesPage.actionKey('B', 'install')), findsNothing);
  });

  testWidgets('保安只看：没有装切退按钮', (t) async {
    final api = FakeApi('guard');
    await t.pumpWidget(MaterialApp(home: SiteReleasesPage(api: api)));
    await t.pumpAndSettle();
    expect(find.byKey(SiteReleasesPage.robotKey('A')), findsOneWidget);
    expect(find.byKey(SiteReleasesPage.actionKey('A', 'install')), findsNothing);
  });

  // 2026-10-14 重做：入口从狗列表的顶栏挪到了底部导航的「更多」栏（管理员是「管理」栏）。
  testWidgets('W53：管理栏有「软件升级」入口', (t) async {
    final api = FakeApi('admin');
    await t.binding.setSurfaceSize(const Size(400, 1400));
    addTearDown(() => t.binding.setSurfaceSize(null));
    await t.pumpWidget(MaterialApp(home: NwShell(api: api, title: '站点')));
    await t.pumpAndSettle();
    await openSiteDir(t, SiteDest.updates);
    expect(find.byType(SiteReleasesPage), findsOneWidget);
  });
  testWidgets('真机 11-25：站点自己一行、构建号、装的进度条、忙的时候说在忙什么', (t) async {
    final api = _ProgressApi();
    await t.pumpWidget(MaterialApp(home: SiteReleasesPage(api: api)));
    await t.pumpAndSettle();
    expect(find.text('站点（这台电脑）'), findsOneWidget);
    expect(find.text('机器人升级包（存在站点上）'), findsOneWidget);
    expect(find.text('站点上的版本'), findsNothing, reason: '原来这么叫，用户当成站点自己的版本');
    expect(find.text('1.4.0 · 构建 36 · 2026-11-26-abcdef12'), findsOneWidget);
    expect(find.text('2026-11-24-166a47ee · 构建 35'), findsNWidgets(2));
    expect(find.textContaining('2026-11-26-abcdef12（1.0.0） · 构建 36'), findsOneWidget);
    expect(find.byKey(const Key('rel-progress-install-A')), findsOneWidget);
    expect(find.textContaining('编译 Super-LIO'), findsOneWidget);
    expect(find.text('80%'), findsOneWidget);
    expect(find.byKey(const Key('rel-progress-activate-B')), findsOneWidget);
    expect(find.textContaining('正在用新版重启'), findsOneWidget);
    await t.scrollUntilVisible(find.byKey(const Key('rel-app-version')), 200);
    expect(find.textContaining('（构建 '), findsOneWidget, reason: '这台手机也写构建号');
    await t.pumpWidget(const SizedBox());
  });

  test('真机 11-25：拒的原因是忙，写清在忙什么', () {
    expect(releaseReasonText('busy: 正在装 r36(编 Super-LIO,80%) —— 重启那几秒谁都无法停止它,等它完'),
        '机器人在忙：正在装 r36（编译 Super-LIO（约 4 分钟），80%）。等它忙完再试');
    expect(releaseReasonText('busy: 在录包 —— 重启那几秒谁都无法停止它,等它完'), '机器人在忙：在录包。等它忙完再试');
  });
}

class _ProgressApi extends FakeApi {
  _ProgressApi() : super('admin');
  @override
  Future<Map<String, dynamic>> releases() async => {
        'releases': <Object>[
          {'name': '2026-11-26-abcdef12', 'version': '1.0.0', 'size': 1048576, 'build': 36},
        ],
        'robots': {'A': '2026-11-24-166a47ee', 'B': '2026-11-24-166a47ee'},
        'builds': {'A': 35, 'B': 35},
        'last': {
          'A': {
            'cmd': {'kind': 'release_install', 'name': '2026-11-26-abcdef12', 'at_ms': 1, 'result': 'accepted'},
            'event': null,
            'progress': {'name': '2026-11-26-abcdef12', 'stage': 'superlio', 'pct': 80, 'at_ms': 2},
          },
          'B': {
            'cmd': {'kind': 'release_activate', 'name': '2026-11-26-abcdef12', 'at_ms': 5, 'result': 'accepted'},
            'event': {'kind': 'release_activating', 'name': '2026-11-26-abcdef12', 'at_ms': 6},
            'progress': null,
          },
        },
      };
  @override
  Future<Map<String, dynamic>> versions() async => {
        'site': {'version': '1.4.0', 'release_build': 36, 'release_name': '2026-11-26-abcdef12'},
        'robots': <Object>[],
      };
}

class _PrecheckApi extends FakeApi {
  _PrecheckApi() : super('admin');
  static const _checks = <Object>[
    {'name': 'busy', 'ok': true, 'blocking': true, 'detail': '空闲'},
    {'name': 'disk', 'ok': false, 'blocking': true, 'detail': '双槽所在的盘不够'},
    {'name': 'backup', 'ok': false, 'blocking': false, 'detail': '站点没配备份盘'},
    {'name': 'localizer', 'ok': true, 'blocking': false, 'detail': '定位器（W09）还没部署'},
  ];
  @override
  Future<Map<String, dynamic>> releaseAction(String robotId, String action,
      {String name = ''}) async {
    calls.add('release $robotId $action $name');
    if (action == 'precheck') {
      return <String, dynamic>{'ok': false, 'blocking': <Object>['disk'], 'checks': _checks};
    }
    return <String, dynamic>{
      'ack': <String, dynamic>{
        'result': 'rejected',
        'reason': 'storage_full',
        'data': <String, dynamic>{'ok': false, 'blocking': <Object>['disk'], 'checks': _checks},
      }
    };
  }
}

/// 两台狗：A 报了在跑哪一版，B 没报（不支持站点下发版本，或者不在线）。
class _TwoDogsApi extends FakeApi {
  _TwoDogsApi() : super('admin');
  @override
  Future<Map<String, dynamic>> releases() async => {
        'releases': <Object>[],
        'robots': {'A': '2026-09-20-aaaaaa', 'B': null},
      };
}
