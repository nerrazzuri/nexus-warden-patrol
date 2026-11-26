// 用户 11-25：机器人看见人，不能只是告警 —— 打开 App 直接横屏、整屏放看到人的那一路实时画面（跟遥控页一样拿）。
//
// - 来报警全屏页（后台值守拉起来的）遇到「机器人看见人」就是这个样子：画面铺满左边，右边一列按钮
//   （我来处理 / 静音 2 分钟 / 详情），见 [PersonLiveView]，按钮由 RingPage 给。
// - App 开着（或刚打开）在「现在」页，读到一条还没人接手、刚发生的「机器人看见人」：自动推一页 [PersonLivePage]，
//   同一条只推一次（[personLiveShown]，来报警全屏页弹过的也算）。
// - 先开报了看到人的那一路（前、后都看到 = 前）；画面下面照样能切前后。
// - 上面一行写看见人、在哪、哪台相机看到的、跟随状态（在退 / 退不了站定 / 人离开防区）。
import 'dart:async';

import 'package:flutter/material.dart';

import '../l10n.dart';
import '../model/alert.dart';
import '../net/background_watch.dart' as bg;
import '../net/site_client.dart';
import 'nw/nw_theme.dart';
import 'orientation.dart';
import 'site_alert_scene.dart';
import 'site_video.dart';
import '../net/person_names.dart';

/// 这条报警要不要横屏整屏放画面：「机器人看见人」、机器人报的（不是站点、监控相机）、还没结案。
bool personLiveFor(Alert a) =>
    a.kind == 'dog_sees_person' &&
    a.robot.isNotEmpty &&
    a.robot != 'site' &&
    !a.robot.startsWith('cctv:') &&
    !a.resolved;

/// 先开哪一路：只有后相机看到 = 后，别的 = 前。
String personLiveCam(Map<String, dynamic> ctx) {
  final p = ctx['persons'];
  final cams = p is Map && p['cams'] is List ? (p['cams'] as List).map((x) => '$x').toList() : const <String>[];
  return cams.contains('back') && !cams.contains('front') ? 'back' : 'front';
}

/// 这次打开 App 已经整屏弹过的（同一条不弹第二次）。
final Set<String> personLiveShown = <String>{};

/// 多久以内的算「刚发生」，打开 App 自动弹（旧的不弹，去「这件事」看）。
const personLiveFreshMs = 10 * 60 * 1000;

/// 「现在」页读到报警以后：该自动弹的那一条（没有 = null）。
Alert? personLiveToPop(Iterable<Alert> alerts, {required int nowMs}) {
  for (final a in alerts) {
    if (a.level == 'P1' && personLiveFor(a) && !a.acked && !personLiveShown.contains(a.key) &&
        nowMs - a.lastMs <= personLiveFreshMs) {
      return a;
    }
  }
  return null;
}

/// 横屏整屏的样子：左边画面（铺满、能切前后），右边一列 [actions]。外面要包 [LandscapeOnly]。
class PersonLiveView extends StatelessWidget {
  final SiteApi api;
  final Alert alert;
  final String site;
  final List<Widget> actions;
  final String note;
  const PersonLiveView(
      {super.key, required this.api, required this.alert, this.site = '', required this.actions, this.note = ''});

  static const Key key_ = Key('person-live');

  @override
  Widget build(BuildContext context) {
    return Theme(
        data: nwTheme(Brightness.dark),
        child: ScaffoldMessenger(
            // 易用性 build 36 P1-1：自己一个 ScaffoldMessenger —— 外面那条「无人确认」提示条不进这一页（这页就是那条报警），不会压住「我来处理」
            child: Builder(builder: (context) {
          final c = Nw.of(context);
          final a = alert;
          final ctx = a.context;
          final where = [
            if (site.isNotEmpty) site,
            a.robot,
            if ('${ctx['zone'] ?? ''}'.isNotEmpty) '${ctx['zone']}',
            if (seenByText(ctx).isNotEmpty) seenByText(ctx),
          ].join(' · ');
          final follow = followLine(a);
          return Scaffold(
              key: key_,
              backgroundColor: Colors.black,
              body: Row(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                Expanded(
                    child: Stack(fit: StackFit.expand, children: [
                  SiteVideo(
                      key: ValueKey<String>('person-live-video ${a.robot}'),
                      api: api,
                      robotId: a.robot,
                      fullscreen: true,
                      initialCamera: personLiveCam(ctx)),
                  Positioned(
                      left: 0,
                      top: 0,
                      right: 0,
                      child: SafeArea(
                          bottom: false,
                          right: false,
                          child: Container(
                              margin: const EdgeInsets.all(Nw.s8),
                              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: Nw.s8),
                              decoration: BoxDecoration(
                                  color: Colors.black.withValues(alpha: 0.55),
                                  border: Border(left: BorderSide(color: a.resolved ? Colors.white54 : c.error, width: 4))),
                              child: Column(crossAxisAlignment: CrossAxisAlignment.start, mainAxisSize: MainAxisSize.min,
                                  children: [
                                // 易用性 37 复测 P2-19：报警关了还红字写「P1 · …」—— 关了写「已关闭」、不用红
                                Text(
                                    a.resolved
                                        ? tr('Closed · ${alertTitle(a.kind, a.title)}', '已关闭 · ${alertTitle(a.kind, a.title)}')
                                        : '${a.level} · ${alertTitle(a.kind, a.title)}',
                                    key: const Key('person-live-head'),
                                    maxLines: 1,
                                    overflow: TextOverflow.ellipsis,
                                    style: NwText.titleMedium
                                        .copyWith(color: a.resolved ? Colors.white : c.error, fontWeight: FontWeight.w700)),
                                Text(where,
                                    maxLines: 1,
                                    overflow: TextOverflow.ellipsis,
                                    style: NwText.bodyMedium.copyWith(color: Colors.white)),
                                if (follow.isNotEmpty)
                                  Text(follow,
                                      key: const Key('person-live-follow'),
                                      maxLines: 2,
                                      overflow: TextOverflow.ellipsis,
                                      style: NwText.bodyMedium.copyWith(color: Colors.white)),
                              ])))),
                ])),
                Container(
                    width: 184,
                    color: c.bg,
                    child: SafeArea(
                        left: false,
                        child: Padding(
                            padding: const EdgeInsets.all(12),
                            child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                              if (note.isNotEmpty)
                                Expanded(
                                    child: SingleChildScrollView(
                                        child: Text(note,
                                            key: const Key('person-live-note'),
                                            style: NwText.bodySmall.copyWith(color: c.textSecondary))))
                              else
                                const Spacer(),
                              for (final w in actions) ...[w, const SizedBox(height: Nw.s8)],
                            ])))),
              ]));
        })));
  }
}

/// 一个按钮（跟来报警全屏页一样的样子：主按钮红底）。
Widget personLiveButton(BuildContext context, Key key, String label, VoidCallback? on, {bool primary = false}) {
  final c = Nw.of(context);
  final shape = RoundedRectangleBorder(borderRadius: BorderRadius.circular(2));
  const size = Size(48, 48);
  final child = Text(label, textAlign: TextAlign.center, maxLines: 2, overflow: TextOverflow.ellipsis);
  return primary
      ? FilledButton(
          key: key,
          style: FilledButton.styleFrom(
              backgroundColor: c.error, foregroundColor: c.onError, minimumSize: size, textStyle: NwText.titleSmall,
              shape: shape),
          onPressed: on,
          child: child)
      : OutlinedButton(
          key: key,
          style: OutlinedButton.styleFrom(
              foregroundColor: Colors.white,
              disabledForegroundColor: c.textMuted,
              side: BorderSide(color: c.textMuted),
              minimumSize: size,
              padding: const EdgeInsets.symmetric(horizontal: Nw.s8),
              textStyle: NwText.titleSmall,
              shape: shape),
          onPressed: on,
          child: child);
}

/// App 开着时自动弹的那一页（也是来报警全屏页「我来处理」以后去的地方）：横屏整屏画面 + 我来处理 / 详情 / 关闭。
class PersonLivePage extends StatefulWidget {
  final SiteApi api;
  final Alert alert;
  final Duration every;
  final DateTime Function() now;
  final Future<void> Function(String key) mute;
  const PersonLivePage(
      {super.key,
      required this.api,
      required this.alert,
      this.every = const Duration(seconds: 3),
      this.now = DateTime.now,
      this.mute = bg.muteRing});

  static const Key takeKey = Key('person-live-take');
  /// 易用性 build 36 P2-14：自动弹的这一页也要「静音 2 分钟」（以前只有来报警全屏页有）。
  static const Key muteKey = Key('person-live-mute');
  static const Key detailKey = Key('person-live-detail');
  static const Key closeKey = Key('person-live-close');

  @override
  State<PersonLivePage> createState() => _PersonLivePageState();
}

class _PersonLivePageState extends State<PersonLivePage> {
  late Alert _a = widget.alert;
  Timer? _poll;
  bool _busy = false;
  String _msg = '';
  int? _mutedUntil;

  Future<void> _mute() async {
    // 跟来报警全屏页一样：前台的铃和后台通知的铃静到同一个点
    final until = widget.now().add(const Duration(minutes: 2)).millisecondsSinceEpoch;
    bg.ringMutedUntil[_a.key] = until;
    await widget.mute(_a.key);
    if (!mounted) return;
    final d = DateTime.fromMillisecondsSinceEpoch(until);
    final hm = '${d.hour.toString().padLeft(2, '0')}:${d.minute.toString().padLeft(2, '0')}';
    setState(() {
      _mutedUntil = until;
      _msg = tr('Muted on this phone until $hm. It rings again if no one takes ownership.',
          '这台手机静音到 $hm，到时还没人接手会接着响。');
    });
  }

  @override
  void initState() {
    super.initState();
    personLiveShown.add(_a.key);
    _poll = Timer.periodic(widget.every, (_) => unawaited(_check()));
  }

  @override
  void dispose() {
    _poll?.cancel();
    super.dispose();
  }

  /// 跟随状态、谁接手了：跟着站点更新。
  Future<void> _check() async {
    try {
      final rows = await widget.api.alerts(all: true);
      final got = rows.where((x) => x.key == _a.key);
      if (mounted && got.isNotEmpty) setState(() => _a = got.first);
    } on Object {
      return;
    }
  }

  Future<void> _take() async {
    if (_busy) return;
    setState(() => _busy = true);
    try {
      final r = await widget.api.ackAlert(_a.key);
      final got = r['alert'] is Map ? Alert.fromWire(Map<String, dynamic>.from(r['alert'] as Map)) : null;
      if (mounted && got != null && got.key == _a.key) setState(() => _a = got);
    } on SiteError catch (e) {
      if (mounted) setState(() => _msg = tr('Not taken: $e', '没接上：$e'));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  void _detail() {
    // 换掉这一页（「这件事」竖屏横屏都行，这一页一关就放开横屏）
    unawaited(Navigator.of(context)
        .pushReplacement(MaterialPageRoute<void>(builder: (_) => SiteAlertScenePage(api: widget.api, alert: _a))));
  }

  @override
  Widget build(BuildContext context) {
    final handle = widget.api.session?.canHandleAlerts ?? false;
    final by = _a.ackedBy.isEmpty ? '' : personName(_a.ackedBy);
    final closedBy = _a.resolvedBy.isEmpty ? '' : personName(_a.resolvedBy);
    final note = _msg.isNotEmpty
        ? _msg
        : _a.resolved
            ? (closedBy.isEmpty ? tr('Closed', '已关闭') : tr('Closed by $closedBy', '$closedBy 已关闭'))
            : _a.acked
            ? tr('Handled by $by', '$by 在处理')
            : tr('No one has taken it yet', '还没人接手');
    return LandscapeOnly(
        child: Builder(
            builder: (context) => PersonLiveView(api: widget.api, alert: _a, note: note, actions: [
                  if (handle && !_a.acked && !_a.resolved)
                    personLiveButton(context, PersonLivePage.takeKey, tr('Take ownership', '我来处理'),
                        _busy ? null : () => unawaited(_take()),
                        primary: true),
                  if (!_a.acked && !_a.resolved)
                    personLiveButton(context, PersonLivePage.muteKey, tr('Mute 2 min', '静音 2 分钟'),
                        _mutedUntil == null ? () => unawaited(_mute()) : null),
                  personLiveButton(context, PersonLivePage.detailKey, tr('Details', '详情'), _detail),
                  personLiveButton(context, PersonLivePage.closeKey, tr('Close', '关闭'), () => Navigator.of(context).pop()),
                ])));
  }
}
