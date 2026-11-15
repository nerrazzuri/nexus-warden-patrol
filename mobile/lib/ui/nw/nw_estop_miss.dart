// App V2 稿 N-refuse 下半：急停没确认的红框。全部急停时某台没回执 / 说没停成，就在「现在」页、「这件事」页顶上
// 一台一块：站点几点发的、它可能还在动、去看画面或者到现场；「再发一次急停」「看它的画面」一排等宽。
import 'dart:async';

import 'package:flutter/material.dart';

import '../../l10n.dart';
import '../../net/site_client.dart';
import '../site_robot.dart';
import '../widget/alarm_widgets.dart';
import 'nw_ask.dart' show scrollPageToTop;
import 'nw_theme.dart';

/// 外审 App-V2-1 #3：新来一块「急停没确认」时，这一页滚回顶，让红框看得见（人可能正滚在下面）。
/// 放红框的那一页的 State 混入它。
mixin EstopMissReveal<W extends StatefulWidget> on State<W> {
  int _misses = 0;

  void _onMiss() {
    final n = estopMisses.value.length;
    final grew = n > _misses;
    _misses = n;
    if (!grew || !mounted) return;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) scrollPageToTop(context);
    });
  }

  @override
  void initState() {
    super.initState();
    _misses = estopMisses.value.length;
    estopMisses.addListener(_onMiss);
  }

  @override
  void dispose() {
    estopMisses.removeListener(_onMiss);
    super.dispose();
  }
}

class EstopMissCards extends StatefulWidget {
  final SiteApi api;
  const EstopMissCards({super.key, required this.api});

  static Key cardKey(String id) => Key('estop-miss-$id');
  static Key againKey(String id) => Key('estop-again-$id');
  static Key videoKey(String id) => Key('estop-video-$id');

  @override
  State<EstopMissCards> createState() => _EstopMissCardsState();
}

class _EstopMissCardsState extends State<EstopMissCards> {
  final Set<String> _busy = {};

  static String _hms(DateTime d) =>
      [d.hour, d.minute, d.second].map((x) => x.toString().padLeft(2, '0')).join(':');

  Future<void> _again(String id) async {
    setState(() => _busy.add(id));
    await resendEstop(widget.api, id);
    if (mounted) setState(() => _busy.remove(id));
  }

  Widget _card(NwColors c, EstopMiss m) {
    final id = m.robot;
    final text = m.noAck
        ? tr('The site sent it at ${_hms(m.at)} but $id has not acknowledged. $id may still be moving; check video or go on site.',
            '站点 ${_hms(m.at)} 已发出，但 $id 没有回执。$id 可能还在动，请看画面或到现场。')
        : tr('$id did not stop (${m.error.message}). It may still be moving; use the E-stop on the robot or go on site.',
            '$id 没停成（${m.error.message}），可能还在动。请按机身急停或到现场。');
    final shape = RoundedRectangleBorder(borderRadius: BorderRadius.circular(2));
    return Container(
      key: EstopMissCards.cardKey(id),
      margin: const EdgeInsets.fromLTRB(Nw.s16, 12, Nw.s16, 0),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(color: c.surface, border: Border.all(color: c.error, width: 4), borderRadius: BorderRadius.circular(2)),
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Container(width: 22, height: 22, decoration: BoxDecoration(shape: BoxShape.circle, border: Border.all(color: c.error, width: 4))),
          const SizedBox(width: 12),
          Expanded(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(tr('E-stop not confirmed', '急停没确认'), style: NwText.titleLarge.copyWith(color: c.text, fontWeight: FontWeight.w700)),
            Text(text, style: NwText.bodyMedium.copyWith(color: c.textSecondary)),
          ])),
        ]),
        const SizedBox(height: 12),
        Row(children: [
          Expanded(
              child: FilledButton(
                  key: EstopMissCards.againKey(id),
                  style: FilledButton.styleFrom(
                      backgroundColor: c.error, foregroundColor: c.onError, minimumSize: const Size(48, 48), shape: shape),
                  onPressed: _busy.contains(id) ? null : () => unawaited(_again(id)),
                  child: Text(tr('Send E-stop again', '再发一次急停'), textAlign: TextAlign.center))),
          const SizedBox(width: Nw.s8),
          Expanded(
              child: OutlinedButton(
                  key: EstopMissCards.videoKey(id),
                  style: OutlinedButton.styleFrom(
                      foregroundColor: c.text, side: BorderSide(color: c.textMuted), minimumSize: const Size(48, 48), shape: shape),
                  onPressed: () => Navigator.push(
                      context, MaterialPageRoute<void>(builder: (_) => SiteRobotPage(api: widget.api, robotId: id))),
                  child: Text(tr('View $id video', '看 $id 画面'), textAlign: TextAlign.center))),
        ]),
      ]),
    );
  }

  @override
  Widget build(BuildContext context) => ValueListenableBuilder<List<EstopMiss>>(
      valueListenable: estopMisses,
      builder: (context, misses, _) {
        if (misses.isEmpty) return const SizedBox.shrink();
        final c = Nw.of(context);
        return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [for (final m in misses) _card(c, m)]);
      });
}
