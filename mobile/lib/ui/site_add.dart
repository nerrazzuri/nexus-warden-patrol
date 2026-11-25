/// 添加站点（App V2）：扫值班台「系统」页上的二维码，或者粘贴那一行配对码，或者手填。
///
/// 配对码里只有站点名、地址、证书指纹（`net/pairing.dart`），**没有账号口令**。扫完把三样填进表单、
/// 摆在眼前：别人给的码能把手机指到别的站点去，所以存之前人要跟值班台上显示的核对一遍。
///
/// 2026-10-14 按设计稿重做（P1）：换成新设计系统的页头、按钮、输入框；流程和每一栏没变。
library;

import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../l10n.dart';
import '../net/pairing.dart';
import '../net/site_client.dart';
import '../store/site_store.dart';
import 'nw/nw_p1_entry.dart';
import 'nw/nw_theme.dart';
import 'nw/nw_widgets.dart';
import 'site_scan.dart';

/// 扫一个码，回扫到的字（没扫、退出来了回 null）。测试换成假的。
typedef CodeScanner = Future<String?> Function(BuildContext context);

/// 这个平台能不能扫码：只有手机（安卓、iOS）有相机插件；桌面版粘贴。
bool get canScanCodes =>
    defaultTargetPlatform == TargetPlatform.android || defaultTargetPlatform == TargetPlatform.iOS;

class SiteAddPage extends StatefulWidget {
  /// 不给：按平台（手机上开相机，桌面版没有「扫码」按钮）。
  final CodeScanner? scanner;
  /// 列表里已有的站点（M22：同一个站点不加第二次）。
  final List<SiteEntry> existing;
  const SiteAddPage({super.key, this.scanner, this.existing = const []});

  static const Key errorKey = Key('site-add-error');

  @override
  State<SiteAddPage> createState() => _SiteAddPageState();
}

class _SiteAddPageState extends State<SiteAddPage> {
  final _name = TextEditingController();
  final _url = TextEditingController(text: 'https://');
  final _fp = TextEditingController();
  final _user = TextEditingController();
  final _code = TextEditingController();
  String? _err;

  /// 表单里这三样是从配对码来的（提示人去核对）。
  bool _fromCode = false;

  /// 手填（稿上「手动输入地址」）：三栏摆出来。扫到、贴上码也摆出来（让人核对、能改）。
  bool _manual = false;

  /// 贴配对码那一栏开着（就地，不弹窗）。
  bool _pasting = false;

  @override
  void dispose() {
    for (final c in [_name, _url, _fp, _user, _code]) {
      c.dispose();
    }
    super.dispose();
  }

  void _say(String s) => ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(s)));

  void _take(String raw) {
    final PairingInfo p;
    try {
      p = decodePairing(raw);
    } on PairingException catch (e) {
      _say(e.message);
      return;
    }
    setState(() {
      _name.text = p.name;
      _url.text = p.url;
      _fp.text = p.fingerprint;
      _fromCode = true;
      _pasting = false;
      _err = null;
    });
  }

  Future<void> _scan() async {
    final scan = widget.scanner ?? scanSiteCode;
    final raw = await scan(context);
    if (raw == null || !mounted) return;
    _take(raw);
  }

  void _paste() {
    setState(() => _pasting = !_pasting);
    if (!_pasting) return;
    // 手机 App 测试 M21：剪贴板里就是站点码就先填进框里（以前要长按 → 粘贴），点「用这个码」就行
    unawaited(Clipboard.getData(Clipboard.kTextPlain).then((d) {
      final t = d?.text?.trim() ?? '';
      if (mounted && t.startsWith(pairingPrefix) && _code.text.isEmpty) _code.text = t;
    }, onError: (Object _) {}));
  }

  void _save() {
    var bad = checkSiteEntry(_url.text, _fp.text);
    if (bad == null && _name.text.trim().isEmpty) bad = tr('enter a name', '请填写名称');
    final fp = normalizeFingerprint(_fp.text);
    if (bad == null) {
      for (final e in widget.existing) {
        if (e.url == _url.text.trim() && e.fingerprint == fp) {
          bad = tr('this site is already in the list as "${e.name}"', '这个站点已经在列表里了（叫「${e.name}」）');
        }
      }
    }
    if (bad != null) {
      // M22：原因留在页面上（以前只闪一下）
      setState(() => _err = tr('Not saved: $bad', '未保存：$bad'));
      return;
    }
    Navigator.pop(
      context,
      SiteEntry(
        name: _name.text.trim(),
        url: _url.text.trim(),
        fingerprint: normalizeFingerprint(_fp.text),
        // 账号可以现在填，也可以第一次登录时再输（用户 10-30：加站点时可能还没有账号）
        username: _user.text.trim(),
      ),
    );
  }

  @override
  Widget build(BuildContext context) => Theme(data: nwTheme(Brightness.dark), child: Builder(builder: _build));

  Widget _build(BuildContext context) {
    final scan = widget.scanner != null || canScanCodes;
    final c = Nw.of(context);
    const gap = SizedBox(height: Nw.s16);
    final shape = RoundedRectangleBorder(borderRadius: BorderRadius.circular(2));
    final out = OutlinedButton.styleFrom(
        minimumSize: const Size(48, 44),
        shape: shape,
        padding: const EdgeInsets.symmetric(horizontal: Nw.s8),
        foregroundColor: c.text,
        side: BorderSide(color: c.textMuted));
    final label = NwText.labelMedium.copyWith(color: c.textSecondary, fontWeight: FontWeight.w700);
    final showForm = _manual || _fromCode;
    // App V2 稿 E-add（深色）：取景框、「粘贴配对码 | 手动输入地址」、扫到的三样、账号、「保存并登录」
    return Scaffold(
      backgroundColor: c.bg,
      appBar: AppBar(
          backgroundColor: c.bg,
          title: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(tr('Add site', '添加站点'), style: NwText.titleMedium.copyWith(color: c.text, fontWeight: FontWeight.w700)),
            Text(
                // I5 11-17：写网页上真实的位置（以前说「系统」页，新版网页没有这一页）
                tr('Site code: web console → Site Setup → Maps, localization, diagnostics, updates → Site host',
                    '站点码在网页：现场设置 → 地图、定位、诊断、升级 → 站点主机'),
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                style: NwText.bodySmall.copyWith(color: c.textSecondary)),
          ])),
      // 不用懒加载的列表：横屏弹键盘时剩不了多高，表单要整个都在（能滚到），不然光标落不到输入框上。
      body: SafeArea(
        top: false,
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(Nw.s16),
          child: Center(
            // 宽屏（桌面版）上表单不拉满一整行
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 560),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  // 取景框：点了开相机（桌面版没有相机，不摆）
                  if (scan)
                    Material(
                      color: Colors.black,
                      child: InkWell(
                        key: const Key('site-scan'),
                        onTap: _scan,
                        child: SizedBox(
                          height: 240,
                          child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
                            Container(
                                width: 150,
                                height: 150,
                                alignment: Alignment.center,
                                decoration: BoxDecoration(border: Border.all(color: Colors.white, width: 3)),
                                child: const Icon(Icons.qr_code_scanner_rounded, size: 40, color: Colors.white70)),
                            const SizedBox(height: Nw.s8),
                            Text(tr('Tap to scan the QR code', '点这里扫二维码'),
                                style: NwText.bodySmall.copyWith(color: Colors.white70)),
                          ]),
                        ),
                      ),
                    ),
                  if (scan) const SizedBox(height: Nw.s8),
                  Row(children: [
                    Expanded(
                        child: OutlinedButton(
                            key: const Key('site-paste'),
                            style: out,
                            onPressed: _paste,
                            child: Text(tr('Paste pairing code', '粘贴配对码'), maxLines: 1, overflow: TextOverflow.ellipsis))),
                    const SizedBox(width: Nw.s8),
                    Expanded(
                        child: OutlinedButton(
                            key: const Key('site-manual'),
                            style: out,
                            onPressed: () => setState(() => _manual = true),
                            child: Text(tr('Enter address manually', '手动输入地址'), maxLines: 1, overflow: TextOverflow.ellipsis))),
                  ]),
                  if (_pasting) ...[
                    gap,
                    NwField(
                      fieldKey: const Key('pair-code'),
                      controller: _code,
                      autofocus: true,
                      autocorrect: false,
                      enableSuggestions: false,
                      maxLines: 4,
                      minLines: 2,
                      mono: true,
                      hint: '$pairingPrefix…',
                    ),
                    const SizedBox(height: Nw.s8),
                    Row(children: [
                      Expanded(
                          child: OutlinedButton(
                              style: out, onPressed: () => setState(() => _pasting = false), child: Text(tr('Cancel', '取消')))),
                      const SizedBox(width: Nw.s8),
                      Expanded(
                          child: FilledButton(
                              key: const Key('pair-code-ok'),
                              style: FilledButton.styleFrom(minimumSize: const Size(48, 44), shape: shape),
                              onPressed: () => _take(_code.text),
                              child: Text(tr('Use code', '用这个码')))),
                    ]),
                  ],
                  if (showForm) ...[
                    gap,
                    Text(_fromCode ? tr('Scanned', '扫到的') : tr('Site', '站点'), style: label),
                    const SizedBox(height: Nw.s8),
                    if (_fromCode)
                      Padding(
                        key: const Key('site-check-note'),
                        padding: const EdgeInsets.only(bottom: Nw.s16),
                        child: NwNotice(
                          tone: NwTone.warning,
                          text: tr(
                            'Check that the site name and certificate fingerprint match the duty console, then save.',
                            '请核对下方站点名称和证书指纹与值班台一致后再保存。',
                          ),
                        ),
                      ),
                    NwField(fieldKey: const Key('site-name'), controller: _name, label: tr('Site name', '站点名')), // 易用性 37 P3-11：跟上面的「Site」重了
                    gap,
                    NwField(
                      fieldKey: const Key('site-url'),
                      controller: _url,
                      keyboardType: TextInputType.url,
                      autocorrect: false,
                      label: tr('Address, with port (https://…)', '地址，含端口（https://…）'),
                    ),
                    gap,
                    NwField(
                      fieldKey: const Key('site-fp'),
                      controller: _fp,
                      autocorrect: false,
                      enableSuggestions: false,
                      minLines: 1,
                      maxLines: 3,
                      mono: true,
                      label: tr(
                        'Certificate fingerprint (shown next to the site code on the console)',
                        '证书指纹（值班台上站点码旁边有）',
                      ),
                    ),
                    gap,
                    NwField(
                      fieldKey: const Key('site-user'),
                      controller: _user,
                      autocorrect: false,
                      enableSuggestions: false,
                      label: tr('Account (optional, or enter it at sign-in)', '账号（可以不填，登录时再输）'),
                    ),
                    if (_err != null) ...[
                      gap,
                      NwNotice(key: SiteAddPage.errorKey, tone: NwTone.error, text: _err!),
                    ],
                    gap,
                    FilledButton(
                      key: const Key('site-save'),
                      style: FilledButton.styleFrom(minimumSize: const Size(48, 48), shape: shape),
                      onPressed: _save,
                      child: Text(tr('Save and sign in', '保存并登录')),
                    ),
                  ],
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
