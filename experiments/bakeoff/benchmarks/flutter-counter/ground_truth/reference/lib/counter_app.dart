/// counter_app.dart — top-level MaterialApp wrapping CounterWidget.
///
/// Provides title, theme, and a Scaffold around the counter widget so
/// the widget can be hosted without manual Material-context wiring.

import 'package:flutter/material.dart';
import 'counter_widget.dart';

class CounterApp extends StatelessWidget {
  final int initial;
  final int min;
  final int max;
  final String title;

  const CounterApp({
    super.key,
    this.initial = 0,
    this.min = -100,
    this.max = 100,
    this.title = 'Counter',
  });

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: title,
      theme: ThemeData(useMaterial3: true),
      home: Scaffold(
        appBar: AppBar(title: Text(title)),
        body: Center(
          child: CounterWidget(initial: initial, min: min, max: max),
        ),
      ),
    );
  }
}
