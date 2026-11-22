/// 第四档 #45 省流量（用户 11-21）：手机用流量看画面时打开 —— 每一路要站点的小画面
/// （`?lite=1`：最宽 640、每秒约 2 帧、画质压低），一路约 0.3 Mbit/s（原画约 4 Mbit/s）。
///
/// 设置页里的开关，记在手机上（App 重启照旧）；默认关。
library;

import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart';

/// 省流量开没开。
final ValueNotifier<bool> dataSaver = ValueNotifier<bool>(false);

File? _file;

/// 启动时读上次的选择（文件坏了、没有就当关）。
Future<void> loadDataSaver(File f) async {
  _file = f;
  var on = false;
  try {
    if (await f.exists()) {
      final v = jsonDecode(await f.readAsString());
      on = v is Map && v['on'] == true;
    }
  } catch (_) {
    // 坏了当没开过
  }
  dataSaver.value = on;
}

/// 开关一下，顺手存下来（存不了就只管这一次）。
void setDataSaver(bool on) {
  dataSaver.value = on;
  final f = _file;
  if (f == null) return;
  unawaited(f.writeAsString(jsonEncode(<String, bool>{'on': on})).then((_) {}, onError: (_) {}));
}

/// 画面地址：省流量时加 `lite=1`（已经带问号的接 `&`）。
String videoPath(String path, {bool? saver}) {
  if (!(saver ?? dataSaver.value)) return path;
  return '$path${path.contains('?') ? '&' : '?'}lite=1';
}
