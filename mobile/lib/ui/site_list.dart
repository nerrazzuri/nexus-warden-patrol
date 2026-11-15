/// 站点列表（W00c4）：存着的站点一个一张卡，点了去登录页、登上了进站点；右上换语言、添加，底下也能添加。
/// 登录之后进的是带底部导航的外壳（`nw/nw_shell.dart`）。
/// 2026-10-14 按设计稿重做（P1）：选站点是设计稿的 Site Selection，登录从弹窗改成一页（[SiteLoginPage]）。
library;

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../l10n.dart';
import '../net/background_watch.dart';
import '../net/push.dart';
import '../net/site_client.dart';
import '../store/site_store.dart';
import 'app_settings.dart';
import '../model/alert.dart';
import 'nw/nw_p1_entry.dart';
import 'nw/nw_ring.dart';
import 'nw/nw_shell.dart';
import 'nw/nw_theme.dart';
import 'nw/nw_widgets.dart';
import '../net/pairing.dart';
import 'problem_report.dart';
import 'site_add.dart';
import 'site_health.dart' show shareBundle;
import 'site_scan.dart';

const Key newCodeFieldKey = Key('site-new-code');
const Key newCodeOkKey = Key('site-new-code-ok');
const Key newCodeScanKey = Key('site-new-code-scan');

/// 造一个站点客户端。测试换成假的。
typedef SiteApiFactory = SiteApi Function(SiteEntry site);

SiteApi defaultSiteApi(SiteEntry s) => SiteClient(s.url, s.fingerprint);

class SiteListPage extends StatefulWidget {
  final SiteStore store;
  final SiteApiFactory apiFactory;
  /// 后台值守（W17）：测试换成假的。
  final BackgroundWatch watch;
  /// P1 推到手机（商业化 A6）：测试换成假的；缺省按平台（手机上是极光，桌面版不推）。
  final PushRegistrar? push;
  /// 语言存哪儿（App V2）；不给就只在这次运行里生效。
  final LangStore? langStore;
  /// 扫配对码（App V2）：测试换成假的；缺省手机上开相机，桌面版没有扫码按钮。
  final CodeScanner? scanner;
  const SiteListPage(
      {super.key,
      required this.store,
      this.apiFactory = defaultSiteApi,
      this.watch = const ChannelBackgroundWatch(),
      this.push,
      this.langStore,
      this.scanner});

  /// 右上角齿轮：设置（W55，语言、工程师工具、App 版本）。
  static const Key settingsKey = Key('open-settings');
  static const Key removeOkKey = Key('site-remove-ok');

  @override
  State<SiteListPage> createState() => _SiteListPageState();
}

class _SiteListPageState extends State<SiteListPage> {
  List<SiteEntry> _sites = <SiteEntry>[];

  /// 卡片最宽这么多（桌面版的大窗口上不拉满）。
  static const double _maxWidth = 720;

  /// 站点文件读不出来（坏了）。这时**不许**添加或删除：一保存就把坏文件里的其余站点覆盖掉了。
  String? _loadError;

  @override
  void initState() {
    super.initState();
    pendingRing.addListener(_onRing);
    widget.store.load().then((s) {
      if (mounted) setState(() => _sites = s);
      _sitesLoaded = true;
      _onRing(); // 冷启动：报警可能比站点列表先到
    }, onError: (Object e) {
      if (mounted) setState(() => _loadError = '$e');
      _sitesLoaded = true;
      _onRing();
    });
  }

  @override
  void dispose() {
    pendingRing.removeListener(_onRing);
    super.dispose();
  }

  /// 已经整屏弹过的那一条（同一条不重复弹）。
  String? _ringShown;
  bool _sitesLoaded = false;

  /// 外审 App-V2-3 I5：还没登录（没有外壳开着）时来了报警 —— App 被系统收了、报警把它冷启动起来 ——
  /// 照样整屏弹来报警页（能看、能静音），「登录后处理」去那个站点的登录页；登上了外壳接着弹这一条。
  void _onRing() {
    final r = pendingRing.value;
    if (r == null || !mounted || !_sitesLoaded || liveShells > 0 || _ringShown == r.key) return;
    final site = _sites.where((e) => r.isFor(name: e.name, urls: e.urls, fingerprint: e.fingerprint)).firstOrNull;
    _ringShown = r.key;
    final a = Alert.fromWire(<String, dynamic>{...r.alert, 'key': r.key});
    unawaited(Navigator.of(context).push(MaterialPageRoute<void>(
        fullscreenDialog: true,
        builder: (_) => RingPage(
            api: null,
            alert: a,
            site: site?.name ?? r.site,
            onSignIn: site == null ? null : () => unawaited(_open(site))))));
  }

  /// 换掉列表里的一条（按身份找；找不到就不动）、存下来。
  Future<void> _replace(SiteEntry old, SiteEntry? upd) async {
    final next = [
      for (final x in _sites)
        if (!identical(x, old)) x else ?upd,
    ];
    await widget.store.save(next);
    if (mounted) setState(() => _sites = next);
  }

  /// 添加站点（App V2）：扫码、粘贴配对码或手填，都在 `SiteAddPage`；这里只管存。
  Future<void> _add() async {
    final entry = await Navigator.push<SiteEntry>(context,
        MaterialPageRoute<SiteEntry>(builder: (_) => SiteAddPage(scanner: widget.scanner, existing: _sites)));
    if (entry == null || !mounted) return;
    // M21：新加的放最上面（以前在最底下只露半张），并说一声
    final next = [entry, ..._sites];
    await widget.store.save(next);
    if (!mounted) return;
    setState(() => _sites = next);
    // 稿 E-add「保存并登录」：存好直接去登录页
    await _open(entry);
  }

  Future<void> _open(SiteEntry s) async {
    String? account0;
    String? used;
    final messenger = ScaffoldMessenger.of(context);
    final nav = Navigator.of(context);
    // 口令在登录页上收（2026-10-14 重做：原来是弹窗）。登录不了人留在那一页、原因摆在那一页上，
    // 改了能再试；登上了那一页带着连好的客户端退回来，下面的顺序跟原来一样。
    final api = await nav.push<SiteApi>(MaterialPageRoute<SiteApi>(
        builder: (_) => SiteLoginPage(
            site: s,
            signIn: (account, password) async {
              // POC 11-05：同一个站点几个地址（不同网）：按顺序试，连不上（状态 0）换下一个
              final errs = <String>[];
              for (final u in s.urls) {
                SiteApi? api;
                try {
                  api = widget.apiFactory(s.copyWith(url: u));
                  await api.login(account, password);
                } on SiteError catch (e) {
                  api?.close();
                  // 证书变了 = 已经找到这台站点主机了：别的地址也是同一张证书，不用再试（M03）
                  if (e.status != 0 || e.certChanged || s.urls.length == 1) rethrow;
                  errs.add(tr('$u: ${e.message}', '$u：${e.message}'));
                  continue;
                } catch (_) {
                  api?.close();
                  rethrow;
                }
                account0 = account;
                used = u;
                return api;
              }
              throw SiteError(0, errs.join('\n'));
            },
            // 手机 App 测试 M03：证书变了，登录页上直接「新站点码」：只换地址和指纹（名字、账号、备用地址留着）。
            // 下面登录用的是换过的 s（闭包抓的是变量）。
            scanner: widget.scanner ?? (canScanCodes ? scanSiteCode : null),
            updateCode: (raw) async {
              final p = decodePairing(raw);
              final upd = s.copyWith(url: p.url, fingerprint: p.fingerprint, alts: s.alts.where((u) => u != p.url).toList());
              await _replace(s, upd);
              s = upd;
              return upd;
            },
            // POC 11-05：同一个站点在别的网里的地址
            saveAlts: (alts) async {
              final upd = s.copyWith(alts: alts.where((u) => u != s.url).toList());
              await _replace(s, upd);
              s = upd;
              return upd;
            },
            remove: () => _replace(s, null),
            openAnon: () => widget.apiFactory(s),
            // W52：没有账号就在这里申请（不用登录），管理员批了直接用这个账号登录
            apply: (name, display, password) async {
              final api = widget.apiFactory(s);
              try {
                await api.applyAccount(name, display, password);
              } finally {
                api.close();
              }
            })));
    if (api == null) return;
    final a = api;
    // 记下这次登录用的账号（下次登录页自动填好）、登上的地址（下次先试它）
    if ((account0 != null && account0 != s.username) || (used != null && used != s.url)) {
      final upd = (used == null ? s : s.preferring(used!)).copyWith(username: account0);
      await _replace(s, upd);
      s = upd;
    }
    // 商业化 A6：进了站点就收这个站点的 P1 推送。登记不上不挡进站点（后台值守照旧），退避一直重试，
    // 页面上看得见没登记上（A6 外审 F2）。
    final push = PushSession(widget.push ?? defaultPush(),
        also: widget.push == null ? defaultAlsoPush() : const <PushRegistrar>[],
        register: (id, platform, provider) => a.pushRegister(id, platform, provider: provider),
        unregister: a.pushUnregister)
      ..start();
    final why = await nav.push<String>(MaterialPageRoute<String>(
        builder: (_) => NwShell(
            api: a, title: s.name, entry: s, watch: widget.watch, push: push)));
    // 离开就注销：不然令牌在站点上还能用半小时。推送先停、注销推送号（在路上的登记落定了再注销，
    // A6 外审 F3），再注销会话（站点那头推送号跟这次登录绑着，退出了也不再推）。
    await push.stop();
    try {
      if (a.session != null) await a.logout();
    } catch (_) {}
    a.close();
    if (why != null) messenger.showSnackBar(SnackBar(content: Text(why)));
  }

  Future<void> _problem() => Navigator.push(
      context, MaterialPageRoute<void>(builder: (_) => ProblemReportPage(api: null, share: shareBundle)));

  @override
  Widget build(BuildContext context) => nwEntryTheme(Builder(builder: _build));

  Widget _build(BuildContext context) {
    final c = Nw.of(context);
    final broken = _loadError != null;
    final shape = RoundedRectangleBorder(borderRadius: BorderRadius.circular(2));
    // App V2 稿 E-sites：深色；一个站点一行（名字、账号、地址），底下「扫码添加站点 | 报问题」一排等宽
    return Scaffold(
      backgroundColor: c.bg,
      body: SafeArea(
          child: Align(
              alignment: Alignment.topCenter,
              child: ConstrainedBox(
                  constraints: const BoxConstraints(maxWidth: _maxWidth),
                  child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                    Padding(
                        padding: const EdgeInsets.fromLTRB(Nw.s16, Nw.s16, Nw.s16, Nw.s8),
                        child: Row(children: [
                          Expanded(
                              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                            Text('NEXUS WARDEN',
                                style: NwText.labelSmall.copyWith(
                                    color: c.textSecondary, fontWeight: FontWeight.w700, letterSpacing: 1.2)),
                            Text(tr('Select site', '选择站点'),
                                style: NwText.headlineSmall.copyWith(color: c.text, fontWeight: FontWeight.w700)),
                          ])),
                          // W55：语言、工程师工具（解绑令）、App 版本都在「设置」里
                          SizedBox(
                              width: 44,
                              height: 36,
                              child: OutlinedButton(
                                  key: SiteListPage.settingsKey,
                                  style: OutlinedButton.styleFrom(
                                      padding: EdgeInsets.zero, shape: shape, side: BorderSide(color: c.textMuted)),
                                  onPressed: () => Navigator.push(context,
                                      MaterialPageRoute<void>(builder: (_) => AppSettingsPage(langStore: widget.langStore))),
                                  child: Icon(Icons.settings_outlined,
                                      size: 20, color: c.text, semanticLabel: tr('Settings', '设置')))),
                        ])),
                    Expanded(
                        child: broken
                            ? Center(
                                child: SingleChildScrollView(
                                    padding: const EdgeInsets.all(Nw.s24),
                                    child: Column(mainAxisSize: MainAxisSize.min, children: [
                                      Icon(Icons.error_outline_rounded, size: 48, color: c.error),
                                      const SizedBox(height: Nw.s16),
                                      Text(tr("Can't read the site list: $_loadError", '无法读取站点列表：$_loadError'),
                                          key: const Key('site-load-error'),
                                          textAlign: TextAlign.center,
                                          style: NwText.bodyMedium.copyWith(color: c.text)),
                                    ])))
                            : ListView(padding: const EdgeInsets.fromLTRB(Nw.s16, Nw.s8, Nw.s16, Nw.s16), children: [
                                if (_sites.isEmpty)
                                  Padding(
                                      padding: const EdgeInsets.symmetric(vertical: Nw.s24),
                                      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                                        Text(tr('No sites yet.', '还没有站点。'),
                                            style: NwText.titleMedium.copyWith(color: c.text, fontWeight: FontWeight.w700)),
                                        const SizedBox(height: Nw.s4),
                                        Text(
                                            tr('Tap "Scan to add site" below and scan the site code on the duty console, or enter the address by hand.',
                                                '点下面「扫码添加站点」，扫值班台上的站点码，或者手填地址。'),
                                            style: NwText.bodyMedium.copyWith(color: c.textSecondary)),
                                      ])),
                                for (final s in _sites) ...[_row(c, s), const SizedBox(height: Nw.s8)],
                                if (_sites.isNotEmpty)
                                  Text(tr('Passwords are not stored on the phone; enter yours at each sign-in.', '密码不存在手机上，每次登录都要输。'),
                                      style: NwText.bodySmall.copyWith(color: c.textSecondary)),
                              ])),
                    Padding(
                        padding: const EdgeInsets.all(Nw.s16),
                        child: Row(children: [
                          // 站点文件坏了不给添加（见 _loadError）
                          if (!broken) ...[
                            Expanded(
                                child: FilledButton.icon(
                                    key: const Key('site-add'),
                                    style: FilledButton.styleFrom(
                                        minimumSize: const Size(48, 48),
                                        shape: shape,
                                        padding: const EdgeInsets.symmetric(horizontal: Nw.s8)),
                                    icon: const Icon(Icons.qr_code_scanner_rounded, size: 18),
                                    label: Text(tr('Scan to add site', '扫码添加站点'), overflow: TextOverflow.ellipsis),
                                    onPressed: _add)),
                            const SizedBox(width: Nw.s8),
                          ],
                          Expanded(
                              child: OutlinedButton(
                                  key: const Key('site-problem'),
                                  style: OutlinedButton.styleFrom(
                                      minimumSize: const Size(48, 48),
                                      shape: shape,
                                      foregroundColor: c.text,
                                      side: BorderSide(color: c.textMuted)),
                                  onPressed: _problem,
                                  child: Text(tr('Report a problem', '报问题'), overflow: TextOverflow.ellipsis))),
                        ])),
                  ])))),
    );
  }

  /// 一个站点一行。登录之前不知道连没连上、有没有 P1、是什么角色：不显示这几样（不编）。
  Widget _row(NwColors c, SiteEntry s) => Material(
      color: c.surface,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(2), side: BorderSide(color: c.outline)),
      child: InkWell(
          key: Key('site-enter-${s.name}'),
          onTap: () => _open(s),
          child: Padding(
              padding: const EdgeInsets.all(Nw.s16),
              child: Row(children: [
                Expanded(
                    child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text(s.name,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: NwText.titleMedium.copyWith(color: c.text, fontWeight: FontWeight.w700)),
                  if (s.username.isNotEmpty)
                    Text(s.username, style: NwText.bodySmall.copyWith(color: c.textSecondary)),
                  Text(s.url,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: NwText.bodySmall.copyWith(color: c.textSecondary)),
                ])),
                Icon(Icons.chevron_right_rounded, color: c.textSecondary),
              ]))));
}

/// 进入页（App V2 稿 E-*）一律深色，不跟系统。
Widget nwEntryTheme(Widget child) => Theme(data: nwTheme(Brightness.dark), child: child);

/// 登录这个站点：拿口令去登，登上了回连好的客户端，登不上抛（原因给人看）。
/// 用账号、口令登录（账号添加站点时不填，第一次登录时输，之后记着；用户 10-30）。
/// 登录失败时站点说的申请状态（W52，站点原话是中文）按语言说。
String applyStateText(String site) {
  if (site.contains('等管理员批准')) {
    return tr('This account is still waiting for an administrator to approve it.', site);
  }
  if (site.contains('拒')) return tr('An administrator turned down this account application.', site);
  if (site.contains('过期')) {
    return tr('This account application expired (nobody approved it in 7 days). Apply again.', site);
  }
  return site;
}

typedef SiteSignIn = Future<SiteApi> Function(String account, String password);

/// 申请账号（W52）：账号名、给管理员看的名字、密码。
typedef SiteApply = Future<void> Function(String name, String display, String password);

/// 登录页（App V2 稿 E-login，深色）：顶栏站点名和地址；账号、密码、登录；证书变了琥珀一条 +「扫新码 | 其他地址」；
/// 底下「申请账号 | 报问题」一排等宽。站点卡上原来的「⋮」菜单（其他地址、更新站点码、删除）都在这一页上就地做，不弹窗。
/// 登上了带着客户端退回去（`Navigator.pop(context, api)`）；登不上留在这一页说原因。
class SiteLoginPage extends StatefulWidget {
  final SiteEntry site;
  final SiteSignIn signIn;
  /// 给了就有「申请账号」（W52）。
  final SiteApply? apply;

  /// 手机 App 测试 M03：换站点码（扫的或贴的那一行）。回换好的那一条；认不出来抛 [PairingException]。
  final Future<SiteEntry> Function(String raw)? updateCode;

  /// 备用地址（POC 11-05），一行一个。回换好的那一条。
  final Future<SiteEntry> Function(List<String> alts)? saveAlts;

  /// 从这台手机上删掉这个站点（删完这一页退出）。
  final Future<void> Function()? remove;

  /// 扫新码用；不给就只能贴。
  final CodeScanner? scanner;

  /// 日志设计 第 6 条：登不进去也能「上传日志」—— 给一个还没登录的站点连接（用完关掉）。
  final SiteApi Function()? openAnon;
  const SiteLoginPage(
      {super.key,
      required this.site,
      required this.signIn,
      this.apply,
      this.updateCode,
      this.saveAlts,
      this.remove,
      this.scanner,
      this.openAnon});

  static const Key problemKey = Key('login-problem');
  static const Key applyKey = Key('login-apply');
  static const Key newCodeKey = Key('login-new-code');
  static const Key altsKey = Key('login-alts');
  static const Key removeKey = Key('login-remove');
  static const Key msgKey = Key('login-msg');

  @override
  State<SiteLoginPage> createState() => _SiteLoginPageState();
}

enum _Panel { none, code, alts }

class _SiteLoginPageState extends State<SiteLoginPage> {
  late SiteEntry _site = widget.site;
  late final _account = TextEditingController(text: widget.site.username);
  final _pw = TextEditingController();
  final _code = TextEditingController();
  late final _alts = TextEditingController(text: widget.site.alts.join('\n'));

  /// 正在登：这时候不收第二次提交，也不许退出去（退了登上的那个会话就没人管了）。
  bool _busy = false;
  String? _error;

  /// 这次登不上是因为没连上站点（证书、网络），不是账号密码：密码框不标红（M03）。
  bool _notPassword = false;
  bool _certChanged = false;

  _Panel _panel = _Panel.none;
  String? _panelErr;
  bool _askRemove = false;

  /// 换好码、存好地址之后的那句话。
  String? _msg;

  @override
  void dispose() {
    for (final c in [_account, _pw, _code, _alts]) {
      c.dispose();
    }
    super.dispose();
  }

  Future<void> _submit() async {
    if (_busy) return;
    if (_account.text.trim().isEmpty) {
      setState(() => _error = tr('Enter your account', '请输入账号'));
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
      _msg = null;
    });
    final SiteApi api;
    try {
      api = await widget.signIn(_account.text.trim(), _pw.text);
    } catch (e) {
      if (mounted) {
        setState(() {
          _busy = false;
          _notPassword = e is SiteError && e.status == 0;
          _certChanged = e is SiteError && e.certChanged;
          _error = e is SiteError && e.body['apply'] is String
              ? applyStateText(e.message)
              : _certChanged
                  ? tr('The site certificate has changed. Scan the new code only if you have confirmed this is your site; otherwise do not sign in.',
                      '站点证书变了。确认是你们的站点才扫新码；不确定就先不要登录。')
                  : tr("Can't sign in: $e", '登录失败：$e');
        });
      }
      return;
    }
    if (!mounted) {
      // 页面已经没了（不该发生：正在登的时候退不出去）。登上的会话不留着：注销、关掉。
      try {
        await api.logout();
      } catch (_) {}
      api.close();
      return;
    }
    Navigator.pop(context, api);
  }

  Future<void> _problem() async {
    final api = widget.openAnon!();
    try {
      await Navigator.push(context,
          MaterialPageRoute<void>(builder: (_) => ProblemReportPage(api: api, share: shareBundle)));
    } finally {
      api.close();
    }
  }

  void _toggle(_Panel p) => setState(() {
        _panel = _panel == p ? _Panel.none : p;
        _panelErr = null;
        _askRemove = false;
        if (_panel == _Panel.code) {
          // 手机 App 测试 M21：剪贴板里就是站点码就先填进框里
          unawaited(Clipboard.getData(Clipboard.kTextPlain).then((d) {
            final t = d?.text?.trim() ?? '';
            if (mounted && t.startsWith(pairingPrefix) && _code.text.isEmpty) _code.text = t;
          }, onError: (Object _) {}));
        }
      });

  Future<void> _useCode(String raw) async {
    if (raw.trim().isEmpty) return;
    try {
      final upd = await widget.updateCode!(raw);
      if (!mounted) return;
      setState(() {
        _site = upd;
        _panel = _Panel.none;
        _error = null;
        _certChanged = false;
        _code.clear();
        _msg = tr('Site code of ${upd.name} updated. Sign in again.', '${upd.name} 的站点码已更新，请重新登录。');
      });
    } on PairingException catch (e) {
      if (mounted) setState(() => _panelErr = e.message);
    }
  }

  Future<void> _scanCode() async {
    final got = await widget.scanner!(context);
    if (got != null && mounted) await _useCode(got);
  }

  Future<void> _saveAlts() async {
    final lines = _alts.text.split('\n').map((l) => l.trim()).where((l) => l.isNotEmpty).toList();
    final bad = lines.where((l) => Uri.tryParse(l)?.scheme != 'https' || Uri.parse(l).host.isEmpty);
    if (bad.isNotEmpty) {
      setState(() => _panelErr = tr('Must start with https:// : ${bad.first}', '要以 https:// 开头：${bad.first}'));
      return;
    }
    final upd = await widget.saveAlts!(lines);
    if (!mounted) return;
    setState(() {
      _site = upd;
      _panel = _Panel.none;
      _msg = tr('Other addresses saved.', '其他地址已保存。');
    });
  }

  Future<void> _remove() async {
    await widget.remove!();
    if (mounted) Navigator.pop(context);
  }

  @override
  Widget build(BuildContext context) => nwEntryTheme(Builder(builder: _build));

  Widget _build(BuildContext context) {
    final c = Nw.of(context);
    final s = _site;
    final error = _error;
    final shape = RoundedRectangleBorder(borderRadius: BorderRadius.circular(2));
    ButtonStyle out([Color? fg]) => OutlinedButton.styleFrom(
        minimumSize: const Size(48, 44),
        shape: shape,
        padding: const EdgeInsets.symmetric(horizontal: Nw.s8),
        foregroundColor: fg ?? c.text,
        side: BorderSide(color: fg ?? c.textMuted));
    Widget two(Widget a, Widget b) =>
        Row(children: [Expanded(child: a), const SizedBox(width: Nw.s8), Expanded(child: b)]);
    Widget btn(Key key, String label, VoidCallback? on, [Color? fg]) => OutlinedButton(
        key: key,
        style: out(fg),
        onPressed: on,
        child: Text(label, maxLines: 1, overflow: TextOverflow.ellipsis, textAlign: TextAlign.center));
    final sub = NwText.bodySmall.copyWith(color: c.textSecondary);
    final hasCode = widget.updateCode != null, hasAlts = widget.saveAlts != null;
    return PopScope(
      canPop: !_busy,
      child: Scaffold(
        backgroundColor: c.bg,
        appBar: AppBar(
            backgroundColor: c.bg,
            leading: IconButton(
                key: const Key('login-switch'),
                tooltip: tr('Back to site list', '回站点列表'),
                icon: Icon(Icons.arrow_back_rounded, color: c.text),
                onPressed: _busy ? null : () => Navigator.pop(context)),
            title: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(s.name,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: NwText.titleMedium.copyWith(color: c.text, fontWeight: FontWeight.w700)),
              Text(s.url, maxLines: 1, overflow: TextOverflow.ellipsis, style: sub),
            ])),
        // 横屏弹键盘剩不了多高：整页能滚
        body: SafeArea(
            child: Align(
                alignment: Alignment.topCenter,
                child: SingleChildScrollView(
                    padding: const EdgeInsets.all(Nw.s16),
                    child: ConstrainedBox(
                        constraints: const BoxConstraints(maxWidth: 480),
                        child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                          NwField(
                              fieldKey: const Key('site-account'),
                              controller: _account,
                              label: tr('Account', '账号'),
                              autocorrect: false,
                              enableSuggestions: false,
                              autofocus: s.username.isEmpty),
                          const SizedBox(height: Nw.s16),
                          NwField(
                              fieldKey: const Key('site-password'),
                              controller: _pw,
                              label: tr('Password', '密码'),
                              obscureText: true,
                              autofocus: s.username.isNotEmpty, // 桌面版（W15）：一进来就能打字，回车就登录
                              autocorrect: false,
                              enableSuggestions: false,
                              error: error != null && !_notPassword,
                              textInputAction: TextInputAction.go,
                              onSubmitted: (_) => _submit()),
                          const SizedBox(height: Nw.s16),
                          FilledButton(
                              key: const Key('site-login'),
                              style: FilledButton.styleFrom(minimumSize: const Size(48, 48), shape: shape),
                              onPressed: _busy ? null : _submit,
                              child: Text(_busy ? tr('Signing in…', '正在登录…') : tr('Sign in', '登录'))),
                          if (error != null) ...[
                            const SizedBox(height: Nw.s16),
                            NwNotice(
                                key: const Key('site-login-error'),
                                text: error,
                                tone: _certChanged ? NwTone.warning : NwTone.error),
                          ],
                          if (_msg != null) ...[
                            const SizedBox(height: Nw.s16),
                            NwNotice(key: SiteLoginPage.msgKey, text: _msg!, tone: NwTone.success),
                          ],
                          if (hasCode || hasAlts) ...[
                            const SizedBox(height: Nw.s16),
                            two(
                                hasCode
                                    ? btn(SiteLoginPage.newCodeKey, tr('New site code…', '新站点码…'),
                                        _busy ? null : () => _toggle(_Panel.code))
                                    : const SizedBox.shrink(),
                                hasAlts
                                    ? btn(SiteLoginPage.altsKey, tr('Other site addresses…', '其他地址…'),
                                        _busy ? null : () => _toggle(_Panel.alts))
                                    : const SizedBox.shrink()),
                          ],
                          if (_panel == _Panel.code) ...[
                            const SizedBox(height: Nw.s16),
                            Text(
                                tr('Use this after an administrator reinstalled the site or renewed its certificate. The new code is on the duty console (Add to phone). If nobody changed the site, stop and ask the administrator first.',
                                    '管理员重装站点或更换证书后用这个。新的站点码在值班台的「加到手机」页上。如果没人动过站点，先停下，问管理员。'),
                                style: sub),
                            const SizedBox(height: Nw.s8),
                            NwField(
                                fieldKey: newCodeFieldKey,
                                controller: _code,
                                autocorrect: false,
                                enableSuggestions: false,
                                maxLines: 4,
                                minLines: 2,
                                mono: true,
                                error: _panelErr != null,
                                hint: '$pairingPrefix…'),
                            if (_panelErr != null) ...[
                              const SizedBox(height: Nw.s4),
                              Text(_panelErr!, style: NwText.bodySmall.copyWith(color: c.error)),
                            ],
                            const SizedBox(height: Nw.s8),
                            two(
                                widget.scanner != null
                                    ? btn(newCodeScanKey, tr('Scan new code', '扫新码'), _scanCode)
                                    : btn(const Key('login-code-cancel'), tr('Cancel', '取消'), () => _toggle(_Panel.code)),
                                FilledButton(
                                    key: newCodeOkKey,
                                    style: FilledButton.styleFrom(minimumSize: const Size(48, 44), shape: shape),
                                    onPressed: () => _useCode(_code.text),
                                    child: Text(tr('Use this code', '用这个码')))),
                          ],
                          if (_panel == _Panel.alts) ...[
                            const SizedBox(height: Nw.s16),
                            Text(
                                tr('Same site on other networks (e.g. robot hotspot, office Wi-Fi). One per line. Sign-in tries ${s.url} first, then these in order.',
                                    '同一个站点在别的网里的地址（比如机器人热点、办公室 Wi-Fi），一行一个。登录时先试 ${s.url}，连不上按顺序试这些。'),
                                style: sub),
                            const SizedBox(height: Nw.s8),
                            NwField(
                                fieldKey: const Key('site-alts-field'),
                                controller: _alts,
                                minLines: 2,
                                maxLines: 5,
                                autocorrect: false,
                                enableSuggestions: false,
                                error: _panelErr != null,
                                hint: tr('https://address:port', 'https://地址:端口')),
                            if (_panelErr != null) ...[
                              const SizedBox(height: Nw.s4),
                              Text(_panelErr!, style: NwText.bodySmall.copyWith(color: c.error)),
                            ],
                            const SizedBox(height: Nw.s8),
                            two(
                                btn(const Key('site-alts-cancel'), tr('Cancel', '取消'), () => _toggle(_Panel.alts)),
                                FilledButton(
                                    key: const Key('site-alts-save'),
                                    style: FilledButton.styleFrom(minimumSize: const Size(48, 44), shape: shape),
                                    onPressed: _saveAlts,
                                    child: Text(tr('Save', '保存')))),
                            if (widget.remove != null) ...[
                              const SizedBox(height: Nw.s24),
                              if (!_askRemove)
                                btn(SiteLoginPage.removeKey, tr('Remove this site from this phone', '从这台手机上删掉这个站点'),
                                    () => setState(() => _askRemove = true), c.error)
                              else ...[
                                Text(
                                    tr('Remove ${s.name} from this phone? The site itself is not affected. To add it back you need its site code again.',
                                        '从这台手机上删掉「${s.name}」？站点本身不受影响。要再加回来，得重新扫或粘贴它的站点码。'),
                                    style: NwText.bodySmall.copyWith(color: c.text)),
                                const SizedBox(height: Nw.s8),
                                two(
                                    btn(const Key('login-remove-cancel'), tr('Keep', '不删'), () => setState(() => _askRemove = false)),
                                    FilledButton(
                                        key: SiteListPage.removeOkKey,
                                        style: FilledButton.styleFrom(
                                            minimumSize: const Size(48, 44), shape: shape, backgroundColor: c.error),
                                        onPressed: _remove,
                                        child: Text(tr('Remove', '删除')))),
                              ],
                            ],
                          ],
                          if (widget.apply != null || widget.openAnon != null) ...[
                            const SizedBox(height: Nw.s32),
                            two(
                                widget.apply != null
                                    ? btn(
                                        SiteLoginPage.applyKey,
                                        tr('Request account', '申请账号'),
                                        _busy
                                            ? null
                                            : () => Navigator.push(
                                                context,
                                                MaterialPageRoute<void>(
                                                    builder: (_) => AccountApplyPage(site: s, apply: widget.apply!))))
                                    : const SizedBox.shrink(),
                                widget.openAnon != null
                                    ? btn(SiteLoginPage.problemKey, tr('Report a problem', '报问题'), _busy ? null : _problem)
                                    : const SizedBox.shrink()),
                          ],
                        ]))))),
      ),
    );
  }
}


// ------------------------------------------------------------ W52：申请账号

/// 申请账号（W52，稿 E-register）：名字（给管理员看）、账号、密码。交了就等管理员批准，批了在登录页用这个账号登录。
/// 角色是管理员批的时候选（站点不收「想要的角色」），这里不让选。
class AccountApplyPage extends StatefulWidget {
  final SiteEntry site;
  final SiteApply apply;
  final DateTime Function() now;
  const AccountApplyPage({super.key, required this.site, required this.apply, this.now = DateTime.now});

  static const Key nameKey = Key('apply-display');
  static const Key accountKey = Key('apply-account');
  static const Key passwordKey = Key('apply-password');
  static const Key submitKey = Key('apply-submit');
  static const Key doneKey = Key('apply-done');

  @override
  State<AccountApplyPage> createState() => _AccountApplyPageState();
}

class _AccountApplyPageState extends State<AccountApplyPage> {
  final _display = TextEditingController();
  final _account = TextEditingController();
  final _pw = TextEditingController();
  bool _busy = false;
  DateTime? _sent;
  String? _error;

  @override
  void dispose() {
    _display.dispose();
    _account.dispose();
    _pw.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    final name = _account.text.trim(), display = _display.text.trim();
    if (display.isEmpty || name.isEmpty) {
      setState(() => _error = tr('Enter your name and an account name', '请填写姓名和账号'));
      return;
    }
    if (_pw.text.length < 10) {
      setState(() => _error = tr('Password needs at least 10 characters', '密码至少 10 位'));
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await widget.apply(name, display, _pw.text);
      if (mounted) setState(() => _sent = widget.now());
    } on SiteError catch (e) {
      if (mounted) setState(() => _error = e.message);
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => nwEntryTheme(Builder(builder: _build));

  Widget _build(BuildContext context) {
    final c = Nw.of(context);
    final sent = _sent;
    final locked = _busy || sent != null;
    String two(int v) => v.toString().padLeft(2, '0');
    return Scaffold(
      backgroundColor: c.bg,
      appBar: AppBar(
          backgroundColor: c.bg,
          title: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(tr('Request account', '申请账号'),
                style: NwText.titleMedium.copyWith(color: c.text, fontWeight: FontWeight.w700)),
            Text(widget.site.name, style: NwText.bodySmall.copyWith(color: c.textSecondary)),
          ])),
      body: SafeArea(
        child: Align(
          alignment: Alignment.topCenter,
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(Nw.s16),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 480),
              child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                Text(
                    tr('You can sign in after an administrator approves and picks your role. Until then this phone receives no alarms.',
                        '管理员批准并选好权限后才能登录。在那之前这台手机收不到报警。'),
                    style: NwText.bodySmall.copyWith(color: c.textSecondary)),
                const SizedBox(height: Nw.s16),
                NwField(
                    fieldKey: AccountApplyPage.nameKey,
                    controller: _display,
                    enabled: !locked,
                    label: tr('Your name (shown to the administrator)', '姓名（供管理员识别）')),
                const SizedBox(height: Nw.s16),
                NwField(
                    fieldKey: AccountApplyPage.accountKey,
                    controller: _account,
                    enabled: !locked,
                    label: tr('Username (letters, digits)', '账号（字母、数字）'),
                    autocorrect: false,
                    enableSuggestions: false),
                const SizedBox(height: Nw.s16),
                NwField(
                    fieldKey: AccountApplyPage.passwordKey,
                    controller: _pw,
                    enabled: !locked,
                    label: tr('Password (at least 10 characters)', '密码（至少 10 个字符）'),
                    obscureText: true,
                    autocorrect: false,
                    enableSuggestions: false),
                if (_error != null) ...[
                  const SizedBox(height: Nw.s16),
                  NwNotice(text: _error!, tone: NwTone.error),
                ],
                const SizedBox(height: Nw.s16),
                FilledButton(
                    key: AccountApplyPage.submitKey,
                    style: FilledButton.styleFrom(
                        minimumSize: const Size(48, 48), shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(2))),
                    onPressed: locked ? null : _submit,
                    child: Text(_busy ? tr('Sending…', '正在提交…') : tr('Send request', '提交申请'))),
                if (sent != null) ...[
                  const SizedBox(height: Nw.s16),
                  Container(
                      key: AccountApplyPage.doneKey,
                      padding: const EdgeInsets.all(Nw.s16),
                      decoration: BoxDecoration(color: c.surface, border: Border.all(color: c.outline)),
                      child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                        Padding(
                            padding: const EdgeInsets.only(top: 4),
                            child: Icon(Icons.circle, size: 12, color: c.primary)),
                        const SizedBox(width: Nw.s8),
                        Expanded(
                            child: Text(
                                tr('Sent ${two(sent.hour)}:${two(sent.minute)} · Awaiting administrator approval. Then sign in as "${_account.text.trim()}".',
                                    '${two(sent.hour)}:${two(sent.minute)} 已提交 · 等管理员批准。批准后用账号「${_account.text.trim()}」登录。'),
                                style: NwText.bodyMedium.copyWith(color: c.text))),
                      ])),
                ],
              ]),
            ),
          ),
        ),
      ),
    );
  }
}
