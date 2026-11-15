// App V2 稿 S-layout「地图与布置」：上面一张小地图（点了进全屏地图），下面一层一行，每行进原来那一页。
import 'dart:async';

import 'package:flutter/material.dart';

import '../../l10n.dart';
import '../../net/site_client.dart';
import '../map_manage.dart';
import '../map_view.dart' show loadMapPicture;
import '../site_cameras.dart';
import '../site_intercepts.dart';
import '../site_routes.dart';
import 'nw_p2_duty.dart' show NwMapThumb;
import 'nw_theme.dart';

/// 机器人在用哪张图（图号、版本）；没报就是 null。
(String, String)? robotMapOf(Map<String, dynamic>? r) {
  final caps = r?['capabilities'];
  final tasks = caps is Map ? caps['tasks'] : null;
  for (final k in const ['running_config', 'patrol']) {
    final x = tasks is Map ? tasks[k] : null;
    if (x is Map && '${x['map_id'] ?? ''}'.isNotEmpty && '${x['map_version'] ?? ''}'.isNotEmpty) {
      return ('${x['map_id']}', '${x['map_version']}');
    }
  }
  return null;
}

class SiteLayoutPage extends StatefulWidget {
  final SiteApi api;

  /// 待命点、原点按机器人设：去机器人列表（外壳那一层）。
  final VoidCallback onRobots;

  /// 全屏地图（外壳的地图层：防区、禁行区在那里画）。
  final VoidCallback onMap;
  const SiteLayoutPage({super.key, required this.api, required this.onRobots, required this.onMap});

  static const Key mapKey = Key('layout-map');
  static Key rowKey(String id) => Key('layout-$id');

  @override
  State<SiteLayoutPage> createState() => _SiteLayoutPageState();
}

class _SiteLayoutPageState extends State<SiteLayoutPage> {
  (String, String)? _map;
  List<String> _robotsOnMap = const [];
  int? _cameras;
  (int, int)? _intercepts;

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  Future<void> _load() async {
    try {
      final rs = await widget.api.robots();
      final live = [for (final r in rs) if (r['revoked'] != true) r];
      final m = live.map(robotMapOf).whereType<(String, String)>().firstOrNull;
      if (mounted) {
        setState(() {
          _map = m;
          _robotsOnMap = [for (final r in live) if (robotMapOf(r) == m) '${r['robot_id']}'];
        });
      }
    } on SiteError {
      // 读不到就不摆小地图
    }
    try {
      final n = (await widget.api.cameras()).length;
      if (mounted) setState(() => _cameras = n);
    } on SiteError {
      // 站点没开摄像头
    }
    try {
      final d = await widget.api.intercepts();
      final linked = [for (final z in (d['zones'] as List? ?? const [])) if (z is Map && '${z['intercept'] ?? ''}'.isNotEmpty) z];
      if (mounted) setState(() => _intercepts = ((d['intercepts'] as List? ?? const []).length, linked.length));
    } on SiteError {
      // 同上
    }
  }

  void _push(Widget page) => Navigator.of(context).push(MaterialPageRoute<void>(builder: (_) => page));

  void _fullMap() {
    Navigator.of(context).maybePop();
    widget.onMap();
  }

  void _robots() {
    Navigator.of(context).maybePop();
    widget.onRobots();
  }

  @override
  Widget build(BuildContext context) {
    final c = Nw.of(context);
    final s = widget.api.session;
    final maps = s?.canManageMaps ?? false;
    final m = _map;
    Widget label(String t) => Padding(
        padding: const EdgeInsets.fromLTRB(Nw.s16, Nw.s16, Nw.s16, Nw.s8),
        child: Text(t, style: NwText.labelLarge.copyWith(color: c.textSecondary, fontWeight: FontWeight.w600)));
    Widget row(String id, IconData icon, String title, String sub, VoidCallback on) => Material(
        color: c.surface,
        child: InkWell(
            key: SiteLayoutPage.rowKey(id),
            onTap: on,
            child: Container(
                padding: const EdgeInsets.symmetric(horizontal: Nw.s16, vertical: 12),
                decoration: BoxDecoration(border: Border(bottom: BorderSide(color: c.outline))),
                child: Row(children: [
                  Icon(icon, size: 22, color: c.textSecondary),
                  const SizedBox(width: Nw.s16),
                  Expanded(
                      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Text(title, style: NwText.titleSmall.copyWith(color: c.text, fontWeight: FontWeight.w700)),
                    if (sub.isNotEmpty) Text(sub, style: NwText.bodySmall.copyWith(color: c.textSecondary)),
                  ])),
                  Icon(Icons.chevron_right_rounded, color: c.textSecondary),
                ]))));
    final sep = tr(', ', '、');
    return Scaffold(
      backgroundColor: c.bg,
      appBar: AppBar(
          title: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(tr('Map & layout', '地图与布置')),
        if (m != null) Text('${m.$1} · v${m.$2}', style: NwText.bodySmall.copyWith(color: c.textSecondary)),
      ])),
      body: RefreshIndicator(
          onRefresh: _load,
          child: ListView(padding: const EdgeInsets.only(bottom: Nw.s24), children: [
            if (m != null)
              Padding(
                  padding: const EdgeInsets.all(Nw.s16),
                  child: NwMapThumb(
                      key: ValueKey<String>('layout-map ${m.$1}:${m.$2}'),
                      tapKey: SiteLayoutPage.mapKey,
                      height: 200,
                      load: () => loadMapPicture(widget.api, m.$1, m.$2),
                      label: _robotsOnMap.isEmpty ? '' : tr('In use by ${_robotsOnMap.join(sep)}', '${_robotsOnMap.join(sep)} 在用'),
                      action: tr('Full-screen map', '全屏地图'),
                      onTap: _fullMap)),
            label(tr('Layers', '图层')),
            row('zones', Icons.shield_outlined, tr('Zones', '防区'), tr('Draw and edit zones on the map', '在地图上画、改防区'), _fullMap),
            row('nogo', Icons.close_rounded, tr('No-go zones, speed limits, virtual walls', '禁行区、限速、虚拟墙'),
                tr('Robots only go out on their own once confirmed', '确认后机器人才会自己出发'), _fullMap),
            if (maps)
              row('routes', Icons.route_outlined, tr('Patrol routes', '巡逻路线'),
                  tr('Which points, how long to stop, what to photograph', '途经点、停多久、拍什么'), () => _push(SiteRoutesPage(api: widget.api))),
            row('standby', Icons.place_outlined, tr('Standby points & origin', '待命点与原点'),
                tr('Set per robot: Robots → robot → Settings', '按机器人设：机器人 → 某台 → 设置'), _robots),
            if (maps)
              row('cameras', Icons.videocam_outlined, tr('Fixed cameras', '固定摄像头'),
                  _cameras == null ? '' : tr('$_cameras', '$_cameras 个'), () => _push(SiteCamerasPage(api: widget.api))),
            if (maps)
              row(
                  'intercepts',
                  Icons.person_pin_circle_outlined,
                  tr('Intercept points', '拦截点'),
                  _intercepts == null ? '' : tr('${_intercepts!.$1} · Linked to ${_intercepts!.$2} zones', '${_intercepts!.$1} 个 · 关联 ${_intercepts!.$2} 个防区'),
                  () => _push(SiteInterceptsPage(api: widget.api))),
            if (maps) ...[
              label(tr('Maps', '地图')),
              row('maps', Icons.map_outlined, tr('Map management & mapping', '地图管理与建图'),
                  m == null ? tr('Versions, deploy, roll back, new map', '版本、下发、退回、新建') : tr('${m.$1} v${m.$2}', '${m.$1} v${m.$2}'),
                  () => _push(MapManagePage(api: widget.api))),
            ],
          ])),
    );
  }
}
