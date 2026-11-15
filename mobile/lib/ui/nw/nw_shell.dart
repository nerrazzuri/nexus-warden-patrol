/// 登录之后的外壳（App V2，design/app-v2：结构 B「现在 / 现场」两层，用户 2026-11-15 批准）。
///
/// - 顶栏：站点名 + 布防状态（牌子：绿方块 / 红圈）+ 时钟；下面一条两段开关「现在 | 现场」。
/// - 「现在」：深色；值班内容（第 1 期先沿用 [SiteDutyPage]，第 2 期按 N-normal 重排）；右下角拇指区一个
///   大红方块「全部急停」—— 手机上唯一的整块红底，每个「现在」屏都有。
/// - 「现场」：浅色目录（[SiteDirectory]，按角色四套），顶栏放小红「急停」。
/// - 「机器人」：目录里点「机器人」切到一直活着的 [SiteRobotsPage]（事件流、响铃、后台值守、登录过期都在它身上，
///   所以它从进站点起就一直挂着，不显示也在）。
///
/// 老的底部五栏（值守 / 机器人 / 地图 / 记录 / 管理）2026-11-15 删了：一件事不再摊在四栏里。
library;

import 'dart:async';

import 'package:flutter/material.dart';

import '../../l10n.dart';
import '../../net/app_update.dart';
import '../../net/background_watch.dart';
import '../../net/error_log.dart';
import '../../net/push.dart';
import '../../net/site_client.dart';
import '../../store/site_store.dart';
import '../app_settings.dart';
import '../app_update_ui.dart';
import '../guide.dart';
import '../map_wizard.dart' show maybeOfferMapping;
import '../site_duty_page.dart';
import '../site_robots.dart';
import '../site_tabs.dart' show AdminHomeTab;
import '../widget/alarm_widgets.dart' show StopAllButton;
import 'nw_site_dir.dart';
import 'nw_theme.dart';

/// 外壳里的三层。
enum ShellLayer { now, site, robots, overview }

class NwShell extends StatefulWidget {
  final SiteApi api;

  /// 以下几项原样交给机器人列表（[SiteRobotsPage]）：站点名、响铃、后台值守、站点条目、推送登记、多久再响一次。
  final String? title;
  final void Function() ring;
  final BackgroundWatch watch;
  final SiteEntry? entry;
  final PushSession? push;
  final Duration ringEvery;

  /// W55：登录后问站点有没有新版 App；测试给 null 就不问（默认按本机平台问）。
  final AppUpdater? Function(SiteApi api)? updater;

  /// 手机 App 测试 M01：在「现在」按返回键做什么（默认把 App 退到后台）；测试换成记一笔。
  final Future<void> Function() toBackground;

  /// 时钟、布防状态多久刷一次（测试调小）。
  final Duration clockEvery;

  const NwShell(
      {super.key,
      required this.api,
      this.title,
      this.ring = defaultRing,
      this.watch = const ChannelBackgroundWatch(),
      this.entry,
      this.push,
      this.ringEvery = const Duration(seconds: 4),
      this.updater = defaultUpdater,
      this.toBackground = moveAppToBackground,
      this.clockEvery = const Duration(seconds: 30)});

  static AppUpdater? defaultUpdater(SiteApi api) {
    final p = updatePlatform();
    return p == null ? null : AppUpdater(api: api, platform: p);
  }

  static const Key nowKey = Key('open-now');
  static const Key siteKey = Key('open-site');
  static const Key estopKey = Key('estop-all');
  static const Key estopSmallKey = Key('estop-small');
  static const Key backKey = Key('shell-back');
  static const Key armKey = Key('shell-arm');
  static const Key clockKey = Key('shell-clock');
  static const Key p1BarKey = Key('shell-p1-bar');

  @override
  State<NwShell> createState() => _NwShellState();
}

class _NwShellState extends State<NwShell> {
  ShellLayer _layer = ShellLayer.now;

  /// 后台值守开关（机器人页管开停，设置页显示、点它）。
  final WatchControl _watchCtl = WatchControl();

  /// 还开着的 P1（机器人页一直连着站点、记着它）：「现在」以外的层顶上红条。
  final ValueNotifier<Map<String, String>> _openP1 = ValueNotifier(const <String, String>{});
  Map<String, dynamic>? _mode;
  DateTime _now = DateTime.now();
  Timer? _tick;
  bool _tourChecked = false;
  bool _replay = false;
  String _toast = '';

  @override
  void initState() {
    super.initState();
    ErrorLog.instance.attach(widget.api);
    final u = widget.updater?.call(widget.api);
    if (u != null) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) unawaited(offerAppUpdate(context, u));
      });
    }
    replayTour = () async {
      _replay = true;
      if (_layer == ShellLayer.now) {
        final t = _targets, ctx = _dutyContext;
        _replay = false;
        if (t != null && ctx != null && ctx.mounted) await runTour(ctx, widget.api, t);
      } else {
        setState(() => _layer = ShellLayer.now);
      }
    };
    unawaited(_refresh());
    _tick = Timer.periodic(widget.clockEvery, (_) => unawaited(_refresh()));
  }

  Future<void> _refresh() async {
    if (!mounted) return;
    setState(() => _now = DateTime.now());
    try {
      final m = await widget.api.mode();
      if (mounted) setState(() => _mode = m);
    } on SiteError {
      // 顶栏的布防状态拿不到就留着上一次的;机器人页会报断线
    }
  }

  @override
  void dispose() {
    _tick?.cancel();
    unawaited(ErrorLog.instance.flush());
    ErrorLog.instance.detach(widget.api);
    _watchCtl.dispose();
    _openP1.dispose();
    replayTour = null;
    super.dispose();
  }

  DutyTargets? _targets;
  BuildContext? _dutyContext;
  void _onDutyReady(BuildContext ctx, DutyTargets t) {
    _targets = t;
    _dutyContext = ctx;
    if (_replay) {
      _replay = false;
      unawaited(runTour(ctx, widget.api, t));
      return;
    }
    if (_tourChecked) return;
    _tourChecked = true;
    unawaited(maybeStartTour(ctx, widget.api, t).then((_) async {
      if (ctx.mounted) await maybeOfferMapping(ctx, widget.api);
    }));
  }

  void _say(String s) {
    if (!mounted) return;
    setState(() => _toast = s);
    ScaffoldMessenger.maybeOf(context)?.showSnackBar(SnackBar(content: Text(s)));
  }

  /// 顶栏布防那一行：状态词 + 牌子颜色。
  (String, _Sign) _armText() {
    final m = _mode;
    if (m == null) return (tr('Connecting…', '连接中…'), _Sign.none);
    final state = '${m['state'] ?? m['mode'] ?? ''}';
    final mode = '${m['mode'] ?? ''}';
    final until = m['until_ms'];
    final next = m['next_change_ms'];
    String hm(Object? ms) {
      if (ms is! num) return '';
      final d = DateTime.fromMillisecondsSinceEpoch(ms.toInt());
      return '${d.hour.toString().padLeft(2, '0')}:${d.minute.toString().padLeft(2, '0')}';
    }
    if (mode == 'visitor' && until != null) return (tr('Temporary disarm · until ${hm(until)}', '临时撤防 · 到 ${hm(until)}'), _Sign.warn);
    if (state == 'armed') {
      final n = next != null ? tr(' · until ${hm(next)}', ' · 到 ${hm(next)}') : '';
      return (tr('Armed$n', '布防中$n'), _Sign.ok);
    }
    if (state == 'disarmed') {
      final n = next != null ? tr(' · Arms ${hm(next)}', ' · ${hm(next)} 布防') : '';
      return (tr('Disarmed$n', '已撤防$n'), _Sign.idle);
    }
    if (state == 'partial') return (tr('Partly armed', '部分布防'), _Sign.warn);
    return ('${m['label'] ?? state}', _Sign.idle);
  }

  bool get _dark => _layer == ShellLayer.now;

  @override
  Widget build(BuildContext context) {
    final api = widget.api;
    final dark = _dark;
    final theme = nwTheme(dark ? Brightness.dark : Brightness.light);
    return PopScope(
        canPop: false,
        onPopInvokedWithResult: (didPop, _) {
          if (didPop) return;
          if (_layer == ShellLayer.robots || _layer == ShellLayer.overview) {
            setState(() => _layer = ShellLayer.site);
          } else if (_layer != ShellLayer.now) {
            setState(() => _layer = ShellLayer.now);
          } else {
            unawaited(widget.toBackground());
          }
        },
        child: SettingsHost(
            watch: _watchCtl,
            push: widget.push,
            updater: widget.updater,
            child: Theme(
                data: theme,
                child: Builder(builder: (context) {
                  final c = Nw.of(context);
                  return Scaffold(
                      backgroundColor: c.bg,
                      body: Column(children: [
                        _TopBar(
                            title: widget.title ?? widget.entry?.name ?? api.session?.name ?? '',
                            arm: _armText(),
                            now: _now,
                            dark: dark,
                            sub: _layer == ShellLayer.robots
                                ? tr('Robots', '机器人')
                                : _layer == ShellLayer.overview
                                    ? tr('Overview', '概况')
                                    : null,
                            onBack: _layer == ShellLayer.robots || _layer == ShellLayer.overview
                                ? () => setState(() => _layer = ShellLayer.site)
                                : null,
                            onEstop: dark ? null : () => StopAllButton.press(context, api, _say)),
                        if (_layer == ShellLayer.now || _layer == ShellLayer.site)
                          _Segment(layer: _layer, onPick: (l) => setState(() => _layer = l)),
                        if (!dark)
                          ValueListenableBuilder<Map<String, String>>(
                              valueListenable: _openP1,
                              builder: (context, p1, _) => p1.isEmpty
                                  ? const SizedBox.shrink()
                                  : _P1Bar(titles: p1.values.toList(), onTap: () => setState(() => _layer = ShellLayer.now))),
                        Expanded(
                            child: Stack(children: [
                          IndexedStack(
                              index: _layer == ShellLayer.robots ? 0 : 1,
                              sizing: StackFit.expand,
                              children: [
                                SiteRobotsPage(
                                    api: api,
                                    title: widget.title,
                                    ring: widget.ring,
                                    watch: widget.watch,
                                    entry: widget.entry,
                                    push: widget.push,
                                    ringEvery: widget.ringEvery,
                                    control: _watchCtl,
                                    openP1: _openP1),
                                switch (_layer) {
                                  ShellLayer.now => SiteDutyPage(
                                      key: const ValueKey('now'), api: api, title: widget.title, onReady: _onDutyReady),
                                  ShellLayer.site => SiteDirectory(
                                      key: const ValueKey('site'),
                                      api: api,
                                      entry: widget.entry,
                                      onRobots: () => setState(() => _layer = ShellLayer.robots),
                                      onOverview: () => setState(() => _layer = ShellLayer.overview)),
                                  ShellLayer.overview => AdminHomeTab(
                                      key: const ValueKey('overview'),
                                      api: api,
                                      entry: widget.entry,
                                      switchTab: (_) => setState(() => _layer = ShellLayer.robots)),
                                  ShellLayer.robots => const SizedBox.shrink(),
                                },
                              ]),
                          if (dark)
                            Positioned(
                                right: Nw.s16,
                                bottom: Nw.s16,
                                child: SafeArea(child: _EstopSquare(onPressed: () => StopAllButton.press(context, api, _say)))),
                        ])),
                      ]));
                }))));
  }
}

enum _Sign { ok, warn, bad, idle, none }

/// 顶栏：左边站点名 + 布防那一行，右边时钟（「现在」）或小红「急停」（「现场」）。子层（机器人、概况）左边多一个返回。
class _TopBar extends StatelessWidget {
  final String title;
  final (String, _Sign) arm;
  final DateTime now;
  final bool dark;
  final String? sub;
  final VoidCallback? onBack;
  final VoidCallback? onEstop;
  const _TopBar({required this.title, required this.arm, required this.now, required this.dark, this.sub, this.onBack, this.onEstop});

  @override
  Widget build(BuildContext context) {
    final c = Nw.of(context);
    final (text, sign) = arm;
    final hhmm = '${now.hour.toString().padLeft(2, '0')}:${now.minute.toString().padLeft(2, '0')}';
    return Material(
        color: c.bg,
        child: SafeArea(
            bottom: false,
            child: Padding(
                padding: const EdgeInsets.fromLTRB(Nw.s16, 10, Nw.s16, 6),
                child: Row(children: [
                  if (onBack != null)
                    IconButton(
                        key: NwShell.backKey,
                        onPressed: onBack,
                        padding: EdgeInsets.zero,
                        constraints: const BoxConstraints(minWidth: Nw.touch, minHeight: Nw.touch),
                        icon: Icon(Icons.arrow_back_ios_new_rounded, color: c.text, size: 22)),
                  Expanded(
                      child: Column(crossAxisAlignment: CrossAxisAlignment.start, mainAxisSize: MainAxisSize.min, children: [
                    Text(sub ?? title,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: NwText.titleMedium.copyWith(color: c.text, fontWeight: FontWeight.w700)),
                    Row(key: NwShell.armKey, children: [
                      _SignDot(sign),
                      if (sign != _Sign.none) const SizedBox(width: 6),
                      Flexible(
                          child: Text(sub != null ? title : text,
                              maxLines: 1, overflow: TextOverflow.ellipsis, style: NwText.bodySmall.copyWith(color: c.textSecondary))),
                    ]),
                  ])),
                  if (onEstop != null)
                    _EstopSmall(onPressed: onEstop!)
                  else
                    Text(hhmm,
                        key: NwShell.clockKey,
                        style: NwText.titleMedium.copyWith(color: c.text, fontWeight: FontWeight.w700, fontFeatures: const [FontFeature.tabularFigures()])),
                ]))));
  }
}

/// 牌子：绿方块 = 正常，红圈 = 急停 / P1，琥珀三角 = 警告，灰圈 = 撤防 / 不活动。
class _SignDot extends StatelessWidget {
  final _Sign sign;
  const _SignDot(this.sign);
  @override
  Widget build(BuildContext context) {
    final c = Nw.of(context);
    return switch (sign) {
      _Sign.ok => Container(width: 9, height: 9, color: c.success),
      _Sign.bad => Container(
          width: 12, height: 12, decoration: BoxDecoration(shape: BoxShape.circle, border: Border.all(color: c.error, width: 3))),
      _Sign.warn => CustomPaint(size: const Size(13, 11), painter: _TriPainter(c.warning)),
      _Sign.idle => Container(
          width: 11, height: 11, decoration: BoxDecoration(shape: BoxShape.circle, border: Border.all(color: c.textMuted, width: 2))),
      _Sign.none => const SizedBox.shrink(),
    };
  }
}

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

/// 「现在 | 现场」两段开关：等宽,选中的蓝底。
class _Segment extends StatelessWidget {
  final ShellLayer layer;
  final ValueChanged<ShellLayer> onPick;
  const _Segment({required this.layer, required this.onPick});
  @override
  Widget build(BuildContext context) {
    final c = Nw.of(context);
    Widget seg(ShellLayer l, Key key, String label) {
      final on = layer == l;
      return Expanded(
          child: Semantics(
              button: true,
              selected: on,
              child: InkWell(
                  key: key,
                  onTap: () => onPick(l),
                  child: Container(
                      height: 40,
                      alignment: Alignment.center,
                      decoration: BoxDecoration(color: on ? c.primary : Colors.transparent, borderRadius: BorderRadius.circular(2)),
                      child: Text(label,
                          style: NwText.labelLarge.copyWith(color: on ? c.onPrimary : c.textSecondary, fontWeight: FontWeight.w600))))));
    }

    return Padding(
        padding: const EdgeInsets.fromLTRB(Nw.s16, 4, Nw.s16, Nw.s8),
        child: Container(
            padding: const EdgeInsets.all(3),
            decoration: BoxDecoration(border: Border.all(color: c.outline), borderRadius: BorderRadius.circular(2), color: c.surface),
            child: Row(children: [
              seg(ShellLayer.now, NwShell.nowKey, tr('Now', '现在')),
              const SizedBox(width: 3),
              seg(ShellLayer.site, NwShell.siteKey, tr('Site', '现场')),
            ])));
  }
}

/// 「现在」右下角的大红方块（拇指区）：手机上唯一的整块红底。
class _EstopSquare extends StatelessWidget {
  final VoidCallback onPressed;
  const _EstopSquare({required this.onPressed});
  @override
  Widget build(BuildContext context) {
    final c = Nw.of(context);
    return Material(
        color: c.error,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(2), side: BorderSide(color: c.errorFrame, width: 2)),
        elevation: 6,
        shadowColor: Colors.black54,
        child: InkWell(
            key: NwShell.estopKey,
            onTap: onPressed,
            child: SizedBox(
                width: 88,
                height: 88,
                child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
                  Icon(Icons.do_not_disturb_on_outlined, color: c.onError, size: 26),
                  const SizedBox(height: 4),
                  Text(tr('E-STOP\nALL', '全部\n急停'),
                      textAlign: TextAlign.center,
                      style: NwText.labelLarge.copyWith(color: c.onError, fontWeight: FontWeight.w800, height: 1.1)),
                ]))));
  }
}

/// 「现场」顶栏的小红「急停」。
class _EstopSmall extends StatelessWidget {
  final VoidCallback onPressed;
  const _EstopSmall({required this.onPressed});
  @override
  Widget build(BuildContext context) {
    final c = Nw.of(context);
    return Material(
        color: c.error,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(2), side: BorderSide(color: c.errorFrame, width: 2)),
        child: InkWell(
            key: NwShell.estopSmallKey,
            onTap: onPressed,
            child: Container(
                height: 40,
                padding: const EdgeInsets.symmetric(horizontal: 12),
                child: Row(mainAxisSize: MainAxisSize.min, children: [
                  Icon(Icons.do_not_disturb_on_outlined, color: c.onError, size: 18),
                  const SizedBox(width: 6),
                  Text(tr('E-STOP', '急停'), style: NwText.labelLarge.copyWith(color: c.onError, fontWeight: FontWeight.w800)),
                ]))));
  }
}

/// 「现在」以外的层顶上的红条：有 P1 还开着。点了回「现在」。
class _P1Bar extends StatelessWidget {
  final List<String> titles;
  final VoidCallback onTap;
  const _P1Bar({required this.titles, required this.onTap});
  @override
  Widget build(BuildContext context) {
    final c = Nw.of(context);
    final text = titles.length == 1
        ? tr('P1: ${titles.first}. Tap to handle', 'P1：${titles.first}，点这里处理')
        : tr('${titles.length} P1 alarms open. Tap to handle', '${titles.length} 条 P1 没处理，点这里处理');
    return Material(
      key: NwShell.p1BarKey,
      color: c.error,
      child: InkWell(
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: Nw.s16, vertical: Nw.s8),
          child: Row(children: [
            Container(
                width: 14, height: 14, decoration: BoxDecoration(shape: BoxShape.circle, border: Border.all(color: c.onError, width: 3))),
            const SizedBox(width: Nw.s8),
            Expanded(
                child: Text(text,
                    maxLines: 2, overflow: TextOverflow.ellipsis, style: NwText.labelLarge.copyWith(color: c.onError, fontWeight: FontWeight.w700))),
            Icon(Icons.chevron_right_rounded, color: c.onError),
          ]),
        ),
      ),
    );
  }
}
