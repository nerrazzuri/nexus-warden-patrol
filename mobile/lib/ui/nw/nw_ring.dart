// App V2 来报警全屏页（稿 N-ring）：锁屏 / 后台时，后台值守的全屏通知把 App 拉起来，直接是这一页。
// 一直响到有人接手；别人接手了这页自己关（响铃是后台值守那边管的：站点说有人确认了才停）。
//
// 三个按钮等宽：我来处理（确认 → 进「这件事」）、只看画面（不确认，进「这件事」，接着响）、静音 2 分钟
// （只是这台手机这一会儿不出声，到点没人接手接着响）。不弹窗。
import 'dart:async';

import 'package:flutter/material.dart';

import '../../l10n.dart';
import '../../model/alert.dart';
import '../../net/background_watch.dart' as bg;
import '../../net/site_client.dart';
import '../site_alert_scene.dart';
import 'nw_theme.dart';

class RingPage extends StatefulWidget {
  final SiteApi api;
  final Alert alert;
  final String site;
  final DateTime Function() now;

  /// 「静音 2 分钟」交给后台值守（测试里换掉）。回 false = 没在后台值守，静不了。
  final Future<bool> Function(String key) mute;

  /// 这一页处理完了（锁屏上不再显示 App）。
  final Future<void> Function() done;

  /// 多久问一次站点：别人接手了就关。
  final Duration every;

  const RingPage(
      {super.key,
      required this.api,
      required this.alert,
      required this.site,
      this.now = DateTime.now,
      this.mute = bg.muteRing,
      this.done = bg.ringDone,
      this.every = const Duration(seconds: 3)});

  static const Key takeKey = Key('ring-take');
  static const Key videoKey = Key('ring-video');
  static const Key muteKey = Key('ring-mute');
  static const Key msgKey = Key('ring-msg');

  @override
  State<RingPage> createState() => _RingPageState();
}

class _RingPageState extends State<RingPage> {
  late Alert _a = widget.alert;
  Timer? _poll;
  String _msg = '';
  int? _mutedUntil;
  bool _busy = false;
  bool _left = false;

  @override
  void initState() {
    super.initState();
    _poll = Timer.periodic(widget.every, (_) => unawaited(_check()));
  }

  @override
  void dispose() {
    _poll?.cancel();
    if (!_left) unawaited(widget.done());
    super.dispose();
  }

  /// 别人接手了、关了：这一页没事了，回去。
  Future<void> _check() async {
    try {
      final rows = await widget.api.alerts(all: true);
      final now = rows.where((x) => x.key == _a.key);
      if (!mounted || now.isEmpty) return;
      final got = now.first;
      if (got.acked || got.resolved) {
        _leave();
        return;
      }
      setState(() => _a = got);
    } on Object {
      return; // 问不到：接着响，下一拍再问
    }
  }

  void _leave() {
    if (_left || !mounted) return;
    _left = true;
    unawaited(widget.done());
    // 外审 App-V2-1 #6：只关自己这一页。上面可能压着另一件报警的来报警页，不能弹栈顶
    final route = ModalRoute.of(context);
    if (route == null) return;
    if (route.isCurrent) {
      Navigator.of(context).pop();
    } else if (route.isActive) {
      Navigator.of(context).removeRoute(route);
    }
  }

  void _open() {
    _left = true;
    unawaited(widget.done());
    Navigator.of(context).pushReplacement(
        MaterialPageRoute<void>(builder: (_) => SiteAlertScenePage(api: widget.api, alert: _a)));
  }

  Future<void> _take() async {
    if (_busy) return;
    setState(() => _busy = true);
    try {
      final r = await widget.api.ackAlert(_a.key);
      if (!mounted) return;
      final got = r['alert'] is Map ? Alert.fromWire(Map<String, dynamic>.from(r['alert'] as Map)) : null;
      if (got != null && got.key == _a.key) _a = got;
      _open();
    } on SiteError catch (e) {
      if (mounted) setState(() => _msg = tr('Not taken: $e', '没接上：$e'));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _mute() async {
    // 前台的铃（App 开着时机器人列表页那一套）和后台通知的铃静到同一个点（外审 App-V2-1 #5）
    final until = widget.now().add(const Duration(minutes: 2)).millisecondsSinceEpoch;
    bg.ringMutedUntil[_a.key] = until;
    await widget.mute(_a.key);
    if (!mounted) return;
    setState(() {
      _mutedUntil = until;
      _msg = tr('Muted on this phone until ${_hm(until)}. It rings again if no one takes ownership.',
          '这台手机静音到 ${_hm(until)}，到时还没人接手会接着响。');
    });
  }

  static String _hm(int ms) {
    final d = DateTime.fromMillisecondsSinceEpoch(ms);
    return '${d.hour.toString().padLeft(2, '0')}:${d.minute.toString().padLeft(2, '0')}';
  }

  Widget _btn(Key key, String label, VoidCallback? on, {bool primary = false}) {
    final c = Nw.of(context);
    final shape = RoundedRectangleBorder(borderRadius: BorderRadius.circular(2));
    const size = Size(48, 56);
    final child = Text(label, textAlign: TextAlign.center, maxLines: 2, overflow: TextOverflow.ellipsis);
    return primary
        ? FilledButton(
            key: key,
            style: FilledButton.styleFrom(
                backgroundColor: c.error,
                foregroundColor: c.onError,
                minimumSize: size,
                textStyle: NwText.titleMedium,
                shape: shape),
            onPressed: on,
            child: child)
        : OutlinedButton(
            key: key,
            style: OutlinedButton.styleFrom(
                foregroundColor: c.text,
                disabledForegroundColor: c.textMuted,
                side: BorderSide(color: c.textMuted),
                minimumSize: size,
                padding: const EdgeInsets.symmetric(horizontal: Nw.s8),
                textStyle: NwText.titleSmall,
                shape: shape),
            onPressed: on,
            child: child);
  }

  @override
  Widget build(BuildContext context) {
    return Theme(
        data: nwTheme(Brightness.dark),
        child: Builder(builder: (context) {
          final c = Nw.of(context);
          final ctx = _a.context;
          final where = [
            _a.level,
            if ('${ctx['camera'] ?? ''}'.isNotEmpty) '${ctx['camera']}',
            if ('${ctx['zone'] ?? ''}'.isNotEmpty) '${ctx['zone']}',
            if ('${ctx['exit'] ?? ''}'.isNotEmpty) tr('heading to ${ctx['exit']}', '往 ${ctx['exit']} 去'),
          ].join(' · ');
          final point = ctx['intercept'] is Map ? '${(ctx['intercept'] as Map)['name'] ?? ''}' : '';
          final robot = _a.robot.isNotEmpty && _a.robot != 'site' && !_a.robot.startsWith('cctv:') ? _a.robot : '';
          final dispatch = robot.isEmpty
              ? ''
              : point.isNotEmpty
                  ? tr('$robot dispatched to $point', '$robot 已派去 $point')
                  : tr('Robot $robot is on scene', '机器人 $robot 在现场');
          final handle = widget.api.session?.canHandleAlerts ?? false;
          return Scaffold(
              backgroundColor: c.bg,
              body: SafeArea(
                  child: Container(
                      margin: const EdgeInsets.all(Nw.s16),
                      padding: const EdgeInsets.all(Nw.s16),
                      decoration: BoxDecoration(
                          border: Border.all(color: c.error, width: 4), borderRadius: BorderRadius.circular(2)),
                      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                        Text('${widget.site} · ${_hm(_a.firstMs)}',
                            style: NwText.labelLarge.copyWith(color: c.textSecondary)),
                        const Spacer(),
                        Icon(Icons.notifications_active_rounded, color: c.error, size: 48),
                        const SizedBox(height: Nw.s16),
                        Text(alertTitle(_a.kind, _a.title),
                            style: NwText.headlineSmall.copyWith(color: c.text, fontWeight: FontWeight.w700)),
                        const SizedBox(height: Nw.s8),
                        Text(where, style: NwText.bodyLarge.copyWith(color: c.error, fontWeight: FontWeight.w600)),
                        if (dispatch.isNotEmpty) ...[
                          const SizedBox(height: Nw.s8),
                          Text(dispatch, style: NwText.bodyLarge.copyWith(color: c.text)),
                        ],
                        const SizedBox(height: Nw.s16),
                        Text(
                            tr('Rings until someone takes ownership; stops automatically when another user does.',
                                '一直响到有人接手；别人接手了这里自动停。'),
                            style: NwText.bodyMedium.copyWith(color: c.textSecondary)),
                        const Spacer(),
                        if (_msg.isNotEmpty) ...[
                          Text(_msg, key: RingPage.msgKey, style: NwText.bodyMedium.copyWith(color: c.text)),
                          const SizedBox(height: Nw.s16),
                        ],
                        if (handle)
                          _btn(RingPage.takeKey, tr('Take ownership', '我来处理'), _busy ? null : () => unawaited(_take()),
                              primary: true),
                        const SizedBox(height: Nw.s8),
                        Row(children: [
                          Expanded(child: _btn(RingPage.videoKey, tr('View video only', '只看画面'), _open)),
                          const SizedBox(width: Nw.s8),
                          Expanded(
                              child: _btn(RingPage.muteKey, tr('Mute 2 min', '静音 2 分钟'),
                                  _mutedUntil == null ? () => unawaited(_mute()) : null)),
                        ]),
                      ]))));
        }));
  }
}
