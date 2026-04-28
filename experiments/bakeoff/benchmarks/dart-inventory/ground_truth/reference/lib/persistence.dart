/// persistence.dart — In-memory store shared by all services.
///
/// Holds maps keyed by id/sku/orderId/tokenId. `snapshot()` returns a
/// deep-enough copy for round-trip restore in tests. `restore()`
/// replaces all current state with a snapshot.

import 'types/customers.dart';
import 'types/products.dart';
import 'types/inventory.dart';
import 'types/orders.dart';

class Snapshot {
  final Map<String, Customer> customers;
  final Map<String, Product> products;
  final Map<String, StockLevel> stock;
  final Map<String, Order> orders;
  final Map<String, ReservationToken> reservations;

  Snapshot({
    required this.customers,
    required this.products,
    required this.stock,
    required this.orders,
    required this.reservations,
  });
}

class Store {
  final Map<String, Customer> customers = <String, Customer>{};
  final Map<String, Product> products = <String, Product>{};
  final Map<String, StockLevel> stock = <String, StockLevel>{};
  final Map<String, Order> orders = <String, Order>{};
  final Map<String, ReservationToken> reservations =
      <String, ReservationToken>{};

  Snapshot snapshot() {
    return Snapshot(
      customers: Map<String, Customer>.from(customers),
      products: Map<String, Product>.from(products),
      stock: stock.map(
        (k, v) => MapEntry(
          k,
          StockLevel(sku: v.sku, onHand: v.onHand, reserved: v.reserved),
        ),
      ),
      orders: orders.map(
        (k, v) => MapEntry(
          k,
          Order(
            id: v.id,
            customerId: v.customerId,
            items: List<Item>.from(v.items),
            status: v.status,
            history: List<Transition>.from(v.history),
            reservationTokens: List<String>.from(v.reservationTokens),
          ),
        ),
      ),
      reservations: reservations.map(
        (k, v) => MapEntry(
          k,
          ReservationToken(
            tokenId: v.tokenId,
            orderId: v.orderId,
            sku: v.sku,
            quantity: v.quantity,
            committed: v.committed,
            released: v.released,
          ),
        ),
      ),
    );
  }

  void restore(Snapshot snap) {
    customers
      ..clear()
      ..addAll(snap.customers);
    products
      ..clear()
      ..addAll(snap.products);
    stock
      ..clear()
      ..addAll(snap.stock);
    orders
      ..clear()
      ..addAll(snap.orders);
    reservations
      ..clear()
      ..addAll(snap.reservations);
  }
}
