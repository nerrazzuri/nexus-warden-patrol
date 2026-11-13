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
  // minor #16（A6-02）：遥控结束时机器人报一条 task_done，以前写成「任务完成」，看着像跑完了一趟任务
  test('遥控那一趟结束写「遥控结束」，不写任务完成', () {
    expect(robotEventTitle('task_done', {'task_id': 'teleop-ab12'}), '遥控结束');
    expect(robotEventTitle('task_aborted', {'task_id': 'teleop-ab12'}), '遥控结束');
    expect(robotEventTitle('task_failed', {'task_id': 'teleop-ab12'}), '遥控异常结束');
    expect(robotEventTitle('task_done', {'task_id': 'adhoc-1'}), '任务完成');
  });
}
