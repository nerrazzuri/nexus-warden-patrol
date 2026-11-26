/// 告警页（App V2，视觉规范 2.5；前身是 W17 的「告警现场」）：一条告警的处理都在这一页 ——
/// 报警头（优先级、标题、没确认多久）、实时画面（手机一次只拉一路，前后可切）、在哪、四个大按钮
/// （我来处理 / 警笛 / 误报 / 对讲还没有）、现场细节（防区、拦截点、狗在哪、那一趟）、事件经过。
///
/// 只有**没确认的 P1** 闪框；确认了框稳住、头条换成谁在什么时候确认的。
///
/// 现场是站点记在告警上的（`context`）：狗最后一次报的地图位姿与收到的时刻、正在跑的那一趟、入侵的
/// 防区与拦截点。老站点不发：细节那一段只剩一句话。
///
/// 2026-10-14 重做（设计稿的 AlarmIncidentDetail）：四个大按钮和按了之后的那句话挪到**底栏**
/// （拇指够得着、不跟着滚）；「在哪」、细节是一张卡，事件经过是一张卡；有位置的告警多一张小地图
/// （站点渲染的那张栅格图，点了进地图）。状态、防迟到回包的那些一个字没动。
///
/// W60（用户 2026-10-31 定）：以现场为先 —— 报警头下面先放现场照片（那一趟拍的第一张，点开看全部），
/// 再是实时画面；没有照片就不占地方。
library;

import 'dart:async';
import 'dart:typed_data';

import 'package:flutter/material.dart';

import '../design/tokens.g.dart' show D1Motion;
import '../l10n.dart';
import '../model/alert.dart';
import '../net/site_client.dart';
import '../net/map_names.dart';
import '../net/site_text.dart';
import 'map_view.dart' show loadMapPicture;
import 'nw/nw_p2_duty.dart';
import 'nw/nw_estop_miss.dart';
import 'nw/nw_theme.dart';
import 'nw/nw_shell.dart' show EstopSquare;
import 'site_tabs.dart' show AccountsPage;
import 'site_mapping.dart';
import 'site_deter.dart' show deterAckFailure, deterQuietFirst;
import 'site_deterrence.dart' show deterSessionText;
import 'site_recordings.dart';
import 'site_runs.dart';
import 'site_video.dart';
import 'widget/alarm_widgets.dart';
import '../net/person_names.dart';

/// 真机 11-25：哪台相机看到的人（用户分不清是前面还是后面）。没报是空串。
String seenByText(Map<String, dynamic> ctx) {
  final p = ctx['persons'];
  final cams = p is Map ? p['cams'] : null;
  if (cams is! List || cams.isEmpty) return '';
  final names = [
    for (final c in cams)
      c == 'front' ? tr('front', '前') : c == 'back' ? tr('rear', '后') : '$c',
  ];
  return tr('seen by the ${names.join(' and ')} camera', '${names.join('、')}相机看到的');
}

/// 跟随一行：「A 正在跟随，距离 4.6 米」/「看不到人了」。
String followLine(Alert a) {
  final f = a.context['follow'];
  if (f == 'follow') return tr('${a.robot} following', '${a.robot} 正在跟随');
  // 易用性 build 36 P2-13：不会跟人的机器人停着看，说一句
  if (f == 'unsupported') {
    return tr("${a.robot} can't follow people: it stays where it is and keeps watching", '${a.robot} 不能跟人，原地看着');
  }
  // 真机 11-25：用户看不出它为什么往后退、为什么站着不动
  if (f == 'retreat') return tr('Person too close: ${a.robot} is backing away', '人太近，${a.robot} 在往后退');
  if (f == 'cornered') {
    return tr("Person too close and something is behind ${a.robot}: it can't back away, standing still",
        '人太近，${a.robot} 身后有东西退不了，原地站定');
  }
  if (a.context['follow_left'] == true) {
    return tr('Person left the zone: ${a.robot} stopped following', '人离开了防区，${a.robot} 不再跟');
  }
  if (f == 'lost' || f == 'limit' || a.context['lost_ms'] is num) return tr('Person no longer seen', '看不到人了');
  return '';
}

class SiteAlertScenePage extends StatefulWidget {
  final SiteApi api;
  final Alert alert;
  final DateTime Function() now;
  const SiteAlertScenePage({super.key, required this.api, required this.alert, this.now = DateTime.now});

  static const Key mapKey = Key('scene-map');
  static const Key photoKey = Key('scene-photo');
  static const Key msgKey = Key('scene-msg');
  static const Key videoKey = Key('scene-video');
  static const Key deterKey = Key('scene-deter-here');
  static const Key ackKey = Key('scene-ack');
  static const Key whyKey = Key('scene-why');
  static const Key accountsKey = Key('scene-accounts');
  static const Key arriveKey = Key('scene-arrive');
  static const Key doneKey = Key('scene-done');
  static const Key doneGoKey = Key('scene-done-go');
  static const Key sirenKey = Key('scene-siren');
  static const Key falseKey = Key('scene-false');
  static const Key falseGoKey = Key('scene-false-go');
  static const Key headKey = Key('scene-head');
  static const Key stateKey = Key('scene-state');
  static const Key nextKey = Key('scene-next');
  static const Key staleKey = Key('scene-deter-stale');

  /// 底栏：四个大按钮和按了之后的那句话。
  static const Key barKey = Key('scene-bar');
  static const Key stepsKey = Key('scene-steps');
  static const Key situationKey = Key('scene-situation');
  static const Key warnKey = Key('scene-warn');
  static const Key speakKey = Key('scene-speak');
  static const Key strobeKey = Key('scene-strobe');
  static const Key allOffKey = Key('scene-all-off');
  static const Key endDeterKey = Key('scene-end-deter');
  static const Key deterLevelKey = Key('scene-deter-level');
  static const Key notifyKey = Key('scene-notify');
  static const Key backupKey = Key('scene-backup');
  static const Key backupDoneKey = Key('scene-backup-done');
  static const Key verdictKey = Key('scene-verdict');
  static const Key intruderKey = Key('scene-v-intruder');
  static const Key handledKey = Key('scene-v-handled');
  static const Key noteKey = Key('scene-note');
  static const Key closedKey = Key('scene-closed');
  static const Key reopenKey = Key('scene-reopen');
  static const Key timelineKey = Key('scene-timeline');
  static const Key estopKey = Key('scene-estop');

  @override
  State<SiteAlertScenePage> createState() => _SiteAlertScenePageState();
}

/// 告警现场里要在图上标的点：狗（红）、拦截点（紫）。没有位姿的不标；图不是同一张的（拦截点与狗报的
/// 不是一张图）各算各的。回 `(图 id, 版本, 点)`；一个都没有回 null。
(String, String, List<MapMark>)? sceneMarks(Alert a) {
  final ctx = a.context;
  final pose = ctx['last_seen'] ?? ctx['pose']; // W74：最后看见人时机器人在哪（每 5 秒更新）
  final point = ctx['intercept'];
  String? mapId;
  String? version;
  final marks = <MapMark>[];
  void add(Object? p, String label, Color color) {
    if (p is! Map || p['x'] is! num || p['y'] is! num) return;
    final m = '${p['map_id'] ?? ''}';
    final v = '${p['map_version'] ?? ''}';
    if (m.isEmpty || v.isEmpty) return;
    if (mapId != null && (m != mapId || v != version)) return; // 别的图上的：不往这张图上画
    mapId = m;
    version = v;
    marks.add(MapMark(label, (p['x'] as num).toDouble(), (p['y'] as num).toDouble(), color));
  }

  add(pose, a.robot == 'site' ? tr('Robot', '机器人') : tr('Robot ${a.robot}', '机器人 ${a.robot}'), Colors.red);
  // W74 二期：人最后在哪（机器人跟人时算的，跟机器人同一张图）
  final person = ctx['person'];
  if (person is Map && mapId != null) {
    add(
      <String, dynamic>{'map_id': mapId, 'map_version': version, ...person.cast<String, dynamic>()},
      tr('Person last seen', '人最后在这'),
      Colors.orange,
    );
  }
  if (point is Map) {
    add(point, tr('Intercept point ${point['name'] ?? ''}', '拦截点 ${point['name'] ?? ''}'), Colors.purple);
  }
  if (marks.isEmpty) return null;
  return (mapId!, version!, marks);
}

/// 一场驱离里警笛的状态：狗接受了、要求了还没确认、没要求、这台狗没装、说不清。
enum SirenState { on, requested, off, notFitted, unknown }

/// 警笛在第几级、一场驱离里警笛现在算什么状态（C-B2 外审 I1）。
abstract final class SiteAlertScenePageSiren {
  /// 警笛在第 3 级（站点 `deterrence.RELAYS`）；第 2 级只有灯和语音警告。
  static const int level = 3;

  /// `on` 只在狗**接受了**开警笛的命令时才算（站点回的 `active`）：级别到了只是要求，不等于响了。
  /// 老站点不发 `active` / `outputs`：到了级别也只算「要求了」。
  static SirenState of(Map<String, dynamic>? d) {
    if (d == null) return SirenState.unknown;
    final outputs = d['outputs'], active = d['active'], lv = d['level'];
    if (outputs is List && !outputs.contains('siren')) return SirenState.notFitted;
    if (active is List && active.contains('siren')) return SirenState.on;
    return lv is num && lv >= level ? SirenState.requested : SirenState.off;
  }
}

/// 过了多久：`0:42`、`12:05`、`1:02:03`。负数（两头的钟差一点）当 0。
abstract final class SiteAlertScenePageSpan {
  static String of(int ms) {
    final s = ms < 0 ? 0 : ms ~/ 1000;
    final h = s ~/ 3600, m = (s % 3600) ~/ 60;
    String two(int n) => n.toString().padLeft(2, '0');
    return h > 0 ? '$h:${two(m)}:${two(s % 60)}' : '$m:${two(s % 60)}';
  }
}

class _SiteAlertScenePageState extends State<SiteAlertScenePage> with EstopMissReveal {
  late Alert _a = widget.alert;

  /// 在这一页点了「我来处理」之后站点回的（或者本地记的）确认人、时刻；刷新拿到新的告警就用新的。
  (String, int)? _ackedHere;

  /// 最后一次**问到**的驱离（这台狗没在驱离就是 null）。它只是一张快照：[_deterFresh] 不成立时
  /// （上一次没问到，或者太久没问到）不能当成现在的声光状态，见 [_d]（C-B2 外审 I2）。
  Map<String, dynamic>? _deter;
  bool _deterKnown = false;

  /// 问到 [_deter] 那一刻：第几拍（判新鲜用，不靠墙上的钟）、几点（给人看）。
  int _deterTick = 0;
  int _deterAtMs = 0;

  /// 隔这么多拍还没再问到，就算旧的（一拍 800 ms、每 4 拍问一次：连着三次没回来）。
  static const int _freshTicks = 12;

  /// 这一页现在是第几条告警：换了一条就加一。在途的请求回来时对不上就不许动页面（外审 I3）。
  int _gen = 0;

  /// 向站点问的编号：回来得比已经用上的还旧就丢掉（先发的后到）。
  int _asked = 0;
  int _alertApplied = 0;
  int _deterApplied = 0;

  String _msg = '';
  bool _dim = false;
  /// 易用性 build 37 复测：站点没配推送还写「已推送到所有手机」—— 问一次站点（问不到当配了，照旧写）。
  // 易用性 37 复测：null = 还没问到（满载、网慢）—— 不说「已推送」也不说「没配」
  bool? _pushOff;
  int _ticks = 0;
  Timer? _timer;

  bool get _deterFresh => _deterKnown && _ticks - _deterTick <= _freshTicks;

  /// **现在**的驱离：只有新鲜的才算；旧快照、没问到都是 null。
  Map<String, dynamic>? get _d => _deterFresh ? _deter : null;

  bool get _isRobot => _a.robot != 'site' && _a.robot.isNotEmpty;
  bool get _acked => _a.ackedMs != null || _ackedHere != null;
  bool get _open => _a.resolvedMs == null;

  /// W74：看见人那一类要保安点过「已到场」才能处置完成 / 标误报（站点也这么拦）。
  bool get _needsArrive => _a.kind == 'dog_sees_person';

  /// 手机 App 测试 M04：「误报」只给可能误报的（有人闯入、起火类，和几种传感器判断）；机器人故障、
  /// 派单被拒、掉线、账号申请这些是真事，只给「已处理」，不然误报统计就乱了。
  bool get _canBeFalse => alertCanBeFalse(_a);
  (String, int)? _arrivedHere;
  bool get _arrived => _a.context['arrived_ms'] != null || _arrivedHere != null;
  bool get _flashing => _a.level == 'P1' && _open && !_acked;

  Future<void> _checkPush() async {
    try {
      final s = await widget.api.watchSummary();
      final site = s['site'];
      if (site is! Map || !site.containsKey('push')) return; // 老站点不报：照旧写
      final push = site['push'];
      final off = push == null || (push is Map && push['configured'] != true);
      if (mounted && off != _pushOff) setState(() => _pushOff = off);
    } catch (_) {}
  }

  @override
  void initState() {
    super.initState();
    unawaited(_refresh());
    unawaited(_checkPush());
    // 一个钟管三件事：没确认多久（每拍重画）、闪框（半个周期翻一次）、隔几拍向站点再问一遍。
    _timer = Timer.periodic(const Duration(milliseconds: D1Motion.p1FlashMs ~/ 2), (_) {
      if (!mounted) return;
      _ticks++;
      if (_ticks % 4 == 0) unawaited(_refresh());
      if (_deterKnown && _ticks - _deterTick == _freshTicks + 1) setState(() {}); // 刚变旧：重画
      if (_flashing) {
        setState(() => _dim = !_dim);
      } else if (_dim) {
        setState(() => _dim = false);
      }
    });
  }

  @override
  void didUpdateWidget(SiteAlertScenePage old) {
    super.didUpdateWidget(old);
    if (identical(old.alert, widget.alert) && identical(old.api, widget.api)) return;
    final same = old.alert.key == widget.alert.key && identical(old.api, widget.api);
    _a = widget.alert;
    if (!same) {
      // 同一个位置换了一条告警：这一页记的东西是上一条的，全部重来；上一条还在路上的请求、还开着的
      // 「记成误报？」都作废（外审 I3）
      _gen++;
      _ackedHere = null;
      _arrivedHere = null;
      _deter = null;
      _deterKnown = false;
      _msg = '';
      _dim = false;
      _verdict = null;
      _note.clear();
      _closedHere = null;
      _backupHere = null;
      _caps = null;
    }
    unawaited(_refresh());
  }

  /// 记下刚问到的驱离（[s] 是 null = 这台狗没在驱离）。在它之前发出去的查询回来了也不许盖掉它。
  void _gotDeter(Map<String, dynamic>? s) {
    _deter = s;
    _deterKnown = true;
    _deterTick = _ticks;
    _deterAtMs = widget.now().millisecondsSinceEpoch;
    _deterApplied = ++_asked;
  }

  @override
  void dispose() {
    _timer?.cancel();
    _note.dispose();
    super.dispose();
  }

  /// 向站点再问一遍：这条告警现在什么样（别人可能确认了、解决了）、这台狗有没有在驱离。
  /// 告警没问到就留着旧的。驱离没问到记成「说不清」：旧快照留着给人看「最后问到时」，但不当成现在的。
  /// 发出去之后这一页换了告警、或者更新的结果已经用上了：这一次的结果丢掉。
  Future<void> _refresh() async {
    final gen = _gen, key = _a.key, robot = _a.robot, isRobot = _isRobot;
    final seq = ++_asked;
    bool current() => mounted && gen == _gen;
    try {
      final now = (await widget.api.alerts(all: true)).where((x) => x.key == key);
      if (!current()) return;
      if (now.isNotEmpty && seq > _alertApplied) {
        _alertApplied = seq;
        setState(() => _a = now.first);
      }
    } on Object {
      if (!current()) return; // 留着旧的
    }
    if (!isRobot) return;
    if (_caps == null) {
      // 这台机器人有哪几路上装（喊话、警灯、警笛）：只问一次
      try {
        final v = await widget.api.robot(robot);
        if (!current()) return;
        final d = (((v['capabilities'] as Map?)?['tasks'] as Map?)?['deter']);
        setState(() => _caps = d is Map ? Map<String, dynamic>.from(d) : const <String, dynamic>{});
      } on Object {
        if (!current()) return;
      }
    }
    try {
      final rows = await widget.api.deterrence();
      if (!current() || seq <= _deterApplied) return;
      final mine = rows.where((r) => r['robot_id'] == robot);
      setState(() {
        _deter = mine.isEmpty ? null : mine.first;
        _deterKnown = true;
        _deterTick = _ticks;
        _deterAtMs = widget.now().millisecondsSinceEpoch;
        _deterApplied = seq;
      });
    } on Object {
      if (!current() || seq <= _deterApplied) return;
      setState(() {
        _deterKnown = false;
        _deterApplied = seq;
      });
    }
  }

  Future<void> _ack() async {
    final gen = _gen, key = _a.key;
    try {
      final r = await widget.api.ackAlert(key);
      if (!mounted || gen != _gen) return; // 这一页已经是另一条告警了：上一条的回包不许动它
      final got = r['alert'] is Map ? Alert.fromWire(Map<String, dynamic>.from(r['alert'] as Map)) : null;
      if (got != null && got.key != key) {
        // 站点明说回的是另一条：不能当成这一条确认上了
        setState(
          () => _msg = tr(
            "Not acknowledged: the site returned a different alarm (${got.key})",
            '确认失败：站点返回的是另一条报警（${got.key}）',
          ),
        );
        return;
      }
      // 易用性 37 第十二轮 P3：自己接了，外面那条「（无人确认）」提示条马上收起（不等事件流）
      ScaffoldMessenger.maybeOf(context)?.hideCurrentSnackBar();
      // 站点回了确认之后的这一条：谁、几点以站点记的为准。老站点不回正文：先在本地记成「我、现在」，
      // 下一次刷新拿到站点的再换。
      setState(() {
        if (got != null && got.ackedMs != null) {
          _a = got;
          _ackedHere = (got.ackedBy, got.ackedMs!);
        } else {
          _ackedHere = (widget.api.session?.name ?? '', widget.now().millisecondsSinceEpoch);
        }
        _msg = '';
      });
    } on SiteError catch (e) {
      if (mounted && gen == _gen) setState(() => _msg = tr('Not acknowledged: $e', '确认失败：$e'));
    }
  }

  static const int sirenLevel = SiteAlertScenePageSiren.level;
  static SirenState sirenState(Map<String, dynamic>? d) => SiteAlertScenePageSiren.of(d);

  Future<void> _siren() async {
    final gen = _gen, robot = _a.robot;
    try {
      final r = await widget.api.deterLevel(robot, sirenLevel);
      if (!mounted || gen != _gen) return;
      final s = r['session'] is Map ? Map<String, dynamic>.from(r['session'] as Map) : null;
      setState(() {
        if (s != null) _gotDeter(s);
        _msg = switch (sirenState(s)) {
          SirenState.on => '',
          SirenState.notFitted => tr(
            'Level $sirenLevel is set, but this robot has no siren.',
            '已到第 $sirenLevel 级，但此机器人没有警笛。',
          ),
          _ => tr(
            'Level $sirenLevel requested. Waiting for the robot to confirm the siren.',
            '已请求第 $sirenLevel 级，机器人尚未确认警笛开启。',
          ),
        };
      });
    } on SiteError catch (e) {
      if (mounted && gen == _gen) setState(() => _msg = tr("Siren didn't start: $e", '警笛开启失败：$e'));
    }
  }

  Future<void> _arrive() async {
    final gen = _gen, key = _a.key;
    try {
      final r = await widget.api.arriveAlert(key);
      if (!mounted || gen != _gen) return;
      final got = r['alert'] is Map ? Alert.fromWire(Map<String, dynamic>.from(r['alert'] as Map)) : null;
      setState(() {
        if (got != null && got.key == key) {
          _a = got;
        } else {
          _arrivedHere = (widget.api.session?.name ?? '', widget.now().millisecondsSinceEpoch);
        }
        _msg = '';
      });
    } on SiteError catch (e) {
      if (mounted && gen == _gen) setState(() => _msg = tr('Not recorded: $e', '到场没记上：$e'));
    }
  }

  /// 结论（跟网页一样）：入侵、起火给三种，别的给「已处理 / 误报」；不能误报的（机器人故障、派单被拒……
  /// 是真事，手机 App 测试 M04）只给「已处理」。
  List<String> get _verdicts {
    final sec = _a.audience == 'intrusion' || _a.audience == 'fire';
    final all = sec ? const ['intruder', 'false_alarm', 'handled'] : const ['handled', 'false_alarm'];
    return [
      for (final v in all)
        if (v != 'false_alarm' || _canBeFalse) v,
    ];
  }

  static String verdictWord(String v) => switch (v) {
    // 易用性 37 场景测试：两边、各页同一个说法
    'intruder' => tr('Confirmed intrusion', '确认入侵'),
    'false_alarm' => tr('False alarm', '误报'),
    'handled' => tr('Resolved', '已处理'),
    _ => tr('Closed', '已关闭'),
  };

  /// 选了结论、写了备注，点「结案」才关（App V2 不弹窗：结论这一段就是确认）。
  String? _verdict;
  final TextEditingController _note = TextEditingController();
  bool _busy = false;

  Future<void> _close() async {
    final gen = _gen, key = _a.key, verdict = _verdict;
    if (verdict == null || _busy) return;
    setState(() => _busy = true);
    try {
      final r = await widget.api.resolveAlert(key, verdict: verdict, note: _note.text);
      if (!mounted || gen != _gen) return;
      final got = r['alert'] is Map ? Alert.fromWire(Map<String, dynamic>.from(r['alert'] as Map)) : null;
      setState(() {
        if (got != null && got.key == key) _a = got;
        _closedHere = widget.now().millisecondsSinceEpoch;
        _msg = tr('Alarm closed. You can reopen it within 10 minutes.', '报警已关闭。10 分钟内可以重新打开。');
      });
    } on SiteError catch (e) {
      if (mounted && gen == _gen) setState(() => _msg = tr('Not closed: $e', '关闭失败：$e'));
    } finally {
      if (mounted && gen == _gen) setState(() => _busy = false);
    }
  }

  /// 这一页上刚结的案（站点回包里没有关的时刻时，按本机时刻算撤销的 10 分钟）。
  int? _closedHere;
  static const int reopenMs = 10 * 60 * 1000;

  bool get _canReopen {
    final at = _a.resolvedMs ?? _closedHere;
    if (at == null || _open && _closedHere == null) return false;
    final by = _a.resolvedBy;
    final auto =
        _a.verdict.isEmpty &&
        (by == 'system' ||
            by.startsWith('site:') ||
            by.startsWith('\u7ad9\u70b9:') ||
            by.startsWith('\u7ad9\u70b9\uff1a'));
    return !auto && widget.now().millisecondsSinceEpoch - at < reopenMs;
  }

  Future<void> _reopen() async {
    final gen = _gen, key = _a.key;
    try {
      final r = await widget.api.reopenAlert(key);
      if (!mounted || gen != _gen) return;
      final got = r['alert'] is Map ? Alert.fromWire(Map<String, dynamic>.from(r['alert'] as Map)) : null;
      setState(() {
        if (got != null && got.key == key) _a = got;
        _closedHere = null;
        _verdict = null;
        _msg = tr('Alarm reopened.', '报警已重新打开。');
      });
      unawaited(_refresh());
    } on SiteError catch (e) {
      if (mounted && gen == _gen) setState(() => _msg = tr('Not reopened: $e', '没能重新打开：$e'));
    }
  }

  Future<void> _backup() async {
    final gen = _gen, key = _a.key;
    try {
      final r = await widget.api.backupAlert(key);
      if (!mounted || gen != _gen) return;
      final got = r['alert'] is Map ? Alert.fromWire(Map<String, dynamic>.from(r['alert'] as Map)) : null;
      setState(() {
        if (got != null && got.key == key) _a = got;
        _backupHere ??= (widget.api.session?.name ?? '', widget.now().millisecondsSinceEpoch);
        _msg = tr('Backup requested; managers and administrators notified.', '已请求支援，经理和管理员已收到推送。');
      });
    } on SiteError catch (e) {
      if (mounted && gen == _gen) setState(() => _msg = tr('Backup not requested: $e', '没能请求支援：$e'));
    }
  }

  (String, int)? _backupHere;

  /// 这台机器人报的上装（`capabilities.tasks.deter`）：有哪几路、预录话术、能不能念字。
  Map<String, dynamic>? _caps;
  List<String> get _outputs => ((_caps?['outputs'] as List?) ?? const []).map((e) => '$e').toList();

  /// 现场警示：开一路（喊话、警灯、警笛），带时长、到点机器人自己关。
  Future<void> _warn(String output, {double? maxS, String? clip}) async {
    final gen = _gen, robot = _a.robot;
    try {
      final why = deterAckFailure(await widget.api.deter(robot, output, true, maxS: maxS, clip: clip, alert: _a.key));
      if (!mounted || gen != _gen) return;
      if (why != null) {
        setState(() => _msg = tr('Not done: $why', '没执行：$why'));
        return;
      }
      setState(
        () => _msg = switch (output) {
          'speaker' => tr('$robot: announcing.', '$robot 在喊话。'),
          'strobe' => tr('$robot: strobe on for ${maxS?.round() ?? 30} s.', '$robot 警灯开 ${maxS?.round() ?? 30} 秒。'),
          _ => tr('$robot: siren on for ${maxS?.round() ?? 10} s.', '$robot 警笛响 ${maxS?.round() ?? 10} 秒。'),
        },
      );
    } on SiteError catch (e) {
      if (mounted && gen == _gen) setState(() => _msg = tr('Not done: $e', '没执行：$e'));
    }
  }

  /// 「全部关」：这台机器人上开着的警示一路路关掉。
  Future<void> _allOff() async {
    final gen = _gen, robot = _a.robot;
    final fails = <String>[];
    // 外审 App-V2-3 I7：还在驱离先退到 L0（不然站点下一拍又把声光打开）；跟按钮用同一套「有哪几路」
    final quiet = await deterQuietFirst(widget.api, robot);
    if (!mounted || gen != _gen) return;
    if (quiet != null) fails.add(quiet);
    final outs = (_outputs.isNotEmpty ? _outputs : ((_d?['outputs'] as List?) ?? const []).map((e) => '$e').toList())
        .where((o) => const {'speaker', 'strobe', 'siren', 'spotlight'}.contains(o))
        .toList();
    if (outs.isEmpty) {
      setState(() => _msg = tr("Don't know which outputs $robot has; nothing was turned off.", '不知道 $robot 装了哪几路，没关任何一路。'));
      return;
    }
    for (final o in outs) {
      try {
        if (deterAckFailure(await widget.api.deter(robot, o, false)) != null) fails.add(o);
      } on SiteError {
        fails.add(o);
      }
      if (!mounted || gen != _gen) return;
    }
    setState(
      () => _msg = fails.isEmpty
          ? tr('$robot: all warnings off.', '$robot 警示全部关了。')
          : tr('Some outputs did not turn off: ${fails.join(', ')}', '有几路没关上：${fails.join('、')}'),
    );
  }

  /// 「结束驱离」：站点那一场解除，警示全关、机器人回待命点。
  Future<void> _endDeter() async {
    final gen = _gen, robot = _a.robot;
    try {
      await widget.api.deterRelease(robot);
      if (!mounted || gen != _gen) return;
      setState(() {
        _gotDeter(null);
        _msg = tr('Deterrence ended on $robot; it returns to standby.', '$robot 结束驱离，回待命点。');
      });
    } on SiteError catch (e) {
      if (mounted && gen == _gen) setState(() => _msg = tr('Deterrence not ended: $e', '没能结束驱离：$e'));
    }
  }

  Future<void> _photo(String taskId) async {
    final gen = _gen;
    List<Map<String, dynamic>> runs;
    try {
      runs = await widget.api.runs(mission: taskId);
    } on SiteError catch (e) {
      if (mounted && gen == _gen) {
        setState(() => _msg = tr("Can't find the record for that task: $e", '未找到该任务的记录：$e'));
      }
      return;
    }
    if (!mounted || gen != _gen) return;
    if (runs.isEmpty) {
      setState(
        () => _msg = tr(
          'The task record hasn\'t reached the site yet (it uploads after the robot arrives and takes photos)',
          '该任务的记录尚未上传到站点（机器人到达并拍照后上传）',
        ),
      );
      return;
    }
    await Navigator.push(
      context,
      MaterialPageRoute<void>(
        builder: (_) => SiteRunPage(api: widget.api, runId: (runs.first['id'] as num).toInt()),
      ),
    );
  }

  /// 就地驱离（W33，决策 48）：狗在跑的任务先撤掉，就在它这儿开一场、从 L1（灯光）起。
  Future<void> _deterHere() async {
    final gen = _gen, robot = _a.robot;
    try {
      final s = await widget.api.deterStart(robot);
      if (!mounted || gen != _gen) return;
      final lv = s['session'] is Map ? (s['session'] as Map)['level'] : null;
      setState(() {
        if (s['session'] is Map) _gotDeter(Map<String, dynamic>.from(s['session'] as Map));
        _msg = tr(
          'Deterrence started on $robot (L${lv ?? 1}). Escalate or end it on the deterrence page',
          '已在 $robot 启动驱离（L${lv ?? 1}），可在驱离页升级或解除',
        );
      });
    } on SiteError catch (e) {
      if (mounted && gen == _gen) setState(() => _msg = tr("Can't start deterrence: $e", '无法启动驱离：$e'));
    }
  }

  static String _two(int n) => n.toString().padLeft(2, '0');

  /// 当地时间 时:分:秒。
  static String hms(int ms) {
    final d = DateTime.fromMillisecondsSinceEpoch(ms);
    return '${_two(d.hour)}:${_two(d.minute)}:${_two(d.second)}';
  }

  static String span(int ms) => SiteAlertScenePageSpan.of(ms);

  String _stateLine() {
    if (!_open) return tr('Closed at ${hms(_a.resolvedMs!)}', '${hms(_a.resolvedMs!)} 已关闭');
    if (_acked) {
      final by = _a.ackedBy.isNotEmpty ? _a.ackedBy : (_ackedHere?.$1 ?? '');
      final at = hms(_a.ackedMs ?? _ackedHere!.$2);
      final me = by.isNotEmpty && by == widget.api.session?.name;
      return me ? tr('Acknowledged by you at $at', '你已于 $at 确认') : tr('Acknowledged by ${personName(by)} at $at', '${personName(by)} 已于 $at 确认');
    }
    return tr(
      'Unacknowledged for ${span(widget.now().millisecondsSinceEpoch - _a.firstMs)}',
      '已 ${span(widget.now().millisecondsSinceEpoch - _a.firstMs)} 无人确认',
    );
  }

  Map? get _persons {
    final p = _a.context['persons'] ?? _d?['persons'];
    return p is Map ? p : null;
  }

  /// 「在哪」下面那一句：人离狗多远、驱离到第几级。
  String _whereLine() {
    final parts = <String>[];
    final m = _persons?['nearest_m'];
    if (m is num && _isRobot) {
      // 站点只给最近的距离，没给方向（前后相机汇总的）：不说「前方」（外审 M1）
      parts.add(
        tr(
          'Nearest person ${m.toStringAsFixed(1)} m from ${_a.robot}.',
          '最近的人距 ${_a.robot} ${m.toStringAsFixed(1)} 米。',
        ),
      );
    }
    final d = _d;
    if (d != null) {
      parts.add(tr('Deterrence level ${d['level']}.', '驱离第 ${d['level']} 级。'));
    } else if (_isRobot && !_deterFresh) {
      final old = _deter;
      parts.add(
        old == null
            ? tr('Deterrence status unknown.', '驱离状态未知。')
            : tr(
                'Deterrence status unknown (level ${old['level']} when last checked at ${hms(_deterAtMs)}).',
                '驱离状态未知（${hms(_deterAtMs)} 最后查询时为第 ${old['level']} 级）。',
              ),
      );
    }
    return parts.join(' ');
  }

  // ------------------------------------------------------------ App V2「这件事」（稿 N-incident）

  bool get _security =>
      _a.audience == 'intrusion' || _a.audience == 'fire' || _a.kind == 'payload_sos' || _a.kind == 'dog_sees_person';

  /// 步骤条（跟网页 incidentSteps 一样）：发现 → 接手 → 派出（安全事件、有机器人）→ 到场（要到场的那类）→ 关闭。
  List<(String, int?, String)> _steps() {
    final ackAt = _a.ackedMs ?? _ackedHere?.$2;
    final ackBy = _a.ackedBy.isNotEmpty ? _a.ackedBy : (_ackedHere?.$1 ?? '');
    final arrivedMs = _a.context['arrived_ms'] is num ? (_a.context['arrived_ms'] as num).toInt() : _arrivedHere?.$2;
    return [
      (tr('Detected', '发现'), _a.firstMs, ''),
      (tr('Assigned', '接手'), ackAt, personName(ackBy)),
      if (_security) (tr('Dispatched', '派出'), _isRobot ? _a.firstMs : null, _isRobot ? _a.robot : ''),
      if (_needsArrive) (tr('On site', '到场'), arrivedMs, personName(_a.context['arrived_by'] ?? _arrivedHere?.$1 ?? '')),
      (tr('Closed', '结案'), _a.resolvedMs ?? _closedHere, _a.resolvedMs != null ? verdictWord(_a.verdict) : ''),
    ];
  }

  static String _hm(int ms) {
    final d = DateTime.fromMillisecondsSinceEpoch(ms);
    return '${_two(d.hour)}:${_two(d.minute)}';
  }

  String _followLine() => followLine(_a);

  /// 页头：标题 + P1、在哪 · 几点、谁在处理（或没人接手多久 +「我来处理」）、步骤条。没接手的 P1 红框闪。
  Widget _header(NwColors c) {
    final p1 = _a.level == 'P1' && _open;
    final ctx = _a.context;
    final where = [
      if ('${ctx['zone'] ?? ''}'.isNotEmpty) '${ctx['zone']}',
      if ('${ctx['camera'] ?? ''}'.isNotEmpty) '${ctx['camera']}',
      if (_isRobot) _a.robot,
      if (seenByText(ctx).isNotEmpty) seenByText(ctx),
      if ('${ctx['exit'] ?? ''}'.isNotEmpty) tr('left via ${ctx['exit']}', '从 ${ctx['exit']} 离开'),
    ].join(' · ');
    final follow = _followLine();
    final situation = _whereLine();
    final handle = widget.api.session?.canHandleAlerts ?? false;
    // 关了的不再走表：写开了多久（稿 S-alarm-rec）
    final closedAt = _a.resolvedMs;
    final elapsed = span((closedAt ?? widget.now().millisecondsSinceEpoch) - _a.firstMs);
    return AnimatedOpacity(
      opacity: _dim ? D1Motion.p1FlashMinOpacity : 1.0,
      duration: const Duration(milliseconds: D1Motion.fast),
      child: Container(
        key: SiteAlertScenePage.headKey,
        margin: const EdgeInsets.fromLTRB(Nw.s16, 12, Nw.s16, 0),
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: c.surface,
          border: Border.all(color: p1 && _open ? c.error : c.outline, width: p1 && _open ? 4 : 1),
          borderRadius: BorderRadius.circular(2),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              closedAt != null
                  ? tr('Detected ${_hm(_a.firstMs)} · closed after $elapsed', '${_hm(_a.firstMs)} 发现 · $elapsed 后结案')
                  : tr('Detected ${_hm(_a.firstMs)} · $elapsed elapsed', '${_hm(_a.firstMs)} 发现 · 已过 $elapsed'),
              style: NwText.bodySmall.copyWith(color: c.textSecondary),
            ),
            const SizedBox(height: 4),
            Row(
              crossAxisAlignment: CrossAxisAlignment.center,
              children: [
                Expanded(
                  child: Text(
                    alertTitle(_a.kind, _a.title),
                    style: NwText.titleLarge.copyWith(color: c.text, fontWeight: FontWeight.w700),
                  ),
                ),
                const SizedBox(width: Nw.s8),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                  color: _a.level == 'P1' ? c.errorSoft : c.surfaceVariant,
                  child: Text(
                    _a.level,
                    style: NwText.labelLarge.copyWith(color: priorityColor(_a.level, c), fontWeight: FontWeight.w700),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 4),
            Text(where, style: NwText.bodySmall.copyWith(color: c.textSecondary)),
            if (situation.isNotEmpty) ...[
              const SizedBox(height: 4),
              Text(
                situation,
                key: SiteAlertScenePage.situationKey,
                style: NwText.bodyMedium.copyWith(color: c.text),
              ),
            ],
            const SizedBox(height: 6),
            Text(
              [_stateLine(), if (follow.isNotEmpty) follow].join(' · '),
              key: SiteAlertScenePage.stateKey,
              style: NwText.labelLarge.copyWith(
                color: _open && !_acked ? c.error : c.text,
                fontWeight: FontWeight.w600,
              ),
            ),
            if (handle && _open && !_acked && _a.kind != 'account_request') ...[
              const SizedBox(height: 10),
              _act(SiteAlertScenePage.ackKey, tr('Take ownership', '我来处理'), _ack, primary: true),
            ],
            const SizedBox(height: 12),
            _stepBar(c),
          ],
        ),
      ),
    );
  }

  Widget _stepBar(NwColors c) {
    final steps = _steps();
    return Row(
      key: SiteAlertScenePage.stepsKey,
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // 按字数分宽（390 宽上「Dispatched」不截断）；格子之间留一点缝
        for (final st in steps)
          Expanded(
            flex: st.$1.length < 5 ? 5 : st.$1.length,
            child: Padding(
              padding: const EdgeInsets.only(right: 4),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Container(height: 3, color: st.$2 != null ? c.success : c.outline),
                  const SizedBox(height: 4),
                  Text(
                    st.$1,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: NwText.labelSmall.copyWith(
                      color: st.$2 != null ? c.text : c.textMuted,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                  if (st.$2 != null)
                    Text(
                      st.$3.isNotEmpty ? st.$3 : _hm(st.$2!),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: NwText.labelSmall.copyWith(color: c.textSecondary),
                    ),
                ],
              ),
            ),
          ),
      ],
    );
  }

  /// 本页包在深色主题里（C1 11-17）：State 自己的 context 在那层主题外面，取颜色要用里面那层的。
  BuildContext? _inner;
  NwColors get _c => Nw.of(_inner ?? context);

  /// 本页的动作按钮：字 14（正文半粗）、高 48、内距小 —— 390 宽两个一排也摆得下一行；夜里戴手套也点得中。
  Widget _act(Key key, String label, VoidCallback? on, {bool primary = false, IconData? icon}) {
    final c = _c;
    const size = Size(48, 48);
    const padding = EdgeInsets.symmetric(horizontal: Nw.s8);
    final shape = RoundedRectangleBorder(borderRadius: BorderRadius.circular(2));
    final child = Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        if (icon != null) ...[Icon(icon, size: 18), const SizedBox(width: 6)],
        Flexible(
          child: Text(label, textAlign: TextAlign.center, maxLines: 2, overflow: TextOverflow.ellipsis),
        ),
      ],
    );
    return primary
        ? FilledButton(
            key: key,
            style: FilledButton.styleFrom(
              backgroundColor: c.primary,
              foregroundColor: c.onPrimary,
              disabledBackgroundColor: c.surfaceVariant,
              disabledForegroundColor: c.textMuted,
              minimumSize: size,
              padding: padding,
              textStyle: NwText.titleSmall,
              shape: shape,
            ),
            onPressed: on,
            child: child,
          )
        : OutlinedButton(
            key: key,
            style: OutlinedButton.styleFrom(
              foregroundColor: c.text,
              disabledForegroundColor: c.textMuted,
              side: BorderSide(color: c.textMuted),
              minimumSize: size,
              padding: padding,
              textStyle: NwText.titleSmall,
              shape: shape,
            ),
            onPressed: on,
            child: child,
          );
  }

  /// 一段的标题行（稿：小标题 + 右边一个说明）。
  Widget _section(NwColors c, String title, List<Widget> children, {Key? key, String? note}) => Container(
    key: key,
    margin: const EdgeInsets.fromLTRB(Nw.s16, 16, Nw.s16, 0),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text(
          title,
          style: NwText.titleSmall.copyWith(color: c.text, fontWeight: FontWeight.w700),
        ),
        if (note != null) ...[
          const SizedBox(height: 2),
          Text(note, style: NwText.bodySmall.copyWith(color: c.textSecondary)),
        ],
        const SizedBox(height: 8),
        ...children,
      ],
    ),
  );

  Widget _row(List<Widget> xs) => Row(
    children: [
      for (var i = 0; i < xs.length; i++) ...[if (i > 0) const SizedBox(width: Nw.s8), Expanded(child: xs[i])],
    ],
  );

  /// 现场照片 + 画面 + 回放（这一台机器人的；不是机器人报的没有画面）。
  List<Widget> _media(NwColors c) {
    final taskId = _a.context['task_id'] is String ? _a.context['task_id'] as String : null;
    return [
      if (taskId != null)
        Padding(
          padding: const EdgeInsets.fromLTRB(Nw.s16, 12, Nw.s16, 0),
          child: ScenePhoto(
            key: ValueKey<String>('scene-photo ${_a.key}'),
            api: widget.api,
            taskId: taskId,
            onOpen: () => _photo(taskId),
          ),
        ),
      if (_isRobot && _open) ...[
        Padding(
          padding: const EdgeInsets.fromLTRB(Nw.s16, 12, Nw.s16, 6),
          child: Text(
            [
              tr('${_a.robot} · Live video', '${_a.robot} · 实时画面'),
              if (const ['follow', 'retreat', 'cornered'].contains(_a.context['follow'])) tr('Following', '跟随中'),
            ].join(' · '),
            style: NwText.labelLarge.copyWith(color: c.text, fontWeight: FontWeight.w600),
          ),
        ),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: Nw.s16),
          child: SiteVideo(api: widget.api, robotId: _a.robot),
        ),
      ],
      if (_isRobot || taskId != null)
        Padding(
          padding: const EdgeInsets.fromLTRB(Nw.s16, 8, Nw.s16, 0),
          child: _row([
            if (_isRobot)
              _act(
                SiteAlertScenePage.videoKey,
                tr('−30 s replay', '回看 30 秒'),
                () => Navigator.push(
                  context,
                  MaterialPageRoute<void>(
                    builder: (_) => SiteRecordingsPage(api: widget.api, robotId: _a.robot, aroundMs: _a.firstMs),
                  ),
                ),
                icon: Icons.replay_30_rounded,
              ),
            if (taskId != null)
              _act(
                SiteAlertScenePage.photoKey,
                tr('Scene photos', '现场照片'),
                () => _photo(taskId),
                icon: Icons.photo_camera_outlined,
              ),
          ]),
        ),
    ];
  }

  /// 小地图（机器人、人最后在哪、拦截点），点了进全屏。
  Widget? _mapBlock() {
    final marks = sceneMarks(_a);
    if (marks == null) return null;
    return Padding(
      padding: const EdgeInsets.fromLTRB(Nw.s16, 12, Nw.s16, 0),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          NwMapThumb(
            key: ValueKey<String>('scene-map-thumb ${marks.$1}:${marks.$2}'),
            tapKey: SiteAlertScenePage.mapKey,
            height: 180,
            load: () => loadMapPicture(widget.api, marks.$1, marks.$2),
            label: marks.$3.map((m) => m.label).join(' · '),
            action: tr('Full-screen map', '全屏地图'),
            onTap: () => Navigator.push(
              context,
              MaterialPageRoute<void>(
                builder: (_) =>
                    SiteMapPreviewPage(api: widget.api, mapId: marks.$1, version: marks.$2, marks: marks.$3),
              ),
            ),
          ),
        ],
      ),
    );
  }

  /// 现场警示：自动驱离到第几级 +「结束驱离」；喊话 / 警灯 / 警笛 / 全部关（这台机器人有的才摆）。
  /// 只读、经理（不能派的）只说一句由保安操作。
  Widget? _warning(NwColors c) {
    // 外审 App-V2-2 N3：结案不等于驱离结束（站点结案不解除驱离）：还在驱离就照样摆着「结束驱离」
    if ((!_open && _d == null) || !_isRobot || !_security) return null;
    final dispatch = widget.api.session?.canDispatch ?? false;
    // 外审 App-V2-4 R1：「结束驱离」站点按叫停权限（经理也有）；升级、喊话、警灯仍要能派
    final abort = widget.api.session?.canAbort ?? false;
    if (!dispatch) {
      final d0 = _d;
      return _section(c, tr('On-site warning', '现场警示'), key: SiteAlertScenePage.warnKey, [
        if (d0 != null && abort) ...[
          Text(tr('Deterrence running: ${deterSessionText(d0)}', '正在驱离：${deterSessionText(d0)}'),
              key: SiteAlertScenePage.deterLevelKey,
              style: NwText.labelLarge.copyWith(color: c.text, fontWeight: FontWeight.w700)),
          const SizedBox(height: Nw.s8),
          _act(SiteAlertScenePage.endDeterKey, tr('End deterrence', '结束驱离'), _endDeter),
          const SizedBox(height: Nw.s8),
        ],
        Text(
          tr('Dispatching robots to the alarm and on-site warnings are handled by guards', '派机器人去报警点和现场警示由保安操作'),
          style: NwText.bodyMedium.copyWith(color: c.textSecondary),
        ),
      ]);
    }
    final d = _d;
    // 机器人没报上装（老机器人）：按站点那一场驱离报的几路
    final out = _outputs.isNotEmpty ? _outputs : ((d?['outputs'] as List?) ?? const []).map((e) => '$e').toList();
    final clips = ((_caps?['clips'] as List?) ?? const []).map((e) => '$e').toList();
    final canSpeak = out.contains('speaker') && (clips.isNotEmpty || _caps?['tts'] == true);
    final clip = clips.contains('restricted')
        ? 'restricted'
        : clips.isNotEmpty
        ? clips.first
        : 'tts:${appLang.value == AppLang.zh ? 'zh' : 'en'}:${tr('This is a restricted area. Please leave now.', '这里是禁区，请马上离开。')}';
    final level = d?['level'];
    final levelWord = switch (level) {
      1 => tr('light', '灯光'),
      2 => tr('voice warning', '语音警告'),
      3 => tr('siren', '警笛'),
      _ => tr('observe', '观察'),
    };
    // 在驱离（C-B2 外审）：警笛是站点那一场的第 3 级，按了升级；机器人接受了才写已开。旧快照不猜，让人能再要求一次。
    // 没在驱离：机器人装了警笛才摆「警笛 10 秒」，直接响、到点自己关。
    Widget siren(String label, VoidCallback? on) => _act(SiteAlertScenePage.sirenKey, label, on);
    const lv = SiteAlertScenePageSiren.level;
    final sound = tr('Sound siren (level $lv)', '开警笛（第 $lv 级）');
    final Widget? sirenBtn = d != null
        ? switch (SiteAlertScenePageSiren.of(d)) {
            SirenState.on => siren(tr('Siren is on', '警笛已开'), null),
            SirenState.notFitted => siren(tr('No siren on this robot', '此机器人没有警笛'), null),
            SirenState.requested => siren(tr('Siren not confirmed. Retry', '警笛未确认，请重试'), _siren),
            _ => siren(sound, _siren),
          }
        : _deter != null && !_deterFresh
        ? siren(sound, _siren)
        : out.contains('siren')
        ? siren(tr('Siren 10 s', '警笛 10 秒'), () => _warn('siren', maxS: 10))
        : null;
    final buttons = <Widget>[
      if (canSpeak)
        _act(
          SiteAlertScenePage.speakKey,
          tr('Announce warning', '喊话：请离开'),
          () => _warn('speaker', maxS: 60, clip: clip),
        ),
      if (out.contains('strobe'))
        _act(SiteAlertScenePage.strobeKey, tr('Strobe 30 s', '开警灯 30 秒'), () => _warn('strobe', maxS: 30)),
      ?sirenBtn,
      if (out.isNotEmpty) _act(SiteAlertScenePage.allOffKey, tr('All off', '全部关'), _allOff),
    ];
    final staleOld = d == null && _deter != null && !_deterFresh;
    return _section(
      c,
      tr('On-site warning · ${_a.robot}', '现场警示 · 用 ${_a.robot} 的喇叭和警灯'),
      key: SiteAlertScenePage.warnKey,
      note: tr('Directed at the intruder; strobe and announcement work best together', '对着闯入的人；警灯和喊话一起用效果最好'),
      [
        if (d != null)
          Container(
            padding: const EdgeInsets.all(10),
            margin: const EdgeInsets.only(bottom: 8),
            decoration: BoxDecoration(
              color: c.surface,
              border: Border.all(color: c.outline),
              borderRadius: BorderRadius.circular(2),
            ),
            child: Row(
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        tr('Auto deterrence: Level $level, $levelWord', '自动驱离：第 $level 级 $levelWord'),
                        key: SiteAlertScenePage.deterLevelKey,
                        style: NwText.labelLarge.copyWith(color: c.text, fontWeight: FontWeight.w700),
                      ),
                      Text(
                        tr('Observe → Light → Voice → Siren', '观察 → 灯光 → 语音 → 警笛'),
                        style: NwText.bodySmall.copyWith(color: c.textSecondary),
                      ),
                    ],
                  ),
                ),
                const SizedBox(width: Nw.s8),
                _act(SiteAlertScenePage.endDeterKey, tr('End deterrence', '结束驱离'), _endDeter),
              ],
            ),
          )
        else if (!staleOld && _a.kind == 'dog_sees_person')
          Padding(
            padding: const EdgeInsets.only(bottom: 8),
            child: _act(SiteAlertScenePage.deterKey, tr('Deter here', '就地驱离'), _deterHere),
          ),
        for (var i = 0; i < buttons.length; i += 2) ...[
          if (i > 0) const SizedBox(height: Nw.s8),
          _row(buttons.sublist(i, i + 2 > buttons.length ? buttons.length : i + 2)),
        ],
      ],
    );
  }

  /// 通知：推给了谁；请求支援 / 已到场。
  Widget? _notify(NwColors c) {
    if (!_open || _a.kind == 'account_request') return null;
    final handle = widget.api.session?.canHandleAlerts ?? false;
    final by = '${_a.context['backup_by'] ?? _backupHere?.$1 ?? ''}';
    final at = _a.context['backup_ms'] is num ? (_a.context['backup_ms'] as num).toInt() : _backupHere?.$2;
    final buttons = <Widget>[
      if (handle && by.isEmpty) _act(SiteAlertScenePage.backupKey, tr('Request backup', '请求支援'), _backup),
      if (handle && _needsArrive && !_arrived) _act(SiteAlertScenePage.arriveKey, tr('On scene', '已到场'), _arrive),
    ];
    return _section(c, tr('Notify', '通知'), key: SiteAlertScenePage.notifyKey, [
      Text(
        _a.level == 'P1'
            ? (_pushOff == null
                ? tr('P1 alarm: shown in the app and on every console', 'P1 报警：App 和所有控制台都看得到')
                : _pushOff!
                ? tr('Phone push is not set up on this site: this alarm shows only in the app and on consoles',
                    '站点没配手机推送：这条报警只在 App 和网页里')
                : tr('Pushed to all signed-in phones', '已推送到所有登录的手机'))
            : tr('Shown on every console', '所有控制台都看得到'),
        style: NwText.bodyMedium.copyWith(color: c.text),
      ),
      if (by.isNotEmpty)
        Text(
          tr(
            'Backup requested by $by${at != null ? ' at ${_hm(at)}' : ''}; managers and administrators were notified.',
            '$by${at != null ? ' ${_hm(at)}' : ''} 请求了支援，已推送给经理和管理员。',
          ),
          key: SiteAlertScenePage.backupDoneKey,
          style: NwText.bodySmall.copyWith(color: c.textSecondary),
        ),
      if (buttons.isNotEmpty) ...[const SizedBox(height: 8), _row(buttons)],
      const SizedBox(height: 4),
      Text(
        tr(
          'Request backup notifies managers and administrators; On scene is logged in the timeline.',
          '请求支援会推给经理和管理员；已到场写进经过。',
        ),
        style: NwText.bodySmall.copyWith(color: c.textSecondary),
      ),
    ]);
  }

  /// 结论：选一个（等宽一排），可写一句备注，「结案」。要先到场的那类没到场只说一句；只读说一句。
  /// 关了的：谁、什么结论、几点；10 分钟内能重新打开。
  Widget _disposition(NwColors c) {
    final handle = widget.api.session?.canHandleAlerts ?? false;
    if (_a.kind == 'account_request') {
      return _section(c, tr('Account application', '账号申请'), [
        if (widget.api.session?.canManageAccounts ?? false)
          _act(
            SiteAlertScenePage.accountsKey,
            tr('Review the application', '去审批'),
            () => Navigator.push(context, MaterialPageRoute<void>(builder: (_) => AccountsPage(api: widget.api))),
            primary: true,
          )
        else
          Text(
            tr('An administrator approves account applications. Nothing to do here.', '账号申请由管理员审批，这里不用处理。'),
            key: SiteAlertScenePage.whyKey,
            style: NwText.bodyMedium.copyWith(color: c.textSecondary),
          ),
      ]);
    }
    if (!_open || _closedHere != null && _a.resolvedMs == null) {
      final at = _a.resolvedMs ?? _closedHere;
      final who = personName(_a.resolvedBy.isNotEmpty ? _a.resolvedBy : (widget.api.session?.name ?? ''));
      final v = _a.verdict.isNotEmpty ? _a.verdict : (_verdict ?? '');
      return _section(c, tr('Disposition', '结论'), key: SiteAlertScenePage.verdictKey, [
        Text(
          tr(
            'Closed: ${verdictWord(v)} · $who${at != null ? ' · ${_hm(at)}' : ''}',
            '已结案：${verdictWord(v)} · $who${at != null ? ' · ${_hm(at)}' : ''}',
          ),
          key: SiteAlertScenePage.closedKey,
          style: NwText.bodyMedium.copyWith(color: c.text, fontWeight: FontWeight.w600),
        ),
        if (handle && _canReopen) ...[
          const SizedBox(height: 8),
          _act(SiteAlertScenePage.reopenKey, tr('Reopen', '重新打开'), _reopen),
        ],
      ]);
    }
    if (!handle) {
      return _section(c, tr('Disposition', '结论'), key: SiteAlertScenePage.verdictKey, [
        Text(
          tr('Read-only account: you can watch this alarm; a guard or administrator handles it.', '只读账号：能看，处理要保安或管理员。'),
          key: SiteAlertScenePage.whyKey,
          style: NwText.bodyMedium.copyWith(color: c.textSecondary),
        ),
      ]);
    }
    if (_needsArrive && !_arrived) {
      return _section(c, tr('Disposition', '结论'), key: SiteAlertScenePage.verdictKey, [
        Text(
          tr('Close it only after someone is on site: tap On scene first.', '有人到场后才能结案：先点「已到场」。'),
          key: SiteAlertScenePage.whyKey,
          style: NwText.bodyMedium.copyWith(color: c.textSecondary),
        ),
      ]);
    }
    final vs = _verdicts;
    return _section(
      c,
      tr('Disposition', '结论'),
      key: SiteAlertScenePage.verdictKey,
      note: tr('Set a disposition before closing', '定了结论才能结案'),
      [
        _row([
          for (final v in vs)
            _act(
              v == 'false_alarm'
                  ? SiteAlertScenePage.falseKey
                  : v == 'handled'
                  ? SiteAlertScenePage.handledKey
                  : SiteAlertScenePage.intruderKey,
              verdictWord(v),
              () => setState(() => _verdict = v),
              primary: _verdict == v,
            ),
        ]),
        const SizedBox(height: 8),
        TextField(
          key: SiteAlertScenePage.noteKey,
          controller: _note,
          maxLength: 200,
          decoration: InputDecoration(
            // 易用性 37 场景测试：这句备注记在这条报警上（报警记录、交班报告里看得到），不进交班留言 —— 以前写「给下一班看」
            hintText: tr('Note on this alarm (optional; shown in the alarm log)', '备注（可不写，记在这条报警上）'),
            counterText: '',
          ),
        ),
        const SizedBox(height: 8),
        _act(
          SiteAlertScenePage.doneKey,
          tr('Close incident', '结案'),
          _verdict == null || _busy ? null : _close,
          primary: true,
        ),
      ],
    );
  }

  /// 事件经过：站点记下来的时刻，一行一条；最后一行是「接下来会自动发生什么」（提示色）。
  List<Widget> _timeline() {
    final c = _c;
    final note = NwText.bodyMedium.copyWith(color: c.info, fontWeight: FontWeight.w600);
    final rows = <(int, String)>[
      (
        _a.firstMs,
        [
          alertTitle(_a.kind, _a.title),
          if (_a.detail.isNotEmpty && appLang.value == AppLang.zh) siteText(_a.detail),
        ].join(' · '),
      ),
      if (_a.count > 1 && _a.lastMs > _a.firstMs)
        (_a.lastMs, tr('Raised again (${_a.count} times in total).', '再次报警（共 ${_a.count} 次）。')),
    ];
    // 开始、升级是带时刻的旧事，旧快照里的也照摆；「接下来」是现在的计划，只有新鲜的才说
    final d = _deter;
    if (d != null) {
      if (d['started_ms'] is num) {
        rows.add(((d['started_ms'] as num).toInt(), tr('Deterrence started.', '开始驱离。')));
      }
      if (d['level_ms'] is num && d['level'] is num && (d['level'] as num) > 1) {
        rows.add((
          (d['level_ms'] as num).toInt(),
          tr('Deterrence raised to level ${d['level']}.', '驱离升至第 ${d['level']} 级。'),
        ));
      }
    }
    final at = _a.ackedMs ?? _ackedHere?.$2;
    if (at != null) {
      final by = _a.ackedBy.isNotEmpty ? _a.ackedBy : (_ackedHere?.$1 ?? '');
      rows.add((at, tr('Acknowledged by ${personName(by)}.', '${personName(by)} 已确认。')));
    }
    final lost = _a.context['lost_ms'];
    if (lost is num) {
      rows.add((lost.toInt(), tr('Person no longer seen: whereabouts unknown.', '看不到人了，去向不明。')));
    }
    // W74 二期：机器人在跟 / 跟丢了（人最后在哪）
    final follow = _a.context['follow'];
    final person = _a.context['person'] is Map ? _a.context['person'] as Map : null;
    final pAt = person?['at_ms'] is num ? (person!['at_ms'] as num).toInt() : _a.lastMs;
    if (follow == 'follow') {
      rows.add((pAt, tr('The robot is following this person.', '机器人正跟着这个人。')));
    } else if (follow == 'retreat' || follow == 'cornered') {
      rows.add((pAt, '${_followLine()}${tr('.', '。')}'));
    } else if (_a.context['follow_left'] == true) {
      rows.add((pAt, '${_followLine()}${tr('.', '。')}'));
    } else if (follow == 'lost' || follow == 'limit') {
      final w = person?['where'] is String ? person!['where'] as String : '';
      rows.add((
        pAt,
        w.isEmpty
            ? tr('Robot stopped following.', '机器人不跟了，回到人最后出现的地方。')
            : tr('Lost the person, last seen near $w.', '跟丢了，人最后在 $w。'),
      ));
    }
    final arrivedMs = _a.context['arrived_ms'] is num ? (_a.context['arrived_ms'] as num).toInt() : _arrivedHere?.$2;
    if (arrivedMs != null) {
      final by = _a.context['arrived_by'] is String ? _a.context['arrived_by'] as String : (_arrivedHere?.$1 ?? '');
      rows.add((arrivedMs, tr('${personName(by)} is on site.', '${personName(by)} 已到场。')));
    }
    // 易用性 37 场景测试：从这里点的喊话、警灯、警笛（站点记在 context.warnings）
    for (final w in (_a.context['warnings'] as List? ?? const []).whereType<Map>()) {
      if (w['at_ms'] is! num) continue;
      final who = personName(w['by']);
      rows.add((
        (w['at_ms'] as num).toInt(),
        switch ('${w['output']}') {
          'speaker' => tr('$who made an announcement.', '$who 喊话。'),
          'strobe' => tr('$who turned on the strobe.', '$who 开了警灯。'),
          'siren' => tr('$who sounded the siren.', '$who 拉了警笛。'),
          'spotlight' => tr('$who turned on the spotlight.', '$who 开了聚光灯。'),
          final o => tr('$who turned on $o.', '$who 开了 $o。'),
        },
      ));
    }
    final bAt = _a.context['backup_ms'] is num ? (_a.context['backup_ms'] as num).toInt() : _backupHere?.$2;
    if (bAt != null) {
      final by = '${_a.context['backup_by'] ?? _backupHere?.$1 ?? ''}';
      rows.add((bAt, tr('$by requested backup.', '$by 请求了支援。')));
    }
    if (_a.resolvedMs != null) {
      final n = '${_a.context['note'] ?? ''}';
      final who = _a.resolvedBy.isEmpty ? '' : ' ${personName(_a.resolvedBy)}';
      rows.add((
        _a.resolvedMs!,
        _a.verdict.isEmpty
            ? tr('Closed$who.', '$who 已关闭。'.trim())
            : tr(
                'Closed by${who.isEmpty ? ' ?' : who}: ${verdictWord(_a.verdict)}.${n.isEmpty ? '' : ' Note: $n'}',
                '${who.trim()} 结案：${verdictWord(_a.verdict)}。${n.isEmpty ? '' : '备注：$n'}'.trim(),
              ),
      ));
    }
    rows.sort((x, y) => x.$1.compareTo(y.$1));
    final staleNote = _isRobot && d != null && !_deterFresh
        ? tr('Deterrence status not updated since ${hms(_deterAtMs)}.', '驱离状态自 ${hms(_deterAtMs)} 起未更新。')
        : null;
    final next = _deterFresh && d != null && d['auto'] == true && d['next_in_s'] is num
        ? tr(
            'Next: level ${(d['level'] as num? ?? 0) + 1} in ${d['next_in_s']} s if no one responds.',
            '下一步：若无人处理，${d['next_in_s']} 秒后升至第 ${(d['level'] as num? ?? 0) + 1} 级。',
          )
        : null;
    return [
      Text(tr('Timeline', '事件经过'), style: NwText.titleSmall.copyWith(color: c.text)),
      const SizedBox(height: 4),
      for (final r in rows)
        Padding(
          padding: const EdgeInsets.symmetric(vertical: 2),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(hms(r.$1), style: NwText.labelMedium.copyWith(color: c.textSecondary)),
              const SizedBox(width: 12),
              Expanded(
                child: Text(r.$2, style: NwText.bodyMedium.copyWith(color: c.text)),
              ),
            ],
          ),
        ),
      if (staleNote != null)
        Padding(
          padding: const EdgeInsets.symmetric(vertical: 2),
          child: Text(staleNote, key: SiteAlertScenePage.staleKey, style: note),
        ),
      if (next != null)
        Padding(
          padding: const EdgeInsets.symmetric(vertical: 2),
          child: Text(next, key: SiteAlertScenePage.nextKey, style: note),
        ),
    ];
  }

  /// 现场数据（旧页的「现场细节」）：防区、拦截点、机器人最后在哪、那一趟。
  List<Widget> _facts(NwColors c) {
    final ctx = _a.context;
    final small = NwText.bodySmall.copyWith(color: c.textSecondary);
    final p0 = ctx['last_seen'] ?? ctx['pose'];
    final pose = p0 is Map ? p0 : null;
    final point = ctx['intercept'] is Map ? ctx['intercept'] as Map : null;
    final taskId = ctx['task_id'] is String ? ctx['task_id'] as String : null;
    String f(Object? v) => (v as num).toStringAsFixed(1);
    // 易用性 37 场景测试：坐标、地图版本号、任务号对保安没用 —— 只给管地图的（管理员、工程师）看；地图上已经画了位置
    final tech = widget.api.session?.canManageMaps ?? false;
    return [
      if (ctx['zone'] != null) Text(tr('Zone: ${ctx['zone']}', '防区：${ctx['zone']}'), style: small),
      if (point != null && point['x'] is num && point['y'] is num)
        Text(
          tech
              ? tr('Intercept point: ${point['name']}  (${f(point['x'])}, ${f(point['y'])})',
                  '拦截点：${point['name']}  (${f(point['x'])}, ${f(point['y'])})')
              : tr('Intercept point: ${point['name']}', '拦截点：${point['name']}'),
          style: small,
        ),
      if (tech && pose != null && pose['x'] is num && pose['y'] is num)
        Text(
          tr(
            'Robot last at: (${f(pose['x'])}, ${f(pose['y'])})  map ${mapName(pose['map_id'])} v${pose['map_version']}',
            '机器人最后位置：(${f(pose['x'])}, ${f(pose['y'])})  地图 ${mapName(pose['map_id'])} 第 ${pose['map_version']} 版',
          ),
          style: small,
        ),
      if (tech && taskId != null) Text(tr('Task: $taskId', '那一趟：$taskId'), style: small),
      if (ctx.isEmpty)
        Text(
          tr('This alarm has no scene data (older site, or a site-level alarm)', '此报警没有现场数据（旧版站点或站点级报警）'),
          style: small,
        ),
    ];
  }

  @override
  Widget build(BuildContext context) {
    final dark = nwTheme(Brightness.dark);
    return Theme(
      data: dark,
      child: Builder(
        builder: (context) {
          _inner = context;
          final c = Nw.of(context);
          final map = _mapBlock();
          final warn = _warning(c);
          final notify = _notify(c);
          final dispatch = widget.api.session?.canDispatch ?? false;
          final detail = appLang.value != AppLang.zh && _a.detail.isNotEmpty ? siteTextOrEmpty(_a.detail) : '';
          return Scaffold(
            backgroundColor: c.bg,
            appBar: AppBar(
              backgroundColor: c.bg,
              leading: Navigator.canPop(context)
                  ? IconButton(
                      icon: const Icon(Icons.arrow_back_ios_new_rounded),
                      tooltip: MaterialLocalizations.of(context).backButtonTooltip,
                      onPressed: () => Navigator.maybePop(context),
                    )
                  : null,
              title: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text(tr('Incident', '这件事')),
                // 稿 S-alarm-rec：关了的是一条记录，顶栏写「几点 · 已结案」
                if (_a.resolvedMs != null)
                  Text(tr('${_hm(_a.firstMs)} · Closed', '${_hm(_a.firstMs)} · 已结案'),
                      style: NwText.bodySmall.copyWith(color: c.textSecondary)),
              ]),
            ),
            body: Stack(
              children: [
                ListView(
                  padding: EdgeInsets.only(bottom: 120, right: MediaQuery.sizeOf(context).aspectRatio > 1.3 ? 120 : 0),
                  children: [
                    EstopMissCards(api: widget.api), // 急停没确认(稿 N-refuse)
                    _header(c),
                    ..._media(c),
                    ?map,
                    ?warn,
                    ?notify,
                    _disposition(c),
                    _section(c, tr('Timeline', '经过'), key: SiteAlertScenePage.timelineKey, [
                      ..._timeline().skip(2),
                      const SizedBox(height: 8),
                      if (detail.isNotEmpty) Text(detail, style: NwText.bodySmall.copyWith(color: c.textSecondary)),
                      ..._facts(c),
                    ]),
                  ],
                ),
                // 按了之后的那句话：钉在底下（急停方块左边），滚到哪儿点的都看得到
                if (_msg.isNotEmpty)
                  Positioned(
                    left: Nw.s16,
                    right: dispatch ? Nw.s16 + 88 + Nw.s8 : Nw.s16,
                    bottom: Nw.s16,
                    child: SafeArea(
                      child: Container(
                        constraints: const BoxConstraints(minHeight: 48, maxHeight: 120),
                        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                        decoration: BoxDecoration(
                          color: c.surfaceVariant,
                          border: Border.all(color: c.outline),
                          borderRadius: BorderRadius.circular(2),
                        ),
                        child: SingleChildScrollView(
                          child: Text(
                            _msg,
                            key: SiteAlertScenePage.msgKey,
                            style: NwText.bodyMedium.copyWith(color: c.text, fontWeight: FontWeight.w600),
                          ),
                        ),
                      ),
                    ),
                  ),
                // 外审 App-V2-3 I3：急停按叫停权限（经理也能急停），不按派遣权限
                if (widget.api.session?.canAbort ?? false)
                  Positioned(
                    right: Nw.s16,
                    bottom: Nw.s16,
                    child: SafeArea(
                      child: EstopSquare(
                        buttonKey: SiteAlertScenePage.estopKey,
                        onPressed: () => StopAllButton.press(context, widget.api, (m) => setState(() => _msg = m)),
                      ),
                    ),
                  ),
              ],
            ),
          );
        },
      ),
    );
  }
}

/// W60：报警页的现场照片（那一趟拍的第一张）。没有那一趟、还没上传、取不到：不占地方（不报错，
/// 「现场照片」按钮照旧能点开看全部）。
class ScenePhoto extends StatefulWidget {
  final SiteApi api;
  final String taskId;
  final VoidCallback onOpen;
  const ScenePhoto({super.key, required this.api, required this.taskId, required this.onOpen});

  static const Key photoKey = Key('scene-photo-inline');

  @override
  State<ScenePhoto> createState() => _ScenePhotoState();
}

class _ScenePhotoState extends State<ScenePhoto> {
  late final Future<Uint8List?> _bytes = _load();

  Future<Uint8List?> _load() async {
    try {
      final runs = await widget.api.runs(mission: widget.taskId);
      if (runs.isEmpty) return null;
      final id = (runs.first['id'] as num).toInt();
      final d = await widget.api.run(id);
      final ps = (d['photos'] as List? ?? const []).whereType<Map>().toList();
      if (ps.isEmpty) return null;
      final b = await widget.api.runPhoto(id, '${ps.first['name']}');
      return b.isEmpty ? null : b;
    } catch (_) {
      return null;
    }
  }

  @override
  Widget build(BuildContext context) {
    final c = Nw.of(context);
    return FutureBuilder<Uint8List?>(
      future: _bytes,
      builder: (context, snap) {
        final b = snap.data;
        if (b == null) return const SizedBox.shrink();
        return Padding(
          padding: const EdgeInsets.fromLTRB(Nw.s8, Nw.s8, Nw.s8, 0),
          child: Semantics(
            button: true,
            label: tr('Scene photo', '现场照片'),
            child: InkWell(
              key: ScenePhoto.photoKey,
              onTap: widget.onOpen,
              child: ClipRRect(
                borderRadius: BorderRadius.circular(Nw.r8),
                child: AspectRatio(
                  aspectRatio: 4 / 3,
                  child: Stack(
                    fit: StackFit.expand,
                    children: [
                      Image.memory(b, fit: BoxFit.cover, gaplessPlayback: true),
                      Positioned(
                        left: Nw.s8,
                        top: Nw.s8,
                        child: Container(
                          padding: const EdgeInsets.symmetric(horizontal: Nw.s8, vertical: 2),
                          decoration: BoxDecoration(color: c.scrim, borderRadius: BorderRadius.circular(Nw.r4)),
                          child: Text(tr('Scene photo', '现场照片'), style: NwText.bodySmall.copyWith(color: c.onScrim)),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
        );
      },
    );
  }
}
