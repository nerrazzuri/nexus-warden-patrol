/// 1.1-4 远程喊话：按住说话（松开就发给机器人放）、听回话（机器人录几秒现场声音传回来）、最近的对讲。
///
/// 设计 docs/1.1-4-远程喊话-设计.md。录音是 AAC（m4a，16 kHz 单声道，一段最多 30 秒），整个传给站点；
/// 站点只留 24 小时。机器人报了 `deter.talk` 才有这一块；报了 `mic` 才有「听回话」。
library;

import 'dart:async';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:path_provider/path_provider.dart';
import 'package:record/record.dart';
import 'package:video_player/video_player.dart';

import '../l10n.dart';
import '../net/site_client.dart';
import 'nw/nw_theme.dart';

const int talkMaxSeconds = 30;
const int listenSeconds = 10;

/// 录音（测试换成假的）。
abstract class TalkRecorder {
  Future<bool> permitted();
  Future<void> start(String path);
  /// 停下，回录好的文件路径（没录成回 null）。
  Future<String?> stop();
  Future<void> dispose();
}

class _RecordRecorder implements TalkRecorder {
  final AudioRecorder _r = AudioRecorder();
  @override
  Future<bool> permitted() => _r.hasPermission();
  @override
  Future<void> start(String path) => _r.start(
      const RecordConfig(encoder: AudioEncoder.aacLc, bitRate: 48000, sampleRate: 16000, numChannels: 1),
      path: path);
  @override
  Future<String?> stop() => _r.stop();
  @override
  Future<void> dispose() => _r.dispose();
}

TalkRecorder Function() makeTalkRecorder = _RecordRecorder.new;

/// 录音临时放哪（测试换成临时目录）。
Future<Directory> Function() talkTempDir = getTemporaryDirectory;

/// 放一段录音（测试换成假的）。
Future<void> Function(Uint8List bytes, String id) playTalk = _play;

VideoPlayerController? _player;

Future<void> _play(Uint8List bytes, String id) async {
  final dir = await getTemporaryDirectory();
  final f = File('${dir.path}/talk-$id.audio');
  await f.writeAsBytes(bytes, flush: true);
  await _player?.dispose();
  final p = _player = VideoPlayerController.file(f);
  await p.initialize();
  await p.play();
}

class SiteTalk extends StatefulWidget {
  const SiteTalk({super.key, required this.api, required this.robotId, required this.listen});
  final SiteApi api;
  final String robotId;
  final bool listen;

  static const holdKey = Key('talk-hold');
  static const listenKey = Key('talk-listen');
  static const msgKey = Key('talk-msg');
  static Key rowKey(String id) => Key('talk-row-$id');

  @override
  State<SiteTalk> createState() => _SiteTalkState();
}

enum _Rec { idle, rec, send }

class _SiteTalkState extends State<SiteTalk> {
  late final TalkRecorder _rec = makeTalkRecorder();
  _Rec _state = _Rec.idle;
  DateTime? _t0;
  Timer? _limit, _tick, _poll;
  int _secs = 0;
  String _msg = '';
  bool _asking = false;
  List<Map<String, dynamic>> _rows = const [];

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  @override
  void dispose() {
    _limit?.cancel();
    _tick?.cancel();
    _poll?.cancel();
    unawaited(_rec.dispose());
    super.dispose();
  }

  Future<void> _load() async {
    try {
      final r = await widget.api.talks(widget.robotId);
      if (mounted) setState(() => _rows = r);
    } on SiteError {
      // 老站点没有对讲记录：不显示
    }
  }

  void _say(String s) {
    if (mounted) setState(() => _msg = s);
  }

  String _ackText(Map<String, dynamic> d, String ok) {
    final ack = d['ack'];
    final res = ack is Map ? '${ack['result']}' : 'accepted';
    if (res == 'accepted' || res == 'duplicate') return ok;
    return tr('Not played: ${ack is Map ? ack['reason'] ?? res : res}', '没放出来：${ack is Map ? ack['reason'] ?? res : res}');
  }

  Future<void> _start() async {
    if (_state != _Rec.idle) return;
    if (!await _rec.permitted()) {
      _say(tr('Microphone not allowed. Allow it in the phone settings.', '没有麦克风权限。请在手机设置里允许。'));
      return;
    }
    final dir = await talkTempDir();
    final path = '${dir.path}/talk-out-${DateTime.now().millisecondsSinceEpoch}.m4a';
    try {
      await _rec.start(path);
    } catch (e) {
      _say(tr('Cannot record: $e', '录不了音：$e'));
      return;
    }
    _t0 = DateTime.now();
    _limit = Timer(const Duration(seconds: talkMaxSeconds), () => unawaited(_finish()));
    _tick = Timer.periodic(const Duration(milliseconds: 250), (_) {
      if (mounted && _t0 != null) setState(() => _secs = DateTime.now().difference(_t0!).inSeconds);
    });
    if (mounted) {
      setState(() {
        _state = _Rec.rec;
        _secs = 0;
        _msg = '';
      });
    }
  }

  Future<void> _finish() async {
    if (_state != _Rec.rec) return;
    _limit?.cancel();
    _tick?.cancel();
    final ms = DateTime.now().difference(_t0 ?? DateTime.now()).inMilliseconds;
    setState(() => _state = _Rec.send);
    String? path;
    try {
      path = await _rec.stop();
    } catch (_) {
      path = null;
    }
    if (path == null || ms < 600) {
      if (mounted) setState(() => _state = _Rec.idle);
      _say(tr('Too short — hold the button while you speak.', '太短了：说话时一直按着。'));
      return;
    }
    try {
      final f = File(path);
      final bytes = f.readAsBytesSync(); // 最多 30 秒 AAC，几百 KB
      try {
        f.deleteSync();
      } on FileSystemException {
        // 删不掉留在临时目录里，系统会清
      }
      final d = await widget.api.talk(widget.robotId, bytes, 'audio/mp4');
      _say(_ackText(d, tr('${widget.robotId}: your message is playing.', '${widget.robotId}：正在放你说的话。')));
    } on SiteError catch (e) {
      _say(tr('Sending failed: $e', '发送失败：$e'));
    } catch (e) {
      _say(tr('Sending failed: $e', '发送失败：$e'));
    } finally {
      if (mounted) setState(() => _state = _Rec.idle);
      unawaited(_load());
    }
  }

  Future<void> _ask() async {
    setState(() => _asking = true);
    try {
      final d = await widget.api.listen(widget.robotId, seconds: listenSeconds);
      _say(_ackText(d, tr('${widget.robotId} is recording $listenSeconds seconds of sound for you.',
          '${widget.robotId} 正在录 $listenSeconds 秒现场声音。')));
      _poll?.cancel();
      var n = 0;
      _poll = Timer.periodic(const Duration(seconds: 2), (t) {
        n++;
        unawaited(_load());
        final waiting = _rows.any((r) => r['direction'] == 'in' && r['state'] == 'waiting');
        if (!waiting || n > (listenSeconds + 20) ~/ 2) t.cancel();
      });
    } on SiteError catch (e) {
      _say(tr('Failed: $e', '失败：$e'));
    } finally {
      if (mounted) setState(() => _asking = false);
      unawaited(_load());
    }
  }

  Future<void> _playRow(String id) async {
    try {
      await playTalk(await widget.api.talkAudio(id), id);
    } on SiteError catch (e) {
      _say(tr('Cannot play: $e', '放不了：$e'));
    } catch (e) {
      _say(tr('Cannot play: $e', '放不了：$e'));
    }
  }

  String _rowState(Map<String, dynamic> r) {
    final st = '${r['state']}';
    if (st == 'refused') return tr('Not played', '没放出来');
    if (r['direction'] == 'in') return st == 'recorded' ? tr('Reply recorded', '回话已录好') : tr('Waiting…', '等回话…');
    return st == 'fetched' ? tr('Played', '已放') : tr('Sent', '已发');
  }

  @override
  Widget build(BuildContext context) {
    final c = Nw.of(context);
    final rec = _state == _Rec.rec;
    final label = switch (_state) {
      _Rec.rec => tr('Recording $_secs s / $talkMaxSeconds s — release to send', '录音中 $_secs 秒 / $talkMaxSeconds 秒，松开就发'),
      _Rec.send => tr('Sending…', '正在发…'),
      _Rec.idle => tr('Hold to talk', '按住说话'),
    };
    final waiting = _rows.any((r) => r['direction'] == 'in' && r['state'] == 'waiting');
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      Listener(
        onPointerDown: (_) => unawaited(_start()),
        onPointerUp: (_) => unawaited(_finish()),
        onPointerCancel: (_) => unawaited(_finish()),
        child: Container(
          key: SiteTalk.holdKey,
          height: 56,
          alignment: Alignment.center,
          decoration: BoxDecoration(
              color: rec ? c.errorSoft : c.surface,
              border: Border.all(color: rec ? c.error : c.textMuted),
              borderRadius: BorderRadius.circular(2)),
          child: Row(mainAxisAlignment: MainAxisAlignment.center, children: [
            Icon(rec ? Icons.mic_rounded : Icons.mic_none_rounded, size: 20, color: rec ? c.error : c.text),
            const SizedBox(width: Nw.s8),
            Flexible(
                child: Text(label,
                    textAlign: TextAlign.center,
                    style: NwText.titleSmall.copyWith(color: rec ? c.error : c.text))),
          ]),
        ),
      ),
      if (widget.listen) ...[
        const SizedBox(height: Nw.s8),
        OutlinedButton.icon(
            key: SiteTalk.listenKey,
            style: OutlinedButton.styleFrom(
                minimumSize: const Size(48, 48),
                foregroundColor: c.text,
                side: BorderSide(color: c.textMuted),
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(2))),
            onPressed: _asking || waiting || _state != _Rec.idle ? null : () => unawaited(_ask()),
            icon: const Icon(Icons.hearing_rounded, size: 18),
            label: Text(waiting ? tr('Waiting for reply…', '等回话…') : tr('Listen $listenSeconds s', '听 $listenSeconds 秒'))),
      ],
      if (_msg.isNotEmpty)
        Padding(
            padding: const EdgeInsets.only(top: Nw.s8),
            child: Text(_msg, key: SiteTalk.msgKey, style: NwText.bodyMedium.copyWith(color: c.text))),
      for (final r in _rows.take(5))
        Padding(
          key: SiteTalk.rowKey('${r['id']}'),
          padding: const EdgeInsets.only(top: Nw.s4),
          child: Row(children: [
            Expanded(
                child: Text(
                    '${r['direction'] == 'out' ? r['account'] : widget.robotId} · '
                    '${TimeOfDay.fromDateTime(DateTime.fromMillisecondsSinceEpoch((r['created_ms'] as num?)?.toInt() ?? 0)).format(context)}'
                    ' · ${_rowState(r)}',
                    style: NwText.bodySmall.copyWith(color: c.textSecondary))),
            if (((r['bytes'] as num?) ?? 0) > 0 && (r['direction'] == 'out' || r['state'] == 'recorded'))
              IconButton(
                  tooltip: tr('Play recording', '播放录音'),
                  onPressed: () => unawaited(_playRow('${r['id']}')),
                  icon: const Icon(Icons.play_arrow_rounded)),
          ]),
        ),
      Padding(
          padding: const EdgeInsets.only(top: Nw.s4),
          child: Text(tr('Recordings are kept on the site for 24 hours.', '录音在站点只留 24 小时。'),
              style: NwText.bodySmall.copyWith(color: c.textSecondary))),
    ]);
  }
}
