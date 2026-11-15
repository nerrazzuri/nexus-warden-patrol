/// 连续录像（W18，决策 31、32）：一只狗一分钟一段，按时间往前翻；点一段下载下来放。
///
/// 录像在站点上留 30 天；值班的人、管理员能把一段标成「留着」（过了 30 天也不删）。下载走 app 自己那条
/// 钉证书的连接（系统播放器不认站点的自签证书），下到 app 的临时目录再放：手机、Mac 在 app 里放，Linux、
/// Windows 桌面交给系统播放器。时刻是**狗的钟**（狗的钟不准站点会报告警）。
library;

import 'dart:async';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:path_provider/path_provider.dart';
import 'package:video_player/video_player.dart';

import '../l10n.dart';
import '../net/site_client.dart';
import 'nw/nw_ask.dart';
import 'nw/nw_theme.dart';
import 'nw/nw_widgets.dart';

/// 放一段录像。测试换成记下来的。
abstract class ClipPlayer {
  Future<void> play(BuildContext context, Uint8List bytes, String title);
}

class DefaultClipPlayer implements ClipPlayer {
  const DefaultClipPlayer();

  @override
  Future<void> play(BuildContext context, Uint8List bytes, String title) async {
    final dir = await getTemporaryDirectory();
    final f = File('${dir.path}/nexwar_clip.mp4');
    await f.writeAsBytes(bytes, flush: true);
    if (Platform.isLinux || Platform.isWindows) {
      // video_player 没有 Linux、Windows 的实现：交给系统播放器
      await Process.start(Platform.isLinux ? 'xdg-open' : 'cmd', Platform.isLinux ? [f.path] : ['/c', 'start', '', f.path],
          mode: ProcessStartMode.detached);
      return;
    }
    if (!context.mounted) return;
    await Navigator.push(context, MaterialPageRoute<void>(builder: (_) => _ClipPage(file: f, title: title)));
  }
}

class _ClipPage extends StatefulWidget {
  final File file;
  final String title;
  const _ClipPage({required this.file, required this.title});

  @override
  State<_ClipPage> createState() => _ClipPageState();
}

class _ClipPageState extends State<_ClipPage> {
  late final VideoPlayerController _c = VideoPlayerController.file(widget.file);
  String? _error;

  @override
  void initState() {
    super.initState();
    _c.initialize().then((_) {
      if (mounted) {
        setState(() {});
        _c.play();
      }
    }, onError: (Object e) {
      if (mounted) setState(() => _error = tr("Can't play: $e", '无法播放：$e'));
    });
  }

  @override
  void dispose() {
    _c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: Text(widget.title)),
        body: Center(
          child: _error != null
              ? Text(_error!)
              : !_c.value.isInitialized
                  ? const CircularProgressIndicator()
                  : GestureDetector(
                      onTap: () => setState(() => _c.value.isPlaying ? _c.pause() : _c.play()),
                      child: AspectRatio(aspectRatio: _c.value.aspectRatio, child: VideoPlayer(_c))),
        ),
      );
}

/// 时刻（毫秒）→ 本机时间 `MM-dd HH:mm:ss`。
String clipTime(int ms) {
  final t = DateTime.fromMillisecondsSinceEpoch(ms);
  String two(int v) => v.toString().padLeft(2, '0');
  return '${two(t.month)}-${two(t.day)} ${two(t.hour)}:${two(t.minute)}:${two(t.second)}';
}

class SiteRecordingsPage extends StatefulWidget {
  final SiteApi api;
  final String robotId;
  /// 从告警现场进来（W17 的现场页）：看这一刻前后各几分钟。不给就看最近的。
  final int? aroundMs;
  final ClipPlayer player;

  /// 站点上的几台（App V2 稿 S-video：顶上一排切机器人）；只有一台就不摆。
  final List<String> robots;
  const SiteRecordingsPage(
      {super.key,
      required this.api,
      required this.robotId,
      this.aroundMs,
      this.robots = const <String>[],
      this.player = const DefaultClipPlayer()});

  static Key robotKey(String id) => Key('rec-robot-$id');
  static const Key latestKey = Key('rec-latest');

  static const Key olderKey = Key('rec-older');
  static const Key newerKey = Key('rec-newer');
  static const Key msgKey = Key('rec-msg');
  static Key clipKey(int id) => Key('rec-$id');
  static Key keepKey(int id) => Key('rec-keep-$id');
  static Key cameraKey(String c) => Key('rec-cam-$c');

  /// 一屏看多长（分钟）。
  static const int windowMin = 30;
  static const Key dataOkKey = Key('rec-data-ok');

  @override
  State<SiteRecordingsPage> createState() => _SiteRecordingsPageState();
}

class _SiteRecordingsPageState extends State<SiteRecordingsPage> with NwAsk {
  late String _robotId = widget.robotId;
  List<Map<String, dynamic>> _rows = const [];

  /// 第几次读录像列表：晚回来的旧一次不覆盖新的（外审 App-V2-1 #8）。
  int _gen = 0;
  String? _camera;
  String _msg = '';
  bool _loading = true;
  int? _busyId;
  /// 这一屏的窗口：[_until - windowMin, _until]；null = 最新的。
  int? _until;
  /// 这只狗有哪几路（W40：装了热像的多一路）。读单狗视图；读不到就是前后两路。
  List<String> _cams = const <String>['front', 'back'];

  @override
  void initState() {
    super.initState();
    final a = widget.aroundMs;
    if (a != null) _until = a + SiteRecordingsPage.windowMin * 60000 ~/ 2;
    unawaited(_load());
    unawaited(_loadCams());
  }

  Future<void> _loadCams() async {
    final id = _robotId;
    try {
      final cams = robotCameras(await widget.api.robot(id));
      if (mounted && id == _robotId && cams.join(',') != _cams.join(',')) setState(() => _cams = cams);
    } on Object {
      // 读不到：照前后两路
    }
  }

  Future<void> _load() async {
    final gen = ++_gen;
    setState(() => _loading = true);
    try {
      final until = _until;
      final rows = await widget.api.recordings(
          robotId: _robotId,
          camera: _camera,
          until: until,
          since: until == null ? null : until - SiteRecordingsPage.windowMin * 60000,
          limit: until == null ? 60 : null);
      if (!mounted || gen != _gen) return;
      setState(() {
        _rows = rows;
        _loading = false;
        _msg = '';
      });
    } on SiteError catch (e) {
      if (mounted && gen == _gen) {
        setState(() {
          _loading = false;
          _msg = e.status == 404
              ? tr('Recording is not enabled on this site', '此站点未启用录像')
              : tr("Can't load recordings: $e", '无法加载录像：$e');
        });
      }
    }
  }

  void _shift(int minutes) {
    final base = _until ??
        (_rows.isNotEmpty ? (_rows.first['start_ms'] as num).toInt() + 60000 : DateTime.now().millisecondsSinceEpoch);
    _until = base + minutes * 60000;
    unawaited(_load());
  }

  bool _dataOk = false;

  Future<void> _play(Map<String, dynamic> r) async {
    final id = (r['id'] as num).toInt();
    final mb = ((r['bytes'] as num? ?? 0) / 1048576).toStringAsFixed(1);
    // M34：一段好几 MB，用手机流量看先说一声（这一页问一次；就地问，不弹窗）
    if (!_dataOk && (r['bytes'] as num? ?? 0) > 2 * 1048576) {
      // 外审 App-V2-1 #9：页内确认条（滚到看得见）；问着的时候换了机器人就作废
      final robot = _robotId;
      final ok = await askYes(tr('Play on mobile data?', '用手机流量播放？'),
          body: tr('Each clip is about $mb MB. On mobile data that is used per minute of video.',
              '每段约 $mb MB，用手机流量看每看一分钟就用这么多。'),
          ok: tr('Play', '播放'),
          okKey: SiteRecordingsPage.dataOkKey);
      if (!ok || !mounted || robot != _robotId) return;
      _dataOk = true;
    }
    setState(() {
      _busyId = id;
      _msg = tr('Downloading $mb MB…', '下载中（$mb MB）…');
    });
    try {
      final bytes = await widget.api.recordingBytes(id);
      if (!mounted) return;
      setState(() => _msg = '');
      await widget.player.play(context, bytes, '${cameraName('${r['camera']}')} · ${clipTime((r['start_ms'] as num).toInt())}');
    } on SiteError catch (e) {
      if (mounted) setState(() => _msg = tr("Can't download: $e", '下载失败：$e'));
    } on Exception catch (e) {
      if (mounted) setState(() => _msg = tr("Can't play: $e", '无法播放：$e'));
    } finally {
      if (mounted) setState(() => _busyId = null);
    }
  }

  Future<void> _keep(Map<String, dynamic> r) async {
    final id = (r['id'] as num).toInt();
    final want = r['keep'] != 1;
    try {
      await widget.api.setRecordingKeep(id, want);
      await _load();
      if (mounted) {
        setState(() => _msg = want
            ? tr('Marked to keep: not deleted after 30 days', '已标记保留：超过 30 天也不删除')
            : tr('No longer kept: deleted after 30 days as usual', '已取消保留：30 天后正常删除'));
      }
    } on SiteError catch (e) {
      if (mounted) setState(() => _msg = tr("Couldn't change the keep mark: $e", '标记失败：$e'));
    }
  }

  void _pickRobot(String id) {
    if (id == _robotId) return;
    setState(() {
      _robotId = id;
      _camera = null;
      _rows = const [];
      _cams = const <String>['front', 'back'];
      if (asking) askCancel();
    });
    unawaited(_load());
    unawaited(_loadCams());
  }

  static String _hm(int ms) {
    final t = DateTime.fromMillisecondsSinceEpoch(ms);
    String two(int v) => v.toString().padLeft(2, '0');
    return '${two(t.hour)}:${two(t.minute)}';
  }

  /// 这一屏是哪一段时间（时间轴两头）。
  (int, int) _window() {
    final until = _until ??
        (_rows.isNotEmpty ? (_rows.first['start_ms'] as num).toInt() + 60000 : DateTime.now().millisecondsSinceEpoch);
    return (until - SiteRecordingsPage.windowMin * 60000, until);
  }

  @override
  Widget build(BuildContext context) {
    final c = Nw.of(context);
    final canKeep = widget.api.session?.canReview ?? false; // 站点按 review 查（W20：经理能确认告警，但不能标留着）
    final around = widget.aroundMs;
    final shape = RoundedRectangleBorder(borderRadius: BorderRadius.circular(2));
    final out = OutlinedButton.styleFrom(
        minimumSize: const Size(48, 44), shape: shape, padding: const EdgeInsets.symmetric(horizontal: Nw.s8));
    final sub = NwText.bodySmall.copyWith(color: c.textSecondary);
    final (from, to) = _window();
    // App V2 稿 S-video：切机器人、相机；时间轴；一分钟一段一行；底下「← 30 分钟 | 30 分钟 →」
    return Scaffold(
      backgroundColor: c.bg,
      appBar: AppBar(
          title: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(widget.robots.length > 1 ? tr('Recordings', '录像') : tr('$_robotId · Recordings', '$_robotId · 录像')),
        Text(tr('One-minute segments · tap to play', '一分钟一段 · 点一段播放'), style: sub),
      ])),
      body: ListView(padding: const EdgeInsets.only(bottom: Nw.s24), children: [
        askStrip(),
        Container(
            color: c.surface,
            padding: const EdgeInsets.all(Nw.s16),
            child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
              if (widget.robots.length > 1) ...[
                SegmentedButton<String>(
                    showSelectedIcon: false,
                    style: SegmentedButton.styleFrom(
                        shape: shape, selectedBackgroundColor: c.primary, selectedForegroundColor: c.onPrimary),
                    segments: [
                      for (final r in widget.robots)
                        ButtonSegment(value: r, label: Text(r, key: SiteRecordingsPage.robotKey(r), overflow: TextOverflow.ellipsis)),
                    ],
                    selected: {_robotId},
                    onSelectionChanged: (v) => _pickRobot(v.first)),
                const SizedBox(height: Nw.s8),
              ],
              // 按相机筛：全部 / 前 / 后（/ 热像）
              NwSegment<String>(
                  values: <String>['all', ..._cams],
                  selected: _camera ?? 'all',
                  keyOf: SiteRecordingsPage.cameraKey,
                  labelOf: (v) => v == 'all' ? tr('All', '全部') : cameraName(v),
                  onChanged: (v) {
                    _camera = v == 'all' ? null : v;
                    unawaited(_load());
                  }),
              if (around != null) ...[
                const SizedBox(height: Nw.s8),
                Text(
                    tr('Alarm time: ${clipTime(around)} (times are by the robot clock)',
                        '报警时刻：${clipTime(around)}（按机器人时钟）'),
                    style: NwText.bodyMedium.copyWith(color: c.text)),
              ],
              const SizedBox(height: Nw.s16),
              // 时间轴：这半小时哪几分钟有录像（蓝），报警那一刻（红）
              Text('${_hm(from)} – ${_hm(to)}', style: NwText.labelMedium.copyWith(color: c.textSecondary, fontWeight: FontWeight.w700)),
              const SizedBox(height: Nw.s4),
              SizedBox(
                  height: 28,
                  child: CustomPaint(
                      painter: _Timeline(
                          from: from,
                          to: to,
                          clips: [for (final r in _rows) (r['start_ms'] as num).toInt()],
                          mark: around,
                          bg: c.bg,
                          fill: c.primary,
                          markColor: c.error))),
              const SizedBox(height: Nw.s4),
              Row(children: [
                Text(_hm(from), style: sub),
                const Spacer(),
                Text(_hm((from + to) ~/ 2), style: sub),
                const Spacer(),
                Text(_hm(to), style: sub),
              ]),
            ])),
        if (_msg.isNotEmpty)
          Padding(
              padding: const EdgeInsets.fromLTRB(Nw.s16, Nw.s8, Nw.s16, 0),
              child: Text(_msg, key: SiteRecordingsPage.msgKey, style: NwText.bodyMedium.copyWith(color: c.text))),
        if (_loading) const Padding(padding: EdgeInsets.all(16), child: Center(child: CircularProgressIndicator())),
        if (!_loading && _rows.isEmpty && _msg.isEmpty)
          Padding(
              padding: const EdgeInsets.all(Nw.s16),
              child: Text(
                  tr(
                      'No recordings in this period (recording is off on the robot, not uploaded yet, or deleted after 30 days)',
                      '此时段没有录像（机器人未开录像、尚未上传，或已超过 30 天删除）'),
                  style: NwText.bodyMedium.copyWith(color: c.textSecondary))),
        const SizedBox(height: Nw.s8),
        // 一段一行；盖住告警那一刻的那一段写「报警」、底色标出来
        for (final r in _rows) _row(c, r, around, canKeep),
        Padding(
            padding: const EdgeInsets.fromLTRB(Nw.s16, Nw.s16, Nw.s16, 0),
            child: Row(children: [
              Expanded(
                  child: OutlinedButton(
                      key: SiteRecordingsPage.olderKey,
                      style: out,
                      onPressed: () => _shift(-SiteRecordingsPage.windowMin),
                      // 手机 App 测试 M34：说一次翻多久
                      child: Text(tr('← 30 min', '← 早 30 分钟')))),
              const SizedBox(width: Nw.s8),
              Expanded(
                  child: OutlinedButton(
                      key: SiteRecordingsPage.newerKey,
                      style: out,
                      onPressed: () => _shift(SiteRecordingsPage.windowMin),
                      child: Text(tr('30 min →', '晚 30 分钟 →')))),
            ])),
        Padding(
            padding: const EdgeInsets.all(Nw.s16),
            child: Text(
                tr('Recordings are kept on the site for 30 days; segments marked Kept are not deleted. Recordings from unbound robots remain available here.',
                    '录像在站点上留 30 天；标了「保留」的不删。解绑了的机器人的录像也还在这里能看。'),
                style: sub)),
      ]),
    );
  }

  Widget _row(NwColors c, Map<String, dynamic> r, int? around, bool canKeep) {
    final id = (r['id'] as num).toInt();
    final start = (r['start_ms'] as num).toInt();
    final atAlarm = around != null && start <= around && around < start + 60000;
    final kept = r['keep'] == 1;
    return Material(
        color: atAlarm ? c.infoSoft : c.surface,
        child: InkWell(
            key: SiteRecordingsPage.clipKey(id),
            onTap: _busyId == null ? () => _play(r) : null,
            child: Container(
                padding: const EdgeInsets.symmetric(horizontal: Nw.s16, vertical: 8),
                decoration: BoxDecoration(border: Border(bottom: BorderSide(color: c.outline))),
                child: Row(children: [
                  Container(
                      width: 64,
                      height: 40,
                      color: Colors.black,
                      alignment: Alignment.center,
                      child: _busyId == id
                          ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2))
                          : const Icon(Icons.play_arrow_rounded, color: Colors.white70)),
                  const SizedBox(width: Nw.s16),
                  Expanded(
                      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Text('${_hm(start)} – ${_hm(start + 60000)}',
                        style: NwText.titleSmall.copyWith(color: c.text, fontWeight: FontWeight.w700)),
                    Text(
                        [
                          '$_robotId ${cameraName('${r['camera']}')}',
                          '${((r['bytes'] as num) / 1048576).toStringAsFixed(1)} MB',
                          if (atAlarm) tr('Alarm', '报警'),
                        ].join(' · '),
                        style: NwText.bodySmall.copyWith(color: atAlarm ? c.error : c.textSecondary)),
                  ])),
                  if (canKeep)
                    OutlinedButton(
                        key: SiteRecordingsPage.keepKey(id),
                        style: OutlinedButton.styleFrom(
                            minimumSize: const Size(48, 36),
                            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(2)),
                            backgroundColor: kept ? c.surfaceVariant : null,
                            padding: const EdgeInsets.symmetric(horizontal: Nw.s8)),
                        onPressed: () => _keep(r),
                        child: Text(kept ? tr('Kept', '已保留') : tr('Keep', '保留')))
                  else if (kept)
                    Container(
                        padding: const EdgeInsets.symmetric(horizontal: Nw.s8, vertical: 4),
                        color: c.surfaceVariant,
                        child: Text(tr('Kept', '已保留'), style: NwText.labelSmall.copyWith(color: c.text))),
                ]))));
  }
}

/// 时间轴：底色一条；有录像的那几分钟画蓝；报警那一刻一道红。
class _Timeline extends CustomPainter {
  final int from, to;
  final List<int> clips;
  final int? mark;
  final Color bg, fill, markColor;
  _Timeline(
      {required this.from,
      required this.to,
      required this.clips,
      required this.mark,
      required this.bg,
      required this.fill,
      required this.markColor});

  @override
  void paint(Canvas canvas, Size size) {
    canvas.drawRect(Offset.zero & size, Paint()..color = bg);
    final span = (to - from).toDouble();
    if (span <= 0) return;
    double x(int ms) => ((ms - from) / span * size.width).clamp(0.0, size.width);
    final blue = Paint()..color = fill.withValues(alpha: 0.6);
    for (final s in clips) {
      canvas.drawRect(Rect.fromLTRB(x(s), size.height - 8, x(s + 60000), size.height), blue);
    }
    final m = mark;
    if (m != null && m >= from && m <= to) {
      canvas.drawRect(Rect.fromLTWH(x(m) - 4, 0, 8, size.height), Paint()..color = markColor);
    }
  }

  @override
  bool shouldRepaint(_Timeline o) =>
      o.from != from || o.to != to || o.mark != mark || o.clips.length != clips.length || o.fill != fill;
}
