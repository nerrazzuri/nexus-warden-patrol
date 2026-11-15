/// 远程运维（W55）：管理员、工程师在手机上看机器人的诊断快照、各服务日志，重启服务、重启整机（再输一次密码，
/// 仅空闲时）、开 1 小时详细日志、立即对时、立即续签证书。入口在单机器人页「管理」区，机器人报了 `ops_diag` 才有。
/// 网页上「高级 → 诊断」是同一套（`web/console/src/remoteops.tsx`）。
library;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../l10n.dart';
import '../net/site_client.dart';
import 'nw/nw_theme.dart';
import 'nw/nw_widgets.dart';

/// 能看日志、能重启的服务（跟机器人上执行器的白名单一致）。
const List<String> opsUnits = <String>[
  'nexwar_agent', 'nexwar_localizer', 'nexwar_obstacles', 'nexwar_persons', 'nexwar_lidar_merge',
  'nexwar_nav2', 'nexwar_sidecar', 'nexwar_zenohd', 'nexwar_bind',
];

/// 机器人报的全部运维能力（测试、版面矩阵用）。
const Set<String> robotOpsAll = <String>{
  'ops_diag', 'ops_journal', 'ops_restart', 'ops_reboot', 'ops_debug', 'ops_timesync', 'ops_cleanup', 'cert_csr',
  'ops_settings',
};

/// 11-06 不靠 SSH：站点能改的机器人设置（跟 nexwar_contract.robot_settings 一样）：键 → 名字。
Map<String, String> get robotSettingNames => <String, String>{
      'NEXWAR_PERSONS': tr('Person detection', '人员检测'),
      'NEXWAR_OBS_PERMIT': tr('Obstacle clearance permit', '障碍净空许可'),
      'NEXWAR_MAX_FRACTION': tr('Forward speed cap', '前进速度上限'),
      'NEXWAR_VENDOR_PAUSE': tr('Pause vendor processes at boot', '开机暂停厂家进程'),
      'NEXWAR_VENDOR_AUTOSTART': tr("Vendor services we don't use start at boot", '厂家用不上的服务开机自启'),
    };

/// 设置的取值说人话。
String robotSettingValue(String k, String v) => k == 'NEXWAR_MAX_FRACTION'
    ? '${((double.tryParse(v) ?? 0) * 100).round()}%'
    : (v == 'bridge' || v == '1')
        ? tr('On', '开')
        : tr('Off', '关');

/// 字节数说人话（诊断快照里的内存、磁盘）。
String opsBytes(Object? n) {
  if (n is! num) return '—';
  if (n >= 1 << 30) return '${(n / (1 << 30)).toStringAsFixed(1)} GB';
  return '${(n / (1 << 20)).round()} MB';
}

/// 诊断快照摘成几行给人看：版本、开机时长、内存、磁盘、温度、时间同步、证书、各服务。
List<(String, String)> diagLines(Map<String, dynamic> d) {
  final out = <(String, String)>[];
  final rel = d['release'];
  if (rel is Map) out.add((tr('Software version', '软件版本'), '${rel['current'] ?? '—'}'));
  final up = d['uptime_s'];
  if (up is num) out.add((tr('Uptime', '开机时长'), '${(up / 3600).toStringAsFixed(1)} h'));
  final mem = d['memory'];
  if (mem is Map) {
    out.add((tr('Memory available', '可用内存'), '${opsBytes(mem['MemAvailable'])} / ${opsBytes(mem['MemTotal'])}'));
  }
  final disks = d['disks'];
  if (disks is Map) {
    for (final e in disks.entries) {
      final v = e.value;
      out.add((tr('Disk free (${e.key})', '磁盘剩余（${e.key}）'),
          v is Map ? '${opsBytes(v['free'])} / ${opsBytes(v['total'])}' : '—'));
    }
  }
  final temps = d['temps_c'];
  if (temps is Map && temps.isNotEmpty) {
    out.add((tr('Temperatures', '温度'),
        temps.entries.map((e) => '${e.key} ${(e.value as num).round()}°C').join(' · ')));
  }
  final time = d['time'];
  if (time is Map) {
    final s = time['synced'];
    out.add((tr('Time sync', '时间同步'),
        s == true ? tr('Synced', '已同步') : s == false ? tr('Not synced', '未同步') : tr('Unknown', '未知')));
  }
  final cert = d['cert'];
  if (cert is Map) out.add((tr('Certificate expiry', '证书到期'), '${cert['not_after'] ?? cert['error'] ?? '—'}'));
  if (d['busy'] is String && (d['busy'] as String).isNotEmpty) out.add((tr('Busy', '忙'), '${d['busy']}'));
  final svcs = d['services'];
  if (svcs is List) {
    for (final s in svcs.whereType<Map>()) {
      if ('${s['active'] ?? ''}'.isEmpty) continue;
      final r = s['restarts'];
      out.add(('${s['unit']}', '${s['active']}/${s['sub']}${r is num && r > 0 ? tr(' · restarted $r×', ' · 重启 $r 次') : ''}'));
    }
  }
  return out;
}

class RobotOpsPage extends StatefulWidget {
  final SiteApi api;
  final String robotId;

  /// 机器人报的能力（`capabilities.tasks` 的键）：报了哪样才给哪样按钮。
  final Set<String> tasks;
  const RobotOpsPage({super.key, required this.api, required this.robotId, required this.tasks});

  static const Key diagKey = Key('ops-diag');
  static const Key logKey = Key('ops-log');
  static const Key restartGoKey = Key('ops-restart-go');
  static const Key restartKey = Key('ops-restart');
  static const Key rebootKey = Key('ops-reboot');
  static const Key debugKey = Key('ops-debug');
  static const Key timesyncKey = Key('ops-timesync');
  static const Key certKey = Key('ops-cert');
  static const Key rebootPwKey = Key('ops-reboot-pw');
  static const Key rebootGoKey = Key('ops-reboot-go');
  static const Key settingsKey = Key('ops-settings');
  static const Key settingsSaveKey = Key('ops-settings-save');
  static const Key settingsPwKey = Key('ops-settings-pw');
  static const Key settingsGoKey = Key('ops-settings-go');

  @override
  State<RobotOpsPage> createState() => _RobotOpsPageState();
}

class _RobotOpsPageState extends State<RobotOpsPage> {
  Map<String, dynamic>? _diag;
  Map<String, dynamic>? _log;
  String _unit = 'nexwar_agent';
  int _hours = 6;
  bool _busy = false;
  String? _msg;
  bool _msgBad = false;
  Map<String, String>? _sets;
  Map<String, List<String>> _choices = const {};
  Map<String, String> _draft = <String, String>{};

  Map<String, String> get _changed =>
      {for (final e in _draft.entries) if (_sets?[e.key] != e.value) e.key: e.value};
  bool get _setConflict =>
      (_draft['NEXWAR_MAX_FRACTION'] ?? '0.5') != '0.5' && _draft['NEXWAR_OBS_PERMIT'] != '1';

  Future<void> _loadSettings() => _run(() async {
        final d = await widget.api.robotOps(widget.robotId, 'settings');
        final cur = ((d['settings'] as Map?) ?? const {}).map((k, v) => MapEntry('$k', '$v'));
        final ch = ((d['choices'] as Map?) ?? const {})
            .map((k, v) => MapEntry('$k', ((v as List?) ?? const []).map((e) => '$e').toList()));
        if (mounted) {
          setState(() {
            _sets = cur;
            _choices = ch;
            _draft = Map<String, String>.of(cur);
          });
        }
      });

  Future<void> _saveSettings() async {
    final pw = TextEditingController();
    final ok = await showDialog<bool>(
        context: context,
        builder: (c) => AlertDialog(
              title: Text(tr('Change settings of ${widget.robotId}?', '修改 ${widget.robotId} 的设置？')),
              content: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text(tr('The robot must be idle. Enter your password to confirm.', '机器人要空闲。请输入你的密码确认。')),
                TextField(
                    key: RobotOpsPage.settingsPwKey,
                    controller: pw,
                    obscureText: true,
                    decoration: InputDecoration(labelText: tr('Your password', '你的密码'))),
              ]),
              actions: [
                TextButton(onPressed: () => Navigator.pop(c, false), child: Text(tr('Cancel', '取消'))),
                FilledButton(
                    key: RobotOpsPage.settingsGoKey,
                    onPressed: () => Navigator.pop(c, true),
                    child: Text(tr('Save', '保存'))),
              ],
            ));
    final p = pw.text;
    if (ok != true) return;
    final changes = _changed;
    await _run(() async {
      await widget.api.robotOps(widget.robotId, 'settings',
          body: <String, dynamic>{'set': changes, 'confirm_password': p});
      if (mounted) setState(() => _sets = null);
    },
        ok: tr('Settings saved. The robot restarts its services and is back in about 1 minute.',
            '设置已保存，机器人重启相关服务，约 1 分钟后恢复。'));
  }

  bool _has(String k) => widget.tasks.contains(k);

  Future<void> _run(Future<void> Function() fn, {String? ok}) async {
    setState(() {
      _busy = true;
      _msg = null;
    });
    try {
      await fn();
      if (mounted && ok != null) {
        setState(() {
          _msg = ok;
          _msgBad = false;
        });
      }
    } on SiteError catch (e) {
      if (mounted) {
        setState(() {
          _msg = refusalText(e);
          _msgBad = true;
        });
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _diagnose() => _run(() async {
        final d = await widget.api.robotOps(widget.robotId, 'diag');
        if (mounted) setState(() => _diag = d);
      });

  Future<void> _loadLog() => _run(() async {
        final d = await widget.api
            .robotOps(widget.robotId, 'journal', query: <String, String>{'unit': _unit, 'hours': '$_hours'});
        if (mounted) setState(() => _log = d);
      });

  /// 重启服务就地确认（App V2 不弹窗）。
  bool _askRestart = false;

  Future<void> _restart() async {
    setState(() => _askRestart = false);
    final u = _unit;
    await _run(() => widget.api.robotOps(widget.robotId, 'restart', body: <String, dynamic>{'unit': u}),
        ok: tr('$u restarted', '$u 已重启'));
  }

  Future<void> _reboot() async {
    final pw = TextEditingController();
    final ok = await showDialog<bool>(
        context: context,
        builder: (c) => AlertDialog(
              title: Text(tr('Restart ${widget.robotId}?', '重启 ${widget.robotId}？')),
              content: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text(tr('Only allowed while the robot is idle. Enter your password to confirm.',
                    '仅在空闲时可重启。请输入你的密码确认。')),
                TextField(
                    key: RobotOpsPage.rebootPwKey,
                    controller: pw,
                    obscureText: true,
                    decoration: InputDecoration(labelText: tr('Your password', '你的密码'))),
              ]),
              actions: [
                TextButton(onPressed: () => Navigator.pop(c, false), child: Text(tr('Cancel', '取消'))),
                FilledButton(
                    key: RobotOpsPage.rebootGoKey,
                    onPressed: () => Navigator.pop(c, true),
                    child: Text(tr('Restart', '重启'))),
              ],
            ));
    final p = pw.text;
    if (ok != true) return;
    await _run(
        () => widget.api.robotOps(widget.robotId, 'reboot', body: <String, dynamic>{'confirm_password': p}),
        ok: tr('Robot restarting; it will be back online in about two minutes.', '机器人正在重启，约两分钟后重新上线。'));
  }

  @override
  Widget build(BuildContext context) {
    final nw = Nw.of(context);
    final debugOn = ((_diag?['debug_until_ms'] as num?) ?? 0) > DateTime.now().millisecondsSinceEpoch;
    final d = _diag;
    final log = _log;
    final shape = RoundedRectangleBorder(borderRadius: BorderRadius.circular(2));
    ButtonStyle out([Color? fg]) => OutlinedButton.styleFrom(
        minimumSize: const Size(48, 44), shape: shape, foregroundColor: fg, side: fg == null ? null : BorderSide(color: fg));
    // 一排等宽
    Widget row(List<Widget> bs) => Row(children: [
          for (final (i, b) in bs.indexed) ...[if (i > 0) const SizedBox(width: Nw.s8), Expanded(child: b)],
        ]);
    Widget section(String title, List<Widget> kids) => Padding(
        padding: const EdgeInsets.only(top: Nw.s8),
        child: Material(
            color: nw.surface,
            child: Padding(
                padding: const EdgeInsets.all(Nw.s16),
                child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          Text(title, style: NwText.titleMedium.copyWith(color: nw.text, fontWeight: FontWeight.w700)),
          const SizedBox(height: Nw.s8),
          ...kids,
        ]))));
    final sub = NwText.bodySmall.copyWith(color: nw.textSecondary);
    // App V2 稿 S-ops：诊断快照、服务与日志、详细日志、参数、重启 —— 一段一段往下
    return Scaffold(
      appBar: AppBar(
          title: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(tr('Remote maintenance · ${widget.robotId}', '远程运维 · ${widget.robotId}')),
        Text(tr('Available when the robot reports diagnostics', '机器人报了诊断能力才有'), style: sub),
      ])),
      body: ListView(padding: const EdgeInsets.only(bottom: Nw.s24), children: [
        if (_busy) const LinearProgressIndicator(),
        if (_msg != null)
          Padding(
              padding: const EdgeInsets.all(Nw.s16),
              child: NwNotice(tone: _msgBad ? NwTone.error : NwTone.success, text: _msg!)),
        section(tr('Diagnostics snapshot', '诊断快照'), [
          if (d != null)
            for (final (k, v) in diagLines(d))
              Container(
                  padding: const EdgeInsets.symmetric(vertical: 8),
                  decoration: BoxDecoration(border: Border(top: BorderSide(color: nw.outline))),
                  child: Row(children: [
                    Expanded(child: Text(k, style: NwText.bodyMedium.copyWith(color: nw.text))),
                    ConstrainedBox(
                        constraints: const BoxConstraints(maxWidth: 220),
                        child: Text(v,
                            textAlign: TextAlign.end, style: NwText.bodyMedium.copyWith(color: nw.text, fontWeight: FontWeight.w700))),
                  ]))
          else
            Text(tr('Take a snapshot to see uptime, temperature, memory, storage, time and certificate.',
                '拍一张快照看运行时长、温度、内存、存储、时间、证书。'), style: sub),
          const SizedBox(height: Nw.s8),
          row([
            OutlinedButton(
                key: RobotOpsPage.diagKey,
                style: out(),
                onPressed: _busy ? null : _diagnose,
                child: Text(d == null ? tr('Take snapshot', '拍快照') : tr('Refresh', '刷新'))),
            if (_has('ops_timesync'))
              OutlinedButton(
                  key: RobotOpsPage.timesyncKey,
                  style: out(),
                  onPressed: _busy
                      ? null
                      : () => _run(() => widget.api.robotOps(widget.robotId, 'timesync', body: const <String, dynamic>{}),
                          ok: tr('Time synced', '已对时')),
                  child: Text(tr('Sync time', '对时'))),
            if (_has('cert_csr'))
              OutlinedButton(
                  key: RobotOpsPage.certKey,
                  style: out(),
                  onPressed: _busy
                      ? null
                      : () => _run(() => widget.api.robotOps(widget.robotId, 'cert-renew', body: const <String, dynamic>{}),
                          ok: tr('Certificate renewed; the robot reconnects in a few seconds.', '证书已续签，机器人几秒后重新连接。')),
                  child: Text(tr('Renew certificate', '续签证书'))),
          ]),
        ]),
        section(tr('Services & logs', '服务与日志'), [
          Row(children: [
            Expanded(
                child: DropdownButton<String>(
                    key: const Key('ops-unit'),
                    isExpanded: true,
                    value: _unit,
                    items: [for (final u in opsUnits) DropdownMenuItem(value: u, child: Text(u, overflow: TextOverflow.ellipsis))],
                    onChanged: (u) => setState(() {
                          _unit = u ?? _unit;
                          _askRestart = false;
                        }))),
            const SizedBox(width: Nw.s8),
            DropdownButton<int>(
                key: const Key('ops-hours'),
                value: _hours,
                items: [
                  for (final h in const <int>[1, 6, 24, 72])
                    DropdownMenuItem(value: h, child: Text(tr('Last $h h', '最近 $h 小时'))),
                ],
                onChanged: (h) => setState(() => _hours = h ?? _hours)),
          ]),
          const SizedBox(height: Nw.s8),
          row([
            if (_has('ops_journal'))
              OutlinedButton(key: RobotOpsPage.logKey, style: out(), onPressed: _busy ? null : _loadLog, child: Text(tr('View logs', '查看日志'))),
            if (_has('ops_restart'))
              OutlinedButton(
                  key: RobotOpsPage.restartKey,
                  style: out(),
                  onPressed: _busy ? null : () => setState(() => _askRestart = true),
                  child: Text(tr('Restart service', '重启服务'))),
          ]),
          if (_askRestart) ...[
            const SizedBox(height: Nw.s8),
            Text(tr('Restart $_unit? Its work stops for a few seconds.', '重启 $_unit？它的活会停几秒。'), style: NwText.bodySmall.copyWith(color: nw.text)),
            const SizedBox(height: Nw.s8),
            row([
              OutlinedButton(style: out(), onPressed: () => setState(() => _askRestart = false), child: Text(tr('Cancel', '取消'))),
              FilledButton(
                  key: RobotOpsPage.restartGoKey,
                  style: FilledButton.styleFrom(minimumSize: const Size(48, 44), shape: shape),
                  onPressed: _busy ? null : _restart,
                  child: Text(tr('Restart', '重启'))),
            ]),
          ],
          if (log != null) ...[
            const SizedBox(height: Nw.s8),
            Row(children: [
              Expanded(
                  child: Text(
                      log['truncated'] == true
                          ? tr('Only the latest part is shown (newest at the bottom).', '仅显示最近一部分（最新在底部）。')
                          : tr('Newest at the bottom.', '最新在底部。'),
                      style: sub)),
              TextButton.icon(
                  icon: const Icon(Icons.copy_rounded, size: 18),
                  label: Text(tr('Copy', '复制')),
                  onPressed: () => Clipboard.setData(ClipboardData(text: '${log['text'] ?? ''}'))),
            ]),
            Container(
                padding: const EdgeInsets.all(Nw.s8),
                decoration: BoxDecoration(color: nw.bg, border: Border.all(color: nw.outline)),
                child: SelectableText(
                    '${log['text'] ?? ''}'.isEmpty ? tr('No log entries in this time range.', '此时间段没有日志。') : '${log['text']}',
                    key: const Key('ops-log-text'),
                    style: NwText.labelSmall.copyWith(color: nw.text, fontWeight: FontWeight.w400, height: 1.4))),
          ],
        ]),
        if (_has('ops_debug'))
          section(tr('Verbose logging', '详细日志'), [
            SwitchListTile(
                key: RobotOpsPage.debugKey,
                contentPadding: EdgeInsets.zero,
                title: Text(tr('Verbose logging for 1 hour', '详细日志 1 小时'), style: NwText.bodyMedium.copyWith(color: nw.text)),
                subtitle: d == null ? Text(tr('Take a snapshot first to see whether it is on.', '先拍快照才知道开没开。'), style: sub) : null,
                value: debugOn,
                onChanged: _busy
                    ? null
                    : (_) => _run(() async {
                          await widget.api.robotOps(widget.robotId, 'debug', body: <String, dynamic>{'minutes': debugOn ? 0 : 60});
                          final dd = await widget.api.robotOps(widget.robotId, 'diag');
                          if (mounted) setState(() => _diag = dd);
                        }, ok: debugOn ? tr('Detailed logs off', '已关闭详细日志') : tr('Detailed logs on for 1 hour', '已打开详细日志 1 小时'))),
          ]),
        if (_has('ops_settings'))
          section(tr('Parameters', '参数'), [
            if (_sets == null)
              OutlinedButton(
                  key: RobotOpsPage.settingsKey, style: out(), onPressed: _busy ? null : _loadSettings, child: Text(tr('Load parameters', '读参数')))
            else ...[
              for (final e in robotSettingNames.entries)
                if (_choices[e.key] != null)
                  Container(
                      padding: const EdgeInsets.symmetric(vertical: 4),
                      decoration: BoxDecoration(border: Border(top: BorderSide(color: nw.outline))),
                      child: Row(children: [
                        Expanded(child: Text(e.value, style: NwText.bodyMedium.copyWith(color: nw.text))),
                        DropdownButton<String>(
                          key: Key('set-${e.key}'),
                          value: _draft[e.key],
                          items: [
                            for (final v in _choices[e.key]!) DropdownMenuItem(value: v, child: Text(robotSettingValue(e.key, v))),
                          ],
                          onChanged: (v) => setState(() => _draft = {..._draft, e.key: v ?? _draft[e.key]!}),
                        ),
                      ])),
              if (_setConflict)
                NwNotice(tone: NwTone.error, text: tr('A forward cap above 0.5 needs the obstacle clearance permit on first.',
                    '前进上限超过 0.5 要先开障碍净空许可。')),
              const SizedBox(height: Nw.s8),
              Text(tr('Saving restarts the affected services and the agent on the robot (offline for about 1 minute).',
                  '保存后机器人上相关服务和代理会重启（约 1 分钟离线）。'), style: sub),
              const SizedBox(height: Nw.s8),
              FilledButton(
                  key: RobotOpsPage.settingsSaveKey,
                  style: FilledButton.styleFrom(minimumSize: const Size(48, 48), shape: shape),
                  onPressed: _busy || _changed.isEmpty || _setConflict ? null : _saveSettings,
                  child: Text(tr('Save parameters', '保存参数'))),
            ],
          ]),
        if (_has('ops_reboot'))
          section(tr('Restart robot', '重启整机'), [
            Text(tr('Restart is available only when idle and requires your password.', '只能在空闲时重启，要输你的密码。'), style: sub),
            const SizedBox(height: Nw.s8),
            OutlinedButton(
                key: RobotOpsPage.rebootKey,
                style: out(nw.error),
                onPressed: _busy ? null : _reboot,
                child: Text(tr('Restart robot…', '重启机器人…'))),
          ]),
      ]),
    );
  }
}
