/// counter_model.dart — pure-Dart counter state with bounds + history.
///
/// No Flutter dependency. Holds value, increment/decrement/reset, and
/// records every transition. Tests cover: starting value, bounds,
/// history, reset.

class CounterModel {
  int _value;
  final int min;
  final int max;
  final List<int> _history = <int>[];

  CounterModel({int initial = 0, this.min = -100, this.max = 100})
      : _value = initial {
    if (initial < min || initial > max) {
      throw ArgumentError('initial $initial out of bounds [$min, $max]');
    }
    _history.add(initial);
  }

  int get value => _value;
  List<int> get history => List<int>.unmodifiable(_history);

  void increment() {
    if (_value >= max) {
      throw StateError('counter at max ($max)');
    }
    _value += 1;
    _history.add(_value);
  }

  void decrement() {
    if (_value <= min) {
      throw StateError('counter at min ($min)');
    }
    _value -= 1;
    _history.add(_value);
  }

  void reset() {
    _value = 0;
    _history.add(0);
  }
}
