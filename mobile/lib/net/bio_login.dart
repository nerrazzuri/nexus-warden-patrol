/// 手机指纹登录（用户 11-20）。
///
/// 手机在 Android Keystore 里生成一把 P-256 私钥，**要按指纹才能用**、录了新指纹就作废、出不了这部手机
/// （原生部分 `BioKey.kt`）；站点只存公钥（`/api/me/bio`）。登录时站点出一次性随机数，这里按指纹签了
/// 换一个普通会话（`/api/login/bio`）。手机上不存密码、不存令牌，只记「这个站点、这个账号用哪把钥匙」。
///
/// 站点那头 30 天到期；改口令、改角色、停用账号、管理员撤销都作废 —— 站点回 `bio_gone`，这里删掉
/// 钥匙和记录，人照旧输密码，登上以后可以再开。
library;

import 'dart:convert';
import 'dart:io';
import 'dart:math';

import 'package:flutter/services.dart';

import '../l10n.dart';
import '../store/site_store.dart';
import 'site_client.dart';

/// 签名框按了以后的结果：`ok`、`cancelled`、`invalidated`（钥匙作废了）、`lockout`、`error`。
class BioSign {
  final String result;
  final List<int>? sig;
  const BioSign(this.result, [this.sig]);
  bool get ok => result == 'ok' && sig != null;
}

/// 指纹钥匙的平台那一半（测试换成假的）。
abstract class BioKeys {
  Future<bool> available();
  Future<List<int>> create(String alias);
  Future<BioSign> sign(String alias, List<int> data, {required String title, required String subtitle, required String cancel});
  Future<void> delete(String alias);
}

/// 真的：Android 走 `nexwar/bio`；别的平台（桌面版）一律不支持。
class ChannelBioKeys implements BioKeys {
  static const MethodChannel _ch = MethodChannel('nexwar/bio');
  const ChannelBioKeys();

  @override
  Future<bool> available() async {
    if (!Platform.isAndroid) return false;
    try {
      return await _ch.invokeMethod<bool>('available') ?? false;
    } on Object {
      return false;
    }
  }

  @override
  Future<List<int>> create(String alias) async =>
      (await _ch.invokeMethod<Uint8List>('create', <String, dynamic>{'alias': alias})) ?? Uint8List(0);

  @override
  Future<BioSign> sign(String alias, List<int> data,
      {required String title, required String subtitle, required String cancel}) async {
    try {
      final r = await _ch.invokeMapMethod<String, dynamic>('sign', <String, dynamic>{
        'alias': alias, 'data': Uint8List.fromList(data), 'title': title, 'subtitle': subtitle, 'cancel': cancel});
      final sig = r?['sig'];
      return BioSign('${r?['result'] ?? 'error'}', sig is Uint8List ? sig : null);
    } on Object {
      return const BioSign('error');
    }
  }

  @override
  Future<void> delete(String alias) async {
    try {
      await _ch.invokeMethod<void>('delete', <String, dynamic>{'alias': alias});
    } on Object {
      // 删不掉也没关系：站点那头会作废
    }
  }
}

/// 这个站点、这个账号用的那把钥匙。
class BioRecord {
  final String site;
  final String account;
  final String alias;
  final String keyId;
  final int expiresAt;
  const BioRecord({required this.site, required this.account, required this.alias, required this.keyId, required this.expiresAt});

  Map<String, dynamic> toJson() =>
      <String, dynamic>{'site': site, 'account': account, 'alias': alias, 'key_id': keyId, 'expires_at': expiresAt};

  static BioRecord? fromJson(Object? d) {
    if (d is! Map) return null;
    final v = [d['site'], d['account'], d['alias'], d['key_id']];
    if (v.any((x) => x is! String || x.isEmpty) || d['expires_at'] is! int) return null;
    return BioRecord(site: d['site'] as String, account: d['account'] as String, alias: d['alias'] as String,
        keyId: d['key_id'] as String, expiresAt: d['expires_at'] as int);
  }
}

/// 一个站点认哪个：有证书指纹用指纹（重装了证书钥匙也就没用了），没有用地址。
String bioSiteKey(SiteEntry s) => s.fingerprint.isNotEmpty ? s.fingerprint : s.url;

/// 记录：每个站点最多一条（一部手机一个站点只给一个账号开指纹）；还有「不用了」点过的（站点|账号）。
class BioBook {
  final File? file;
  final Map<String, BioRecord> _records = <String, BioRecord>{};
  final Set<String> _declined = <String>{};
  bool _loaded = false;
  BioBook([this.file]);

  Future<void> _load() async {
    if (_loaded) return;
    _loaded = true;
    final f = file;
    if (f == null) return;
    try {
      if (!await f.exists()) return;
      final d = jsonDecode(await f.readAsString());
      if (d is! Map) return;
      for (final r in (d['records'] as List? ?? const [])) {
        final b = BioRecord.fromJson(r);
        if (b != null) _records[b.site] = b;
      }
      _declined.addAll((d['declined'] as List? ?? const []).whereType<String>());
    } on Object {
      // 读不出来当没有：照旧输密码
    }
  }

  Future<void> _save() async {
    final f = file;
    if (f == null) return;
    final tmp = File('${f.path}.tmp');
    await tmp.writeAsString(jsonEncode(<String, dynamic>{
      'records': [for (final r in _records.values) r.toJson()],
      'declined': _declined.toList(),
    }), flush: true);
    await tmp.rename(f.path);
  }

  Future<BioRecord?> of(SiteEntry s, int nowMs) async {
    await _load();
    final r = _records[bioSiteKey(s)];
    return r != null && r.expiresAt > nowMs ? r : null;
  }

  /// 这个站点的记录，不管到没到期（清理到期的用）。
  Future<BioRecord?> any(SiteEntry s) async {
    await _load();
    return _records[bioSiteKey(s)];
  }

  Future<bool> declined(SiteEntry s, String account) async {
    await _load();
    return _declined.contains('${bioSiteKey(s)}|$account');
  }

  Future<void> decline(SiteEntry s, String account) async {
    await _load();
    _declined.add('${bioSiteKey(s)}|$account');
    await _save();
  }

  Future<void> put(BioRecord r) async {
    await _load();
    _records[r.site] = r;
    _declined.remove('${r.site}|${r.account}');
    await _save();
  }

  Future<BioRecord?> remove(SiteEntry s) async {
    await _load();
    final r = _records.remove(bioSiteKey(s));
    if (r != null) await _save();
    return r;
  }
}

/// 这个站点能用的那条记录。到期了的顺手清掉（记录和 Keystore 里的钥匙都删；外审指纹-2 Minor 1），
/// 回 null。
Future<BioRecord?> bioRecordFor(BioKeys keys, BioBook book, SiteEntry s, int nowMs) async {
  final r = await book.any(s);
  if (r == null || r.expiresAt > nowMs) return r;
  try {
    await book.remove(s);
  } on Object {
    // 写不进去：下次再清
  }
  await keys.delete(r.alias);
  return null;
}

/// 签的内容：跟站点 `accounts.BIO_ENROLL` / `BIO_LOGIN` 一字不差。
List<int> bioMessage(String purpose, String nonce, String subject) =>
    <int>[...utf8.encode('nexwar-bio-$purpose'), 0, ...utf8.encode(nonce), 0, ...utf8.encode(subject)];

String _newAlias() {
  final r = Random.secure();
  return 'nexwar-bio-${List<int>.generate(12, (_) => r.nextInt(256)).map((b) => b.toRadixString(16).padLeft(2, '0')).join()}';
}

/// 指纹登录不成的原因（给登录页说）。
class BioFailure implements Exception {
  final String message;
  /// 钥匙没了（站点作废了、录了新指纹）：记录已经删掉，这个站点不再显示指纹登录。
  final bool gone;
  /// 人自己按了「用密码」：不用说什么。
  final bool cancelled;
  const BioFailure(this.message, {this.gone = false, this.cancelled = false});
  @override
  String toString() => message;
}

String get _cancelText => tr('Use password', '用密码');

/// 登记：已经登录了 [api]（账号 [account]），生成钥匙、按一次指纹、交给站点、记下。成了回 true；
/// 人取消了回 false；别的错抛 [BioFailure]。
Future<bool> bioEnroll(SiteApi api, BioKeys keys, BioBook book, SiteEntry s, String account,
    {String label = ''}) async {
  final alias = _newAlias();
  try {
    final pub = await keys.create(alias);
    final nonce = await api.bioEnrollNonce();
    final r = await keys.sign(alias, bioMessage('enroll', nonce, account),
        title: tr('Turn on fingerprint sign-in', '开启指纹登录'),
        subtitle: tr('Confirm with your fingerprint for ${s.name}', '按指纹确认（${s.name}）'),
        cancel: tr('Cancel', '取消'));
    if (!r.ok) {
      await keys.delete(alias);
      if (r.result == 'cancelled') return false;
      throw BioFailure(tr('Fingerprint check failed (${r.result})', '指纹验证没通过（${r.result}）'));
    }
    final d = await api.bioEnroll(pub, label, nonce, r.sig!);
    final kid = d['key_id'], exp = d['expires_at'];
    if (kid is! String || exp is! int) throw BioFailure(tr('The site did not accept it', '站点没收下'));
    final old = await book.remove(s);
    if (old != null) await keys.delete(old.alias);
    await book.put(BioRecord(site: bioSiteKey(s), account: account, alias: alias, keyId: kid, expiresAt: exp));
    return true;
  } on BioFailure {
    rethrow;
  } on Object catch (e) {
    await keys.delete(alias);
    throw BioFailure(tr("Couldn't turn on fingerprint sign-in: $e", '没开成指纹登录：$e'));
  }
}

/// 用指纹登录 [api]（还没登录的连接）。成了回会话；不成抛 [BioFailure]（钥匙作废的已经删干净）。
/// 连不上站点（状态 0）原样抛 [SiteError]，好让调用方换下一个地址。
Future<SiteSession> bioSignIn(SiteApi api, BioKeys keys, BioBook book, SiteEntry s, BioRecord rec) async {
  Future<Never> gone(String why) async {
    await book.remove(s);
    await keys.delete(rec.alias);
    throw BioFailure(why, gone: true);
  }

  final nonce = await api.bioLoginNonce(rec.keyId);
  final r = await keys.sign(rec.alias, bioMessage('login', nonce, rec.keyId),
      title: tr('Sign in to ${s.name}', '登录 ${s.name}'),
      subtitle: tr('Account ${rec.account}', '账号 ${rec.account}'),
      cancel: _cancelText);
  if (!r.ok) {
    if (r.result == 'cancelled') throw const BioFailure('', cancelled: true);
    if (r.result == 'invalidated') {
      return gone(tr('Fingerprints on this phone changed. Sign in with your password, then turn fingerprint sign-in on again.',
          '这部手机的指纹有变动，请用密码登录，登录后可以重新开启指纹登录。'));
    }
    if (r.result == 'lockout') {
      throw BioFailure(tr('Too many fingerprint attempts. Use your password.', '指纹试错太多次，请用密码登录。'));
    }
    throw BioFailure(tr('Fingerprint check failed. Use your password.', '指纹验证没通过，请用密码登录。'));
  }
  try {
    return await api.bioLogin(rec.keyId, nonce, r.sig!);
  } on SiteError catch (e) {
    if (e.body['bio_gone'] == true) {
      return gone(tr('Fingerprint sign-in has been turned off for this phone (password changed, account changed or revoked). Sign in with your password.',
          '这部手机的指纹登录已失效（改过密码、账号有变动或被撤销），请用密码登录。'));
    }
    rethrow;
  }
}

/// 关掉这部手机在这个站点的指纹登录：站点那头撤（[api] 登着的话）、删钥匙、删记录。
Future<void> bioTurnOff(SiteApi? api, BioKeys keys, BioBook book, SiteEntry s) async {
  final r = await book.remove(s);
  if (r == null) return;
  await keys.delete(r.alias);
  if (api != null) {
    try {
      await api.bioRevoke(keyId: r.keyId);
    } on Object {
      // 站点那头撤不掉：私钥已经删了，没人能再用它；30 天后自己到期
    }
  }
}
