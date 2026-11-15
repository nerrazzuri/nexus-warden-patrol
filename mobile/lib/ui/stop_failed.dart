/// 叫停没成功（手机 App 测试 M02）：站点联系不上、站点拒了、机器人没收下 —— 都弹这个框。
///
/// 以前是一条几秒就消失的半透明提示，压在别的字上，看的人可能以为机器人已经停了。现在：红色标题、
/// 写明「机器人没收到停车指令，请立刻按机身急停」，不点「知道了」不消失。值守页、单台机器人页、遥控页同一个写法。
library;

import 'package:flutter/material.dart';

import '../l10n.dart';
import '../net/site_client.dart';
import 'nw/nw_theme.dart';

const Key stopFailedKey = Key('stop-failed');

/// 叫停失败的原因写成一行（技术原文放小字里）。
String stopFailedDetail(Object? error) => switch (error) {
      null => '',
      SiteError e => refusalText(e),
      _ => '$error',
    };

Future<void> showStopFailed(BuildContext context, {String? robot, Object? error}) async {
  if (!context.mounted) return;
  final c = Nw.of(context);
  final who = (robot ?? '').isEmpty ? tr('The robot', '机器人') : robot!;
  final detail = stopFailedDetail(error);
  await showDialog<void>(
      context: context,
      barrierDismissible: false,
      builder: (ctx) => AlertDialog(
            key: stopFailedKey,
            icon: Icon(Icons.warning_amber_rounded, color: c.error, size: 40),
            title: Text(tr('Stop did not get through', '叫停没有成功'),
                style: NwText.titleLarge.copyWith(color: c.error, fontWeight: FontWeight.w700)),
            content: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(
                  tr('$who did not get the stop command and may still be moving. Press the emergency stop on the robot now.',
                      '$who没有收到停车指令，可能还在走。请立刻按机身上的急停按钮。'),
                  style: NwText.bodyLarge),
              if (detail.isNotEmpty) ...[
                const SizedBox(height: Nw.s8),
                Text(tr('Reason: $detail', '原因：$detail'),
                    style: NwText.bodySmall.copyWith(color: c.textSecondary)),
              ],
            ]),
            actions: [
              FilledButton(
                  style: FilledButton.styleFrom(backgroundColor: c.error, foregroundColor: c.onError),
                  onPressed: () => Navigator.pop(ctx),
                  child: Text(tr('Acknowledge', '知道了'))),
            ],
          ));
}

/// App V2（不弹窗）：叫停没成功的红框，钉在机器人页顶上直到人按「知道了」；带「再停一次」。
const stopFailedCardKey = Key('stop-failed-card');
const stopAgainKey = Key('stop-failed-again');
const stopAckKey = Key('stop-failed-ack');

class StopFailedCard extends StatelessWidget {
  final String robot;
  final Object? error;
  final VoidCallback onAgain;
  final VoidCallback onAck;
  const StopFailedCard({super.key = stopFailedCardKey, required this.robot, this.error, required this.onAgain, required this.onAck});

  @override
  Widget build(BuildContext context) {
    final c = Nw.of(context);
    final detail = stopFailedDetail(error);
    Widget btn(Key k, String label, VoidCallback on, {bool red = false}) => Expanded(
        child: red
            ? FilledButton(
                key: k,
                style: FilledButton.styleFrom(
                    backgroundColor: c.error,
                    foregroundColor: c.onError,
                    minimumSize: const Size(48, 48),
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(2))),
                onPressed: on,
                child: Text(label))
            : OutlinedButton(
                key: k,
                style: OutlinedButton.styleFrom(
                    foregroundColor: c.text,
                    side: BorderSide(color: c.textMuted),
                    minimumSize: const Size(48, 48),
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(2))),
                onPressed: on,
                child: Text(label)));
    return Container(
        margin: const EdgeInsets.fromLTRB(Nw.s16, 12, Nw.s16, 0),
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(color: c.errorSoft, border: Border.all(color: c.error, width: 2)),
        child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          Text(tr('Stop did not get through', '叫停没有成功'),
              style: NwText.titleMedium.copyWith(color: c.error, fontWeight: FontWeight.w700)),
          const SizedBox(height: Nw.s4),
          Text(
              tr('$robot did not get the stop command and may still be moving. Press the emergency stop on the robot now.',
                  '$robot没有收到停车指令，可能还在走。请立刻按机身上的急停按钮。'),
              style: NwText.bodyMedium.copyWith(color: c.text)),
          if (detail.isNotEmpty)
            Text(tr('Reason: $detail', '原因：$detail'), style: NwText.bodySmall.copyWith(color: c.textSecondary)),
          const SizedBox(height: Nw.s8),
          Row(children: [
            btn(stopAgainKey, tr('Stop again', '再停一次'), onAgain, red: true),
            const SizedBox(width: Nw.s8),
            btn(stopAckKey, tr('Acknowledge', '知道了'), onAck),
          ]),
        ]));
  }
}
