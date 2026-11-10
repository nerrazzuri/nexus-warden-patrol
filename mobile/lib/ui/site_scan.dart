/// 扫配对码的相机页（App V2）。只在手机上有（相机插件没有 Linux / Windows 版）；扫到第一个码就回去，
/// 认不认得出来归 `site_add.dart`（不是站点的码它会说）。相机起不来（没给权限）说清楚怎么办。
library;

import 'package:flutter/material.dart';
import 'package:mobile_scanner/mobile_scanner.dart';

import '../l10n.dart';
import 'nw/nw_p1_entry.dart';
import 'nw/nw_theme.dart';
import 'nw/nw_widgets.dart';

/// 开相机扫一个码；没扫、退出来了回 null。
Future<String?> scanSiteCode(BuildContext context) =>
    Navigator.push<String>(context, MaterialPageRoute<String>(builder: (_) => const SiteScanPage()));

class SiteScanPage extends StatefulWidget {
  /// 扫机器人身上的贴纸（加机器人），不是站点码（手机 App 测试 M18：以前标题、提示都叫人去扫值班台的码）。
  final bool robot;
  const SiteScanPage({super.key, this.robot = false});

  @override
  State<SiteScanPage> createState() => _SiteScanPageState();
}

class _SiteScanPageState extends State<SiteScanPage> {
  final _camera = MobileScannerController(formats: const [BarcodeFormat.qrCode]);
  bool _done = false;

  @override
  void dispose() {
    _camera.dispose();
    super.dispose();
  }

  void _found(BarcodeCapture capture) {
    if (_done) return;
    for (final b in capture.barcodes) {
      final v = b.rawValue;
      if (v == null || v.isEmpty) continue;
      _done = true; // 相机一秒回好几帧：只回去一次
      Navigator.pop(context, v);
      return;
    }
  }

  @override
  Widget build(BuildContext context) {
    final c = Nw.of(context);
    return Scaffold(
      backgroundColor: c.bg,
      appBar: nwHeaderBar(
          context,
          NwHeader(
              leading: BackButton(color: c.text),
              title: widget.robot ? tr('Scan the robot sticker', '扫机器人贴纸') : tr('Scan site code', '扫描配对码'))),
      body: Stack(
        fit: StackFit.expand,
        children: [
          MobileScanner(
            controller: _camera,
            onDetect: _found,
            errorBuilder: (context, error) => Center(
              child: SingleChildScrollView(
                // 底下那条提示压着，留出它的地方
                padding: const EdgeInsets.fromLTRB(Nw.s24, Nw.s24, Nw.s24, 96),
                child: NwNotice(
                  tone: NwTone.warning,
                  text: error.errorCode == MobileScannerErrorCode.permissionDenied
                      ? tr(
                          'Camera access is off for this app. Allow it in the phone settings, or go back and paste the code.',
                          'App 没有相机权限。请在手机设置中允许，或返回粘贴配对码。',
                        )
                      : tr("The camera didn't start. Go back and type the code instead.", '相机未能启动，请返回手动输入。'),
                ),
              ),
            ),
          ),
          Align(
            alignment: Alignment.bottomCenter,
            child: Container(
              width: double.infinity,
              color: c.scrim,
              child: SafeArea(
                top: false,
                child: Padding(
                  padding: const EdgeInsets.all(Nw.s16),
                  child: Text(
                    widget.robot
                        ? tr('Point the camera at the QR sticker on the robot body.', '对准机器人机身上贴的二维码。')
                        : tr('Point the camera at the code on the console: Admin, System.', '对准值班台「管理 → 系统」中的二维码。'),
                    textAlign: TextAlign.center,
                    style: NwText.bodyMedium.copyWith(color: c.onScrim),
                  ),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
