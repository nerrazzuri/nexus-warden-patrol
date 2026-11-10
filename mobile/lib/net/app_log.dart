/// App 自己的日志文件（日志设计 第 6 条，用户 11-10）：正式版也写。出了问题，人在「上传日志」页一按，
/// 连同手机型号、App 版本打包传给站点开问题单（[ProblemReportPage]）；站点连不上时直接用手机分享。
///
/// - 写在 App 私有目录 `logs/app.log`，每行 `2026-11-10T08:30:00.123+08:00 E 内容`；
///   超过 [maxBytes] 换成 `app.log.1`（只留一份旧的），整个最多两倍 [maxBytes]。
/// - 打码：令牌（`Bearer …`、`token=…`）、口令（`password…`）不落盘。
/// - 没打开文件之前（启动最早那一下、测试里）先记在内存里，打开后补写进去。
library;

import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart';

class AppLog {
  AppLog({this.maxBytes = 2 * 1024 * 1024, DateTime Function()? now}) : _now = now ?? DateTime.now;

  static final AppLog instance = AppLog();

  final int maxBytes;
  final DateTime Function() _now;
  File? _file;
  final List<String> _early = <String>[];

  static final RegExp _bearer = RegExp(r'Bearer\s+[A-Za-z0-9._~+/=-]+');
  static final RegExp _kv = RegExp(r'((?:token|password|passwd|secret|confirm_password|t)=)[^\s&"]+',
      caseSensitive: false);
  static final RegExp _json = RegExp(r'("(?:token|password|confirm_password|secret)"\s*:\s*")[^"]*"',
      caseSensitive: false);

  static String redact(String s) => s
      .replaceAll(_bearer, 'Bearer ***')
      .replaceAllMapped(_kv, (m) => '${m[1]}***')
      .replaceAllMapped(_json, (m) => '${m[1]}***"');

  String _stamp(DateTime t) {
    String two(int n) => n.toString().padLeft(2, '0');
    final off = t.timeZoneOffset;
    final sign = off.isNegative ? '-' : '+';
    final oh = two(off.inHours.abs()), om = two(off.inMinutes.abs() % 60);
    return '${t.year}-${two(t.month)}-${two(t.day)}T${two(t.hour)}:${two(t.minute)}:${two(t.second)}'
        '.${t.millisecond.toString().padLeft(3, '0')}$sign$oh:$om';
  }

  /// 打开日志文件（`main()` 里调一次）。
  void open(Directory dir) {
    try {
      dir.createSync(recursive: true);
      _file = File('${dir.path}${Platform.pathSeparator}app.log');
      if (_early.isNotEmpty) {
        _file!.writeAsStringSync(_early.join(), mode: FileMode.append, flush: true);
        _early.clear();
      }
    } on Object {
      _file = null; // 写不了盘：照旧记内存（上传时带内存里的）
    }
  }

  /// 记一行。[level]：`E` 错误、`W` 警告、`I` 一般。
  void line(String level, String message) {
    final text = '${_stamp(_now())} $level ${redact(message).replaceAll('\n', '\n    ')}\n';
    final f = _file;
    if (f == null) {
      _early.add(text);
      if (_early.length > 2000) _early.removeRange(0, _early.length - 2000);
      return;
    }
    try {
      if (f.existsSync() && f.lengthSync() > maxBytes) {
        f.renameSync('${f.path}.1');
      }
      f.writeAsStringSync(text, mode: FileMode.append);
    } on Object {
      _early.add(text);
    }
  }

  /// 现在有的日志（旧的那份在前）。
  String text() {
    final f = _file;
    final b = StringBuffer();
    if (f != null) {
      for (final p in <String>['${f.path}.1', f.path]) {
        try {
          final x = File(p);
          if (x.existsSync()) b.write(x.readAsStringSync());
        } on Object {
          // 读不了就不带
        }
      }
    }
    b.writeAll(_early);
    return b.toString();
  }

  /// 打包上传：开头写手机、App 的情况和人写的说明，后面是日志；gzip。最多 [maxPack] 字节（留最新的）。
  Uint8List pack({required String header, int maxPack = 4 * 1024 * 1024}) {
    var body = text();
    final room = maxPack * 4; // 文字一般能压到四分之一以下
    if (body.length > room) body = body.substring(body.length - room);
    return Uint8List.fromList(gzip.encode(utf8.encode('$header\n\n$body')));
  }
}

/// 手机的情况（不带任何账号、口令）：放在包开头，也作为问题单的「设备」。
String deviceSummary() {
  if (kIsWeb) return 'web';
  return '${Platform.operatingSystem} ${Platform.operatingSystemVersion}';
}
