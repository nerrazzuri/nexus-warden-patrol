/// 上传日志（日志设计 第 6 条，用户 11-10）：谁都能传，不要权限；登录页上也有（登不进去的时候最需要）。
///
/// 写一句出了什么事、选是哪台机器人（可不选），按「上传」：App 的日志连同手机型号、App 版本打包传给站点，
/// 站点开一张问题单、回一个编号（`NW-1110-7F3A`）。把编号报给工程师，工程师按编号直接取整包
/// （站点那段时间的日志、机器人的日志和轨迹都在里面），不用管理员转。
///
/// 临时方案（用户 11-10，公司收日志的服务器放第二版）：主按钮「发给工程师（微信 / WhatsApp）」——
/// 先传站点开单，再用手机的分享面板发出去：登录着传的发整包，没登录的、连不上站点的发 App 日志。
library;


import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../l10n.dart';
import '../net/app_log.dart';
import '../net/site_client.dart';
import 'nw/nw_p1_entry.dart';
import 'nw/nw_theme.dart';
import 'nw/nw_widgets.dart';

typedef ProblemSharer = Future<bool> Function(String name, Uint8List bytes);

class ProblemReportPage extends StatefulWidget {
  /// 站点（登录着的、或者登录页上还没登的）；`null` = 连站点都没有，只能分享 App 日志。
  final SiteApi? api;

  /// 可以选的机器人（登录着才有）。
  final List<String> robots;
  final ProblemSharer share;
  final AppLog log;
  final DateTime Function() now;
  ProblemReportPage(
      {super.key,
      required this.api,
      this.robots = const <String>[],
      required this.share,
      AppLog? log,
      this.now = DateTime.now})
      : log = log ?? AppLog.instance;

  static const Key noteKey = Key('problem-note');
  static const Key robotKey = Key('problem-robot');
  static const Key sendKey = Key('problem-send');
  static const Key engineerKey = Key('problem-engineer');
  static const Key codeKey = Key('problem-code');
  static const Key shareBundleKey = Key('problem-share-bundle');
  static const Key shareAppKey = Key('problem-share-app');
  static const Key msgKey = Key('problem-msg');
  static const Key otherKey = Key('problem-other');

  @override
  State<ProblemReportPage> createState() => _ProblemReportPageState();
}

class _ProblemReportPageState extends State<ProblemReportPage> {
  final _note = TextEditingController();
  String _robot = '';
  bool _busy = false;
  String? _code;
  String? _token;
  String? _msg;
  bool _msgBad = false;

  @override
  void dispose() {
    _note.dispose();
    super.dispose();
  }

  String _header() => [
        'Nexus Warden App $appVersion+$appBuild',
        'device: ${deviceSummary()}',
        'time: ${widget.now().toIso8601String()}',
        if (_robot.isNotEmpty) 'robot: $_robot',
        'note: ${_note.text.trim()}',
      ].join('\n');

  String _stamp() {
    final t = widget.now();
    String two(int n) => n.toString().padLeft(2, '0');
    return '${t.year}${two(t.month)}${two(t.day)}-${two(t.hour)}${two(t.minute)}';
  }

  void _say(String s, {bool bad = false}) {
    if (mounted) {
      setState(() {
        _msg = s;
        _msgBad = bad;
      });
    }
  }

  /// 临时方案（用户 11-10）：主按钮「发给工程师」—— 先传站点开单（传得上的话），再用手机的分享面板
  /// 发微信 / WhatsApp：登录着传的发整包，别的发 App 日志。
  Future<void> _sendToEngineer() async {
    if (_busy) return;
    var uploaded = _code != null;
    if (!uploaded && widget.api != null) uploaded = await _send(quiet: true);
    if (_token != null) {
      await _shareBundle();
    } else {
      await _shareApp(note: uploaded
          ? null
          : tr("Couldn't reach the site; sent the app log only.", '没连上站点，只发了 App 日志。'));
    }
  }

  Future<bool> _send({bool quiet = false}) async {
    final api = widget.api;
    if (api == null || _busy) return false;
    setState(() {
      _busy = true;
      _msg = null;
    });
    widget.log.line('I', 'upload problem report robot=${_robot.isEmpty ? '-' : _robot}');
    try {
      final d = await api.uploadProblem(widget.log.pack(header: _header()),
          note: _note.text.trim(), robot: _robot, device: deviceSummary(), app: '$appVersion+$appBuild');
      if (mounted) {
        setState(() {
          _code = d['code']?.toString();
          _token = d['token']?.toString();
        });
      }
      return true;
    } on SiteError catch (e) {
      if (!quiet) {
        _say(tr('Upload failed: ${e.message}. Use "Send to engineer" to send the app log directly.',
            '上传失败：${e.message}。可以按「发给工程师」直接把 App 日志发出去。'), bad: true);
      }
    } on Object catch (e) {
      if (!quiet) _say(tr('Upload failed: $e', '上传失败：$e'), bad: true);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
    return false;
  }

  Future<void> _shareBundle() async {
    final api = widget.api, code = _code, tok = _token;
    if (api == null || code == null || tok == null || _busy) return;
    setState(() => _busy = true);
    try {
      final bytes = await api.problemBundle(code, tok);
      final ok = await widget.share('nexwar_$code.tar.gz', bytes);
      _say(ok ? tr('Shared.', '已分享。') : tr('Sharing cancelled', '已取消分享'));
    } on Object catch (e) {
      _say(tr('Could not get the package: $e', '取不到整包：$e'), bad: true);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _shareApp({String? note}) async {
    if (_busy) return;
    setState(() => _busy = true);
    try {
      final name = _code == null ? 'nexwar_app-${_stamp()}.log.gz' : 'nexwar_${_code}_app.log.gz';
      final ok = await widget.share(name, widget.log.pack(header: _header()));
      _say(ok ? (note ?? tr('Shared.', '已分享。')) : tr('Sharing cancelled', '已取消分享'), bad: ok && note != null);
    } on Object catch (e) {
      _say(tr('Sharing failed: $e', '分享失败：$e'), bad: true);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final c = Nw.of(context);
    final code = _code;
    final shape = RoundedRectangleBorder(borderRadius: BorderRadius.circular(2));
    final out = OutlinedButton.styleFrom(
        minimumSize: const Size(48, 44), shape: shape, padding: const EdgeInsets.symmetric(horizontal: Nw.s8));
    final sub = NwText.bodySmall.copyWith(color: c.textSecondary);
    Widget section(List<Widget> kids, {Key? key}) => Container(
        key: key,
        margin: const EdgeInsets.only(top: Nw.s8),
        padding: const EdgeInsets.all(Nw.s16),
        color: c.surface,
        child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: kids));
    Widget title(String t) => Padding(
        padding: const EdgeInsets.only(bottom: Nw.s8),
        child: Text(t, style: NwText.titleMedium.copyWith(color: c.text, fontWeight: FontWeight.w700)));
    final appOnly = OutlinedButton(
        key: ProblemReportPage.shareAppKey,
        style: out,
        onPressed: _busy ? null : () => _shareApp(),
        child: Text(tr('Send app log only', '只发 App 日志'), maxLines: 1, overflow: TextOverflow.ellipsis));
    // App V2 稿 S-report：一段「报问题」（出了什么事、哪台、发送），一段别的办法（站点连不上时）
    return Scaffold(
      backgroundColor: c.bg,
      // 第 9 轮 A6-07 尾巴：入口都叫「报问题」，标题跟着叫（以前进来变成「上传日志」）
      appBar: AppBar(
          title: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(tr('Report a problem', '报问题')),
        Text(tr('Also available from sign-in', '登录页上也有'), style: sub),
      ])),
      body: SafeArea(
        child: Align(
          alignment: Alignment.topCenter,
          child: SingleChildScrollView(
            padding: const EdgeInsets.only(bottom: Nw.s24),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 560),
              child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                if (code == null) ...[
                  section([
                    title(tr('Report a problem', '报问题')),
                    NwField(
                        fieldKey: ProblemReportPage.noteKey,
                        controller: _note,
                        label: tr('What happened', '出了什么事'),
                        hint: tr('e.g. robot stopped at the gate around 9:30', '比如：9 点半左右机器人在大门口停住不走了'),
                        minLines: 3,
                        maxLines: 6),
                    if (widget.robots.isNotEmpty) ...[
                      const SizedBox(height: Nw.s16),
                      Text(tr('Robot (optional)', '哪台机器人（可不选）'),
                          style: NwText.labelMedium.copyWith(color: c.textSecondary, fontWeight: FontWeight.w700)),
                      const SizedBox(height: Nw.s8),
                      // 三台以内一排分段；多了用下拉
                      if (widget.robots.length <= 3)
                        SegmentedButton<String>(
                            key: ProblemReportPage.robotKey,
                            showSelectedIcon: false,
                            style: SegmentedButton.styleFrom(
                                shape: shape, selectedBackgroundColor: c.primary, selectedForegroundColor: c.onPrimary),
                            segments: [
                              for (final r in widget.robots) ButtonSegment(value: r, label: Text(r)),
                              ButtonSegment(value: '', label: Text(tr('Not a robot', '跟机器人无关'))),
                            ],
                            selected: {_robot},
                            onSelectionChanged: _busy ? null : (v) => setState(() => _robot = v.first))
                      else
                        DropdownButtonFormField<String>(
                            key: ProblemReportPage.robotKey,
                            initialValue: _robot,
                            items: [
                              DropdownMenuItem<String>(value: '', child: Text(tr('Not a robot', '跟机器人无关'))),
                              for (final r in widget.robots) DropdownMenuItem<String>(value: r, child: Text(r)),
                            ],
                            onChanged: _busy ? null : (v) => setState(() => _robot = v ?? '')),
                    ],
                    const SizedBox(height: Nw.s8),
                    // 易用性第 6 轮 A6-07 / A7-02：说明跟唯一的主按钮「发送」对得上；没登录站点时不提站点开单
                    Text(
                        widget.api != null
                            ? tr('Tap "Send": the site opens a report with a number and the logs go to the engineer (WeChat / WhatsApp). No passwords or photos are sent.',
                                '按「发送」：站点开一张问题单、给一个编号，日志发给工程师（微信 / WhatsApp）。不会传密码和照片。')
                            : tr('Tap "Send": the app log goes to the engineer (WeChat / WhatsApp). No passwords or photos are sent.',
                                '按「发送」，App 日志发给工程师（微信 / WhatsApp）。不会传密码和照片。'),
                        style: sub),
                    const SizedBox(height: Nw.s16),
                    FilledButton(
                        key: ProblemReportPage.engineerKey,
                        style: FilledButton.styleFrom(minimumSize: const Size(48, 48), shape: shape),
                        onPressed: _busy ? null : _sendToEngineer,
                        child: Text(_busy ? tr('Sending…', '正在发送…') : tr('Send', '发送'))),
                  ]),
                  // 别的办法：只传到站点（工程师远程取）、只发 App 日志。都是描边按钮，主按钮只有「发送」一个（A6-07）
                  if (widget.api != null)
                    section(key: ProblemReportPage.otherKey, [
                      title(tr('Other ways', '其他方式')),
                      Text(
                          tr('Upload only, for the engineer to fetch remotely; or, if the site is unreachable, share this phone\'s app log.',
                              '只传到站点，工程师远程取；站点连不上时，把这台手机的 App 日志分享出去。'),
                          style: sub),
                      const SizedBox(height: Nw.s8),
                      Row(children: [
                        Expanded(
                            child: OutlinedButton(
                                key: ProblemReportPage.sendKey,
                                style: out,
                                onPressed: _busy ? null : () => _send(),
                                child: Text(tr('Upload to site only', '只传到站点'), maxLines: 1, overflow: TextOverflow.ellipsis))),
                        const SizedBox(width: Nw.s8),
                        Expanded(child: appOnly),
                      ]),
                    ]),
                ] else
                  section([
                    Icon(Icons.square, size: 20, color: c.success),
                    const SizedBox(height: Nw.s8),
                    Text(tr('Report number', '问题单编号'), style: sub),
                    SelectableText(code,
                        key: ProblemReportPage.codeKey,
                        style: NwText.titleLarge.copyWith(color: c.text, fontWeight: FontWeight.w700)),
                    const SizedBox(height: Nw.s8),
                    Text(
                        tr('The site keeps this report. Tell the engineer the number, or send the package below.',
                            '站点已留下这张单。把编号告诉工程师，或者用下面的按钮把日志发给工程师。'),
                        style: NwText.bodyMedium.copyWith(color: c.text)),
                    const SizedBox(height: Nw.s16),
                    if (_token != null) ...[
                      FilledButton(
                          key: ProblemReportPage.shareBundleKey,
                          style: FilledButton.styleFrom(minimumSize: const Size(48, 48), shape: shape),
                          onPressed: _busy ? null : _shareBundle,
                          child: Text(tr('Send package to engineer (WeChat / WhatsApp)', '整包发给工程师（微信 / WhatsApp）'))),
                      const SizedBox(height: Nw.s8),
                    ],
                    Row(children: [
                      Expanded(
                          child: OutlinedButton(
                              style: out,
                              onPressed: () {
                                Clipboard.setData(ClipboardData(text: code));
                                _say(tr('Copied', '已复制'));
                              },
                              child: Text(tr('Copy number', '复制编号')))),
                      const SizedBox(width: Nw.s8),
                      Expanded(child: appOnly),
                    ]),
                  ]),
                if (_msg != null)
                  Padding(
                      padding: const EdgeInsets.all(Nw.s16),
                      child: NwNotice(key: ProblemReportPage.msgKey, text: _msg!, tone: _msgBad ? NwTone.error : NwTone.info)),
              ]),
            ),
          ),
        ),
      ),
    );
  }
}
