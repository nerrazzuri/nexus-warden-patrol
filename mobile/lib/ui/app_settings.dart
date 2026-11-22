/// 设置（W55，用户 2026-10-31 定）：设置类的都在这一页 —— 语言；通知与值守（后台值守开关、P1 推送状态）；
/// 关于与更新（App 版本、检查更新、开源许可）；工程师工具（站点列表进来时：用解绑令解绑机器人）。
///
/// 入口：站点列表右上角的齿轮；进了站点在「管理」/「我的」栏（经理在「日程」栏右上角）。
library;

import 'package:flutter/material.dart';

import '../l10n.dart';
import '../net/data_saver.dart';
import '../net/app_update.dart';
import '../net/background_watch.dart';
import '../net/push.dart';
import '../net/site_client.dart';
import 'app_update_ui.dart';
import 'arrival_alert.dart';
import 'nw/nw_p4_admin.dart' show NwListView, NwListCard, nwGap8, nwGap16;
import 'nw/nw_ask.dart';
import 'nw/nw_theme.dart';
import 'nw/nw_widgets.dart';
import 'problem_report.dart';
import 'robot_bind_page.dart';
import 'site_health.dart' show shareBundle;

/// 进了站点以后由外壳（`NwShell`）挂上：设置页要的后台值守、推送、更新从这里拿。
class SettingsHost extends InheritedWidget {
  final WatchControl? watch;
  final PushSession? push;
  final AppUpdater? Function(SiteApi api)? updater;
  const SettingsHost({super.key, required super.child, this.watch, this.push, this.updater});

  static SettingsHost? maybeOf(BuildContext context) =>
      context.dependOnInheritedWidgetOfExactType<SettingsHost>();

  @override
  bool updateShouldNotify(SettingsHost oldWidget) =>
      watch != oldWidget.watch || push != oldWidget.push || updater != oldWidget.updater;
}

/// 从站点里打开设置。
Future<void> openSettings(BuildContext context, SiteApi api) {
  final h = SettingsHost.maybeOf(context);
  return Navigator.push(
      context,
      MaterialPageRoute<void>(
          builder: (_) => AppSettingsPage(api: api, watch: h?.watch, push: h?.push, updater: h?.updater)));
}

class AppSettingsPage extends StatefulWidget {
  /// 登录着的站点；站点列表进来的是 null（没有值守、推送、检查更新，多一组工程师工具）。
  final SiteApi? api;
  final WatchControl? watch;
  final PushSession? push;
  final AppUpdater? Function(SiteApi api)? updater;

  /// 语言存哪儿；不给用 [langStoreRef]（`main()` 里设的）。
  final LangStore? langStore;

  const AppSettingsPage({super.key, this.api, this.watch, this.push, this.updater, this.langStore});

  static const Key problemKey = Key('settings-problem');
  static const Key langKey = Key('lang-switch');
  static const Key watchKey = Key('btn-bg-watch');
  static const Key pushKey = Key('push-state');
  static const Key versionKey = Key('app-version');
  static const Key checkUpdateKey = Key('app-check-update');
  static const Key licensesKey = Key('app-licenses');
  static const Key unbindKey = Key('engineer-unbind');
  static const Key engineerKey = Key('engineer-tools');
  static const Key arrivalKey = Key('arrival-alerts');
  static const Key dataSaverKey = Key('data-saver');

  @override
  State<AppSettingsPage> createState() => _AppSettingsPageState();
}

class _AppSettingsPageState extends State<AppSettingsPage> with NwAsk {
  bool _checking = false;

  Future<void> _setLang(AppLang lang) async {
    if (lang == appLang.value) return;
    // 易用性第 6 轮 A6-06：换语言留在这一页、登录还在（PatrolApp 只重画），不用再先问
    await setAppLang(lang, store: widget.langStore);
  }

  Future<void> _checkUpdate(AppUpdater u) async {
    setState(() => _checking = true);
    Map<String, dynamic>? info;
    String? why;
    try {
      info = await u.check();
    } on SiteError catch (e) {
      why = e.status == 404 ? tr('This site does not distribute the app', '此站点未提供 App 安装包') : refusalText(e);
    }
    if (!mounted) return;
    setState(() => _checking = false);
    if (info == null) {
      ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(why ?? tr('This is the latest version', '已是最新版本'))));
      return;
    }
    final v = '${info['version'] ?? ''}';
    final go = await askYes(tr('Version $v is available', '有新版本 $v'),
        body: tr('Download and install it now?', '是否立即下载安装？'),
        cancel: tr('Later', '稍后'),
        ok: tr('Update', '更新'),
        okKey: const Key('app-update-go'));
    if (go && mounted) await runAppUpdate(context, u, info);
  }

  @override
  Widget build(BuildContext context) {
    final c = Nw.of(context);
    final api = widget.api;
    final watch = widget.watch;
    final push = widget.push;
    final updater = api == null ? null : widget.updater?.call(api);
    TextStyle sub() => NwText.bodySmall.copyWith(color: c.textSecondary);
    return Scaffold(
      appBar: AppBar(title: Text(tr('Settings', '设置'))),
      body: NwListView(children: [
        askStrip(margin: const EdgeInsets.only(bottom: Nw.s16)),
        NwSectionLabel(tr('General', '通用')),
        nwGap8,
        NwListCard(children: [
          // App V2 稿 S-settings：语言是两段等宽开关；外观按页面定（「现在」深色、设置类页面浅色）
          Padding(
            padding: const EdgeInsets.fromLTRB(Nw.s16, Nw.s16, Nw.s16, Nw.s8),
            child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
              Text(tr('Language', '语言'), style: NwText.labelMedium.copyWith(color: c.textSecondary)),
              const SizedBox(height: Nw.s8),
              SegmentedButton<AppLang>(
                  key: AppSettingsPage.langKey,
                  showSelectedIcon: false,
                  style: SegmentedButton.styleFrom(
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(2)),
                      selectedBackgroundColor: c.primary,
                      selectedForegroundColor: c.onPrimary),
                  segments: const [
                    ButtonSegment(value: AppLang.en, label: Text('English')),
                    ButtonSegment(value: AppLang.zh, label: Text('中文')),
                  ],
                  selected: {appLang.value},
                  onSelectionChanged: (v) => _setLang(v.first)),
              const SizedBox(height: Nw.s16),
              Text(tr('Appearance', '外观'), style: NwText.labelMedium.copyWith(color: c.textSecondary)),
              const SizedBox(height: Nw.s4),
              Text(tr('Per screen: Now is dark, setup screens are light.', '按页面：「现在」是深色，设置类页面是浅色。'),
                  style: NwText.bodyMedium.copyWith(color: c.text)),
            ]),
          ),
        ]),
        if (api != null) ...[
          nwGap16,
          NwSectionLabel(tr('Notifications & monitoring', '通知与值守')),
          nwGap8,
          NwListCard(children: [
            if (watch != null && watch.available)
              ListenableBuilder(
                  listenable: watch,
                  builder: (_, _) => SwitchListTile(
                        key: AppSettingsPage.watchKey,
                        secondary: Icon(watch.on ? Icons.shield : Icons.shield_outlined,
                            color: watch.on ? c.success : c.textSecondary),
                        title: Text(tr('Background monitoring', '后台值守')),
                        subtitle: Text(
                            tr('Keep receiving P1 alarms when the app is in the background',
                                'App 在后台时继续接收 P1 报警'),
                            style: sub()),
                        value: watch.on,
                        onChanged: watch.busy ? null : (_) => watch.toggle(),
                      )),
            if (push != null && push.state.value != PushState.off)
              ValueListenableBuilder<PushState>(
                  valueListenable: push.state,
                  builder: (_, st, _) => ListTile(
                        key: AppSettingsPage.pushKey,
                        leading: Icon(st == PushState.ready ? Icons.notifications_on : Icons.notifications_paused,
                            color: st == PushState.ready ? c.success : c.textSecondary),
                        title: Text(tr('P1 push', 'P1 推送')),
                        subtitle: Text(
                            st == PushState.ready
                                ? tr('Ready', '已就绪')
                                : push.reason,
                            style: sub()),
                      )),
            ValueListenableBuilder<bool>(
                valueListenable: arrivalAlerts,
                builder: (_, on, _) => SwitchListTile(
                      key: AppSettingsPage.arrivalKey,
                      secondary: Icon(on ? Icons.where_to_vote : Icons.where_to_vote_outlined,
                          color: on ? c.success : c.textSecondary),
                      title: Text(tr('Waypoint arrival alerts', '巡逻到点提醒')),
                      subtitle: Text(
                          tr('Sound and vibrate at each patrol point (for on-site tests; off after the app restarts)',
                              '每到一个巡逻点就响铃、震动（现场测试用，App 重启后自动关闭）'),
                          style: sub()),
                      value: on,
                      onChanged: (v) => arrivalAlerts.value = v,
                    )),
            ValueListenableBuilder<bool>(
                valueListenable: dataSaver,
                builder: (_, on, _) => SwitchListTile(
                      key: AppSettingsPage.dataSaverKey,
                      secondary: Icon(on ? Icons.data_saver_on : Icons.data_saver_off,
                          color: on ? c.success : c.textSecondary),
                      title: Text(tr('Data saver', '省流量')),
                      subtitle: Text(
                          tr('Smaller, slower video (about 2 frames a second). Turn on when watching over mobile data.',
                              '画面变小、每秒约 2 帧。用手机流量看的时候打开。'),
                          style: sub()),
                      value: on,
                      onChanged: setDataSaver,
                    )),
          ]),
        ],
        nwGap16,
        NwSectionLabel(tr('About & updates', '关于与更新')),
        nwGap8,
        NwListCard(children: [
          ListTile(
            key: AppSettingsPage.versionKey,
            leading: const Icon(Icons.info_outline_rounded),
            title: Text(tr('App version', 'App 版本')),
            subtitle: Text(tr('$appVersion (build $appBuild) · API level $appApiLevel',
                '$appVersion（构建 $appBuild）· 接口级别 $appApiLevel'), style: sub()),
          ),
          if (updater != null)
            ListTile(
              key: AppSettingsPage.checkUpdateKey,
              leading: const Icon(Icons.system_update_rounded),
              title: Text(tr('Check for updates', '检查更新')),
              subtitle: Text(tr('New versions are distributed by this site', '新版本由当前站点分发'), style: sub()),
              trailing: _checking
                  ? const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2))
                  : null,
              onTap: _checking ? null : () => _checkUpdate(updater),
            ),
          // 日志设计 第 6 条：谁都能传日志（不要权限），站点开问题单、给编号，工程师按编号取
          ListTile(
            key: AppSettingsPage.problemKey,
            leading: const Icon(Icons.bug_report_outlined),
            title: Text(tr('Report a problem', '报问题')),
            subtitle: Text(tr('Something went wrong? Send logs to the engineer', '遇到问题？把日志发给工程师'), style: sub()),
            onTap: () => openProblemReport(context, api),
          ),
          ListTile(
            key: AppSettingsPage.licensesKey,
            leading: const Icon(Icons.description_outlined),
            title: Text(tr('Open-source licenses', '开源许可')),
            onTap: () => showLicensePage(
                context: context, applicationName: 'Nexus Warden', applicationVersion: '$appVersion+$appBuild'),
          ),
        ]),
        if (api == null) ...[
          nwGap16,
          NwSectionLabel(tr('Engineer tools', '工程师工具')),
          nwGap8,
          // 手机 App 测试 M23：没登录的人随手能看到「解绑机器人」—— 收起来，展开前说清楚是给谁用的
          NwListCard(children: [
            ExpansionTile(
              key: AppSettingsPage.engineerKey,
              leading: const Icon(Icons.engineering_outlined),
              title: Text(tr('For installation engineers', '安装工程师专用')),
              subtitle: Text(tr('Only when the site is lost. Not needed in daily use.', '只在站点坏了时用，平常用不到。'), style: sub()),
              children: [
            ListTile(
              key: AppSettingsPage.unbindKey,
              leading: const Icon(Icons.build_circle_outlined),
              title: Text(tr('Unbind a robot with a token', '用解绑令解绑机器人')),
              subtitle: Text(tr('When the site is lost and has no backup', '站点损坏且无备份时使用'), style: sub()),
              onTap: () => Navigator.push(
                  context, MaterialPageRoute<void>(builder: (_) => const EngineerUnbindPage())),
            ),
              ]),
          ]),
        ],
      ]),
    );
  }
}

/// 打开上传日志页（设置页、「我的」页共用）：先取机器人列表给下拉框，取不到就不选机器人照样能传。
Future<void> openProblemReport(BuildContext context, SiteApi? api) async {
  final nav = Navigator.of(context);
  var ids = <String>[];
  if (api != null) {
    try {
      ids = [for (final r in await api.robots()) '${r['robot_id']}'];
    } on Object {
      ids = <String>[];
    }
  }
  await nav.push(MaterialPageRoute<void>(builder: (_) => ProblemReportPage(api: api, robots: ids, share: shareBundle)));
}
