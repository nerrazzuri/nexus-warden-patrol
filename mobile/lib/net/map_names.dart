import 'package:flutter/foundation.dart';

/// 用户 11-26「建图名字这很重要」：地图的显示名（建图向导里填的、网页地图管理里改的），整张图一个。
/// 站点在 `/api/robots`（`map_names`）、`/api/maps`（每版的 `name`）里给；拉到就更新。
final ValueNotifier<Map<String, String>> mapNames = ValueNotifier<Map<String, String>>(const {});

/// 给人看的地图名：起了名用名字，没起用地图号。
String mapName(Object? id) {
  final k = '${id ?? ''}';
  final n = mapNames.value[k];
  return n == null || n.isEmpty ? k : n;
}

/// 从站点回的 `map_names`（`{地图号: 名字}`）更新；不是 Map 不动（老站点没这一项）。
void updateMapNames(Object? raw) {
  if (raw is! Map) return;
  final next = <String, String>{
    for (final e in raw.entries)
      if (e.value is String && (e.value as String).isNotEmpty) '${e.key}': e.value as String,
  };
  if (!mapEquals(next, mapNames.value)) mapNames.value = next;
}
