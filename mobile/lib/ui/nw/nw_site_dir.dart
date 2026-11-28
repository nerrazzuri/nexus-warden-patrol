/// 「现场」层（App V2，design/app-v2 S-admin / S-guard / S-mgr / S-viewer）：浅色目录。
///
/// 按角色给四套：管理员（日常 / 现场 / 记录 / 高级 / 本机）、经理（日常 / 现场 / 记录 / 本机）、
/// 保安（记录 / 本机）、只读（记录 / 本机）。角色没有的项直接不列，不放灰的。底部是账号、改密码、退出站点。
/// 每一项先接到老页面（第 1 期）；后面几期按稿重排各页时这里只改目的地。
library;

import '../../net/person_names.dart';
import 'package:flutter/material.dart';

import '../../l10n.dart';
import '../../net/site_client.dart';
import '../../store/site_store.dart';
import '../alarm_log.dart';
import '../face_enrol.dart';
import '../app_settings.dart' show openSettings;
import '../guide.dart';
import '../map_manage.dart';
import '../problem_report.dart';
import '../site_health.dart' show SiteHealthPage, shareBundle;
import '../site_incidents.dart';
import '../site_mode.dart';
import '../site_recordings.dart';
import '../site_releases.dart';
import '../site_ob.dart';
import '../site_runs.dart';
import '../site_tabs.dart' show AccountsPage, leaveConfirmKey;
import 'nw_layout_hub.dart';
import 'nw_theme.dart';

/// 目录里一行要去哪。
enum SiteDest { overview, robots, users, layout, arming, alarms, events, recordings, runs, notes, ob, maps, health, updates, settings, help, report }

class SiteDirectory extends StatelessWidget {
  final SiteApi api;
  final SiteEntry? entry;

  /// 机器人列表是外壳里一直活着的那一页（响铃、事件流在它身上）：目录只告诉外壳切过去。
  final VoidCallback onRobots;

  /// 概况（管理员的「要你处理 + 开站清单」）也在外壳里。
  final VoidCallback onOverview;

  /// 全屏地图(老的「地图」栏 [SiteMapTab]:狗正在用的图、图例、缩放、点一下派去看一眼)也在外壳里。
  final VoidCallback onLayout;
  const SiteDirectory(
      {super.key, required this.api, this.entry, required this.onRobots, required this.onOverview, required this.onLayout});

  static Key itemKey(SiteDest d) => Key('site-${d.name}');
  static const Key leaveKey = Key('site-leave');
  static const Key passwordKey = Key('site-password');
  static const Key facesKey = Key('site-faces');

  void _push(BuildContext context, Widget page) =>
      Navigator.of(context).push(MaterialPageRoute<void>(builder: (_) => page));

  /// 老的「栏」(自己没有顶栏的那几页)推出去时套一个顶栏,好有返回。
  void _pushBar(BuildContext context, String title, Widget body) =>
      _push(context, Scaffold(appBar: AppBar(title: Text(title)), body: body));

  @override
  Widget build(BuildContext context) {
    final s = api.session;
    final role = s?.role ?? '';
    final manage = s?.canManageMaps ?? false;              // 管理员、工程师
    final owner = role == 'owner';
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
            // App V2 稿 S-layout：先到「地图与布置」入口页（小地图 + 一层一行）
            () => _push(context, SiteLayoutPage(api: api, onRobots: onRobots, onMap: onLayout))),
        _Row(SiteDest.arming, Icons.shield_outlined, tr('Arming & patrols', '布防与巡逻'),
            tr('Arming mode, temporary disarm, arming schedule, patrol schedules, weather', '布防模式、临时撤防、布防时间、巡逻日程、天气'),
            () => _push(context, SiteModePage(api: api))),
      ]));
    } else if (owner) {
      groups.add((tr('Daily', '日常'), [
        _Row(SiteDest.overview, Icons.home_outlined, tr('Overview', '概况'), tr('Read-only · alarms and outcomes, last 24 h', '只读 · 24 小时报警和处理结果'), onOverview),
        _Row(SiteDest.robots, Icons.smart_toy_outlined, tr('Robots', '机器人'), tr('Status; dispatch patrols', '看状态、派巡逻'), onRobots),
      ]));
      // 稿 S-mgr:经理的「现场」只有布防与巡逻;看图从「现在」的小地图进全屏
      groups.add((tr('Site', '现场'), [
        _Row(SiteDest.arming, Icons.shield_outlined, tr('Arming & patrols', '布防与巡逻'),
            tr('Arming mode, temporary disarm, arming schedule, patrol schedules', '布防模式、临时撤防、布防时间、巡逻日程'),
            () => _push(context, SiteModePage(api: api))),
      ]));
    }
    if (role == 'guard') {
      // 外审 App-V2-2 N2：保安能布防、留守、临时撤防（canArm / canSetMode），要有入口
      groups.add((tr('Site', '现场'), [
        _Row(SiteDest.arming, Icons.shield_outlined, tr('Arming', '布防'),
            tr('Arming mode, temporary disarm', '布防模式、临时撤防'), () => _push(context, SiteModePage(api: api))),
      ]));
    }
    final readOnly = role == 'viewer';
    // 稿 S-guard / S-viewer:保安、只读没有「日常」—— 机器人和地图都在「现在」页上(格子「控制」、小地图进全屏)
    groups.add((tr('Records', '记录'), [
      _Row(SiteDest.alarms, Icons.notifications_none_rounded, tr('Alarm log', '报警记录'),
          readOnly ? tr('View only', '只看') : tr('This shift and before', '本班和之前'), () => _pushBar(context, tr('Alarm log', '报警记录'), AlarmLogPage(api: api))),
      if (!readOnly)
        _Row(SiteDest.events, Icons.history_rounded, tr('Events', '事件账'),
            tr('Robot events, cameras, intercept points', '机器人事件、摄像头、拦截点'),
            () => _pushBar(context, tr('Events', '事件账'), SiteIncidentsPage(api: api, embedded: true))),
      _Row(SiteDest.recordings, Icons.videocam_outlined, tr('Recordings', '录像'),
          readOnly ? tr('View only', '只看') : tr('One-minute segments per robot, kept 30 days', '每台机器人一分钟一段，留 30 天'),
          () => _push(context, _RecordingsPick(api: api))),
      _Row(SiteDest.runs, Icons.route_outlined, tr('Patrol log', '巡逻记录'),
          readOnly ? tr('View only', '只看') : tr('Photos and assessment for each run', '每一趟的照片和判读'),
          () => _push(context, SiteRunsPage(api: api))),
      if (!readOnly)
        _Row(SiteDest.notes, Icons.sticky_note_2_outlined, tr('Handover notes', '交班留言'), tr('Latest note and history', '最近一条和历史'),
            () => _push(context, ShiftNotesPage(api: api))),
      // 1.1-5 电子值班簿：只读账号也能看
      _Row(SiteDest.ob, Icons.menu_book_outlined, tr('Occurrence book', '值班簿'),
          readOnly ? tr('View only', '只看') : tr('Write entries; alarms and patrols added by the site', '自己写的，加上站点记的报警、巡检'),
          () => _push(context, OccurrenceBookPage(api: api))),
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
          () => _push(context, HelpPage(role: role, api: api))),
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
      _AccountBlock(api: api, entry: entry),
    ]);
  }
}

/// 目录最下面：我是谁、改密码、退出站点（就地确认，不弹窗）。
class _AccountBlock extends StatefulWidget {
  final SiteApi api;
  final SiteEntry? entry;
  const _AccountBlock({required this.api, this.entry});
  @override
  State<_AccountBlock> createState() => _AccountBlockState();
}

class _AccountBlockState extends State<_AccountBlock> {
  bool _leaving = false;

  @override
  Widget build(BuildContext context) {
    final c = Nw.of(context);
    final s = widget.api.session;
    final site = widget.entry?.name ?? '';
    final shape = RoundedRectangleBorder(borderRadius: BorderRadius.circular(2));
    Widget row(Key key, String title, String? sub, VoidCallback on) => ListTile(
        key: key,
        title: Text(title, style: NwText.titleSmall.copyWith(color: c.text, fontWeight: FontWeight.w600)),
        subtitle: sub == null ? null : Text(sub, style: NwText.bodySmall.copyWith(color: c.textSecondary)),
        trailing: Icon(Icons.chevron_right_rounded, color: c.textSecondary),
        onTap: on);
    return Material(
        color: c.surface,
        child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          Divider(height: 1, thickness: 1, color: c.outline),
          ListTile(
              leading: Icon(Icons.person_outline, color: c.textSecondary),
              title: Text(personName(s?.name), style: NwText.titleSmall.copyWith(color: c.text, fontWeight: FontWeight.w700)),
              subtitle: Text(site.isEmpty ? roleName(s?.role ?? '') : '${roleName(s?.role ?? '')} · $site',
                  style: NwText.bodySmall.copyWith(color: c.textSecondary))),
          Divider(height: 1, thickness: 1, color: c.outline),
          row(SiteDirectory.passwordKey, tr('Change password', '改密码'), null,
              () => Navigator.of(context).push(MaterialPageRoute<void>(builder: (_) => ChangePasswordPage(api: widget.api)))),
          Divider(height: 1, thickness: 1, color: c.outline),
          // 1.1-1：登记自己的脸，机器人巡逻时认得出是工作人员
          row(SiteDirectory.facesKey, tr('Face enrolment', '人脸登记'),
              tr('So the robot recognises you as staff', '让机器人认得你是工作人员'),
              () => Navigator.of(context).push(MaterialPageRoute<void>(builder: (_) => FaceEnrolPage(api: widget.api)))),
          Divider(height: 1, thickness: 1, color: c.outline),
          row(SiteDirectory.leaveKey, tr('Leave site', '退出站点'),
              tr("Return to the site list; this phone stops receiving this site's alerts", '回到站点列表；这台手机不再收这个站点的报警'),
              () => setState(() => _leaving = !_leaving)),
          if (_leaving)
            Padding(
                padding: const EdgeInsets.fromLTRB(Nw.s16, 0, Nw.s16, Nw.s16),
                child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                  Text(
                      tr('You will be signed out. Background monitoring stops, so this phone will no longer get alarms from this site.',
                          '退出后会注销登录，后台值守也会停止，这台手机将收不到这个站点的报警。'),
                      style: NwText.bodySmall.copyWith(color: c.text)),
                  const SizedBox(height: Nw.s8),
                  Row(children: [
                    Expanded(
                        child: OutlinedButton(
                            style: OutlinedButton.styleFrom(minimumSize: const Size(48, 48), shape: shape),
                            onPressed: () => setState(() => _leaving = false),
                            child: Text(tr('Cancel', '取消')))),
                    const SizedBox(width: Nw.s8),
                    Expanded(
                        child: FilledButton(
                            key: leaveConfirmKey,
                            style: FilledButton.styleFrom(minimumSize: const Size(48, 48), shape: shape),
                            onPressed: () => Navigator.of(context, rootNavigator: true).pop(),
                            child: Text(tr('Leave', '退出')))),
                  ]),
                ])),
          Divider(height: 1, thickness: 1, color: c.outline),
        ]));
  }
}

/// 改自己的密码（稿 S-mgr「改密码」）：旧密码、新密码两遍；改好了站点吊销所有会话，要重新登录。
class ChangePasswordPage extends StatefulWidget {
  final SiteApi api;
  const ChangePasswordPage({super.key, required this.api});

  static const Key oldKey = Key('pw-old');
  static const Key newKey = Key('pw-new');
  static const Key againKey = Key('pw-again');
  static const Key goKey = Key('pw-go');
  static const Key msgKey = Key('pw-msg');
  static const Key reloginKey = Key('pw-relogin');

  @override
  State<ChangePasswordPage> createState() => _ChangePasswordPageState();
}

class _ChangePasswordPageState extends State<ChangePasswordPage> {
  final _old = TextEditingController(), _new = TextEditingController(), _again = TextEditingController();
  String _msg = '';
  bool _busy = false, _done = false;

  @override
  void dispose() {
    _old.dispose();
    _new.dispose();
    _again.dispose();
    super.dispose();
  }

  Future<void> _go() async {
    if (_new.text != _again.text) {
      setState(() => _msg = tr("The two new passwords don't match.", '两次新密码不一样。'));
      return;
    }
    if (_new.text.isEmpty || _old.text.isEmpty) {
      setState(() => _msg = tr('Fill in all three fields.', '三栏都要填。'));
      return;
    }
    setState(() {
      _busy = true;
      _msg = '';
    });
    try {
      await widget.api.changeOwnPassword(_old.text, _new.text);
      if (mounted) {
        setState(() {
          _done = true;
          _msg = tr('Password changed. All sessions are signed out; sign in again with the new password.',
              '密码改好了。所有登录都已注销，请用新密码重新登录。');
        });
      }
    } on SiteError catch (e) {
      if (mounted) setState(() => _msg = tr('Not changed: ${refusalText(e)}', '没改成：${refusalText(e)}'));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final c = Nw.of(context);
    final shape = RoundedRectangleBorder(borderRadius: BorderRadius.circular(2));
    InputDecoration dec(String l) => InputDecoration(labelText: l);
    return Scaffold(
        appBar: AppBar(title: Text(tr('Change password', '改密码'))),
        body: ListView(padding: const EdgeInsets.all(Nw.s16), children: [
          if (!_done) ...[
            TextField(key: ChangePasswordPage.oldKey, controller: _old, obscureText: true, decoration: dec(tr('Current password', '现在的密码'))),
            const SizedBox(height: Nw.s8),
            TextField(key: ChangePasswordPage.newKey, controller: _new, obscureText: true, decoration: dec(tr('New password', '新密码'))),
            const SizedBox(height: Nw.s8),
            TextField(
                key: ChangePasswordPage.againKey, controller: _again, obscureText: true, decoration: dec(tr('New password again', '再输一遍新密码'))),
            const SizedBox(height: Nw.s16),
            FilledButton(
                key: ChangePasswordPage.goKey,
                style: FilledButton.styleFrom(minimumSize: const Size(48, 48), shape: shape),
                onPressed: _busy ? null : _go,
                child: Text(tr('Change password', '改密码'))),
          ],
          if (_msg.isNotEmpty) ...[
            const SizedBox(height: Nw.s16),
            Text(_msg, key: ChangePasswordPage.msgKey, style: NwText.bodyMedium.copyWith(color: _done ? c.text : c.error)),
          ],
          if (_done) ...[
            const SizedBox(height: Nw.s16),
            FilledButton(
                key: ChangePasswordPage.reloginKey,
                style: FilledButton.styleFrom(minimumSize: const Size(48, 48), shape: shape),
                // 回到站点列表（站点已经把这台手机的登录吊销了）
                onPressed: () => Navigator.of(context, rootNavigator: true).popUntil((r) => r.isFirst),
                child: Text(tr('Back to sign in', '回去重新登录'))),
          ],
        ]));
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
    // 稿 S-video：一页，顶上切机器人（解绑了的也列着：录像还在）
    final ids = [for (final r in _robots ?? const <Map<String, dynamic>>[]) '${r['robot_id']}'];
    if (ids.isNotEmpty) return SiteRecordingsPage(api: widget.api, robotId: ids.first, robots: ids);
    return Scaffold(
        appBar: AppBar(title: Text(tr('Recordings', '录像'))),
        body: _err != null
            ? Center(child: Text(_err!, style: NwText.bodyMedium.copyWith(color: c.error)))
            : _robots == null
                ? const Center(child: CircularProgressIndicator())
                : Padding(
                    padding: const EdgeInsets.all(Nw.s16),
                    child: Text(tr('No robots on this site yet, so there are no recordings.', '站点上还没有机器人，所以没有录像。'),
                        style: NwText.bodyMedium.copyWith(color: c.textSecondary))));
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
        appBar: AppBar(
            title: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(tr('Handover notes', '交班留言')),
          if (_notes != null && _notes!.isNotEmpty)
            Text(tr('Latest ${_notes!.length}', '最近 ${_notes!.length} 条'), style: NwText.bodySmall.copyWith(color: c.textSecondary)),
        ])),
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
                      decoration: InputDecoration(hintText: tr('Note for the next shift…', '给下一班留一句…'))),
                  const SizedBox(height: Nw.s8),
                  FilledButton(
                      key: const Key('note-send'),
                      style: FilledButton.styleFrom(
                          minimumSize: const Size(48, 48), shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(2))),
                      onPressed: _busy ? null : _send,
                      child: Text(tr('Post', '发出'))),
                ])),
          if (_err != null) Padding(padding: const EdgeInsets.all(Nw.s16), child: Text(_err!, style: NwText.bodyMedium.copyWith(color: c.error))),
          Expanded(
              child: _notes == null
                  ? const Center(child: CircularProgressIndicator())
                  : _notes!.isEmpty
                      ? Center(child: Text(tr('No notes yet.', '还没有留言。'), style: NwText.bodyMedium.copyWith(color: c.textSecondary)))
                      : ListView.separated(
                          itemCount: _notes!.length,
                          separatorBuilder: (_, _) => Divider(height: 1, thickness: 1, color: c.outline),
                          itemBuilder: (_, i) {
                            final n = _notes![i];
                            final at = DateTime.fromMillisecondsSinceEpoch((n['at_ms'] as num?)?.toInt() ?? 0);
                            final hm = '${at.hour.toString().padLeft(2, '0')}:${at.minute.toString().padLeft(2, '0')}';
                            final now = DateTime.now();
                            final days = DateTime(now.year, now.month, now.day).difference(DateTime(at.year, at.month, at.day)).inDays;
                            final when = switch (days) {
                              0 => tr('Today $hm', '今天 $hm'),
                              1 => tr('Yesterday $hm', '昨天 $hm'),
                              _ => '${at.month.toString().padLeft(2, '0')}-${at.day.toString().padLeft(2, '0')} $hm',
                            };
                            // App V2 稿 S-notes：上面「谁 …… 什么时候」，下面留言
                            return Padding(
                                key: Key('note-${n['id']}'),
                                padding: const EdgeInsets.symmetric(horizontal: Nw.s16, vertical: 12),
                                child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                                  Row(children: [
                                    Expanded(
                                        child: Text(personName(n['author']),
                                            style: NwText.labelLarge.copyWith(color: c.text, fontWeight: FontWeight.w700))),
                                    Text(when, style: NwText.bodySmall.copyWith(color: c.textSecondary)),
                                  ]),
                                  const SizedBox(height: Nw.s4),
                                  Text('${n['text'] ?? ''}', style: NwText.bodyMedium.copyWith(color: c.text)),
                                ]));
                          })),
        ]));
  }
}
