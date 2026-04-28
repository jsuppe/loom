/// types/orders.dart — Order + Item types and OrderStatus enum.
///
/// `Item` snapshots `unitPrice` at order time so later product price
/// changes don't retroactively affect totals. `Order.total` is computed
/// from items, not stored. `Order.history` records every status change.

import '../errors.dart';

enum OrderStatus { newly, paid, shipped, delivered, cancelled }

class Item {
  final String sku;
  final int quantity;
  final double unitPrice;

  Item({required this.sku, required this.quantity, required this.unitPrice}) {
    if (quantity <= 0) {
      throw ValidationError('item quantity must be > 0');
    }
    if (unitPrice < 0) {
      throw ValidationError('item unitPrice must be >= 0');
    }
  }

  double get lineTotal => quantity * unitPrice;
}

class Transition {
  final OrderStatus? fromStatus;
  final OrderStatus toStatus;
  final DateTime timestamp;

  Transition({
    required this.fromStatus,
    required this.toStatus,
    required this.timestamp,
  });
}

class Order {
  final String id;
  final String customerId;
  final List<Item> items;
  OrderStatus status;
  final List<Transition> history;
  final List<String> reservationTokens;

  Order({
    required this.id,
    required this.customerId,
    required this.items,
    this.status = OrderStatus.newly,
    List<Transition>? history,
    List<String>? reservationTokens,
  })  : history = history ?? <Transition>[],
        reservationTokens = reservationTokens ?? <String>[] {
    if (id.isEmpty) {
      throw ValidationError('order id must be non-empty');
    }
    if (customerId.isEmpty) {
      throw ValidationError('order customerId must be non-empty');
    }
    if (items.isEmpty) {
      throw ValidationError('order must have at least one item');
    }
  }

  double get total =>
      items.fold(0.0, (sum, it) => sum + it.lineTotal);
}
