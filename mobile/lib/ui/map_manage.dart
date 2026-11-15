/// 地图管理（W54，管理员、工程师）：每张图的版本（显示名、什么时候建的、建图结论、哪台在用），下发给哪台、
/// 删旧版本、把某台退回上一版，新建（开建图向导）。数据是站点的地图管理总览（`/api/admin/maps`）。
/// 录包、拿录包重建这些工程师的活还在原来的地图目录页（最下面一行进）。
library;

import 'dart:async';

import 'package:flutter/material.dart';

import '../l10n.dart';
import '../net/site_client.dart';
import '../net/site_text.dart' show siteKnown;
import 'map_wizard.dart';
import 'nw/nw_button.dart';
import 'nw/nw_theme.dart';
import 'nw/nw_widgets.dart';
import 'site_mapping.dart' show SiteMapPreviewPage;
import 'site_maps.dart' show SiteMapsPage;

/// 第 8 轮 A8-04：版本先写「第 N 版」（纯数字的）；别的写法（日期编号）写「版本 X」。
String versionLabel(String v) =>
    RegExp(r'^\d+$').hasMatch(v) ? tr('Version $v', '第 $v 版') : tr('Version $v', '版本 $v');

/// 站点记的版本说明（「从 10 编辑:擦了…」）按界面写：「从第 10 版编辑：擦了…」。
String versionNoteText(String note) {
  // 站点原话「从 X 编辑:…」（写成 \u 转义：这里是认站点的字，不是给人看的）
  final m = RegExp('^\u4ece (\\S+) \u7f16\u8f91:(.*)\$').firstMatch(note);
  if (m == null) return siteKnown(note);          // 第 9 轮 A8-04 尾巴：「从 7 清了…」也写第几版、按语言
  return tr('Edited from ${versionLabel(m[1]!).toLowerCase()}: ${m[2]}', '从${versionLabel(m[1]!)}编辑：${m[2]}');
}

/// 第 11 轮 A11-01：站点记的地图来源（edit:demo、cli:liang、import、draft:demo、建图的机器人编号）写人话。
String mapSourceText(String source) {
  final m = RegExp(r'^(edit|cli|draft|denoise):(.+)$').firstMatch(source);
  if (m != null) {
    final who = m[2]!;
    return switch (m[1]) {
      'edit' => tr('Edited by $who', '$who 编辑'),
      'cli' => tr('Imported by $who', '$who 导入'),
      'denoise' => tr('Denoised by $who', '$who 去噪'),
      _ => tr('Edited by $who (draft)', '$who 编辑（草稿）'),
    };
  }
  if (source.isEmpty) return '';
  if (source == 'import') return tr('Imported', '导入');
  return tr('Mapped by $source', '$source 建图');
}

class MapManagePage extends StatefulWidget {
  final SiteApi api;
  const MapManagePage({super.key, required this.api});

  static const Key newKey = Key('maps-new');
  static Key versionKey(String m, String v) => Key('mapver-$m-$v');
  static Key viewKey(String m, String v) => Key('mapver-view-$m-$v');
  static Key sendKey(String m, String v) => Key('mapver-send-$m-$v');
  static Key draftKey(String m, String v) => Key('mapver-draft-$m-$v');
  static Key deleteKey(String m, String v) => Key('mapver-delete-$m-$v');
  static Key rollbackKey(String r) => Key('map-rollback-$r');
  static const Key bagsKey = Key('maps-bags');
  static Key mapViewKey(String m) => Key('map-view-$m');
  static Key progressKey(String r) => Key('map-progress-$r');

  @override
  State<MapManagePage> createState() => _MapManagePageState();
}

String _when(Object? ms) {
  if (ms is! num) return '';
  final d = DateTime.fromMillisecondsSinceEpoch(ms.toInt());
  String two(int n) => n.toString().padLeft(2, '0');
  return '${d.year}-${two(d.month)}-${two(d.day)} ${two(d.hour)}:${two(d.minute)}';
}

String _mb(num bytes) => bytes >= 1e9
    ? '${(bytes / 1e9).toStringAsFixed(1)} GB'
    : '${(bytes / 1e6).toStringAsFixed(bytes >= 1e7 ? 0 : 1)} MB';

String _left(num s) {
  final n = s.round();
  if (n < 60) return tr('$n s', '$n 秒');
  return tr('${n ~/ 60} min ${n % 60} s', '${n ~/ 60} 分 ${n % 60} 秒');
}

/// POC 第 6 项：换图走到哪了（站点的换图记录 `activation`）。[rateBps]：最近两次刷新算出来的下载速度。
String mapSwitchText(Map<String, dynamic> a, {required int nowMs, double? rateBps}) {
  final reason = '${a['reason'] ?? ''}';
  switch (a['state']) {
    case 'pending':
      final d = a['download'];
      if (d is! Map) return tr('Sent: waiting for the robot to start downloading', '已发出，等机器人开始下载');
      final bytes = (d['bytes'] as num?) ?? 0, total = (d['total'] as num?) ?? 0;
      final at = (d['at_ms'] as num?)?.toInt() ?? nowMs;
      final idle = ((nowMs - at) / 1000).round();
      final total0 = total > 0 ? total : bytes;
      final got = '${_mb(bytes).replaceAll(' MB', '')} / ${_mb(total0)}';
      if (idle > 15) {
        return tr('Downloaded $got; nothing for $idle s: loading the map, or the link is down',
            '已下载 $got；$idle 秒没再下：在载入定位，或者网断了');
      }
      final eta = rateBps != null && rateBps > 0 && total > bytes ? (total - bytes) / rateBps : null;
      return tr('Downloaded $got${eta != null ? ', about ${_left(eta)} left' : ''}',
          '已下载 $got${eta != null ? '，约还要 ${_left(eta)}' : ''}');
    case 'confirmed':
      return a['confirmed'] == 'localizer'
          ? tr('Switched; localized on the new map', '已换好，已在新图上定好位')
          : tr('Switched. The robot is using this map now.', '已换好，机器人正在用这张图。');
    case 'failed':
      return tr('Not switched${reason.isEmpty ? '' : ': $reason'}', '没换成${reason.isEmpty ? '' : '：$reason'}');
    default:
      return tr('No answer for too long: treat as not switched', '太久没动静，当作没换成');
  }
}

class _MapManagePageState extends State<MapManagePage> {
  /// 每台机器人上一次看到的下载量（字节、站点时刻），用来算速度。
  final Map<String, (num, int)> _lastDl = {};
  final Map<String, double> _rate = {};
  Timer? _poll;

  @override
  void dispose() {
    _poll?.cancel();
    super.dispose();
  }

  /// 有机器人在换图就 2 秒刷一次；都换完了停。
  void _track(Map<String, dynamic> ov) {
    var pending = false;
    for (final r in (ov['robots'] as List? ?? const [])) {
      if (r is! Map) continue;
      final a = r['activation'];
      if (a is! Map || a['state'] != 'pending') continue;
      pending = true;
      final d = a['download'];
      if (d is! Map) continue;
      final id = '${r['robot_id']}';
      final bytes = (d['bytes'] as num?) ?? 0;
      final at = (d['at_ms'] as num?)?.toInt() ?? 0;
      final prev = _lastDl[id];
      if (prev != null && at > prev.$2 && bytes >= prev.$1) {
        _rate[id] = (bytes - prev.$1) / ((at - prev.$2) / 1000);
      }
      _lastDl[id] = (bytes, at);
    }
    if (pending) {
      _poll ??= Timer.periodic(const Duration(seconds: 2), (_) => unawaited(_load()));
    } else {
      _poll?.cancel();
      _poll = null;
    }
  }

  SiteApi get api => widget.api;
  Map<String, dynamic>? _ov;
  bool _wizardActive = false;
  String _err = '';

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  Future<void> _load() async {
    try {
      final got = await Future.wait([api.mapsOverview(), api.mapWizard()]);
      if (!mounted) return;
      _track(got[0]);
      setState(() {
        _ov = got[0];
        _wizardActive = got[1]['wizard'] is Map;
        _err = '';
      });
    } on SiteError catch (e) {
      if (mounted) setState(() => _err = refusalText(e));
    }
  }

  void _snack(String t) {
    if (!mounted) return;
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(SnackBar(content: Text(t)));
  }

  Future<void> _send(String mapId, String version) async {
    final robots = [
      for (final r in (_ov?['robots'] as List? ?? const []))
        if (r is Map && r['can_activate'] == true) '${r['robot_id']}'
    ];
    if (robots.isEmpty) {
      _snack(tr('No robot online can switch maps right now', '现在没有在线、能换图的机器人'));
      return;
    }
    final robot = await showDialog<String>(
      context: context,
      builder: (c) => SimpleDialog(title: Text(tr('Send to which robot', '下发给哪台机器人')), children: [
        for (final r in robots)
          SimpleDialogOption(key: Key('send-to-$r'), onPressed: () => Navigator.pop(c, r), child: Text(r)),
      ]),
    );
    if (robot == null || !mounted) return;
    try {
      Map<String, dynamic> r;
      try {
        r = await api.activateMap(robot, mapId, version);
      } on SiteError catch (e) {
        if (e.status != 409 || e.body['reason'] != 'no_home' || !mounted) rethrow;
        final go = await showDialog<bool>(
          context: context,
          builder: (c) => AlertDialog(
            title: Text(tr('$robot has no origin on this version', '$robot 在此版本上尚未标原点')),
            content: Text(tr(
                'The robot takes no patrols until its origin is marked. Drive it in front of the dock and tap "Mark origin here" on its page.',
                '标原点之前机器人不执行巡逻。请将机器人开到充电桩前，在机器人页点「在这儿标原点」。')),
            actions: [
              TextButton(onPressed: () => Navigator.pop(c, false), child: Text(tr('Cancel', '取消'))),
              FilledButton(
                  key: const Key('send-without-home'),
                  onPressed: () => Navigator.pop(c, true),
                  child: Text(tr('Send anyway', '仍然下发'))),
            ],
          ),
        );
        if (go != true) return;
        r = await api.activateMap(robot, mapId, version, withoutHome: true);
      }
      final ack = (r['ack'] as Map?) ?? const {};
      _snack(ack['result'] == 'accepted'
          ? tr('$robot is downloading and loading the map', '$robot 正在下载并加载地图')
          : tr('The robot rejected it: ${ack['reason'] ?? ack['result']}', '机器人未接受：${ack['reason'] ?? ack['result']}'));
    } on SiteError catch (e) {
      _snack(refusalText(e));
    }
    await _load();
  }

  Future<void> _delete(String mapId, String version) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (c) => AlertDialog(
        title: Text(tr('Delete this version?', '删除此版本？')),
        content: Text(tr("This can't be undone. No robot is using this version.", '删除后无法恢复。当前没有机器人使用此版本。')),
        actions: [
          TextButton(onPressed: () => Navigator.pop(c, false), child: Text(tr('Cancel', '取消'))),
          FilledButton(key: const Key('delete-ok'), onPressed: () => Navigator.pop(c, true), child: Text(tr('Delete', '删除'))),
        ],
      ),
    );
    if (ok != true) return;
    try {
      await api.deleteMapVersion(mapId, version);
    } on SiteError catch (e) {
      _snack(refusalText(e));
    }
    await _load();
  }

  Future<void> _rollback(String robot, Map rb) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (c) => AlertDialog(
        title: Text(tr('Switch $robot to ${rb['map_id']} ${versionLabel('${rb['version']}')}?', '把 $robot 换回 ${rb['map_id']} ${versionLabel('${rb['version']}')}？')),
        actions: [
          TextButton(onPressed: () => Navigator.pop(c, false), child: Text(tr('Cancel', '取消'))),
          FilledButton(key: const Key('rollback-ok'), onPressed: () => Navigator.pop(c, true), child: Text(tr('Roll back', '回退'))),
        ],
      ),
    );
    if (ok != true) return;
    try {
      await api.rollbackMap(robot);
      _snack(tr('$robot is rolling back', '$robot 正在回退到上一版'));
    } on SiteError catch (e) {
      _snack(refusalText(e));
    }
    await _load();
  }

  Widget _version(NwColors c, String mapId, Map<String, dynamic> v) {
    final version = '${v['version']}';
    final note = '${v['note'] ?? ''}';
    final q = (v['quality'] as Map?) ?? const {};
    final verdict = verdictOf(q);
    final reasons = [for (final r in (q['reasons'] as List? ?? const [])) qualityReasonText('$r')];
    final on = [for (final r in (v['loaded_on'] as List? ?? const [])) '$r'];
    final path = q['path_m'];
    final canDelete = on.isEmpty && v['latest'] != true;
    // 11-05 现场第 10 条：缺定位文件的老版本，带定位器的机器人收了也会拒
    final unusable = '${v['unusable'] ?? ''}';
    // 11-11：编辑、去噪出来的草稿只在站点上，网页预览、发布到站点后才能下发
    final draft = v['draft'] == true;
    final sub = NwText.bodySmall.copyWith(color: c.textSecondary);
    final info = [
      _when(v['created_ms']),
      if (path is num) tr('walked ${path.round()} m', '走了 ${path.round()} 米'),
      ...reasons,
    ].where((s) => s.isNotEmpty).join(' · ');
    Widget btn(Key key, String label, VoidCallback on) => Expanded(
        child: NwButton(buttonKey: key, label: label, size: NwButtonSize.small, variant: NwButtonVariant.outline, onPressed: on));
    // App V2 稿 S-maps：一版一行 —— 在用的绿方块、别的空心圈；第几版 · 说明；建图结论、谁在用、日期；按钮一排等宽
    return Container(
      key: MapManagePage.versionKey(mapId, version),
      padding: const EdgeInsets.symmetric(vertical: 10),
      decoration: BoxDecoration(border: Border(top: BorderSide(color: c.outline))),
      child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Padding(
            padding: const EdgeInsets.only(top: 4, right: Nw.s8),
            child: on.isNotEmpty
                ? Icon(Icons.square, size: 12, color: c.success)
                : Icon(Icons.circle_outlined, size: 12, color: c.textSecondary)),
        Expanded(
            child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          Row(children: [
            Expanded(
                child: Text(note.isNotEmpty ? '${versionLabel(version)} · ${versionNoteText(note)}' : versionLabel(version),
                    style: NwText.titleSmall.copyWith(color: c.text, fontWeight: FontWeight.w700))),
            if (draft)
              NwStatusPill(key: MapManagePage.draftKey(mapId, version), label: tr('Draft', '草稿'), tone: NwTone.warning),
          ]),
          Wrap(children: [
            // 第 13 轮 W13-03 ③：这是建图质量，不是能不能下发（下发要先确认禁行区）—— 写明「建图」
            if (verdict != 'unknown')
              Text(tr('Mapping: ${verdictText(verdict)}', '建图${verdictText(verdict)}'),
                  style: sub.copyWith(color: c.fg(verdictTone(verdict)), fontWeight: FontWeight.w600)),
            if (on.isNotEmpty) ...[
              if (verdict != 'unknown') Text(' · ', style: sub),
              Text(tr('In use: ${on.join(', ')}', '${on.join('、')} 在用'), style: sub.copyWith(color: c.text)),
            ],
          ]),
          if (info.isNotEmpty) Text(info, style: sub),
          if (draft)
            Text(
                tr('Draft: preview it in the web map editor and publish it to the site before sending it to robots',
                    '草稿：在网页地图编辑器里预览、发布到站点后才能下发'),
                style: sub),
          if (unusable.isNotEmpty)
            Text(tr("This version lacks localization files, robots can't use it: $unusable", '这一版缺定位文件，机器人用不了：$unusable'),
                style: NwText.bodySmall.copyWith(color: c.error)),
          const SizedBox(height: Nw.s8),
          Row(children: [
            btn(MapManagePage.viewKey(mapId, version), tr('View', '看图'), () => Navigator.push(context,
                MaterialPageRoute<void>(builder: (_) => SiteMapPreviewPage(api: api, mapId: mapId, version: version)))),
            if (!draft) ...[
              const SizedBox(width: Nw.s8),
              btn(MapManagePage.sendKey(mapId, version), tr('Deploy to…', '下发给…'), () => _send(mapId, version)),
            ],
            if (canDelete) ...[
              const SizedBox(width: Nw.s8),
              btn(MapManagePage.deleteKey(mapId, version), tr('Delete', '删除'), () => _delete(mapId, version)),
            ],
          ]),
        ])),
      ]),
    );
  }

  @override
  Widget build(BuildContext context) {
    final c = Nw.of(context);
    final ov = _ov;
    final maps = [for (final m in (ov?['maps'] as List? ?? const [])) if (m is Map) m.cast<String, dynamic>()];
    final robots = [for (final r in (ov?['robots'] as List? ?? const [])) if (r is Map) r.cast<String, dynamic>()];
    Future<void> wizard() async {
      await openMapWizard(context, api);
      await _load();
    }

    final newLabel = _wizardActive
        ? tr('Continue mapping', '继续建图')
        : (maps.isEmpty ? tr('Build the first map', '建第一张图') : tr('Build new version', '重新建一版'));
    Widget section(List<Widget> kids, {String? title}) => Container(
        margin: const EdgeInsets.only(top: Nw.s8),
        color: c.surface,
        padding: const EdgeInsets.fromLTRB(Nw.s16, Nw.s16, Nw.s16, Nw.s16),
        child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          if (title != null) ...[
            Text(title, style: NwText.titleMedium.copyWith(color: c.text, fontWeight: FontWeight.w700)),
            const SizedBox(height: Nw.s8),
          ],
          ...kids,
        ]));
    return Scaffold(
      appBar: AppBar(
          title: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(tr('Map management', '地图管理')),
        Text(tr('Versions of each map', '每张图的各个版本'), style: NwText.bodySmall.copyWith(color: c.textSecondary)),
      ])),
      body: RefreshIndicator(
        onRefresh: _load,
        child: ListView(padding: const EdgeInsets.only(bottom: Nw.s24), children: [
          if (_err.isNotEmpty) Padding(padding: const EdgeInsets.all(Nw.s16), child: NwNotice(tone: NwTone.error, text: _err)),
          if (ov == null && _err.isEmpty) const Padding(padding: EdgeInsets.all(Nw.s24), child: Center(child: CircularProgressIndicator())),
          if (ov != null && maps.isEmpty)
            Padding(
                padding: const EdgeInsets.all(Nw.s16),
                child: NwButton(
                    buttonKey: MapManagePage.newKey,
                    label: newLabel,
                    icon: Icons.add_location_alt_rounded,
                    fullWidth: true,
                    size: NwButtonSize.large,
                    onPressed: wizard)),
          for (final (mi, m) in maps.indexed)
            () {
              final vs = [for (final v in (m['versions'] as List? ?? const [])) if (v is Map) v.cast<String, dynamic>()];
              final latest = vs.where((v) => v['latest'] == true).firstOrNull ?? vs.firstOrNull;
              return section(title: '${m['map_id']}', [
                for (final v in vs) _version(c, '${m['map_id']}', v),
                const SizedBox(height: Nw.s8),
                // 建图一次只能建一张（向导是全站一个）：按钮放在第一张图下面
                Row(children: [
                  if (mi == 0)
                    Expanded(
                        child: NwButton(buttonKey: MapManagePage.newKey, label: newLabel, onPressed: wizard)),
                  if (mi == 0 && latest != null) const SizedBox(width: Nw.s8),
                  if (latest != null)
                    Expanded(
                        child: NwButton(
                            buttonKey: MapManagePage.mapViewKey('${m['map_id']}'),
                            label: tr('View map', '看图'),
                            variant: NwButtonVariant.outline,
                            onPressed: () => Navigator.push(
                                context,
                                MaterialPageRoute<void>(
                                    builder: (_) =>
                                        SiteMapPreviewPage(api: api, mapId: '${m['map_id']}', version: '${latest['version']}'))))),
                ]),
              ]);
            }(),
          if (robots.isNotEmpty)
            section(title: tr('Version per robot', '各机器人在用哪一版'), [
              for (final r in robots)
                Container(
                  padding: const EdgeInsets.symmetric(vertical: 8),
                  decoration: BoxDecoration(border: Border(top: BorderSide(color: c.outline))),
                  child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                    Row(children: [
                      SizedBox(
                          width: 32,
                          child: Text('${r['robot_id']}', style: NwText.titleSmall.copyWith(color: c.text, fontWeight: FontWeight.w700))),
                      Expanded(
                          child: Text(
                              r['loaded'] is Map
                                  ? '${r['loaded']['map_id']} · ${versionLabel('${r['loaded']['version']}')}'
                                  : tr('(no map)', '（没有图）'),
                              style: NwText.bodyMedium.copyWith(color: c.text))),
                      if (r['rollback'] is Map)
                        NwButton(
                            buttonKey: MapManagePage.rollbackKey('${r['robot_id']}'),
                            label: tr('Switch to ${versionLabel('${r['rollback']['version']}')}', '换回${versionLabel('${r['rollback']['version']}')}'),
                            size: NwButtonSize.small,
                            variant: NwButtonVariant.outline,
                            onPressed: () => _rollback('${r['robot_id']}', r['rollback'] as Map)),
                    ]),
                    // POC 第 6 项：换图进度（下了多少、还要多久、在载入、换好、没换成的原因）
                    if (r['activation'] is Map && (r['activation'] as Map)['state'] != null)
                      Padding(
                        padding: const EdgeInsets.only(top: Nw.s4),
                        child: Text(
                            '${(r['activation'] as Map)['map_id']}:${(r['activation'] as Map)['version']}  '
                            '${mapSwitchText((r['activation'] as Map).cast<String, dynamic>(), nowMs: (ov?['now_ms'] as num?)?.toInt() ?? DateTime.now().millisecondsSinceEpoch, rateBps: _rate['${r['robot_id']}'])}',
                            key: MapManagePage.progressKey('${r['robot_id']}'),
                            style: NwText.bodySmall.copyWith(color: c.textSecondary)),
                      ),
                  ]),
                ),
            ]),
          Padding(
              padding: const EdgeInsets.fromLTRB(Nw.s16, Nw.s16, Nw.s16, Nw.s8),
              child: Text(tr('Engineer', '工程师'), style: NwText.labelMedium.copyWith(color: c.textSecondary))),
          Material(
            color: c.surface,
            child: ListTile(
              key: MapManagePage.bagsKey,
              leading: Icon(Icons.description_outlined, color: c.textSecondary),
              title: Text(tr('Mapping recordings', '建图录包'), style: NwText.bodyMedium.copyWith(color: c.text, fontWeight: FontWeight.w700)),
              subtitle: Text(tr('Record, rebuild from recordings', '录包、用录包重建'), style: NwText.bodySmall.copyWith(color: c.textSecondary)),
              trailing: Icon(Icons.chevron_right_rounded, color: c.textSecondary),
              onTap: () => Navigator.push(context, MaterialPageRoute<void>(builder: (_) => SiteMapsPage(api: api))),
            ),
          ),
        ]),
      ),
    );
  }
}
