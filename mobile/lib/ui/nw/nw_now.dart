/// 「现在」页（App V2 第 2 期，design/app-v2 N-normal / N-alarm / N-multi / N-estop / N-nomap / M-now / V-now）。
///
/// 从上往下：
/// 1. 一条「全场正常」（绿方块 + 谁在跑、下一趟几点谁跑），或者每件没关的 P1 一个红框事件条
///    （标题 · 在哪 · 几点；没人接手多久 / 谁在处理；「我来处理」+「打开这件事」）；全部急停之后一张红框卡
///    （N 台已急停，「确认全部恢复？」就地确认，不弹窗）。
/// 2. 一路画面：选中那台的前 / 后 / 热像，默认不播、点开才拉流（[SiteVideo]）。
/// 3. 机器人格：每台一格（名字、牌子、状态词、电量、一句在干什么、「控制 ›」），点格换画面。
/// 4. 小地图（机器人在用的那张图）+「派去看一眼」「临时路线」「全屏地图」。
/// 5. 今晚巡逻、设备与运营（P1 以外没处理的）、上一班留言、最新活动。
/// 6. 还没有地图时顶上一张「站点还没有地图 · 开始建图」（管理员），别人只说请管理员建。
///
/// 数据跟老值班页一套（机器人、告警、今天的巡逻、布防、建图向导、演练；事件流推一下就重读，30 秒兜底）。
/// 连不上站点、证书变了的横幅照旧。只读账号没有按钮、没有「控制」。
library;

import 'dart:async';

import 'package:flutter/material.dart';

import '../../design/nw_tokens.g.dart' show NwFont;
import '../../l10n.dart';
import '../../model/alert.dart';
import '../../net/site_client.dart';
import '../map_view.dart' show loadMapPicture;
import '../map_wizard.dart' show openMapWizard, wizardSteps;
import '../patrol_dispatch.dart';
import '../robot_events.dart';
import '../site_alert_scene.dart';
import '../site_deterrence.dart' show SiteDeterrencePage, deterSessionText;
import '../site_duty_page.dart' show DutyTargets, dutyOrder, robotLabel, kSiteDownGrace;
import '../site_robot.dart' show SiteRobotPage, robotStatusLine;
import '../site_video.dart';
import 'nw_button.dart';
import 'nw_p2_duty.dart' show NwMapThumb;
import 'nw_p3_robots.dart';
import 'nw_site_dir.dart' show ShiftNotesPage;
import 'nw_estop_miss.dart';
import 'nw_theme.dart';
import 'nw_widgets.dart';

class NowPage extends StatefulWidget {
  final SiteApi api;

  /// 建好以后把导览要圈的几块交出去（外壳接着开导览）。
  final void Function(BuildContext context, DutyTargets targets)? onReady;

  /// 「全屏地图」、「记录与录像」：留在外壳里的层，页面只喊一声。
  final VoidCallback? onOpenMap;
  final VoidCallback? onOpenRecords;

  /// 外壳「现在」段上的 P1 计数、浅色页上的红条：这页读到报警就更新（不靠机器人列表页的实时连接）。
  final ValueNotifier<Map<String, String>>? openP1;
  const NowPage({super.key, required this.api, this.onReady, this.onOpenMap, this.onOpenRecords, this.openP1});

  static const Key okKey = Key('now-ok');
  static Key deterKey(String id) => Key('now-deter-$id');
  static const Key attnKey = Key('now-attn');
  static Key p1Key(String key) => Key('now-p1-$key');
  static Key ackKey(String key) => Key('now-ack-$key');
  static Key openKey(String key) => Key('now-open-$key');
  static const Key multiKey = Key('now-multi');
  static const Key estopCardKey = Key('now-estop-card');
  static const Key resumeAllKey = Key('now-resume-all');
  static const Key resumeAskKey = Key('now-resume-ask');
  static const Key resumeLaterKey = Key('now-resume-later');
  static const Key videoKey = Key('now-video');
  static const Key playKey = Key('now-play');
  static const Key closeKey = Key('now-video-close');
  static Key tileKey(String id) => Key('now-tile-$id');
  static Key controlKey(String id) => Key('now-control-$id');
  static const Key mapKey = Key('now-map');
  static const Key lookKey = Key('now-look');
  static const Key routeKey = Key('now-route');
  static const Key fullMapKey = Key('now-full-map');
  static const Key tonightKey = Key('now-tonight');
  static const Key opsKey = Key('now-ops');
  static Key opsRowKey(String key) => Key('now-ops-$key');
  static const Key noteKey = Key('now-note');
  static const Key noteWriteKey = Key('now-note-write');
  static const Key activityKey = Key('now-activity');
  static const Key recordsKey = Key('now-records');
  static const Key noMapKey = Key('now-no-map');
  static const Key mapWizardKey = Key('now-map-wizard');
  static const Key siteDownKey = Key('now-site-down');
  static const Key certChangedKey = Key('now-cert-changed');
  static const Key unknownKey = Key('now-robots-unknown');
  static const Key noRobotsKey = Key('now-no-robots');
  static const Key todayUnknownKey = Key('now-today-unknown');
  static const Key drillKey = Key('now-drill');
  static const Key viewerNoteKey = Key('now-viewer-note');

  @override
  State<NowPage> createState() => _NowPageState();
}

/// 每个站点上次选的哪台（这一次打开 App 里记着；按站点地址分）。
final Map<String, String> _picked = {};

class _NowPageState extends State<NowPage> with EstopMissReveal {
  final DutyTargets _t = DutyTargets();
  List<Map<String, dynamic>> _robots = const [];
  final Map<String, Map<String, dynamic>> _views = {};
  List<Alert> _alerts = const [];
  List<Map<String, dynamic>> _today = const [];
  int? _offsetMin;
  Map<String, dynamic>? _mapWiz;
  Map<String, dynamic>? _drill;
  Map<String, dynamic>? _note;
  String? _sel;
  bool _playing = false;
  bool _loaded = false;
  bool _ready = false;
  bool _robotsKnown = false;
  bool _todayKnown = false;
  bool _askResume = false;
  bool _resumeBusy = false;
  String? _error;
  DateTime? _downSince;
  bool _downShown = false;
  bool _downGraceOver = false;
  Timer? _downTimer;
  bool _downNow = false;
  bool _cert = false;
  bool _certNow = false;
  String? _errNow;
  StreamSubscription<Map<String, dynamic>>? _sub;
  Timer? _debounce;
  Timer? _poll;
  final List<Timer> _after = [];

  String get _site => widget.api.baseUrl;
  bool get _viewer => widget.api.session?.isViewer ?? true;

  @override
  void initState() {
    super.initState();
    unawaited(_reload());
    _sub = widget.api.events().listen((f) {
      final k = f['kind'];
      if (k == 'alert' || k == 'status' || k == 'mode' || k == 'event' || k == 'robot' || k == 'deterrence') _soon();
    }, onError: (Object _) {});
    _poll = Timer.periodic(const Duration(seconds: 30), (_) => unawaited(_reload()));
    patrolSent.addListener(_onSent);
  }

  void _onSent() {
    unawaited(_reload());
    for (final t in _after) {
      t.cancel();
    }
    _after
      ..clear()
      ..addAll([for (final ms in const [1000, 3000]) Timer(Duration(milliseconds: ms), () => unawaited(_reload()))]);
  }

  @override
  void dispose() {
    _sub?.cancel();
    _debounce?.cancel();
    _poll?.cancel();
    _downTimer?.cancel();
    patrolSent.removeListener(_onSent);
    for (final t in _after) {
      t.cancel();
    }
    super.dispose();
  }

  void _soon() {
    if (_debounce?.isActive ?? false) return;
    _debounce = Timer(const Duration(milliseconds: 400), () => unawaited(_reload()));
  }

  Future<T?> _try<T>(Future<T> Function() f) async {
    try {
      return await f();
    } on SiteError catch (e) {
      if (e.status == 0) {
        _downNow = true;
        if (e.certChanged) _certNow = true;
      } else if (e.status != 404) {
        _errNow = refusalText(e);
      }
      return null;
    } on FormatException {
      return null;
    }
  }

  Future<void> _reload() async {
    _downNow = false;
    _certNow = false;
    _errNow = null;
    final got = await Future.wait<Object?>([
      _try(widget.api.robots),
      _try(() => widget.api.alerts()),
      _try(widget.api.patrolsToday),
      _try(widget.api.mapWizard),
      _try(widget.api.alertTest),
      _try(() => widget.api.shiftNotes(recent: 1)),
      _try(widget.api.deterrence),
    ]);
    if (!mounted) return;
    final robots = got[0] is List ? dutyOrder((got[0] as List).cast<Map<String, dynamic>>()) : _robots;
    setState(() {
      _downSince = _downNow ? (_downSince ?? DateTime.now()) : null;
      _armDownBanner();
      _cert = _downNow && _certNow;
      _error = _errNow;
      if (got[0] is List) _robotsKnown = true;
      if (got[2] is Map) _todayKnown = true;
      _robots = robots;
      if (got[1] is List) {
        _alerts = (got[1] as List).cast<Alert>();
        widget.openP1?.value = {
          for (final a in _alerts)
            if (a.level == 'P1' && a.resolvedMs == null) a.key: alertTitle(a.kind, a.title),
        };
      }
      if (got[2] is Map) {
        _offsetMin = ((got[2] as Map)['utc_offset_min'] as num?)?.toInt();
        _today = [
          for (final x in ((got[2] as Map)['items'] as List? ?? const [])) if (x is Map) x.cast<String, dynamic>(),
        ];
      }
      if (got[3] is Map) _mapWiz = (got[3] as Map).cast<String, dynamic>();
      if (got[4] is Map) _drill = (got[4] as Map)['active'] == true ? (got[4] as Map).cast<String, dynamic>() : null;
      // 外审 App-V2-3 I4：正在驱离的（报警结案了驱离可能还在）；读不到就留着上一次的
      if (got[6] is List) _deter = {for (final x in (got[6] as List)) if (x is Map) '${x['robot_id']}': x.cast<String, dynamic>()};
      if (got[5] is List) {
        final l = got[5] as List;
        _note = l.isEmpty ? null : (l.first as Map).cast<String, dynamic>();
      }
      final ids = robots.map((r) => '${r['robot_id']}').toList();
      final want = _sel ?? _picked[_site];
      _sel = want != null && ids.contains(want) ? want : (ids.isEmpty ? null : ids.first);
      if (_heldIds().isEmpty) _askResume = false;
      _loaded = true;
    });
    // 每台的视图(最近事件、状态细节):台数不多,一起读
    final views = await Future.wait([
      for (final r in robots) _try(() => widget.api.robot('${r['robot_id']}')),
    ]);
    if (!mounted) return;
    setState(() {
      for (var i = 0; i < robots.length; i++) {
        final v = views[i];
        if (v is Map) _views['${robots[i]['robot_id']}'] = (v as Map).cast<String, dynamic>();
      }
    });
    if (!_ready) {
      _ready = true;
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) widget.onReady?.call(context, _t);
      });
    }
  }

  void _armDownBanner() {
    if (_downSince == null) {
      _downTimer?.cancel();
      _downTimer = null;
      _downGraceOver = false;
      _downShown = false;
    } else if (_downGraceOver) {
      _downShown = true;
    } else {
      _downTimer ??= Timer(kSiteDownGrace, () {
        _downTimer = null;
        _downGraceOver = true;
        if (mounted) unawaited(_reload());
      });
    }
  }

  bool get _drillOn {
    final u = _drill?['until_ms'];
    return _drill != null && (u is! num || DateTime.now().millisecondsSinceEpoch < u);
  }

  Map<String, dynamic>? _robot(String id) {
    for (final r in _robots) {
      if ('${r['robot_id']}' == id) return r;
    }
    return null;
  }

  Map<String, dynamic>? get _selRobot => _sel == null ? null : _robot(_sel!);

  /// 被叫停(全部急停按过)的几台。
  List<String> _heldIds() => [for (final r in _robots) if (r['held'] is Map) '${r['robot_id']}'];

  void _select(String id) {
    if (id == _sel) return;
    _picked[_site] = id;
    setState(() {
      _sel = id;
      _playing = false;
    });
  }

  void _say(String text) {
    if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(text)));
  }

  Future<void> _go(Widget page) async {
    await Navigator.push(context, MaterialPageRoute<void>(builder: (_) => page));
    unawaited(_reload());
  }

  Future<void> _ack(Alert a) async {
    try {
      await widget.api.ackAlert(a.key);
    } on SiteError catch (e) {
      _say(refusalText(e));
    }
    unawaited(_reload());
  }

  Future<void> _resumeAll() async {
    setState(() => _resumeBusy = true);
    final bad = <String>[];
    for (final id in _heldIds()) {
      try {
        await widget.api.resume(id);
      } on SiteError catch (e) {
        bad.add('$id: ${refusalText(e)}');
      }
    }
    if (!mounted) return;
    setState(() {
      _resumeBusy = false;
      _askResume = false;
    });
    if (bad.isNotEmpty) _say(bad.join(' '));
    unawaited(_reload());
  }

  String _hm(int ms) => hhmm(ms, _offsetMin);

  String _since(int ms) {
    final sec = ((DateTime.now().millisecondsSinceEpoch - ms) / 1000).round();
    if (sec < 60) return tr('${sec < 0 ? 0 : sec} s', '${sec < 0 ? 0 : sec} 秒');
    if (sec < 3600) return tr('${sec ~/ 60} min', '${sec ~/ 60} 分钟');
    return tr('${sec ~/ 3600} h', '${sec ~/ 3600} 小时');
  }

  String _label(String id) {
    final r = _robot(id);
    return r == null ? id : robotLabel(r);
  }

  // ------------------------------------------------------------ 顶上那一条

  /// 「全场正常」下面那一句:谁在跑什么、下一趟几点谁跑。
  String _okNote() {
    final parts = <String>[];
    for (final r in _robots) {
      final st = r['status'];
      final task = st is Map ? st['task'] : null;
      final tid = task is Map ? '${task['task_id'] ?? ''}' : null;
      final run = runningItem(_today, '${r['robot_id']}', tid);
      if (run != null) {
        final lap = lapText(run['lap'] ?? r['lap']);
        parts.add(tr('${robotLabel(r)} is on ${todayLabel(run)}${lap.isEmpty ? '' : ' · $lap'}',
            '${robotLabel(r)} 在跑 ${todayLabel(run)}${lap.isEmpty ? '' : ' $lap'}'));
        break;
      }
    }
    final nowMs = DateTime.now().millisecondsSinceEpoch;
    Map<String, dynamic>? next;
    for (final it in _today) {
      final at = it['at_ms'];
      if (at is num && at > nowMs && const {'queued', 'waiting', 'next', 'later', 'planned'}.contains('${it['state']}')) {
        if (next == null || (next['at_ms'] as num) > at) next = it;
      }
    }
    if (next != null) {
      final who = '${next['robot'] ?? ''}';
      parts.add(who.isEmpty
          ? tr('Next patrol ${_hm((next['at_ms'] as num).toInt())}', '下一次巡逻 ${_hm((next['at_ms'] as num).toInt())}')
          : tr('Next patrol ${_hm((next['at_ms'] as num).toInt())} by ${_label(who)}',
              '下一次巡逻 ${_hm((next['at_ms'] as num).toInt())} 由 ${_label(who)} 跑'));
    }
    if (parts.isEmpty) {
      final online = _robots.where(robotOnline).length;
      parts.add(tr('Robots online $online/${_robots.length}', '机器人在线 $online/${_robots.length}'));
    }
    return parts.join(' · ');
  }

  /// 正在驱离的机器人（站点那一场）：号 → 那一场。
  Map<String, Map<String, dynamic>> _deter = const {};

  /// 机器人格、要看一下那一条用的状态：驱离中算进去（外审 App-V2-3 I4）。
  RobotPhase _phaseOf(Map<String, dynamic> r) => robotPhase(r, deterring: _deter.containsKey('${r['robot_id']}'));

  /// 驱离还在的：一台一条红框，写到第几级；能派的点进驱离页（降级、转人工、结束）。有这一条就不说「全场正常」。
  Widget _deterStrip(NwColors c, String id, Map<String, dynamic> d) {
    // 外审 App-V2-4 R1：经理（能叫停）也进得去结束驱离；驱离页自己按权限摆按钮
    final can = (widget.api.session?.canDispatch ?? false) || (widget.api.session?.canAbort ?? false);
    return Material(
        color: c.surface,
        shape: Border(left: BorderSide(color: c.error, width: 4), bottom: BorderSide(color: c.outline)),
        child: InkWell(
            key: NowPage.deterKey(id),
            onTap: can
                ? () => Navigator.push(
                    context, MaterialPageRoute<void>(builder: (_) => SiteDeterrencePage(api: widget.api, robotId: id)))
                : null,
            child: Padding(
                padding: const EdgeInsets.fromLTRB(Nw.s16, 12, Nw.s16, 12),
                child: Row(children: [
                  Icon(Icons.campaign_rounded, color: c.error, size: 20),
                  const SizedBox(width: 10),
                  Expanded(
                      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Text(tr('$id deterring · ${deterSessionText(d)}', '$id 驱离中 · ${deterSessionText(d)}'),
                        style: NwText.titleSmall.copyWith(color: c.text, fontWeight: FontWeight.w700)),
                    Text(
                        can
                            ? tr('Lights and sound may still be on. Tap to see or end it.', '声光可能还开着。点进去查看或结束。')
                            : tr('Lights and sound may still be on. Guards can end it.', '声光可能还开着。由保安结束。'),
                        style: NwText.bodySmall.copyWith(color: c.textSecondary)),
                  ])),
                  if (can) Icon(Icons.chevron_right_rounded, color: c.textSecondary),
                ]))));
  }

  /// 急停、离线、吊销的机器人(被人叫停的走上面的急停卡)。有这些就不能说「全场正常」。
  List<Map<String, dynamic>> _needAttention() => [
        for (final r in _robots)
          if (const {RobotPhase.estop, RobotPhase.offline, RobotPhase.revoked}.contains(_phaseOf(r))) r,
      ];

  /// 截图核对 11-15:有机器人急停 / 离线时顶上一条琥珀「要看一下」,写清是哪台、什么状态。
  Widget _attnStrip(NwColors c, List<Map<String, dynamic>> bad) => Container(
        key: NowPage.attnKey,
        padding: const EdgeInsets.fromLTRB(Nw.s16, 12, Nw.s16, 12),
        decoration: BoxDecoration(border: Border(bottom: BorderSide(color: c.outline))),
        child: Row(children: [
          CustomPaint(size: const Size(14, 12), painter: _TriPainter(c.warning)),
          const SizedBox(width: 10),
          Expanded(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(tr('${bad.length} ${bad.length == 1 ? 'robot needs' : 'robots need'} attention', '${bad.length} 台机器人要看一下'),
                style: NwText.titleSmall.copyWith(color: c.text, fontWeight: FontWeight.w700)),
            Text([for (final r in bad) '${robotLabel(r)}: ${_phaseWord(_phaseOf(r))}'].join(' · '),
                maxLines: 2, overflow: TextOverflow.ellipsis, style: NwText.bodySmall.copyWith(color: c.textSecondary)),
          ])),
        ]),
      );

  Widget _okStrip(NwColors c) => Container(
        key: NowPage.okKey,
        padding: const EdgeInsets.fromLTRB(Nw.s16, 12, Nw.s16, 12),
        decoration: BoxDecoration(border: Border(bottom: BorderSide(color: c.outline))),
        child: Row(children: [
          Container(width: 12, height: 12, color: c.success),
          const SizedBox(width: 10),
          Expanded(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(tr('All systems normal', '全场正常'), style: NwText.titleSmall.copyWith(color: c.text, fontWeight: FontWeight.w700)),
            Text(_okNote(), maxLines: 2, overflow: TextOverflow.ellipsis, style: NwText.bodySmall.copyWith(color: c.textSecondary)),
          ])),
        ]),
      );

  /// 一件 P1 的红框事件条。
  Widget _p1Strip(NwColors c, Alert a) {
    final owned = a.ackedBy.isNotEmpty;
    final where = [
      if ('${a.context['zone'] ?? ''}'.isNotEmpty) '${a.context['zone']}',
      if (a.robot != 'site') _label(a.robot),
      _hm(a.firstMs),
    ].join(' · ');
    final ownerLine = owned
        ? tr('${a.ackedBy} is handling', '${a.ackedBy} 在处理')
        : tr('Unowned · ${_since(a.firstMs)}', '没人接手 · ${_since(a.firstMs)}');
    Widget buttons;
    if (_viewer) {
      buttons = Padding(
          padding: const EdgeInsets.only(top: 10),
          child: Text(tr('Read-only account: you can follow progress; guards and managers handle it.', '只读账号：能看进度，处理由保安和经理做。'),
              key: NowPage.viewerNoteKey, style: NwText.bodySmall.copyWith(color: c.textSecondary)));
    } else if (owned) {
      buttons = Padding(
          padding: const EdgeInsets.only(top: 12),
          child: NwButton(
              buttonKey: NowPage.openKey(a.key),
              icon: Icons.adjust_rounded,
              label: tr('Open incident', '打开这件事'),
              onPressed: () => _go(SiteAlertScenePage(api: widget.api, alert: a))));
    } else {
      buttons = Padding(
          padding: const EdgeInsets.only(top: 12),
          child: Row(children: [
            Expanded(
                child: NwButton(
                    buttonKey: NowPage.ackKey(a.key),
                    label: tr('Take ownership', '我来处理'),
                    onPressed: () => _ack(a))),
            const SizedBox(width: Nw.s8),
            Expanded(
                child: NwButton(
                    buttonKey: NowPage.openKey(a.key),
                    variant: NwButtonVariant.outline,
                    label: tr('Open incident', '打开这件事'),
                    onPressed: () => _go(SiteAlertScenePage(api: widget.api, alert: a)))),
          ]));
    }
    return Container(
      key: NowPage.p1Key(a.key),
      margin: const EdgeInsets.fromLTRB(Nw.s16, 12, Nw.s16, 0),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(color: c.surface, border: Border.all(color: c.error, width: 4), borderRadius: BorderRadius.circular(2)),
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        InkWell(
          onTap: () => _go(SiteAlertScenePage(api: widget.api, alert: a)),
          child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Container(
                width: 22,
                height: 22,
                margin: const EdgeInsets.only(top: 2),
                decoration: BoxDecoration(shape: BoxShape.circle, border: Border.all(color: c.error, width: 4))),
            const SizedBox(width: 12),
            Expanded(
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Row(crossAxisAlignment: CrossAxisAlignment.baseline, textBaseline: TextBaseline.alphabetic, children: [
                Flexible(
                    child: Text(alertTitle(a.kind, a.title),
                        maxLines: 2, overflow: TextOverflow.ellipsis, style: NwText.titleLarge.copyWith(color: c.text, fontWeight: FontWeight.w700))),
                const SizedBox(width: Nw.s8),
                Container(
                    padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 1),
                    decoration: BoxDecoration(color: c.errorSoft, borderRadius: BorderRadius.circular(2)),
                    child: Text('P1', style: NwText.labelSmall.copyWith(color: c.error, fontWeight: FontWeight.w700))),
              ]),
              Text(where, maxLines: 1, overflow: TextOverflow.ellipsis, style: NwText.bodySmall.copyWith(color: c.textSecondary)),
              const SizedBox(height: 4),
              Text(ownerLine, style: NwText.bodyMedium.copyWith(color: owned ? c.text : c.error, fontWeight: FontWeight.w600)),
            ])),
          ]),
        ),
        buttons,
      ]),
    );
  }

  /// 全部急停之后:N 台已急停,就地问「确认全部恢复?」。
  Widget _estopCard(NwColors c, List<String> held) {
    final can = widget.api.session?.canDispatch ?? false;
    final names = held.map(_label).join(', ');
    return Container(
      key: NowPage.estopCardKey,
      margin: const EdgeInsets.fromLTRB(Nw.s16, 12, Nw.s16, 0),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(color: c.surface, border: Border.all(color: c.error, width: 4), borderRadius: BorderRadius.circular(2)),
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Container(
              width: 22, height: 22, decoration: BoxDecoration(shape: BoxShape.circle, border: Border.all(color: c.error, width: 4))),
          const SizedBox(width: 12),
          Expanded(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(
                held.length == 1
                    ? tr('1 robot is stopped', '1 台机器人已急停')
                    : tr('${held.length} robots are stopped', '${held.length} 台机器人已急停'),
                style: NwText.titleLarge.copyWith(color: c.text, fontWeight: FontWeight.w700)),
            Text(tr('$names. After reset they do not resume on their own; dispatch again.', '$names。恢复后不会自己接着跑，要再派。'),
                style: NwText.bodySmall.copyWith(color: c.textSecondary)),
          ])),
        ]),
        if (can) ...[
          const SizedBox(height: 12),
          if (!_askResume)
            NwButton(
                buttonKey: NowPage.resumeAskKey,
                variant: NwButtonVariant.outline,
                label: held.length == 1 ? tr('Reset', '恢复') : tr('Reset all', '全部恢复'),
                onPressed: () => setState(() => _askResume = true))
          else
            Container(
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(color: c.bg, border: Border.all(color: c.outline)),
                child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                  Text(held.length == 1 ? tr('Reset this robot?', '确认恢复？') : tr('Reset all robots?', '确认全部恢复？'),
                      style: NwText.titleSmall.copyWith(color: c.text, fontWeight: FontWeight.w700)),
                  const SizedBox(height: 4),
                  Text(tr('They return to standby; patrols must be dispatched again.', '恢复后回到待命，巡逻要重新派。'),
                      style: NwText.bodySmall.copyWith(color: c.textSecondary)),
                  const SizedBox(height: 10),
                  Row(children: [
                    Expanded(
                        child: NwButton(
                            buttonKey: NowPage.resumeAllKey,
                            label: tr('Confirm reset', '确认恢复'),
                            onPressed: _resumeBusy ? null : _resumeAll)),
                    const SizedBox(width: Nw.s8),
                    Expanded(
                        child: NwButton(
                            buttonKey: NowPage.resumeLaterKey,
                            variant: NwButtonVariant.outline,
                            label: tr('Not now', '先不恢复'),
                            onPressed: () => setState(() => _askResume = false))),
                  ]),
                ])),
        ],
      ]),
    );
  }

  /// 还没有地图(W54):管理员一张「开始建图」,别人一句话。
  Widget? _noMap(NwColors c) {
    final w = _mapWiz;
    if (w == null || (w['maps'] as num? ?? 1) > 0) return null;
    final admin = widget.api.session?.canManageMaps ?? false;
    final wiz = w['wizard'] is Map ? (w['wizard'] as Map) : null;
    final step = wiz == null ? 0 : wizardSteps.indexOf('${wiz['step']}') + 1;
    final first = _robots.isEmpty ? '' : robotLabel(_robots.first);
    return Container(
      key: NowPage.noMapKey,
      margin: const EdgeInsets.fromLTRB(Nw.s16, 12, Nw.s16, 0),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(color: c.surface, border: Border.all(color: c.outline)),
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Container(width: 10, height: 10, margin: const EdgeInsets.only(top: 6), decoration: BoxDecoration(shape: BoxShape.circle, color: c.primary)),
          const SizedBox(width: 10),
          Expanded(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(tr('The site has no map yet', '站点还没有地图'), style: NwText.titleMedium.copyWith(color: c.text, fontWeight: FontWeight.w700)),
            Text(
                wiz != null
                    ? tr('${wiz['by']} is mapping (step $step of 7).', '${wiz['by']} 正在建图（第 $step / 7 步）。')
                    : admin
                        ? tr('Robots need a map before they can patrol. Walk $first around once, about 20 minutes.',
                            '机器人要先有图才能巡逻。用 $first 走一圈，大约 20 分钟。')
                        : tr('Robots need a map before they can patrol. Ask an administrator to build it.', '机器人要先有图才能巡逻，请管理员建图。'),
                style: NwText.bodySmall.copyWith(color: c.textSecondary)),
          ])),
        ]),
        if (admin) ...[
          const SizedBox(height: 12),
          NwButton(
              buttonKey: NowPage.mapWizardKey,
              label: wiz != null ? tr('Continue mapping', '继续建图') : tr('Start mapping', '开始建图'),
              onPressed: () async {
                await openMapWizard(context, widget.api);
                await _reload();
              }),
        ],
      ]),
    );
  }

  // ------------------------------------------------------------ 画面

  Widget _video(NwColors c) {
    final id = _sel!;
    final r = _selRobot!;
    if (_playing) {
      return Column(key: NowPage.videoKey, crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        Container(
            color: const Color(0xFF0A0C0E),
            padding: const EdgeInsets.fromLTRB(Nw.s16, 6, Nw.s8, 6),
            child: Row(children: [
              Expanded(
                  child: Text(tr('${robotLabel(r)} · live', '${robotLabel(r)} · 实时'),
                      style: NwText.labelLarge.copyWith(color: c.text, fontWeight: FontWeight.w600))),
              TextButton.icon(
                  key: NowPage.closeKey,
                  onPressed: () => setState(() => _playing = false),
                  icon: const Icon(Icons.close_rounded, size: 18),
                  label: Text(tr('Stop video', '关闭画面'))),
            ])),
        SiteVideo(key: ValueKey<String>('now-video-$id'), api: widget.api, robotId: id),
      ]);
    }
    return AspectRatio(
      key: NowPage.videoKey,
      aspectRatio: 16 / 9,
      child: Material(
        color: const Color(0xFF07080A),
        child: InkWell(
          key: NowPage.playKey,
          onTap: () => setState(() => _playing = true),
          child: Stack(children: [
            Positioned(
                left: 0,
                right: 0,
                top: 0,
                child: Container(
                    color: const Color(0xB30A0C0E),
                    padding: const EdgeInsets.symmetric(horizontal: Nw.s16, vertical: 6),
                    child: Row(children: [
                      Expanded(
                          child: Text(tr('${robotLabel(r)} · Front camera', '${robotLabel(r)} · 前摄像头'),
                              maxLines: 1, overflow: TextOverflow.ellipsis, style: NwText.labelLarge.copyWith(color: c.text, fontWeight: FontWeight.w600))),
                      for (final (i, t) in [tr('Front', '前'), tr('Rear', '后'), tr('Thermal', '热像')].indexed)
                        Container(
                            margin: const EdgeInsets.only(left: 4),
                            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                            decoration: BoxDecoration(
                                color: i == 0 ? c.primary : Colors.transparent,
                                border: Border.all(color: i == 0 ? c.primary : c.textMuted),
                                borderRadius: BorderRadius.circular(2)),
                            child: Text(t, style: NwText.labelSmall.copyWith(color: i == 0 ? c.onPrimary : c.text, fontWeight: FontWeight.w600))),
                    ]))),
            Center(
                child: Column(mainAxisSize: MainAxisSize.min, children: [
              Icon(Icons.play_arrow_rounded, size: 40, color: c.text),
              const SizedBox(height: 4),
              Text(tr('Tap to watch live', '点开看实时画面'), style: NwText.bodyMedium.copyWith(color: c.textSecondary)),
            ])),
          ]),
        ),
      ),
    );
  }

  // ------------------------------------------------------------ 机器人格

  /// 牌子:绿方块 / 琥珀三角 / 红圈 / 灰圈。
  Widget _sign(NwColors c, RobotPhase p, {double size = 11}) {
    switch (p) {
      case RobotPhase.estop:
      case RobotPhase.deterring:
      case RobotPhase.offline:
      case RobotPhase.held:
        return Container(width: size + 2, height: size + 2, decoration: BoxDecoration(shape: BoxShape.circle, border: Border.all(color: c.error, width: 3)));
      case RobotPhase.lowBattery:
        return CustomPaint(size: Size(size + 2, size), painter: _TriPainter(c.warning));
      case RobotPhase.revoked:
      case RobotPhase.unknown:
        return Container(width: size, height: size, decoration: BoxDecoration(shape: BoxShape.circle, border: Border.all(color: c.textMuted, width: 2)));
      case RobotPhase.working:
      case RobotPhase.charging:
      case RobotPhase.idle:
      case RobotPhase.notStanding:
        return Container(width: size - 2, height: size - 2, color: c.success);
    }
  }

  /// 格子上的状态词(比药丸的更口语:待命、巡逻中、充电中……)。
  String _phaseWord(RobotPhase p) => switch (p) {
        RobotPhase.working => tr('Patrolling', '巡逻中'),
        RobotPhase.charging => tr('Charging', '充电中'),
        RobotPhase.idle => tr('Standby', '待命'),
        RobotPhase.held => tr('Stopped', '已急停'),
        RobotPhase.estop => tr('E-STOP', '急停'),
        RobotPhase.lowBattery => tr('Low battery', '低电'),
        RobotPhase.offline => tr('Offline', '离线'),
        RobotPhase.deterring => tr('Deterring', '驱离中'),
        RobotPhase.notStanding => tr('Not standing', '没站起来'),
        RobotPhase.revoked => tr('Revoked', '已吊销'),
        RobotPhase.unknown => tr('No data', '未上报'),
      };

  /// 格子第二行:在跑哪条第几圈 / 回充 / 老的那一行。
  String _tileNote(Map<String, dynamic> r) {
    final st = r['status'];
    final task = st is Map ? st['task'] : null;
    final tid = task is Map ? '${task['task_id'] ?? ''}' : null;
    final run = runningItem(_today, '${r['robot_id']}', tid);
    if (run != null) {
      final lap = lapText(run['lap'] ?? r['lap']);
      final end = run['end_ms'] is num ? tr(' · ends ${_hm((run['end_ms'] as num).toInt())}', ' · 约 ${_hm((run['end_ms'] as num).toInt())} 走完') : '';
      return '${todayLabel(run)}${lap.isEmpty ? '' : ' · $lap'}$end';
    }
    if (r['held'] is Map) return tr('Stopped by ${(r['held'] as Map)['by']}', '${(r['held'] as Map)['by']} 叫停的');
    if (r['manual_only'] is Map) return tr('Manual only', '仅限手动');
    final line = robotStatusLine(r);
    // 「在线 · 」是格子上牌子已经说了的
    return line.replaceFirst('${tr('Online', '在线')} · ', '');
  }

  Widget _tile(NwColors c, Map<String, dynamic> r) {
    final id = '${r['robot_id']}';
    final on = id == _sel;
    final p = _phaseOf(r);
    final b = robotBattery(r);
    final low = p == RobotPhase.lowBattery || (b != null && b < NwBattery.lowBelow);
    return Material(
      key: NowPage.tileKey(id),
      color: on ? c.surfaceVariant : c.surface,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(2), side: BorderSide(color: on ? c.primary : c.outline)),
      child: InkWell(
        onTap: () => _select(id),
        child: Padding(
          padding: const EdgeInsets.fromLTRB(12, 10, 12, 10),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, mainAxisSize: MainAxisSize.min, children: [
            // 稿 N-normal:第一行名字 + 电量;第二行牌子 + 状态词;第三行在干什么
            Row(children: [
              Expanded(
                  child: Text(robotLabel(r),
                      maxLines: 1, overflow: TextOverflow.ellipsis, style: NwText.titleLarge.copyWith(color: c.text, fontWeight: FontWeight.w700))),
              if (b != null)
                Text('${b.round()}%',
                    style: NwText.labelLarge.copyWith(color: low ? c.warning : c.text, fontWeight: FontWeight.w700, fontFamily: NwFont.mono)),
            ]),
            const SizedBox(height: 4),
            Row(children: [
              _sign(c, p),
              const SizedBox(width: 6),
              Expanded(
                  child: Text(_phaseWord(p),
                      maxLines: 1, overflow: TextOverflow.ellipsis, style: NwText.labelLarge.copyWith(color: c.text, fontWeight: FontWeight.w600))),
            ]),
            const SizedBox(height: 2),
            Text(_tileNote(r), maxLines: 1, overflow: TextOverflow.ellipsis, style: NwText.bodySmall.copyWith(color: c.textSecondary)),
            if (!_viewer) ...[
              const SizedBox(height: 6),
              InkWell(
                key: NowPage.controlKey(id),
                onTap: () => _go(SiteRobotPage(api: widget.api, robotId: id)),
                child: Row(mainAxisSize: MainAxisSize.min, children: [
                  Text(tr('Control', '控制'), style: NwText.labelLarge.copyWith(color: c.tertiary, fontWeight: FontWeight.w600)),
                  Icon(Icons.chevron_right_rounded, size: 16, color: c.tertiary),
                ]),
              ),
            ],
          ]),
        ),
      ),
    );
  }

  Widget _tiles(NwColors c) {
    final rows = <Widget>[];
    for (var i = 0; i < _robots.length; i += 2) {
      final a = _tile(c, _robots[i]);
      final b = i + 1 < _robots.length ? _tile(c, _robots[i + 1]) : null;
      // 一行两格等高:列表里高度没上限,stretch 要先量出两格里高的那格
      rows.add(IntrinsicHeight(
          child: Row(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        Expanded(child: a),
        const SizedBox(width: Nw.s8),
        Expanded(child: b ?? const SizedBox.shrink()),
      ])));
      if (b != null || i + 2 < _robots.length) rows.add(const SizedBox(height: Nw.s8));
    }
    return Column(key: _t.chips, crossAxisAlignment: CrossAxisAlignment.stretch, children: rows);
  }

  // ------------------------------------------------------------ 小地图

  (String, String)? _mapOf(Map<String, dynamic>? r) {
    final caps = r?['capabilities'];
    final tasks = caps is Map ? caps['tasks'] : null;
    final rc = tasks is Map ? tasks['running_config'] : null;
    if (rc is Map && '${rc['map_id'] ?? ''}'.isNotEmpty && '${rc['map_version'] ?? ''}'.isNotEmpty) {
      return ('${rc['map_id']}', '${rc['map_version']}');
    }
    final p = tasks is Map ? tasks['patrol'] : null;
    if (p is Map && '${p['map_id'] ?? ''}'.isNotEmpty && '${p['map_version'] ?? ''}'.isNotEmpty) return ('${p['map_id']}', '${p['map_version']}');
    return null;
  }

  Widget? _mapBlock(NwColors c) {
    final m = _mapOf(_selRobot) ?? _mapOf(_robots.isEmpty ? null : _robots.first);
    if (m == null) return null;
    final label = [for (final r in _robots) '${robotLabel(r)} · ${_phaseWord(_phaseOf(r))}'].join(' · ');
    final can = widget.api.session?.canDispatch ?? false;
    return Column(key: _t.status, crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      NwMapThumb(
          key: ValueKey<String>('now-map ${m.$1}:${m.$2}'),
          tapKey: NowPage.mapKey,
          height: 200,
          load: () => loadMapPicture(widget.api, m.$1, m.$2),
          label: label,
          action: tr('Full-screen map', '全屏地图'),
          onTap: () => widget.onOpenMap?.call()),
      if (can) ...[
        const SizedBox(height: Nw.s8),
        Row(children: [
          Expanded(
              child: NwButton(
                  buttonKey: NowPage.lookKey,
                  variant: NwButtonVariant.outline,
                  size: NwButtonSize.small,
                  icon: Icons.place_outlined,
                  label: tr('Spot check', '派去看一眼'),
                  onPressed: () => widget.onOpenMap?.call())),
          const SizedBox(width: Nw.s8),
          Expanded(
              child: NwButton(
                  buttonKey: NowPage.routeKey,
                  variant: NwButtonVariant.outline,
                  size: NwButtonSize.small,
                  icon: Icons.route_outlined,
                  label: tr('One-off route', '临时路线'),
                  onPressed: () => widget.onOpenMap?.call())),
          const SizedBox(width: Nw.s8),
          SizedBox(
              width: 44,
              height: 36,
              child: OutlinedButton(
                  key: NowPage.fullMapKey,
                  style: OutlinedButton.styleFrom(padding: EdgeInsets.zero, minimumSize: const Size(44, 36)),
                  onPressed: () => widget.onOpenMap?.call(),
                  child: Icon(Icons.open_in_full_rounded, size: 18, color: c.text))),
        ]),
      ],
    ]);
  }

  // ------------------------------------------------------------ 下面几段

  Widget _section(NwColors c, String title, Widget body, {Widget? right, Key? key, EdgeInsets? pad}) => Container(
        key: key,
        padding: pad ?? const EdgeInsets.fromLTRB(Nw.s16, 14, Nw.s16, 14),
        decoration: BoxDecoration(border: Border(bottom: BorderSide(color: c.outline))),
        child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          Row(children: [
            Expanded(child: Text(title, style: NwText.titleMedium.copyWith(color: c.text, fontWeight: FontWeight.w700))),
            ?right,
          ]),
          const SizedBox(height: 10),
          body,
        ]),
      );

  Widget _ops(NwColors c) {
    final rows = _alerts.where((a) => a.level != 'P1' && alertNeedsAttention(a)).toList();
    return _section(
        c,
        rows.isEmpty ? tr('Equipment & operations', '设备与运营') : tr('Equipment & operations ${rows.length}', '设备与运营 ${rows.length}'),
        key: NowPage.opsKey,
        pad: const EdgeInsets.fromLTRB(Nw.s16, 14, Nw.s16, 4),
        rows.isEmpty
            ? Padding(padding: const EdgeInsets.only(bottom: 10), child: Text(tr('Nothing open.', '没有要处理的。'), style: NwText.bodySmall.copyWith(color: c.textSecondary)))
            : Column(children: [
                for (final a in rows)
                  InkWell(
                    key: NowPage.opsRowKey(a.key),
                    onTap: () => _go(SiteAlertScenePage(api: widget.api, alert: a)),
                    child: Container(
                      constraints: const BoxConstraints(minHeight: 52),
                      padding: const EdgeInsets.symmetric(vertical: 6),
                      decoration: BoxDecoration(border: Border(top: BorderSide(color: c.outline))),
                      child: Row(children: [
                        SizedBox(
                            width: 22,
                            child: a.level == 'P2'
                                ? Container(width: 13, height: 13, decoration: BoxDecoration(shape: BoxShape.circle, border: Border.all(color: c.error, width: 3)))
                                : CustomPaint(size: const Size(13, 11), painter: _TriPainter(c.warning))),
                        const SizedBox(width: Nw.s8),
                        Expanded(
                            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                          Text(alertTitle(a.kind, a.title),
                              maxLines: 1, overflow: TextOverflow.ellipsis, style: NwText.bodyMedium.copyWith(color: c.text, fontWeight: FontWeight.w600)),
                          Text(
                              [
                                if ('${a.context['zone'] ?? ''}'.isNotEmpty) '${a.context['zone']}',
                                if (a.robot != 'site') _label(a.robot),
                                _hm(a.firstMs),
                                if (a.ackedBy.isNotEmpty) tr('${a.ackedBy} handling', '${a.ackedBy} 处理中'),
                              ].join(' · '),
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style: NwText.bodySmall.copyWith(color: c.textSecondary)),
                        ])),
                        Icon(Icons.chevron_right_rounded, color: c.textMuted),
                      ]),
                    ),
                  ),
              ]));
  }

  Widget _lastNote(NwColors c) {
    final n = _note;
    final at = n?['at_ms'] is num ? _hm((n!['at_ms'] as num).toInt()) : '';
    return _section(
        c,
        n == null ? tr('Handover note', '上一班留言') : tr('Last shift note · ${n['author'] ?? ''} $at', '上一班留言 · ${n['author'] ?? ''} $at'),
        key: NowPage.noteKey,
        Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(n == null ? tr('No note from the last shift.', '上一班没有留言。') : '${n['text'] ?? ''}',
              style: NwText.bodyMedium.copyWith(color: n == null ? c.textSecondary : c.text)),
          if (!_viewer) ...[
            const SizedBox(height: 10),
            Align(
                alignment: Alignment.centerLeft,
                child: NwButton(
                    buttonKey: NowPage.noteWriteKey,
                    variant: NwButtonVariant.outline,
                    size: NwButtonSize.small,
                    icon: Icons.sticky_note_2_outlined,
                    label: tr('Leave a note for the next shift', '给下一班留言'),
                    onPressed: () => _go(ShiftNotesPage(api: widget.api)))),
          ],
        ]));
  }

  Widget _activity(NwColors c) {
    final all = <(String, String, String)>[]; // (排序键, 时间, 话)
    for (final e in _views.entries) {
      for (final ev in compactEvents((e.value['events'] as List? ?? const []).whereType<Map>().toList())) {
        final when = robotEventTime(ev['stamp']);
        all.add(('${ev['stamp']}', when, '${_label(e.key)} ${robotEventTitle('${ev['kind']}', ev['data'] is Map ? (ev['data'] as Map).cast<String, dynamic>() : null)}'));
      }
    }
    all.sort((a, b) => b.$1.compareTo(a.$1));
    final rows = all.take(4).toList();
    return _section(
        c,
        tr('Recent activity', '最新活动'),
        key: NowPage.activityKey,
        right: InkWell(
            key: NowPage.recordsKey,
            onTap: () => widget.onOpenRecords?.call(),
            child: Text(tr('Records & recordings', '记录与录像'), style: NwText.labelLarge.copyWith(color: c.tertiary, fontWeight: FontWeight.w600))),
        rows.isEmpty
            ? Text(tr('Nothing yet.', '还没有。'), style: NwText.bodySmall.copyWith(color: c.textSecondary))
            : Column(children: [
                for (final r in rows)
                  Container(
                      constraints: const BoxConstraints(minHeight: 36),
                      alignment: Alignment.centerLeft,
                      child: Row(children: [
                        SizedBox(width: 52, child: Text(_shortTime(r.$2), style: NwText.bodySmall.copyWith(color: c.textMuted, fontFamily: NwFont.mono))),
                        const SizedBox(width: Nw.s8),
                        Expanded(child: Text(r.$3, maxLines: 2, overflow: TextOverflow.ellipsis, style: NwText.bodyMedium.copyWith(color: c.text))),
                      ])),
              ]));
  }

  /// `10-31 01:29:51` / `01:29:51` → `01:29`。
  String _shortTime(String s) {
    final m = RegExp(r'(\d{2}):(\d{2})').firstMatch(s);
    return m == null ? s : '${m.group(1)}:${m.group(2)}';
  }

  @override
  Widget build(BuildContext context) {
    final c = Nw.of(context);
    final p1 = _alerts.where((a) => a.level == 'P1' && a.resolvedMs == null).toList();
    final held = _heldIds();
    final attn = _needAttention();
    final hasRobot = _sel != null && _selRobot != null;
    final noMap = _noMap(c);
    final map = hasRobot ? _mapBlock(c) : null;
    // 自己带一层 Material(深色底):单独推出来、或外壳换了也有点按水波和文字底色
    return Material(
        color: c.bg,
        child: RefreshIndicator(
      onRefresh: _reload,
      // 横屏:右下角「全部急停」方块(88 + 边距)盖着右边一列,内容让开;竖屏只在底下留出空
      child: ListView(
          padding: EdgeInsets.only(bottom: 120, right: MediaQuery.sizeOf(context).aspectRatio > 1.3 ? 120 : 0),
          children: [
        if (_downSince != null && _cert)
          Padding(
              padding: const EdgeInsets.fromLTRB(Nw.s16, 12, Nw.s16, 0),
              child: NwNotice(
                  key: NowPage.certChangedKey,
                  tone: NwTone.error,
                  icon: Icons.gpp_bad_rounded,
                  text: tr(
                      "$certChangedText Robot status here is out of date and alerts won't arrive. To update the code: leave this site, open it in the site list, then tap New site code on the sign-in page.",
                      '$certChangedText这里机器人的状态是旧的，报警也收不到。更新站点码：退出这个站点，在站点列表里点它，登录页上点「新站点码」。')))
        else if (_downSince != null && _downShown)
          Padding(
              padding: const EdgeInsets.fromLTRB(Nw.s16, 12, Nw.s16, 0),
              child: NwNotice(
                  key: NowPage.siteDownKey,
                  tone: NwTone.error,
                  icon: Icons.cloud_off_rounded,
                  text: tr(
                      "Can't reach the site host since ${_hmOf(_downSince!)}. Robot status here is out of date and alerts won't arrive. Check the site host is on and this phone is on the site's network.",
                      '从 ${_hmOf(_downSince!)} 起连不上站点主机：这里机器人的状态是旧的，报警也收不到。请检查站点主机是否开着、手机是否连在站点的网络上。'))),
        if (_error != null) Padding(padding: const EdgeInsets.fromLTRB(Nw.s16, 12, Nw.s16, 0), child: NwNotice(text: _error!, tone: NwTone.error)),
        if (_drillOn)
          Padding(
              padding: const EdgeInsets.fromLTRB(Nw.s16, 12, Nw.s16, 0),
              child: NwNotice(
                  key: NowPage.drillKey,
                  tone: NwTone.warning,
                  text: tr(
                      'Alarm drill until ${_drillEnd()}: alarms whose title starts with "TEST:" are the drill. Handle them as usual.',
                      '报警演练中（到 ${_drillEnd()}）：标题带「测试：」的报警是演练，照常处理即可。'))),
        // 急停没确认(稿 N-refuse):比别的都先说
        EstopMissCards(api: widget.api),
        // 顶上那一条:P1 事件条 > 急停卡 > 全场正常
        KeyedSubtree(
            key: _t.mode,
            child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
              if (p1.length > 1)
                Padding(
                    key: NowPage.multiKey,
                    padding: const EdgeInsets.fromLTRB(Nw.s16, 12, Nw.s16, 0),
                    child: Row(children: [
                      Container(width: 14, height: 14, decoration: BoxDecoration(shape: BoxShape.circle, border: Border.all(color: c.error, width: 3))),
                      const SizedBox(width: Nw.s8),
                      Expanded(
                          child: Text(tr('${p1.length} security incidents in progress', '${p1.length} 件安全事件同时在处理'),
                              style: NwText.titleSmall.copyWith(color: c.text, fontWeight: FontWeight.w700))),
                      Text(tr('By detection time', '按发现时间'), style: NwText.bodySmall.copyWith(color: c.textSecondary)),
                    ])),
              for (final a in p1) _p1Strip(c, a),
              if (held.isNotEmpty) _estopCard(c, held),
              for (final e in _deter.entries) _deterStrip(c, e.key, e.value),
              ?noMap,
              if (p1.isEmpty && held.isEmpty && _deter.isEmpty && _robotsKnown)
                if (attn.isEmpty) _okStrip(c) else _attnStrip(c, attn)
              else if (p1.isNotEmpty || held.isNotEmpty || _deter.isNotEmpty)
                const SizedBox(height: 12),
            ])),
        if (!_loaded)
          const Padding(padding: EdgeInsets.all(Nw.s24), child: Center(child: CircularProgressIndicator()))
        else if (!hasRobot && !_robotsKnown)
          Padding(
              padding: const EdgeInsets.all(Nw.s16),
              child: NwNotice(key: NowPage.unknownKey, tone: NwTone.warning, text: tr("Status unknown: the robot list couldn't be read from the site.", '状态未知：读不到站点上的机器人列表。')))
        else if (!hasRobot)
          Padding(
              padding: const EdgeInsets.all(Nw.s16),
              child: NwNotice(key: NowPage.noRobotsKey, text: tr('No robots on this site yet. An administrator adds them under Site → Robots.', '站点还没有机器人，请管理员在「现场 → 机器人」添加。')))
        else ...[
          KeyedSubtree(key: _t.video, child: _video(c)),
          Container(
              padding: const EdgeInsets.fromLTRB(Nw.s16, 12, Nw.s16, 12),
              decoration: BoxDecoration(border: Border(bottom: BorderSide(color: c.outline))),
              child: _tiles(c)),
          if (map != null)
            Container(
                padding: const EdgeInsets.fromLTRB(Nw.s16, 12, Nw.s16, 12),
                decoration: BoxDecoration(border: Border(bottom: BorderSide(color: c.outline))),
                child: map),
        ],
        KeyedSubtree(
            key: _t.today,
            child: _section(
                c,
                tr("Tonight's patrols", '今晚巡逻'),
                key: NowPage.tonightKey,
                right: Text(_today.isEmpty ? '' : tr('${_today.length} runs', '${_today.length} 趟'), style: NwText.bodySmall.copyWith(color: c.textSecondary)),
                _todayKnown || _downSince == null
                    ? TodayPatrolList(api: widget.api, items: _today, onChanged: _reload, offsetMin: _offsetMin)
                    : Text(tr("Unknown: today's patrols couldn't be read from the site.", '未知：读不到站点上今天的巡逻。'),
                        key: NowPage.todayUnknownKey, style: NwText.bodyMedium.copyWith(color: c.textSecondary)))),
        KeyedSubtree(key: _t.actions, child: _ops(c)),
        _lastNote(c),
        _activity(c),
      ]),
    ));
  }

  String _drillEnd() {
    final u = _drill?['until_ms'];
    return u is num ? _hm(u.toInt()) : '?';
  }
}

String _hmOf(DateTime t) => '${t.hour.toString().padLeft(2, '0')}:${t.minute.toString().padLeft(2, '0')}';

class _TriPainter extends CustomPainter {
  final Color color;
  const _TriPainter(this.color);
  @override
  void paint(Canvas canvas, Size s) {
    final p = Path()
      ..moveTo(s.width / 2, 0)
      ..lineTo(s.width, s.height)
      ..lineTo(0, s.height)
      ..close();
    canvas.drawPath(p, Paint()..color = color);
  }

  @override
  bool shouldRepaint(_TriPainter old) => old.color != color;
}
