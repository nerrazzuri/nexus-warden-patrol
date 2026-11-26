// 用户 11-26「建图名字这很重要」：建图向导填的名字是整张图的显示名，App 各处按它显示（没起名写地图号）。
import 'package:flutter_test/flutter_test.dart';
import 'package:nexwar_patrol/net/map_names.dart';

void main() {
  tearDown(() => mapNames.value = const {});

  test('起了名写名字，没起写地图号；站点回的不是 Map 不动', () {
    expect(mapName('main'), 'main');
    updateMapNames({'main': 'Elmina', 'b': ''});
    expect(mapName('main'), 'Elmina');
    expect(mapName('b'), 'b');
    expect(mapName(null), '');
    updateMapNames(null);
    expect(mapName('main'), 'Elmina');
    updateMapNames(<String, dynamic>{});
    expect(mapName('main'), 'main');
  });
}
