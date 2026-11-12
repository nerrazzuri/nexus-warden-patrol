/// 派巡逻（W53）和「今天的巡逻」。
///
/// **派巡逻**是底部弹框：每条路线写预计多久（站点估，含走完回待命点那一段）；跟日程撞了先说清楚「日程优先，
/// 你这趟排到几点」。派出去会通知经理和管理员；这是临时巡逻，不进日程。被站点拒了弹「为什么 + 去处理」。
///
/// **今天的巡逻**：日程的每一轮和临时巡逻按时间排，一行一趟；没走完的点开看原因；排队中的临时巡逻派的人、
/// 经理、管理员能取消。值守页、日程页共用。
library;

import 'dart:async';

import 'package:flutter/material.dart';

import '../l10n.dart';
import '../net/site_client.dart';
import '../net/site_text.dart';
import 'nw/nw_button.dart';
import 'nw/nw_p4_admin.dart' show nwGap8;
import 'nw/nw_theme.dart';
import 'nw/nw_widgets.dart';
import 'refusal.dart';
import 'site_robot.dart' show SiteRobotPage;
import 'site_routes.dart' show SiteRouteEditorPage;

/// 时刻 `14:05`。给了 [offsetMin]（站点时区离 UTC 几分钟，站点回的 `utc_offset_min`）就按站点的钟，
/// 不按手机的（外审 W53-1 #12：人在异地、手机时区设错，巡逻时间就对不上）。
String hhmm(int ms, [int? offsetMin]) {
  final t = offsetMin == null
      ? DateTime.fromMillisecondsSinceEpoch(ms)
      : DateTime.fromMillisecondsSinceEpoch(ms, isUtc: true).add(Duration(minutes: offsetMin));
  return '${t.hour.toString().padLeft(2, '0')}:${t.minute.toString().padLeft(2, '0')}';
}

/// A7-03：临时巡逻跑完去哪（派巡逻弹层、临时路线页共用一句；跟站点 standby.py 一个口径：
/// 正常跑完回默认待命点，只许手动派的不自己回）。[manualOnly] 不知道（null）就把例外也写上。
String adhocEndText({String robot = '', bool? manualOnly}) => switch (manualOnly) {
      true => tr("$robot is set to manual dispatch only, so it won't go back to standby by itself afterwards; tap Return to standby.",
          '$robot 只许手动派，结束后不会自己回待命点，要回就点「回待命点」。'),
      false => tr('When it finishes, the robot goes back to its default standby point.', '跑完后机器人回默认待命点。'),
      null => tr(
          'When it finishes, the robot goes back to its default standby point (robots set to manual dispatch only stay where they are).',
          '跑完后机器人回默认待命点（只许手动派的机器人留在原地）。'),
    };

String minutesText(num seconds) {
  final m = (seconds / 60).round().clamp(1, 24 * 60);
  return tr('about $m min', '约 $m 分钟');
}

/// 派出去以后（或排上了）给人看的一句。
String dispatchResultText(Map<String, dynamic> r, String label) {
  final off = (r['utc_offset_min'] as num?)?.toInt();
  if (r['queued'] == true) {
    final at = r['start_after_ms'];
    final why = '${r['because'] ?? ''}';
    return tr(
        'Queued: "$label" starts after ${at is num ? hhmm(at.toInt(), off) : '?'} (schedule first${why.isEmpty ? '' : ': $why'}). You\'ll be notified when it starts.',
        '已排队：「$label」将在 ${at is num ? hhmm(at.toInt(), off) : '?'} 之后开始（日程优先${why.isEmpty ? '' : '：$why'}），开始时通知你。');
  }
  final est = r['estimate_s'];
  return tr('Dispatched: "$label"${est is num ? ', ${minutesText(est)}' : ''}. The manager and administrator have been notified.',
      '已派出：「$label」${est is num ? '，${minutesText(est)}' : ''}，已通知经理和管理员。');
}

/// 第 8 轮 A8-06：派出去（或排上了）一趟就加一。首页「今天的巡逻」听它马上重读（在机器人页、路线页派的也算）。
final ValueNotifier<int> patrolSent = ValueNotifier<int>(0);

/// 弹派巡逻框。派出去（或排上了）回给人看的那一句；没派回 null。
Future<String?> showPatrolSheet(BuildContext context, SiteApi api, String robotId) async {
  final msg = await showModalBottomSheet<String>(
      context: context,
      isScrollControlled: true,
      showDragHandle: true,
      builder: (_) => _PatrolSheet(api: api, robotId: robotId));
  if (msg != null) patrolSent.value++;
  return msg;
}

class _PatrolSheet extends StatefulWidget {
  final SiteApi api;
  final String robotId;
  const _PatrolSheet({required this.api, required this.robotId});

  static Key routeKey(String id) => Key('patrol-route-$id');
  static const Key sendKey = Key('patrol-send');

  @override
  State<_PatrolSheet> createState() => _PatrolSheetState();
}

/// 测试找派巡逻框里的东西用。
Key patrolRouteKey(String id) => _PatrolSheet.routeKey(id);
const Key patrolSendKey = _PatrolSheet.sendKey;
const Key patrolQueuedKey = Key('patrol-queued');
const Key patrolCustomKey = Key('patrol-custom');

/// W76 循环次数：1、2、3、5、10 圈或一直巡逻（0）。
const List<int> patrolLoopChoices = <int>[1, 2, 3, 5, 10, 0];
Key patrolLoopsKey(int n) => Key('patrol-loops-$n');
const Key patrolForeverKey = Key('patrol-forever');

String loopsText(int n) => n == 0 ? tr('Keep patrolling', '一直巡逻') : tr('$n×', '$n 圈');

/// 正在跑第几圈（站点机器人视图的 `lap`）：共几圈写「第 2 / 3 圈」，一直巡逻写「一直巡逻 · 第 5 圈」；一圈的是空串。
String lapText(Object? lap) {
  if (lap is! Map || lap['n'] is! num || lap['of'] is! num) return '';
  final n = (lap['n'] as num).toInt(), of = (lap['of'] as num).toInt();
  return of == 0 ? tr('Keep patrolling · loop $n', '一直巡逻 · 第 $n 圈') : tr('Loop $n of $of', '第 $n / $of 圈');
}

class _PatrolSheetState extends State<_PatrolSheet> {
  List<String>? _routes;
  final Map<String, Map<String, dynamic>> _plans = <String, Map<String, dynamic>>{};
  String? _pick;
  String? _error;
  bool _busy = false;
  int _loops = 1;

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  /// 被叫停了（手机 App 测试 M13）：派之前就说，不等点了才被拒。
  Map? _held;

  /// A7-03：这台只许手动派（结束后不自己回）；没读到是 null。
  bool? _manualOnly;

  /// 易用性第 6 轮 A6-03：画在别的地图版本上的路线 → 画在哪一版（派不了，灰掉写明）。
  final Map<String, String> _otherMap = <String, String>{};
  String _loaded = '';

  Future<void> _load() async {
    unawaited(widget.api.robot(widget.robotId).then((v) async {
      if (mounted) {
        setState(() {
          if (v['held'] is Map) _held = v['held'] as Map;
          _manualOnly = v['manual_only'] is Map;
        });
      }
      final caps = v['capabilities'];
      final tasks = caps is Map ? caps['tasks'] : null;
      final p = tasks is Map ? tasks['patrol'] : null;
      if (p is! Map || p['map_id'] is! String || p['map_version'] is! String) return;
      final lib = await widget.api.routes();
      final other = <String, String>{};
      for (final r in (lib['routes'] as List? ?? const []).whereType<Map>()) {
        final v2 = '${r['map_version'] ?? ''}';
        if (v2.isEmpty) continue;                     // 没绑版本的路线照旧能派（站点自己判）
        if (r['map_id'] != p['map_id'] || v2 != p['map_version']) other['${r['id']}'] = v2;
      }
      if (!mounted) return;
      setState(() {
        _loaded = '${p['map_version']}';
        _otherMap..clear()..addAll(other);
        if (_otherMap.containsKey(_pick)) _pick = null;
      });
    }, onError: (Object _) {}));
    try {
      final s = await widget.api.schedule();
      final rs = (s['missions'] as List? ?? const []).map((e) => '$e').toList();
      if (!mounted) return;
      setState(() {
        _routes = rs;
        _pick = rs.length == 1 && !_otherMap.containsKey(rs.first) ? rs.first : null;
      });
      _loadPlans(rs);
    } on SiteError catch (e) {
      if (mounted) setState(() => _error = tr("Can't load routes: ${refusalText(e)}", '无法加载路线：${refusalText(e)}'));
    }
  }

  void _loadPlans(List<String> rs) {
    final n = _loops;
    for (final r in rs) {
      unawaited(widget.api.patrolPlan(widget.robotId, r, loops: n).then((p) {
        if (mounted && _loops == n) setState(() => _plans[r] = p);
      }, onError: (Object _) {}));
    }
  }

  void _setLoops(int n) {
    if (n == _loops) return;
    setState(() {
      _loops = n;
      _plans.clear();
    });
    final rs = _routes;
    if (rs != null) _loadPlans(rs);
  }

  Future<void> _send() async {
    final r = _pick;
    if (r == null) return;
    setState(() => _busy = true);
    try {
      final got = await widget.api.patrol(widget.robotId, r, loops: _loops);
      final ack = got['ack'];
      if (got['queued'] != true && ack is Map && ack['result'] != 'accepted' && ack['result'] != 'duplicate') {
        // 机器人明确没收（忙、电量低……）：不说「派出去了」（外审 W53-1 #4）
        if (mounted) {
          setState(() {
            _busy = false;
            _error = tr('The robot did not accept: ${ack['result']} ${ack['reason'] ?? ''}',
                '机器人未接受：${ack['result']} ${ack['reason'] ?? ''}');
          });
        }
        return;
      }
      if (mounted) Navigator.pop(context, dispatchResultText(got, r));
    } on SiteError catch (e) {
      if (!mounted) return;
      setState(() => _busy = false);
      final nav = Navigator.of(context);
      final host = nav.context;
      nav.pop();
      if (host.mounted) await showRefusal(host, widget.api, e, robotId: widget.robotId);
    }
  }

  /// 在图上点几个点（W53，用户 10-31）：路线编辑页的临时模式，派出去不存。
  Future<void> _custom() async {
    Map<String, dynamic> v;
    try {
      v = await widget.api.robot(widget.robotId);
    } on SiteError catch (e) {
      if (mounted) setState(() => _error = refusalText(e));
      return;
    }
    final caps = v['capabilities'];
    final tasks = caps is Map ? caps['tasks'] : null;
    final p = tasks is Map ? tasks['patrol'] : null;
    if (p is! Map || p['map_id'] is! String || p['map_version'] is! String) {
      if (mounted) {
        setState(() => _error = tr("${widget.robotId} hasn't reported its loaded map",
            '${widget.robotId} 未上报已加载的地图'));
      }
      return;
    }
    if (!mounted) return;
    final msg = await Navigator.push<String>(
        context,
        MaterialPageRoute<String>(
            builder: (_) => SiteRouteEditorPage(
                api: widget.api,
                mapId: '${p['map_id']}',
                version: '${p['map_version']}',
                newName: '',
                tempFor: widget.robotId)));
    if (msg != null && mounted) Navigator.pop(context, msg);
  }

  @override
  Widget build(BuildContext context) {
    final c = Nw.of(context);
    final rs = _routes;
    final plan = _pick == null ? null : _plans[_pick];
    final queued = plan != null && plan['queued'] == true;
    final startAt = plan != null && plan['start_ms'] is num
        ? hhmm((plan['start_ms'] as num).toInt(), (plan['utc_offset_min'] as num?)?.toInt())
        : '?';
    return SafeArea(
      child: Padding(
        padding: EdgeInsets.fromLTRB(Nw.s16, 0, Nw.s16, Nw.s16 + MediaQuery.viewInsetsOf(context).bottom),
        child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          Text(tr('Dispatch ${widget.robotId} on patrol', '派 ${widget.robotId} 巡逻'),
              style: NwText.titleMedium.copyWith(color: c.text, fontWeight: FontWeight.w700)),
          nwGap8,
          if (_held != null) ...[
            NwNotice(
                key: const Key('patrol-held'),
                tone: NwTone.warning,
                text: tr(
                    '${widget.robotId} was stopped by ${_held!['by']}. It won\'t go until a guard or administrator taps Resume.',
                    '${widget.robotId} 已被 ${_held!['by']} 叫停。保安或管理员点「恢复」之前，它不会出发。')),
            nwGap8,
          ],
          if (_error != null)
            NwNotice(text: _error!, tone: NwTone.error)
          else if (rs == null)
            const Padding(padding: EdgeInsets.all(Nw.s16), child: Center(child: CircularProgressIndicator()))
          else if (rs.isEmpty)
            NwNotice(
                text: (widget.api.session?.canManageRoutes ?? false)
                    ? tr('No patrol routes yet. Add them under Admin → Patrol routes.', '暂无巡逻路线，请在「管理 → 巡逻路线」中添加。')
                    : tr('No patrol routes yet. Ask an administrator to add them.', '暂无巡逻路线，请找管理员添加。'))
          else
            ConstrainedBox(
              constraints: BoxConstraints(maxHeight: MediaQuery.sizeOf(context).height * 0.45),
              child: ListView(shrinkWrap: true, children: [
                for (final r in rs)
                  Padding(
                    padding: const EdgeInsets.only(bottom: Nw.s8),
                    // 易用性第 7 轮：画在别的版本上的路线整行变淡、不写预计时间、写「派不了」和按角色的去处
                    child: Opacity(
                      opacity: _otherMap.containsKey(r) ? 0.55 : 1,
                      child: NwCard(
                        key: _PatrolSheet.routeKey(r),
                        tone: _pick == r ? NwTone.info : NwTone.neutral,
                        onTap: _otherMap.containsKey(r) ? null : () => setState(() => _pick = r),
                        child: Row(children: [
                          Icon(
                              _otherMap.containsKey(r)
                                  ? Icons.block_rounded
                                  : _pick == r
                                      ? Icons.radio_button_checked_rounded
                                      : Icons.radio_button_off_rounded,
                              color: _pick == r ? c.primary : c.textSecondary),
                          const SizedBox(width: Nw.s8),
                          Expanded(
                              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                            Text(r,
                                style: NwText.bodyLarge
                                    .copyWith(color: _otherMap.containsKey(r) ? c.textSecondary : c.text)),
                            if (_otherMap.containsKey(r)) ...[
                              Text(
                                  tr("Can't dispatch: drawn on map v${_otherMap[r]}; ${widget.robotId} is using v$_loaded",
                                      '派不了：画在 v${_otherMap[r]} 上，${widget.robotId} 用的是 v$_loaded'),
                                  style: NwText.bodySmall.copyWith(color: c.textSecondary)),
                              Text(refusalHint('map_mismatch', widget.api.session),
                                  style: NwText.bodySmall.copyWith(color: c.textSecondary)),
                            ],
                          ])),
                          if (!_otherMap.containsKey(r))
                            Text(
                                _plans[r]?['forever'] == true
                                    ? loopsText(0)
                                    : _plans[r]?['estimate_s'] is num
                                        ? minutesText(_plans[r]!['estimate_s'] as num)
                                        : '…',
                                style: NwText.bodySmall.copyWith(color: c.textSecondary)),
                        ]),
                      ),
                    ),
                  ),
              ]),
            ),
          // 外审 W76-1 #8：站点回的「先看会怎样」里有 `loops` 才认圈数（老站点不认，选了也白选）
          if (rs != null && rs.isNotEmpty && _plans.values.any((p) => p.containsKey('loops'))) ...[
            nwGap8,
            Text(tr('Loops', '循环次数'), style: NwText.bodySmall.copyWith(color: c.textSecondary)),
            const SizedBox(height: Nw.s4),
            Wrap(spacing: Nw.s8, runSpacing: Nw.s4, children: [
              for (final n in patrolLoopChoices)
                ChoiceChip(
                    key: patrolLoopsKey(n),
                    label: Text(loopsText(n)),
                    selected: _loops == n,
                    onSelected: _busy ? null : (_) => _setLoops(n)),
            ]),
          ],
          if (plan != null && plan['forever'] == true) ...[
            nwGap8,
            NwNotice(
                key: patrolForeverKey,
                tone: NwTone.info,
                text: tr(
                    'Keep patrolling: starts now and loops until the battery ${plan['return_pct'] is num ? 'drops to ${plan['return_pct']}% (the site\'s patrol battery line)' : 'reaches the site\'s patrol battery line'}, then goes back to recharge or swap and the task ends.'
                        '${'${plan['interrupted_by'] ?? ''}'.isEmpty ? '' : ' ${plan['interrupted_by']} will stop it and run instead.'}',
                    '一直巡逻：现在就走，一圈接一圈，电量${plan['return_pct'] is num ? '降到 ${plan['return_pct']}%（站点设的巡逻电量线）' : '到站点设的巡逻电量线'}就回去充电或换电池，这一趟结束。'
                        '${'${plan['interrupted_by'] ?? ''}'.isEmpty ? '' : '${plan['interrupted_by']}到点会停下它、改跑日程。'}')),
          ],
          nwGap8,
          NwButton(
              buttonKey: patrolCustomKey,
              variant: NwButtonVariant.outline,
              icon: Icons.touch_app_rounded,
              label: tr('Pick points on the map (one-off route)', '在地图上选点（临时路线）'),
              onPressed: _busy ? null : _custom),
          if (queued) ...[
            nwGap8,
            NwNotice(
                key: patrolQueuedKey,
                tone: NwTone.warning,
                text: tr(
                    'Clashes with the schedule (${plan['because']}). The schedule takes priority: this patrol starts after $startAt.',
                    '与日程冲突（${plan['because']}），日程优先：本次巡逻将在 $startAt 之后开始。')),
          ],
          nwGap8,
          Text(
              // 手机 App 测试 M38：对经理不说「会通知经理」
              '${widget.api.session?.role == 'owner' ? tr('One-off patrols are not saved to the schedule. The administrator is notified. ', '临时巡逻不保存到日程，派出后通知管理员。') : tr('One-off patrols are not saved to the schedule. The manager and administrator are notified. ', '临时巡逻不保存到日程，派出后通知经理和管理员。')}'
              '${adhocEndText(robot: widget.robotId, manualOnly: _manualOnly)}',
              style: NwText.bodySmall.copyWith(color: c.textSecondary)),
          nwGap8,
          Row(children: [
            Expanded(
                child: NwButton(
                    variant: NwButtonVariant.outline,
                    label: tr('Cancel', '取消'),
                    onPressed: _busy ? null : () => Navigator.pop(context))),
            const SizedBox(width: Nw.s8),
            Expanded(
                child: NwButton(
                    buttonKey: _PatrolSheet.sendKey,
                    label: queued ? tr('Queue it', '排队派出') : tr('Send', '派出'),
                    onPressed: _pick == null || _busy || _held != null ? null : _send)),
          ]),
        ]),
      ),
    );
  }
}

// ------------------------------------------------------------ 今天的巡逻

/// 一行的状态说人话 + 颜色。
/// W71：跑完了、跳过了几个点（到了一部分算完成）→「完成（跳过 N 点）」。
(String, NwTone) patrolStateText(String state, [int skipped = 0]) => state == 'done' && skipped > 0
    ? (tr('Done ($skipped skipped)', '完成（跳过 $skipped 点）'), NwTone.warning)
    : switch (state) {
      'done' => (tr('Done', '完成'), NwTone.success),
      'failed' => (tr('Not finished', '未完成'), NwTone.error),
      'aborted' => (tr('Stopped', '已叫停'), NwTone.neutral),
      'running' => (tr('In progress', '进行中'), NwTone.info),
      'waiting' => (tr('Waiting for a robot', '等待机器人'), NwTone.warning),
      'missed' => (tr('Missed', '未执行'), NwTone.error),
      'next' => (tr('Next', '下一次'), NwTone.neutral),
      'later' => (tr('Later', '稍后'), NwTone.neutral),
      'queued' => (tr('Queued', '排队中'), NwTone.warning),
      'cancelled' => (tr('Cancelled', '已取消'), NwTone.neutral),
      'expired' => (tr('Expired', '已作废'), NwTone.neutral),
      'blocked' => (tr("Won't run", '不会跑'), NwTone.warning),
      // 第 8 轮 W8-03：被日程（或更急的任务）接替不是故障
      'handed_over' => (tr('Handed over', '被接替'), NwTone.neutral),
      _ => (state, NwTone.neutral),
    };

/// 易用性第 6 轮 W6-02：站点给的原因码说人话（`manual_only` = 排给的那台只许手动派）；别的原样。
String patrolReasonText(String reason, String robot) => switch (reason) {
      'manual_only' => tr('$robot is set to manual dispatch only', '$robot 只许手动派'),
      'map_mismatch' => tr("$robot's map doesn't match the route", '$robot 用的地图跟路线对不上'),
      _ => reason,
    };

String _ver(String v) => RegExp(r'^\d+$').hasMatch(v) ? 'v$v' : v;

/// 易用性第 7 轮：站点给的 `map`（路线画在哪一版、机器人用的哪一版）说人话；没有就是空。
String patrolMapText(Object? map, String robot) {
  if (map is! Map) return '';
  final a = _ver('${map['route']}'), b = _ver('${map['robot']}');
  return tr('The route is drawn on map $a; $robot is using $b', '路线画在 $a 上，$robot 用的是 $b');
}

/// 易用性第 7 轮：「不会跑」去哪改（按角色；App 里改不了派遣方式，管理员去网页）。
String patrolFixText(Map<String, dynamic> it, SiteSession? s) {
  final robot = '${it['robot'] ?? ''}';
  final fixes = <String>[
    if (it['reason'] == 'manual_only')
      (s?.canManageRobots ?? false)
          ? tr('To let it run on schedule: web console → Admin → Robots → $robot → set to automatic dispatch.',
              '要让它按日程跑：在网页「管理 → 机器人」把 $robot 改回自动派。')
          : tr('Ask an administrator to set $robot back to automatic dispatch.', '找管理员把 $robot 改回自动派。'),
    if (it['map'] is Map) refusalHint('map_mismatch', s),
  ];
  return fixes.join('\n');
}

/// 第 8 轮 W8-03：被接替的那一趟 —— 跑了几圈、谁接的（站点给的 `handover`）；没有就是空。
String patrolHandoverText(Object? h) {
  if (h is! Map) return '';
  final who = switch (h['by']) {
    'schedule' => tr('schedule ${h['name']}', '日程 ${h['name']} '),
    'teleop' => tr('remote control', '遥控'),
    _ => tr('a more urgent task', '更急的任务'),
  };
  final laps = h['laps'] is num ? (h['laps'] as num).toInt() : 0;
  return laps > 0 ? tr('Ran $laps loop(s), then $who took over', '已跑 $laps 圈，由$who接替') : tr('$who took over', '由$who接替');
}

int _skippedOf(Map<String, dynamic> it) => it['skipped'] is int ? it['skipped'] as int : 0;

/// 这台机器人正在走的那一趟（今天的巡逻里 `running`、`task_id` 对得上的）。
Map<String, dynamic>? runningItem(List<Map<String, dynamic>> items, String robotId, String? taskId) {
  for (final it in items) {
    if (it['state'] == 'running' && it['robot'] == robotId && (taskId == null || it['task_id'] == taskId)) {
      return it;
    }
  }
  return null;
}

Key todayRowKey(int i) => Key('today-row-$i');

class TodayPatrolList extends StatelessWidget {
  final SiteApi api;
  final List<Map<String, dynamic>> items;
  /// 取消了一条以后调（页面重读）。
  final VoidCallback? onChanged;

  /// 站点时区离 UTC 几分钟（今天的巡逻回的 `utc_offset_min`）；老站点没有就按手机的钟。
  final int? offsetMin;
  const TodayPatrolList({super.key, required this.api, required this.items, this.onChanged, this.offsetMin});

  static const Key emptyKey = Key('today-empty');

  Future<void> _open(BuildContext context, Map<String, dynamic> it) async {
    final s = api.session;
    final reason = '${it['reason'] ?? ''}';
    final adhoc = it['kind'] == 'adhoc';
    final canCancel = adhoc && it['state'] == 'queued' && (s?.canPatrol ?? false) &&
        (it['by'] == s?.name || (s?.canSchedule ?? false));
    final (st, _) = patrolStateText('${it['state']}', _skippedOf(it));
    final lines = <String>[
      '${hhmm((it['at_ms'] as num).toInt(), offsetMin)} · ${siteKnown('${it['label']}')}${'${it['robot'] ?? ''}'.isEmpty ? '' : ' · ${it['robot']}'}',
      st,
      if (adhoc) tr('One-off patrol sent by ${it['by']}', '${it['by']} 派的临时巡逻'),
      if (it['state'] == 'running' && it['lap'] is Map) lapText(it['lap']),
      if (it['handover'] is Map) patrolHandoverText(it['handover']),
      // 第 8 轮：还没跑完的才是「预计」；跑完了的写几点结束
      if (it['end_ms'] is num)
        const {'running', 'queued', 'waiting', 'next', 'later'}.contains(it['state'])
            ? tr('Ends around ${hhmm((it['end_ms'] as num).toInt(), offsetMin)}', '预计 ${hhmm((it['end_ms'] as num).toInt(), offsetMin)} 结束')
            : tr('Ended ${hhmm((it['end_ms'] as num).toInt(), offsetMin)}', '${hhmm((it['end_ms'] as num).toInt(), offsetMin)} 结束'),
      if (reason.isNotEmpty && !(reason == 'map_mismatch' && it['map'] is Map))
        patrolReasonText(reason, '${it['robot'] ?? ''}'),
      if (it['map'] is Map) patrolMapText(it['map'], '${it['robot'] ?? ''}'),
      if (it['state'] == 'blocked') patrolFixText(it, s),
    ];
    final robotId = '${it['robot'] ?? ''}';
    final cancel = await showDialog<bool>(
        context: context,
        builder: (c) => AlertDialog(
              content: Text(lines.join('\n')),
              actions: [
                if (it['state'] == 'blocked' && robotId.isNotEmpty)
                  TextButton(
                      key: const Key('today-robot'),
                      onPressed: () {
                        Navigator.pop(c, false);
                        Navigator.push(context,
                            MaterialPageRoute<void>(builder: (_) => SiteRobotPage(api: api, robotId: robotId)));
                      },
                      child: Text(tr('Open robot', '去机器人页'))),
                if (canCancel)
                  TextButton(
                      key: const Key('today-cancel'),
                      onPressed: () => Navigator.pop(c, true),
                      child: Text(tr('Cancel this patrol', '取消本次巡逻'))),
                TextButton(onPressed: () => Navigator.pop(c, false), child: Text(tr('Close', '关闭'))),
              ],
            ));
    if (cancel != true) return;
    try {
      await api.cancelAdhoc('${it['adhoc_id']}');
    } on SiteError catch (e) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(refusalText(e))));
      }
    }
    onChanged?.call();
  }

  @override
  Widget build(BuildContext context) {
    final c = Nw.of(context);
    if (items.isEmpty) {
      return Padding(
          key: emptyKey,
          padding: const EdgeInsets.symmetric(vertical: Nw.s8),
          child: Text(tr('No patrols today.', '今天没有巡逻。'),
              style: NwText.bodyMedium.copyWith(color: c.textSecondary)));
    }
    return NwCard(
      padding: EdgeInsets.zero,
      child: Column(mainAxisSize: MainAxisSize.min, children: [
        for (var i = 0; i < items.length; i++)
          InkWell(
            key: todayRowKey(i),
            onTap: () => _open(context, items[i]),
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: Nw.s8),
              child: Row(children: [
                // 手机 App 测试 M16：时间列跟着字宽，不折行（以前写死 48，字放大到 1.3 倍折成「12:5」「3」）
                ConstrainedBox(
                    constraints: const BoxConstraints(minWidth: 48),
                    child: Padding(
                      padding: const EdgeInsets.only(right: Nw.s8),
                      child: Text(hhmm((items[i]['at_ms'] as num).toInt(), offsetMin),
                          maxLines: 1,
                          softWrap: false,
                          style: NwText.labelLarge.copyWith(color: c.text, fontFeatures: const [FontFeature.tabularFigures()])),
                    )),
                Expanded(
                    child: Text(
                        [
                          if (items[i]['kind'] == 'adhoc') tr('One-off', '临时'),
                          siteKnown('${items[i]['label']}'),
                          if ('${items[i]['robot'] ?? ''}'.isNotEmpty) '${items[i]['robot']}',
                          if (items[i]['kind'] == 'adhoc' && '${items[i]['by'] ?? ''}'.isNotEmpty) '${items[i]['by']}',
                        ].join(' · '),
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                        style: NwText.bodyMedium.copyWith(color: c.text))),
                const SizedBox(width: Nw.s8),
                Builder(builder: (_) {
                  final (label, tone) = patrolStateText('${items[i]['state']}', _skippedOf(items[i]));
                  return NwStatusPill(label: label, tone: tone);
                }),
              ]),
            ),
          ),
      ]),
    );
  }
}
