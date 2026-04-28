/// services/order_service.dart — Order placement + lifecycle.
///
/// Coordinates customer + inventory services. On `place`, validates
/// customer exists, products exist, then reserves stock for each item.
/// On reservation failure mid-loop, releases everything reserved so
/// far (atomic-ish across the call). On `ship`, commits all open
/// reservations. On `cancel` (only valid pre-ship), releases them.

import '../errors.dart';
import '../persistence.dart';
import '../types/orders.dart';
import 'customer_service.dart';
import 'inventory_service.dart';

class OrderService {
  final Store store;
  final CustomerService customers;
  final InventoryService inventory;
  int _orderSeq = 0;

  OrderService(this.store, this.customers, this.inventory);

  Order place({
    required String customerId,
    required List<({String sku, int quantity})> lines,
  }) {
    customers.get(customerId);
    if (lines.isEmpty) {
      throw ValidationError('order must have at least one line');
    }
    // Validate SKUs first so we don't reserve anything if a SKU is bogus.
    for (final l in lines) {
      inventory.getProduct(l.sku);
    }

    final orderId = 'ord-${(++_orderSeq).toString().padLeft(6, '0')}';
    final reserved = <String>[];
    final items = <Item>[];
    try {
      for (final l in lines) {
        final p = inventory.getProduct(l.sku);
        final tok = inventory.reserve(
          orderId: orderId,
          sku: l.sku,
          quantity: l.quantity,
        );
        reserved.add(tok.tokenId);
        items.add(Item(sku: l.sku, quantity: l.quantity, unitPrice: p.price));
      }
    } catch (_) {
      for (final tid in reserved) {
        inventory.release(tid);
      }
      rethrow;
    }

    final order = Order(
      id: orderId,
      customerId: customerId,
      items: items,
      reservationTokens: reserved,
    );
    order.history.add(Transition(
      fromStatus: null,
      toStatus: OrderStatus.newly,
      timestamp: DateTime.now(),
    ));
    store.orders[orderId] = order;
    return order;
  }

  Order get(String orderId) {
    final o = store.orders[orderId];
    if (o == null) {
      throw NotFoundError('order not found: $orderId');
    }
    return o;
  }

  void _transition(Order o, OrderStatus next) {
    o.history.add(Transition(
      fromStatus: o.status,
      toStatus: next,
      timestamp: DateTime.now(),
    ));
    o.status = next;
  }

  void markPaid(String orderId) {
    final o = get(orderId);
    if (o.status != OrderStatus.newly) {
      throw InvalidTransitionError(
        'cannot mark paid from ${o.status}',
      );
    }
    _transition(o, OrderStatus.paid);
  }

  void ship(String orderId) {
    final o = get(orderId);
    if (o.status != OrderStatus.paid) {
      throw InvalidTransitionError('cannot ship from ${o.status}');
    }
    for (final tid in o.reservationTokens) {
      inventory.commit(tid);
    }
    _transition(o, OrderStatus.shipped);
  }

  void deliver(String orderId) {
    final o = get(orderId);
    if (o.status != OrderStatus.shipped) {
      throw InvalidTransitionError('cannot deliver from ${o.status}');
    }
    _transition(o, OrderStatus.delivered);
  }

  void cancel(String orderId) {
    final o = get(orderId);
    if (o.status == OrderStatus.shipped ||
        o.status == OrderStatus.delivered ||
        o.status == OrderStatus.cancelled) {
      throw InvalidTransitionError('cannot cancel from ${o.status}');
    }
    for (final tid in o.reservationTokens) {
      final t = store.reservations[tid];
      if (t != null && t.isOpen) {
        inventory.release(tid);
      }
    }
    _transition(o, OrderStatus.cancelled);
  }
}
