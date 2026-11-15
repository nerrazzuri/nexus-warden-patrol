/// 「现场」层（App V2，design/app-v2 S-admin / S-guard / S-mgr / S-viewer）：浅色目录。
///
/// 按角色给四套：管理员（日常 / 现场 / 记录 / 高级 / 本机）、经理（日常 / 现场 / 记录 / 本机）、
/// 保安（记录 / 本机）、只读（记录 / 本机）。角色没有的项直接不列，不放灰的。底部是账号、改密码、退出站点。
/// 每一项先接到老页面（第 1 期）；后面几期按稿重排各页时这里只改目的地。
library;

import 'package:flutter/material.dart';

import '../../l10n.dart';
import '../../net/site_client.dart';
import '../../store/site_store.dart';
import '../alarm_log.dart';
import '../app_settings.dart' show openSettings;
import '../guide.dart';
import '../map_manage.dart';
import '../problem_report.dart';
import '../site_health.dart' show SiteHealthPage, shareBundle;
import '../site_maps.dart';
import '../site_mode.dart';
import '../site_releases.dart';
import '../site_runs.dart';
import '../site_tabs.dart' show AccountsPage, leaveSite;
import 'nw_theme.dart';

/// 目录里一行要去哪。
enum SiteDest { overview, robots, users, layout, arming, alarms, recordings, runs, notes, maps, health, updates, settings, help, report }

class SiteDirectory extends StatelessWidget {
  final SiteApi api;
  final SiteEntry? entry;

  /// 机器人列表是外壳里一直活着的那一页（响铃、事件流在它身上）：目录只告诉外壳切过去。
  final VoidCallback onRobots;

  /// 概况（管理员的「要你处理 + 开站清单」）也在外壳里。
  final VoidCallback onOverview;
  const SiteDirectory({super.key, required this.api, this.entry, required this.onRobots, required this.onOverview});

  static Key itemKey(SiteDest d) => Key('site-${d.name}');
  static const Key leaveKey = Key('site-leave');

  void _push(BuildContext context, Widget page) =>
      Navigator.of(context).push(MaterialPageRoute<void>(builder: (_) => page));

  @override
  Widget build(BuildContext context) {
    final s = api.session;
    final role = s?.role ?? '';
    final manage = s?.canManageMaps ?? false;              // 管理员、工程师
    final owner = role == 'owner';
    final c = Nw.of(context);
    final groups = <(String, List<_Row>)>[];
    if (manage) {
      groups.add((tr('Daily', '日常'), [
        _Row(SiteDest.overview, Icons.home_outlined, tr('Overview', '概况'), tr('Pending items · site setup', '待处理 · 开站清单'), onOverview),
        _Row(SiteDest.robots, Icons.smart_toy_outlined, tr('Robots', '机器人'), tr('Status, control, join requests', '状态、控制、加入申请'), onRobots),
        _Row(SiteDest.users, Icons.person_outline, tr('Users', '人员'), tr('Accounts, roles, approvals', '账号、角色、审批'),
            () => _push(context, AccountsPage(api: api))),
      ]));
      groups.add((tr('Site', '现场'), [
        _Row(SiteDest.layout, Icons.map_outlined, tr('Map & layout', '地图与布置'),
            tr('Zones, no-go zones, patrol routes, standby points, cameras, intercept points', '防区、禁行区、巡逻路线、待命点、摄像头、拦截点'),
            () => _push(context, SiteMapsPage(api: api))),
        _Row(SiteDest.arming, Icons.shield_outlined, tr('Arming & patrols', '布防与巡逻'),
            tr('Arming mode, temporary disarm, arming schedule, patrol schedules, weather', '布防模式、临时撤防、布防时间、巡逻日程、天气'),
            () => _push(context, SiteModePage(api: api))),
      ]));
    } else if (owner) {
      groups.add((tr('Daily', '日常'), [
        _Row(SiteDest.overview, Icons.home_outlined, tr('Overview', '概况'), tr('Read-only · alarms and outcomes, last 24 h', '只读 · 24 小时报警和处理结果'), onOverview),
        _Row(SiteDest.robots, Icons.smart_toy_outlined, tr('Robots', '机器人'), tr('Status; dispatch patrols', '看状态、派巡逻'), onRobots),
      ]));
      groups.add((tr('Site', '现场'), [
        _Row(SiteDest.arming, Icons.shield_outlined, tr('Arming & patrols', '布防与巡逻'),
            tr('Arming mode, temporary disarm, arming schedule, patrol schedules', '布防模式、临时撤防、布防时间、巡逻日程'),
            () => _push(context, SiteModePage(api: api))),
      ]));
    }
    final readOnly = role == 'viewer';
    groups.add((tr('Records', '记录'), [
      _Row(SiteDest.alarms, Icons.notifications_none_rounded, tr('Alarm log', '报警记录'),
          readOnly ? tr('View only', '只看') : tr('This shift and before', '本班和之前'), () => _push(context, AlarmLogPage(api: api))),
      _Row(SiteDest.recordings, Icons.videocam_outlined, tr('Recordings', '录像'),
          readOnly ? tr('View only', '只看') : tr('One-minute segments per robot, kept 30 days', '每台机器人一分钟一段，留 30 天'),
          () => _push(context, _RecordingsPick(api: api))),
      _Row(SiteDest.runs, Icons.route_outlined, tr('Patrol log', '巡逻记录'),
          readOnly ? tr('View only', '只看') : tr('Photos and assessment for each run', '每一趟的照片和判读'),
          () => _push(context, SiteRunsPage(api: api))),
      if (!readOnly)
        _Row(SiteDest.notes, Icons.sticky_note_2_outlined, tr('Handover notes', '交班留言'), tr('Latest note and history', '最近一条和历史'),
            () => _push(context, ShiftNotesPage(api: api))),
    ]));
    if (manage) {
      groups.add((tr('Advanced', '高级'), [
        _Row(SiteDest.maps, Icons.layers_outlined, tr('Map management & mapping', '地图管理与建图'),
            tr('Map versions, deploy, roll back, new', '每张图的版本、下发、退回、新建'), () => _push(context, MapManagePage(api: api))),
        _Row(SiteDest.health, Icons.monitor_heart_outlined, tr('Site health', '站点体检'),
            tr('Checks, versions, diagnostics bundle', '各项检查、版本、诊断包'), () => _push(context, SiteHealthPage(api: api))),
        _Row(SiteDest.updates, Icons.system_update_alt_outlined, tr('Software updates', '软件升级'),
            tr('Site, robot and app versions', '站点、机器人、App 的版本'), () => _push(context, SiteReleasesPage(api: api))),
      ]));
    }
    groups.add((tr('This device', '本机'), [
      _Row(SiteDest.settings, Icons.settings_outlined, tr('Settings', '设置'),
          tr('Language, appearance, alarm sound, background monitoring, waypoint alerts, about & updates',
              '语言、外观、报警声音、后台值守、到点提醒、关于与更新'),
          () => openSettings(context, api)),
      _Row(SiteDest.help, Icons.help_outline_rounded, tr('Guides & FAQ', '使用教程与常见问题'),
          tr('Monitoring tour, handling alarms, alarm drill', '值班页导览、怎么处理报警、报警演练'),
          () => _push(context, HelpPage(role: role))),
      _Row(SiteDest.report, Icons.description_outlined, tr('Report a problem', '报问题'),
          tr('Describe the issue; logs are sent to the engineer', '写一句出了什么事，日志发给工程师'),
          () => _push(context, ProblemReportPage(api: api, share: shareBundle))),
    ]));

    return ListView(padding: const EdgeInsets.only(bottom: Nw.s24), children: [
      for (final (title, rows) in groups) ...[
        _GroupTitle(title),
        for (var i = 0; i < rows.length; i++) rows[i],
      ],
      const SizedBox(height: Nw.s8),
      Container(
          decoration: BoxDecoration(border: Border(top: BorderSide(color: c.outline))),
          child: Column(children: [
            ListTile(
                leading: Icon(Icons.person_outline, color: c.textSecondary),
                title: Text(s?.name ?? '', style: NwText.titleSmall.copyWith(color: c.text, fontWeight: FontWeight.w700)),
                subtitle: Text('${roleName(role)} · ${entry?.name ?? ''}',
                    style: NwText.bodySmall.copyWith(color: c.textSecondary))),
            Divider(height: 1, thickness: 1, color: c.outline),
            ListTile(
                key: leaveKey,
                title: Text(tr('Leave site', '退出站点'), style: NwText.titleSmall.copyWith(color: c.text, fontWeight: FontWeight.w600)),
                subtitle: Text(tr("Return to the site list; this phone stops receiving this site's alerts", '回到站点列表；这台手机不再收这个站点的报警'),
                    style: NwText.bodySmall.copyWith(color: c.textSecondary)),
                onTap: () => leaveSite(context)),
          ])),
    ]);
  }
}

class _GroupTitle extends StatelessWidget {
  final String text;
  const _GroupTitle(this.text);
  @override
  Widget build(BuildContext context) {
    final c = Nw.of(context);
    return Container(
        padding: const EdgeInsets.fromLTRB(Nw.s16, 14, Nw.s16, 6),
        color: c.bg,
        child: Text(text.toUpperCase(), style: NwText.labelSmall.copyWith(color: c.textMuted, letterSpacing: 0.6, fontWeight: FontWeight.w600)));
  }
}

/// 目录的一行：图标、标题、一句说明、右箭头;56 高、底下一条线。
class _Row extends StatelessWidget {
  final SiteDest dest;
  final IconData icon;
  final String title;
  final String sub;
  final VoidCallback onTap;
  const _Row(this.dest, this.icon, this.title, this.sub, this.onTap);
  @override
  Widget build(BuildContext context) {
    final c = Nw.of(context);
    return Material(
        color: c.surface,
        child: InkWell(
            key: SiteDirectory.itemKey(dest),
            onTap: onTap,
            child: Container(
                constraints: const BoxConstraints(minHeight: 56),
                padding: const EdgeInsets.symmetric(horizontal: Nw.s16, vertical: Nw.s8),
                decoration: BoxDecoration(border: Border(bottom: BorderSide(color: c.outline))),
                child: Row(children: [
                  Icon(icon, size: 22, color: c.textSecondary),
                  const SizedBox(width: 12),
                  Expanded(
                      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Text(title, style: NwText.titleSmall.copyWith(color: c.text, fontWeight: FontWeight.w600)),
                    const SizedBox(height: 2),
                    Text(sub, style: NwText.bodySmall.copyWith(color: c.textSecondary)),
                  ])),
                  Icon(Icons.chevron_right_rounded, color: c.textMuted),
                ]))));
  }
}

/// 录像页要先选一台(老页面按机器人进):列出机器人让人点。
class _RecordingsPick extends StatefulWidget {
  final SiteApi api;
  const _RecordingsPick({required this.api});
  @override
  State<_RecordingsPick> createState() => _RecordingsPickState();
}

class _RecordingsPickState extends State<_RecordingsPick> {
  List<Map<String, dynamic>>? _robots;
  String? _err;
  @override
  void initState() {
    super.initState();
    widget.api.robots().then((r) => mounted ? setState(() => _robots = r) : null,
        onError: (Object e) => mounted ? setState(() => _err = '$e') : null);
  }

  @override
  Widget build(BuildContext context) {
    final c = Nw.of(context);
    return Scaffold(
        appBar: AppBar(title: Text(tr('Recordings', '录像'))),
        body: _err != null
            ? Center(child: Text(_err!, style: NwText.bodyMedium.copyWith(color: c.error)))
            : _robots == null
                ? const Center(child: CircularProgressIndicator())
                : ListView(children: [
                    for (final r in _robots!)
                      ListTile(
                          key: Key('rec-robot-${r['robot_id']}'),
                          title: Text('${r['name'] ?? r['robot_id']}', style: NwText.titleSmall.copyWith(color: c.text)),
                          subtitle: Text('${r['robot_id']}', style: NwText.bodySmall.copyWith(color: c.textSecondary)),
                          trailing: Icon(Icons.chevron_right_rounded, color: c.textMuted),
                          onTap: () => Navigator.of(context).push(MaterialPageRoute<void>(
                              builder: (_) => SiteRecordingsPage(api: widget.api, robotId: '${r['robot_id']}')))),
                  ]));
  }
}

/// 交班留言(第 1 期先给最小的一页:最近 50 条 + 写一条;接口跟网页同一个 /api/shift-notes)。
class ShiftNotesPage extends StatefulWidget {
  final SiteApi api;
  const ShiftNotesPage({super.key, required this.api});
  @override
  State<ShiftNotesPage> createState() => _ShiftNotesPageState();
}

class _ShiftNotesPageState extends State<ShiftNotesPage> {
  List<Map<String, dynamic>>? _notes;
  String? _err;
  final _text = TextEditingController();
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final d = await widget.api.shiftNotes(recent: 50);
      if (mounted) setState(() => _notes = d);
    } on SiteError catch (e) {
      if (mounted) setState(() => _err = '$e');
    }
  }

  Future<void> _send() async {
    final t = _text.text.trim();
    if (t.isEmpty) return;
    setState(() => _busy = true);
    try {
      await widget.api.postShiftNote(t);
      _text.clear();
      await _load();
    } on SiteError catch (e) {
      if (mounted) setState(() => _err = '$e');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  void dispose() {
    _text.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final c = Nw.of(context);
    final can = widget.api.session?.canHandleAlerts ?? false;
    return Scaffold(
        appBar: AppBar(title: Text(tr('Handover notes', '交班留言'))),
        body: Column(children: [
          if (can)
            Padding(
                padding: const EdgeInsets.all(Nw.s16),
                child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                  TextField(
                      key: const Key('note-text'),
                      controller: _text,
                      maxLines: 3,
                      maxLength: 300,
                      decoration: InputDecoration(hintText: tr('Leave a note for the next shift', '给下一班留一句'))),
                  const SizedBox(height: Nw.s8),
                  FilledButton(key: const Key('note-send'), onPressed: _busy ? null : _send, child: Text(tr('Leave note', '留言'))),
                ])),
          if (_err != null) Padding(padding: const EdgeInsets.all(Nw.s16), child: Text(_err!, style: NwText.bodyMedium.copyWith(color: c.error))),
          Expanded(
              child: _notes == null
                  ? const Center(child: CircularProgressIndicator())
                  : _notes!.isEmpty
                      ? Center(child: Text(tr('No notes yet.', '还没有留言。'), style: NwText.bodyMedium.copyWith(color: c.textSecondary)))
                      : ListView.separated(
                          itemCount: _notes!.length,
                          separatorBuilder: (_, __) => Divider(height: 1, thickness: 1, color: c.outline),
                          itemBuilder: (_, i) {
                            final n = _notes![i];
                            final at = DateTime.fromMillisecondsSinceEpoch((n['at_ms'] as num?)?.toInt() ?? 0);
                            final hm = '${at.hour.toString().padLeft(2, '0')}:${at.minute.toString().padLeft(2, '0')}';
                            return ListTile(
                                title: Text('${n['text'] ?? ''}', style: NwText.bodyMedium.copyWith(color: c.text)),
                                subtitle: Text('${n['author'] ?? ''} · ${at.month}-${at.day} $hm',
                                    style: NwText.bodySmall.copyWith(color: c.textSecondary)));
                          })),
        ]));
  }
}
