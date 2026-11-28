/// 1.1-5 电子值班簿（Occurrence Book）：一天发生的事 —— 保安写的，加上站点自己记的（报警、确认、关闭、
/// 机器人巡检、外部报警器、交班留言），按时间排。写了不能改、不能删：写错了点「更正」另写一条，原来那条划掉。
///
/// 事件报告：报警详情里「分享事件报告」—— 站点出一页能打印的网页（照片嵌在里面），交给系统的分享面板，
/// 用浏览器打开就能存成 PDF。设计 docs/1.1-5-值班簿-设计.md。
library;

import 'dart:async';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:path_provider/path_provider.dart';
import 'package:share_plus/share_plus.dart';

import '../l10n.dart';
import '../net/person_names.dart';
import '../net/site_client.dart';
import 'nw/nw_theme.dart';

const List<String> obCategories = <String>[
  'duty_on', 'duty_off', 'patrol', 'incident', 'visitor', 'handover', 'maintenance', 'observation', 'other',
];

String obCategoryName(String c) => switch (c) {
      'duty_on' => tr('On duty', '上岗'),
      'duty_off' => tr('Off duty', '下岗'),
      'patrol' => tr('Patrol', '巡查'),
      'incident' => tr('Incident', '事件'),
      'visitor' => tr('Visitor', '访客'),
      'handover' => tr('Handover', '交班'),
      'maintenance' => tr('Maintenance', '维修'),
      'observation' => tr('Observation', '观察'),
      'alarm' => tr('Alarm', '报警'),
      'external' => tr('External alarm', '外部报警'),
      _ => tr('Other', '其他'),
    };

/// 分享一份网页（测试换成假的）。回 false = 人关掉了面板。
Future<bool> Function(String name, Uint8List bytes) shareHtml = _shareHtml;

Future<bool> _shareHtml(String name, Uint8List bytes) async {
  final dir = await getTemporaryDirectory();
  final f = File('${dir.path}${Platform.pathSeparator}$name');
  await f.writeAsBytes(bytes, flush: true);
  final r = await SharePlus.instance.share(ShareParams(files: [XFile(f.path, mimeType: 'text/html')], subject: name));
  return r.status != ShareResultStatus.dismissed;
}

/// 报警详情里的「分享事件报告」。回给人看的那一句。
Future<String> shareIncidentReport(SiteApi api, String alertKey) async {
  try {
    final bytes = await api.incidentReport(alertKey);
    final safe = alertKey.replaceAll(RegExp(r'[^A-Za-z0-9_-]'), '_');
    final name = 'incident-report-${safe.length > 40 ? safe.substring(0, 40) : safe}.html';
    final ok = await shareHtml(name, bytes);
    return ok
        ? tr('Report shared. Open it in a browser to print or save as PDF.', '报告已分享。用浏览器打开就能打印或存成 PDF。')
        : tr('Sharing cancelled.', '没有分享。');
  } on SiteError catch (e) {
    return tr('Report unavailable: $e', '拿不到报告：$e');
  } catch (e) {
    return tr('Sharing failed: $e', '分享失败：$e');
  }
}

/// 写一条值班簿的对话框（报警详情、值班簿页都用）。回写好的那条；取消回 null。
Future<Map<String, dynamic>?> writeOccurrence(BuildContext context, SiteApi api,
    {String category = 'observation', String text = '', int? corrects, String? alert}) {
  return showDialog<Map<String, dynamic>>(
      context: context,
      builder: (_) => _WriteDialog(api: api, category: category, text: text, corrects: corrects, alert: alert));
}

class _WriteDialog extends StatefulWidget {
  const _WriteDialog({required this.api, required this.category, required this.text, this.corrects, this.alert});
  final SiteApi api;
  final String category, text;
  final int? corrects;
  final String? alert;
  @override
  State<_WriteDialog> createState() => _WriteDialogState();
}

class _WriteDialogState extends State<_WriteDialog> {
  late String _cat = widget.category;
  late final TextEditingController _t = TextEditingController(text: widget.text);
  bool _busy = false;
  String _err = '';

  @override
  void dispose() {
    _t.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    final text = _t.text.trim();
    if (text.isEmpty) return;
    setState(() {
      _busy = true;
      _err = '';
    });
    try {
      final e = await widget.api.addOccurrence(_cat, text, corrects: widget.corrects, alert: widget.alert);
      if (mounted) Navigator.of(context).pop(e);
    } on SiteError catch (e) {
      if (mounted) setState(() => _err = '$e');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final c = Nw.of(context);
    return AlertDialog(
      title: Text(widget.corrects != null
          ? tr('Correct entry #${widget.corrects}', '更正第 #${widget.corrects} 条')
          : tr('Occurrence book entry', '写一条值班簿')),
      content: SingleChildScrollView(
        child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          DropdownButton<String>(
              key: const Key('ob-category'),
              isExpanded: true,
              value: _cat,
              items: [for (final k in obCategories) DropdownMenuItem(value: k, child: Text(obCategoryName(k)))],
              onChanged: (v) => setState(() => _cat = v ?? _cat)),
          TextField(
              key: const Key('ob-text'),
              controller: _t,
              maxLines: 4,
              maxLength: 1000,
              decoration: InputDecoration(hintText: tr('What happened, where, who was involved', '什么事、在哪、谁'))),
          Text(tr('Entries cannot be edited or deleted; to fix a mistake, write a correction.', '写了不能改、不能删；写错了另写一条更正。'),
              style: NwText.bodySmall.copyWith(color: c.textSecondary)),
          if (_err.isNotEmpty) Text(_err, style: NwText.bodyMedium.copyWith(color: c.error)),
        ]),
      ),
      actions: [
        TextButton(onPressed: _busy ? null : () => Navigator.of(context).pop(), child: Text(tr('Cancel', '取消'))),
        FilledButton(key: const Key('ob-save'), onPressed: _busy ? null : _save, child: Text(tr('Save', '保存'))),
      ],
    );
  }
}

class OccurrenceBookPage extends StatefulWidget {
  const OccurrenceBookPage({super.key, required this.api, this.now});
  final SiteApi api;
  final DateTime Function()? now;

  static const writeKey = Key('ob-write');
  static Key rowKey(Object id) => Key('ob-row-$id');
  static Key fixKey(Object id) => Key('ob-fix-$id');

  @override
  State<OccurrenceBookPage> createState() => _OccurrenceBookPageState();
}

class _OccurrenceBookPageState extends State<OccurrenceBookPage> {
  late DateTime _day = _today();
  List<Map<String, dynamic>>? _rows;
  String? _err;
  bool _manualOnly = false;

  DateTime _today() {
    final n = (widget.now ?? DateTime.now)();
    return DateTime(n.year, n.month, n.day);
  }

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  Future<void> _load() async {
    final a = _day, b = DateTime(_day.year, _day.month, _day.day + 1);
    try {
      final r = await widget.api.occurrenceBook(a.millisecondsSinceEpoch, b.millisecondsSinceEpoch);
      if (mounted) {
        setState(() {
          _rows = r;
          _err = null;
        });
      }
    } on SiteError catch (e) {
      if (mounted) setState(() => _err = '$e');
    }
  }

  void _shift(int days) {
    final d = DateTime(_day.year, _day.month, _day.day + days);
    if (d.isAfter(_today())) return;
    setState(() {
      _day = d;
      _rows = null;
    });
    unawaited(_load());
  }

  Future<void> _write({Map<String, dynamic>? fix}) async {
    final got = await writeOccurrence(context, widget.api,
        category: fix != null ? '${fix['category']}' : 'observation',
        text: fix != null ? '${fix['text']}' : '',
        corrects: fix != null ? (fix['id'] as num?)?.toInt() : null);
    if (got != null) unawaited(_load());
  }

  String _hm(int ms) {
    final t = DateTime.fromMillisecondsSinceEpoch(ms);
    return '${t.hour.toString().padLeft(2, '0')}:${t.minute.toString().padLeft(2, '0')}';
  }

  @override
  Widget build(BuildContext context) {
    final c = Nw.of(context);
    final can = widget.api.session?.canHandleAlerts ?? false;
    final day = '${_day.year}-${_day.month.toString().padLeft(2, '0')}-${_day.day.toString().padLeft(2, '0')}';
    final rows = (_rows ?? const <Map<String, dynamic>>[]).where((r) => !_manualOnly || r['source'] == 'manual').toList();
    final isToday = _day == _today();
    return Scaffold(
      appBar: AppBar(title: Text(tr('Occurrence book', '值班簿'))),
      floatingActionButton: can
          ? FloatingActionButton.extended(
              key: OccurrenceBookPage.writeKey,
              onPressed: () => unawaited(_write()),
              icon: const Icon(Icons.edit_outlined),
              label: Text(tr('Write', '写一条')))
          : null,
      body: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(Nw.s8, Nw.s8, Nw.s16, 0),
          child: Wrap(crossAxisAlignment: WrapCrossAlignment.center, spacing: Nw.s8, children: [
            Row(mainAxisSize: MainAxisSize.min, children: [
              IconButton(tooltip: tr('Previous day', '前一天'), onPressed: () => _shift(-1), icon: const Icon(Icons.chevron_left_rounded)),
              Text(isToday ? tr('Today $day', '今天 $day') : day, style: NwText.titleSmall.copyWith(color: c.text)),
              IconButton(
                  tooltip: tr('Next day', '后一天'),
                  onPressed: isToday ? null : () => _shift(1),
                  icon: const Icon(Icons.chevron_right_rounded)),
            ]),
            FilterChip(
                key: const Key('ob-manual-only'),
                label: Text(tr('Written only', '只看手写的')),
                selected: _manualOnly,
                onSelected: (v) => setState(() => _manualOnly = v)),
          ]),
        ),
        if (_err != null)
          Padding(padding: const EdgeInsets.all(Nw.s16), child: Text(_err!, style: NwText.bodyMedium.copyWith(color: c.error))),
        Expanded(
          child: _rows == null && _err == null
              ? const Center(child: CircularProgressIndicator())
              : rows.isEmpty
              ? Center(child: Text(tr('Nothing recorded on this day.', '这一天没有记录。'), style: NwText.bodyMedium.copyWith(color: c.textSecondary)))
              : ListView.separated(
                  padding: const EdgeInsets.only(bottom: 88),
                  itemCount: rows.length,
                  separatorBuilder: (_, _) => Divider(height: 1, thickness: 1, color: c.outline),
                  itemBuilder: (_, i) {
                    final r = rows[i];
                    final manual = r['source'] == 'manual';
                    final fixed = r['corrected_by'] != null;
                    final id = r['id'];
                    final who = '${r['author'] ?? ''}'.isEmpty ? '' : personName(r['author']);
                    final robot = '${r['robot'] ?? ''}';
                    return Padding(
                      key: OccurrenceBookPage.rowKey(id ?? '${r['source']}-$i'),
                      padding: const EdgeInsets.symmetric(horizontal: Nw.s16, vertical: 10),
                      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                        Row(children: [
                          Text(_hm((r['at_ms'] as num?)?.toInt() ?? 0), style: NwText.labelLarge.copyWith(color: c.text)),
                          const SizedBox(width: Nw.s8),
                          if (id != null) Text('#$id ', style: NwText.bodySmall.copyWith(color: c.textSecondary)),
                          Expanded(
                              child: Text(obCategoryName('${r['category']}'),
                                  style: NwText.bodySmall.copyWith(color: c.textSecondary))),
                          if (manual && !fixed && can)
                            TextButton(
                                key: OccurrenceBookPage.fixKey(id as Object),
                                onPressed: () => unawaited(_write(fix: r)),
                                child: Text(tr('Correct', '更正'))),
                        ]),
                        Text(
                          '${r['corrects'] != null ? tr('Correction to #${r['corrects']}: ', '更正 #${r['corrects']}：') : ''}${r['text']}',
                          style: NwText.bodyMedium.copyWith(
                              color: manual && !fixed ? c.text : c.textSecondary,
                              decoration: fixed ? TextDecoration.lineThrough : null),
                        ),
                        if (fixed)
                          Text(tr('Corrected by #${r['corrected_by']}', '已由 #${r['corrected_by']} 更正'),
                              style: NwText.bodySmall.copyWith(color: c.textSecondary)),
                        if (who.isNotEmpty || robot.isNotEmpty)
                          Text([if (robot.isNotEmpty) robot, if (who.isNotEmpty) who].join(' · '),
                              style: NwText.bodySmall.copyWith(color: c.textSecondary)),
                      ]),
                    );
                  }),
        ),
      ]),
    );
  }
}
