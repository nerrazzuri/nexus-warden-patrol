// 手机 App 测试 M27：连着的「在路上」只留一条；写着没成的「完成」说没成；摄像头叫「后摄像头」。
import 'package:flutter_test/flutter_test.dart';
import 'package:nexwar_patrol/l10n.dart';
import 'package:nexwar_patrol/net/site_client.dart';
import 'package:nexwar_patrol/ui/robot_events.dart';

void main() {
  setUp(() => appLang.value = AppLang.zh);
  test('连着的进度只留最新一条', () {
    final got = compactEvents([
      {'kind': 'task_progress', 'stamp': 5},
      {'kind': 'task_progress', 'stamp': 4},
      {'kind': 'task_progress', 'stamp': 3},
      {'kind': 'task_done', 'stamp': 2},
      {'kind': 'task_progress', 'stamp': 1},
    ]);
    expect(got.map((e) => e['stamp']), [5, 2, 1]);
  });
  test('完成里写着失败、中止的照实说', () {
    expect(robotEventTitle('task_done', {'result': 'failed'}), '任务失败');
    expect(robotEventTitle('task_done', {'result': 'aborted'}), '任务中止');
    expect(robotEventTitle('task_done', {'result': 'done'}), '任务完成');
    expect(cameraName('back'), '后摄像头');
  });
}
