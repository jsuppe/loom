# flutter-counter benchmark

Multi-widget Flutter benchmark — three coordinating files (model,
widget, app) over the existing `flutter_test` runner. Used to test
whether the asymmetric pipeline transfers to Flutter (widget tree,
async pumps, BuildContext state) on top of the validated
pure-Dart-test path (`dart-orders`).

## Public API

```dart
import 'package:counter_app/counter_app.dart';

void main() {
  runApp(const CounterApp(initial: 0, min: -100, max: 100));
}
```

The benchmark exercises a model with bounds + history, a
StatefulWidget that wraps the model with bound-violation handling
via SnackBar, and a top-level MaterialApp that hosts the widget.

## Files (3 executor tasks)

```
lib/
├── counter_model.dart      [task 1] — pure-Dart bounds + history
├── counter_widget.dart     [task 2] — StatefulWidget + SnackBar
└── counter_app.dart        [task 3] — MaterialApp wrapping the widget
```

## Domain model

### REQ-1: CounterModel (`lib/counter_model.dart`)

Pure-Dart class. Fields: `int _value`, `final int min`, `final int
max`, `final List<int> _history`. Constructor:
`CounterModel({int initial = 0, int min = -100, int max = 100})`.
Validates `min <= initial <= max` (else `ArgumentError`). Records
`initial` to history.

Getters: `int get value`, `List<int> get history` (returns
`List.unmodifiable(_history)`).

Methods:
- `increment()` — at max raises `StateError`; else `_value += 1` and
  appends to history.
- `decrement()` — symmetric, raises at min.
- `reset()` — sets to 0 and appends.

### REQ-2: CounterWidget (`lib/counter_widget.dart`)

`StatefulWidget` with constructor params `initial`, `min`, `max`
(defaults match CounterModel). State holds a `CounterModel`. Renders:

- `Text('${_model.value}', key: Key('counter-value'))`
- Three buttons in a `Row`:
  - decrement, key `'btn-dec'`
  - reset, key `'btn-reset'`
  - increment, key `'btn-inc'`

Increment/decrement wrap the call in try/catch on `StateError`; on
catch, show a `SnackBar` with key `'snack-inc'` / `'snack-dec'`
containing the error message. Reset always succeeds.

### REQ-3: CounterApp (`lib/counter_app.dart`)

`StatelessWidget` returning a `MaterialApp` with:

- `title` (default `'Counter'`)
- Material 3 theme
- `home: Scaffold(appBar: AppBar(title: Text(title)),
   body: Center(child: CounterWidget(initial:..., min:..., max:...)))`

## Grading

```
flutter pub get
flutter test
```

Reports `+N` per-test counts. Reference: 17/17 pass.

Tests cover:
- 9 CounterModel pure-logic tests
- 5 CounterWidget interaction tests (render, increment, decrement,
  reset, increment-at-max → snackbar)
- 3 CounterApp wrapping tests

## Why this benchmark

`dart-orders` validates the asymmetric pipeline on pure Dart
(`dart_test`). Flutter introduces:

- `pumpWidget` / `pump` async testing flow
- `BuildContext`, theme inheritance, Material widgets
- StatefulWidget lifecycle (`initState`, `setState`)
- `Key` selectors (`find.byKey`)
- ScaffoldMessenger / SnackBar interaction

These are the surfaces qwen3.5 might handle differently from pure
Dart. Flutter is also the dominant audience for the pure-Dart cell.

## Driver

A driver mirroring `phC_dart_oneshot_auto.py` (single-cell, 3-task
chain) is on the roadmap but not yet authored. Toolchain (`flutter
test`) is wired through `runners.py` (`flutter_test` runner shipped
in milestone 0.5h). Authoring the driver is small — copy
`phC_dart_oneshot_auto.py`, change `TARGET_FILES`, `BARREL_PATH`,
`PROJECT`, and the test command in `setup_workspace`.
