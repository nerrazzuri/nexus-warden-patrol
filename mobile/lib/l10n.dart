/// 中英文（App V2，视觉规范第十节）：**英文为主，中文可选**。
///
/// 写法是把两种文字并排写在用的地方：`tr('E-STOP ALL', '全部急停')`。带变量的照常插值，两边各写各的：
/// `tr('$n robots', '$n 台机器人')`。这样词条不会跟界面漂开（没有 key、没有另一份表要对），也不需要
/// `BuildContext`（网络层报错的文字同样走它）。代价是加第三种语言要改每一处 —— 现在只定了两种。
///
/// 站点给的文字（告警标题、原因）是中文：告警标题按种类查 `design/alert_titles.g.dart`（跟网页值班台
/// 同一份词条），不认识的种类才用站点给的原文。
library;

import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart';

import 'design/alert_titles.g.dart';
import 'net/site_text.dart' show guardStuckTitleEn, zhPunct;

enum AppLang { en, zh }

/// 现在用哪种文字。换了之后 `PatrolApp` 整棵重建。
final ValueNotifier<AppLang> appLang = ValueNotifier<AppLang>(AppLang.en);

/// 界面文字：英文、中文各写一遍，按当前语言取。
String tr(String en, String zh) => appLang.value == AppLang.zh ? zh : en;

/// 告警标题：英文界面按种类查词条；中文界面用站点给的原文（它带着当时的细节，比如「(授权已不适用)」）。
/// 种类不认识（站点比 app 新）也用站点原文。
/// 站点给告警测试模式期间的告警标题加的前缀（站点 alert_store.TEST_PREFIX）；英文界面换成 "TEST: "，
/// 不然演练看着跟真告警一样（外审 r1 #9）。
const String kAlertTestPrefix = '测试：';

String alertTitle(String kind, String siteTitle) {
  // 第 9 轮 W9-10：站点给的标题多用半角「:,(」，挨着汉字的换成全角（跟网页一样）
  if (appLang.value == AppLang.zh && siteTitle.isNotEmpty) return zhPunct(siteTitle);
  // 用户 11-26：值守的机器人被困 90 秒（换车 / 指定了它没换）—— 写清是哪台、多久
  final bare = siteTitle.startsWith(kAlertTestPrefix) ? siteTitle.substring(kAlertTestPrefix.length) : siteTitle;
  final held = kind == 'guard_stuck' ? guardStuckTitleEn(bare) : null;
  if (held != null) return '${siteTitle.startsWith(kAlertTestPrefix) ? 'TEST: ' : ''}$held';
  // 第十六轮 P2：回原点那一趟没成（撤防收队、手动叫回）跟「未返回待命点」同一个种类，标题分开说
  if (kind == 'standby_failed' && bare == '回原点失败') {
    return '${siteTitle.startsWith(kAlertTestPrefix) ? 'TEST: ' : ''}Did not return to home point';
  }
  final e = alertTitles[kind];
  if (e == null) return siteTitle;
  final title = appLang.value == AppLang.zh ? e.$2 : e.$1;
  return siteTitle.startsWith(kAlertTestPrefix) ? 'TEST: $title' : title;
}

/// App 用的那一份语言存储（`main()` 里设）；测试不设（不落盘）。
LangStore? langStoreRef;

/// 换语言并存下来（站点列表、设置页都走这里）。存不上只是下次打开还是原来的语言，不挡这一次。
Future<void> setAppLang(AppLang lang, {LangStore? store}) async {
  if (lang == appLang.value) return;
  appLang.value = lang;
  try {
    await (store ?? langStoreRef)?.save(lang);
  } catch (_) {
    // 同上
  }
}

/// 用户 11-27（新人易用性报告 I）：没选过语言就跟手机（系统）语言走 —— 系统首选是中文就中文，别的都英文。
AppLang systemLang(Iterable<String> languageCodes) =>
    languageCodes.isNotEmpty && languageCodes.first.toLowerCase() == 'zh' ? AppLang.zh : AppLang.en;

/// 语言选了哪种存在哪儿。只存这一项；文件坏了、没有，都当没选过（[fallback]，App 开机时给系统语言）。
class LangStore {
  final File file;
  const LangStore(this.file);

  Future<AppLang> load({AppLang fallback = AppLang.en}) async {
    try {
      if (!await file.exists()) return fallback;
      final raw = jsonDecode(await file.readAsString());
      if (raw is Map && raw['lang'] == 'zh') return AppLang.zh;
      if (raw is Map && raw['lang'] == 'en') return AppLang.en;
      return fallback;
    } catch (_) {
      return fallback;
    }
  }

  Future<void> save(AppLang lang) async {
    final tmp = File('${file.path}.tmp');
    await tmp.writeAsString(jsonEncode(<String, String>{'lang': lang.name}), flush: true);
    await tmp.rename(file.path);
  }
}
