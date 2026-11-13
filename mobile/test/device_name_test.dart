// W46：上装 V2 的设备健康多了主控板温度、风扇、功放，设备名说人话。
import 'package:nexwar_patrol/l10n.dart';
import 'package:nexwar_patrol/net/site_client.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('主控板、风扇、功放说人话', () {
    appLang.value = AppLang.zh;
    expect(deviceName('board'), '主控板温度');
    expect(deviceName('fan:stir'), '风扇 stir');
    expect(deviceName('amp'), '功放');
    expect(deviceName('lens:thermal'), '热像镜头');
    expect(deviceName('nav2'), '自主导航（Nav2）');
    appLang.value = AppLang.en;
    expect(deviceName('fan:stir'), 'Fan stir');
    appLang.value = AppLang.zh;
  });

  test('第 11 轮 W9-09：存储盘只是快满了，写「存储盘快满（88%）」不写「降级」', () {
    appLang.value = AppLang.zh;
    expect(deviceHead('disk', 'degraded', '已用 88%,剩 27 GB:到 90% 就不接新的巡逻'), '存储盘快满（88%）');
    expect(deviceHead('disk', 'error', '读不出来'), '存储盘：故障');
    expect(deviceHead('speaker', 'degraded', ''), '喇叭：降级');
    appLang.value = AppLang.en;
    expect(deviceHead('disk', 'degraded', '已用 88%,剩 27 GB'), 'Storage disk nearly full (88%)');
    appLang.value = AppLang.zh;
  });
}
