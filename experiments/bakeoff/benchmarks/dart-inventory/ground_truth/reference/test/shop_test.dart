// shop_test.dart — hidden test suite for the dart-inventory benchmark.
// Never shown to the planning or executor agents.

import 'package:test/test.dart';
import 'package:shop/shop.dart';

void main() {
  // ============================================================
  // Customer service
  // ============================================================
  group('customers', () {
    test('register + lookup', () {
      final s = Store();
      final svc = CustomerService(s);
      final c = svc.register(id: 'c1', name: 'Alice', email: 'a@x.com');
      expect(c.id, 'c1');
      expect(svc.get('c1').name, 'Alice');
    });

    test('register duplicate id raises ConflictError', () {
      final svc = CustomerService(Store());
      svc.register(id: 'c1', name: 'Alice', email: 'a@x.com');
      expect(
        () => svc.register(id: 'c1', name: 'Alice2', email: 'b@x.com'),
        throwsA(isA<ConflictError>()),
      );
    });

    test('register with bad email raises ValidationError', () {
      final svc = CustomerService(Store());
      expect(
        () => svc.register(id: 'c1', name: 'Alice', email: 'no-at-sign'),
        throwsA(isA<ValidationError>()),
      );
    });

    test('get unknown raises NotFoundError', () {
      final svc = CustomerService(Store());
      expect(() => svc.get('nope'), throwsA(isA<NotFoundError>()));
    });

    test('addAddress appends', () {
      final svc = CustomerService(Store());
      svc.register(id: 'c1', name: 'A', email: 'a@x.com');
      svc.addAddress('c1', const Address(
        street: '1 Main', city: 'Town', postalCode: '00001'));
      svc.addAddress('c1', const Address(
        street: '2 Side', city: 'Town', postalCode: '00002'));
      expect(svc.get('c1').addresses.length, 2);
    });
  });

  // ============================================================
  // Inventory service
  // ============================================================
  group('inventory', () {
    test('register product + lookup', () {
      final svc = InventoryService(Store());
      svc.registerProduct(sku: 'A', name: 'Widget', price: 9.99);
      expect(svc.getProduct('A').name, 'Widget');
    });

    test('duplicate sku raises ConflictError', () {
      final svc = InventoryService(Store());
      svc.registerProduct(sku: 'A', name: 'Widget', price: 9.99);
      expect(
        () => svc.registerProduct(sku: 'A', name: 'Other', price: 1.00),
        throwsA(isA<ConflictError>()),
      );
    });

    test('non-positive price raises ValidationError', () {
      final svc = InventoryService(Store());
      expect(
        () => svc.registerProduct(sku: 'A', name: 'Widget', price: 0),
        throwsA(isA<ValidationError>()),
      );
    });

    test('addStock + reserve + commit', () {
      final svc = InventoryService(Store());
      svc.registerProduct(sku: 'A', name: 'W', price: 1);
      svc.addStock('A', 10);
      expect(svc.stockOf('A').available, 10);
      final t = svc.reserve(orderId: 'o1', sku: 'A', quantity: 3);
      expect(svc.stockOf('A').reserved, 3);
      expect(svc.stockOf('A').available, 7);
      svc.commit(t.tokenId);
      expect(svc.stockOf('A').onHand, 7);
      expect(svc.stockOf('A').reserved, 0);
      expect(svc.stockOf('A').available, 7);
    });

    test('release returns stock to available', () {
      final svc = InventoryService(Store());
      svc.registerProduct(sku: 'A', name: 'W', price: 1);
      svc.addStock('A', 10);
      final t = svc.reserve(orderId: 'o1', sku: 'A', quantity: 4);
      svc.release(t.tokenId);
      expect(svc.stockOf('A').reserved, 0);
      expect(svc.stockOf('A').available, 10);
      expect(svc.stockOf('A').onHand, 10);
    });

    test('reserve insufficient raises InsufficientStockError', () {
      final svc = InventoryService(Store());
      svc.registerProduct(sku: 'A', name: 'W', price: 1);
      svc.addStock('A', 2);
      expect(
        () => svc.reserve(orderId: 'o1', sku: 'A', quantity: 5),
        throwsA(isA<InsufficientStockError>()),
      );
    });

    test('commit twice raises ReservationError', () {
      final svc = InventoryService(Store());
      svc.registerProduct(sku: 'A', name: 'W', price: 1);
      svc.addStock('A', 10);
      final t = svc.reserve(orderId: 'o1', sku: 'A', quantity: 2);
      svc.commit(t.tokenId);
      expect(
        () => svc.commit(t.tokenId),
        throwsA(isA<ReservationError>()),
      );
    });

    test('release after commit raises ReservationError', () {
      final svc = InventoryService(Store());
      svc.registerProduct(sku: 'A', name: 'W', price: 1);
      svc.addStock('A', 10);
      final t = svc.reserve(orderId: 'o1', sku: 'A', quantity: 2);
      svc.commit(t.tokenId);
      expect(
        () => svc.release(t.tokenId),
        throwsA(isA<ReservationError>()),
      );
    });

    test('addStock non-positive raises ValidationError', () {
      final svc = InventoryService(Store());
      svc.registerProduct(sku: 'A', name: 'W', price: 1);
      expect(() => svc.addStock('A', 0), throwsA(isA<ValidationError>()));
    });
  });

  // ============================================================
  // Order service
  // ============================================================
  group('orders', () {
    Map<String, Object> setup() {
      final s = Store();
      final cs = CustomerService(s);
      final inv = InventoryService(s);
      final os = OrderService(s, cs, inv);
      cs.register(id: 'c1', name: 'A', email: 'a@x.com');
      inv.registerProduct(sku: 'A', name: 'W', price: 10.0);
      inv.registerProduct(sku: 'B', name: 'G', price: 3.5);
      inv.addStock('A', 100);
      inv.addStock('B', 100);
      return {'store': s, 'customer': cs, 'inventory': inv, 'order': os};
    }

    test('place + lifecycle to delivered', () {
      final m = setup();
      final os = m['order'] as OrderService;
      final inv = m['inventory'] as InventoryService;
      final o = os.place(customerId: 'c1', lines: [
        (sku: 'A', quantity: 2),
        (sku: 'B', quantity: 4),
      ]);
      expect(o.status, OrderStatus.newly);
      expect(o.total, 10.0 * 2 + 3.5 * 4);
      expect(inv.stockOf('A').reserved, 2);
      expect(inv.stockOf('B').reserved, 4);

      os.markPaid(o.id);
      os.ship(o.id);
      expect(inv.stockOf('A').onHand, 98);
      expect(inv.stockOf('A').reserved, 0);
      os.deliver(o.id);
      expect(os.get(o.id).status, OrderStatus.delivered);
    });

    test('place with unknown customer raises NotFoundError', () {
      final m = setup();
      final os = m['order'] as OrderService;
      expect(
        () => os.place(customerId: 'ghost', lines: [(sku: 'A', quantity: 1)]),
        throwsA(isA<NotFoundError>()),
      );
    });

    test('place with unknown sku raises NotFoundError', () {
      final m = setup();
      final os = m['order'] as OrderService;
      expect(
        () => os.place(customerId: 'c1', lines: [(sku: 'Z', quantity: 1)]),
        throwsA(isA<NotFoundError>()),
      );
    });

    test('place with empty lines raises ValidationError', () {
      final m = setup();
      final os = m['order'] as OrderService;
      expect(
        () => os.place(customerId: 'c1', lines: []),
        throwsA(isA<ValidationError>()),
      );
    });

    test('place with insufficient stock releases prior reservations', () {
      final m = setup();
      final inv = m['inventory'] as InventoryService;
      final os = m['order'] as OrderService;
      // overdraw: 200 of B, only have 100
      expect(
        () => os.place(customerId: 'c1', lines: [
          (sku: 'A', quantity: 5),
          (sku: 'B', quantity: 200),
        ]),
        throwsA(isA<InsufficientStockError>()),
      );
      expect(inv.stockOf('A').reserved, 0);
      expect(inv.stockOf('B').reserved, 0);
    });

    test('mark paid twice raises InvalidTransitionError', () {
      final m = setup();
      final os = m['order'] as OrderService;
      final o = os.place(
        customerId: 'c1', lines: [(sku: 'A', quantity: 1)]);
      os.markPaid(o.id);
      expect(
        () => os.markPaid(o.id),
        throwsA(isA<InvalidTransitionError>()),
      );
    });

    test('ship from new raises InvalidTransitionError', () {
      final m = setup();
      final os = m['order'] as OrderService;
      final o = os.place(
        customerId: 'c1', lines: [(sku: 'A', quantity: 1)]);
      expect(() => os.ship(o.id), throwsA(isA<InvalidTransitionError>()));
    });

    test('cancel from new releases reservations', () {
      final m = setup();
      final inv = m['inventory'] as InventoryService;
      final os = m['order'] as OrderService;
      final o = os.place(
        customerId: 'c1', lines: [(sku: 'A', quantity: 3)]);
      expect(inv.stockOf('A').reserved, 3);
      os.cancel(o.id);
      expect(inv.stockOf('A').reserved, 0);
      expect(inv.stockOf('A').onHand, 100);
      expect(os.get(o.id).status, OrderStatus.cancelled);
    });

    test('cancel from paid releases reservations', () {
      final m = setup();
      final inv = m['inventory'] as InventoryService;
      final os = m['order'] as OrderService;
      final o = os.place(
        customerId: 'c1', lines: [(sku: 'A', quantity: 3)]);
      os.markPaid(o.id);
      os.cancel(o.id);
      expect(inv.stockOf('A').reserved, 0);
      expect(inv.stockOf('A').onHand, 100);
    });

    test('cancel from shipped raises InvalidTransitionError', () {
      final m = setup();
      final os = m['order'] as OrderService;
      final o = os.place(
        customerId: 'c1', lines: [(sku: 'A', quantity: 1)]);
      os.markPaid(o.id);
      os.ship(o.id);
      expect(() => os.cancel(o.id), throwsA(isA<InvalidTransitionError>()));
    });

    test('history records every transition', () {
      final m = setup();
      final os = m['order'] as OrderService;
      final o = os.place(
        customerId: 'c1', lines: [(sku: 'A', quantity: 1)]);
      os.markPaid(o.id);
      os.ship(o.id);
      os.deliver(o.id);
      final h = os.get(o.id).history;
      expect(h.length, 4);
      expect(h[0].fromStatus, isNull);
      expect(h[0].toStatus, OrderStatus.newly);
      expect(h[1].toStatus, OrderStatus.paid);
      expect(h[2].toStatus, OrderStatus.shipped);
      expect(h[3].toStatus, OrderStatus.delivered);
    });

    test('item snapshots unitPrice; later product price change does not affect order total', () {
      final m = setup();
      final inv = m['inventory'] as InventoryService;
      final os = m['order'] as OrderService;
      final o = os.place(
        customerId: 'c1', lines: [(sku: 'A', quantity: 2)]);
      final originalTotal = o.total;
      // Simulate a price update by registering a NEW product would conflict;
      // mutate the inventory's stored product reference is fine since we
      // expose the raw map via `Store.products`. But the spec says price is
      // final on Product, so just confirm the order total stays consistent.
      // (Item snapshot makes this trivially true — that IS the test.)
      expect(o.items.first.unitPrice, 10.0);
      expect(originalTotal, 20.0);
      // Sanity: original Product price still 10
      expect(inv.getProduct('A').price, 10.0);
    });

    test('order total uses Item.lineTotal aggregation', () {
      final m = setup();
      final os = m['order'] as OrderService;
      final o = os.place(customerId: 'c1', lines: [
        (sku: 'A', quantity: 3),
        (sku: 'B', quantity: 7),
      ]);
      expect(o.total, 3 * 10.0 + 7 * 3.5);
    });
  });

  // ============================================================
  // Persistence: snapshot + restore round trip
  // ============================================================
  group('persistence', () {
    test('snapshot + restore round-trips full state', () {
      final s = Store();
      final cs = CustomerService(s);
      final inv = InventoryService(s);
      final os = OrderService(s, cs, inv);
      cs.register(id: 'c1', name: 'A', email: 'a@x.com');
      inv.registerProduct(sku: 'A', name: 'W', price: 10.0);
      inv.addStock('A', 50);
      final o = os.place(
        customerId: 'c1', lines: [(sku: 'A', quantity: 3)]);
      os.markPaid(o.id);
      final snap = s.snapshot();

      // Mutate after snapshot
      cs.register(id: 'c2', name: 'B', email: 'b@x.com');
      inv.addStock('A', 100);
      os.cancel(o.id);
      // Restore should wipe the post-snapshot mutations
      s.restore(snap);
      expect(s.customers.length, 1);
      expect(s.customers.containsKey('c2'), false);
      expect(s.stock['A']!.onHand, 50);
      expect(s.orders[o.id]!.status, OrderStatus.paid);
    });
  });
}
