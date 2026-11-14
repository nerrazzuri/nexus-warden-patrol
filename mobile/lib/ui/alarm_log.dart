/// 报警记录（W53：「记录」栏的一段）：最近的 P1、P2，谁确认的、解决了没有。点开是报警处理页。
library;

import 'dart:async';

import 'package:flutter/material.dart';

import '../l10n.dart';
import '../net/site_text.dart';
import '../model/alert.dart';
import '../net/site_client.dart';
import 'nw/nw_p2_duty.dart';
import 'nw/nw_p4_admin.dart' show NwListView;
import 'nw/nw_theme.dart';
import 'nw/nw_widgets.dart';
import 'patrol_dispatch.dart' show hhmm;
import 'site_alert_scene.dart';

class AlarmLogPage extends StatefulWidget {
  final SiteApi api;
  const AlarmLogPage({super.key, required this.api});

  static Key rowKey(String key) => Key('alarm-log-$key');
  static const Key todoKey = Key('alarm-log-todo');
  static Key todoRowKey(String key) => Key('alarm-log-todo-$key');

  /// 第 12 轮 W12-02：跟网页报警记录同一套规则 —— 给保安的（入侵、起火、求助、离线；老站点没有
  /// audience 也算）才是「报警」；授权的人在场照旧列。
  // 易用性 r7:P1 不管发给谁都算报警 —— 手机按出声档响铃不看受众(换电 30 分钟没进展是发给经理的,保安手机也响),
  // 响了就得在这里找得到;首页「紧急报警」也是数所有没处理的 P1
  static bool isAlarm(Alert a) =>
      (a.level != 'P3' && alertForGuard(a)) || a.level == 'P1' || a.kind == 'authorized_person';

  /// 管理员要处理的事（存储不足、排程派不了……）：网页总览叫「待处理事项」，这里也这么叫，不当报警。
  static bool isTodo(Alert a) => !isAlarm(a) && a.level != 'P3' && a.resolvedMs == null;

  /// 同一种、同一句话的合成一组（每晚一条的「排程派不了」只占一行）；组内新的在前，组按最新一次排。
  static List<List<Alert>> groupTodo(Iterable<Alert> list) {
    final m = <String, List<Alert>>{};
    for (final a in list) {
      (m['${a.kind}\u0000${a.title}'] ??= <Alert>[]).add(a);
    }
    final groups = [for (final g in m.values) g..sort((a, b) => b.firstMs.compareTo(a.firstMs))];
    return groups..sort((a, b) => b.first.firstMs.compareTo(a.first.firstMs));
  }

  /// 测试模式条幅多久重新问一次站点（外审 r1 #10：别人开了、结束了，这边也跟着变）。
  static const Duration testPoll = Duration(seconds: 15);

  @override
  State<AlarmLogPage> createState() => _AlarmLogPageState();
}

class _AlarmLogPageState extends State<AlarmLogPage> {
  List<Alert>? _rows;
  /// 待处理事项，同类合成一组（第 13 轮 W13-02：跟网页一样，同一句话的合成一条；组里最新的在前）。
  List<List<Alert>> _todo = const [];
  String? _error;

  /// POC 告警测试模式开着：到几点、谁开的。没开 / 老站点 = null。
  Map<String, dynamic>? _test;

  Timer? _poll;

  @override
  void initState() {
    super.initState();
    unawaited(_load());
    _poll = Timer.periodic(AlarmLogPage.testPoll, (_) => unawaited(_loadTest()));
  }

  @override
  void dispose() {
    _poll?.cancel();
    super.dispose();
  }

  Future<void> _loadTest() async {
    Map<String, dynamic>? test;
    try {
      final m = await widget.api.alertTest();
      test = m['active'] == true ? m : null;
    } on SiteError {
      test = null; // 老站点没有这个接口
    } on FormatException {
      test = null;
    }
    if (mounted) setState(() => _test = test);
  }

  /// 到点就当结束了（不等下一次问）。
  bool get _testOn {
    final u = _test?['until_ms'];
    return _test != null && (u is! num || DateTime.now().millisecondsSinceEpoch < u);
  }

  Future<void> _load() async {
    try {
      final all = await widget.api.alerts(all: true);
      await _loadTest();
      if (mounted) {
        setState(() {
          _rows = all.where(AlarmLogPage.isAlarm).toList();
          // 第 13 轮 W13-02：网页只给管理员、工程师看待处理事项（保安批不了账号、管不了存储）
          final role = widget.api.session?.role ?? '';
          _todo = role == 'admin' || role == 'engineer' ? AlarmLogPage.groupTodo(all.where(AlarmLogPage.isTodo)) : const [];
        });
      }
    } on SiteError catch (e) {
      if (mounted) setState(() => _error = refusalText(e));
    } on FormatException catch (e) {
      if (mounted) setState(() => _error = e.message);
    }
  }

  String _day(int ms) {
    final t = DateTime.fromMillisecondsSinceEpoch(ms);
    // 手机 App 测试 M33：跟别处一样写 11-08（以前 11/8）
    return '${t.month.toString().padLeft(2, '0')}-${t.day.toString().padLeft(2, '0')} ${hhmm(ms)}';
  }

  @override
  Widget build(BuildContext context) {
    final c = Nw.of(context);
    final rows = _rows;
    return RefreshIndicator(
      onRefresh: _load,
      child: NwListView(children: [
        if (_testOn)
          NwNotice(
              key: const Key('alarm-test-mode'),
              tone: NwTone.warning,
              text: tr(
                  'Alert test mode until ${_test!['until_ms'] is num ? hhmm((_test!['until_ms'] as num).toInt()) : '?'} (started by ${_test!['by']}): alerts raised now carry a test prefix in the title.',
                  '报警测试模式中，到 ${_test!['until_ms'] is num ? hhmm((_test!['until_ms'] as num).toInt()) : '?'} 结束（${_test!['by']} 开的）：这期间的报警标题带「测试：」。')),
        if (_error != null) NwNotice(text: _error!, tone: NwTone.error),
        if (rows == null && _error == null) const Center(child: CircularProgressIndicator()),
        if (_todo.isNotEmpty)
          Padding(
            key: AlarmLogPage.todoKey,
            padding: const EdgeInsets.only(bottom: Nw.s16),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(tr('Needs your attention (${_todo.length}) — not alarms', '待处理事项（${_todo.length} 条，不是报警）'),
                  style: NwText.titleSmall.copyWith(color: c.text)),
              const SizedBox(height: Nw.s8),
              for (final g in _todo)
                Padding(
                  padding: const EdgeInsets.only(bottom: Nw.s8),
                  child: NwCard(
                    key: AlarmLogPage.todoRowKey(g.first.key),
                    onTap: () => Navigator.push(context,
                        MaterialPageRoute<void>(builder: (_) => SiteAlertScenePage(api: widget.api, alert: g.first))),
                    child: Row(children: [
                      Expanded(
                          child: Text(
                              '${alertLine(g.first.robot, g.first.kind, g.first.title)}'
                              '${g.length > 1 ? tr(' · ${g.length} times', ' · 共 ${g.length} 次') : ''}',
                              maxLines: 2,
                              overflow: TextOverflow.ellipsis,
                              style: NwText.bodyMedium.copyWith(color: c.text))),
                      Text(_day(g.first.firstMs), style: NwText.labelSmall.copyWith(color: c.textSecondary)),
                    ]),
                  ),
                ),
            ]),
          ),
        // 第 13 轮 W13-02：报警部分要有标题；没有未处理的也说一句（以前待处理事项后面直接接「已解决」）
        if (rows != null) ...[
          Text(tr('Alarms', '报警'), style: NwText.titleSmall.copyWith(color: c.text)),
          const SizedBox(height: Nw.s8),
        ],
        if (rows != null && rows.isEmpty)
          Text(tr('No alarms.', '没有报警。'), style: NwText.bodyMedium.copyWith(color: c.textSecondary)),
        if (rows != null && rows.isNotEmpty && rows.every((a) => a.resolvedMs != null))
          Padding(
            padding: const EdgeInsets.only(bottom: Nw.s8),
            child: Text(tr('No open alarms.', '没有未处理的报警。'),
                style: NwText.bodyMedium.copyWith(color: c.textSecondary)),
          ),
        for (final a in rows ?? const <Alert>[])
          Padding(
            padding: const EdgeInsets.only(bottom: Nw.s8),
            child: NwCard(
              key: AlarmLogPage.rowKey(a.key),
              onTap: () => Navigator.push(context,
                  MaterialPageRoute<void>(builder: (_) => SiteAlertScenePage(api: widget.api, alert: a))),
              child: Row(children: [
                NwLevelBox(level: a.level),
                const SizedBox(width: Nw.s8),
                Expanded(
                    child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text(alertLine(a.robot, a.kind, a.title),
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: NwText.bodyMedium.copyWith(color: c.text, fontWeight: FontWeight.w600)),
                  Text(
                      a.resolvedMs != null
                          ? tr('Resolved${a.ackedBy.isEmpty ? '' : ' · handled by ${a.ackedBy}'}',
                              '已解决${a.ackedBy.isEmpty ? '' : ' · ${a.ackedBy} 处理'}')
                          : a.ackedBy.isNotEmpty
                              ? tr('${a.ackedBy} is handling it', '${a.ackedBy} 在处理')
                              : tr('Not handled yet', '未处理'),
                      style: NwText.bodySmall.copyWith(color: c.textSecondary)),
                ])),
                Text(_day(a.firstMs), style: NwText.labelSmall.copyWith(color: c.textSecondary)),
              ]),
            ),
          ),
      ]),
    );
  }
}
