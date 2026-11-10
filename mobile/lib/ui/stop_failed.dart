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
                  child: Text(tr('OK', '知道了'))),
            ],
          ));
}
