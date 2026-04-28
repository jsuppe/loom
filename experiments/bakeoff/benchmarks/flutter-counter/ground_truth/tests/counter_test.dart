// counter_test.dart — hidden test suite for the flutter-counter benchmark.
// Never shown to the planning or executor agents.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:counter_app/counter_model.dart';
import 'package:counter_app/counter_widget.dart';
import 'package:counter_app/counter_app.dart';

void main() {
  // ============================================================
  // CounterModel — pure-Dart logic
  // ============================================================
  group('CounterModel', () {
    test('initial value defaults to 0', () {
      final m = CounterModel();
      expect(m.value, 0);
    });

    test('initial value can be set', () {
      final m = CounterModel(initial: 5);
      expect(m.value, 5);
    });

    test('initial out of bounds raises ArgumentError', () {
      expect(() => CounterModel(initial: 200, max: 100),
          throwsA(isA<ArgumentError>()));
    });

    test('increment + decrement', () {
      final m = CounterModel();
      m.increment();
      m.increment();
      m.decrement();
      expect(m.value, 1);
    });

    test('increment at max raises StateError', () {
      final m = CounterModel(initial: 100, max: 100);
      expect(() => m.increment(), throwsA(isA<StateError>()));
    });

    test('decrement at min raises StateError', () {
      final m = CounterModel(initial: -100, min: -100);
      expect(() => m.decrement(), throwsA(isA<StateError>()));
    });

    test('reset returns to 0', () {
      final m = CounterModel(initial: 7);
      m.increment();
      m.reset();
      expect(m.value, 0);
    });

    test('history records every transition', () {
      final m = CounterModel(initial: 5);
      m.increment();
      m.decrement();
      m.reset();
      // initial(5) + inc(6) + dec(5) + reset(0) = 4 entries
      expect(m.history, [5, 6, 5, 0]);
    });

    test('history is unmodifiable from outside', () {
      final m = CounterModel();
      expect(() => m.history.add(99), throwsA(isA<UnsupportedError>()));
    });
  });

  // ============================================================
  // CounterWidget — Flutter widget rendering + interaction
  // ============================================================
  group('CounterWidget', () {
    testWidgets('renders initial value', (tester) async {
      await tester.pumpWidget(const MaterialApp(
        home: Scaffold(body: CounterWidget(initial: 7)),
      ));
      expect(find.text('7'), findsOneWidget);
    });

    testWidgets('increment button increases the value', (tester) async {
      await tester.pumpWidget(const MaterialApp(
        home: Scaffold(body: CounterWidget(initial: 0)),
      ));
      await tester.tap(find.byKey(const Key('btn-inc')));
      await tester.pump();
      expect(find.text('1'), findsOneWidget);
    });

    testWidgets('decrement button decreases the value', (tester) async {
      await tester.pumpWidget(const MaterialApp(
        home: Scaffold(body: CounterWidget(initial: 5)),
      ));
      await tester.tap(find.byKey(const Key('btn-dec')));
      await tester.pump();
      expect(find.text('4'), findsOneWidget);
    });

    testWidgets('reset button restores 0', (tester) async {
      await tester.pumpWidget(const MaterialApp(
        home: Scaffold(body: CounterWidget(initial: 5)),
      ));
      await tester.tap(find.byKey(const Key('btn-reset')));
      await tester.pump();
      expect(find.text('0'), findsOneWidget);
    });

    testWidgets('increment at max shows snackbar instead of crashing',
        (tester) async {
      await tester.pumpWidget(const MaterialApp(
        home: Scaffold(body: CounterWidget(initial: 5, max: 5)),
      ));
      await tester.tap(find.byKey(const Key('btn-inc')));
      await tester.pump();
      expect(find.byKey(const Key('snack-inc')), findsOneWidget);
      expect(find.text('5'), findsOneWidget);
    });
  });

  // ============================================================
  // CounterApp — top-level wrapping
  // ============================================================
  group('CounterApp', () {
    testWidgets('default app has Counter app bar title',
        (tester) async {
      await tester.pumpWidget(const CounterApp());
      expect(find.text('Counter'), findsWidgets);
    });

    testWidgets('custom title appears in app bar', (tester) async {
      await tester.pumpWidget(const CounterApp(title: 'My Counter'));
      expect(find.text('My Counter'), findsWidgets);
    });

    testWidgets('CounterApp hosts a working CounterWidget', (tester) async {
      await tester.pumpWidget(const CounterApp(initial: 3));
      expect(find.text('3'), findsOneWidget);
      await tester.tap(find.byKey(const Key('btn-inc')));
      await tester.pump();
      expect(find.text('4'), findsOneWidget);
    });
  });
}
