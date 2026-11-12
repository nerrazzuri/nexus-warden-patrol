// 易用性第 6 轮 A6-07：App 日志太少（只有启动和上传两行）—— 登录、派单这些改了东西的请求，成了也记一行
// （只记方法、路径、用时，不带请求体和查询串）。真 HTTPS 的假站点，单独一个文件。
import 'package:flutter_test/flutter_test.dart';
import 'package:nexwar_patrol/net/app_log.dart';
import 'package:nexwar_patrol/net/site_client.dart';

import 'support/fake_site.dart';

void main() {
  late FakeSite site;
  setUp(() async {
    site = FakeSite();
    await site.start();
  });
  tearDown(() async => site.close());

  test('登录成了记一行（不带密码）；只读的 GET 不记', () async {
    final before = AppLog.instance.text().length;
    final c = SiteClient(site.url, testCertFingerprint());
    await c.login('alice', 'correct-horse-battery');
    await c.robots();
    final got = AppLog.instance.text().substring(before);
    expect(got, contains('POST /api/login → ok'));
    expect(got, isNot(contains('correct-horse-battery')));
    expect(got, isNot(contains('GET /api/robots')), reason: '轮询不刷屏');
    c.close();
  });
}
