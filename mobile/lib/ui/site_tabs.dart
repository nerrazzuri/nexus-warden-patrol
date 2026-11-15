/// 底部第 5 栏（W53，按角色）：管理员、工程师是「管理」，经理是「日程」，保安和只看的是「我的」。
///
/// - **管理**：最上面「要你处理」（挡着机器人干活、挡着别人用的事，一行一个、带按钮直接去）；开站清单；
///   下面三组（巡逻 / 报警联动 / 人和系统），每项一句话说清楚是干嘛的。
/// - **日程**：今天（跟值守页「今天的巡逻」同一份）、每周（每条日程哪几天几点、哪条路线、哪台；能加、改、删）。
/// - **我的**：账号、角色、使用教程、常见问题、退出站点。
library;

import 'dart:async';

import 'package:flutter/material.dart';

import '../l10n.dart';
import '../model/alert.dart';
import '../net/site_text.dart' show alertLine;
import 'alarm_log.dart' show AlarmLogPage;
import '../net/site_client.dart';
import '../store/site_store.dart';
import 'app_settings.dart';
import 'guide.dart';
import 'map_wizard.dart' show openMapWizard;
import 'nw/nw_button.dart';
import 'nw/nw_p4_admin.dart' show nwGap8, NwListView;
import 'nw/nw_theme.dart';
import 'nw/nw_widgets.dart';
import 'patrol_dispatch.dart';
import 'nw/nw_p3_robots.dart' show robotBattery, robotPhase, robotPhaseTone;
import 'site_deter.dart' show nwRobotSection;
import 'site_intercepts.dart';
import 'site_robot.dart' show robotStatusLine;
import 'site_mapping.dart';
import 'site_routes.dart';

void _push(BuildContext context, Widget page) =>
    Navigator.push(context, MaterialPageRoute<void>(builder: (_) => page));

/// 退出站点（回站点列表；外壳那一页退掉时站点列表注销会话、停推送）。每个角色的第 5 栏都有。
///
/// 手机 App 测试 M01：外壳不让返回键退出（按返回只回值守页、退到后台），所以这里先问一句，再直接退掉外壳那一页。
Future<void> leaveSite(BuildContext context) async {
  final ok = await showDialog<bool>(
      context: context,
      builder: (c) => AlertDialog(
            title: Text(tr('Leave this site?', '退出这个站点？')),
            content: Text(tr(
                'You will be signed out. Background monitoring stops, so this phone will no longer get alarms from this site.',
                '退出后会注销登录，后台值守也会停止，这台手机将收不到这个站点的报警。')),
            actions: [
              TextButton(onPressed: () => Navigator.pop(c, false), child: Text(tr('Cancel', '取消'))),
              FilledButton(
                  key: leaveConfirmKey,
                  onPressed: () => Navigator.pop(c, true),
                  child: Text(tr('Leave', '退出'))),
            ],
          ));
  if (ok != true || !context.mounted) return;
  Navigator.of(context, rootNavigator: true).pop();
}

const Key leaveSiteKey = Key('leave-site');
const Key leaveConfirmKey = Key('leave-site-confirm');

/// 一个入口：图标、名字、一句说明。
class _Entry extends StatelessWidget {
  final Key entryKey;
  final IconData icon;
  final String title;
  final String hint;
  final VoidCallback onTap;
  const _Entry({required this.entryKey, required this.icon, required this.title, required this.hint, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final c = Nw.of(context);
    return Padding(
      padding: const EdgeInsets.only(bottom: Nw.s8),
      child: NwCard(
        key: entryKey,
        onTap: onTap,
        child: Row(children: [
          Icon(icon, color: c.textSecondary),
          const SizedBox(width: Nw.s16),
          Expanded(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(title, style: NwText.titleSmall.copyWith(color: c.text, fontWeight: FontWeight.w700)),
            const SizedBox(height: 2),
            Text(hint, style: NwText.bodySmall.copyWith(color: c.textSecondary)),
          ])),
          Icon(Icons.chevron_right_rounded, color: c.textSecondary),
        ]),
      ),
    );
  }
}

// ------------------------------------------------------------ 开站清单

/// 开站清单每一项的名字、说明（站点只给 id）。
(String, String) setupItemText(String id) => switch (id) {
      'robots' => (tr('Add robots', '添加机器人'), tr('Robots → Add, scan the sticker on the robot.', '在「机器人 → 添加」中扫描机器人贴纸。')),
      'map' => (
          tr('Map', '地图'),
          tr('Walk the robot around the site once with the mapping wizard (20–40 minutes).',
              '按建图向导操作，开着机器人走一圈（约 20–40 分钟）。')
        ),
      'home' => (tr('Origin for each robot', '每台机器人的原点'),
          tr("Mark where each robot starts on the map it uses now. Without one it can't go anywhere on its own.",
              '在机器人现在用的这版地图上标出发位置。没有原点，机器人不能自己出发。')),
      'zones' => (tr('Confirm no-go zones', '确认禁行区'),
          tr("Robots don't go out on their own until the no-go zones are confirmed.", '禁行区确认前，机器人不会自主出发。')),
      'standby' => (tr('Standby points', '待命点'),
          tr('Where each robot waits and returns to after a patrol.', '每台机器人的待命位置和巡逻后返回位置。')),
      'routes' => (tr('Patrol routes', '巡逻路线'), tr('Draw routes on the map.', '在地图上画路线。')),
      'schedule' => (tr('Patrol schedule', '巡逻日程'), tr('When each route runs, and on which robot.', '各路线的执行时间和执行机器人。')),
      'arming' => (tr('Arming times', '布防时间'),
          tr('When the site arms and disarms automatically (set on the web console). Tap Skip if you always switch manually.',
              '自动布防、撤防的时间（在网页值班台设置）。始终手动切换请点「跳过」。')),
      'accounts' => (tr('Create accounts for your team', '为保安、经理开通账号'),
          tr('Approve applications or add accounts.', '审批申请或直接添加账号。')),
      'push' => (tr('Phone alerts', '手机推送'), tr('At least one phone signed in and receiving P1 alerts.', '至少一部手机已登录并能收到 P1 推送。')),
      _ => (id, ''),
    };

/// 第 8 轮 W8-08：清单那一项的具体情况（路线都画在别的版本上、日程的路线跑不了）；没有就是空，用通用说明。
String setupDetailText(Map it) {
  String ver(Object? m) => m is Map ? ('${m['version'] ?? ''}'.isEmpty ? '${m['map']}' : 'v${m['version']}') : '';
  final away = it['elsewhere'], use = it['using'], blocked = it['blocked'];
  if (it['id'] == 'routes' && away is List && away.isNotEmpty && use is List && use.isNotEmpty) {
    final sep = tr(', ', '\u3001');
    final names = away.map((r) => r is Map ? '${r['route']}' : '').join(sep);
    final at = away.map(ver).toSet().join(sep), u = use.map(ver).join(sep);
    return tr('${away.length} route(s) ($names) are drawn on $at, but the robots use $u: redraw on $u.',
        '有 ${away.length} 条路线（$names）画在 $at 上，机器人在用 $u：在 $u 上重画。');
  }
  final noMap = it['no_map'];
  if ((it['id'] == 'home' || it['id'] == 'standby') && it['done'] != true && noMap is List && noMap.isNotEmpty) {
    // minor #40：登记了还没报在用哪张图的机器人
    final ids = noMap.join(tr(', ', '\u3001'));
    return tr("$ids hasn't reported which map it is using yet, so this can't be checked. Turn it on and let it localize, then look again.",
        '$ids 还没报在用哪张图，查不了这一项。开机、定好位以后再看。');
  }
  final home = it['at_home'];
  if (it['id'] == 'standby' && it['done'] == true && home is List && home.isNotEmpty) {
    // minor #21：标原点时站点顺手加的待命点就在原点上
    final ids = home.join(tr(', ', '\u3001'));
    return tr('The standby point of $ids is its origin (added automatically when the origin was marked). '
        'To park it somewhere else, add a standby point on the Layout page.',
        '$ids 的待命点就是原点（标原点时自动加的）。想让它停到别处，在网页布置页加一个待命点。');
  }
  if (it['id'] == 'schedule' && blocked is List && blocked.isNotEmpty) {
    final names = blocked.join(tr(', ', '\u3001'));
    return tr("Schedule $names can't run its route (drawn on another map version, or deleted): change the route or redraw it.",
        '日程 $names 要跑的路线跑不了（画在别的地图版本上或已删除）：改路线或重画。');
  }
  return '';
}

class SetupChecklist extends StatefulWidget {
  final SiteApi api;
  /// 「去做」按到哪儿（外壳给：切到哪一栏或推哪一页）。
  final void Function(BuildContext context, String id) go;
  const SetupChecklist({super.key, required this.api, required this.go});

  static const Key cardKey = Key('setup-card');
  static Key itemKey(String id) => Key('setup-$id');
  static Key goKey(String id) => Key('setup-go-$id');
  static Key skipKey(String id) => Key('setup-skip-$id');
  static const Key hideKey = Key('setup-hide');
  static const Key showKey = Key('setup-show');

  @override
  State<SetupChecklist> createState() => _SetupChecklistState();
}

class _SetupChecklistState extends State<SetupChecklist> {
  Map<String, dynamic>? _setup;
  Map<String, dynamic>? _guide;
  bool _open = false;

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  Future<void> _load() async {
    try {
      final got = await Future.wait([widget.api.setup(), widget.api.me()]);
      if (!mounted) return;
      setState(() {
        _setup = got[0];
        final g = got[1]['guide'];
        _guide = g is Map ? g.cast<String, dynamic>() : <String, dynamic>{};
        _open = _guide!['setup_hidden'] != true;
      });
    } on SiteError {
      // 老站点没有清单：不摆
    } on FormatException {
      // 同上
    }
  }

  Future<void> _patch(Map<String, dynamic> p) async {
    try {
      final g = await widget.api.setGuide(p);
      if (mounted) setState(() => _guide = g);
    } on SiteError catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(refusalText(e))));
    }
    await _load();
  }

  @override
  Widget build(BuildContext context) {
    final c = Nw.of(context);
    final s = _setup;
    if (s == null) return const SizedBox.shrink();
    final items = [for (final x in (s['items'] as List? ?? const [])) if (x is Map) x.cast<String, dynamic>()];
    final done = s['done'], total = s['total'];
    final all = done == total;
    final skip = [for (final x in (_guide?['skip'] as List? ?? const [])) '$x'];
    return Padding(
      padding: const EdgeInsets.only(bottom: Nw.s16),
      child: NwCard(
        key: SetupChecklist.cardKey,
        child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          Row(children: [
            Expanded(
                child: Text(
                    all ? tr('Site setup done ($done/$total)', '开站清单已完成（$done/$total）') : tr('Site setup $done/$total', '开站清单 $done/$total'),
                    style: NwText.titleSmall.copyWith(color: c.text, fontWeight: FontWeight.w700))),
            if (_open)
              TextButton(
                  key: SetupChecklist.hideKey,
                  onPressed: () {
                    setState(() => _open = false);
                    unawaited(_patch(<String, dynamic>{'setup_hidden': true}));
                  },
                  child: Text(all ? tr('Hide', '收起') : tr('Not now', '暂不处理')))
            else
              TextButton(
                  key: SetupChecklist.showKey,
                  onPressed: () => setState(() => _open = true),
                  child: Text(tr('Show', '展开'))),
          ]),
          if (_open)
            for (final it in items)
              Padding(
                key: SetupChecklist.itemKey('${it['id']}'),
                padding: const EdgeInsets.only(top: Nw.s8),
                child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Icon(
                      it['done'] == true
                          ? Icons.check_circle_rounded
                          : (it['skipped'] == true ? Icons.remove_circle_outline_rounded : Icons.radio_button_unchecked_rounded),
                      size: 20,
                      color: it['done'] == true ? c.success : c.textSecondary),
                  const SizedBox(width: Nw.s8),
                  Expanded(
                      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Text(setupItemText('${it['id']}').$1, style: NwText.bodyMedium.copyWith(color: c.text)),
                    if (it['done'] != true)
                      Text(setupDetailText(it).isNotEmpty ? setupDetailText(it) : setupItemText('${it['id']}').$2,
                          style: NwText.bodySmall.copyWith(color: c.textSecondary))
                    else if (setupDetailText(it).isNotEmpty)
                      Text(setupDetailText(it), style: NwText.bodySmall.copyWith(color: c.textSecondary)),
                  ])),
                  if (it['done'] != true && it['skipped'] != true) ...[
                    TextButton(
                        key: SetupChecklist.skipKey('${it['id']}'),
                        onPressed: () => _patch(<String, dynamic>{'skip': <String>[...skip, '${it['id']}']}),
                        child: Text(tr('Skip', '跳过'))),
                    NwButton(
                        buttonKey: SetupChecklist.goKey('${it['id']}'),
                        size: NwButtonSize.small,
                        label: tr('Do it', '前往'),
                        onPressed: () async {
                          widget.go(context, '${it['id']}');
                        }),
                  ],
                ]),
              ),
        ]),
      ),
    );
  }
}

// ------------------------------------------------------------ 管理栏

class AdminHomeTab extends StatefulWidget {
  final SiteApi api;
  final SiteEntry? entry;
  /// 切到底部的某一栏（「去做」用：机器人栏、地图栏）。
  final void Function(int tab) switchTab;
  const AdminHomeTab({super.key, required this.api, required this.switchTab, this.entry});

  static const Key todoKey = Key('admin-todo');
  static Key entryKey(String id) => Key('admin-entry-$id');

  @override
  State<AdminHomeTab> createState() => _AdminHomeTabState();
}

class _AdminHomeTabState extends State<AdminHomeTab> {
  List<(String, String, VoidCallback)> _todo = const [];

  /// 今天（App V2 稿 S-home）：报警几条（几条没结）、巡逻跑完几趟、误报几条；今晚的巡逻几点。
  ({int alarms, int open, int falseAlarms, int patrols, List<String> times})? _today;
  List<Map<String, dynamic>> _robots = const [];

  /// 经理那一版（稿 S-home-m）：24 小时的报警、最新一条交班留言、站点的布防模式。
  List<Alert> _day = const [];
  Map<String, dynamic>? _note;
  Map<String, dynamic>? _mode;

  bool get _manager => !(widget.api.session?.canManageMaps ?? false);

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  Future<void> _load() async {
    final s = widget.api.session;
    final todo = <(String, String, VoidCallback)>[];
    try {
      final setup = await widget.api.setup();
      for (final x in (setup['items'] as List? ?? const [])) {
        if (x is Map && x['id'] == 'zones' && x['done'] != true) {
          for (final m in (x['maps'] as List? ?? const [])) {
            final parts = '$m'.split(':');
            if (parts.length != 2) continue;
            todo.add(('zones-$m', tr('No-go zones on $m are not confirmed: robots won\'t go out on their own',
                    '$m 的禁行区未确认：机器人不会自主出发'), () {
              _push(context, SiteMapPreviewPage(api: widget.api, mapId: parts[0], version: parts[1]));
            }));
          }
        }
      }
    } on SiteError {
      // 老站点：没有清单
    } on FormatException {
      // 同上
    }
    if (s?.canManageRobots ?? false) {
      try {
        final n = (await widget.api.bindRequests()).length;
        if (n > 0) {
          todo.add(('bind', tr(n == 1 ? '1 robot waiting to join' : '$n robots waiting to join', '$n 台机器人待批准加入'), () => widget.switchTab(1)));
        }
      } on SiteError {
        // 站点没开绑定
      }
    }
    if (s?.canManageAccounts ?? false) {
      try {
        final n = (await widget.api.accountRequests()).length;
        if (n > 0) {
          todo.add(('accounts', tr('$n account application(s) waiting', '$n 个账号待批准'),
              () => _push(context, AccountsPage(api: widget.api))));
        }
      } on SiteError {
        // 老站点
      }
    }
    try {
      final d = await widget.api.intercepts();
      final used = {for (final z in (d['zones'] as List? ?? const [])) if (z is Map) '${z['intercept']}'};
      for (final i in (d['intercepts'] as List? ?? const [])) {
        if (i is Map && !used.contains('${i['name']}')) {
          todo.add(('intercept-${i['name']}', tr('Intercept point "${i['name']}" isn\'t linked to any zone',
                  '拦截点「${i['name']}」未关联防区'), () => _push(context, SiteInterceptsPage(api: widget.api))));
        }
      }
    } on SiteError {
      // 站点没开
    }
    if (mounted) setState(() => _todo = todo);
    await _loadToday();
  }

  Future<void> _loadToday() async {
    final now = DateTime.now();
    final midnight = DateTime(now.year, now.month, now.day).millisecondsSinceEpoch;
    try {
      final got = await Future.wait<Object>([
        widget.api.alerts(all: true),
        widget.api.patrolsToday().catchError((Object _) => <String, dynamic>{}),
        widget.api.robots().catchError((Object _) => <Map<String, dynamic>>[]),
      ]);
      final all = got[0] as List<Alert>;
      final alerts = all.where((a) => a.firstMs >= midnight).toList();
      final since = now.millisecondsSinceEpoch - const Duration(hours: 24).inMilliseconds;
      final day = [for (final a in all) if (a.firstMs >= since && AlarmLogPage.isAlarm(a)) a]
        ..sort((a, b) => b.firstMs.compareTo(a.firstMs));
      final items = [for (final x in ((got[1] as Map)['items'] as List? ?? const [])) if (x is Map) x];
      String hm(Object? ms) {
        if (ms is! num) return '';
        final d = DateTime.fromMillisecondsSinceEpoch(ms.toInt());
        return '${d.hour.toString().padLeft(2, '0')}:${d.minute.toString().padLeft(2, '0')}';
      }
      if (!mounted) return;
      setState(() {
        _today = (
          alarms: alerts.length,
          open: alerts.where((a) => !a.resolved).length,
          falseAlarms: alerts.where((a) => a.verdict == 'false_alarm').length,
          patrols: items.where((x) => x['state'] == 'done').length,
          times: [for (final x in items) if (hm(x['start_ms'] ?? x['at_ms']).isNotEmpty) hm(x['start_ms'] ?? x['at_ms'])],
        );
        _robots = [for (final r in got[2] as List<Map<String, dynamic>>) if (r['revoked'] != true) r];
        _day = day;
      });
    } on SiteError {
      // 读不到就不摆「今天」
    }
    if (!_manager) return;
    try {
      final notes = await widget.api.shiftNotes(recent: 1);
      if (mounted) setState(() => _note = notes.firstOrNull);
    } on SiteError {
      // 老站点没有交班留言
    }
    try {
      final m = await widget.api.mode();
      if (mounted) setState(() => _mode = m);
    } on SiteError {
      // 同上
    }
  }

  static String _hm(Object? ms) {
    if (ms is! num) return '';
    final d = DateTime.fromMillisecondsSinceEpoch(ms.toInt());
    return '${d.hour.toString().padLeft(2, '0')}:${d.minute.toString().padLeft(2, '0')}';
  }

  /// 经理的概况（稿 S-home-m）：只看。24 小时报警（谁处理、结论）、管理员那边的事（只写状态）、值班（最新交班留言）、
  /// 今天的安排（布防、巡逻几点）。
  Widget _managerView(BuildContext context) {
    final c = Nw.of(context);
    final sub = NwText.bodySmall.copyWith(color: c.textSecondary);
    String outcome(Alert a) => a.resolvedMs == null
        ? (a.ackedBy.isNotEmpty ? tr('Handling', '处理中') : tr('Open', '未处理'))
        : switch (a.verdict) {
            'false_alarm' => tr('False alarm', '误报'),
            'intruder' => tr('Confirmed intrusion', '确认入侵'),
            _ => tr('Resolved', '已解决'),
          };
    final t = _today;
    final m = _mode;
    final armed = m == null ? '' : (m['state'] ?? m['mode']) == 'armed' ? tr('Armed', '布防中') : tr('Disarmed', '撤防');
    final next = m?['next_change_ms'];
    final plan = [
      if (m != null) next is num ? tr('$armed · changes at ${_hm(next)}', '$armed · ${_hm(next)} 切换') : armed,
      if (t != null && t.times.isNotEmpty) tr('Patrols ${t.times.join(' / ')}', '巡逻 ${t.times.join(' / ')}'),
    ];
    return Scaffold(
      backgroundColor: c.bg,
      body: Column(children: [
        NwHeader(title: tr('Overview', '概况'), subtitle: tr('View only', '只看')),
        Expanded(
            child: RefreshIndicator(
                onRefresh: _load,
                child: ListView(padding: const EdgeInsets.only(bottom: Nw.s24), children: [
                  nwRobotSection(c, tr('Alarms, last 24 h: ${_day.length}', '24 小时报警：${_day.length}'), key: const Key('overview-day'), [
                    if (_day.isEmpty) Text(tr('No alarms.', '没有报警。'), style: sub),
                    for (final a in _day)
                      Container(
                          key: Key('overview-alarm-${a.key}'),
                          padding: const EdgeInsets.symmetric(vertical: 8),
                          decoration: BoxDecoration(border: Border(top: BorderSide(color: c.outline))),
                          child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                            SizedBox(width: 52, child: Text(_hm(a.firstMs), style: NwText.bodyMedium.copyWith(color: c.textSecondary))),
                            Padding(
                                padding: const EdgeInsets.only(top: 3, right: Nw.s8),
                                child: Icon(a.level == 'P1' ? Icons.radio_button_checked : Icons.circle_outlined,
                                    size: 16, color: a.level == 'P1' ? c.error : c.textSecondary)),
                            Expanded(
                                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                              Text(alertLine(a.robot, a.kind, a.title),
                                  style: NwText.titleSmall.copyWith(color: c.text, fontWeight: FontWeight.w700)),
                              Text([if (a.ackedBy.isNotEmpty) a.ackedBy, outcome(a)].join(' · '), style: sub),
                            ])),
                          ])),
                  ]),
                  if (_todo.isNotEmpty)
                    nwRobotSection(c, tr('With administrator', '在管理员那边'), key: const Key('overview-admin'), [
                      Text(tr('Status only.', '只看状态。'), style: sub),
                      for (final it in _todo)
                        Container(
                            padding: const EdgeInsets.symmetric(vertical: 8),
                            decoration: BoxDecoration(border: Border(top: BorderSide(color: c.outline))),
                            child: Row(children: [
                              Container(width: 10, height: 10, decoration: BoxDecoration(color: c.primary, shape: BoxShape.circle)),
                              const SizedBox(width: 10),
                              Expanded(child: Text(it.$2, style: NwText.bodyMedium.copyWith(color: c.text, fontWeight: FontWeight.w600))),
                            ])),
                    ]),
                  if (_note != null)
                    nwRobotSection(c, tr('On duty', '值班'), key: const Key('overview-duty'), [
                      Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                        SizedBox(width: 96, child: Text(tr('Handover notes', '交班留言'), style: sub)),
                        Expanded(
                            child: Text('${_note!['author'] ?? ''} ${_hm(_note!['at_ms'])}${tr(': ', '：')}${_note!['text'] ?? ''}',
                                style: NwText.bodyMedium.copyWith(color: c.text))),
                      ]),
                    ]),
                  if (plan.isNotEmpty)
                    nwRobotSection(c, tr("Today's schedule", '今天的安排'), key: const Key('overview-plan'), [
                      Text(plan.join(' · '), style: sub),
                    ]),
                ]))),
      ]),
    );
  }

  void _go(BuildContext context, String id) {
    switch (id) {
      case 'robots' || 'standby' || 'home':
        widget.switchTab(1);
      case 'map':
        unawaited(openMapWizard(context, widget.api).then((_) => _load()));
      case 'zones':
        widget.switchTab(2);
      case 'routes':
        _push(context, SiteRoutesPage(api: widget.api));
      case 'schedule':
        _push(context, SchedulePage(api: widget.api));
      case 'accounts':
        _push(context, AccountsPage(api: widget.api));
      case 'push' || 'arming':
        _push(context, HelpPage(role: widget.api.session?.role ?? ''));
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_manager) return _managerView(context);
    final c = Nw.of(context);
    // App V2 稿 S-home：待处理、开站清单、今天、机器人。路线、日程、摄像头、拦截点在「地图与布置」，天气在「布防与巡逻」，
    // 设置、教程在「现场」目录的「本机」那一组。
    final t = _today;
    Widget stat(String n, String label, Key key) => Expanded(
        child: Container(
            key: key,
            padding: const EdgeInsets.all(10),
            decoration: BoxDecoration(border: Border.all(color: c.outline)),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(n, style: NwText.headlineSmall.copyWith(color: c.text, fontWeight: FontWeight.w700)),
              Text(label, style: NwText.bodySmall.copyWith(color: c.textSecondary)),
            ])));
    return Scaffold(
      backgroundColor: c.bg,
      body: Column(children: [
        NwHeader(
            title: tr('Overview', '概况'),
            subtitle: _todo.isEmpty ? null : tr('${_todo.length} pending', '${_todo.length} 件待处理')),
        Expanded(
          child: RefreshIndicator(
            onRefresh: _load,
            child: ListView(padding: const EdgeInsets.only(bottom: Nw.s24), children: [
              if (_todo.isNotEmpty)
                nwRobotSection(c, tr('Pending ${_todo.length}', '待处理 ${_todo.length}'), key: AdminHomeTab.todoKey, [
                  for (final it in _todo)
                    Container(
                      padding: const EdgeInsets.symmetric(vertical: 10),
                      decoration: BoxDecoration(border: Border(top: BorderSide(color: c.outline))),
                      child: Row(children: [
                        Container(width: 10, height: 10, decoration: BoxDecoration(color: c.primary, shape: BoxShape.circle)),
                        const SizedBox(width: 10),
                        Expanded(child: Text(it.$2, style: NwText.bodyMedium.copyWith(color: c.text, fontWeight: FontWeight.w600))),
                        const SizedBox(width: Nw.s8),
                        FilledButton(
                            key: Key('todo-${it.$1}'),
                            style: FilledButton.styleFrom(
                                minimumSize: const Size(48, 40),
                                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(2))),
                            onPressed: it.$3,
                            child: Text(tr('Go', '去处理'))),
                      ]),
                    ),
                ]),
              SetupChecklist(api: widget.api, go: _go),
              if (t != null)
                nwRobotSection(c, tr('Today', '今天'), key: const Key('overview-today'), [
                  // 三格一样高（某格字换行也不高低不齐）
                  IntrinsicHeight(
                      child: Row(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                    stat('${t.alarms}', t.open > 0 ? tr('Alarms (${t.open} open)', '报警（${t.open} 条没结）') : tr('Alarms', '报警'),
                        const Key('overview-alarms')),
                    stat('${t.patrols}', tr('Patrols completed', '巡逻跑完'), const Key('overview-patrols')),
                    stat('${t.falseAlarms}', tr('False alarms', '误报'), const Key('overview-false')),
                  ])),
                  if (t.times.isNotEmpty) ...[
                    const SizedBox(height: Nw.s8),
                    Text(tr('Patrols ${t.times.join(' / ')}', '巡逻 ${t.times.join(' / ')}'),
                        style: NwText.bodySmall.copyWith(color: c.textSecondary)),
                  ],
                ]),
              if (_robots.isNotEmpty)
                nwRobotSection(c, tr('Robots', '机器人'), key: const Key('overview-robots'), [
                  for (final r in _robots)
                    InkWell(
                        key: Key('overview-robot-${r['robot_id']}'),
                        onTap: () => widget.switchTab(1),
                        child: Padding(
                            padding: const EdgeInsets.symmetric(vertical: 8),
                            child: Row(children: [
                              Container(width: 10, height: 10, color: c.fg(robotPhaseTone(robotPhase(r)))),
                              const SizedBox(width: 10),
                              Text('${r['robot_id']}', style: NwText.titleSmall.copyWith(color: c.text, fontWeight: FontWeight.w700)),
                              const SizedBox(width: 10),
                              Expanded(
                                  child: Text(robotStatusLine(r),
                                      maxLines: 1, overflow: TextOverflow.ellipsis, style: NwText.bodyMedium.copyWith(color: c.text))),
                              if (robotBattery(r) != null)
                                Text('${robotBattery(r)!.round()}%',
                                    style: NwText.titleSmall.copyWith(color: c.text, fontWeight: FontWeight.w700)),
                            ]))),
                ]),
            ]),
          ),
        ),
      ]),
    );
  }
}

// ------------------------------------------------------------ 账号审批（W52）

class AccountsPage extends StatefulWidget {
  final SiteApi api;
  const AccountsPage({super.key, required this.api});

  static Key approveKey(String id) => Key('acct-approve-$id');
  static Key rejectKey(String id) => Key('acct-reject-$id');
  static Key roleKey(String id) => Key('acct-role-$id');

  @override
  State<AccountsPage> createState() => _AccountsPageState();
}

class _AccountsPageState extends State<AccountsPage> {
  List<Map<String, dynamic>>? _reqs;
  List<Map<String, dynamic>> _all = const [];
  final Map<String, String> _roles = <String, String>{};
  String? _msg;

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  Future<void> _load() async {
    try {
      final r = await widget.api.accountRequests();
      if (mounted) setState(() => _reqs = r);
    } on SiteError catch (e) {
      if (mounted) setState(() => _msg = refusalText(e));
    }
    try {
      final a = await widget.api.accounts();
      if (mounted) setState(() => _all = a);
    } on SiteError {
      // 老站点、没权限：不列
    }
  }

  Future<void> _approve(Map<String, dynamic> r) async {
    final id = '${r['id']}';
    final role = _roles[id] ?? 'viewer';
    final pw = TextEditingController();
    final ok = await showDialog<bool>(
        context: context,
        builder: (c) => AlertDialog(
              title: Text(tr('Approve ${r['display']}', '批准 ${r['display']}')),
              content: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text(tr('Account "${r['name']}" as ${roleName(role)}. Enter your password to confirm.',
                    '账号「${r['name']}」，权限：${roleName(role)}。请输入你的密码确认。')),
                TextField(
                    key: const Key('acct-confirm-pw'),
                    controller: pw,
                    obscureText: true,
                    decoration: InputDecoration(labelText: tr('Your password', '你的密码'))),
              ]),
              actions: [
                TextButton(onPressed: () => Navigator.pop(c, false), child: Text(tr('Cancel', '取消'))),
                FilledButton(
                    key: const Key('acct-confirm-go'),
                    onPressed: () => Navigator.pop(c, true),
                    child: Text(tr('Approve', '批准'))),
              ],
            ));
    if (ok != true) return;
    try {
      await widget.api.approveAccount(id, role, pw.text);
      if (mounted) setState(() => _msg = tr('Approved ${r['name']}', '批准了 ${r['name']}'));
    } on SiteError catch (e) {
      if (mounted) setState(() => _msg = refusalText(e));
    }
    await _load();
  }

  Future<void> _reject(Map<String, dynamic> r) async {
    try {
      await widget.api.rejectAccount('${r['id']}');
    } on SiteError catch (e) {
      if (mounted) setState(() => _msg = refusalText(e));
    }
    await _load();
  }

  /// 账号那一行右边写什么：本机、停用、到期、最近登录。
  String _state(Map<String, dynamic> a) {
    if (a['disabled'] == true) return tr('Disabled', '已停用');
    if (a['expired'] == true) return tr('Expired', '已过期');
    final until = a['expires_ms'];
    if (until is num) {
      final d = DateTime.fromMillisecondsSinceEpoch(until.toInt());
      String two(int x) => x.toString().padLeft(2, '0');
      return tr('Until ${two(d.month)}-${two(d.day)} ${two(d.hour)}:${two(d.minute)}', '到 ${two(d.month)}-${two(d.day)} ${two(d.hour)}:${two(d.minute)}');
    }
    if (a['name'] == widget.api.session?.name) return tr('This phone', '本机');
    return a['last_login_ms'] == null ? tr('Never signed in', '没登录过') : '';
  }

  @override
  Widget build(BuildContext context) {
    final c = Nw.of(context);
    final reqs = _reqs;
    const roles = <String>['viewer', 'guard', 'owner', 'admin'];
    final shape = RoundedRectangleBorder(borderRadius: BorderRadius.circular(2));
    // App V2 稿 S-people：待批准在上（一排等宽「批准 / 拒绝」），下面全部账号一行一个
    return Scaffold(
      appBar: AppBar(
          title: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(tr('Users', '人员')),
        Text(
            tr('${_all.length} accounts · ${reqs?.length ?? 0} pending approval', '${_all.length} 个账号 · ${reqs?.length ?? 0} 个待批准'),
            style: NwText.bodySmall.copyWith(color: c.textSecondary)),
      ])),
      body: ListView(padding: const EdgeInsets.only(bottom: Nw.s24), children: [
        if (_msg != null) Padding(padding: const EdgeInsets.all(Nw.s16), child: NwNotice(text: _msg!)),
        nwRobotSection(c, tr('Pending approval ${reqs?.length ?? 0}', '待批准 ${reqs?.length ?? 0}'), key: const Key('acct-pending'), [
          if (reqs == null)
            const Center(child: CircularProgressIndicator())
          else if (reqs.isEmpty)
            Text(tr('No pending applications.', '没有待批准的申请。'), style: NwText.bodyMedium.copyWith(color: c.textSecondary))
          else
            for (final r in reqs)
              Padding(
                padding: const EdgeInsets.only(bottom: Nw.s16),
                child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                  Row(children: [
                    Container(width: 10, height: 10, decoration: BoxDecoration(color: c.primary, shape: BoxShape.circle)),
                    const SizedBox(width: 10),
                    Expanded(
                        child: Text('${r['display']} · ${r['name']}',
                            style: NwText.titleSmall.copyWith(color: c.text, fontWeight: FontWeight.w700))),
                  ]),
                  Row(children: [
                    Text(tr('Role', '权限'), style: NwText.bodyMedium.copyWith(color: c.textSecondary)),
                    const SizedBox(width: Nw.s16),
                    DropdownButton<String>(
                        key: AccountsPage.roleKey('${r['id']}'),
                        value: _roles['${r['id']}'] ?? 'viewer',
                        items: [for (final x in roles) DropdownMenuItem(value: x, child: Text(roleName(x)))],
                        onChanged: (v) => setState(() => _roles['${r['id']}'] = v ?? 'viewer')),
                  ]),
                  Row(children: [
                    Expanded(
                        child: FilledButton(
                            key: AccountsPage.approveKey('${r['id']}'),
                            style: FilledButton.styleFrom(minimumSize: const Size(48, 48), shape: shape),
                            onPressed: () => _approve(r),
                            child: Text(tr('Approve', '批准')))),
                    const SizedBox(width: Nw.s8),
                    Expanded(
                        child: OutlinedButton(
                            key: AccountsPage.rejectKey('${r['id']}'),
                            style: OutlinedButton.styleFrom(minimumSize: const Size(48, 48), shape: shape),
                            onPressed: () => _reject(r),
                            child: Text(tr('Reject', '拒绝')))),
                  ]),
                ]),
              ),
        ]),
        if (_all.isNotEmpty)
          nwRobotSection(c, tr('All accounts ${_all.length}', '全部账号 ${_all.length}'), key: const Key('acct-all'), [
            for (final a in _all)
              Container(
                  key: Key('acct-row-${a['name']}'),
                  padding: const EdgeInsets.symmetric(vertical: 10),
                  decoration: BoxDecoration(border: Border(top: BorderSide(color: c.outline))),
                  child: Row(children: [
                    Icon(Icons.person_outline_rounded, color: c.textSecondary),
                    const SizedBox(width: 12),
                    Expanded(
                        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                      Text('${a['name']}', style: NwText.titleSmall.copyWith(color: c.text, fontWeight: FontWeight.w700)),
                      Text(roleName('${a['role']}'), style: NwText.bodySmall.copyWith(color: c.textSecondary)),
                    ])),
                    Text(_state(a), style: NwText.bodyMedium.copyWith(color: a['disabled'] == true ? c.textMuted : c.text)),
                  ])),
          ]),
        Padding(
            padding: const EdgeInsets.all(Nw.s16),
            child: Text(
                tr('To add accounts, create a temporary engineer account, change roles, reset passwords or disable accounts, use Users on the web console.',
                    '加账号、开临时工程师账号、改权限、重设密码、停用账号请在网页值班台「用户」中操作。'),
                style: NwText.bodySmall.copyWith(color: c.textSecondary))),
      ]),
    );
  }
}

// ------------------------------------------------------------ 日程（经理、管理员）

const List<String> _allDays = <String>['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'];

String dayName(String d) => switch (d) {
      'mon' => tr('Mon', '一'),
      'tue' => tr('Tue', '二'),
      'wed' => tr('Wed', '三'),
      'thu' => tr('Thu', '四'),
      'fri' => tr('Fri', '五'),
      'sat' => tr('Sat', '六'),
      'sun' => tr('Sun', '日'),
      _ => d,
    };

String daysText(List days) {
  final ds = [for (final d in days) '$d'];
  if (ds.length == 7) return tr('Every day', '每天');
  return tr(ds.map(dayName).join(' '), '周${ds.map(dayName).join('、')}');
}

/// 日程页：今天 / 每周。[embedded] 在底部栏里（经理的第 5 栏）不带返回。
/// 第 9 轮 W9-01：日程给人看的名字——起了日程名写日程名，没有写路线的显示名，再没有写编号。
String schedName(Map<String, dynamic> e, Map<String, String> titles) {
  final t = '${e['title'] ?? ''}';
  if (t.isNotEmpty) return t;
  return titles['${e['mission']}'] ?? '${e['mission']}';
}

/// 第 9 轮 A9-01：哪些路线排了也跑不了（画在别的地图版本上，没有一台机器人在用那一版）→ 为什么。
/// 机器人都没报在用哪张图时一条也不灰（不知道就别拦）。
Map<String, String> routeBlocked(List<Map> routes, List<Map> robots) {
  // 第 10 轮 A9-01：/api/robots 里在用哪张图在 running.map_id / map_version（没有 map 字段）
  final using = <String>{
    for (final r in robots)
      if (r['running'] is Map && (r['running'] as Map)['map_id'] != null)
        '${(r['running'] as Map)['map_id']}@${(r['running'] as Map)['map_version']}',
  };
  if (using.isEmpty) return const {};
  return {
    for (final r in routes)
      if ('${r['map_version'] ?? ''}'.isNotEmpty && !using.contains('${r['map_id']}@${r['map_version']}'))
        '${r['id']}': tr('drawn on map version ${r['map_version']}; no robot is using it', '画在第 ${r['map_version']} 版地图上，没有机器人在用'),
  };
}

class SchedulePage extends StatefulWidget {
  final SiteApi api;
  final bool embedded;
  const SchedulePage({super.key, required this.api, this.embedded = false});

  static const Key todayTabKey = Key('sched-today');
  static const Key settingsKey = Key('sched-settings');
  static const Key weekTabKey = Key('sched-week');
  static const Key addKey = Key('sched-add');
  static Key rowKey(String id) => Key('sched-row-$id');

  @override
  State<SchedulePage> createState() => _SchedulePageState();
}

class _SchedulePageState extends State<SchedulePage> {
  bool _week = false;
  List<Map<String, dynamic>> _today = const [];
  int? _offsetMin;
  Map<String, dynamic>? _sched;
  List<String> _routes = const [];
  List<String> _robots = const [];
  /// 第 9 轮 W9-01 / A9-01：路线编号 → 显示名；跑不了的路线 → 为什么；只许手动派的机器人。
  Map<String, String> _titles = const {};
  Map<String, String> _blocked = const {};
  Set<String> _manual = const {};
  String? _msg;

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  Future<void> _load() async {
    try {
      final got = await Future.wait<Object>([
        widget.api.patrolsToday(),
        widget.api.routeSchedules(),
        widget.api.schedule(),
        widget.api.robots(),
        widget.api.routes().catchError((_) => <String, dynamic>{}),
      ]);
      if (!mounted) return;
      final robots = [for (final r in got[3] as List) if (r is Map && r['revoked'] != true) r];
      final lib = [for (final r in ((got[4] as Map)['routes'] as List? ?? const [])) if (r is Map) r];
      setState(() {
        _today = [for (final x in ((got[0] as Map)['items'] as List? ?? const [])) if (x is Map) x.cast<String, dynamic>()];
        _offsetMin = ((got[0] as Map)['utc_offset_min'] as num?)?.toInt();
        _sched = (got[1] as Map).cast<String, dynamic>();
        _routes = [for (final m in ((got[2] as Map)['missions'] as List? ?? const [])) '$m'];
        _robots = [for (final r in robots) '${r['robot_id']}'];
        // 第 10 轮 A9-01：站点给的是 {by, at_ms, note} 对象（没设是 null），不是 true
        _manual = {for (final r in robots) if (r['manual_only'] != null && r['manual_only'] != false) '${r['robot_id']}'};
        _titles = {for (final r in lib) if ('${r['title'] ?? ''}'.isNotEmpty) '${r['id']}': '${r['title']}'};
        _blocked = routeBlocked(lib, robots);
      });
    } on SiteError catch (e) {
      if (mounted) setState(() => _msg = refusalText(e));
    } on FormatException catch (e) {
      if (mounted) setState(() => _msg = e.message);
    }
  }

  /// 就地编辑（App V2 不弹窗）：null = 没在编；{} = 新加的；别的 = 在编的那一条。
  Map<String, dynamic>? _editing;

  void _edit([Map<String, dynamic>? old]) => setState(() => _editing = old ?? const <String, dynamic>{});

  Future<void> _save(Map<String, dynamic>? old, Map<String, dynamic> got) async {
    final id = old != null ? '${old['id']}' : 'app-${DateTime.now().millisecondsSinceEpoch}';
    // 外审 W53-1 #9：编辑器没有的字段（每隔几分钟、到几点、优先级、回哪个待命点……）原样带回去，
    // 站点是整条替换的；选了「任一台」就把原来的 robot 去掉
    const meta = {'id', 'revision', 'active_from_ms', 'updated_ms', 'updated_by', 'source'};
    final body = <String, dynamic>{
      if (old != null)
        for (final e in old.entries)
          if (!meta.contains(e.key)) e.key: e.value,
      'window_min': old?['window_min'] ?? 30,
      'on_missed': old?['on_missed'] ?? 'skip',
      ...got,
      'base_revision': old?['revision'] ?? 0,
    };
    if (!got.containsKey('robot')) body.remove('robot');
    try {
      await widget.api.saveSchedule(id, body);
      if (mounted) {
        setState(() {
          _msg = tr('Saved', '已保存');
          _editing = null;
        });
      }
    } on SiteError catch (e) {
      if (mounted) setState(() => _msg = refusalText(e));
    }
    await _load();
  }

  Future<void> _delete(Map<String, dynamic> e) async {
    try {
      await widget.api.deleteSchedule('${e['id']}', (e['revision'] as num?)?.toInt() ?? 0);
      if (mounted) setState(() => _editing = null);
    } on SiteError catch (err) {
      if (mounted) setState(() => _msg = refusalText(err));
    }
    await _load();
  }

  @override
  Widget build(BuildContext context) {
    final c = Nw.of(context);
    final can = widget.api.session?.canSchedule ?? false;
    final rows = [for (final x in (_sched?['schedules'] as List? ?? const [])) if (x is Map) x.cast<String, dynamic>()]
      ..sort((a, b) => '${a['at']}'.compareTo('${b['at']}'));
    final body = RefreshIndicator(
      onRefresh: _load,
      child: NwListView(children: [
        SegmentedButton<bool>(
          showSelectedIcon: false,
          style: SegmentedButton.styleFrom(
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(2)),
              selectedBackgroundColor: c.primary,
              selectedForegroundColor: c.onPrimary),
          segments: [
            ButtonSegment(value: false, label: Text(tr('Today', '今天'), key: SchedulePage.todayTabKey)),
            ButtonSegment(value: true, label: Text(tr('Weekly', '每周'), key: SchedulePage.weekTabKey)),
          ],
          selected: {_week},
          onSelectionChanged: (v) => setState(() => _week = v.first),
        ),
        nwGap8,
        if (_msg != null) ...[NwNotice(text: _msg!), nwGap8],
        if (!_week)
          TodayPatrolList(api: widget.api, items: _today, onChanged: _load, offsetMin: _offsetMin)
        else ...[
          if (rows.isEmpty)
            Text(tr('No schedule yet.', '暂无日程。'), style: NwText.bodyMedium.copyWith(color: c.textSecondary)),
          // App V2 稿 S-schedule：一行一个（几点、名字、哪台 · 哪几天），点一行在下面就地编辑
          for (final e in rows)
            InkWell(
              key: SchedulePage.rowKey('${e['id']}'),
              onTap: can ? () => _edit(e) : null,
              child: Container(
                padding: const EdgeInsets.symmetric(vertical: 10),
                decoration: BoxDecoration(
                    color: identical(_editing, e) ? c.surfaceVariant : null,
                    border: Border(bottom: BorderSide(color: c.outline))),
                child: Row(children: [
                  SizedBox(
                      width: 60,
                      child: Text('${e['at']}', style: NwText.titleSmall.copyWith(color: c.text, fontWeight: FontWeight.w700))),
                  Expanded(
                      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    // 第 9 轮 W9-01：先写排程名，再写路线名（起了名的写显示名）
                    Text(
                        [
                          if ('${e['title'] ?? ''}'.isNotEmpty) '${e['title']}',
                          _titles['${e['mission']}'] ?? '${e['mission']}',
                        ].join(' · '),
                        style: NwText.titleSmall.copyWith(color: c.text, fontWeight: FontWeight.w700)),
                    Text(
                        [
                          if ('${e['robot'] ?? ''}'.isNotEmpty) '${e['robot']}' else tr('any free robot', '哪台空就哪台'),
                          daysText(e['days'] as List? ?? const []),
                          if ((e['every_min'] as num? ?? 0) > 0) scheduleWhen(e),
                        ].join(' · '),
                        style: NwText.bodySmall.copyWith(color: c.textSecondary)),
                  ])),
                  if (can) Icon(Icons.chevron_right_rounded, color: c.textSecondary),
                ]),
              ),
            ),
          if (can && _editing != null) ...[
            const SizedBox(height: Nw.s16),
            _ScheduleEditor(
                key: ValueKey('sched-edit-${_editing!['id'] ?? 'new'}'),
                api: widget.api,
                routes: _routes,
                robots: _robots,
                old: _editing!.isEmpty ? null : _editing,
                titles: _titles,
                blocked: _blocked,
                manual: _manual,
                onSave: (got) => _save(_editing!.isEmpty ? null : _editing, got),
                onCancel: () => setState(() => _editing = null),
                onDelete: _editing!.isEmpty ? null : () => _delete(_editing!)),
          ],
          if (can && _editing == null) ...[
            const SizedBox(height: Nw.s16),
            NwButton(
                buttonKey: SchedulePage.addKey,
                icon: Icons.add_rounded,
                variant: NwButtonVariant.outline,
                label: tr('Add schedule', '添加日程'),
                onPressed: _routes.isEmpty ? null : () => _edit()),
          ],
          const SizedBox(height: Nw.s16),
          Text(
              tr('Arming times (when the site arms and disarms by itself) are set on the web console.',
                  '布防时间（自动布防、撤防的时间）在网页值班台中设置。'),
              style: NwText.bodySmall.copyWith(color: c.textSecondary)),
        ],
      ]),
    );
    if (widget.embedded) {
      return Scaffold(
          body: Column(children: [
        NwHeader(overline: 'Nexus Warden', title: tr('Schedule', '日程'), trailing: [
          // 经理的第 5 栏是日程（没有「我的」栏）：设置从这里进
          IconButton(
              key: SchedulePage.settingsKey,
              tooltip: tr('Settings', '设置'),
              icon: const Icon(Icons.settings_rounded),
              onPressed: () => openSettings(context, widget.api)),
          IconButton(
              key: leaveSiteKey,
              tooltip: tr('Leave this site', '退出站点'),
              icon: const Icon(Icons.logout_rounded),
              onPressed: () => leaveSite(context)),
        ]),
        Expanded(child: body),
      ]));
    }
    return Scaffold(appBar: AppBar(title: Text(tr('Patrol schedules', '巡逻日程'))), body: body);
  }
}

class _ScheduleEditor extends StatefulWidget {
  final SiteApi api;
  final List<String> routes;
  final List<String> robots;
  final Map<String, dynamic>? old;
  final Map<String, String> titles;
  final Map<String, String> blocked;
  final Set<String> manual;
  const _ScheduleEditor(
      {required this.api,
      required this.routes,
      required this.robots,
      this.old,
      this.titles = const {},
      this.blocked = const {},
      this.manual = const {},
      required this.onSave,
      required this.onCancel,
      this.onDelete,
      super.key});

  final ValueChanged<Map<String, dynamic>> onSave;
  final VoidCallback onCancel;
  final VoidCallback? onDelete;

  @override
  State<_ScheduleEditor> createState() => _ScheduleEditorState();
}

class _ScheduleEditorState extends State<_ScheduleEditor> {
  // 第 9 轮 A9-01：新加的默认选第一条跑得了的路线
  late String _route = widget.old?['mission'] as String? ??
      widget.routes.firstWhere((r) => !widget.blocked.containsKey(r), orElse: () => widget.routes.firstOrNull ?? '');
  late final TextEditingController _name = TextEditingController(text: '${widget.old?['title'] ?? ''}');
  late String _robot = widget.old?['robot'] as String? ?? '';
  late final TextEditingController _at = TextEditingController(text: '${widget.old?['at'] ?? '08:00'}');
  bool _askDelete = false;

  /// 「1:5」「01:05」都认；认不出 = null。
  static String? _hhmm(String s) {
    final m = RegExp(r'^\s*(\d{1,2}):(\d{1,2})\s*$').firstMatch(s);
    if (m == null) return null;
    final h = int.parse(m[1]!), mi = int.parse(m[2]!);
    if (h > 23 || mi > 59) return null;
    return '${h.toString().padLeft(2, '0')}:${mi.toString().padLeft(2, '0')}';
  }

  @override
  void dispose() {
    _name.dispose();
    _at.dispose();
    super.dispose();
  }
  late final Set<String> _picked = {for (final d in (widget.old?['days'] as List? ?? _allDays)) '$d'};
  int? _est;

  @override
  void initState() {
    super.initState();
    unawaited(_estimate());
  }

  Future<void> _estimate() async {
    final rid = _robot.isNotEmpty ? _robot : (widget.robots.isEmpty ? null : widget.robots.first);
    if (rid == null) return;
    try {
      final p = await widget.api.patrolPlan(rid, _route);
      if (mounted) setState(() => _est = (p['estimate_s'] as num?)?.toInt());
    } on SiteError {
      // 估不了就不写
    }
  }

  @override
  Widget build(BuildContext context) {
    final c = Nw.of(context);
    final shape = RoundedRectangleBorder(borderRadius: BorderRadius.circular(2));
    final at = _hhmm(_at.text);
    Widget label(String t) => Padding(
        padding: const EdgeInsets.only(top: Nw.s16, bottom: Nw.s4),
        child: Text(t, style: NwText.labelMedium.copyWith(color: c.textSecondary)));
    // App V2 稿 S-schedule：就地编辑，不弹窗
    return Container(
      key: const Key('sched-editor'),
      padding: const EdgeInsets.all(Nw.s16),
      decoration: BoxDecoration(color: c.surface, border: Border.all(color: c.outline)),
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        Text(
            widget.old == null
                ? tr('Add schedule', '添加日程')
                : tr('Edit: ${widget.old!['at']} ${widget.titles['${widget.old!['mission']}'] ?? widget.old!['mission']}',
                    '编辑：${widget.old!['at']} ${widget.titles['${widget.old!['mission']}'] ?? widget.old!['mission']}'),
            style: NwText.titleMedium.copyWith(color: c.text, fontWeight: FontWeight.w700)),
        label(tr('Start', '开始时间')),
        TextField(
            key: const Key('sched-time'),
            controller: _at,
            keyboardType: TextInputType.datetime,
            decoration: InputDecoration(
                hintText: '19:00', errorText: at == null ? tr('Write it as 19:00', '写成 19:00 这样') : null),
            onChanged: (_) => setState(() {})),
        label(tr('Days', '哪几天')),
        Row(children: [
          for (final (i, d) in _allDays.indexed) ...[
            if (i > 0) const SizedBox(width: 4),
            Expanded(
                child: Material(
                    color: _picked.contains(d) ? c.primary : c.surface,
                    shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(2), side: BorderSide(color: _picked.contains(d) ? c.primary : c.outline)),
                    child: InkWell(
                        key: Key('sched-day-$d'),
                        onTap: () => setState(() => _picked.contains(d) ? _picked.remove(d) : _picked.add(d)),
                        child: SizedBox(
                            height: 40,
                            child: Center(
                                child: Text(dayName(d),
                                    style: NwText.labelMedium.copyWith(
                                        color: _picked.contains(d) ? c.onPrimary : c.text, fontWeight: FontWeight.w700)))))))
          ],
        ]),
        label(tr('Route · Robot', '路线 · 机器人')),
        DropdownButtonFormField<String>(
            key: const Key('sched-route'),
            initialValue: _route,
            isExpanded: true,
            decoration: InputDecoration(labelText: tr('Route', '路线')),
            // 第 9 轮 W9-01 / A9-01：写显示名；跑不了的灰掉，写为什么
            items: [
              // 日程指着的路线已经删了 / 不在这张图上：照样列出来，写明找不到（不然下拉框没有这一项就崩）
              if (!widget.routes.contains(_route))
                DropdownMenuItem(
                    value: _route,
                    child: Text(tr('$_route (route not found)', '$_route（找不到这条路线）'), overflow: TextOverflow.ellipsis)),
              for (final r in widget.routes)
                DropdownMenuItem(
                    value: r,
                    enabled: !widget.blocked.containsKey(r) || r == widget.old?['mission'],
                    child: Text(
                        widget.blocked.containsKey(r)
                            ? tr('${widget.titles[r] ?? r} (${widget.blocked[r]})', '${widget.titles[r] ?? r}（${widget.blocked[r]}）')
                            : widget.titles[r] ?? r,
                        overflow: TextOverflow.ellipsis)),
            ],
            onChanged: (v) {
              setState(() => _route = v ?? _route);
              unawaited(_estimate());
            }),
        const SizedBox(height: Nw.s8),
        DropdownButtonFormField<String>(
            key: const Key('sched-robot'),
            initialValue: _robot,
            isExpanded: true,
            decoration: InputDecoration(labelText: tr('Robot', '机器人')),
            items: [
              DropdownMenuItem(value: '', child: Text(tr('Any free robot', '哪台空就哪台'))),
              if (_robot.isNotEmpty && !widget.robots.contains(_robot))
                DropdownMenuItem(value: _robot, child: Text(tr('$_robot (not on this site)', '$_robot（站点上没有）'))),
              for (final r in widget.robots)
                DropdownMenuItem(
                    value: r,
                    child: Text(
                        widget.manual.contains(r)
                            ? tr('$r (manual dispatch only: schedules will not send it)', '$r（只许手动派，日程不会派它）')
                            : r,
                        overflow: TextOverflow.ellipsis)),
            ],
            onChanged: (v) {
              setState(() => _robot = v ?? '');
              unawaited(_estimate());
            }),
        const SizedBox(height: Nw.s8),
        TextField(
            key: const Key('sched-name'),
            controller: _name,
            maxLength: 40,
            decoration:
                InputDecoration(labelText: tr('Schedule name', '日程名'), hintText: tr('e.g. Night patrol', '例如：夜巡'))),
        if (_est != null)
          Text(tr('${minutesText(_est!)} per run (incl. return).', '每趟${minutesText(_est!)}（含返回）。'),
              style: NwText.bodySmall.copyWith(color: c.textSecondary)),
        const SizedBox(height: Nw.s16),
        Row(children: [
          Expanded(
              child: FilledButton(
                  key: const Key('sched-save'),
                  style: FilledButton.styleFrom(minimumSize: const Size(48, 48), shape: shape),
                  onPressed: _picked.isEmpty || at == null
                      ? null
                      : () => widget.onSave(<String, dynamic>{
                            'mission': _route,
                            'title': _name.text.trim(),
                            if (_robot.isNotEmpty) 'robot': _robot,
                            'at': at,
                            'days': [for (final d in _allDays) if (_picked.contains(d)) d],
                          }),
                  child: Text(tr('Save', '保存')))),
          const SizedBox(width: Nw.s8),
          Expanded(
              child: widget.onDelete != null
                  ? OutlinedButton(
                      key: Key('sched-delete-${widget.old!['id']}'),
                      style: OutlinedButton.styleFrom(
                          minimumSize: const Size(48, 48), shape: shape, foregroundColor: c.error, side: BorderSide(color: c.error)),
                      onPressed: () => setState(() => _askDelete = true),
                      child: Text(tr('Delete', '删除')))
                  : OutlinedButton(
                      key: const Key('sched-cancel'),
                      style: OutlinedButton.styleFrom(minimumSize: const Size(48, 48), shape: shape),
                      onPressed: widget.onCancel,
                      child: Text(tr('Cancel', '取消')))),
        ]),
        if (_askDelete) ...[
          const SizedBox(height: Nw.s8),
          Text(tr('Delete this schedule? Patrols at this time stop from tonight.', '删掉这条日程？从今晚起这个时间不再派巡逻。'),
              style: NwText.bodySmall.copyWith(color: c.text)),
          const SizedBox(height: Nw.s8),
          Row(children: [
            Expanded(
                child: OutlinedButton(
                    style: OutlinedButton.styleFrom(minimumSize: const Size(48, 48), shape: shape),
                    onPressed: () => setState(() => _askDelete = false),
                    child: Text(tr('Keep', '不删')))),
            const SizedBox(width: Nw.s8),
            Expanded(
                child: FilledButton(
                    key: const Key('sched-delete-go'),
                    style: FilledButton.styleFrom(minimumSize: const Size(48, 48), shape: shape, backgroundColor: c.error),
                    onPressed: widget.onDelete,
                    child: Text(tr('Delete', '删除')))),
          ]),
        ],
        if (widget.onDelete != null)
          TextButton(key: const Key('sched-cancel'), onPressed: widget.onCancel, child: Text(tr('Close', '收起'))),
      ]),
    );
  }
}

// ------------------------------------------------------------ 我的（保安、只看）

class MeTab extends StatelessWidget {
  final SiteApi api;
  final SiteEntry? entry;
  const MeTab({super.key, required this.api, this.entry});

  static const Key leaveKey = Key('me-leave');
  static const Key settingsKey = Key('me-settings');
  static const Key reportKey = Key('me-report');

  @override
  Widget build(BuildContext context) {
    final c = Nw.of(context);
    final s = api.session;
    return Scaffold(
      body: Column(children: [
        NwHeader(overline: 'Nexus Warden', title: tr('Me', '我的')),
        Expanded(
          child: NwListView(children: [
            NwCard(
              child: Row(children: [
                Icon(Icons.account_circle_rounded, size: 40, color: c.textSecondary),
                const SizedBox(width: Nw.s16),
                Expanded(
                    child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text(s?.displayName.isNotEmpty == true ? s!.displayName : (s?.name ?? ''),
                      style: NwText.titleMedium.copyWith(color: c.text, fontWeight: FontWeight.w700)),
                  Text('${s?.name ?? ''} · ${roleName(s?.role ?? '')}${entry == null ? '' : ' · ${entry!.name}'}',
                      style: NwText.bodySmall.copyWith(color: c.textSecondary)),
                ])),
              ]),
            ),
            const SizedBox(height: Nw.s16),
            _Entry(
                entryKey: MeTab.settingsKey,
                icon: Icons.settings_rounded,
                title: tr('Settings', '设置'),
                hint: tr('Language, background watch and push, app version and updates.',
                    '语言、后台值守与推送、App 版本与更新。'),
                onTap: () => openSettings(context, api)),
            _Entry(
                entryKey: const Key('me-tour'),
                icon: Icons.school_rounded,
                title: tr('How to use', '使用教程'),
                hint: tr('Replay the duty page tour.', '重新观看值守页导览。'),
                onTap: () => restartTour(context, api)),
            if (s?.canHandleAlerts ?? false)
              _Entry(
                  entryKey: const Key('me-practice'),
                  icon: Icons.sports_score_rounded,
                  title: tr('Practice an alarm', '报警演练'),
                  hint: tr("A simulated alarm visible only to you; nothing is sent to the site.", '模拟报警，仅你可见，不发送到站点。'),
                  onTap: () => _push(context, const PracticeAlarmPage())),
            // 易用性第 6 轮 A6-07：保安出了问题直接在这儿报（以前要走「我的 → 设置 → 上传日志」三层）
            _Entry(
                entryKey: MeTab.reportKey,
                icon: Icons.bug_report_outlined,
                title: tr('Report a problem', '报问题'),
                hint: tr('Say what happened; the logs go to the engineer.', '写一句出了什么事，日志发给工程师。'),
                onTap: () => openProblemReport(context, api)),
            _Entry(
                entryKey: const Key('me-help'),
                icon: Icons.help_outline_rounded,
                title: tr('Common questions', '常见问题'),
                hint: tr('Handling alarms, robots that won\'t go, and more.',
                    '报警处理、机器人无法派出等常见问题。'),
                onTap: () => _push(context, HelpPage(role: s?.role ?? ''))),
            const SizedBox(height: Nw.s16),
            NwButton(
                buttonKey: leaveKey,
                variant: NwButtonVariant.outline,
                icon: Icons.logout_rounded,
                label: tr('Leave this site', '退出站点'),
                onPressed: () => leaveSite(context)),
          ]),
        ),
      ]),
    );
  }
}
