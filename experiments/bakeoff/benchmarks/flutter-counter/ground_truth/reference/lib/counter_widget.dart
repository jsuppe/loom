/// counter_widget.dart — StatefulWidget wrapping CounterModel.
///
/// Renders the current value and three buttons (decrement, reset,
/// increment). On increment/decrement at bounds, shows a SnackBar
/// instead of crashing.

import 'package:flutter/material.dart';
import 'counter_model.dart';

class CounterWidget extends StatefulWidget {
  final int initial;
  final int min;
  final int max;

  const CounterWidget({
    super.key,
    this.initial = 0,
    this.min = -100,
    this.max = 100,
  });

  @override
  State<CounterWidget> createState() => _CounterWidgetState();
}

class _CounterWidgetState extends State<CounterWidget> {
  late CounterModel _model;

  @override
  void initState() {
    super.initState();
    _model = CounterModel(
      initial: widget.initial, min: widget.min, max: widget.max);
  }

  void _safe(void Function() action, String label) {
    try {
      setState(action);
    } on StateError catch (e) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('$label: ${e.message}'), key: Key('snack-$label')));
    }
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Text('${_model.value}', key: const Key('counter-value'),
            style: Theme.of(context).textTheme.headlineMedium),
        Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            TextButton(
              key: const Key('btn-dec'),
              onPressed: () => _safe(_model.decrement, 'dec'),
              child: const Text('-'),
            ),
            TextButton(
              key: const Key('btn-reset'),
              onPressed: () => setState(_model.reset),
              child: const Text('reset'),
            ),
            TextButton(
              key: const Key('btn-inc'),
              onPressed: () => _safe(_model.increment, 'inc'),
              child: const Text('+'),
            ),
          ],
        ),
      ],
    );
  }
}
