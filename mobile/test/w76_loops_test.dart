// W76 循环巡逻：机器人状态行写第几圈。
import 'package:flutter_test/flutter_test.dart';
import 'package:nexwar_patrol/l10n.dart';
import 'package:nexwar_patrol/ui/patrol_dispatch.dart';
import 'package:nexwar_patrol/ui/site_robot.dart';

Map<String, dynamic> _r(Object? lap) => <String, dynamic>{
      'fresh': true,
      'lap': lap,
      'status': <String, dynamic>{
        'online': true,
        'task': <String, dynamic>{'task_id': 'adhoc-forever-x', 'kind': 'patrol', 'state': 'running'},
      },
    };

void main() {
  setUp(() => appLang.value = AppLang.zh);

  test('几圈的巡逻写第几圈，一直巡逻也写，一圈的不写', () {
    expect(robotStatusLine(_r(<String, dynamic>{'n': 2, 'of': 3})), contains('第 2 / 3 圈'));
    expect(robotStatusLine(_r(<String, dynamic>{'n': 5, 'of': 0})), contains('一直巡逻 · 第 5 圈'));
    expect(robotStatusLine(_r(null)), isNot(contains('圈')));
  });

  test('第 9 轮 W9-05：下一趟排给的机器人蹲着，那一行写出来；不是下一趟、就绪了的不写', () {
    expect(patrolNotReadyText({'state': 'next', 'robot': 'B', 'not_ready': ['motion']}), 'B 现在没站起来，到点前不好就跑不了');
    expect(patrolNotReadyText({'state': 'later', 'robot': 'B', 'not_ready': ['motion']}), '');
    expect(patrolNotReadyText({'state': 'next', 'robot': 'B'}), '');
  });

  test('循环次数的字', () {
    expect(patrolLoopChoices, <int>[1, 2, 3, 5, 10, 0]);
    expect(loopsText(0), '一直巡逻');
    expect(loopsText(3), '3 圈');
  });
}
