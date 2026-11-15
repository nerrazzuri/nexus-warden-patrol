/// 站点模式的版本（W00c5d 第三部分，决策 8：版本也由站点管）。
///
/// - 站点上登记过的每一版；每台狗在跑哪一版（狗自己报的）。
/// - 管理员：给一台狗**装**一版（狗后台下载、核对、落槽、建 venv，不切）→ **切**过去（狗要空闲；
///   重启代理，连上站点才算成，起不来自己退回）→ 不对劲就**退**回上一版。
/// - **查**（W00c6d 升级前检查）：切之前看一张清单 —— 狗那边（空闲、电量、盘、装没装、槽里的包对不对、
///   起不起得来、定位器/感知/外参）加站点这边（任务包 schema、备份）。切被狗拒的时候也把清单摆出来。
library;

import 'package:flutter/material.dart';

import '../l10n.dart';
import '../net/site_client.dart';
import 'app_settings.dart' show openSettings;
import 'nw/nw_button.dart';
import 'nw/nw_p4_admin.dart';
import 'nw/nw_ask.dart';
import 'nw/nw_theme.dart';
import 'nw/nw_widgets.dart';

class SiteReleasesPage extends StatefulWidget {
  final SiteApi api;
  const SiteReleasesPage({super.key, required this.api});

  static Key robotKey(String id) => Key('rel-robot-$id');
  static Key actionKey(String id, String action) => Key('rel-$action-$id');
  static const Key appKey = Key('rel-app-check');

  @override
  State<SiteReleasesPage> createState() => _SiteReleasesPageState();
}

class _SiteReleasesPageState extends State<SiteReleasesPage> with NwAsk {
  late Future<Map<String, dynamic>> _data = widget.api.releases();

  void _snack(String t) {
    if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(t)));
  }

  Future<String?> _pick(List<String> names) => ask<String>(
      title: tr('Which release', '哪一版'), choices: [for (final n in names) AskChoice(n, n, key: Key('pick-rel-$n'))]);

  Future<void> _act(String robot, String action, List<String> names) async {
    var name = '';
    if (action != 'rollback') {
      final got = await _pick(names);
      if (got == null) return;
      name = got;
    }
    final what = {
      'install': tr('install', '安装'),
      'activate': tr('activate', '启用'),
      'rollback': tr('Roll back to the previous release', '退回上一版'),
    }[action];
    if (!mounted) return;
    if (action == 'precheck') {
      try {
        final r = await widget.api.releaseAction(robot, action, name: name);
        if (!mounted) return;
        await _showChecks(tr('Before activating $name on $robot', '$robot 切到 $name 之前'), r);
      } on SiteError catch (e) {
        _snack(tr('Check failed: $e', '检查失败：$e'));
      }
      return;
    }
    if (action != 'install') {
      final ok = await askYes(tr('$robot: $what $name', '$robot $what $name'),
          body: tr('The robot restarts its software (tens of seconds) and refuses while a task is running. Continue?',
              '机器人上的程序要重启（约几十秒），执行任务时会拒绝。确定继续？'),
          ok: tr('Confirm', '确定'),
          okKey: const Key('rel-confirm'));
      if (!ok) return;
    }
    try {
      final r = await widget.api.releaseAction(robot, action, name: name);
      final ack = (r['ack'] as Map?) ?? const {};
      _snack(ack['result'] == 'accepted'
          ? tr('$robot accepted: $what $name (it reports when done; the site raises an alarm on failure)',
              '$robot 已接受：$what $name（完成后上报，失败时站点报警）')
          : tr('$robot did not accept: ${ack['reason'] ?? ack['result']}',
              '$robot 未接受：${ack['reason'] ?? ack['result']}'));
      final data = ack['data'];
      if (mounted && ack['result'] != 'accepted' && data is Map<String, dynamic>) {
        // 狗拒切时回执里带着清单
        await _showChecks(tr('$robot did not activate: reasons', '$robot 未切换：原因'), data);
      }
    } on SiteError catch (e) {
      _snack(tr('Not sent: $e', '发送失败：$e'));
    }
  }

  /// 升级前检查的清单：拦住的在前，只是提示的标出来。
  Future<void> _showChecks(String title, Map<String, dynamic> r) {
    final checks = (r['checks'] as List? ?? const []).whereType<Map>().toList()
      ..sort((a, b) => _rank(a).compareTo(_rank(b)));
    final blocking = (r['blocking'] as List? ?? const []).length;
    final nw = Nw.of(context);
    // App V2：清单就地摆在页面上面（不弹窗），「确定」收起
    return ask<bool>(
          title: title,
          choices: const [],
          cancel: tr('OK', '确定'),
          content: Column(crossAxisAlignment: CrossAxisAlignment.stretch, mainAxisSize: MainAxisSize.min, children: [
              // 能切是绿的；不能切是红的（拦着的那几项也是红的，只是提示的是橙的）
              Text(
                  r['ok'] == true
                      ? tr('Can activate: all blocking checks passed', '可以切换：所有阻断检查均已通过')
                      : tr('Cannot activate: $blocking blocking check(s) failed', '不能切换：$blocking 项阻断检查未通过'),
                  key: const Key('precheck-verdict'),
                  style: NwText.titleSmall.copyWith(color: r['ok'] == true ? nw.success : nw.error)),
              nwGap8,
              for (final ch in checks)
                ListTile(
                  key: Key('precheck-item-${ch['name']}'),
                  dense: true,
                  contentPadding: EdgeInsets.zero,
                  leading: Icon(
                      ch['ok'] == true
                          ? Icons.check_circle_rounded
                          : (ch['blocking'] == true ? Icons.cancel_rounded : Icons.warning_amber_rounded),
                      color: ch['ok'] == true ? nw.success : (ch['blocking'] == true ? nw.error : nw.warning)),
                  title: Text(
                      '${_label('${ch['name']}')}'
                      '${ch['ok'] != true && ch['blocking'] != true ? tr(' (advisory, not blocking)', '（仅提示，不阻断）') : ''}',
                      style: NwText.bodyMedium.copyWith(color: nw.text)),
                  subtitle: Text('${ch['detail'] ?? ''}', style: NwText.bodySmall.copyWith(color: nw.textSecondary)),
                ),
            ]));
  }

  /// 清单项的名字：狗与站点报的是英文键，给人看中文（不认识的原样显示）。
  static String _label(String name) =>
      {
        'busy': tr('Idle', '空闲'),
        'battery': tr('Battery', '电量'),
        'disk': tr('Disk', '磁盘'),
        'version': tr('Version', '版本'),
        'installed': tr('Installed', '已安装'),
        'package': tr('Package intact', '安装包完整'),
        'schema': tr('Task package format', '任务包格式'),
        'agent_start': tr('Agent starts after activation', '启用后可正常启动'),
        'localizer': tr('Localizer', '定位器'),
        'perception': tr('Perception', '感知'),
        'extrinsic': tr('Extrinsics', '外参'),
        'backup': tr('Site backup', '站点备份'),
      }[name] ??
      name;

  /// 排序：拦住的不过项 → 提示的不过项 → 过了的。
  static int _rank(Map ch) => ch['ok'] == true ? 2 : (ch['blocking'] == true ? 0 : 1);

  @override
  Widget build(BuildContext context) {
    final admin = widget.api.session?.canManageMaps ?? false;
    final nw = Nw.of(context);
    final title = NwText.titleSmall.copyWith(color: nw.text);
    final sub = NwText.bodySmall.copyWith(color: nw.textSecondary);
    // App V2 稿 S-updates：站点上的版本（哪台在跑）、各机器人在跑的（按钮一排等宽）、手机 App
    Widget section(String label, List<Widget> rows, {Key? key}) => Container(
        key: key,
        margin: const EdgeInsets.only(top: Nw.s8),
        color: nw.surface,
        padding: const EdgeInsets.fromLTRB(Nw.s16, Nw.s16, Nw.s16, Nw.s8),
        child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          Text(label, style: NwText.titleMedium.copyWith(color: nw.text, fontWeight: FontWeight.w700)),
          const SizedBox(height: Nw.s8),
          ...rows,
        ]));
    Widget line(Widget child) => Container(
        padding: const EdgeInsets.symmetric(vertical: 10),
        decoration: BoxDecoration(border: Border(top: BorderSide(color: nw.outline))),
        child: child);
    return Scaffold(
      appBar: AppBar(title: Text(tr('Software updates', '软件升级'))),
      body: FutureBuilder<Map<String, dynamic>>(
        future: _data,
        builder: (_, snap) {
          if (snap.hasError) {
            return NwListView(children: [
              NwNotice(
                  tone: NwTone.error, text: tr('Releases unavailable: ${snap.error}', '无法加载：${snap.error}')),
            ]);
          }
          if (!snap.hasData) return const Center(child: CircularProgressIndicator());
          final rels = (snap.data!['releases'] as List).whereType<Map<String, dynamic>>().toList();
          final names = [for (final r in rels) '${r['name']}'];
          final robots = (snap.data!['robots'] as Map).cast<String, dynamic>();
          final sep = tr(', ', '、');
          return RefreshIndicator(
            onRefresh: () async {
              setState(() {
                _data = widget.api.releases();
              });
              await _data.catchError((Object _) => <String, dynamic>{});
            },
            child: ListView(padding: const EdgeInsets.only(bottom: Nw.s24), children: [
              askStrip(),
              section(tr('Versions on the site', '站点上的版本'), [
                if (rels.isEmpty) line(Text(tr('No releases registered yet', '暂无已登记版本'), style: sub)),
                for (final r in rels)
                  () {
                    final on = [for (final e in robots.entries) if (e.value == r['name']) e.key];
                    return line(Row(key: Key('rel-release-${r['name']}'), crossAxisAlignment: CrossAxisAlignment.start, children: [
                      Padding(
                          padding: const EdgeInsets.only(top: 4, right: Nw.s8),
                          child: on.isEmpty
                              ? Icon(Icons.circle, size: 10, color: nw.primary)
                              : Icon(Icons.square, size: 10, color: nw.success)),
                      Expanded(
                          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                        Text(tr('${r['name']} (${r['version']})', '${r['name']}（${r['version']}）'),
                            style: title.copyWith(fontWeight: FontWeight.w700)),
                        Text(
                            [
                              '${((r['size'] as num? ?? 0) / 1048576).toStringAsFixed(1)} MB',
                              if ((r['note'] ?? '') != '') '${r['note']}',
                              on.isEmpty ? tr('Not installed', '没装') : tr('Running on ${on.join(sep)}', '${on.join(sep)} 在跑'),
                            ].join(' · '),
                            style: sub),
                      ])),
                    ]));
                  }(),
              ]),
              section(tr('Running per robot', '各机器人在跑的'), [
                for (final e in robots.entries)
                  line(Column(key: SiteReleasesPage.robotKey(e.key), crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                    Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                      SizedBox(width: 32, child: Text(e.key, style: title.copyWith(fontWeight: FontWeight.w700))),
                      Expanded(
                          child: Text(
                              '${e.value ?? tr('Version not reported. This robot software does not report it, so it cannot be updated from here.', '没报版本：这台机器人的软件不报自己的版本，所以不能从这里升级。')}',
                              style: NwText.bodyMedium.copyWith(color: e.value == null ? nw.textSecondary : nw.text))),
                    ]),
                    // 狗没报在跑哪一版 = 没报发布能力（或者不在线）：按了也是 unsupported，不给按钮。
                    if (admin && e.value != null) ...[
                      nwGap8,
                      Row(children: [
                        for (final (i, (a, label)) in [
                          ('install', tr('Install', '安装')),
                          ('precheck', tr('Check', '检查')),
                          ('activate', tr('Activate', '启用')),
                          ('rollback', tr('Roll back', '回退')),
                        ].indexed) ...[
                          if (i > 0) const SizedBox(width: Nw.s8),
                          Expanded(
                              child: NwButton(
                                  buttonKey: SiteReleasesPage.actionKey(e.key, a),
                                  variant: NwButtonVariant.outline,
                                  size: NwButtonSize.small,
                                  onPressed: () => _act(e.key, a, names),
                                  label: label)),
                        ],
                      ]),
                    ],
                  ])),
              ]),
              section(tr('Mobile app', '手机 App'), [
                line(Row(children: [
                  Icon(Icons.square, size: 10, color: nw.success),
                  const SizedBox(width: Nw.s8),
                  Expanded(child: Text(tr('This phone $appVersion', '这台手机 $appVersion'), style: NwText.bodyMedium.copyWith(color: nw.text))),
                  OutlinedButton(
                      key: SiteReleasesPage.appKey,
                      style: OutlinedButton.styleFrom(
                          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(2)), minimumSize: const Size(48, 40)),
                      onPressed: () => openSettings(context, widget.api),
                      child: Text(tr('Check for updates', '检查更新'))),
                ])),
              ]),
            ]),
          );
        },
      ),
    );
  }
}
