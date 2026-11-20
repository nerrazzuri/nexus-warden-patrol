// 手机指纹登录（用户 11-20）：签的内容跟站点一字不差；用密码登上问一次、开了记下；下次进来先弹指纹、
// 登上直接进外壳；站点说作废了就删掉记录、收起按钮、照旧输密码；「暂不」以后不再问。
import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:nexwar_patrol/net/bio_login.dart';
import 'package:nexwar_patrol/net/site_client.dart';
import 'package:nexwar_patrol/store/site_store.dart';
import 'package:nexwar_patrol/ui/nw/nw_shell.dart';
import 'package:nexwar_patrol/ui/site_list.dart';

import 'site_page_test.dart' show FakeApi;

/// 假钥匙：能不能用、按了指纹回什么（`ok` / `cancelled` / `invalidated`…）都可以设。
class FakeBioKeys implements BioKeys {
  bool can = true;
  String answer = 'ok';
  final List<String> log = <String>[];
  final Set<String> live = <String>{};

  @override
  Future<bool> available() async => can;

  @override
  Future<List<int>> create(String alias) async {
    log.add('create');
    live.add(alias);
    return List<int>.filled(91, 1);
  }

  @override
  Future<BioSign> sign(String alias, List<int> data,
      {required String title, required String subtitle, required String cancel}) async {
    log.add('sign ${utf8.decode(data.takeWhile((b) => b != 0).toList())}');
    return answer == 'ok' ? BioSign('ok', List<int>.filled(70, 2)) : BioSign(answer);
  }

  @override
  Future<void> delete(String alias) async {
    log.add('delete');
    live.remove(alias);
  }
}

/// 存不下东西的记录本（手机存储满了）。
class _FullBook extends BioBook {
  @override
  Future<void> decline(SiteEntry s, String account) async => throw const FileSystemException('No space left on device');
}

SiteEntry _site() => SiteEntry(name: '庄园', url: 'https://h:1', fingerprint: 'ab' * 32, username: 'gina');

Future<void> _openSite(WidgetTester t) async {
  await t.tap(find.text('庄园'));
  await t.pumpAndSettle();
}

Future<void> _leave(WidgetTester t) async {
  // 外壳里退出站点太绕：直接把外壳那一页弹掉（跟按系统返回一样，_open 会注销、关掉）
  Navigator.of(t.element(find.byType(NwShell))).pop();
  await t.pumpAndSettle();
}

void main() {
  test('签的内容：用途、0、随机数、0、账号或钥匙号（跟站点 accounts.BIO_* 一样）', () {
    expect(bioMessage('login', 'n1', 'k1'), [...utf8.encode('nexwar-bio-login'), 0, ...utf8.encode('n1'), 0, ...utf8.encode('k1')]);
    expect(utf8.decode(bioMessage('enroll', 'n', 'gina')), 'nexwar-bio-enroll\u0000n\u0000gina');
  });

  testWidgets('用密码登上问一次 → 开启 → 下次进来自动按指纹、直接进外壳', (t) async {
    t.view.physicalSize = const Size(800, 1600);
    t.view.devicePixelRatio = 2.0;
    addTearDown(t.view.reset);
    final api = FakeApi('guard');
    final keys = FakeBioKeys();
    final book = BioBook();
    final store = MemorySiteStore([_site()]);
    await t.pumpWidget(MaterialApp(home: SiteListPage(store: store, apiFactory: (_) => api, bioKeys: keys, bioBook: book)));
    await t.pumpAndSettle();
    await _openSite(t);
    expect(find.byKey(SiteLoginPage.bioKey), findsNothing, reason: '还没开：只有密码');
    await t.enterText(find.byKey(const Key('site-password')), 'pw');
    await t.tap(find.text('登录'));
    await t.pumpAndSettle();
    expect(find.text('下次用指纹登录？'), findsOneWidget);
    await t.tap(find.byKey(SiteListPage.bioOfferYesKey));
    await t.pumpAndSettle();
    expect(api.bioCalls, ['enrollNonce', startsWith('enroll ')]);
    expect(keys.log, ['create', 'sign nexwar-bio-enroll']);
    expect(find.byType(NwShell), findsOneWidget);
    final rec = await book.of(_site(), DateTime.now().millisecondsSinceEpoch);
    expect(rec?.keyId, '0123456789abcdef0123456789abcdef');
    expect(rec?.account, 'gina');
    await _leave(t);

    // 第二次：进登录页就弹指纹，按对了直接进外壳，不再问
    api.bioCalls.clear();
    await _openSite(t);
    expect(api.bioCalls, ['loginNonce ${rec!.keyId}', 'login ${rec.keyId} n-login']);
    expect(find.byType(NwShell), findsOneWidget);
    expect(find.text('下次用指纹登录？'), findsNothing);
    await _leave(t);

    // 第三次：按了「用密码」：留在登录页、不报错，还能再点按钮
    keys.answer = 'cancelled';
    await _openSite(t);
    expect(find.byType(NwShell), findsNothing);
    expect(find.byKey(SiteLoginPage.bioKey), findsOneWidget);
    expect(find.byKey(const Key('site-login-error')), findsNothing);

    // 站点说作废了（改过密码、被撤）：记录删掉、钥匙删掉、按钮收起来、说清楚
    keys.answer = 'ok';
    api.bioError = const SiteError(401, 'gone', body: <String, dynamic>{'bio_gone': true});
    await t.tap(find.byKey(SiteLoginPage.bioKey));
    await t.pumpAndSettle();
    expect(find.byKey(SiteLoginPage.bioKey), findsNothing);
    expect(find.textContaining('指纹登录已失效'), findsOneWidget);
    expect(await book.of(_site(), DateTime.now().millisecondsSinceEpoch), isNull);
    expect(keys.live, isEmpty);
  });

  testWidgets('「暂不」以后这个站点这个账号不再问；手机不能用指纹的根本不问', (t) async {
    t.view.physicalSize = const Size(800, 1600);
    t.view.devicePixelRatio = 2.0;
    addTearDown(t.view.reset);
    final api = FakeApi('guard');
    final keys = FakeBioKeys();
    final book = BioBook();
    await t.pumpWidget(MaterialApp(
        home: SiteListPage(store: MemorySiteStore([_site()]), apiFactory: (_) => api, bioKeys: keys, bioBook: book)));
    await t.pumpAndSettle();
    for (var i = 0; i < 2; i++) {
      await _openSite(t);
      await t.enterText(find.byKey(const Key('site-password')), 'pw');
      await t.tap(find.text('登录'));
      await t.pumpAndSettle();
      if (i == 0) {
        await t.tap(find.byKey(SiteListPage.bioOfferNoKey));
        await t.pumpAndSettle();
      } else {
        expect(find.text('下次用指纹登录？'), findsNothing);
      }
      await _leave(t);
    }
    expect(api.bioCalls, isEmpty);
    keys.can = false;
    final book2 = BioBook();
    await t.pumpWidget(MaterialApp(
        home: SiteListPage(store: MemorySiteStore([_site()]), apiFactory: (_) => api, bioKeys: keys, bioBook: book2)));
    await t.pumpAndSettle();
    await _openSite(t);
    await t.enterText(find.byKey(const Key('site-password')), 'pw');
    await t.tap(find.text('登录'));
    await t.pumpAndSettle();
    expect(find.text('下次用指纹登录？'), findsNothing);
    expect(find.byType(NwShell), findsOneWidget);
  });

  testWidgets('登录页「在这部手机上关闭指纹登录」：删钥匙、删记录、按钮收起', (t) async {
    t.view.physicalSize = const Size(800, 1600);
    t.view.devicePixelRatio = 2.0;
    addTearDown(t.view.reset);
    final keys = FakeBioKeys()..answer = 'cancelled';
    final book = BioBook();
    await keys.create('a1');
    await book.put(BioRecord(site: 'ab' * 32, account: 'gina', alias: 'a1', keyId: 'k' * 32,
        expiresAt: DateTime.now().millisecondsSinceEpoch + 86400000));
    await t.pumpWidget(MaterialApp(
        home: SiteListPage(store: MemorySiteStore([_site()]), apiFactory: (_) => FakeApi('guard'), bioKeys: keys, bioBook: book)));
    await t.pumpAndSettle();
    await _openSite(t);
    expect(find.textContaining('用指纹登录（gina）'), findsOneWidget);
    await t.tap(find.byKey(SiteLoginPage.bioOffKey));
    await t.pumpAndSettle();
    expect(find.byKey(SiteLoginPage.bioKey), findsNothing);
    expect(find.text('这部手机已关闭指纹登录。'), findsOneWidget);
    expect(keys.live, isEmpty);
    expect(await book.of(_site(), DateTime.now().millisecondsSinceEpoch), isNull);
  });

  testWidgets('外审指纹-2：点「暂不」存不下（存储满）照样进站点', (t) async {
    t.view.physicalSize = const Size(800, 1600);
    t.view.devicePixelRatio = 2.0;
    addTearDown(t.view.reset);
    await t.pumpWidget(MaterialApp(
        home: SiteListPage(store: MemorySiteStore([_site()]), apiFactory: (_) => FakeApi('guard'), bioKeys: FakeBioKeys(), bioBook: _FullBook())));
    await t.pumpAndSettle();
    await _openSite(t);
    await t.enterText(find.byKey(const Key('site-password')), 'pw');
    await t.tap(find.text('登录'));
    await t.pumpAndSettle();
    await t.tap(find.byKey(SiteListPage.bioOfferNoKey));
    await t.pumpAndSettle();
    expect(find.byType(NwShell), findsOneWidget);
  });

  testWidgets('外审指纹-2：到期的记录进登录页时清掉（记录和钥匙都删），只剩密码', (t) async {
    t.view.physicalSize = const Size(800, 1600);
    t.view.devicePixelRatio = 2.0;
    addTearDown(t.view.reset);
    final keys = FakeBioKeys();
    final book = BioBook();
    await keys.create('old');
    await book.put(BioRecord(site: 'ab' * 32, account: 'gina', alias: 'old', keyId: 'k' * 32,
        expiresAt: DateTime.now().millisecondsSinceEpoch - 1));
    await t.pumpWidget(MaterialApp(
        home: SiteListPage(store: MemorySiteStore([_site()]), apiFactory: (_) => FakeApi('guard'), bioKeys: keys, bioBook: book)));
    await t.pumpAndSettle();
    await _openSite(t);
    expect(find.byKey(SiteLoginPage.bioKey), findsNothing);
    expect(keys.live, isEmpty);
    expect(await book.any(_site()), isNull);
  });
}
