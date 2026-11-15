/// 单狗页（W00c4）：状态、派巡检、叫停、回待命点、遥控、画面，管理员的录包、标原点。
///
/// **按钮按角色显示**：经理（owner）只有「叫停」；保安（guard）与管理员（admin）能派单。真正的
/// 权限在站点上（站点回 403），这里只是不给人一个注定被拒的按钮。
library;

import 'dart:async';
import 'dart:math';

import 'package:flutter/material.dart';

import '../l10n.dart';
import '../net/site_client.dart';
import '../net/site_text.dart';
import 'nw/nw_ask.dart';
import 'nw/nw_button.dart';
import 'nw/nw_p3_robots.dart';
import 'nw/nw_theme.dart';
import 'nw/nw_widgets.dart';
import 'robot_events.dart';
import 'robot_ops.dart';
import 'robot_bind_page.dart';
import 'patrol_dispatch.dart';
import 'refusal.dart';
import 'site_deter.dart';
import 'site_deterrence.dart';
import 'site_logs.dart';
import 'site_mapping.dart';
import 'site_recordings.dart';
import 'site_standby.dart';
import 'site_supervise.dart';
import 'site_teleop.dart';
import 'site_maps.dart' show SiteMapTab;
import 'site_video.dart';
import 'stop_failed.dart';
import 'nw/nw_shell.dart' show EstopSquare;
import 'widget/alarm_widgets.dart' show StopAllButton;
import 'widget/fields_dialog.dart';

/// 一只狗的状态说成一行（狗列表、单狗页共用）。
String robotStatusLine(Map<String, dynamic> r) {
  final st = r['status'];
  if (r['revoked'] == true) return tr('Revoked', '已吊销');
  if (st is! Map) return tr('No status', '无状态');
  final online = st['online'] == true && r['fresh'] == true;
  final task = st['task'];
  final lap = task is Map ? lapText(r['lap']) : '';      // W76：几圈的巡逻跑到第几圈
  final taskText = task is Map
      ? '${taskLabel(task)}${lap.isEmpty ? '' : ' · $lap'}'
      : robotNotStanding(r)
          ? tr('Not standing (crouched or lying down)', '没站起来（蹲着或趴着）')
          : tr('Idle', '空闲');
  final held = r['held'] is Map ? tr('Stopped · ', '已叫停 · ') : '';
  // W33：只许手动派的狗（站点自己不让它动）；狗确认看见人（决策 48）
  final manual = r['manual_only'] is Map ? tr('Manual only · ', '仅限手动 · ') : '';
  final caps = r['capabilities'];
  final tasks = caps is Map ? caps['tasks'] : null;
  final p = tasks is Map ? tasks['persons'] : null;
  final seen = online && p is Map && p['state'] == 'ok' && p['present'] == true
      ? tr(' · sees ${p['count'] ?? 1} person(s)', ' · 看见 ${p['count'] ?? 1} 人')
      : '';
  return held +
      manual +
      (online ? tr('Online · $taskText$seen', '在线 · $taskText$seen') : tr('Offline', '离线'));
}

/// 一趟任务说人话（W13：回充那几趟）；别的照原样 `kind state`。
String taskLabel(Map task) {
  final id = '${task['task_id'] ?? ''}';
  if (task['kind'] == 'dock') return tr('Charging (docking, charging, undocking)', '充电中（对桩、充电、离桩）');
  if (task['kind'] == 'goto' && id.startsWith('charge-')) return tr('Going to charge', '去充电');
  // 手机 App 测试 M14：以前原样印 `goto pending`
  final what = switch ('${task['kind']}') {
    'patrol' => tr('Patrolling', '巡逻'),
    'goto' => id.isEmpty ? tr('Going to a point', '去某个点') : taskKindText(id),
    'teleop' => tr('Remote control', '遥控'),
    _ => taskKindText(id),
  };
  final state = switch ('${task['state']}') {
    'pending' || 'queued' => tr('starting', '准备出发'),
    'running' || 'active' => tr('under way', '进行中'),
    'paused' => tr('paused', '暂停'),
    'done' || 'succeeded' => tr('done', '完成'),
    'failed' => tr('failed', '失败'),
    'aborted' => tr('stopped', '已停'),
    final x => x,
  };
  return '$what · $state';
}

/// 机器人连的 WiFi 一行：`Estate · 走 4G`（W42）。
String robotWifiLine(Map w) {
  final link = switch (w['link']) {
    'wifi' => tr('on WiFi', 'WiFi 连接'),
    '4g' => tr('on 4G', '4G 连接'),
    _ => tr('no network', '无网络'),
  };
  final ssid = '${w['ssid'] ?? ''}';
  return ssid.isEmpty ? link : '$ssid · $link';
}

class SiteRobotPage extends StatefulWidget {
  final SiteApi api;
  final String robotId;

  /// App V2：从「现场 → 机器人」进来是浅色（顶上小急停、「操作 | 设置」两页签）；从「现在」进来是深色
  /// （稿 N-robot / M-robot，右下角全部急停，右上 ⋮ 去设置）。
  final bool light;

  /// 一打开就在「设置」页签（深色页 ⋮ →「机器人设置」）。
  final bool settings;
  const SiteRobotPage({super.key, required this.api, required this.robotId, this.light = false, this.settings = false});

  static const Key operateTabKey = Key('robot-tab-operate');
  static const Key settingsTabKey = Key('robot-tab-settings');
  static const Key menuKey = Key('robot-menu');
  static const Key deterBannerKey = Key('robot-deter-banner');
  static const Key estopKey = Key('robot-estop');
  static const Key tonightKey = Key('robot-tonight');
  static const Key lieKey = Key('btn-posture-lie');
  static const Key lieConfirmKey = Key('lie-confirm');
  static const Key relocAutoKey = Key('btn-reloc-auto');
  static const Key manualKey = Key('btn-manual-only');
  static const Key renameKey = Key('btn-rename');
  static const Key nameFieldKey = Key('robot-name-field');
  static const Key nameSaveKey = Key('robot-name-save');
  static const Key unbindKey = Key('btn-unbind');
  static const Key unbindPwKey = Key('robot-unbind-pw');
  static const Key unbindGoKey = Key('robot-unbind-go');

  /// 操作结果的提示条。
  static const Key msgKey = Key('robot-msg');

  @override
  State<SiteRobotPage> createState() => _SiteRobotPageState();
}

class _SiteRobotPageState extends State<SiteRobotPage> with NwAsk {
  Map<String, dynamic>? _view;

  /// 「设置」页签（浅色页才有两页签）。
  late bool _settings = widget.settings;

  /// 就地确认（不弹窗）：'stand' / 'lie' / 'home-abort' / 'unbind' / 'name'。
  String? _ask;
  final TextEditingController _name = TextEditingController();
  final TextEditingController _pw = TextEditingController();

  /// App V2：叫停没成功（不弹窗）—— 页顶红框，人按「知道了」才收。
  Object? _stopErr;

  /// 经理页的「今晚」（今天的巡逻）。
  List<Map<String, dynamic>> _today = const [];
  int? _offsetMin;
  /// 手机 App 测试 M14：操作结果用屏幕底部的提示条（以前写在页顶，人在下面按按钮看不见）。
  void _say(String text) {
    if (!mounted) return;
    ScaffoldMessenger.maybeOf(context)
      ?..hideCurrentSnackBar()
      ..showSnackBar(SnackBar(
          key: SiteRobotPage.msgKey,
          content: Text(text),
          behavior: SnackBarBehavior.floating,
          duration: const Duration(seconds: 6)));
  }

  /// POC 11-05：任务派出去站点收下了，机器人后来报失败（起飞前检查没过之类）—— 这里听事件流，
  /// 是这台的就在页面上说原因；不然人只看到「没动」。
  StreamSubscription<Map<String, dynamic>>? _events;

  @override
  void initState() {
    super.initState();
    _reload();
    _events = widget.api.events().listen(_onFeed, onError: (Object _) {}, cancelOnError: true);
    // 易用性第 7 轮：别处（网页、手柄）改了它的姿态、任务，这一页开着也要跟上（以前要退出再进）
    _poll = Timer.periodic(kRobotPageRefresh, (_) => unawaited(_reload(quiet: true)));
    final s = widget.api.session;
    if (s != null && s.canPatrol && !s.canDispatch) unawaited(_loadToday());
  }

  Future<void> _loadToday() async {
    try {
      final d = await widget.api.patrolsToday();
      if (!mounted) return;
      setState(() {
        _offsetMin = (d['utc_offset_min'] as num?)?.toInt();
        _today = [for (final x in (d['items'] as List? ?? const [])) if (x is Map) x.cast<String, dynamic>()];
      });
    } on SiteError {
      // 读不到就不摆「今晚」
    }
  }

  Timer? _poll;
  final List<Timer> _after = <Timer>[];

  @override
  void dispose() {
    _poll?.cancel();
    _name.dispose();
    _pw.dispose();
    for (final x in _after) {
      x.cancel();
    }
    unawaited(_events?.cancel());
    super.dispose();
  }

  void _onFeed(Map<String, dynamic> f) {
    final e = f['event'];
    if (f['kind'] != 'event' || f['robot_id'] != widget.robotId || e is! Map) return;
    if (e['kind'] != 'task_failed' || !mounted) return;
    final d = e['data'];
    final tid = d is Map ? '${d['task_id'] ?? ''}' : '';
    final why = d is Map ? '${d['reason'] ?? ''}' : '';
    final code = navCodeText(d is Map ? d['code'] : null);
    final fix = why.contains('未标原点')
        ? tr(' Drive the robot to the dock, set its position, then tap "Mark origin here".',
            '把机器人开到充电桩前，设好位置后点「在这儿标原点」。')
        : code != null
            ? tr(' ${code.$2}.', '${code.$2}。')
            : '';
    // 手机 App 测试 M14：不给人看任务号
    _say(tr('${tid.isEmpty ? 'The task' : taskKindText(tid)} did not run: $why.$fix', '${tid.isEmpty ? '任务' : taskKindText(tid)}没走成：$why。$fix'));
    unawaited(_reload());
  }

  /// [quiet]：定时刷新的，读不到不弹提示（断网时每几秒弹一次会刷屏；值守页有连不上的横幅）。
  Future<void> _reload({bool quiet = false}) async {
    try {
      final v = await widget.api.robot(widget.robotId);
      if (mounted) setState(() => _view = v);
    } on SiteError catch (e) {
      if (mounted && !quiet) _say(e.toString());
    }
    unawaited(_loadDeter());
  }

  /// 这台正在驱离的那一场（外审 App-V2-2 N3：保安从机器人页也能进完整的驱离页：降级、转人工、结束）。
  Map<String, dynamic>? _deterSession;

  Future<void> _loadDeter() async {
    if (!(widget.api.session?.canDispatch ?? false)) return;
    try {
      final d = await widget.api.deterrence();
      final mine = d.where((x) => '${x['robot_id']}' == widget.robotId).firstOrNull;
      if (mounted) setState(() => _deterSession = mine);
    } on SiteError {
      return; // 老站点没有驱离
    }
  }

  /// 发一条、把结果写在页面上。狗收下了（或站点没带回执）回真。
  Future<bool> _do(Future<Map<String, dynamic>> Function() f, String what, {bool stop = false}) async {
    String msg;
    var ok = false;
    try {
      final r = await f();
      final ack = r['ack'];
      final reason = ack is Map ? '${ack['reason'] ?? ''}' : '';
      ok = ack is! Map || ack['result'] == 'accepted' || ack['result'] == 'duplicate';
      // 手机 App 测试 M14：回执说人话（以前是 accepted / rejected）
      final res = ok ? tr('sent', '已发出') : tr('not accepted by the robot', '机器人没接受');
      msg = reason.isEmpty
          ? tr('$what: $res', '$what：$res')
          : tr('$what: $res (${ackReasonText(reason)})', '$what：$res（${ackReasonText(reason)}）');
      if (stop && !ok && mounted) {
        setState(() => _stopErr = reason.isEmpty ? res : ackReasonText(reason));
      }
    } on SiteError catch (e) {
      msg = tr('$what failed: ${refusalText(e)}', '$what 失败：${refusalText(e)}');
      if (stop) {
        // 手机 App 测试 M02：叫停失败要醒目、不自动消失，叫人按机身急停
        if (mounted) setState(() => _stopErr = e);
      } else if (e.status == 409 && e.body['reason_code'] is String && mounted) {
        // W53：常见的拒绝说清楚、给去处理的按钮
        await showRefusal(context, widget.api, e, robotId: widget.robotId, title: what, onChanged: _reload);
      }
    }
    if (!mounted) return ok; // 派单要等回执，人可能早就退出这一页了
    _say(msg);
    await _reload();
    return ok;
  }

  static bool _busy(Map<String, dynamic>? v) {
    final st = v?['status'];
    final task = st is Map ? st['task'] : null;
    return task is Map && '${task['task_id'] ?? ''}'.isNotEmpty;
  }

  /// 易用性第 7 轮 A7-01（用户 11-11）：蹲着、趴着时站点不让开遥控，姿态菜单进不去 —— 机器人页直接给「站起」。
  /// 站点报了没站起来（``ready.motion`` 是 false）、急停没按着、没任务、机器人会站起，能遥控的人才有。
  static bool needsStand(Map<String, dynamic>? v) {
    final st = v?['status'];
    final ready = st is Map ? st['ready'] : null;
    return ready is Map && ready['motion'] == false && ready['estop_clear'] != false && !_busy(v) &&
        robotPostures(v).contains('stand');
  }

  /// 站起（App V2 不弹窗）：先在原地问一句「旁边没人」，再按「确认站起」才发。
  void _standUp() => setState(() => _ask = 'stand');

  Future<void> _posture(String mode) async {
    setState(() => _ask = null);
    await _do(() => widget.api.posture(widget.robotId, mode), mode == 'stand' ? tr('Stand up', '站起') : tr('Lie down', '趴下'));
  }

  /// 中止并回原点（App V2 不弹窗）：就地确认。
  void _abortHome() => setState(() => _ask = 'home-abort');

  Future<void> _abortHomeGo() async {
    setState(() => _ask = null);
    await _do(() => widget.api.returnHome(widget.robotId, abort: true), tr('Abort and return to origin', '中止并回原点'));
  }

  Future<void> _rename() async {
    final n = _name.text.trim();
    if (n.isEmpty) return;
    setState(() => _ask = null);
    try {
      await widget.api.renameRobot(widget.robotId, n);
      _say(tr('Renamed to $n', '已改名为 $n'));
    } on SiteError catch (e) {
      _say(tr('Rename failed: ${refusalText(e)}', '改名失败：${refusalText(e)}'));
    }
    await _reload();
  }

  Future<void> _manual(bool on) async {
    try {
      await widget.api.setManualOnly(widget.robotId, on);
      _say(on
          ? tr('${widget.robotId} now runs only when dispatched by hand', '${widget.robotId} 改成只许手动派')
          : tr('${widget.robotId} now takes scheduled and automatic dispatch', '${widget.robotId} 接回日程和自动派遣'));
    } on SiteError catch (e) {
      _say(tr('Not changed: ${refusalText(e)}', '没改成：${refusalText(e)}'));
    }
    await _reload();
  }

  Future<void> _unbind() async {
    final pw = _pw.text;
    if (pw.isEmpty) return;
    try {
      await widget.api.revokeRobot(widget.robotId, pw);
      _pw.clear();
      if (!mounted) return;
      _say(tr('${widget.robotId} was unbound. Its recordings are kept.', '${widget.robotId} 已解绑，录像保留。'));
      Navigator.of(context).maybePop();
    } on SiteError catch (e) {
      _say(tr('Not unbound: ${refusalText(e)}', '没解绑：${refusalText(e)}'));
    }
  }

  void _openTrail() => Navigator.push(context,
      MaterialPageRoute<void>(builder: (_) => SiteMappingTrailPage(api: widget.api, robotId: widget.robotId)));

  /// 录包（W00c5d 第二部分，管理员）：给包起个名，之后经站点遥控开着狗走一圈，再停。
  /// 填了地图号与版本就边走边建（W09c2）：停下之后狗上直接打包成这一版，不用再点「重建」。
  Future<void> _startRecord() async {
    final got = await askFields(
        title: tr('Start bag recording', '开始录包'),
        fields: [
          DialogField(tr('Bag name (letters, digits, . _ -)', '包名（字母、数字、. _ -）'),
              key: const Key('record-name'),
              initial:
                  'rec-${DateTime.now().toUtc().toIso8601String().substring(0, 16).replaceAll(':', '')}'),
          DialogField(
              tr('Map ID (build while driving; leave empty to record only)', '地图号（边走边建；空着只录包）'),
              key: const Key('record-map')),
          DialogField(tr('Version', '版本'), key: const Key('record-version')),
        ],
        confirm: tr('Start', '开始'),
        confirmKey: const Key('record-go'));
    if (got == null || got[0].isEmpty) return;
    final mapId = got[1].trim(), version = got[2].trim();
    if (mapId.isEmpty != version.isEmpty) {
      _say(tr(
          'Build while driving: fill in both map ID and version (leave both empty to record only)',
          '边走边建：地图号和版本需同时填写（只录包则都留空）'));
      return;
    }
    final ok = await _do(
        () => widget.api.mapping(widget.robotId, 'start', name: got[0], mapId: mapId, version: version),
        mapId.isEmpty
            ? tr('Start bag recording', '开始录包')
            : tr('Start bag recording and mapping $mapId:$version', '开始录包并建图 $mapId:$version'));
    // 收下了就打开录包轨迹（W00c6h）：边开边看哪儿走过了。录包在狗上后台起，起来之后才开始记点。
    if (ok && mounted && robotCan(_view, 'mapping_trail')) _openTrail();
  }

  /// 设位置（W00c6e）：「狗在原点」一键，或者输地图坐标（朝向按度输）。
  Future<void> _relocalize([String? pick]) async {
    final how = pick ??
        await ask<String>(title: tr('Where is the robot now', '机器人当前位置'), choices: [
          AskChoice(tr('At the origin (dock)', '在原点（充电桩）'), 'home', key: const Key('reloc-home')),
          // 手机 App 测试 M28：在地图上点（以前只有地图栏有，这里没指过去）
          AskChoice(tr('Pick it on the map', '在地图上点出位置'), 'map', key: const Key('reloc-map')),
          AskChoice(tr('Enter map coordinates', '输地图坐标'), 'xy', key: const Key('reloc-xy')),
          if (robotCanFindPose(_view))
            AskChoice(tr('Auto-localize (match the scanned walls to the map)', '自动定位（用扫描到的墙体匹配地图）'), 'find',
                key: const Key('reloc-find')),
        ]);
    if (how == null || !mounted) return;
    if (how == 'map') {
      await Navigator.push(
          context,
          MaterialPageRoute<void>(
              builder: (_) => Scaffold(
                  appBar: AppBar(
                      title: Text(tr('Set position of ${widget.robotId}: tap the map, then Set position',
                          '设 ${widget.robotId} 的位置：点地图，再点「设位置」'))),
                  body: SiteMapTab(api: widget.api))));
      if (mounted) await _reload();
      return;
    }
    if (how == 'find') {
      // W41：狗拿看到的墙在整张图上套；认不准它会拒、说原因（有两处差不多像……），那时再手动设。
      await _do(() => widget.api.relocalize(widget.robotId, global: true), tr('Auto-localize', '自动定位'));
      return;
    }
    if (how == 'home') {
      // 点错了狗就按错的位置走（W00c6e 内审）：再确认一次。
      final sure = await askYes(tr('Is the robot at the origin now?', '机器人当前在原点？'),
          body: tr(
              'The robot must be on the origin (dock), facing as when the origin was marked; otherwise navigation will be wrong.',
              '机器人须站在原点（充电桩）上，朝向与标原点时一致，否则导航会出错。'),
          ok: tr('At the origin', '在原点'),
          okKey: const Key('reloc-home-go'));
      if (!sure) return;
      await _do(() => widget.api.relocalize(widget.robotId, atHome: true), tr('Set position', '设位置'));
      return;
    }
    final got = await askFields(
        title: tr('Where is the robot on the map', '机器人在地图上的当前位置'),
        fields: [
          DialogField(tr('x (m)', 'x（米）'), key: const Key('reloc-x')),
          DialogField(tr('y (m)', 'y（米）'), key: const Key('reloc-y')),
          // 地图的 x 轴不一定朝东（雷达建的图按建图起点定轴，W00c6e 内审）。
          DialogField(
              tr('Heading (degrees; 0 = map x axis, counter-clockwise positive)',
                  '朝向（度，地图 x 轴方向为 0，逆时针为正）'),
              key: const Key('reloc-yaw'),
              initial: '0'),
        ],
        confirm: tr('Set', '设置'),
        confirmKey: const Key('reloc-go'));
    if (got == null) return;
    final x = double.tryParse(got[0]), y = double.tryParse(got[1]), deg = double.tryParse(got[2]);
    if (x == null || y == null || deg == null || !x.isFinite || !y.isFinite || !deg.isFinite) {
      if (mounted) _say(tr('Coordinates and heading must be numbers', '坐标和朝向须为数字'));
      return;
    }
    await _do(() => widget.api.relocalize(widget.robotId, x: x, y: y, yaw: deg * pi / 180),
        tr('Set position', '设位置'));
  }

  /// 在当前位置标原点（W00c6f，管理员）：确认之后狗用它此刻的位置当这张图上的原点（W13a：原点跟待命点
  /// 分开了 —— 这张图上还没有待命点时，站点顺手用它建一个默认的）。
  Future<void> _markHome() async {
    final ok = await askYes(tr('Mark origin here', '在这儿标原点'),
        body: tr(
            'Set the origin of ${widget.robotId} on this map to its current position? Standby points are unchanged.\n'
                'This applies to the whole map and cannot be undone (only by marking again). Return home and "At the origin" will use the new spot.\n'
                'The robot verifies its localization first and won\'t mark it if the position isn\'t set, the error is large, or it is busy or switching maps.',
            '将 ${widget.robotId} 在此地图上的原点改为当前位置？待命点不变。\n'
                '对整张地图生效，不能撤销（只能重新标）。「回原点」「在原点」以后都按新的位置。\n'
                '机器人会先核验定位：未设置位置、偏差过大、正在执行任务或换图时不会标记。'),
        ok: tr('Mark', '标记'),
        okKey: const Key('mark-home-go'));
    if (!ok) return;
    String msg;
    try {
      Map<String, dynamic> r;
      try {
        r = await widget.api.markHome(widget.robotId);
      } on SiteError catch (e) {
        final taken = e.body['name_taken'];
        if (e.status != 409 || taken is! Map || !mounted) rethrow;
        // 同名的点登记在别的图上（比如重建之前那一版）：问清楚再搬（W00c6f 内审）。
        final where = '${taken['map_id']}:${taken['map_version']}';
        final move = await askYes(tr('Replace the old standby point?', '替换旧的待命点？'),
            body: tr(
                'Standby point home is registered on $where. Move it to the map the robot is using now '
                    '(it is removed from $where)?',
                '待命点 home 目前登记在 $where 上。是否移到机器人当前使用的地图？（$where 上将删除）'),
            ok: tr('Replace', '替换'),
            okKey: const Key('mark-home-replace'));
        if (!move) {
          if (mounted) {
            _say(tr('Not marked: standby point home is still on $where',
                '未标记：待命点 home 仍在 $where 上'));
          }
          return;
        }
        r = await widget.api.markHome(widget.robotId, replace: true);
      }
      final d = (r['ack'] as Map?)?['data'];
      if (d is Map) {
        final x = (d['x'] as num).toStringAsFixed(1), y = (d['y'] as num).toStringAsFixed(1);
        final sigma = (d['sigma_m'] as num? ?? 0).toStringAsFixed(1);
        msg = tr('Origin marked: ($x, $y), error about $sigma m',
            '原点已标记：($x, $y)，偏差约 $sigma m');
      } else {
        msg = tr('Origin marked', '原点已标记');
      }
    } on SiteError catch (e) {
      final d = e.body['data'];
      if (e.status == 500 && d is Map && d['x'] is num && d['y'] is num) {
        // 狗上已经换了、站点没登记上：给坐标，好手工登记待命点。
        final at = '${d['map_id']}:${d['map_version']}';
        final x = (d['x'] as num).toStringAsFixed(1), y = (d['y'] as num).toStringAsFixed(1);
        msg = tr("${e.message}: the robot's origin is at ($x, $y) on $at",
            '${e.message}：机器人上的原点位于 $at 的 ($x, $y)');
      } else if (e.status == 409) {
        // 站点回的是「狗没标:<狗的原因>」：原因照拒收那一套说人话。
        final why = ackReasonText(e.message.replaceFirst(RegExp(r'^机器人标记失败[:：]'), ''));
        msg = tr('Not marked: $why', '未标记：$why');
      } else {
        msg = e.toString(); // 504「狗可能已经标了」等：照站点说的
      }
    }
    if (!mounted) return;
    _say(msg);
    await _reload();
  }

  /// 叫停之前**现取**正在跑的任务：页面上的可能是几秒前的，排程早换了一趟。
  Future<void> _abort() async {
    Map<String, dynamic> v;
    try {
      v = await widget.api.robot(widget.robotId);
    } on SiteError catch (e) {
      if (mounted) {
        _say(tr('Stop failed: ${refusalText(e)}', '叫停失败：${refusalText(e)}'));
        setState(() => _stopErr = e);
      }
      return;
    }
    final st = v['status'];
    final task = st is Map ? st['task'] : null;
    final tid = task is Map ? task['task_id'] : null;
    if (tid is! String || tid.isEmpty) {
      if (mounted) {
        setState(() => _view = v);
        _say(tr('The robot isn\'t running a task', '机器人当前无任务'));
      }
      return;
    }
    await _do(() => widget.api.abort(widget.robotId, tid), tr('Stop', '叫停'), stop: true);
  }

  /// 派巡逻（W53）：底部弹框，带估时、撞日程排队、被拒说原因。
  Future<void> _patrol() async {
    final msg = await showPatrolSheet(context, widget.api, widget.robotId);
    if (msg != null && mounted) _say(msg);
    await _reload();
  }

  /// W42 §6：机器人上有人提了换 WiFi —— 说清楚，给有管理权限的人「确认 / 不换」。
  Widget? _wifiChange(NwColors c, Map<String, dynamic>? v, bool manage) {
    final w = v?['wifi'];
    final ch = w is Map ? w['change'] : null;
    if (ch is! Map) return null;
    final trial = ch['mode'] == 'trial';
    return Padding(
      padding: const EdgeInsets.only(top: Nw.s8),
      child: NwCard(
        key: const Key('robot-wifi-change'),
        tone: NwTone.warning,
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(
              trial
                  ? tr("The robot lost the site and is trying WiFi “${ch['ssid']}”. Approve within 30 minutes to keep it, otherwise it reverts.",
                      '机器人无法连接站点，正在尝试 WiFi「${ch['ssid']}」。30 分钟内确认则保留，否则恢复原网络。')
                  : tr("Someone at the robot asked to switch its WiFi to “${ch['ssid']}”. Nothing changes until it is approved.",
                      '请确认机器人端申请将 WiFi 切换为「${ch['ssid']}」'),
              style: NwText.bodyMedium.copyWith(color: c.text)),
          if (manage) ...[
            const SizedBox(height: Nw.s8),
            Wrap(spacing: Nw.s8, children: [
              NwButton(
                  buttonKey: const Key('btn-wifi-approve'),
                  size: NwButtonSize.small,
                  label: tr('Approve WiFi change', '确认换 WiFi'),
                  onPressed: () => _do(() => widget.api.confirmRobotWifi(widget.robotId, '${ch['id']}', true),
                      tr('Approve WiFi change', '确认换 WiFi'))),
              NwButton(
                  buttonKey: const Key('btn-wifi-reject'),
                  size: NwButtonSize.small,
                  variant: NwButtonVariant.ghost,
                  label: tr("Reject", '拒绝'),
                  onPressed: () => _do(() => widget.api.confirmRobotWifi(widget.robotId, '${ch['id']}', false),
                      tr("Reject WiFi change", '拒绝更换 WiFi'))),
            ]),
          ],
        ]),
      ),
    );
  }

  /// 就地确认那一条（不弹窗）：一句话 + 「确认」「取消」一排等宽。
  Widget _confirm(NwColors c, String text, Key goKey, String go, VoidCallback onGo) => Container(
      margin: const EdgeInsets.only(top: Nw.s8),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(color: c.bg, border: Border.all(color: c.outline)),
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        Text(text, style: NwText.bodyMedium.copyWith(color: c.text)),
        const SizedBox(height: Nw.s8),
        nwButtonRows([
          nwOpButton(c, goKey, go, onGo, primary: true),
          nwOpButton(c, const Key('robot-ask-cancel'), tr('Cancel', '取消'), () => setState(() => _ask = null)),
        ], per: 2),
      ]));

  /// 设置页签的一行：名称、值、右边一个按钮。
  Widget _row(NwColors c, String label, String value, {Widget? action, Key? key}) => Container(
      key: key,
      padding: const EdgeInsets.symmetric(vertical: 10),
      decoration: BoxDecoration(border: Border(top: BorderSide(color: c.outline))),
      child: Row(crossAxisAlignment: CrossAxisAlignment.center, children: [
        SizedBox(width: 104, child: Text(label, style: NwText.bodyMedium.copyWith(color: c.textSecondary))),
        Expanded(child: Text(value, style: NwText.bodyMedium.copyWith(color: c.text))),
        if (action != null) ...[const SizedBox(width: Nw.s8), action],
      ]));

  Widget _small(NwColors c, Key key, String label, VoidCallback? on) => OutlinedButton(
      key: key,
      style: OutlinedButton.styleFrom(
          foregroundColor: c.text,
          side: BorderSide(color: c.textMuted),
          minimumSize: const Size(48, 40),
          padding: const EdgeInsets.symmetric(horizontal: 12),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(2))),
      onPressed: on,
      child: Text(label));

  /// 设置页签有没有东西给这个角色（深色页的 ⋮ 才出）。
  bool _hasSettings(SiteSession? s, Map<String, dynamic>? v) =>
      (s?.canManageRobots ?? false) || (s?.canManageMaps ?? false) || (s?.canSeeHealth ?? false) || (s?.canDispatch ?? false);

  @override
  Widget build(BuildContext context) {
    final light = widget.light;
    return Theme(
        data: nwTheme(light ? Brightness.light : Brightness.dark),
        child: Builder(builder: (context) => _page(context)));
  }

  Widget _page(BuildContext context) {
    final c = Nw.of(context);
    final s = widget.api.session;
    final v = _view;
    final events = compactEvents((v?['events'] as List? ?? const []).whereType<Map>().toList());
    final phase = v == null ? null : robotPhase(v);
    final dispatch = s?.canDispatch ?? false;
    final light = widget.light;
    final name = '${v?['name'] ?? ''}';
    final title = name.isEmpty || name == widget.robotId ? widget.robotId : '${widget.robotId} · $name';
    final battery = robotBattery(v);
    final sub = [
      if (phase != null) robotPhaseLabel(phase),
      if (battery != null) '${battery.round()}%',
    ].join(' · ');
    // 手机 App 测试 M12：从遥控等页面回来就重新拉一次（以前要手动下拉才看到「恢复」）
    Future<void> go(Widget Function() page) async {
      await Navigator.push(context, MaterialPageRoute<void>(builder: (_) => page()));
      if (mounted) await _reload();
      // A7-04：遥控刚放下，站点要一两秒才收掉「遥控 · 进行中」—— 回来后 1 秒、2.5 秒各再看一次
      for (final ms in const [1000, 2500]) {
        _after.add(Timer(Duration(milliseconds: ms), () => unawaited(_reload(quiet: true))));
      }
    }

    final header = Container(
      decoration: BoxDecoration(color: c.surface, border: Border(bottom: BorderSide(color: c.outline))),
      child: SafeArea(
          bottom: false,
          child: Padding(
              padding: EdgeInsets.fromLTRB(Navigator.canPop(context) ? 4 : Nw.s16, 4, Nw.s8, 4),
              child: Row(children: [
                if (Navigator.canPop(context)) const BackButton(),
                Expanded(
                    child: Column(crossAxisAlignment: CrossAxisAlignment.start, mainAxisSize: MainAxisSize.min, children: [
                  Text(title,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: NwText.titleLarge.copyWith(color: c.text, fontWeight: FontWeight.w700)),
                  if (sub.isNotEmpty || !dispatch)
                    Text(
                        (s?.canPatrol ?? false) && !dispatch
                            ? tr('Managers view status and dispatch patrols', '经理看状态、派巡逻')
                            : sub,
                        key: const Key('robot-phase'),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: NwText.bodySmall.copyWith(color: c.textSecondary)),
                ])),
                if (light && (s?.canAbort ?? false))
                  FilledButton.icon(
                      key: SiteRobotPage.estopKey,
                      style: FilledButton.styleFrom(
                          backgroundColor: c.error,
                          foregroundColor: c.onError,
                          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(2))),
                      onPressed: () => StopAllButton.press(context, widget.api, _say),
                      icon: const Icon(Icons.remove_circle_outline_rounded, size: 18),
                      label: Text(tr('E-STOP', '急停'))),
                if (!light && _hasSettings(s, v))
                  PopupMenuButton<String>(
                      key: SiteRobotPage.menuKey,
                      icon: const Icon(Icons.more_vert_rounded),
                      onSelected: (_) => go(() => SiteRobotPage(api: widget.api, robotId: widget.robotId, light: true, settings: true)),
                      itemBuilder: (_) => [
                            PopupMenuItem<String>(value: 'settings', child: Text(tr('Robot settings', '机器人设置'))),
                          ]),
              ]))),
    );

    final deterNow = _deterSession;
    final body = <Widget>[
      if (deterNow != null && (s?.canDispatch ?? false) && !_settings)
        Padding(
            padding: const EdgeInsets.fromLTRB(Nw.s16, 12, Nw.s16, 0),
            child: NwBanner(
                key: SiteRobotPage.deterBannerKey,
                tone: NwTone.error,
                icon: Icons.campaign_rounded,
                title: tr('Deterring · ${deterSessionText(deterNow)}', '驱离中 · ${deterSessionText(deterNow)}'),
                subtitle: tr('Tap to change level, take over or end', '点进去降级、转人工或结束'),
                onTap: () => go(() => SiteDeterrencePage(api: widget.api, robotId: widget.robotId)))),
      if (light)
        Padding(
            padding: const EdgeInsets.fromLTRB(Nw.s16, 12, Nw.s16, 12),
            child: SegmentedButton<bool>(
                showSelectedIcon: false,
                segments: [
                  ButtonSegment<bool>(value: false, label: Text(tr('Operate', '操作'), key: SiteRobotPage.operateTabKey)),
                  ButtonSegment<bool>(value: true, label: Text(tr('Settings', '设置'), key: SiteRobotPage.settingsTabKey)),
                ],
                selected: {_settings},
                onSelectionChanged: (x) => setState(() => _settings = x.first))),
      if (light && _settings) ..._settingsTab(c, s, v, go) else ..._operateTab(c, s, v, phase, go),
      if (!_settings || !light) ...[
        if (events.isNotEmpty)
          nwRobotSection(c, tr('Recent events', '最近的事件'), [
            for (final e in events.take(30))
              Padding(
                  padding: const EdgeInsets.only(bottom: Nw.s8),
                  child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    SizedBox(
                        width: 124,
                        child: Text(robotEventTime(e['stamp']),
                            maxLines: 1, style: NwText.bodyMedium.copyWith(color: c.textSecondary))),
                    Expanded(
                        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                      Text(robotEventTitle('${e['kind']}', e['data'] is Map ? (e['data'] as Map).cast<String, dynamic>() : null),
                          style: NwText.bodyMedium.copyWith(color: c.text)),
                      ?_eventSub(e),
                    ])),
                  ])),
          ]),
      ],
    ];

    return Scaffold(
      backgroundColor: c.bg,
      body: Stack(children: [
        Column(children: [
          header,
          // 「我在现场监护」钉在列表外面（W00c6i 内审）：放在按需构建的列表里，上面插一行提示或者往下一翻，
          // 它的状态就被换掉、发出放租 —— 刚派出去的任务随即被中止。
          // 外审 App-V2-1 #3：停车没成的红框钉在列表外面（滚到哪都看得见），横屏太矮时自己滚
          if (_stopErr != null)
            ConstrainedBox(
                constraints: BoxConstraints(maxHeight: MediaQuery.sizeOf(context).height * 0.5),
                child: SingleChildScrollView(
                    child: StopFailedCard(
                        robot: widget.robotId,
                        error: _stopErr,
                        onAgain: () {
                          setState(() => _stopErr = null);
                          unawaited(_abort());
                        },
                        onAck: () => setState(() => _stopErr = null)))),
          if (dispatch && robotNeedsSupervision(v) && !_settings)
            SupervisionSwitch(key: ValueKey('supervise-${widget.robotId}'), api: widget.api, robotId: widget.robotId),
          Expanded(
              child: RefreshIndicator(
                  onRefresh: _reload,
                  // 一次建好（不按需）：一页就这么多，按需建的列表里下面的按钮没滚到就不存在
                  child: SingleChildScrollView(
                      physics: const AlwaysScrollableScrollPhysics(),
                      padding: EdgeInsets.only(bottom: light ? Nw.s24 : 120),
                      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [askStrip(), ...body])))),
        ]),
        // 深色页：右下角拇指区「全部急停」（经理也能按）
        if (!light && (s?.canAbort ?? false))
          Positioned(
              right: Nw.s16,
              bottom: Nw.s16,
              child: SafeArea(
                  child: EstopSquare(
                      buttonKey: SiteRobotPage.estopKey, onPressed: () => StopAllButton.press(context, widget.api, _say)))),
      ]),
    );
  }

  List<Widget> _operateTab(NwColors c, SiteSession? s, Map<String, dynamic>? v, RobotPhase? phase,
      Future<void> Function(Widget Function()) go) {
    final dispatch = s?.canDispatch ?? false;
    final busy = _busy(v);
    final battery = robotBattery(v);
    final loc = v?['loc'] is Map ? locText((v!['loc'] as Map).cast<String, dynamic>()) : '';
    final facts = [if (loc.isNotEmpty) loc, if (battery != null) tr('Battery ${battery.round()}%', '电量 ${battery.round()}%')]
        .join(' · ');
    final tone = phase == null ? NwTone.neutral : robotPhaseTone(phase);
    final dot = switch (tone) {
      NwTone.success => c.success,
      NwTone.warning => c.warning,
      NwTone.error => c.error,
      NwTone.info => c.primary,
      _ => c.textMuted,
    };
    final postures = robotPostures(v);
    final teleop = s?.canTeleop ?? false;
    final deter = dispatch && robotCan(v, 'deter');
    final tasks = <Widget>[
      if (s?.canPatrol ?? false)
        nwOpButton(c, const Key('btn-patrol'), tr('Dispatch patrol…', '派巡逻…'), _patrol, icon: Icons.route_rounded, primary: true),
      // **有叫停权限就一直按得动**（App 重做外审 I1）：`_abort` 自己现问站点现在跑的是哪一趟
      if (s?.canAbort ?? false)
        nwOpButton(c, const Key('btn-abort'), tr('Stop in place', '原地停下'), _abort, icon: Icons.pause_rounded),
      if (dispatch)
        nwOpButton(c, const Key('btn-standby'), tr('Return to standby', '回待命点'),
            () => _do(() => widget.api.returnToStandby(widget.robotId), tr('Return to standby', '回待命点'))),
      // 回原点（POC）：没任务直接回；有任务只给「中止并回原点」（要确认）
      if (dispatch && !busy)
        nwOpButton(c, const Key('btn-home'), tr('Return to origin', '回原点'),
            () => _do(() => widget.api.returnHome(widget.robotId), tr('Return to origin', '回原点'))),
      if (dispatch && busy)
        nwOpButton(c, const Key('btn-home-abort'), tr('Abort and return to origin…', '中止并回原点…'), _abortHome),
    ];
    return [
      // 状态：一句话 + 在哪、电量
      Padding(
          padding: const EdgeInsets.fromLTRB(Nw.s16, 12, Nw.s16, 12),
          child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Container(width: 14, height: 14, margin: const EdgeInsets.only(top: 5), color: dot),
            const SizedBox(width: 10),
            Expanded(
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(v == null ? tr('Loading…', '加载中…') : robotStatusLine(v),
                  key: const Key('robot-status'), style: NwText.titleMedium.copyWith(color: c.text, fontWeight: FontWeight.w700)),
              if (facts.isNotEmpty)
                Text(facts, key: const Key('robot-loc'), style: NwText.bodySmall.copyWith(color: c.textSecondary)),
              if (v?['nav'] is Map && navText((v!['nav'] as Map).cast<String, dynamic>()).isNotEmpty)
                Text(navText((v['nav'] as Map).cast<String, dynamic>()),
                    key: const Key('robot-nav'), style: NwText.bodySmall.copyWith(color: c.warning)),
            ])),
          ])),
      ?_wifiChange(c, v, s?.canManageRobots ?? false),
      // 叫停之后站点不再派它（W00c5e）：说清楚，给能派单的人一个「恢复」。
      if (v?['held'] is Map)
        Padding(
            padding: const EdgeInsets.fromLTRB(Nw.s16, 0, Nw.s16, 12),
            child: NwCard(
              key: const Key('robot-held'),
              tone: NwTone.info,
              child: Row(children: [
                Expanded(
                    child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text(tr('Stopped by ${(v!['held'] as Map)['by']}', '已被 ${(v['held'] as Map)['by']} 叫停'),
                      style: NwText.titleSmall.copyWith(color: c.text)),
                  const SizedBox(height: Nw.s4),
                  Text(
                      tr("Until you tap Resume, the site won't dispatch it (schedule, incidents, return to standby, remote control)",
                          '点「恢复」前，站点不会再派出此机器人（日程、事件、回待命点、遥控均不派）'),
                      style: NwText.bodySmall.copyWith(color: c.textSecondary)),
                ])),
                if (!dispatch)
                  // 手机 App 测试 M13：经理没有「恢复」：说找谁
                  Padding(
                      padding: const EdgeInsets.only(left: Nw.s8),
                      child: SizedBox(
                          width: 120,
                          child: Text(tr('A guard or administrator can resume it', '保安或管理员能恢复'),
                              key: const Key('robot-held-who'), style: NwText.bodySmall.copyWith(color: c.textSecondary)))),
                if (dispatch) ...[
                  const SizedBox(width: Nw.s8),
                  NwButton(
                      buttonKey: const Key('btn-resume'),
                      label: tr('Resume', '恢复'),
                      onPressed: () => _do(() => widget.api.resume(widget.robotId), tr('Resume', '恢复'))),
                ],
              ]),
            )),
      if (teleop && needsStand(v))
        Padding(
            padding: const EdgeInsets.fromLTRB(Nw.s16, 0, Nw.s16, 12),
            child: NwCard(
              key: const Key('robot-not-standing'),
              tone: NwTone.warning,
              child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                Row(children: [
                  Expanded(
                      child: Text(
                          tr("${widget.robotId} is not standing (crouching or lying). It can't patrol or be remote-controlled until it stands up.",
                              '${widget.robotId} 没站起来（蹲着或趴着），站起来之前不能派巡逻，也不能遥控。'),
                          style: NwText.bodySmall.copyWith(color: c.text))),
                  const SizedBox(width: Nw.s8),
                  NwButton(buttonKey: standUpKey, label: tr('Stand up', '站起'), onPressed: _standUp),
                ]),
                if (_ask == 'stand') _standConfirm(c),
              ]),
            )),
      // 画面经站点来（W00c5b）：谁都能看（经理也是），站点那头有人看才让狗推。
      SiteVideo(api: widget.api, robotId: widget.robotId),
      Padding(
          padding: const EdgeInsets.fromLTRB(Nw.s16, Nw.s8, Nw.s16, 12),
          child: nwOpButton(c, const Key('btn-recordings'), tr('Recordings', '录像'),
              () => go(() => SiteRecordingsPage(api: widget.api, robotId: widget.robotId)), icon: Icons.videocam_outlined)),
      if (tasks.isNotEmpty)
        nwRobotSection(c, tr('Tasks', '任务'), key: const Key('robot-tasks'), [
          nwButtonRows(tasks, per: 2),
          if (_ask == 'home-abort')
            _confirm(c, tr('Stop the current task, then go back to the origin?', '中止当前任务，然后回原点？'),
                const Key('home-abort-confirm'), tr('Abort and return', '中止并回原点'), () => unawaited(_abortHomeGo())),
        ]),
      if (teleop)
        nwRobotSection(c, tr('Remote control & posture', '遥控与姿态'), key: const Key('robot-teleop'),
            note: tr('Remote control is landscape-only; the robot stops when you leave this screen', '遥控只能横屏；离开遥控画面机器人就停'), [
          nwButtonRows([
            nwOpButton(c, const Key('btn-teleop'), tr('Remote', '遥控'),
                () => go(() => SiteTeleopPage(api: widget.api, robotId: widget.robotId)), icon: Icons.sports_esports_outlined),
            if (postures.contains('stand'))
              nwOpButton(c, const Key('btn-posture-stand'), tr('Stand up', '站起'), _standUp),
            if (postures.contains('lie'))
              nwOpButton(c, SiteRobotPage.lieKey, tr('Lie down', '趴下'), () => setState(() => _ask = 'lie')),
          ]),
          if (_ask == 'stand' && !needsStand(v)) _standConfirm(c),
          if (_ask == 'lie')
            _confirm(c, tr('${widget.robotId} will lie down where it is.', '${widget.robotId} 会原地趴下。'), SiteRobotPage.lieConfirmKey,
                tr('Confirm lie down', '确认趴下'), () => unawaited(_posture('lie'))),
          if (dispatch && robotCan(v, 'relocalize')) ...[
            const SizedBox(height: Nw.s8),
            nwButtonRows([
              if (robotCanFindPose(v))
                nwOpButton(c, SiteRobotPage.relocAutoKey, tr('Re-localize', '重新定位'), () => _relocalize('find')),
              nwOpButton(c, const Key('btn-relocalize'), tr('Assist localization…', '协助定位…'), _relocalize),
            ], per: 2),
          ],
        ]),
      // 上装（W21）：云台、喊话、警示 —— 保安、管理员；机器人报了 deter 才有
      if (deter)
        SiteDeterPage(
            key: ValueKey('deter-${widget.robotId}'),
            api: widget.api,
            robotId: widget.robotId,
            embedded: true,
            caps: Map<String, dynamic>.from(((v?['capabilities'] as Map)['tasks'] as Map)['deter'] as Map)),
      // 经理（稿 M-robot）：今晚的巡逻 + 说清楚别的归谁
      if ((s?.canPatrol ?? false) && !dispatch) ...[
        nwRobotSection(c, tr('Tonight', '今晚'), key: SiteRobotPage.tonightKey, [
          TodayPatrolList(api: widget.api, items: _today, onChanged: _loadToday, offsetMin: _offsetMin),
        ]),
        Padding(
            padding: const EdgeInsets.fromLTRB(Nw.s16, 0, Nw.s16, Nw.s16),
            child: Text(
                tr('Remote control, announcements, strobe and PTZ are operated by guards and administrators.',
                    '遥控、喊话、警灯和云台由保安、管理员操作。'),
                style: NwText.bodySmall.copyWith(color: c.textSecondary))),
      ],
    ];
  }

  Widget _standConfirm(NwColors c) => _confirm(
      c,
      tr('${widget.robotId} will stand up where it is. Make sure no one is right next to it.',
          '${widget.robotId} 会原地站起来。先确认它旁边没有人。'),
      standUpConfirmKey,
      tr('Confirm stand up', '确认站起'),
      () => unawaited(_posture('stand')));

  List<Widget> _settingsTab(NwColors c, SiteSession? s, Map<String, dynamic>? v, Future<void> Function(Widget Function()) go) {
    final dispatch = s?.canDispatch ?? false;
    final maps = s?.canManageMaps ?? false;
    final manage = s?.canManageRobots ?? false;
    final manual = v?['manual_only'] is Map;
    final caps = v?['capabilities'] is Map ? (v!['capabilities'] as Map).cast<String, dynamic>() : null;
    final deter = caps?['tasks'] is Map ? (caps!['tasks'] as Map)['deter'] : null;
    final outs = deter is Map ? (deter['outputs'] as List? ?? const []).map((e) => deterOutputs['$e']?.$1 ?? '$e').toList() : <String>[];
    final skew = v?['clock_skew_s'];
    final expires = v?['expires_at'];
    String day(Object? x) {
      if (x is! num) return '$x';
      final d = DateTime.fromMillisecondsSinceEpoch((x < 1e12 ? x * 1000 : x).toInt());
      return '${d.year}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}';
    }

    Widget check(bool ok, String text, {Key? key}) => Padding(
        key: key,
        padding: const EdgeInsets.symmetric(vertical: 6),
        child: Row(children: [
          ok
              ? Container(width: 10, height: 10, color: c.success)
              : Icon(Icons.warning_rounded, size: 14, color: c.warning),
          const SizedBox(width: 10),
          Expanded(child: Text(text, style: NwText.bodyMedium.copyWith(color: c.text))),
        ]));
    final maint = <Widget>[
      if ((s?.canSeeHealth ?? false) && robotCan(v, 'ops_diag'))
        nwOpButton(c, const Key('btn-robot-ops'), tr('Remote maintenance', '远程运维'),
            () => go(() => RobotOpsPage(
                api: widget.api,
                robotId: widget.robotId,
                tasks: ((v?['capabilities'] as Map?)?['tasks'] as Map?)?.keys.map((k) => '$k').toSet() ?? const <String>{}))),
      if (maps && robotCan(v, 'proc_log'))
        nwOpButton(c, const Key('btn-proc-logs'), tr('Mapping logs', '建图日志'),
            () => go(() => SiteProcLogsPage(api: widget.api, robotId: widget.robotId))),
      if (maps && robotCan(v, 'mapping')) ...[
        nwOpButton(c, const Key('btn-record-start'), tr('Start bag recording', '开始录包'), _startRecord),
        nwOpButton(c, const Key('btn-record-stop'), tr('Stop bag recording', '停止录包'),
            () => _do(() => widget.api.mapping(widget.robotId, 'stop'), tr('Stop bag recording', '停止录包'))),
      ],
      if (maps && robotCan(v, 'mapping_trail'))
        nwOpButton(c, const Key('btn-mapping-trail'), tr('Bag recording trail', '录包轨迹'), _openTrail),
    ];
    return [
      nwRobotSection(c, tr('General', '基本'), key: const Key('robot-general'), [
        _row(c, tr('Name', '名字'), v?['name'] is String && '${v!['name']}'.isNotEmpty ? '${v['name']}' : widget.robotId,
            action: manage ? _small(c, SiteRobotPage.renameKey, tr('Edit', '改'), () {
              _name.text = '${v?['name'] ?? ''}';
              setState(() => _ask = 'name');
            }) : null),
        if (_ask == 'name')
          Padding(
              padding: const EdgeInsets.only(bottom: Nw.s8),
              child: Row(children: [
                Expanded(
                    child: TextField(
                        key: SiteRobotPage.nameFieldKey,
                        controller: _name,
                        maxLength: 40,
                        decoration: InputDecoration(counterText: '', hintText: tr('Display name', '显示名')))),
                const SizedBox(width: Nw.s8),
                _small(c, SiteRobotPage.nameSaveKey, tr('Save', '保存'), () => unawaited(_rename())),
              ])),
        _row(c, tr('Dispatch mode', '派遣方式'),
            manual ? tr('Manual dispatch only', '只许手动派') : tr('Scheduled and manual dispatch', '日程和手动都派'),
            action: (manual ? manage : dispatch)
                ? _small(c, SiteRobotPage.manualKey, manual ? tr('Allow automatic', '接回自动') : tr('Manual only', '只许手动'),
                    () => unawaited(_manual(!manual)))
                : null),
        if (v?['wifi'] is Map)
          _row(c, tr('Network', '网络'), robotWifiLine(v!['wifi'] as Map),
              key: const Key('robot-wifi'),
              action: manage && robotCan(v, 'wifi_confirm')
                  ? _small(c, const Key('btn-change-wifi'), tr('Change Wi-Fi', '换 Wi-Fi'),
                      () => go(() => RobotWifiPage(api: widget.api, robotId: widget.robotId)))
                  : null),
        if (outs.isNotEmpty) _row(c, tr('Payload', '上装'), outs.join(tr(', ', '、'))),
      ]),
      nwRobotSection(c, tr('Position', '位置'), key: const Key('robot-position'), [
        if (maps && robotCan(v, 'mark_home'))
          _row(c, tr('Origin', '原点'), v?['home_set'] == true ? tr('Set', '已标') : tr('Not set', '没标'),
              action: _small(c, const Key('btn-mark-home'), tr('Set here', '在这儿标'), _markHome)),
        if (dispatch || maps)
          _row(c, tr('Standby point', '待命点'), tr('Where it waits between tasks', '没任务时在哪等'),
              action: _small(c, const Key('btn-standby-list'), tr('Edit', '改'),
                  () => go(() => SiteStandbyPage(api: widget.api, robotId: widget.robotId, canMarkHere: robotCanStandbyHere(v))))),
        if (dispatch && robotCan(v, 'relocalize'))
          _row(c, tr('Set position', '设位置'), tr('If localization is off, tap its position on the map', '定位不对时，在地图上点它在哪'),
              action: _small(c, const Key('btn-set-position'), tr('Open map', '打开地图'), _relocalize)),
        if (v?['rtk'] is Map)
          _row(c, 'RTK', rtkText((v!['rtk'] as Map).cast<String, dynamic>()), key: const Key('robot-rtk')),
      ]),
      nwRobotSection(c, tr('Checklist', '检查'), key: const Key('robot-checklist'), [
        if (expires != null) check(true, tr('Certificate · expires ${day(expires)}', '证书 · ${day(expires)} 到期')),
        if (skew is num)
          check(skew.abs() < 2,
              skew.abs() < 2 ? tr('Time sync', '时间同步') : tr('Clock off by ${skew.toStringAsFixed(1)} s', '时钟差 ${skew.toStringAsFixed(1)} 秒')),
        if (caps != null && headText(caps).isNotEmpty) check(false, headText(caps), key: const Key('robot-head')),
        if (caps != null && obstaclesText(caps).isNotEmpty) check(true, obstaclesText(caps), key: const Key('robot-obstacles')),
        // W40：设备健康（每台在线 / 离线 / 降级 / 故障）
        if (v?['devices'] is Map && (v!['devices'] as Map)['items'] is List && ((v['devices'] as Map)['items'] as List).isNotEmpty)
          _Devices(view: (v['devices'] as Map).cast<String, dynamic>()),
      ]),
      if (maint.isNotEmpty)
        nwRobotSection(c, tr('Troubleshooting & maintenance', '排查与维护'), key: const Key('robot-maint'), [nwButtonRows(maint, per: 2)]),
      if (s?.canManageAccounts ?? false)
        nwRobotSection(c, tr('Unbind', '解绑'), key: const Key('robot-unbind'),
            note: tr('Unbinding removes the robot from the site and requires your password. Recordings are retained.',
                '解绑把机器人从站点移除，要再输一次你的密码。录像保留。'), [
          if (_ask != 'unbind')
            OutlinedButton(
                key: SiteRobotPage.unbindKey,
                style: OutlinedButton.styleFrom(
                    foregroundColor: c.error,
                    side: BorderSide(color: c.error),
                    minimumSize: const Size(48, 48),
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(2))),
                onPressed: () => setState(() => _ask = 'unbind'),
                child: Text(tr('Unbind ${widget.robotId}…', '解绑 ${widget.robotId}…')))
          else ...[
            TextField(
                key: SiteRobotPage.unbindPwKey,
                controller: _pw,
                obscureText: true,
                decoration: InputDecoration(labelText: tr('Your password', '你的密码'))),
            const SizedBox(height: Nw.s8),
            nwButtonRows([
              FilledButton(
                  key: SiteRobotPage.unbindGoKey,
                  style: FilledButton.styleFrom(
                      backgroundColor: c.error,
                      foregroundColor: c.onError,
                      minimumSize: const Size(48, 48),
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(2))),
                  onPressed: () => unawaited(_unbind()),
                  child: Text(tr('Unbind', '解绑'))),
              nwOpButton(c, const Key('robot-unbind-cancel'), tr('Cancel', '取消'), () {
                _pw.clear();
                setState(() => _ask = null);
              }),
            ], per: 2),
          ],
        ]),
    ];
  }
}

Widget? _eventSub(Map e) {
  final d = e['data'];
  final text = robotEventDetail('${e['kind']}', d is Map ? d.cast<String, dynamic>() : const <String, dynamic>{});
  return text.isEmpty ? null : Text(text, maxLines: 2, overflow: TextOverflow.ellipsis);
}

/// 设备健康（W40）：一台一行，圆点按状态上色；不在线的排前面；好一会儿没更新整块标出来。
class _Devices extends StatelessWidget {
  final Map<String, dynamic> view;
  const _Devices({required this.view});

  static const Key listKey = Key('robot-devices');

  @override
  Widget build(BuildContext context) {
    final c = Nw.of(context);
    const order = <String, int>{'error': 0, 'offline': 1, 'degraded': 2, 'online': 3};
    final items = <Map<String, dynamic>>[
      for (final x in (view['items'] as List)) if (x is Map) x.cast<String, dynamic>(),
    ]..sort((a, b) => (order['${a['state']}'] ?? 9).compareTo(order['${b['state']}'] ?? 9));
    Color dot(String st) => switch (st) {
          'online' => c.success,
          'degraded' => c.warning,
          _ => c.error,
        };
    return Column(key: listKey, crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text(
          view['stale'] == true
              ? tr('Devices (stale)', '设备（长时间未更新）')
              : tr('Devices', '设备'),
          style: NwText.titleSmall.copyWith(color: view['stale'] == true ? c.warning : c.text)),
      for (final d in items)
        Padding(
            padding: const EdgeInsets.only(top: 2),
            child: Row(key: Key('device-${d['id']}'), crossAxisAlignment: CrossAxisAlignment.start, children: [
              Padding(
                  padding: const EdgeInsets.only(top: 5, right: Nw.s8),
                  child: Icon(Icons.circle, size: 10, color: dot('${d['state']}'))),
              Expanded(
                  child: Text(
                      // 第 10 轮 W9-10：站点原话走 siteText（中文全角，英文界面翻）
                      '${deviceHead('${d['id']}', '${d['state']}', '${d['detail'] ?? ''}')}'
                      '${'${d['detail'] ?? ''}'.isEmpty ? '' : ' · ${siteText('${d['detail']}')}'}',
                      style: NwText.bodyMedium.copyWith(color: c.text))),
            ])),
    ]);
  }
}

/// 姿态的叫法（POC）。
/// A7-01：机器人页的「站起」和它的确认。
const standUpKey = Key('btn-stand-up');

/// 机器人页开着时多久重读一次（姿态、任务、电量）。
const kRobotPageRefresh = Duration(seconds: 5);
const standUpConfirmKey = Key('stand-up-confirm');

String postureLabel(String mode) => switch (mode) {
      'stand' => tr('Stand up', '站起'),
      'lie' => tr('Lie down', '趴下'),
      'crawl' => tr('Crouch', '蹲下'),
      _ => mode,
    };

IconData postureIcon(String mode) => switch (mode) {
      'stand' => Icons.arrow_upward_rounded,
      'lie' => Icons.airline_seat_flat_rounded,
      _ => Icons.arrow_downward_rounded,
    };
