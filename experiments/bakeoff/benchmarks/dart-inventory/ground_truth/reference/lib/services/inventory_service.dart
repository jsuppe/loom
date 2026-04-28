/// services/inventory_service.dart — Product catalog + stock + reservations.
///
/// Reservation lifecycle (one token per (order, sku) line):
///   reserve()  -> opens token, increments StockLevel.reserved
///   commit()   -> closes token, decrements onHand AND reserved
///   release()  -> closes token, decrements reserved (returns to available)
/// A token can be committed XOR released, never both, and never twice.

import '../errors.dart';
import '../persistence.dart';
import '../types/products.dart';
import '../types/inventory.dart';

class InventoryService {
  final Store store;
  int _tokenSeq = 0;

  InventoryService(this.store);

  Product registerProduct({
    required String sku,
    required String name,
    required double price,
  }) {
    if (store.products.containsKey(sku)) {
      throw ConflictError('product with sku $sku already exists');
    }
    final p = Product(sku: sku, name: name, price: price);
    store.products[sku] = p;
    store.stock[sku] = StockLevel(sku: sku);
    return p;
  }

  Product getProduct(String sku) {
    final p = store.products[sku];
    if (p == null) {
      throw NotFoundError('product not found: $sku');
    }
    return p;
  }

  StockLevel stockOf(String sku) {
    final s = store.stock[sku];
    if (s == null) {
      throw NotFoundError('no stock record for sku $sku');
    }
    return s;
  }

  void addStock(String sku, int qty) {
    if (qty <= 0) {
      throw ValidationError('addStock qty must be > 0');
    }
    final s = stockOf(sku);
    s.onHand += qty;
  }

  ReservationToken reserve({
    required String orderId,
    required String sku,
    required int quantity,
  }) {
    if (quantity <= 0) {
      throw ValidationError('reserve quantity must be > 0');
    }
    final s = stockOf(sku);
    if (s.available < quantity) {
      throw InsufficientStockError(
        'insufficient stock for $sku: have ${s.available}, need $quantity',
      );
    }
    s.reserved += quantity;
    final tokenId = 'rsv-${(++_tokenSeq).toString().padLeft(6, '0')}';
    final token = ReservationToken(
      tokenId: tokenId,
      orderId: orderId,
      sku: sku,
      quantity: quantity,
    );
    store.reservations[tokenId] = token;
    return token;
  }

  void commit(String tokenId) {
    final t = store.reservations[tokenId];
    if (t == null) {
      throw NotFoundError('reservation not found: $tokenId');
    }
    if (!t.isOpen) {
      throw ReservationError('reservation $tokenId already closed');
    }
    final s = stockOf(t.sku);
    s.onHand -= t.quantity;
    s.reserved -= t.quantity;
    t.committed = true;
  }

  void release(String tokenId) {
    final t = store.reservations[tokenId];
    if (t == null) {
      throw NotFoundError('reservation not found: $tokenId');
    }
    if (!t.isOpen) {
      throw ReservationError('reservation $tokenId already closed');
    }
    final s = stockOf(t.sku);
    s.reserved -= t.quantity;
    t.released = true;
  }
}
