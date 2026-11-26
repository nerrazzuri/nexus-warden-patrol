/// 待命点与原点（W13a，决策 16）。
///
/// **原点**是安全返航、回充的语义，每张图一个（「在这儿标原点」改它）；**待命点**是运营调度的语义，可以
/// 多个：任务做完狗回默认的那一个，也可以叫它回指定的一个。这一页列出这台狗的原点和待命点；管理员能在狗现在
/// 的位置设待命点（不动原点）、设默认、删除；能派单的人能叫狗回某一个待命点。
library;

import 'package:flutter/material.dart';

import '../l10n.dart';
import '../net/site_client.dart';
import 'nw/nw_ask.dart';
import 'nw/nw_points.dart' show standbyDefaultBlocked;
import 'nw/nw_theme.dart';
import 'nw/nw_widgets.dart';
import 'widget/bar_actions.dart';
import '../net/map_names.dart';

/// 第 9 轮 W9-12：标原点时自动加的待命点（名字是 home）写「在原点（标原点时自动加的）」，不写 home。
/// 第 11 轮 W11-04：home 已登记在别的图上时站点起名 home-<图名>，也算。
bool autoHomeName(Object? name) => name == 'home' || RegExp(r'^home-[A-Za-z0-9._-]+$').hasMatch('$name');

String standbyName(Map p) => autoHomeName(p['name'])
    // 用户 11-26：原点和待命点分开（W13a，重标原点不挪它）—— 名字别说「在原点」
    ? tr('First standby point (where the origin was first marked)', '第一个待命点（第一次标原点的地方）')
    : '${p['name']}';

class SiteStandbyPage extends StatefulWidget {
  final SiteApi api;
  final String robotId;

  /// 这台狗能不能「在这儿设待命点」（代理报了 `mark_home.standby`）。
  final bool canMarkHere;
  const SiteStandbyPage({
    super.key,
    required this.api,
    required this.robotId,
    this.canMarkHere = false,
  });

  static const Key hereKey = Key('standby-here');
  static const Key nameKey = Key('standby-here-name');
  static const Key defaultKey = Key('standby-here-default');
  static const Key goKey = Key('standby-here-go');
  static const Key msgKey = Key('standby-msg');
  static const Key chargerKey = Key('standby-charger-here');

  @override
  State<SiteStandbyPage> createState() => _SiteStandbyPageState();
}

class _SiteStandbyPageState extends State<SiteStandbyPage> with NwAsk {
  List<Map<String, dynamic>> _points = const [];
  List<Map<String, dynamic>> _homes = const [];
  String _msg = '';
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final r = await widget.api.standbyPoints(widget.robotId);
      if (!mounted) return;
      setState(() {
        _points = (r['points'] as List? ?? const []).cast<Map<String, dynamic>>();
        _homes = (r['homes'] as List? ?? const []).cast<Map<String, dynamic>>();
        _loading = false;
      });
    } on SiteError catch (e) {
      if (mounted) {
        setState(() {
          _msg = e.toString();
          _loading = false;
        });
      }
    }
  }

  Future<void> _run(Future<Map<String, dynamic>> Function() f, String what) async {
    String msg;
    try {
      final r = await f();
      final ack = r['ack'];
      final res = ack is Map ? ack['result'] : null;
      msg = (res == null || res == 'accepted')
          ? tr('$what: done', '$what：完成')
          : tr('$what: ${ackReasonText('${ack['reason'] ?? res}')}',
              '$what：${ackReasonText('${ack['reason'] ?? res}')}');
    } on SiteError catch (e) {
      msg = e.status == 409
          ? tr('$what failed: ${ackReasonText(e.message.replaceFirst(RegExp(r'^机器人标记失败[:：]'), ''))}',
              '$what失败：${ackReasonText(e.message.replaceFirst(RegExp(r'^机器人标记失败[:：]'), ''))}')
          : tr('$what failed: $e', '$what失败：$e');
    } catch (e) {
      // 易用性 37 复测第六轮：超时、网断（不是站点回的错）原来页面上什么都不说
      msg = tr('$what: no answer from the site. Check the list, then try again',
          '$what：站点没有回应。先看看列表，再试一次');
    }
    if (!mounted) return;
    setState(() => _msg = msg);
    await _load();
  }

  Future<void> _setDefault(Map<String, dynamic> p) async {
    try {
      final why = await standbyDefaultBlocked(widget.api, widget.robotId, p);
      if (why != null) {
        if (mounted) setState(() => _msg = why);
        return;
      }
    } on SiteError catch (e) {
      if (mounted) setState(() => _msg = tr('Make default failed: $e', '设默认失败：$e'));
      return;
    }
    await _run(() => widget.api.setStandbyDefault(widget.robotId, p), tr('Make ${p['name']} default', '设 ${p['name']} 为默认'));
  }

  Future<void> _here() async {
    final name = TextEditingController();
    var isDefault = _points.isEmpty;
    // App V2：页内问，不弹窗
    final ok = await askYes(tr('Set standby point here', '在这儿设待命点'),
        body: tr(
            "Sets the robot's current position as a standby point (origin unchanged). Not possible if the position isn't set, the error is large, or a task is running.",
            '将机器人当前位置设为待命点（原点不变）。未设置位置、偏差过大或执行任务时无法设置。'),
        content: StatefulBuilder(
            builder: (c, set) => Column(mainAxisSize: MainAxisSize.min, children: [
                  TextField(
                    key: SiteStandbyPage.nameKey,
                    controller: name,
                    decoration: InputDecoration(labelText: tr('Name (letters, digits, . _ -)', '名字（字母、数字、. _ -）')),
                  ),
                  CheckboxListTile(
                    key: SiteStandbyPage.defaultKey,
                    contentPadding: EdgeInsets.zero,
                    value: isDefault,
                    onChanged: (v) => set(() => isDefault = v ?? false),
                    title: Text(tr('Make default (the robot returns here after a task)', '设为默认（任务结束后返回此处）')),
                  ),
                ])),
        ok: tr('Set', '设置'),
        okKey: SiteStandbyPage.goKey);
    final n = name.text.trim();
    if (ok != true || n.isEmpty) return;
    await _run(() => widget.api.standbyHere(widget.robotId, n, isDefault: isDefault),
        tr('Set standby point $n', '设待命点 $n'));
  }

  Future<void> _remove(String n) async {
    final ok = await askYes(tr('Delete standby point $n?', '删除待命点 $n？'),
        ok: tr('Delete', '删除'), okKey: Key('standby-remove-go-$n'), danger: true);
    if (ok) {
      await _run(() => widget.api.removeStandby(widget.robotId, n),
          tr('Delete standby point $n', '删除待命点 $n'));
    }
  }

  static String _xy(Map<String, dynamic> p) =>
      '${mapName(p['map_id'])}:${p['map_version']}  (${(p['x'] as num).toStringAsFixed(1)}, '
      '${(p['y'] as num).toStringAsFixed(1)})';

  /// W13：狗现在站的地方登记成充电桩对准点（领到桩前约 1.5 米、正对桩）。
  Future<void> _charger() async {
    final ok = await askYes(
        tr("Set the robot's current position as the dock alignment point?", '把机器人现在的位置设成充电桩对准点？'),
        body: tr(
            'Lead the robot to about 1.5 m in front of the dock, facing it. Below 30% battery it docks to charge automatically.',
            '请将机器人引导到充电桩正前方约 1.5 米处，朝向充电桩。电量低于 30% 时将自动回充。'),
        ok: tr('Set', '设置'),
        okKey: const Key('standby-charger-go'));
    if (!ok) return;
    String msg;
    try {
      final d = await widget.api.setChargerHere(widget.robotId);
      msg = tr(
          'Dock alignment point set (${(d['x'] as num).toStringAsFixed(1)}, ${(d['y'] as num).toStringAsFixed(1)})',
          '充电桩对准点已设置（${(d['x'] as num).toStringAsFixed(1)}, ${(d['y'] as num).toStringAsFixed(1)}）');
    } on SiteError catch (e) {
      msg = tr('Not set: $e', '设置失败：$e');
    }
    if (mounted) setState(() => _msg = msg);
  }

  @override
  Widget build(BuildContext context) {
    final c = Nw.of(context);
    final s = widget.api.session;
    final manage = s?.canManageMaps ?? false;
    final dispatch = s?.canDispatch ?? false;
    final head = NwText.titleSmall.copyWith(color: c.text, fontWeight: FontWeight.bold);
    final body = NwText.bodyMedium.copyWith(color: c.text);
    return Scaffold(
      appBar: AppBar(
        title: Text(tr('${widget.robotId} · Standby points and origin', '${widget.robotId} · 待命点与原点')),
        actions: barActions(context, [
          if (manage && widget.canMarkHere)
            BarAction(
                key: SiteStandbyPage.hereKey,
                onPressed: _here,
                label: tr('Set standby point here', '在这儿设待命点')),
          if (manage)
            BarAction(
                key: SiteStandbyPage.chargerKey,
                onPressed: _charger,
                label: tr('Set dock here', '在这儿设充电桩')),
        ]),
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : ListView(
              padding: const EdgeInsets.all(Nw.s16),
              children: [
                askStrip(margin: const EdgeInsets.only(bottom: Nw.s16)),
                if (_msg.isNotEmpty)
                  Padding(
                      padding: const EdgeInsets.only(bottom: Nw.s16),
                      child: Text(_msg, key: SiteStandbyPage.msgKey, style: body)),
                Text(
                  tr(
                      'Origin (safe return and charging; one per map; change it with '
                          '"Mark origin here" on the robot page)',
                      '原点（用于安全返航和回充；每张地图一个，在机器人页「在这儿标原点」修改）'),
                  style: head,
                ),
                const SizedBox(height: Nw.s8),
                NwCard(
                    child: Column(crossAxisAlignment: CrossAxisAlignment.start, mainAxisSize: MainAxisSize.min, children: [
                  if (_homes.isEmpty)
                    Text(tr('No origin marked yet', '尚未标原点'), style: body.copyWith(color: c.textSecondary)),
                  for (final h in _homes)
                    Text(
                      '${autoHomeName(h['name']) ? tr('Origin', '原点') : h['name']}  ${_xy(h)}',
                      key: Key('home-${h['map_id']}-${h['map_version']}'),
                      style: body,
                    ),
                ])),
                const SizedBox(height: Nw.s24),
                Text(
                    tr('Standby points (the robot returns to the default one after a task)',
                        '待命点（任务结束后返回默认待命点）'),
                    style: head),
                const SizedBox(height: Nw.s8),
                if (_points.isEmpty)
                  Text(tr('No standby points yet', '暂无待命点'), style: body.copyWith(color: c.textSecondary)),
                if (_points.isNotEmpty)
                  NwCard(
                      padding: EdgeInsets.zero,
                      child: Column(mainAxisSize: MainAxisSize.min, children: [
                        for (final p in _points)
                          ListTile(
                            key: Key('standby-${p['name']}'),
                            dense: true,
                            shape: Border(bottom: BorderSide(color: c.outline)),
                            title: Text(
                                '${standbyName(p)}${p['default'] == true ? tr(' (default)', '（默认）') : ''}'),
                            // 易用性 37 复测：按钮放在 trailing 把名字挤成一个字一行 —— 挪到名字下面
                            subtitle: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                              Text(_xy(p)),
                              Wrap(
                              spacing: 4,
                              children: [
                                if (dispatch)
                                  OutlinedButton(
                                    key: Key('standby-go-${p['name']}'),
                                    onPressed: () => _run(
                                      () => widget.api
                                          .returnToStandby(widget.robotId, name: '${p['name']}'),
                                      tr('Return to standby ${p['name']}', '回待命点 ${p['name']}'),
                                    ),
                                    child: Text(tr('Return here', '返回此处')),
                                  ),
                                if (manage && p['default'] != true)
                                  OutlinedButton(
                                    key: Key('standby-default-${p['name']}'),
                                    onPressed: () => _setDefault(p),
                                    child: Text(tr('Make default', '设默认')),
                                  ),
                                if (manage)
                                  IconButton(
                                    key: Key('standby-remove-${p['name']}'),
                                    tooltip: tr('Delete', '删除'),
                                    onPressed: () => _remove('${p['name']}'),
                                    icon: const Icon(Icons.delete_outline_rounded),
                                  ),
                              ],
                            ),
                            ]),
                          ),
                      ])),
              ],
            ),
    );
  }
}
