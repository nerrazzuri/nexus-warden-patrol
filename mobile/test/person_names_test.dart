import 'package:flutter_test/flutter_test.dart';
import 'package:nexwar_patrol/net/person_names.dart';

void main() {
  test('易用性 37 场景测试：谁接的、谁派的显示人名；没起名、老站点不带这一项照旧显示登录名', () {
    addTearDown(() => personNames.value = const {});
    updatePersonNames({'gina': 'Gina Tan', 'bob': ''});
    expect(personName('gina'), 'Gina Tan');
    expect(personName('bob'), 'bob');
    expect(personName(null), '');
    updatePersonNames(null);
    expect(personName('gina'), 'Gina Tan', reason: '不是 Map 不动');
  });
}
