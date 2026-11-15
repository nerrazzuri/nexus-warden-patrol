/// 派单被站点拒了（W53 设计 D10）：不再一闪而过，说**为什么**，再给一个**去处理**的按钮。
///
/// App V2（稿 N-refuse）：不弹框 —— 页面顶上一条琥珀三角的说明（ScaffoldMessenger 的横幅），
/// 「去处理」和「知道了」一排等宽；没站起来的直接给「让 A 站起来」。
///
/// 站点在 409 里带 `reason_code`（十五种常见拒绝）和一句英文 `reason_en`；中文界面照站点原话。按代号给按钮：
/// 叫停了 → 「恢复」；禁行区没确认 → 管理员「去确认」、别人「请管理员确认」；要人监护、没定位、没就绪 → 「去机器人页」。
/// 没带代号的照旧只说原话。
library;

import 'dart:async';

import 'package:flutter/material.dart';

import '../l10n.dart';
import '../net/site_client.dart';
import 'site_mapping.dart';
import 'nw/nw_theme.dart';
import 'site_robot.dart';

/// 被拒说明里「去处理」那个按钮、「知道了」、整条说明（Key 测试用）。
const Key refusalActionKey = Key('refusal-action');
const Key refusalAckKey = Key('refusal-ack');
const Key refusalDialogKey = Key('refusal-dialog');

/// 禁行区没确认：从原话里抠出是哪张图哪一版（`estate-1:7 当前的区域修订…`）。
(String, String)? zonesMapOf(String message) {
  final m = RegExp(r'^(\S+?):(\S+?)\s*当前的区域修订').firstMatch(message);
  return m == null ? null : (m.group(1)!, m.group(2)!);
}

/// 按代号给一句「你可以做什么」（没有就空串）。
String refusalHint(String code, SiteSession? s) => switch (code) {
      'held' => (s?.canDispatch ?? false)
          ? tr('Tap Resume once it is safe.', '确认安全后点「恢复」。')
          : tr('Only a guard or administrator can resume it. Ask one of them.', '只有保安或管理员能点「恢复」，请找他们。'),
      'zones_unconfirmed' => (s?.canManageMaps ?? false)
          ? tr('Review the no-go zones on the map and confirm this version.', '请在地图上核对禁行区并确认此版本。')
          : tr('An administrator must confirm the no-go zones first. Remote control is unaffected.',
              '需要管理员先确认禁行区。遥控不受影响。'),
      'supervision' => tr('Turn on "I\'m supervising" on the robot page.', '请在机器人页开启「我在现场监护」。'),
      'not_localized' => tr('Set the position on the robot page.', '请在机器人页「设位置」。'),
      'offline' => tr('Check the robot is powered on and connected.', '请检查机器人是否开机、网络是否连通。'),
      'teleop' => tr('Dispatch after remote control ends.', '请在遥控结束后再派。'),
      // 易用性第 6 轮 A6-03：管理员自己就能下发，不叫他「请管理员」
      'map_mismatch' => (s?.canManageMaps ?? false)
          ? tr('Pick a route drawn on the map this robot uses, or send it the right map version on the Maps page.',
              '换一条画在这台机器人当前地图上的路线，或在「地图」页给它下发对应的版本。')
          : tr('Ask an administrator to send the correct map to this robot.', '请管理员为此机器人下发正确的地图。'),
      // A6-02：未就绪按原因说（原来一律「还在启动、充电或站起来」）
      // A7-01：蹲着时站点不让开遥控 —— 去机器人页点「站起」
      'not_standing' => tr('On the robot page, tap Stand up, then dispatch again.', '在机器人页点「站起」，再派一次。'),
      'estop' => tr('Release the e-stop on the robot, then dispatch again.', '松开机器人上的急停，再派一次。'),
      'no_control' => tr('Put the handheld remote down / hand control back to the site, then dispatch again.',
          '放下手柄，把控制权交回站点，再派一次。'),
      _ => '',
    };

/// 页面顶上那条被拒说明。[robotId] 给了才有「恢复」「去机器人页」「让它站起来」；[onChanged] 在按了
/// 「恢复」「站起来」之后调（页面刷新）。按了「知道了」、或者「去处理」那一页回来了才返回 ——
/// 调用方据此重看状态、换掉旧提示（A7-04）。
Future<void> showRefusal(BuildContext context, SiteApi api, SiteError e,
    {String? robotId, String? title, VoidCallback? onChanged}) async {
  final m = ScaffoldMessenger.maybeOf(context);
  if (m == null) return;
  final code = '${e.body['reason_code'] ?? ''}';
  final s = api.session;
  var hint = refusalHint(code, s);
  final zones = code == 'zones_unconfirmed' ? zonesMapOf(e.message) : null;
  String? label;
  Future<void> Function(BuildContext)? act;
  Future<void> open(BuildContext c, Widget page) =>
      Navigator.push(c, MaterialPageRoute<void>(builder: (_) => page));
  Future<void> run(BuildContext c, Future<Object?> Function() f) async {
    try {
      await f();
      onChanged?.call();
    } on SiteError catch (err) {
      if (c.mounted) ScaffoldMessenger.of(c).showSnackBar(SnackBar(content: Text(refusalText(err))));
    }
  }
  if (code == 'held' && robotId != null && (s?.canDispatch ?? false)) {
    label = tr('Resume', '恢复');
    act = (c) => run(c, () => api.resume(robotId));
  } else if (code == 'not_standing' && robotId != null && (s?.canTeleop ?? false)) {
    // 稿 N-refuse：就地「让 A 站起来」；原来站起前那句当心旁边有人写在说明里
    label = tr('Stand $robotId up', '让 $robotId 站起来');
    hint = tr('$robotId will stand up where it is. Make sure no one is right next to it, then dispatch again.',
        '$robotId 会原地站起来，先确认旁边没有人，站好后再派一次。');
    act = (c) => run(c, () => api.posture(robotId, 'stand'));
  } else if (zones != null && (s?.canManageMaps ?? false)) {
    label = tr('Confirm zones', '去确认');
    act = (c) async => open(c, SiteMapPreviewPage(api: api, mapId: zones.$1, version: zones.$2));
  } else if (robotId != null &&
      const {'supervision', 'not_localized', 'not_ready', 'obstacles', 'teleop', 'not_standing', 'estop', 'no_control'}
          .contains(code)) {
    label = tr('Open robot', '去机器人页');
    act = (c) async => open(c, SiteRobotPage(api: api, robotId: robotId));
  }
  final done = Completer<bool>();
  void close(bool go) {
    m.hideCurrentMaterialBanner();
    if (!done.isCompleted) done.complete(go);
  }

  final head = title == null ? tr('Not dispatched', '没派出去') : tr('$title: not done', '$title：没成');
  m.clearMaterialBanners();
  m.showMaterialBanner(MaterialBanner(
    key: refusalDialogKey,
    backgroundColor: Nw.of(context).warningSoft,
    leading: Icon(Icons.warning_amber_rounded, color: Nw.of(context).warning),
    content: Builder(builder: (c) {
      final nw = Nw.of(c);
      return Column(crossAxisAlignment: CrossAxisAlignment.stretch, mainAxisSize: MainAxisSize.min, children: [
        Text(head, style: NwText.titleSmall.copyWith(color: nw.text, fontWeight: FontWeight.w700)),
        const SizedBox(height: Nw.s4),
        Text([refusalText(e), if (hint.isNotEmpty) hint].join(' '), style: NwText.bodyMedium.copyWith(color: nw.text)),
        const SizedBox(height: Nw.s8),
        Row(children: [
          if (label != null && act != null) ...[
            Expanded(
                child: FilledButton(
                    key: refusalActionKey,
                    style: FilledButton.styleFrom(minimumSize: const Size(48, 44)),
                    onPressed: () => close(true),
                    child: Text(label, textAlign: TextAlign.center))),
            const SizedBox(width: Nw.s8),
          ],
          Expanded(
              child: OutlinedButton(
                  key: refusalAckKey,
                  style: OutlinedButton.styleFrom(minimumSize: const Size(48, 44)),
                  onPressed: () => close(false),
                  child: Text(tr('Acknowledge', '知道了')))),
        ]),
      ]);
    }),
    actions: const [SizedBox.shrink()],
  ));
  final go = await done.future;
  if (go && act != null && context.mounted) await act(context);
}
