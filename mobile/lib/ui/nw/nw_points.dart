// App V2 稿 S-points「待命点、拦截点、摄像头」：一页四段（原点、待命点、拦截点、固定摄像头）。
// 每段读站点现成的接口，按钮进原来的编辑页；「设为默认」就地做。保安只看原点和待命点。
import 'dart:async';

import 'package:flutter/material.dart';

import '../../l10n.dart';
import '../../net/site_client.dart';
import '../site_cameras.dart';
import '../site_intercepts.dart';
import '../site_recordings.dart' show clipTime;
import '../site_standby.dart';
import 'nw_theme.dart';

class SitePointsPage extends StatefulWidget {
  final SiteApi api;
  const SitePointsPage({super.key, required this.api});

  static Key robotKey(String id) => Key('points-robot-$id');
  static Key standbyKey(String name) => Key('points-standby-$name');
  static Key defaultKey(String name) => Key('points-default-$name');
  static const Key manageStandbyKey = Key('points-standby-manage');
  static Key interceptKey(String name) => Key('points-intercept-$name');
  static Key cameraKey(String name) => Key('points-camera-$name');
  static const Key msgKey = Key('points-msg');

  @override
  State<SitePointsPage> createState() => _SitePointsPageState();
}

class _SitePointsPageState extends State<SitePointsPage> {
  List<Map<String, dynamic>> _robots = const [];
  String? _robot;
  List<Map<String, dynamic>> _points = const [];
  List<Map<String, dynamic>> _homes = const [];
  List<Map<String, dynamic>>? _intercepts;
  List<Map<String, dynamic>> _zones = const [];
  List<Map<String, dynamic>>? _cameras;
  String _msg = '';
  bool _busy = false;

  bool get _maps => widget.api.session?.canManageMaps ?? false;

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  Future<void> _load() async {
    try {
      final rs = [for (final r in await widget.api.robots()) if (r['revoked'] != true) r];
      if (!mounted) return;
      setState(() {
        _robots = rs;
        _robot ??= rs.isEmpty ? null : '${rs.first['robot_id']}';
      });
    } on SiteError catch (e) {
      if (mounted) setState(() => _msg = tr("Can't load robots: $e", '无法加载机器人：$e'));
    }
    await _loadStandby();
    if (!_maps) return;
    try {
      final d = await widget.api.intercepts();
      if (mounted) {
        setState(() {
          _intercepts = (d['intercepts'] as List? ?? const []).cast<Map<String, dynamic>>();
          _zones = (d['zones'] as List? ?? const []).cast<Map<String, dynamic>>();
        });
      }
    } on SiteError {
      // 站点没开拦截点：这一段不摆
    }
    try {
      final cams = await widget.api.cameras();
      if (mounted) setState(() => _cameras = cams);
    } on SiteError {
      // 站点没开摄像头
    }
  }

  Future<void> _loadStandby() async {
    final id = _robot;
    if (id == null) return;
    try {
      final r = await widget.api.standbyPoints(id);
      if (!mounted || id != _robot) return;
      setState(() {
        _points = (r['points'] as List? ?? const []).cast<Map<String, dynamic>>();
        _homes = (r['homes'] as List? ?? const []).cast<Map<String, dynamic>>();
      });
    } on SiteError catch (e) {
      if (mounted) setState(() => _msg = tr("Can't load standby points: $e", '无法加载待命点：$e'));
    }
  }

  void _pick(String id) {
    if (id == _robot) return;
    setState(() {
      _robot = id;
      _points = const [];
      _homes = const [];
    });
    unawaited(_loadStandby());
  }

  Future<void> _makeDefault(Map<String, dynamic> p) async {
    final id = _robot;
    if (id == null || _busy) return;
    setState(() => _busy = true);
    try {
      await widget.api.setStandbyDefault(id, p);
      if (mounted) setState(() => _msg = tr('${standbyName(p)} is now the default', '${standbyName(p)} 已设为默认'));
    } on SiteError catch (e) {
      if (mounted) setState(() => _msg = tr("Couldn't set default: $e", '设默认失败：$e'));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
    await _loadStandby();
  }

  Future<void> _push(Widget page) async {
    await Navigator.of(context).push(MaterialPageRoute<void>(builder: (_) => page));
    if (mounted) unawaited(_load());
  }

  Map<String, dynamic>? get _robotView {
    for (final r in _robots) {
      if ('${r['robot_id']}' == _robot) return r;
    }
    return null;
  }

  @override
  Widget build(BuildContext context) {
    final c = Nw.of(context);
    final shape = RoundedRectangleBorder(borderRadius: BorderRadius.circular(2));
    final small = OutlinedButton.styleFrom(
        minimumSize: const Size(48, 40), shape: shape, padding: const EdgeInsets.symmetric(horizontal: Nw.s8));
    final sub = NwText.bodySmall.copyWith(color: c.textSecondary);
    Widget section(String title, List<Widget> children, {String? note}) => Container(
        margin: const EdgeInsets.only(top: Nw.s8),
        color: c.surface,
        padding: const EdgeInsets.fromLTRB(Nw.s16, Nw.s16, Nw.s16, Nw.s8),
        child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          Text(title, style: NwText.titleMedium.copyWith(color: c.text, fontWeight: FontWeight.w700)),
          if (note != null) ...[const SizedBox(height: Nw.s4), Text(note, style: sub)],
          const SizedBox(height: Nw.s8),
          ...children,
        ]));
    Widget row({Key? key, IconData? icon, Color? dot, required String title, String sub2 = '', Widget? trailing, VoidCallback? onTap}) =>
        Material(
            color: c.surface,
            child: InkWell(
                key: key,
                onTap: onTap,
                child: Container(
                    padding: const EdgeInsets.symmetric(vertical: 10),
                    decoration: BoxDecoration(border: Border(top: BorderSide(color: c.outline))),
                    child: Row(children: [
                      if (icon != null) ...[Icon(icon, size: 20, color: c.textSecondary), const SizedBox(width: Nw.s16)],
                      if (dot != null) ...[Container(width: 10, height: 10, color: dot), const SizedBox(width: Nw.s16)],
                      Expanded(
                          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                        Text(title, style: NwText.titleSmall.copyWith(color: c.text, fontWeight: FontWeight.w700)),
                        if (sub2.isNotEmpty) Text(sub2, style: sub),
                      ])),
                      ?trailing,
                    ]))));
    final robot = _robot;
    final origin = _homes.isNotEmpty;
    final linked = <String, List<String>>{};
    for (final z in _zones) {
      final i = '${z['intercept'] ?? ''}';
      if (i.isNotEmpty) (linked[i] ??= <String>[]).add('${z['zone']}');
    }
    final sep = tr(', ', '、');
    return Scaffold(
      backgroundColor: c.bg,
      appBar: AppBar(title: Text(_maps ? tr('Standby, intercepts & cameras', '待命点、拦截点、摄像头') : tr('Standby points & origin', '待命点与原点'))),
      body: RefreshIndicator(
          onRefresh: _load,
          child: ListView(padding: const EdgeInsets.only(bottom: Nw.s24), children: [
            if (_robots.length > 1)
              Container(
                  color: c.surface,
                  padding: const EdgeInsets.all(Nw.s16),
                  child: SegmentedButton<String>(
                      showSelectedIcon: false,
                      style: SegmentedButton.styleFrom(
                          shape: shape, selectedBackgroundColor: c.primary, selectedForegroundColor: c.onPrimary),
                      segments: [
                        for (final r in _robots)
                          ButtonSegment(
                              value: '${r['robot_id']}',
                              label: Text('${r['name'] ?? r['robot_id']}',
                                  key: SitePointsPage.robotKey('${r['robot_id']}'), overflow: TextOverflow.ellipsis)),
                      ],
                      selected: {?robot},
                      onSelectionChanged: (v) => _pick(v.first))),
            if (_msg.isNotEmpty)
              Padding(
                  padding: const EdgeInsets.fromLTRB(Nw.s16, Nw.s8, Nw.s16, 0),
                  child: Text(_msg, key: SitePointsPage.msgKey, style: NwText.bodyMedium.copyWith(color: c.text))),
            if (robot == null)
              Padding(
                  padding: const EdgeInsets.all(Nw.s16),
                  child: Text(tr('No robots on this site yet.', '站点上还没有机器人。'), style: sub))
            else ...[
              section(tr('Origin', '原点'), [
                row(
                    dot: origin ? c.success : c.outline,
                    title: origin ? tr('Origin set', '已标原点') : tr('No origin marked yet', '尚未标原点'),
                    sub2: tr('Change it with "Mark origin here" on the robot page', '在机器人页「在这儿标原点」修改')),
              ], note: tr('Used for safe return and docking; one per map.', '用于安全返航和回充；每张地图一个。')),
              section(tr('Standby points ${_points.length}', '待命点 ${_points.length}'), [
                for (final p in _points)
                  row(
                      key: SitePointsPage.standbyKey('${p['name']}'),
                      icon: Icons.place_outlined,
                      title: standbyName(p),
                      sub2: p['default'] == true ? tr('Default · return here after patrol', '默认 · 巡逻结束回这里') : '',
                      trailing: _maps && p['default'] != true
                          ? OutlinedButton(
                              key: SitePointsPage.defaultKey('${p['name']}'),
                              style: small,
                              onPressed: _busy ? null : () => unawaited(_makeDefault(p)),
                              child: Text(tr('Set as default', '设为默认')))
                          : null),
                if (_points.isEmpty) Padding(padding: const EdgeInsets.only(bottom: Nw.s8), child: Text(tr('No standby points yet', '暂无待命点'), style: sub)),
                Padding(
                    padding: const EdgeInsets.symmetric(vertical: Nw.s8),
                    child: OutlinedButton(
                        key: SitePointsPage.manageStandbyKey,
                        style: small,
                        onPressed: () => _push(SiteStandbyPage(
                            api: widget.api, robotId: robot, canMarkHere: robotCanStandbyHere(_robotView))),
                        child: Text(_maps
                            ? tr('Add or edit standby points', '添加、修改待命点')
                            : tr('Return to a standby point', '回某个待命点')))),
              ]),
            ],
            if (_maps && _intercepts != null)
              section(tr('Intercept points ${_intercepts!.length}', '拦截点 ${_intercepts!.length}'), [
                for (final p in _intercepts!)
                  row(
                      key: SitePointsPage.interceptKey('${p['name']}'),
                      icon: Icons.person_outline_rounded,
                      title: '${p['name']}',
                      sub2: (linked['${p['name']}'] ?? const <String>[]).join(sep),
                      trailing: OutlinedButton(
                          style: small,
                          onPressed: () => _push(SiteInterceptsPage(api: widget.api)),
                          child: Text(tr('Link zones', '关联防区')))),
                if (_intercepts!.isEmpty)
                  row(
                      title: tr('No intercept points yet', '暂无拦截点'),
                      trailing: OutlinedButton(
                          style: small,
                          onPressed: () => _push(SiteInterceptsPage(api: widget.api)),
                          child: Text(tr('Add', '添加')))),
              ]),
            if (_maps && _cameras != null)
              section(tr('Fixed cameras ${_cameras!.length}', '固定摄像头 ${_cameras!.length}'), [
                for (final cam in _cameras!)
                  row(
                      key: SitePointsPage.cameraKey('${cam['name']}'),
                      dot: cam['connected'] == true ? c.success : c.error,
                      title: '${cam['name']}',
                      trailing: Text(
                          cam['last_event_ms'] == null
                              ? tr('Last: none', '最近：无')
                              : tr('Last: ${clipTime((cam['last_event_ms'] as num).toInt())}',
                                  '最近：${clipTime((cam['last_event_ms'] as num).toInt())}'),
                          style: sub),
                      onTap: () => _push(SiteCamerasPage(api: widget.api))),
                if (_cameras!.isEmpty)
                  Padding(
                      padding: const EdgeInsets.only(bottom: Nw.s8),
                      child: Text(tr('No cameras yet. An engineer registers them on the site host.', '暂无摄像头。摄像头由工程师在站点主机上登记。'),
                          style: sub)),
              ]),
          ])),
    );
  }
}
