import 'package:flutter/foundation.dart';

/// 易用性 37 场景测试：账号 → 人名（管理员在人员页起的）。站点在 `/api/robots`（`person_names`）里给，拉到就更新；
/// 「谁接的、谁派的、谁叫停的」都显示人名，没起名的照旧显示登录名。
final ValueNotifier<Map<String, String>> personNames = ValueNotifier<Map<String, String>>(const {});

/// 给人看的名字：起了名用名字，没起用登录名。
String personName(Object? login) {
  final k = '${login ?? ''}';
  final n = personNames.value[k];
  return n == null || n.isEmpty ? k : n;
}

/// 从站点回的 `person_names`（`{登录名: 人名}`）更新；不是 Map 不动（老站点没这一项）。
void updatePersonNames(Object? raw) {
  if (raw is! Map) return;
  final next = <String, String>{
    for (final e in raw.entries)
      if (e.value is String && (e.value as String).isNotEmpty) '${e.key}': e.value as String,
  };
  if (!mapEquals(next, personNames.value)) personNames.value = next;
}
