/// 报警的几样共用小件（App V2，视觉规范 2.1 / 2.5）：优先级三重编码（颜色 + 形状 + 文字）、全部急停。
library;

import 'package:flutter/material.dart';

import '../../l10n.dart';
import '../../net/site_client.dart';
import '../nw/nw_theme.dart';

/// 优先级的形状：P1 实心菱形、P2 实心三角、别的空心圆。颜色由调用方给（实底上是白的）。
class PriorityShape extends StatelessWidget {
  final String level;
  final Color color;
  final double size;
  const PriorityShape({super.key, required this.level, required this.color, this.size = 14});

  @override
  Widget build(BuildContext context) =>
      CustomPaint(size: Size.square(size), painter: _ShapePainter(level, color));
}

class _ShapePainter extends CustomPainter {
  final String level;
  final Color color;
  const _ShapePainter(this.level, this.color);

  @override
  void paint(Canvas canvas, Size s) {
    final w = s.width, h = s.height;
    final fill = Paint()..color = color;
    if (level == 'P1') {
      canvas.drawPath(
          Path()
            ..moveTo(w / 2, 0)
            ..lineTo(w, h / 2)
            ..lineTo(w / 2, h)
            ..lineTo(0, h / 2)
            ..close(),
          fill);
    } else if (level == 'P2') {
      canvas.drawPath(
          Path()
            ..moveTo(w / 2, h * 0.08)
            ..lineTo(w, h * 0.92)
            ..lineTo(0, h * 0.92)
            ..close(),
          fill);
    } else {
      canvas.drawCircle(
          Offset(w / 2, h / 2),
          w / 2 - 1,
          Paint()
            ..color = color
            ..style = PaintingStyle.stroke
            ..strokeWidth = 1.5);
    }
  }

  @override
  bool shouldRepaint(_ShapePainter old) => old.level != level || old.color != color;
}

/// 优先级的字色：P1 红、P2 橙、别的中性。颜色跟着浅色 / 深色走：把 `Nw.of(context)` 传进来
/// （不传按浅色那一套）。
Color priorityColor(String level, [NwColors c = NwColors.light]) => switch (level) {
      'P1' => c.error,
      'P2' => c.warning,
      _ => c.textSecondary,
    };

/// 急停没确认的一台（稿 N-refuse 红框）：站点发出去的时间、没确认的原因。
class EstopMiss {
  final String robot;
  final DateTime at;
  final SiteError error;
  const EstopMiss(this.robot, this.at, this.error);

  /// 504 = 站点发了、机器人没回执（不知道停没停）；别的 = 机器人或站点说没停成。
  bool get noAck => error.status == 504;
}

/// 急停没确认的那几台（App V2）：全部急停 / 再发一次时更新；「现在」页、「这件事」页摆红框。
final ValueNotifier<List<EstopMiss>> estopMisses = ValueNotifier<List<EstopMiss>>(const <EstopMiss>[]);

void _missed(String id, SiteError? e, DateTime at) {
  final rest = estopMisses.value.where((m) => m.robot != id).toList();
  estopMisses.value = e == null ? rest : [...rest, EstopMiss(id, at, e)];
}

/// 「再发一次急停」：成了从红框里去掉，没成换成这一次的时间和原因。
Future<bool> resendEstop(SiteApi api, String id, {DateTime Function() now = DateTime.now}) async {
  final at = now();
  try {
    await api.halt(id);
    _missed(id, null, at);
    return true;
  } on SiteError catch (e) {
    _missed(id, e, at);
    return false;
  }
}

/// 「全部急停」：红底 + 2px 报警框（红色只给急停这一类）。按了先问一遍，再对每台在线的狗
/// 发急停；哪台没停住说出来（叫人去按它身上的急停）。
class StopAllButton extends StatelessWidget {
  final SiteApi api;

  /// 结果说给谁（页面自己摆，或者弹个提示）。
  final void Function(String message) onResult;
  const StopAllButton({super.key, required this.api, required this.onResult});

  static const Key buttonKey = Key('stop-all');
  static const Key confirmKey = Key('stop-all-go');

  Future<void> _press(BuildContext context) => press(context, api, onResult);

  /// App V2 外壳的「全部急停」方块也走这一套(查在线、确认、逐台发、报没停住的)。
  static Future<void> press(BuildContext context, SiteApi api, void Function(String message) onResult) async {
    final List<Map<String, dynamic>> robots;
    try {
      // 在线 = 狗报在线、并且站点最近收到过它的消息（跟狗列表、网页值班台同一个判据）
      robots = (await api.robots())
          .where((r) => r['fresh'] == true && r['status'] is Map && (r['status'] as Map)['online'] == true)
          .toList();
    } on SiteError catch (e) {
      onResult(tr("Can't reach the site: $e. Use the E-stop on each robot.", '无法连接站点：$e。请按各机器人机身急停。'));
      return;
    }
    if (!context.mounted) return;
    if (robots.isEmpty) {
      onResult(tr('No robots are online.', '没有在线的机器人。'));
      return;
    }
    final n = robots.length;
    final ok = await showDialog<bool>(
        context: context,
        builder: (c) => AlertDialog(
              content: Text(tr(
                  'E-stop all $n robots now? Each one halts where it is until you reset it.',
                  '让全部 $n 台机器人立即急停？每台原地停止，直到你恢复。')),
              actions: [
                TextButton(onPressed: () => Navigator.pop(c, false), child: Text(tr('Cancel', '取消'))),
                FilledButton(
                    key: confirmKey,
                    style: _stopStyle(c),
                    onPressed: () => Navigator.pop(c, true),
                    child: Text(tr('E-STOP ALL', '全部急停'))),
              ],
            ));
    if (ok != true) return;
    final bad = <String>[];
    final at = DateTime.now();
    await Future.wait(robots.map((r) async {
      final id = '${r['robot_id']}';
      try {
        await api.halt(id);
        _missed(id, null, at);
      } on SiteError catch (e) {
        _missed(id, e, at); // 稿 N-refuse：红框「急停没确认」+ 再发一次
        bad.add(tr("$id didn't stop: $e. Use the E-stop on the robot.", '$id 未能停止：$e。请按机身急停。'));
      }
    }));
    onResult(bad.isEmpty ? tr('Stopped $n robots.', '已停止 $n 台机器人。') : bad.join(' '));
  }

  static ButtonStyle _stopStyle(BuildContext context) {
    final c = Nw.of(context);
    return FilledButton.styleFrom(
        backgroundColor: c.error,
        foregroundColor: c.onError,
        side: BorderSide(color: c.errorFrame, width: 2),
        minimumSize: const Size(Nw.touch, 40),
        textStyle: NwText.labelLarge);
  }

  @override
  Widget build(BuildContext context) => Padding(
      padding: const EdgeInsets.symmetric(horizontal: 8),
      child: FilledButton.icon(
          key: buttonKey,
          style: _stopStyle(context),
          onPressed: () => _press(context),
          icon: const Icon(Icons.report, size: 18),
          label: Text(tr('E-STOP ALL', '全部急停'))));
}
