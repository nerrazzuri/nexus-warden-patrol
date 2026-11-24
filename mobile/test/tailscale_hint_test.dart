import 'package:flutter_test/flutter_test.dart';
import 'package:nexwar_patrol/net/site_client.dart';

void main() {
  test('真机 11-24：Tailscale 地址连不上，提示看看 Tailscale 开没开；别的地址不说', () {
    expect(tailscaleHint(Uri.parse('https://100.69.130.19:8443/')), contains('Tailscale'));
    expect(tailscaleHint(Uri.parse('https://100.64.0.1:8443/')), contains('Tailscale'));
    expect(tailscaleHint(Uri.parse('https://100.127.255.254:8443/')), contains('Tailscale'));
    for (final u in [
      'https://192.168.234.232:8443/',
      'https://100.63.0.1:8443/',
      'https://100.128.0.1:8443/',
      'https://site.local:8443/',
      'https://[fd7a:115c:a1e0::1]:8443/',
    ]) {
      expect(tailscaleHint(Uri.parse(u)), isEmpty, reason: u);
    }
  });

  test('真机 11-24：连不上的错误带上这句', () async {
    final c = SiteClient('https://100.64.0.1:9', 'aa' * 32,
        timeout: const Duration(milliseconds: 300));
    Object? got;
    try {
      await c.robots();
    } catch (e) {
      got = e;
    }
    expect(got, isA<SiteError>());
    expect('$got', contains('Tailscale'));
    expect((got! as SiteError).kind, anyOf('timeout', 'net'));
  });
}
