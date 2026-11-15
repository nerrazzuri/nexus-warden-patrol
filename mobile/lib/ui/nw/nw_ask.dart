// App V2「不弹窗」：页内就地问一句。页面 State 混入 [NwAsk]，把 [askStrip] 摆在页面内容最上面；
// [ask] / [askYes] 跟 showDialog 一样 await 结果，只是问题是页面里的一条（琥珀 / 红边），按钮一排等宽，
// 出来时滚到看得见。再问一句会把上一句当「取消」收掉；页面关了也算取消。
// 再输密码的确认（解绑、重启）照旧弹窗，不走这里。
import 'dart:async';

import 'package:flutter/material.dart';

import '../../l10n.dart';
import '../widget/fields_dialog.dart' show DialogField;
import 'nw_theme.dart';

/// 一个选项：按钮上的字、选了回什么、按钮的 Key；[primary] 实心蓝，[danger] 实心红。
class AskChoice<T> {
  final String label;
  final T value;
  final Key? key;
  final bool primary;
  final bool danger;
  const AskChoice(this.label, this.value, {this.key, this.primary = false, this.danger = false});
}

class _AskReq {
  final String title;
  final String? body;
  final Widget? content;
  final List<AskChoice<Object?>> choices;
  final String cancel;
  final Key? cancelKey;
  final bool danger;
  final void Function(Object?) done;

  /// 内容自己带按钮（填几个字那种：确认要等填对了才亮）。
  final bool ownButtons;
  _AskReq(this.title, this.body, this.content, this.choices, this.cancel, this.cancelKey, this.danger, this.done,
      {this.ownButtons = false});
}

/// 把这一页里的第一个滚动列表滚回顶（页顶插进来的警示、确认条要看得见）。
void scrollPageToTop(BuildContext context) {
  ScrollableState? found;
  void visit(Element e) {
    if (found != null) return;
    if (e is StatefulElement && e.state is ScrollableState) {
      found = e.state as ScrollableState;
      return;
    }
    e.visitChildElements(visit);
  }

  (context as Element).visitChildElements(visit);
  final pos = found?.position;
  if (pos != null && pos.pixels > pos.minScrollExtent) pos.jumpTo(pos.minScrollExtent);
}

mixin NwAsk<W extends StatefulWidget> on State<W> {
  _AskReq? _askReq;
  final GlobalKey _askKey = GlobalKey();

  /// 正在问（页面可以拿它决定别的按钮要不要先灰掉）。
  bool get asking => _askReq != null;

  Future<T?> ask<T>({
    required String title,
    String? body,
    Widget? content,
    required List<AskChoice<T>> choices,
    String? cancel,
    Key? cancelKey,
    bool danger = false,
    bool ownButtons = false,
  }) {
    _askReq?.done(null);
    final got = Completer<T?>();
    setState(() => _askReq = _AskReq(title, body, content, [for (final c in choices) AskChoice<Object?>(c.label, c.value, key: c.key, primary: c.primary, danger: c.danger)],
        cancel ?? tr('Cancel', '取消'), cancelKey, danger, (v) {
      if (!got.isCompleted) got.complete(v as T?);
    }, ownButtons: ownButtons));
    WidgetsBinding.instance.addPostFrameCallback((_) => _reveal());
    return got.future;
  }

  /// 滚到那一条：建出来了就 ensureVisible；列表是懒建的、这一条在最上面还没建，就把页面的列表滚回顶。
  void _reveal({bool again = true}) {
    if (!mounted) return;
    final ctx = _askKey.currentContext;
    if (ctx != null && ctx.mounted) {
      unawaited(Scrollable.ensureVisible(ctx, alignment: 0.05, duration: const Duration(milliseconds: 150)));
      return;
    }
    scrollPageToTop(context);
    // 列表在第一行上面插进一条时会把滚动位置往下修正（保住原来看着的那一行）：下一帧再对一次
    if (again) {
      WidgetsBinding.instance.addPostFrameCallback((_) => _reveal(again: false));
      WidgetsBinding.instance.scheduleFrame();
    }
  }

  /// 是 / 否：点了 [ok] 回 true，取消（或被下一句顶掉、页面关了）回 false。
  Future<bool> askYes(String title, {String? body, Widget? content, required String ok, Key? okKey, bool danger = false, String? cancel, Key? cancelKey}) async =>
      await ask<bool>(
          title: title,
          body: body,
          content: content,
          danger: danger,
          cancel: cancel,
          cancelKey: cancelKey,
          choices: [AskChoice<bool>(ok, true, key: okKey, primary: !danger, danger: danger)]) ==
      true;

  /// 填几个字（替代原来的 showFieldsDialog）：按确认回每一栏去掉首尾空白的字；取消回 null。
  /// 有 [DialogField.check] 的栏边输边查，有错时字段下面标红、确认灰着。
  Future<List<String>?> askFields(
          {required String title, String? body, required List<DialogField> fields, required String confirm, Key? confirmKey}) =>
      ask<List<String>>(
          title: title,
          body: body,
          choices: const [],
          ownButtons: true,
          content: _FieldsForm(fields: fields, confirm: confirm, confirmKey: confirmKey, onDone: _pick));

  /// 收掉正在问的那一句（算取消）：问的前提变了（会话换了、数据改了）时调。
  void askCancel() => _pick(null);

  void _pick(Object? v) {
    final r = _askReq;
    if (r == null) return;
    setState(() => _askReq = null);
    r.done(v);
  }

  /// 摆在页面内容最上面（ListView 的第一行、Column 的第一个）；没在问就是空的。
  Widget askStrip({EdgeInsets margin = const EdgeInsets.fromLTRB(Nw.s16, Nw.s8, Nw.s16, Nw.s8)}) {
    final r = _askReq;
    if (r == null) return const SizedBox.shrink();
    // 占满宽（放在 crossAxisAlignment.start 的 Column 里也一样宽）
    return SizedBox(width: double.infinity, child: _AskStrip(key: _askKey, req: r, margin: margin, onPick: _pick));
  }

  @override
  void dispose() {
    _askReq?.done(null);
    _askReq = null;
    super.dispose();
  }
}

class _AskStrip extends StatelessWidget {
  final _AskReq req;
  final EdgeInsets margin;
  final void Function(Object?) onPick;
  const _AskStrip({super.key, required this.req, required this.margin, required this.onPick});

  @override
  Widget build(BuildContext context) {
    final c = Nw.of(context);
    final shape = RoundedRectangleBorder(borderRadius: BorderRadius.circular(2));
    const size = Size(48, 44);
    Widget btn(AskChoice<Object?> a) => a.primary || a.danger
        ? FilledButton(
            key: a.key,
            style: FilledButton.styleFrom(
                minimumSize: size,
                shape: shape,
                padding: const EdgeInsets.symmetric(horizontal: Nw.s8),
                backgroundColor: a.danger ? c.error : null,
                foregroundColor: a.danger ? c.onError : null),
            onPressed: () => onPick(a.value),
            child: Text(a.label, textAlign: TextAlign.center, maxLines: 2))
        : OutlinedButton(
            key: a.key,
            style: OutlinedButton.styleFrom(minimumSize: size, shape: shape, padding: const EdgeInsets.symmetric(horizontal: Nw.s8)),
            onPressed: () => onPick(a.value),
            child: Text(a.label, textAlign: TextAlign.center, maxLines: 2));
    final cancel = OutlinedButton(
        key: req.cancelKey,
        style: OutlinedButton.styleFrom(minimumSize: size, shape: shape, padding: const EdgeInsets.symmetric(horizontal: Nw.s8)),
        onPressed: () => onPick(null),
        child: Text(req.cancel, textAlign: TextAlign.center, maxLines: 2));
    // 两三个选项一排等宽（取消在最左）；多了（选哪台机器人）一个一行，取消在最后
    final many = req.choices.length > 2;
    // 底色给 Material（里面可能有 CheckboxListTile），边框用 shape 画
    return Padding(
        padding: margin,
        child: Material(
            color: c.surface,
            shape: Border.all(color: req.danger ? c.error : c.warning, width: 2),
            child: Padding(
            padding: const EdgeInsets.all(Nw.s16),
            child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, mainAxisSize: MainAxisSize.min, children: [
              Text(req.title, style: NwText.titleSmall.copyWith(color: c.text, fontWeight: FontWeight.w700)),
              if (req.body != null) ...[
                const SizedBox(height: Nw.s4),
                Text(req.body!, style: NwText.bodyMedium.copyWith(color: c.textSecondary)),
              ],
              if (req.content != null) ...[const SizedBox(height: Nw.s8), req.content!],
              if (!req.ownButtons) const SizedBox(height: Nw.s16),
              if (req.ownButtons)
                const SizedBox.shrink()
              else if (many) ...[
                for (final a in req.choices) ...[btn(a), const SizedBox(height: Nw.s8)],
                cancel,
              ] else
                Row(children: [
                  Expanded(child: cancel),
                  for (final a in req.choices) ...[const SizedBox(width: Nw.s8), Expanded(child: btn(a))],
                ]),
            ]))));
  }
}

class _FieldsForm extends StatefulWidget {
  final List<DialogField> fields;
  final String confirm;
  final Key? confirmKey;
  final void Function(Object?) onDone;
  const _FieldsForm({required this.fields, required this.confirm, required this.confirmKey, required this.onDone});
  @override
  State<_FieldsForm> createState() => _FieldsFormState();
}

class _FieldsFormState extends State<_FieldsForm> {
  late final List<TextEditingController> _ctl = [
    for (final f in widget.fields) TextEditingController(text: f.initial),
  ];

  @override
  void dispose() {
    for (final c in _ctl) {
      c.dispose();
    }
    super.dispose();
  }

  String? _error(int i) {
    final t = _ctl[i].text.trim();
    final check = widget.fields[i].check;
    return t.isEmpty || check == null ? null : check(t);
  }

  bool get _ok => [
        for (var i = 0; i < _ctl.length; i++)
          widget.fields[i].check == null || (_ctl[i].text.trim().isNotEmpty && _error(i) == null),
      ].every((v) => v);

  @override
  Widget build(BuildContext context) {
    final c = Nw.of(context);
    final shape = RoundedRectangleBorder(borderRadius: BorderRadius.circular(2));
    const size = Size(48, 44);
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, mainAxisSize: MainAxisSize.min, children: [
      for (var i = 0; i < widget.fields.length; i++)
        Padding(
            padding: EdgeInsets.only(top: i == 0 ? 0 : Nw.s8),
            child: TextField(
                key: widget.fields[i].key,
                controller: _ctl[i],
                onChanged: (_) => setState(() {}),
                style: NwText.bodyMedium.copyWith(color: c.text),
                decoration:
                    InputDecoration(labelText: widget.fields[i].label, errorMaxLines: 3, errorText: _error(i)))),
      const SizedBox(height: Nw.s16),
      Row(children: [
        Expanded(
            child: OutlinedButton(
                style: OutlinedButton.styleFrom(minimumSize: size, shape: shape),
                onPressed: () => widget.onDone(null),
                child: Text(tr('Cancel', '取消')))),
        const SizedBox(width: Nw.s8),
        Expanded(
            child: FilledButton(
                key: widget.confirmKey,
                style: FilledButton.styleFrom(minimumSize: size, shape: shape),
                onPressed: _ok ? () => widget.onDone([for (final c in _ctl) c.text.trim()]) : null,
                child: Text(widget.confirm))),
      ]),
    ]);
  }
}
