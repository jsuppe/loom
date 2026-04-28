# cpp-inventory benchmark (v2: split `.hpp/.cpp` convention)

Multi-file C++ benchmark — three coordinating services (customers,
inventory, orders) over an in-memory persistence store with snapshot /
restore. Direct port of `dart-inventory` and `python-inventory` to
modern C++ idioms (`std::map`, `std::optional`, exception hierarchy
via `using`-inheritance, `.hpp/.cpp` separation for non-trivial
classes).

v2 changed the convention from header-only (v1: 2/5 = 40% ceiling
because qwen reverted to `.hpp/.cpp` despite the spec) to native
`.hpp/.cpp` separation. Small value types stay header-only; services
+ persistence split.

## Public API

The library is exported from `include/shop.hpp` (a barrel — pre-written
by the harness).

```cpp
#include "shop.hpp"

Store store;
CustomerService customers(store);
InventoryService inventory(store);
OrderService orders(store, customers, inventory);

customers.register_customer("c1", "Alice", "alice@example.com");
inventory.register_product("A", "Widget", 9.99);
inventory.add_stock("A", 100);

auto& order = orders.place("c1", {{"A", 3}});
orders.mark_paid(order.id);
orders.ship(order.id);     // commits reservations, decrements on_hand
orders.deliver(order.id);
```

## Files (13 executor tasks)

```
include/                                     (declarations)
├── shop.hpp                                 (barrel — pre-written)
├── errors.hpp                               [task  1] header-only
├── types/
│   ├── customers.hpp                        [task  2] header-only
│   ├── products.hpp                         [task  3] header-only
│   ├── inventory.hpp                        [task  4] header-only
│   └── orders.hpp                           [task  5] header-only
├── persistence.hpp                          [task  6]
└── services/
    ├── customer_service.hpp                 [task  8]
    ├── inventory_service.hpp                [task 10]
    └── order_service.hpp                    [task 12]

src/                                         (definitions)
├── persistence.cpp                          [task  7]
└── services/
    ├── customer_service.cpp                 [task  9]
    ├── inventory_service.cpp                [task 11]
    └── order_service.cpp                    [task 13]
```

Tasks run in topological order. Each task's executor sees the spec
section labeled `### include/<path>.hpp`.

## Domain model (REQ-1 through REQ-6)

### REQ-1: Error hierarchy (`errors.hpp`)

All domain errors derive from `class DomainError : public std::runtime_error`.
Subclass names are exact — tests assert on type:

- `ValidationError`
- `NotFoundError`
- `ConflictError`
- `InsufficientStockError`
- `InvalidTransitionError`
- `ReservationError`

Each subclass uses `using DomainError::DomainError;` to inherit constructors;
no extra fields, no override.

### REQ-2: Customer types + service

`Address` is a plain `struct` with `std::string street`, `city`,
`postal_code`. Equality operator over the three fields.

`Customer` is a `struct` with `std::string id, name, email`,
`std::vector<Address> addresses`. Constructor takes id, name, email
(by-value + std::move); validates: id non-empty, name non-empty, email
contains `'@'` (uses `std::string::find('@') == std::string::npos`).

`CustomerService` holds `Store& store_`. Public methods:
`register_customer(id, name, email)`, `get(id)`, `add_address(id, address)`.
Returns `Customer&` references. Duplicate id raises `ConflictError`;
unknown id raises `NotFoundError`.

### REQ-3: Product type + stock types

`Product` is a `struct` with `std::string sku, name`, `double price`.
Validates in constructor: non-empty sku/name, price > 0.

`StockLevel` is a `struct` with `std::string sku`, `int on_hand = 0`,
`int reserved = 0`. Method `int available() const { return on_hand - reserved; }`.
Constructor takes `std::string sku_` only (other fields default).

`ReservationToken` is a `struct` with `token_id, order_id, sku, quantity`,
plus mutable `bool committed = false, released = false`. Method
`bool is_open() const { return !committed && !released; }`.

### REQ-4: Inventory service

`InventoryService` holds `Store& store_` and `int token_seq_ = 0`. Methods:

- `register_product(sku, name, price) -> Product&` — emplaces into
  `store_.products` AND creates an empty `StockLevel(sku)` in
  `store_.stock`.
- `get_product(sku) -> Product&` / `stock_of(sku) -> StockLevel&`.
- `add_stock(sku, qty)` — qty > 0 required.
- `reserve(order_id, sku, quantity) -> ReservationToken&` — increments
  `StockLevel.reserved`. `InsufficientStockError` if not enough available.
  Token IDs are formatted via `std::ostringstream` + `std::setw(6)` +
  `std::setfill('0')` → `rsv-NNNNNN`.
- `commit(token_id)` — closes token, decrements `on_hand` AND `reserved`.
  `ReservationError` on already-closed token.
- `release(token_id)` — closes token, decrements `reserved`.
  `ReservationError` on already-closed token.

### REQ-5: Order types + service

`OrderStatus` is `enum class` with values `New, Paid, Shipped, Delivered, Cancelled`.

`Item` struct with `sku, quantity, unit_price`. Validates in constructor:
quantity > 0, unit_price >= 0. `double line_total() const`.

`Transition` struct with `std::optional<OrderStatus> from_status`
(nullable for the initial creation record), `OrderStatus to_status`,
`std::chrono::system_clock::time_point timestamp`.

`Order` struct with `std::string id, customer_id`, `std::vector<Item> items`,
mutable `OrderStatus status = OrderStatus::New`, `std::vector<Transition> history`,
`std::vector<std::string> reservation_tokens`. Constructor takes id, customer_id,
items (by-value + move); validates id, customer_id, non-empty items.
`double total() const` aggregates `line_total()` over items.

`OrderLine` is a small helper struct with `sku, quantity` for `place(...)`
input.

`OrderService` holds `Store&`, `CustomerService&`, `InventoryService&`,
plus `int order_seq_ = 0`. Public methods:

- `place(customer_id, std::vector<OrderLine>) -> Order&` — validates
  customer + each sku exists, then reserves stock for each line. On
  failure mid-loop, releases all already-made reservations from this
  call and rethrows. On success: emplaces Order into `store_.orders`,
  appends initial `Transition{nullopt, New, now()}` to history.
- `get(order_id) -> Order&`.
- `mark_paid(order_id)` — New → Paid.
- `ship(order_id)` — Paid → Shipped. Commits all reservation tokens
  before transitioning.
- `deliver(order_id)` — Shipped → Delivered.
- `cancel(order_id)` — New OR Paid → Cancelled. Releases all open
  reservation tokens. From Shipped/Delivered/Cancelled raises.

### REQ-6: Persistence (`persistence.hpp`)

`Snapshot` is a struct holding five `std::map<std::string, T>` members
(customers, products, stock, orders, reservations).
`Store` is the same shape. `snapshot() const -> Snapshot` value-copies
all maps (since the value types are owned, value-copy is a deep copy).
`restore(const Snapshot&)` assigns each map from the snapshot.

## Grading

```
g++ -std=c++20 -I include \
  src/persistence.cpp \
  src/services/customer_service.cpp \
  src/services/inventory_service.cpp \
  src/services/order_service.cpp \
  test/shop_test.cpp \
  -o test_runner.exe
./test_runner.exe
```

Reports `N passed, M failed`. Reference: 28/28 pass.

## Why this benchmark

This is the C++ sibling of `dart-inventory` and `python-inventory`. We
use it to disambiguate two hypotheses about the dart-inventory
complexity ceiling:

- **H1 (Dart-specific):** qwen3.5 has Dart blind spots — named-args
  syntax, `const` constructors, records — that don't exist in C++ or
  Python. Under H1: cpp-inventory should pass at non-zero rate.
- **H2 (Complexity-specific):** qwen3.5 hits a coordination ceiling
  at 8+ files / 700+ LOC regardless of language. Under H2:
  cpp-inventory should fail like dart-inventory.

Same domain semantics, same test count (28), same task count (8) —
only the executor's language changes. Result is paper-relevant
either way.
