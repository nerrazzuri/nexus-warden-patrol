import 'package:flutter_test/flutter_test.dart';
import 'package:nexwar_patrol/model/alert.dart';
import 'package:nexwar_patrol/ui/alarm_log.dart';
import 'package:nexwar_patrol/net/site_text.dart';

Alert _a(String kind, String level, String audience, {String channel = 'screen'}) => Alert(
    key: 'A/$kind#1', level: level, kind: kind, robot: 'A', title: kind, detail: '', firstMs: 1, lastMs: 1,
    count: 1, ackedBy: '', ackedMs: null, resolvedMs: null, escalated: 0, channel: channel, audience: audience);

void main() {
  test('易用性 r7:发给经理的 P1(换电 30 分钟没进展)也进保安的报警记录 —— 手机会为它响,保安得找得到', () {
    final a = _a('swap_overdue', 'P1', 'owner', channel: 'sound');
    expect(AlarmLogPage.isAlarm(a), isTrue);
    expect(AlarmLogPage.isTodo(a), isFalse);
  });

  test('发给经理的 P2 照旧是待处理事项、不算报警', () {
    final a = _a('backup_stale', 'P2', 'owner');
    expect(AlarmLogPage.isAlarm(a), isFalse);
    expect(AlarmLogPage.isTodo(a), isTrue);
  });

  test('易用性 r7:报警行不写内部写法 —— zone:1 写成「防区 1」,标题已经以来源开头就不再重复', () {
    expect(alertSourceText('zone:1'), '防区 1');
    expect(alertLine('A', 'swap_needed', 'A 已到换电位,请来换电池'), 'A 已到换电位,请来换电池'.replaceAll(',', '，'));
    expect(alertLine('zone:1', 'zone_unwatched', '防区 1 已 27 分钟没巡到'), '防区 1 已 27 分钟没巡到');
    expect(alertLine('B', 'stuck', 'Alpha 卡住了'), startsWith('B · '));
  });
}
