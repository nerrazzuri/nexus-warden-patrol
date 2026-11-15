/// 上装（W21，决策 36）：警灯、警笛、聚光灯、喇叭。
///
/// 每一路「开」都带时长，到点狗上自己关（站点、手机断了也一样）；「关」随时能按。喇叭放录好的话术，狗上配了 TTS 的
/// 还能现打一段字。喇叭有优先级：事件派遣、驱离（W22）放的比手动的高，那时候手动的会回「忙」。
/// 只列狗报了接上的那几路（`capabilities.tasks.deter.outputs`）。保安、管理员能用。
///
/// W40（上装 V1.2）：狗报了 `spotlight_sides` 就多两行「左聚光灯」「右聚光灯」（能只开一边）；报了
/// `strobe_colors` 警灯那一行多一个颜色下拉框（开的时候带上）。
library;

import 'dart:async';

import 'package:flutter/material.dart';

import '../l10n.dart';
import '../net/site_client.dart';
import 'nw/nw_theme.dart';

class SiteDeterPage extends StatefulWidget {
  final SiteApi api;
  final String robotId;

  /// 狗报的 `capabilities.tasks.deter`：`outputs`、`clips`、`tts`、`max_s`。
  final Map<String, dynamic> caps;
  /// App V2：嵌在机器人控制页里（不带页头、不自己滚），分「云台与相机」「喊话」「警示」三块。
  final bool embedded;
  const SiteDeterPage({super.key, required this.api, required this.robotId, required this.caps, this.embedded = false});

  static const Key msgKey = Key('deter-msg');
  static const Key allOffKey = Key('deter-all-off');
  static Key langKey(String l) => Key('deter-lang-$l');
  static Key clipKey(String c) => Key('deter-clip-$c');

  @override
  State<SiteDeterPage> createState() => _SiteDeterPageState();
}

/// 话术名说人话（POC 11-05：竞品转接的 4 段英文）；别的原样。
String deterClipLabel(String c) => switch (c) {
      'blocked' => tr('Path blocked (EN)', '请让路（英文）'),
      'passing' => tr('Passing through (EN)', '巡逻经过（英文）'),
      'distance' => tr('Keep distance (EN)', '保持距离（英文）'),
      'restricted' => tr('Restricted area (EN)', '禁区警告（英文）'),
      _ => c,
    };

/// 每一路的名字、默认开多久（秒）。
Map<String, (String, double)> get deterOutputs => <String, (String, double)>{
      'strobe': (tr('Strobe', '警灯'), 60),
      'siren': (tr('Siren', '警笛'), 10),
      'spotlight': (tr('Spotlight', '聚光灯'), 120),
      'speaker': (tr('Speaker', '喇叭'), 30),
      'wiper': (tr('Wiper', '雨刷'), 10), // POC 11-06 竞品上装：刷可见光镜头
    };

/// App V2 机器人控制页的一块：标题、一句说明、内容；上面一道分隔线。
Widget nwRobotSection(NwColors c, String title, List<Widget> children, {String note = '', Key? key}) => Container(
    key: key,
    padding: const EdgeInsets.fromLTRB(Nw.s16, Nw.s16, Nw.s16, Nw.s16),
    decoration: BoxDecoration(border: Border(top: BorderSide(color: c.outline))),
    child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      Text(title, style: NwText.titleMedium.copyWith(color: c.text, fontWeight: FontWeight.w700)),
      if (note.isNotEmpty) ...[
        const SizedBox(height: Nw.s4),
        Text(note, style: NwText.bodySmall.copyWith(color: c.textSecondary)),
      ],
      const SizedBox(height: 12),
      ...children,
    ]));

/// 一排等宽的按钮（App V2 规矩）：每排最多 [per] 个，最后一排不够也一样宽。
Widget nwButtonRows(List<Widget> buttons, {int per = 3}) {
  final rows = <Widget>[];
  for (var i = 0; i < buttons.length; i += per) {
    final row = buttons.sublist(i, (i + per).clamp(0, buttons.length));
    rows.add(Padding(
        padding: EdgeInsets.only(top: i == 0 ? 0 : Nw.s8),
        child: Row(children: [
          for (final (j, b) in row.indexed) ...[
            if (j > 0) const SizedBox(width: Nw.s8),
            Expanded(child: b),
          ],
        ])));
  }
  return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: rows);
}

/// 控制页上的按钮：深色页上的描边 / 实心，最小 48 高，字 14。
Widget nwOpButton(NwColors c, Key key, String label, VoidCallback? on, {IconData? icon, bool primary = false}) {
  final shape = RoundedRectangleBorder(borderRadius: BorderRadius.circular(2));
  final child = Row(mainAxisAlignment: MainAxisAlignment.center, mainAxisSize: MainAxisSize.min, children: [
    if (icon != null) ...[Icon(icon, size: 18), const SizedBox(width: 6)],
    Flexible(child: Text(label, textAlign: TextAlign.center, maxLines: 2, overflow: TextOverflow.ellipsis)),
  ]);
  return primary
      ? FilledButton(
          key: key,
          style: FilledButton.styleFrom(
              minimumSize: const Size(48, 48),
              padding: const EdgeInsets.symmetric(horizontal: Nw.s8),
              textStyle: NwText.titleSmall,
              shape: shape),
          onPressed: on,
          child: child)
      : OutlinedButton(
          key: key,
          style: OutlinedButton.styleFrom(
              foregroundColor: c.text,
              side: BorderSide(color: c.textMuted),
              minimumSize: const Size(48, 48),
              padding: const EdgeInsets.symmetric(horizontal: Nw.s8),
              textStyle: NwText.titleSmall,
              shape: shape),
          onPressed: on,
          child: child);
}

/// POC 11-06 竞品云台：每按一下转多少度、角度上限（跟站点的 nexwar_contract.deter 一致）。
const double ptzPanStep = 15, ptzTiltStep = 10, ptzPanMax = 180, ptzTiltMax = 90;

/// 警灯颜色名说人话（狗的配置里起的名字；不认识的原样显示）。
String strobeColorText(String c) => switch (c) {
      'red' => tr('Red', '红'),
      'yellow' => tr('Yellow', '黄'),
      'green' => tr('Green', '绿'),
      'blue' => tr('Blue', '蓝'),
      'white' => tr('White', '白'),
      'purple' || 'magenta' => tr('Purple', '紫'),
      'cyan' => tr('Cyan', '青'),
      _ => c,
    };

/// 页面上的一行：哪一路、哪一边（只给聚光灯）、名字。
typedef _Row = ({String key, String output, String? side, String name});

/// 狗回的拒绝理由说人话。
String deterReasonText(String r) => switch (r) {
      'busy' => tr('The speaker is playing something more urgent (incident, deterrence). Wait for it to finish',
          '喇叭正在播放更紧急的内容（事件、驱离），请等待播放结束'),
      'unsupported' => tr('This device is not fitted on the robot', '机器人未安装此设备'),
      _ when r.startsWith('unsupported:') => tr('Not supported by the robot: ${r.substring(12).trim()}',
          '机器人不支持：${r.substring(12).trim()}'),
      _ when r.startsWith('device:') =>
        tr('Device failed: ${r.substring(7).trim()}', '设备执行失败：${r.substring(7).trim()}'),
      _ => ackReasonText(r),
    };

class _SiteDeterPageState extends State<SiteDeterPage> {
  String _msg = '';
  final TextEditingController _tts = TextEditingController();
  String _lang = appLang.value == AppLang.zh ? 'zh' : 'en';

  List<String> get _outputs => ((widget.caps['outputs'] as List?) ?? const []).map((e) => '$e').toList();
  List<String> get _clips => ((widget.caps['clips'] as List?) ?? const []).map((e) => '$e').toList();
  List<String> get _sides => ((widget.caps['spotlight_sides'] as List?) ?? const []).map((e) => '$e').toList();
  List<String> get _colors => ((widget.caps['strobe_colors'] as List?) ?? const []).map((e) => '$e').toList();
  String? _color;

  /// 云台：没有回读角度，按「上次按到哪」算（看见人自己转过去以后，先点回正再调）。
  double _pan = 0, _tilt = 0;

  Future<void> _turn(double dp, double dt) async {
    final center = dp == 0 && dt == 0;
    final pan = center ? 0.0 : (_pan + dp).clamp(-ptzPanMax, ptzPanMax).toDouble();
    final tilt = center ? 0.0 : (_tilt + dt).clamp(-ptzTiltMax, ptzTiltMax).toDouble();
    setState(() {
      _pan = pan;
      _tilt = tilt;
    });
    final what = tr('Camera head to pan ${pan.toStringAsFixed(0)}°, tilt ${tilt.toStringAsFixed(0)}°',
        '云台转到水平 ${pan.toStringAsFixed(0)}°、俯仰 ${tilt.toStringAsFixed(0)}°');
    String msg;
    try {
      final r = await widget.api.deter(widget.robotId, 'ptz', true, pan: pan, tilt: tilt);
      final ack = r['ack'];
      final res = ack is Map ? '${ack['result']}' : 'accepted';
      msg = res == 'accepted'
          ? tr('$what: done', '$what：完成')
          : tr('$what failed: ${deterReasonText(ack is Map ? '${ack['reason'] ?? res}' : res)}',
              '$what失败：${deterReasonText(ack is Map ? '${ack['reason'] ?? res}' : res)}');
    } on SiteError catch (e) {
      msg = tr('$what failed: $e', '$what失败：$e');
    }
    if (mounted) setState(() => _msg = msg);
  }

  /// 喇叭以外的每一行。聚光灯分左右的：「两边」一行，再加左、右各一行。
  List<_Row> get _rows => <_Row>[
        for (final o in _outputs.where((o) => o != 'speaker' && o != 'ptz')) ...[
          (key: o, output: o, side: null, name: deterOutputs[o]?.$1 ?? o),
          if (o == 'spotlight' && _sides.contains('left'))
            (key: 'spotlight-left', output: o, side: 'left', name: tr('Left spotlight', '左聚光灯')),
          if (o == 'spotlight' && _sides.contains('right'))
            (key: 'spotlight-right', output: o, side: 'right', name: tr('Right spotlight', '右聚光灯')),
        ],
      ];

  /// POC 11-05：回执收下了不等于放出来了 —— 机器人后来报没放出来，站点起一条 `deter_failed` 告警；
  /// 这里听事件流，是这台的就在面板上说。
  StreamSubscription<Map<String, dynamic>>? _events;

  void _listen() {
    _events = widget.api.events().listen((f) {
      final a = f['alert'];
      if (f['kind'] != 'alert' || a is! Map || a['kind'] != 'deter_failed' || a['robot'] != widget.robotId) {
        return;
      }
      if (a['resolved_ms'] != null || !mounted) return;
      final why = '${a['detail'] ?? ''}';
      setState(() => _msg = why.isEmpty
          ? tr('Announcement not played', '喊话没放出来')
          : tr('Announcement not played: $why', '喊话没放出来：$why'));
    }, onError: (Object _) {}, cancelOnError: true);
  }

  @override
  void initState() {
    super.initState();
    _listen();
    final def = '${widget.caps['strobe_default'] ?? ''}';
    _color = _colors.isEmpty ? null : (_colors.contains(def) ? def : _colors.first);
    if (_outputs.contains('speaker') && widget.caps['tts'] == true) unawaited(_loadPresets());
  }

  /// 机器人报了能念哪几种语言（`tts_langs`，竞品只会中文）；没报 = 不知道，不挡。
  bool _canSay(String? lang) {
    final l = widget.caps['tts_langs'];
    return l is! List || l.contains(lang);
  }

  static String _langName(String? l) => switch (l) {
        'zh' => tr('Chinese', '中文'),
        'en' => tr('English', '英文'),
        'ms' => tr('Malay', '马来文'),
        _ => l ?? '',
      };

  /// 常用喊话（第三档 #41）：站点那张表；老站点没有这个接口就不出这一行。
  List<Map<String, String>>? _presets;
  Future<void> _loadPresets() async {
    try {
      final p = await widget.api.voicePresets();
      if (mounted) setState(() => _presets = p);
    } on SiteError {
      // 老站点：没有常用喊话
    }
  }

  @override
  void dispose() {
    unawaited(_events?.cancel());
    _tts.dispose();
    super.dispose();
  }

  Future<void> _go(String output, bool on, {String? clip, String? side, String? name}) async {
    name ??= deterOutputs[output]?.$1 ?? output;
    final secs = deterOutputs[output]?.$2 ?? 10;
    final color = output == 'strobe' && on ? _color : null;
    final what = on
        ? tr('$name on for ${secs.toStringAsFixed(0)} s', '开启$name ${secs.toStringAsFixed(0)} 秒')
        : tr('$name off', '关$name');
    String msg;
    try {
      final r = await widget.api.deter(widget.robotId, output, on,
          maxS: on ? secs : null, clip: clip, side: side, color: color);
      final ack = r['ack'];
      final res = ack is Map ? '${ack['result']}' : 'accepted';
      if (res == 'accepted' && output == 'speaker' && on) {
        msg = tr('$what: started (if it does not play, it will say so here)', '$what：已开始（放不出来会在这里说）');
      } else if (res == 'accepted') {
        msg = tr('$what: done', '$what：完成');
      } else {
        final why = deterReasonText(ack is Map ? '${ack['reason'] ?? res}' : res);
        msg = tr('$what failed: $why', '$what失败：$why');
      }
    } on SiteError catch (e) {
      msg = tr('$what failed: $e', '$what失败：$e');
    }
    if (mounted) setState(() => _msg = msg);
  }

  /// 「全部关」：警灯、警笛、聚光灯、喇叭各发一次关（雨刷、云台不算）。
  Future<void> _allOff() async {
    final what = tr('All off', '全部关');
    final bad = <String>[];
    for (final o in _outputs.where((o) => o != 'ptz' && o != 'wiper')) {
      try {
        await widget.api.deter(widget.robotId, o, false);
      } on SiteError catch (e) {
        bad.add('${deterOutputs[o]?.$1 ?? o}: $e');
      }
    }
    if (mounted) setState(() => _msg = bad.isEmpty ? tr('$what: done', '$what：完成') : tr('$what failed: ${bad.join('; ')}', '$what失败：${bad.join('；')}'));
  }

  List<Widget> _sections(NwColors c) {
    final outs = _outputs;
    final tts = widget.caps['tts'] == true;
    Widget btn(Key k, String label, VoidCallback? on, {IconData? icon, bool primary = false}) =>
        nwOpButton(c, k, label, on, icon: icon, primary: primary);
    final ptz = outs.contains('ptz');
    final wiper = outs.contains('wiper');
    final rows = _rows.where((r) => r.output != 'wiper').toList();
    return [
      if (_msg.isNotEmpty)
        Container(
            margin: const EdgeInsets.fromLTRB(Nw.s16, Nw.s8, Nw.s16, Nw.s8),
            padding: const EdgeInsets.symmetric(horizontal: Nw.s16, vertical: Nw.s8),
            decoration: BoxDecoration(color: c.infoSoft, borderRadius: BorderRadius.circular(2)),
            child: Text(_msg, key: SiteDeterPage.msgKey, style: NwText.bodyMedium.copyWith(color: c.text))),
      if (outs.isEmpty)
        Padding(
            padding: const EdgeInsets.all(Nw.s16),
            child: Text(tr('No payload fitted on this robot', '此机器人未安装上装'), style: NwText.bodyLarge.copyWith(color: c.text))),
      if (ptz || wiper)
        nwRobotSection(c, tr('PTZ & camera', '云台与相机'), key: const Key('deter-ptz'), [
          Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
            if (ptz)
              SizedBox(
                  width: 3 * 48 + 2 * 6,
                  child: Column(children: [
                    for (final line in <List<(String, IconData, double, double)?>>[
                      [null, ('up', Icons.keyboard_arrow_up_rounded, 0, -ptzTiltStep), null],
                      [
                        ('left', Icons.keyboard_arrow_left_rounded, -ptzPanStep, 0),
                        ('center', Icons.home_outlined, 0, 0),
                        ('right', Icons.keyboard_arrow_right_rounded, ptzPanStep, 0),
                      ],
                      [null, ('down', Icons.keyboard_arrow_down_rounded, 0, ptzTiltStep), null],
                    ])
                      Padding(
                          padding: const EdgeInsets.only(bottom: 6),
                          child: Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
                            for (final k in line)
                              k == null
                                  ? const SizedBox(width: 48, height: 48)
                                  : SizedBox(
                                      width: 48,
                                      height: 48,
                                      child: OutlinedButton(
                                          key: Key('ptz-${k.$1}'),
                                          style: OutlinedButton.styleFrom(
                                              padding: EdgeInsets.zero,
                                              foregroundColor: c.text,
                                              side: BorderSide(color: c.textMuted),
                                              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(2))),
                                          onPressed: () => _turn(k.$3, k.$4),
                                          child: Icon(k.$2,
                                              semanticLabel: switch (k.$1) {
                                                'up' => tr('Up', '向上'),
                                                'down' => tr('Down', '向下'),
                                                'left' => tr('Left', '向左'),
                                                'right' => tr('Right', '向右'),
                                                _ => tr('Center', '回正'),
                                              }))),
                          ])),
                  ])),
            if (ptz && wiper) const SizedBox(width: Nw.s16),
            if (wiper)
              Expanded(
                  child: btn(const Key('deter-on-wiper'), tr('Wiper', '雨刷'), () => _go('wiper', true))),
          ]),
        ]),
      if (outs.contains('speaker'))
        nwRobotSection(c, tr('Announce', '喊话'), key: const Key('deter-speaker'),
            note: tts ? tr('Saved messages are site-wide; typed messages use the selected language', '常用话全站通用；现打的字按选的语言念') : '', [
          if (tts) ...[
            SegmentedButton<String>(
                showSelectedIcon: false,
                segments: [
                  for (final l in const ['en', 'zh', 'ms'])
                    ButtonSegment<String>(
                        value: l, enabled: _canSay(l), label: Text(_langName(l), key: SiteDeterPage.langKey(l))),
                ],
                selected: {_lang},
                onSelectionChanged: (v) => setState(() => _lang = v.first)),
            const SizedBox(height: Nw.s8),
          ],
          // 录好的话术（竞品转接的几段、没配 TTS 的机器人）：点了就放
          if (_clips.isNotEmpty) ...[
            nwButtonRows([
              for (final k in _clips)
                btn(SiteDeterPage.clipKey(k), deterClipLabel(k), () => _go('speaker', true, clip: k)),
            ]),
            const SizedBox(height: Nw.s8),
          ],
          if (tts && (_presets?.isNotEmpty ?? false)) ...[
            nwButtonRows([
              for (final (i, p) in _presets!.indexed)
                btn(Key('deter-preset-$i'), p['text'] ?? '',
                    _canSay(p['lang']) ? () => _go('speaker', true, clip: 'tts:${p['lang']}:${p['text']}') : null),
            ]),
            for (final l in {for (final p in _presets!) if (!_canSay(p['lang'])) p['lang']})
              Padding(
                  padding: const EdgeInsets.only(top: Nw.s4),
                  child: Text(
                      tr('${widget.robotId} cannot speak ${_langName(l)} (not set up on it)',
                          '这台机器人念不了${_langName(l)}（${widget.robotId} 上没配）'),
                      style: NwText.bodySmall.copyWith(color: c.textSecondary))),
            const SizedBox(height: Nw.s8),
          ],
          if (tts) ...[
            Row(children: [
              Expanded(
                  child: TextField(
                      key: const Key('deter-tts'),
                      controller: _tts,
                      maxLength: 300,
                      decoration: InputDecoration(
                          hintText: tr('Type a message…', '输入要喊的话…'), counterText: '', border: const OutlineInputBorder()))),
              const SizedBox(width: Nw.s8),
              SizedBox(
                  width: 96,
                  child: btn(const Key('deter-say'), tr('Announce', '喊话'), _canSay(_lang)
                      ? () {
                          final t = _tts.text.trim();
                          if (t.isEmpty) return;
                          _go('speaker', true, clip: 'tts:$_lang:$t');
                        }
                      : null,
                      primary: true)),
            ]),
            const SizedBox(height: Nw.s8),
          ],
          if (_clips.isEmpty && !tts)
            Padding(
                padding: const EdgeInsets.only(bottom: Nw.s8),
                child: Text(tr('No recorded clips on the robot', '机器人上没有预录话术'),
                    style: NwText.bodyMedium.copyWith(color: c.textSecondary))),
          btn(const Key('deter-off-speaker'), tr('Stop announcement', '停止喊话'), () => _go('speaker', false)),
        ]),
      if (rows.isNotEmpty)
        nwRobotSection(c, tr('Deterrence', '警示'), key: const Key('deter-outputs'),
            note: tr('Each output runs for a set time and turns off automatically', '每一路开一段时间后自动关'), [
          if (_colors.isNotEmpty)
            Row(children: [
              Text(tr('Strobe colour', '警灯颜色'), style: NwText.bodyMedium.copyWith(color: c.textSecondary)),
              const SizedBox(width: Nw.s8),
              DropdownButton<String>(
                key: const Key('deter-color'),
                value: _color,
                items: [for (final k in _colors) DropdownMenuItem(value: k, child: Text(strobeColorText(k)))],
                onChanged: (v) => setState(() => _color = v ?? _color),
              ),
            ]),
          nwButtonRows([
            for (final r in rows)
              btn(Key('deter-on-${r.key}'),
                  r.side == null && r.output == 'spotlight' && _sides.isNotEmpty
                      ? tr('Both spotlights ${deterOutputs['spotlight']!.$2.toStringAsFixed(0)} s',
                          '双侧聚光灯 ${deterOutputs['spotlight']!.$2.toStringAsFixed(0)} 秒')
                      : tr('${r.name} ${deterOutputs[r.output]?.$2.toStringAsFixed(0) ?? ''} s',
                          '${r.name} ${deterOutputs[r.output]?.$2.toStringAsFixed(0) ?? ''} 秒'),
                  () => _go(r.output, true, side: r.side, name: r.name),
                  icon: switch (r.output) {
                    'strobe' => Icons.lightbulb_outline_rounded,
                    'siren' => Icons.notifications_none_rounded,
                    _ => null,
                  }),
            btn(SiteDeterPage.allOffKey, tr('All off', '全部关'), () => unawaited(_allOff())),
          ]),
        ]),
    ];
  }

  @override
  Widget build(BuildContext context) {
    final c = Nw.of(context);
    final parts = _sections(c);
    if (widget.embedded) return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: parts);
    return Scaffold(
      appBar: AppBar(title: Text(tr('${widget.robotId} · Payload', '${widget.robotId} · 上装'))),
      body: ListView(children: parts),
    );
  }
}
