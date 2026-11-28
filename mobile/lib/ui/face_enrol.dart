// 1.1-1 认出保安 第 1 步：本人登记自己的脸（设计 docs/1.1-1-认出保安-设计.md）。
//
// 本人勾「同意」才能拍；前置相机拍一张、缩到 480 px 发给站点，站点算出特征值就把照片丢掉，
// 特征值加密存在站点上。最多 5 张；随时能删（= 撤销同意）。管理员不能替别人登记。

import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';

import '../l10n.dart';
import '../net/site_client.dart';
import 'nw/nw_theme.dart';

/// 拍一张自拍（前置相机，缩到 480 px）；取消了是 `null`。测试换成假的。
typedef SelfieTaker = Future<Uint8List?> Function();

Future<Uint8List?> takeSelfie() async {
  final x = await ImagePicker().pickImage(
      source: ImageSource.camera, preferredCameraDevice: CameraDevice.front, maxWidth: 480, maxHeight: 480, imageQuality: 80);
  return x == null ? null : readAndForget(x.path);
}

/// 外审 1.1 第 4 轮 #5：拍照插件把照片写在 App 缓存里 —— 读出来就删掉（成没成都删），
/// 同一个目录里插件留下的原图、缩图（`image_picker*`、`scaled_*`）一起删。照片不留在手机上。
Future<Uint8List> readAndForget(String path) async {
  final f = File(path);
  try {
    return await f.readAsBytes();
  } finally {
    await _forget(f);
  }
}

Future<void> _forget(File f) async {
  try {
    if (await f.exists()) await f.delete();
  } on FileSystemException {
    // 删不掉也不挡登记；下面再扫一遍
  }
  try {
    await for (final e in f.parent.list()) {
      final name = e.uri.pathSegments.isEmpty ? '' : e.uri.pathSegments.last;
      if (e is File && (name.startsWith('image_picker') || name.startsWith('scaled_'))) {
        try {
          await e.delete();
        } on FileSystemException {
          // 下次再删
        }
      }
    }
  } on FileSystemException {
    // 目录读不了：只删得了上面那一张
  }
}

class FaceEnrolPage extends StatefulWidget {
  final SiteApi api;
  final SelfieTaker take;
  const FaceEnrolPage({super.key, required this.api, this.take = takeSelfie});

  static const consentKey = Key('face-consent');
  static const takeKey = Key('face-take');
  static const removeKey = Key('face-remove');
  static const removeYesKey = Key('face-remove-yes');
  static const countKey = Key('face-count');
  static const msgKey = Key('face-msg');
  static const passesKey = Key('face-passes');

  @override
  State<FaceEnrolPage> createState() => _FaceEnrolPageState();
}

class _FaceEnrolPageState extends State<FaceEnrolPage> {
  Map<String, dynamic>? _v;
  List<Map<String, dynamic>>? _passes;
  bool _consent = false, _busy = false, _askRemove = false, _ok = false;
  String _msg = '';

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final v = await widget.api.myFaces();
      if (mounted) setState(() => _v = v);
    } on SiteError catch (e) {
      if (mounted) setState(() => _msg = refusalText(e));
    }
    await _loadPasses();
  }

  /// 1.1-1 第 4 步：最近 7 天机器人认出我的记录（老站点没有就不显示）。
  Future<void> _loadPasses() async {
    final now = DateTime.now().millisecondsSinceEpoch;
    try {
      final p = await widget.api.guardPasses(now - 7 * 86400000, now + 60000);
      if (mounted) setState(() => _passes = p);
    } on SiteError {
      if (mounted) setState(() => _passes = null);
    }
  }

  String _when(Object? ms) {
    final t = DateTime.fromMillisecondsSinceEpoch((ms as num?)?.toInt() ?? 0);
    String two(int n) => n.toString().padLeft(2, '0');
    return '${two(t.month)}-${two(t.day)} ${two(t.hour)}:${two(t.minute)}';
  }

  int get _n => (_v?['photos'] as num?)?.toInt() ?? 0;
  int get _max => (_v?['max_photos'] as num?)?.toInt() ?? 5;

  Future<void> _take() async {
    setState(() {
      _busy = true;
      _msg = '';
    });
    try {
      final jpeg = await widget.take();
      if (jpeg == null) return;
      final v = await widget.api.addFacePhoto(base64Encode(jpeg));
      if (mounted) {
        setState(() {
          _v = v;
          _ok = true;
          _msg = tr('Photo added.', '这张登记好了。') +
              (_n < 3 ? tr(' Take ${3 - _n} more (slightly different angles) so the robot recognises you better.', '再拍 ${3 - _n} 张（角度稍微变一点），机器人认得更准。') : '');
        });
      }
    } on SiteError catch (e) {
      if (mounted) {
        setState(() {
          _ok = false;
          _msg = tr('Not added: ${refusalText(e)}', '没登记上：${refusalText(e)}');
        });
      }
    } catch (e) {
      // 相机打不开、没给相机权限
      if (mounted) {
        setState(() {
          _ok = false;
          _msg = tr('Camera not available. Allow camera access for this app in the phone settings.', '相机打不开：请在手机设置里允许这个 App 用相机。');
        });
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _remove() async {
    setState(() {
      _busy = true;
      _askRemove = false;
    });
    try {
      final v = await widget.api.removeMyFaces();
      if (mounted) {
        setState(() {
          _v = v;
          _consent = false;
          _ok = true;
          _msg = tr('Your face data and recognition records have been deleted from the site.', '你的人脸资料和认出记录已经从站点上删掉了。');
        });
        await _loadPasses();
      }
    } on SiteError catch (e) {
      if (mounted) setState(() => _msg = refusalText(e));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final c = Nw.of(context);
    final shape = RoundedRectangleBorder(borderRadius: BorderRadius.circular(2));
    final v = _v;
    final engine = v?['engine'] == true;
    final body = NwText.bodyMedium.copyWith(color: c.text);
    return Scaffold(
        appBar: AppBar(title: Text(tr('Face enrolment', '人脸登记'))),
        body: ListView(padding: const EdgeInsets.all(Nw.s16), children: [
          Text(
              tr('Enrol your face so the robot knows you are staff: when it sees you on patrol it only notes that you passed, with no alarm.',
                  '登记你的脸，机器人就认得你是工作人员：巡逻时看见你只记一笔「经过」，不报警。'),
              style: body),
          const SizedBox(height: Nw.s8),
          Text(
              tr('The site keeps only numbers worked out from each photo, encrypted on the site server. The photo itself is not kept, and nothing leaves the site. You can delete it any time.',
                  '站点只存从照片算出来的一串数，加密存在站点主机上；照片本身不留，也不出站点。随时可以删。'),
              style: NwText.bodySmall.copyWith(color: c.textSecondary)),
          const SizedBox(height: Nw.s16),
          if (v == null && _msg.isEmpty) const Center(child: CircularProgressIndicator()),
          if (v != null && !engine)
            Text(tr('Face recognition is not installed on this site. Ask your administrator.', '这个站点没装人脸识别模块，请问管理员。'),
                style: NwText.bodyMedium.copyWith(color: c.warning)),
          if (v != null && engine) ...[
            Text(tr('Enrolled photos: $_n / $_max', '已登记照片：$_n / $_max'),
                key: FaceEnrolPage.countKey, style: NwText.titleSmall.copyWith(color: c.text, fontWeight: FontWeight.w700)),
            const SizedBox(height: Nw.s8),
            CheckboxListTile(
                key: FaceEnrolPage.consentKey,
                contentPadding: EdgeInsets.zero,
                controlAffinity: ListTileControlAffinity.leading,
                value: _consent,
                onChanged: _busy ? null : (x) => setState(() => _consent = x == true),
                title: Text(
                    tr('I agree to the site using my face to recognise me as staff.', '我同意站点用我的脸认出我是工作人员。'),
                    style: body)),
            const SizedBox(height: Nw.s8),
            FilledButton.icon(
                key: FaceEnrolPage.takeKey,
                style: FilledButton.styleFrom(minimumSize: const Size(48, 48), shape: shape),
                onPressed: _busy || !_consent || _n >= _max ? null : _take,
                icon: const Icon(Icons.photo_camera_front_outlined),
                label: Text(_n >= _max ? tr('All $_max photos taken', '$_max 张都拍好了') : tr('Take a photo of my face', '拍一张我的脸'))),
            const SizedBox(height: Nw.s4),
            Text(tr('Face the camera in good light, only you in the picture.', '正对镜头、光线亮一点，画面里只有你自己。'),
                style: NwText.bodySmall.copyWith(color: c.textSecondary)),
            if (_n > 0) ...[
              const SizedBox(height: Nw.s16),
              OutlinedButton(
                  key: FaceEnrolPage.removeKey,
                  style: OutlinedButton.styleFrom(minimumSize: const Size(48, 48), shape: shape),
                  onPressed: _busy ? null : () => setState(() => _askRemove = !_askRemove),
                  child: Text(tr('Delete my face data', '删掉我的人脸资料'))),
              if (_askRemove) ...[
                const SizedBox(height: Nw.s8),
                Text(tr('Delete all $_n photos\' data? The robot will no longer recognise you.', '删掉全部 $_n 张的资料？删了机器人就认不出你了。'), style: body),
                const SizedBox(height: Nw.s8),
                FilledButton(
                    key: FaceEnrolPage.removeYesKey,
                    style: FilledButton.styleFrom(minimumSize: const Size(48, 48), shape: shape),
                    onPressed: _busy ? null : _remove,
                    child: Text(tr('Delete', '删掉'))),
              ],
            ],
          ],
          if (_passes != null && (_passes!.isNotEmpty || _n > 0)) ...[
            const SizedBox(height: Nw.s24),
            Text(tr('Recognised by robots (last 7 days)', '最近 7 天机器人认出的记录'),
                key: FaceEnrolPage.passesKey, style: NwText.titleSmall.copyWith(color: c.text, fontWeight: FontWeight.w700)),
            const SizedBox(height: Nw.s4),
            if (_passes!.isEmpty)
              Text(tr('None yet.', '还没有。'), style: NwText.bodySmall.copyWith(color: c.textSecondary)),
            for (final p in _passes!.take(50))
              Padding(
                padding: const EdgeInsets.symmetric(vertical: Nw.s4),
                child: Text(
                    '${_when(p['first_ms'])}  ${p['account'] ?? ''}  ${'${p['zone'] ?? ''}'.isEmpty ? '' : '${p['zone']} · '}${p['robot'] ?? ''}'
                    '${((p['n'] as num?)?.toInt() ?? 1) > 1 ? '  ×${p['n']}' : ''}',
                    style: body),
              ),
            Text(tr('Kept 90 days; deleted together with your face data.', '留 90 天；删人脸资料时一起删。'),
                style: NwText.bodySmall.copyWith(color: c.textSecondary)),
          ],
          if (_msg.isNotEmpty) ...[
            const SizedBox(height: Nw.s16),
            Text(_msg, key: FaceEnrolPage.msgKey, style: NwText.bodyMedium.copyWith(color: _ok ? c.text : c.error)),
          ],
        ]));
  }
}
