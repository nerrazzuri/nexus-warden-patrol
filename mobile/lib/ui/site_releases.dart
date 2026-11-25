/// 站点模式的版本（W00c5d 第三部分，决策 8：版本也由站点管）。
///
/// - 站点上登记过的每一版；每台狗在跑哪一版（狗自己报的）。
/// - 管理员：给一台狗**装**一版（狗后台下载、核对、落槽、建 venv，不切）→ **切**过去（狗要空闲；
///   重启代理，连上站点才算成，起不来自己退回）→ 不对劲就**退**回上一版。
/// - **查**（W00c6d 升级前检查）：切之前看一张清单 —— 狗那边（空闲、电量、盘、装没装、槽里的包对不对、
///   起不起得来、定位器/感知/外参）加站点这边（任务包 schema、备份）。切被狗拒的时候也把清单摆出来。
library;

import 'dart:async';

import 'package:flutter/material.dart';

import '../l10n.dart';
import '../net/site_client.dart';
import '../net/site_text.dart';
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

/// 「构建 35」；老包没写构建号就是空串（真机 11-25：看不出机器人是 34 还是 35）。
String buildTag(Object? n) => n is int && n > 0 ? tr('build $n', '构建 $n') : '';

/// 装版本那几步（机器人报的 `stage`，代理 release_ops.INSTALL_STAGES）。
String installStepText(String stage) =>
    {
      'download': tr('downloading', '下载'),
      'unpack': tr('unpacking', '解包'),
      'verify': tr('checking the signature', '验签名'),
      'stage': tr('storing it on the robot', '存到机器人上'),
      'venv': tr('installing Python packages', '装 Python 环境'),
      'sidecar': tr('building the motion bridge', '编译运控旁路'),
      'superlio': tr('building Super-LIO (about 4 min)', '编译 Super-LIO（约 4 分钟）'),
    }[stage] ??
    stage;

/// 机器人拒收的原因。真机 11-25「一直显示 busy」：代理现在说在忙什么（`busy: 正在装 …(编 Super-LIO,80%) —— …`），
/// 这里去掉后面那句、英文界面把认得的翻过来。
String releaseReasonText(String reason) {
  if (!reason.startsWith('busy:')) return ackReasonText(reason);
  final what = reason.substring(5).split(' —— ').first.trim();
  final inst = RegExp(r'^正在装 (\S+?)[(（](.+?)[,，](\d+)%[)）]$').firstMatch(what);
  if (inst != null) {
    const zhStep = {
      '下载': 'download', '解包': 'unpack', '验签名': 'verify', '落槽': 'stage',
      '装 Python 环境': 'venv', '编运控旁路': 'sidecar', '编 Super-LIO': 'superlio',
    };
    final step = installStepText(zhStep[inst.group(2)] ?? inst.group(2)!);
    return tr('Robot is busy installing ${inst.group(1)} ($step, ${inst.group(3)}%). Try again when it finishes',
        '机器人在忙：正在装 ${inst.group(1)}（$step，${inst.group(3)}%）。等它忙完再试');
  }
  return tr('Robot is busy: $what. Try again when it finishes', '机器人在忙：$what。等它忙完再试');
}

class _SiteReleasesPageState extends State<SiteReleasesPage> with NwAsk {
  late Future<Map<String, dynamic>> _data = _load();
  Timer? _tick;

  /// 发布目录 + 站点自己的版本（真机 11-25：站点自己那一行单独写）。站点版本读不到不影响别的。
  Future<Map<String, dynamic>> _load() async {
    final d = await widget.api.releases();
    try {
      final v = await widget.api.versions();
      return {...d, 'site': v['site']};
    } catch (_) {
      return d;
    }
  }

  @override
  void initState() {
    super.initState();
    // 装、切的时候机器人几秒到几分钟才报一次：页面开着就每 5 秒刷一次（进度条跟着走）
    _tick = Timer.periodic(const Duration(seconds: 5), (_) {
      if (!mounted) return;
      final next = _load();
      next.then((_) {
        if (mounted) {
          setState(() {
            _data = next;
          });
        }
      }, onError: (Object _) {});
    });
  }

  @override
  void dispose() {
    _tick?.cancel();
    super.dispose();
  }

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
          : tr('$robot did not accept: ${releaseReasonText('${ack['reason'] ?? ack['result']}')}',
              '$robot 未接受：${releaseReasonText('${ack['reason'] ?? ack['result']}')}'));
      if (mounted) {
        setState(() {
          _data = _load();
        });
      }
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

  /// 这台最近一次装 / 切走到哪了（站点 `last`）：装的时候按机器人报的哪一步、百分比；切的时候三步
  /// （收下 → 用新版重启 → 跑起来，跑起来就不显示了）；最近一条被拒的写原因。
  /// 真机 11-25 用户「下载给机器人的时候需要有进度条，升级也是」「只能盲猜下发完成了没」。
  List<Widget> _status(String rid, Object? raw, NwColors nw) {
    if (raw is! Map) return const [];
    final cmd = raw['cmd'] as Map?;
    final ev = raw['event'] as Map?;
    final prog = raw['progress'] as Map?;
    final small = NwText.bodySmall.copyWith(color: nw.textSecondary);
    Widget bar(String kind, double v, String label) => Padding(
        key: Key('rel-progress-$kind-$rid'),
        padding: const EdgeInsets.only(top: Nw.s8),
        child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          Row(children: [
            Expanded(child: Text(label, style: small)),
            Text('${(v * 100).round()}%', style: small.copyWith(color: nw.text)),
          ]),
          const SizedBox(height: 4),
          LinearProgressIndicator(value: v, minHeight: 6, color: nw.success, backgroundColor: nw.outline),
        ]));
    final out = <Widget>[];
    final pct = prog?['pct'];
    final accepted = cmd != null && (cmd['result'] == 'accepted' || cmd['result'] == 'duplicate');
    final evNewer = ev != null && cmd != null && (ev['at_ms'] as num? ?? 0) >= (cmd['at_ms'] as num? ?? 0);
    if (prog != null && pct is int) {
      out.add(bar('install', pct / 100,
          tr('Installing ${prog['name']} on the robot: ${installStepText('${prog['stage']}')}',
              '正在装到机器人：${prog['name']}，${installStepText('${prog['stage']}')}')));
    } else if (accepted && cmd['kind'] == 'release_activate') {
      final k = evNewer ? '${ev['kind']}' : '';
      final done = k == 'release_committed' || k == 'release_rolled_back' || k.endsWith('_failed');
      if (!done) {
        final restarting = k == 'release_activating';
        out.add(bar(
            'activate',
            restarting ? 0.66 : 0.33,
            restarting
                ? tr('Switching to ${cmd['name']}: restarting on the new version (about 1–2 min)',
                    '切换到 ${cmd['name']}：正在用新版重启（约 1–2 分钟）')
                : tr('Switching to ${cmd['name']}: the robot accepted and is about to restart',
                    '切换到 ${cmd['name']}：机器人已收下，马上重启')));
      }
    }
    if (cmd != null && cmd['result'] != null && !accepted) {
      out.add(Padding(
          key: Key('rel-refused-$rid'),
          padding: const EdgeInsets.only(top: Nw.s8),
          child: Text(tr('Last command refused: ${releaseReasonText('${cmd['reason'] ?? cmd['result']}')}',
              '上一条命令被拒：${releaseReasonText('${cmd['reason'] ?? cmd['result']}')}'),
              style: small.copyWith(color: nw.error))));
    }
    return out;
  }

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
          final builds = (snap.data!['builds'] as Map? ?? const {}).cast<String, dynamic>();
          final last = (snap.data!['last'] as Map? ?? const {}).cast<String, dynamic>();
          final site = snap.data!['site'] as Map?;
          final sep = tr(', ', '、');
          return RefreshIndicator(
            onRefresh: () async {
              setState(() {
                _data = _load();
              });
              await _data.catchError((Object _) => <String, dynamic>{});
            },
            child: ListView(padding: const EdgeInsets.only(bottom: Nw.s24), children: [
              askStrip(),
              // 真机 11-25：原来这一栏叫「站点上的版本」，用户当成站点自己的版本（看到 34 就问站点为什么还是 34）
              if (site != null)
                section(tr('Site (this computer)', '站点（这台电脑）'), [
                  line(Text(
                      [
                        '${site['version'] ?? '—'}',
                        buildTag(site['release_build']),
                        if ((site['release_name'] ?? '') != '') '${site['release_name']}',
                      ].where((s) => s.isNotEmpty).join(' · '),
                      key: const Key('rel-site-version'),
                      style: NwText.bodyMedium.copyWith(color: nw.text))),
                ]),
              section(tr('Robot update packages (kept on this site)', '机器人升级包（存在站点上）'), [
                Text(
                    tr('For the robots, not the site\'s own version.', '给机器人用的包，不是站点自己的版本。'),
                    style: sub),
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
                        Text(
                            [
                              tr('${r['name']} (${r['version']})', '${r['name']}（${r['version']}）'),
                              buildTag(r['build']),
                            ].where((s) => s.isNotEmpty).join(' · '),
                            style: title.copyWith(fontWeight: FontWeight.w700)),
                        Text(
                            [
                              '${((r['size'] as num? ?? 0) / 1048576).toStringAsFixed(1)} MB',
                              if ((r['note'] ?? '') != '') siteKnown('${r['note']}'),
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
                              e.value == null
                                  ? tr('Version not reported. This robot software does not report it, so it cannot be updated from here.', '没报版本：这台机器人的软件不报自己的版本，所以不能从这里升级。')
                                  : ['${e.value}', buildTag(builds[e.key])].where((s) => s.isNotEmpty).join(' · '),
                              style: NwText.bodyMedium.copyWith(color: e.value == null ? nw.textSecondary : nw.text))),
                    ]),
                    ..._status(e.key, last[e.key], nw),
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
                  // 真机 11-25：只写 1.0.0-rc.1 看不出是 34 还是 35
                  Expanded(
                      child: Text(tr('This phone $appVersion (build $appBuild)', '这台手机 $appVersion（构建 $appBuild）'),
                          key: const Key('rel-app-version'), style: NwText.bodyMedium.copyWith(color: nw.text))),
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
