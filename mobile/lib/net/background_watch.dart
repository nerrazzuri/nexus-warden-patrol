/// 后台值守（W17，决策 30）的开关。真正值守的是 Android 原生服务（`WatchService.kt`）：app 退到后台、
/// 被划掉之后照样连着站点、P1 弹通知、响铃那一档闹钟声响到有人处理。凭据是站点发的**值守令牌**
/// （只能看告警、30 天、注销即作废），不是登录会话（12 小时就到期）。
///
/// 桌面版、测试里没有后台服务：[supported] 为假，界面上不显示开关（桌面版本来就开着窗口值守）。
library;

import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';

import '../design/alert_titles.g.dart';
import '../l10n.dart';

abstract class BackgroundWatch {
  bool get supported;

  /// 开始（或换一套凭据接着）值守。
  Future<void> start(
      {required String site, required String url, required String fingerprint, required String token});

  /// 停：服务那边顺手注销值守令牌（站点上当场作废）。
  Future<void> stop();

  Future<bool> running();
}

class ChannelBackgroundWatch implements BackgroundWatch {
  static const MethodChannel _ch = MethodChannel('nexwar/watch');
  const ChannelBackgroundWatch();

  @override
  bool get supported => Platform.isAndroid;

  @override
  Future<void> start(
      {required String site,
      required String url,
      required String fingerprint,
      required String token}) async {
    if (!supported) return;
    // 手机 App 测试 M05：后台服务的通知按 App 的语言说；英文报警标题用 App 的那张表
    await _ch.invokeMethod<bool>('start', <String, String>{
      'site': site,
      'url': url,
      'fingerprint': fingerprint,
      'token': token,
      'lang': appLang.value.name,
      'titles': jsonEncode(<String, String>{for (final e in alertTitles.entries) e.key: e.value.$1}),
    });
  }

  @override
  Future<void> stop() async {
    if (!supported) return;
    await _ch.invokeMethod<bool>('stop');
  }

  @override
  Future<bool> running() async => supported && (await _ch.invokeMethod<bool>('running') ?? false);
}

/// 手机 App 测试 M01：底部导航的页面按返回键 = 把 App 退到后台（像按 Home 键），不退出登录、后台值守接着跑。
Future<void> moveAppToBackground() async {
  if (!Platform.isAndroid) return;
  try {
    await const MethodChannel('nexwar/watch').invokeMethod<bool>('background');
  } catch (_) {}
}

/// 后台值守开关的状态（W55：开关从机器人栏顶上挪到「设置」页）。机器人栏（`SiteRobotsPage`）一直活着，管真正的
/// 开、停（进站点自动开，离开站点就停）；设置页看它、点它。
class WatchControl extends ChangeNotifier {
  bool _on = false;
  bool _busy = false;
  Future<void> Function()? _toggle;

  bool get on => _on;
  bool get busy => _busy;

  /// 这台设备、这个站点能不能后台值守（桌面版没有）。
  bool get available => _toggle != null;

  void bind(Future<void> Function() toggle) {
    _toggle = toggle;
    notifyListeners();
  }

  /// 机器人栏关掉时解开（不通知：那时候整棵树在拆）。
  void unbind() => _toggle = null;

  void report({required bool on, required bool busy}) {
    if (on == _on && busy == _busy) return;
    _on = on;
    _busy = busy;
    notifyListeners();
  }

  Future<void> toggle() async => _toggle?.call();
}

/// App V2 来报警全屏页：后台值守的全屏通知拉起 App 时交过来的那一条（原生 `MainActivity`）。
class RingRequest {
  final String key;
  final Map<String, dynamic> alert;

  /// 值守的站点名（跟外壳的标题比：别的站点的不在这个站点里弹）。
  final String site;
  const RingRequest(this.key, this.alert, this.site);

  static RingRequest? fromChannel(Object? raw) {
    if (raw is! Map) return null;
    final key = '${raw['key'] ?? ''}';
    if (key.isEmpty) return null;
    Map<String, dynamic> alert;
    try {
      final j = jsonDecode('${raw['alert'] ?? '{}'}');
      alert = j is Map ? Map<String, dynamic>.from(j) : <String, dynamic>{};
    } on FormatException {
      alert = <String, dynamic>{};
    }
    return RingRequest(key, alert, '${raw['site'] ?? ''}');
  }
}

/// 等着弹的来报警（外壳在的时候接走、清掉）。
final ValueNotifier<RingRequest?> pendingRing = ValueNotifier<RingRequest?>(null);

/// App 启动时接上：原生拉起时那一条、之后 App 开着又来的。只有 Android 有。
Future<void> initRingChannel() async {
  if (!Platform.isAndroid) return;
  const ch = MethodChannel('nexwar/watch');
  ch.setMethodCallHandler((call) async {
    if (call.method == 'ring') pendingRing.value = RingRequest.fromChannel(call.arguments) ?? pendingRing.value;
    return null;
  });
  try {
    final r = RingRequest.fromChannel(await ch.invokeMethod<Object?>('pendingRing'));
    if (r != null) pendingRing.value = r;
  } on PlatformException {
    return;
  } on MissingPluginException {
    return;
  }
}

/// 「静音 2 分钟」：后台值守那边这台手机先不出声，到点没人确认接着响。没在值守（桌面版、没开）回 false。
/// 前台响铃的静音（外审 App-V2-1 #5）：告警键 → 静到几点（毫秒）。来报警页「静音 2 分钟」写这里，
/// 前台一直响的那一套（机器人列表页的铃）看这里，跟后台通知的静音同一个截止时间。
final Map<String, int> ringMutedUntil = <String, int>{};

/// 这一条现在是不是静着（过了点就不算，顺手清掉）。
bool ringMuted(String key, [DateTime Function() now = DateTime.now]) {
  final until = ringMutedUntil[key];
  if (until == null) return false;
  if (now().millisecondsSinceEpoch < until) return true;
  ringMutedUntil.remove(key);
  return false;
}

Future<bool> muteRing(String key) async {
  if (!Platform.isAndroid) return false;
  try {
    return await const MethodChannel('nexwar/watch').invokeMethod<bool>('mute', <String, String>{'key': key}) ?? false;
  } on PlatformException {
    return false;
  } on MissingPluginException {
    return false;
  }
}

/// 来报警这一页处理完了：锁屏上不再显示 App。
Future<void> ringDone() async {
  if (!Platform.isAndroid) return;
  try {
    await const MethodChannel('nexwar/watch').invokeMethod<bool>('ringDone');
  } on PlatformException {
    return;
  } on MissingPluginException {
    return;
  }
}
