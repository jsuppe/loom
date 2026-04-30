import 'package:test/test.dart';
import 'package:{{ app_name }}/{{ app_name }}.dart';

void main() {
  group('Smoke', () {
    test('package loads and exposes version', () {
      expect(version, equals('0.0.1'));
    });
  });
}
