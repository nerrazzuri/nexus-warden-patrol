/// 站点、机器人生成的中文原文按 App 语言说（手机 App 测试 M05；跟网页 `web/console/src/sitetext.tsx` 同一套规则）。
///
/// 英文界面：认得的翻成英文，认不得的那一段不显示中文，写「(in Chinese)」，整句认不得写一句英文说明。
/// 中文界面：机器人原话说成人话（去掉 goto、goal_blocked、检查项名、「起飞」），挨着汉字的半角标点换全角。
/// 改规则时两边一起改（网页那边有 `sitetext.test.ts`，这边有 `site_text_test.dart`）。
library;

import '../l10n.dart';

final RegExp _cjk = RegExp(r'[㐀-鿿]');

bool hasChinese(String s) => _cjk.hasMatch(s);

const String _unk = '\u0000';
const String _fallback = 'Site message in Chinese (switch the language to 中文 to read it)';

const Map<String, String> _preflight = {
  'home': 'the map has no origin yet',
  'localized': 'localization is not settled',
  'device_ready': 'the robot is not ready (control or emergency stop)',
  'nav_ready': 'navigation is not ready',
  'battery': 'battery too low to start',
  'storage': 'robot storage is full',
  'removable': 'robot storage has a problem',
};

const Map<String, String> _preflightZh = {
  'home': '地图还没标原点',
  'localized': '定位还没稳',
  'device_ready': '机器人没准备好（运控或急停）',
  'nav_ready': '导航没准备好',
  'battery': '电量太低，不能出发',
  'storage': '机器人存储满了',
  'removable': '机器人存储有问题',
};

const Map<String, String> _planZh = {
  'goal_blocked': '去不了这个点：终点在障碍物、禁行区里或离得太近',
  'start_blocked': '走不了：机器人所在的地方被障碍物挡住',
  'outside': '这个点在地图外面',
  'no_path': '找不到去终点的路',
  'timeout': '规划路线用时太长',
  'worker': '路线规划出错',
};

const Map<String, String> _plan = {
  'goal_blocked': 'no path — the destination is inside or too close to an obstacle or no-go area',
  'start_blocked': "no path — the robot's own spot is blocked by an obstacle",
  'outside': 'the point is outside the map',
  'no_path': 'no path to the destination',
  'timeout': 'path planning took too long',
  'worker': 'the path planner failed',
};

final RegExp _item = RegExp(r'([a-z_]+)[(（]([^)）]*)[)）]?');

bool _noOrigin(String why) => RegExp(r'原点|出发线').hasMatch(why) && !why.contains('低于');

/// 中文界面：机器人原话说成人话。
String zhRobot(String src) {
  var s = src.replaceAllMapped(RegExp(r'^起飞前检查未通过[:：]\s*([\s\S]*)$'), (m) {
    final rest = m[1]!;
    final seen = <String>{};
    final out = <String>[];
    for (final x in _item.allMatches(rest)) {
      final n = x[1]!, why = x[2] ?? '';
      if (!seen.add(n)) continue;
      final txt = n == 'battery' && _noOrigin(why) ? '算不出返航要留的电量（地图没有可用的原点）' : _preflightZh[n];
      if (txt != null) out.add(txt);
    }
    return '出发前检查未通过：${out.isEmpty ? rest : out.join('；')}';
  });
  s = s
      .replaceAll(RegExp(r'导航拒了[:：]\s*'), '')
      .replaceAllMapped(RegExp(r'(^|[:：;；]\s*)[a-z_]+ 被设备拒绝[:：]\s*'), (m) => m[1]!)
      .replaceAllMapped(
          RegExp(r'重?规划失败[(（](\w+)[)）][:：]?[^;；]*'), (m) => _planZh[m[1]] ?? m[0]!);
  return s;
}

String _lc(String s) => s.length > 1 && RegExp(r'^[A-Z][a-z]').hasMatch(s) ? s[0].toLowerCase() + s.substring(1) : s;
String _pl(String n, String one, String many) => n == '1' ? one : many;

String _preflightList(String s) {
  final seen = <String>{};
  final known = <String>[];
  for (final x in _item.allMatches(s)) {
    final n = x[1]!, why = x[2] ?? '';
    if (!seen.add(n)) continue;
    final txt = n == 'battery' && _noOrigin(why)
        ? 'the turn-back battery level cannot be worked out (the map has no usable origin)'
        : _preflight[n];
    if (txt != null) known.add(txt);
  }
  return known.isEmpty ? _unk : known.join('; ');
}

typedef _Rule = (RegExp, String Function(RegExpMatch m));

final List<_Rule> _rules = [
  (RegExp(r'^跳过 (\d+) 个点[(（]([^)）]*)[)）][:：]\s*([\s\S]*)$'),
      (m) => 'Skipped ${m[1]} ${_pl(m[1]!, 'point', 'points')} (${m[2]}): ${_lc(_en(m[3]!))}'),
  (RegExp(r'^导航拒了[:：]\s*([\s\S]*)$'), (m) => 'Navigation refused: ${_lc(_en(m[1]!))}'),
  (RegExp(r'^\w+ 被设备拒绝[:：]\s*([\s\S]*)$'), (m) => _en(m[1]!)),
  (RegExp(r'^重?规划失败[(（](\w+)[)）][\s\S]*$'), (m) => _plan[m[1]] ?? 'no path (${m[1]})'),
  (RegExp(r'^重规划失败[:：]\s*([\s\S]*)$'), (m) => 'Re-planning failed: ${_lc(_en(m[1]!))}'),
  (RegExp(r'^起飞前检查未通过[:：]\s*([\s\S]*)$'), (m) => 'Pre-departure check failed: ${_preflightList(m[1]!)}'),
  (RegExp(r'^返航失败[:：]\s*未标原点[(（]返航起因[:：]\s*([\s\S]*)[)）]$'),
      (m) => 'Could not return: the map has no origin (it was returning because: ${_lc(_en(m[1]!))})'),
  (RegExp(r'^电量\s*([\d.]+)%\s*低于中止线'), (m) => 'Battery ${m[1]}% is below the turn-back level'),
  (RegExp(r'^([\s\S]*?)[;；]原文[:：][\s\S]*$'), (m) => _en(m[1]!)),
  (RegExp(r'在这儿标原点'),
      (_) => 'Localize the robot on this map, then press “Mark origin here” on the Localization page.'),
  (RegExp(r'帮它重新定位'), (_) => 'Help it find its position on the Localization page, then send it again.'),
  (RegExp(r'急停是否按下'), (_) => 'Check that the emergency stop is released and the site has control.'),
  (RegExp(r'等一分钟再派'), (_) => 'Wait a minute and send it again.'),
  (RegExp(r'先去充电或换电池'), (_) => 'Charge it or swap the battery first.'),
  (RegExp(r'^临时路线 (\d+) 个点$'), (m) => 'One-off route (${m[1]} ${_pl(m[1]!, 'point', 'points')})'),
  (RegExp(r'^临时巡逻不进日程$'), (_) => 'One-off patrol (not in the schedule)'),
  (RegExp(r'^新登记[:：]确认之前只许手动派$'), (_) => 'Newly registered: manual dispatch only until confirmed'),
  (RegExp(r'^(\S+) 离建图时走过的地方 ([\d.]+) m[(（]超过 ([\d.]+) m[)）][,，]那里定位不可靠[:：]先把那里建进图$'),
      (m) => '${m[1]} is ${m[2]} m from where the robot went while mapping (limit ${m[3]} m), '
          'so it cannot locate itself there reliably. Map that area first.'),
  (RegExp(r'^(\S+) 在图上不是可通行的地方'), (m) => '${m[1]} is not a walkable spot on the map (wall, obstacle or not scanned).'),
  (RegExp(r'^(楼梯|台阶|斜坡|草地|碎石路)(\s*\d*)$'),
      (m) => const {'楼梯': 'Stairs', '台阶': 'Steps', '斜坡': 'Slope', '草地': 'Grass', '碎石路': 'Gravel path'}[m[1]]! + m[2]!),
  (RegExp(r"^地图 '([^']+)' 未标原点"), (m) => 'map “${m[1]}” has no origin yet'),
  (RegExp(r'^这个点在地图外面$'), (_) => 'the point is outside the map'),
  (RegExp(r'^这个点在墙、障碍、禁行区里'),
      (_) => 'the point is in or too close to a wall, obstacle or no-go area (no room for the robot)'),
  (RegExp(r'^这个点从待命点、原点走不到$'), (_) => 'the robot cannot get to the point from its standby point or the origin'),
  (RegExp(r'^(\S+) 到 (\S+) 走不通[(（]被墙或禁行区隔开[)）]$'),
      (m) => 'No way from ${m[1]} to ${m[2]} (a wall or no-go area is in between)'),
  (RegExp(r'^摄像头 (\S+)[(（]防区 ([^)）]*)[)）]连不上,这一路的入侵现在收不到[;；]看看摄像头的电源和网线$'),
      (m) => 'Camera ${m[1]} (zone ${m[2]}) cannot be reached, so intrusions from it are not received now. '
          'Check its power and network cable.'),
  (RegExp(r'^点位 (\S+) 连续 (\d+) 趟未到达[:：]路可能被堵住了$'),
      (m) => 'Waypoint ${m[1]} not reached ${m[2]} runs in a row: the way may be blocked'),
  (RegExp(r'^点位 (\S+) 未到达,已跳过$'), (m) => 'Waypoint ${m[1]} not reached, skipped'),
  (RegExp(r'^([\s\S]*?)[;；]?巡逻继续,只做记录$'),
      (m) => '${m[1]!.isNotEmpty ? '${_en(m[1]!)}. ' : ''}The patrol went on; this is only a record.'),
  (RegExp(r'^([\s\S]*?)[;；]?到达一次后自动解除$'),
      (m) => '${m[1]!.isNotEmpty ? '${_parts(m[1]!)}. ' : ''}Clears itself once the point is reached.'),
  (RegExp(r'^到场看看,或者改路线$'), (_) => 'Go and look, or change the route'),
  (RegExp(r'^第 (\d+) 个点[:：]\s*([\s\S]*)$'), (m) => 'Point ${m[1]}: ${_en(m[2]!)}'),
  (RegExp(r'^(\S+) 从现在的位置走不到这个点'),
      (m) => '${m[1]} cannot get to this point from where it is now (a wall or no-go area is in between)'),
  (RegExp(r'^(?:站点盘)?(?:还|只)?剩\s*([\d.]+)\s*(GB|MB|%)$'),
      (m) => '${m[1]}${m[2] == '%' ? '%' : ' ${m[2]}'} free'),
  (RegExp(r'^没有登记过 (\S+)$'), (m) => '${m[1]} is not registered on this site'),
  (RegExp(r'^摄像头 (\S+) 无法连接[(（]防区 ([^)）]+)[)）]$'), (m) => 'Camera ${m[1]} cannot be reached (zone ${m[2]})'),
  (RegExp(r'^(\S+) 无法连接[:：]'), (m) => '${m[1]} cannot be reached'),
  (RegExp(r'^(?:账号 )?(\S+) 已存在$'), (m) => '“${m[1]}” already exists.'),
  (RegExp(r'^账号 (\S+)$'), (m) => 'Account ${m[1]}'),
  (RegExp(r'当前地图上还没有原点'),
      (_) => 'This map has no origin yet. Stand the robot at the origin and press “Mark origin here”.'),
  (RegExp(r'^(\S+) 没有默认待命点$'), (m) => '${m[1]} has no default standby point.'),
  (RegExp(r'^(\S+) 已登记且未吊销'), (m) => '${m[1]} already exists. Unbind it first to add it again.'),
  (RegExp(r'^(\d+) 处不能用$'), (m) => '${m[1]} point${m[1] == '1' ? '' : 's'} cannot be used'),
  // 手机 App 测试 M05：App 上常见的几句
  (RegExp(r'^账号或密码错误$'), (_) => 'Wrong account or password'),
  (RegExp(r'^你的账号[(（]只读[)）]不能做这件事$'), (_) => 'Your account is view-only and cannot do this'),
  (RegExp(r'^没登录或登录已过期$'), (_) => 'Not signed in, or the sign-in has expired'),
  (RegExp(r'^整趟中止了$'), (_) => 'Run stopped before finishing'),
  (RegExp(r'^(\S+) 被 (\S+) 叫停了[:：]先点「恢复」再派$'), (m) => '${m[1]} was stopped by ${m[2]}: tap “Resume” before sending it'),
  (RegExp(r'^机器人看见人了[:：](\d+) 个人(?:[,，]最近 ([\d.]+) m)?$'),
      (m) => 'The robot sees ${m[1]} ${_pl(m[1]!, 'person', 'people')}${m[2] != null ? ', nearest ${m[2]} m' : ''}'),
  (RegExp(r'^值守中$'), (_) => 'On watch'),
  (RegExp(r'^布防中$'), (_) => 'Armed'),
  (RegExp(r'^布防中,机器人不在驱离'),
      (_) => 'The site is armed and the robot is not deterring. Check the photo; tap “Deter here” to deter.'),
  (RegExp(r'^机器人一段时间没看到这个人了'),
      (_) => 'The robot has not seen this person for a while; they may have hidden or left. A guard should go and check.'),
];

String _parts(String s) => s.split(RegExp(r'[;；]')).map(_en).join('. ');

/// 一段原文 → 英文；认不出的换成 [_unk]。
String _en(String s) {
  final x = s.trim();
  if (!hasChinese(x)) return x;
  for (final (re, f) in _rules) {
    final m = re.firstMatch(x);
    if (m != null) return f(m);
  }
  return _unk;
}

/// 中文界面：挨着汉字的半角「( , : ;」换全角（时间 10:30、地址 http://、地图 home:3 不动）。
String zhPunct(String src) {
  if (!hasChinese(src)) return src;
  const h = r'[㐀-鿿「」（）]';
  return src
      .replaceAllMapped(RegExp('($h) ?\\('), (m) => '${m[1]}（')
      .replaceAll(RegExp('\\((?=$h)'), '（')
      .replaceAllMapped(RegExp(r'（([^()（）]*)\)'), (m) => '（${m[1]}）')
      .replaceAllMapped(RegExp('($h|）),\\s?'), (m) => '${m[1]}，')
      .replaceAllMapped(RegExp('($h|）):\\s?(?!//)'), (m) => '${m[1]}：')
      .replaceAllMapped(RegExp('($h|）);\\s?'), (m) => '${m[1]}；');
}

/// 站点、机器人生成的一段话按 App 语言给出（英文认不出的部分写「(in Chinese)」）。
String siteText(String? s) {
  final src = s ?? '';
  if (appLang.value == AppLang.zh) return zhPunct(zhRobot(src));
  if (!hasChinese(src)) return src;
  final out = _en(src);
  if (!out.contains(_unk)) return out;
  return out == _unk ? _fallback : out.split(_unk).join('(in Chinese)');
}

/// 人也可能写的（路线名、区域名）：英文界面只翻认得的站点自动文字，认不得的原样（人写的中文不换掉）。
String siteKnown(String? s) {
  final src = s ?? '';
  if (appLang.value == AppLang.zh) return zhPunct(src);
  if (!hasChinese(src)) return src;
  final out = _en(src);
  return out.contains(_unk) ? src : out;
}
