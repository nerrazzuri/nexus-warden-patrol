/// 站点列表（W00c4）：存着的站点一个一张卡，点了去登录页、登上了进站点；右上换语言、添加，底下也能添加。
/// 登录之后进的是带底部导航的外壳（`nw/nw_shell.dart`）。
/// 2026-10-14 按设计稿重做（P1）：选站点是设计稿的 Site Selection，登录从弹窗改成一页（[SiteLoginPage]）。
library;

import 'package:flutter/material.dart';

import '../l10n.dart';
import '../net/background_watch.dart';
import '../net/push.dart';
import '../net/site_client.dart';
import '../store/site_store.dart';
import 'app_settings.dart';
import 'nw/nw_button.dart';
import 'nw/nw_cards.dart';
import 'nw/nw_p1_entry.dart';
import 'nw/nw_shell.dart';
import 'nw/nw_theme.dart';
import 'nw/nw_widgets.dart';
import '../net/pairing.dart';
import 'site_add.dart';
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
    widget.store.load().then((s) {
      if (mounted) setState(() => _sites = s);
    }, onError: (Object e) {
      if (mounted) setState(() => _loadError = '$e');
    });
  }

  Future<void> _remove(SiteEntry s) async {
    // 手机 App 测试 M22：以前一点就删、不能撤销
    final ok = await showDialog<bool>(
        context: context,
        builder: (c) => AlertDialog(
              title: Text(tr('Remove ${s.name} from this phone?', '从这台手机上删掉「${s.name}」？')),
              content: Text(tr('The site itself is not affected. To add it back you need its site code again.',
                  '站点本身不受影响。要再加回来，得重新扫或粘贴它的站点码。')),
              actions: [
                TextButton(onPressed: () => Navigator.pop(c, false), child: Text(tr('Cancel', '取消'))),
                FilledButton(
                    key: SiteListPage.removeOkKey,
                    onPressed: () => Navigator.pop(c, true),
                    child: Text(tr('Remove', '删除'))),
              ],
            ));
    if (ok != true || !mounted) return;
    final next = [..._sites]..remove(s);
    await widget.store.save(next);
    if (mounted) setState(() => _sites = next);
  }

  /// 备用地址（POC 11-05）：一行一个，`https://` 开头；证书指纹同一个，所以只是换个路走到同一台站点主机。
  Future<void> _editAlts(SiteEntry s) async {
    final ctl = TextEditingController(text: s.alts.join('\n'));
    String? err;
    final got = await showDialog<List<String>>(
        context: context,
        builder: (ctx) => StatefulBuilder(
            builder: (ctx, set) => AlertDialog(
                  title: Text(tr('Other addresses of ${s.name}', '${s.name} 的其他地址')),
                  content: SingleChildScrollView(
                      child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Text(tr('Same site on other networks (e.g. robot hotspot, office Wi-Fi). One per line. '
                            'Login tries ${s.url} first, then these in order.',
                        '同一个站点在别的网里的地址（比如机器人热点、办公室 Wi-Fi），一行一个。登录时先试 ${s.url}，连不上按顺序试这些。')),
                    TextField(
                        key: const Key('site-alts-field'),
                        controller: ctl,
                        minLines: 2,
                        maxLines: 5,
                        decoration: InputDecoration(hintText: tr('https://address:port', 'https://地址:端口'), errorText: err)),
                  ])),
                  actions: [
                    TextButton(onPressed: () => Navigator.pop(ctx), child: Text(tr('Cancel', '取消'))),
                    FilledButton(
                        key: const Key('site-alts-save'),
                        onPressed: () {
                          final lines = ctl.text.split('\n').map((l) => l.trim()).where((l) => l.isNotEmpty).toList();
                          final bad = lines.where((l) => Uri.tryParse(l)?.scheme != 'https' || Uri.parse(l).host.isEmpty);
                          if (bad.isNotEmpty) {
                            set(() => err = tr('Must start with https:// : ${bad.first}', '要以 https:// 开头：${bad.first}'));
                            return;
                          }
                          Navigator.pop(ctx, lines);
                        },
                        child: Text(tr('Save', '保存'))),
                  ],
                )));
    // 控制器不当场 dispose：对话框关的动画还在用它（等回收）
    if (got == null || !mounted) return;
    final upd = s.copyWith(alts: got.where((u) => u != s.url).toList());
    final next = [for (final x in _sites) identical(x, s) ? upd : x];
    await widget.store.save(next);
    if (mounted) setState(() => _sites = next);
  }

  /// 手机 App 测试 M03：站点重装、重签了证书 —— 扫或粘贴新的站点码，只换这个站点的地址和指纹
  /// （名字、账号、备用地址留着）。不用再「删掉重加」。回更新后的那一条（没换回 null）。
  Future<SiteEntry?> _newCode(SiteEntry s) async {
    final code = TextEditingController();
    final scan = widget.scanner ?? (canScanCodes ? scanSiteCode : null);
    final raw = await showDialog<String>(
        context: context,
        builder: (c) => AlertDialog(
              title: Text(tr('Update site code of ${s.name}', '更新 ${s.name} 的站点码')),
              content: SingleChildScrollView(
                  child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text(tr(
                    'Use this after an administrator reinstalled the site or renewed its certificate. Get the new code from '
                        'the duty console (Add to phone). If nobody changed the site, stop and ask the administrator first.',
                    '管理员重装站点或更换证书后用这个。新的站点码在值班台的「加到手机」页上。如果没人动过站点，先停下，问管理员。')),
                const SizedBox(height: Nw.s16),
                NwField(
                    fieldKey: newCodeFieldKey,
                    controller: code,
                    autocorrect: false,
                    enableSuggestions: false,
                    maxLines: 4,
                    minLines: 2,
                    mono: true,
                    hint: '$pairingPrefix…'),
                if (scan != null) ...[
                  const SizedBox(height: Nw.s8),
                  NwButton(
                      buttonKey: newCodeScanKey,
                      variant: NwButtonVariant.outline,
                      icon: Icons.qr_code_scanner_rounded,
                      label: tr('Scan new code', '扫新码'),
                      onPressed: () async {
                        final got = await scan(c);
                        if (got != null && c.mounted) Navigator.pop(c, got);
                      }),
                ],
              ])),
              actions: [
                TextButton(onPressed: () => Navigator.pop(c), child: Text(tr('Cancel', '取消'))),
                FilledButton(
                    key: newCodeOkKey,
                    onPressed: () => Navigator.pop(c, code.text),
                    child: Text(tr('Use this code', '用这个码'))),
              ],
            ));
    if (raw == null || raw.trim().isEmpty || !mounted) return null;
    final PairingInfo p;
    try {
      p = decodePairing(raw);
    } on PairingException catch (e) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
      return null;
    }
    final upd = s.copyWith(
        url: p.url, fingerprint: p.fingerprint, alts: s.alts.where((u) => u != p.url).toList());
    final next = [for (final x in _sites) identical(x, s) ? upd : x];
    await widget.store.save(next);
    if (!mounted) return upd;
    setState(() => _sites = next);
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
        content: Text(tr('Site code of ${s.name} updated. Sign in again.', '${s.name} 的站点码已更新，请重新登录。'))));
    return upd;
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
    ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(tr('Added ${entry.name}. Tap it to sign in.', '已添加「${entry.name}」，点它登录。'))));
  }

  Future<void> _open(SiteEntry s) async {
    String? account0;
    String? used;
    var wantNewCode = false;
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
            // 手机 App 测试 M03：证书变了，登录页上直接给「扫新码 / 粘贴新码」
            onNewCode: () => wantNewCode = true,
            // W52：没有账号就在这里申请（不用登录），管理员批了直接用这个账号登录
            apply: (name, display, password) async {
              final api = widget.apiFactory(s);
              try {
                await api.applyAccount(name, display, password);
              } finally {
                api.close();
              }
            })));
    if (api == null) {
      if (wantNewCode && mounted) {
        final upd = await _newCode(s);
        if (upd != null && mounted) await _open(upd);
      }
      return;
    }
    final a = api;
    // 记下这次登录用的账号（下次登录页自动填好）、登上的地址（下次先试它）
    if ((account0 != null && account0 != s.username) || (used != null && used != s.url)) {
      final upd = (used == null ? s : s.preferring(used!)).copyWith(username: account0);
      final next = [for (final x in _sites) identical(x, s) ? upd : x];
      await widget.store.save(next);
      if (mounted) setState(() => _sites = next);
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

  @override
  Widget build(BuildContext context) {
    final c = Nw.of(context);
    final broken = _loadError != null;
    return Scaffold(
      backgroundColor: c.bg,
      // 页头、底栏各占 Scaffold 的一格（不是 body 里的 Column）：登录页键盘还弹着就退回来的那一下，
      // body 可以只剩零高，这样摆不溢出。
      appBar: nwHeaderBar(
          context,
          NwHeader(overline: 'Nexus Warden', title: tr('Select site', '选择站点'), trailing: [
            // W55：语言、工程师工具（解绑令）、App 版本都在「设置」里
            IconButton(
                key: SiteListPage.settingsKey,
                tooltip: tr('Settings', '设置'),
                icon: Icon(Icons.settings_rounded, color: c.text),
                onPressed: () => Navigator.push(context,
                    MaterialPageRoute<void>(builder: (_) => AppSettingsPage(langStore: widget.langStore)))),
            if (!broken)
              IconButton(
                  key: const Key('site-add-top'),
                  tooltip: tr('Add site', '添加站点'),
                  icon: Icon(Icons.add_circle_outline_rounded, size: 28, color: c.text),
                  onPressed: _add),
          ])),
      // 站点文件坏了不给添加（见 _loadError）
      bottomNavigationBar: broken
          ? null
          : Container(
              decoration:
                  BoxDecoration(color: c.surface, border: Border(top: BorderSide(color: c.outline))),
              child: SafeArea(
                  top: false,
                  child: Padding(
                      padding: const EdgeInsets.symmetric(horizontal: Nw.s24, vertical: Nw.s16),
                      child: Row(mainAxisAlignment: MainAxisAlignment.center, children: [
                        Flexible(
                            child: ConstrainedBox(
                                constraints: const BoxConstraints(maxWidth: _maxWidth - 2 * Nw.s24),
                                child: NwButton(
                                    buttonKey: const Key('site-add'),
                                    label: tr('Add site', '添加站点'),
                                    icon: Icons.qr_code_scanner_rounded,
                                    variant: NwButtonVariant.outline,
                                    fullWidth: true,
                                    onPressed: _add))),
                      ])))),
      body: SafeArea(
          top: false,
          bottom: false,
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
              : _sites.isEmpty
                  ? NwEmpty(
                      icon: Icons.domain_add_rounded,
                      text: tr('No sites yet. Tap "Add site" below.',
                          '暂无站点，请点击下方「添加站点」。'),
                      hint: tr('Scan the site code shown on the duty console, or enter the address by hand.',
                          '扫描值班台上的配对码，或手动输入站点地址。'))
                  // 宽屏（桌面版）上卡片不拉满一整行
                  : Align(
                      alignment: Alignment.topCenter,
                      child: ConstrainedBox(
                          constraints: const BoxConstraints(maxWidth: _maxWidth),
                          child: ListView.separated(
                              padding: const EdgeInsets.all(Nw.s24),
                              itemCount: _sites.length,
                              separatorBuilder: (_, _) => const SizedBox(height: Nw.s16),
                              itemBuilder: (_, i) => _card(c, _sites[i]))))),
    );
  }

  /// 一个站点一张卡。登录之前不知道连没连上、有没有 P1：卡上不显示这两样（不编）。
  Widget _card(NwColors c, SiteEntry s) => NwSiteCard(
      name: s.name,
      address: s.username.isEmpty ? s.url : '${s.url} · ${s.username}',
      enterKey: Key('site-enter-${s.name}'),
      onEnter: () => _open(s),
      menu: PopupMenuButton<String>(
          key: Key('site-menu-${s.name}'),
          tooltip: tr('More', '更多'),
          icon: Icon(Icons.more_vert_rounded, color: c.textSecondary),
          onSelected: (v) => switch (v) {
                'alts' => _editAlts(s),
                'code' => _newCode(s),
                _ => _remove(s),
              },
          itemBuilder: (_) => [
                PopupMenuItem<String>(
                    key: Key('site-alts-${s.name}'),
                    value: 'alts',
                    child: Text(tr('Other addresses of this site…', '这个站点的其他地址…'))),
                PopupMenuItem<String>(
                    key: Key('site-code-${s.name}'),
                    value: 'code',
                    child: Text(tr('Update site code (certificate changed)…', '更新站点码（证书变了）…'))),
                PopupMenuItem<String>(
                    key: Key('site-remove-${s.name}'),
                    value: 'remove',
                    child: Text(tr('Remove', '删除'), style: NwText.bodyMedium.copyWith(color: c.error))),
              ]));
}

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

/// 登录页（2026-10-14 重做，原来是弹窗）：品牌、要登的是哪个站点、口令。账号是加站点时存下的，这里
/// 只填口令。登上了带着客户端退回去（`Navigator.pop(context, api)`）；登不上留在这一页说原因。
/// 设计稿上的数字键盘、指纹、「Emergency Station Reset」没有做（用户 2026-10-14 定的）。
class SiteLoginPage extends StatefulWidget {
  final SiteEntry site;
  final SiteSignIn signIn;
  /// 给了就有「申请账号」（W52）。
  final SiteApply? apply;

  /// 手机 App 测试 M03：证书变了时登录页上「更新站点码」按钮调它（调完登录页退出、站点列表接着换码）。
  final VoidCallback? onNewCode;
  const SiteLoginPage({super.key, required this.site, required this.signIn, this.apply, this.onNewCode});

  static const Key applyKey = Key('login-apply');
  static const Key newCodeKey = Key('login-new-code');

  @override
  State<SiteLoginPage> createState() => _SiteLoginPageState();
}

class _SiteLoginPageState extends State<SiteLoginPage> {
  late final _account = TextEditingController(text: widget.site.username);
  final _pw = TextEditingController();

  /// 正在登：这时候不收第二次提交，也不许退出去（退了登上的那个会话就没人管了）。
  bool _busy = false;
  String? _error;

  /// 这次登不上是因为没连上站点（证书、网络），不是账号密码：密码框不标红（M03）。
  bool _notPassword = false;
  bool _certChanged = false;

  @override
  void dispose() {
    _account.dispose();
    _pw.dispose();
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
                  ? certChangedText
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

  @override
  Widget build(BuildContext context) {
    final c = Nw.of(context);
    final s = widget.site;
    final error = _error;
    return PopScope(
      canPop: !_busy,
      child: Scaffold(
        backgroundColor: c.bg,
        // 横屏弹键盘剩不了多高：整页能滚
        body: SafeArea(
            child: Center(
                child: SingleChildScrollView(
                    padding: const EdgeInsets.all(Nw.s24),
                    child: ConstrainedBox(
                        constraints: const BoxConstraints(maxWidth: 420),
                        child: Column(
                            mainAxisSize: MainAxisSize.min,
                            crossAxisAlignment: CrossAxisAlignment.stretch,
                            children: [
                              // 品牌
                              Center(
                                  child: Container(
                                      width: 64,
                                      height: 64,
                                      alignment: Alignment.center,
                                      decoration: BoxDecoration(
                                          color: c.surface,
                                          borderRadius: BorderRadius.circular(Nw.r12),
                                          border: Border.all(color: c.outline)),
                                      child: Icon(Icons.security_rounded, size: 32, color: c.primary))),
                              const SizedBox(height: Nw.s16),
                              Text('Nexus Warden',
                                  textAlign: TextAlign.center,
                                  style: NwText.titleLarge.copyWith(color: c.text, fontWeight: FontWeight.w700)),
                              const SizedBox(height: Nw.s4),
                              Text(tr('Security Command', '安防指挥'),
                                  textAlign: TextAlign.center,
                                  style: NwText.bodySmall.copyWith(color: c.textSecondary)),
                              const SizedBox(height: Nw.s32),
                              // 要登的是哪个站点；「换站点」回列表
                              Container(
                                  padding: const EdgeInsets.fromLTRB(Nw.s16, Nw.s8, Nw.s8, Nw.s8),
                                  decoration: BoxDecoration(
                                      color: c.surface,
                                      borderRadius: BorderRadius.circular(Nw.r8),
                                      border: Border.all(color: c.outline)),
                                  child: Row(children: [
                                    Icon(Icons.location_on_rounded, size: 20, color: c.textSecondary),
                                    const SizedBox(width: Nw.s16),
                                    Expanded(
                                        child: Column(
                                            mainAxisSize: MainAxisSize.min,
                                            crossAxisAlignment: CrossAxisAlignment.start,
                                            children: [
                                          Text(s.name,
                                              maxLines: 1,
                                              overflow: TextOverflow.ellipsis,
                                              style: NwText.labelLarge.copyWith(color: c.text)),
                                          const SizedBox(height: Nw.s4),
                                          // 站点地址长了折一行（两行为止）
                                          Text(s.url,
                                              maxLines: 2,
                                              overflow: TextOverflow.ellipsis,
                                              style: NwText.labelSmall.copyWith(color: c.textSecondary)),
                                        ])),
                                    const SizedBox(width: Nw.s8),
                                    NwButton(
                                        buttonKey: const Key('login-switch'),
                                        label: tr('Switch', '换站点'),
                                        variant: NwButtonVariant.ghost,
                                        size: NwButtonSize.small,
                                        onPressed: _busy ? null : () => Navigator.pop(context)),
                                  ])),
                              const SizedBox(height: Nw.s32),
                              NwField(
                                  fieldKey: const Key('site-account'),
                                  controller: _account,
                                  label: tr('Account', '账号'),
                                  icon: Icons.person_outline_rounded,
                                  autocorrect: false,
                                  enableSuggestions: false,
                                  autofocus: s.username.isEmpty),
                              const SizedBox(height: Nw.s16),
                              NwField(
                                  fieldKey: const Key('site-password'),
                                  controller: _pw,
                                  label: tr('Password', '密码'),
                                  icon: Icons.lock_outline_rounded,
                                  obscureText: true,
                                  autofocus: s.username.isNotEmpty, // 桌面版（W15）：一进来就能打字，回车就登录
                                  autocorrect: false,
                                  enableSuggestions: false,
                                  error: error != null && !_notPassword,
                                  textInputAction: TextInputAction.go,
                                  onSubmitted: (_) => _submit()),
                              if (error != null) ...[
                                const SizedBox(height: Nw.s16),
                                NwNotice(key: const Key('site-login-error'), text: error, tone: NwTone.error),
                                if (_certChanged && widget.onNewCode != null) ...[
                                  const SizedBox(height: Nw.s8),
                                  NwButton(
                                      buttonKey: SiteLoginPage.newCodeKey,
                                      variant: NwButtonVariant.outline,
                                      icon: Icons.qr_code_scanner_rounded,
                                      label: tr('Update site code', '更新站点码'),
                                      fullWidth: true,
                                      onPressed: () {
                                        widget.onNewCode!();
                                        Navigator.pop(context);
                                      }),
                                ],
                              ],
                              const SizedBox(height: Nw.s24),
                              NwButton(
                                  buttonKey: const Key('site-login'),
                                  label: _busy ? tr('Signing in…', '正在登录…') : tr('Sign in', '登录'),
                                  size: NwButtonSize.large,
                                  fullWidth: true,
                                  onPressed: _busy ? null : _submit),
                              if (widget.apply != null) ...[
                                const SizedBox(height: Nw.s16),
                                Center(
                                  child: NwButton(
                                      buttonKey: SiteLoginPage.applyKey,
                                      variant: NwButtonVariant.ghost,
                                      label: tr('New Account Registration', '新账号注册'),
                                      onPressed: _busy
                                          ? null
                                          : () => Navigator.push(
                                              context,
                                              MaterialPageRoute<void>(
                                                  builder: (_) => AccountApplyPage(site: s, apply: widget.apply!)))),
                                ),
                              ],
                            ]))))),
      ),
    );
  }
}


// ------------------------------------------------------------ W52：申请账号

/// 申请账号（W52）：名字（给管理员看）、账号、密码。交了就等管理员批准，批了在登录页用这个账号登录。
class AccountApplyPage extends StatefulWidget {
  final SiteEntry site;
  final SiteApply apply;
  const AccountApplyPage({super.key, required this.site, required this.apply});

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
  bool _done = false;
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
      if (mounted) setState(() => _done = true);
    } on SiteError catch (e) {
      if (mounted) setState(() => _error = e.message);
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final c = Nw.of(context);
    return Scaffold(
      appBar: AppBar(title: Text(tr('New Account Registration', '新账号注册'))),
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(Nw.s24),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 420),
              child: _done
                  ? Column(key: AccountApplyPage.doneKey, mainAxisSize: MainAxisSize.min, children: [
                      Icon(Icons.hourglass_top_rounded, size: 48, color: c.primary),
                      const SizedBox(height: Nw.s16),
                      Text(
                          tr('Submitted. Waiting for an administrator of ${widget.site.name} to approve. Then sign in as "${_account.text.trim()}".',
                              '已提交，待「${widget.site.name}」管理员批准。批准后使用账号「${_account.text.trim()}」登录。'),
                          textAlign: TextAlign.center,
                          style: NwText.bodyLarge.copyWith(color: c.text)),
                      const SizedBox(height: Nw.s24),
                      NwButton(label: tr('Back to sign in', '回到登录'), onPressed: () => Navigator.pop(context)),
                    ])
                  : Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                      Text(tr('The administrator assigns your role based on your name.', '管理员根据你的姓名分配权限。'),
                          style: NwText.bodyMedium.copyWith(color: c.textSecondary)),
                      const SizedBox(height: Nw.s16),
                      NwField(
                          fieldKey: AccountApplyPage.nameKey,
                          controller: _display,
                          label: tr('Your name (shown to the administrator)', '姓名（供管理员识别）'),
                          icon: Icons.badge_outlined),
                      const SizedBox(height: Nw.s16),
                      NwField(
                          fieldKey: AccountApplyPage.accountKey,
                          controller: _account,
                          label: tr('Account name (letters, digits)', '账号（字母、数字）'),
                          icon: Icons.person_outline_rounded,
                          autocorrect: false,
                          enableSuggestions: false),
                      const SizedBox(height: Nw.s16),
                      NwField(
                          fieldKey: AccountApplyPage.passwordKey,
                          controller: _pw,
                          label: tr('Password (at least 10 characters)', '密码（至少 10 个字符）'),
                          icon: Icons.lock_outline_rounded,
                          obscureText: true,
                          autocorrect: false,
                          enableSuggestions: false),
                      if (_error != null) ...[
                        const SizedBox(height: Nw.s16),
                        NwNotice(text: _error!, tone: NwTone.error),
                      ],
                      const SizedBox(height: Nw.s24),
                      NwButton(
                          buttonKey: AccountApplyPage.submitKey,
                          size: NwButtonSize.large,
                          fullWidth: true,
                          label: _busy ? tr('Sending…', '正在提交…') : tr('Send application', '提交申请'),
                          onPressed: _busy ? null : _submit),
                    ]),
            ),
          ),
        ),
      ),
    );
  }
}
