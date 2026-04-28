// shop_test.cpp — hidden test suite for the cpp-inventory benchmark.
// Never shown to the planning or executor agents.

#include "shop.hpp"
#include <cmath>
#include <iostream>
#include <stdexcept>
#include <string>

// ---------- minimal harness ----------

static int g_pass = 0;
static int g_fail = 0;

#define EXPECT(cond) do { \
    if (!(cond)) throw std::runtime_error( \
        "EXPECT(" #cond ") failed at line " + std::to_string(__LINE__)); \
} while (0)

#define EXPECT_EQ(a, b) do { \
    auto _av = (a); auto _bv = (b); \
    if (!(_av == _bv)) throw std::runtime_error( \
        "EXPECT_EQ failed at line " + std::to_string(__LINE__)); \
} while (0)

#define EXPECT_THROWS(expr, ex_type) do { \
    bool _t = false; \
    try { expr; } catch (const ex_type&) { _t = true; } \
    catch (...) { throw std::runtime_error( \
        "EXPECT_THROWS got wrong type at line " + std::to_string(__LINE__)); } \
    if (!_t) throw std::runtime_error( \
        "EXPECT_THROWS got nothing at line " + std::to_string(__LINE__)); \
} while (0)

#define RUN(fn) do { \
    try { fn(); ++g_pass; } \
    catch (const std::exception& e) { \
        ++g_fail; \
        std::cerr << "FAIL " #fn ": " << e.what() << '\n'; \
    } \
} while (0)

// ============================================================
// Customers
// ============================================================

void t_customers_register_and_lookup() {
    Store s;
    CustomerService svc(s);
    auto& c = svc.register_customer("c1", "Alice", "a@x.com");
    EXPECT(c.id == "c1");
    EXPECT(svc.get("c1").name == "Alice");
}

void t_customers_register_duplicate_raises_conflict() {
    Store s; CustomerService svc(s);
    svc.register_customer("c1", "Alice", "a@x.com");
    EXPECT_THROWS(svc.register_customer("c1", "Alice2", "b@x.com"), ConflictError);
}

void t_customers_register_bad_email_raises_validation() {
    Store s; CustomerService svc(s);
    EXPECT_THROWS(svc.register_customer("c1", "Alice", "no-at-sign"), ValidationError);
}

void t_customers_get_unknown_raises_notfound() {
    Store s; CustomerService svc(s);
    EXPECT_THROWS(svc.get("nope"), NotFoundError);
}

void t_customers_add_address_appends() {
    Store s; CustomerService svc(s);
    svc.register_customer("c1", "A", "a@x.com");
    svc.add_address("c1", Address{"1 Main", "Town", "00001"});
    svc.add_address("c1", Address{"2 Side", "Town", "00002"});
    EXPECT_EQ(svc.get("c1").addresses.size(), size_t(2));
}

// ============================================================
// Inventory
// ============================================================

void t_inv_register_product_and_lookup() {
    Store s; InventoryService svc(s);
    svc.register_product("A", "Widget", 9.99);
    EXPECT(svc.get_product("A").name == "Widget");
}

void t_inv_duplicate_sku_raises_conflict() {
    Store s; InventoryService svc(s);
    svc.register_product("A", "Widget", 9.99);
    EXPECT_THROWS(svc.register_product("A", "Other", 1.00), ConflictError);
}

void t_inv_non_positive_price_raises_validation() {
    Store s; InventoryService svc(s);
    EXPECT_THROWS(svc.register_product("A", "Widget", 0), ValidationError);
}

void t_inv_add_stock_reserve_commit() {
    Store s; InventoryService svc(s);
    svc.register_product("A", "W", 1.0);
    svc.add_stock("A", 10);
    EXPECT_EQ(svc.stock_of("A").available(), 10);
    auto& t = svc.reserve("o1", "A", 3);
    EXPECT_EQ(svc.stock_of("A").reserved, 3);
    EXPECT_EQ(svc.stock_of("A").available(), 7);
    svc.commit(t.token_id);
    EXPECT_EQ(svc.stock_of("A").on_hand, 7);
    EXPECT_EQ(svc.stock_of("A").reserved, 0);
    EXPECT_EQ(svc.stock_of("A").available(), 7);
}

void t_inv_release_returns_stock() {
    Store s; InventoryService svc(s);
    svc.register_product("A", "W", 1.0);
    svc.add_stock("A", 10);
    auto& t = svc.reserve("o1", "A", 4);
    svc.release(t.token_id);
    EXPECT_EQ(svc.stock_of("A").reserved, 0);
    EXPECT_EQ(svc.stock_of("A").available(), 10);
    EXPECT_EQ(svc.stock_of("A").on_hand, 10);
}

void t_inv_reserve_insufficient_raises() {
    Store s; InventoryService svc(s);
    svc.register_product("A", "W", 1.0);
    svc.add_stock("A", 2);
    EXPECT_THROWS(svc.reserve("o1", "A", 5), InsufficientStockError);
}

void t_inv_commit_twice_raises() {
    Store s; InventoryService svc(s);
    svc.register_product("A", "W", 1.0);
    svc.add_stock("A", 10);
    auto& t = svc.reserve("o1", "A", 2);
    svc.commit(t.token_id);
    EXPECT_THROWS(svc.commit(t.token_id), ReservationError);
}

void t_inv_release_after_commit_raises() {
    Store s; InventoryService svc(s);
    svc.register_product("A", "W", 1.0);
    svc.add_stock("A", 10);
    auto& t = svc.reserve("o1", "A", 2);
    svc.commit(t.token_id);
    EXPECT_THROWS(svc.release(t.token_id), ReservationError);
}

void t_inv_add_stock_non_positive_raises() {
    Store s; InventoryService svc(s);
    svc.register_product("A", "W", 1.0);
    EXPECT_THROWS(svc.add_stock("A", 0), ValidationError);
}

// ============================================================
// Orders
// ============================================================

struct Setup {
    Store store;
    CustomerService customers;
    InventoryService inventory;
    OrderService orders;
    Setup()
        : customers(store), inventory(store),
          orders(store, customers, inventory) {
        customers.register_customer("c1", "A", "a@x.com");
        inventory.register_product("A", "W", 10.0);
        inventory.register_product("B", "G", 3.5);
        inventory.add_stock("A", 100);
        inventory.add_stock("B", 100);
    }
};

void t_orders_place_lifecycle_to_delivered() {
    Setup ctx;
    auto& o = ctx.orders.place("c1", {{"A", 2}, {"B", 4}});
    EXPECT(o.status == OrderStatus::New);
    EXPECT(std::abs(o.total() - (10.0*2 + 3.5*4)) < 1e-9);
    EXPECT_EQ(ctx.inventory.stock_of("A").reserved, 2);
    EXPECT_EQ(ctx.inventory.stock_of("B").reserved, 4);

    ctx.orders.mark_paid(o.id);
    ctx.orders.ship(o.id);
    EXPECT_EQ(ctx.inventory.stock_of("A").on_hand, 98);
    EXPECT_EQ(ctx.inventory.stock_of("A").reserved, 0);
    ctx.orders.deliver(o.id);
    EXPECT(ctx.orders.get(o.id).status == OrderStatus::Delivered);
}

void t_orders_place_unknown_customer_raises() {
    Setup ctx;
    EXPECT_THROWS(ctx.orders.place("ghost", {{"A", 1}}), NotFoundError);
}

void t_orders_place_unknown_sku_raises() {
    Setup ctx;
    EXPECT_THROWS(ctx.orders.place("c1", {{"Z", 1}}), NotFoundError);
}

void t_orders_place_empty_lines_raises() {
    Setup ctx;
    EXPECT_THROWS(ctx.orders.place("c1", {}), ValidationError);
}

void t_orders_place_insufficient_releases_priors() {
    Setup ctx;
    EXPECT_THROWS(
        ctx.orders.place("c1", {{"A", 5}, {"B", 200}}),
        InsufficientStockError);
    EXPECT_EQ(ctx.inventory.stock_of("A").reserved, 0);
    EXPECT_EQ(ctx.inventory.stock_of("B").reserved, 0);
}

void t_orders_mark_paid_twice_raises() {
    Setup ctx;
    auto& o = ctx.orders.place("c1", {{"A", 1}});
    ctx.orders.mark_paid(o.id);
    EXPECT_THROWS(ctx.orders.mark_paid(o.id), InvalidTransitionError);
}

void t_orders_ship_from_new_raises() {
    Setup ctx;
    auto& o = ctx.orders.place("c1", {{"A", 1}});
    EXPECT_THROWS(ctx.orders.ship(o.id), InvalidTransitionError);
}

void t_orders_cancel_from_new_releases_reservations() {
    Setup ctx;
    auto& o = ctx.orders.place("c1", {{"A", 3}});
    EXPECT_EQ(ctx.inventory.stock_of("A").reserved, 3);
    ctx.orders.cancel(o.id);
    EXPECT_EQ(ctx.inventory.stock_of("A").reserved, 0);
    EXPECT_EQ(ctx.inventory.stock_of("A").on_hand, 100);
    EXPECT(ctx.orders.get(o.id).status == OrderStatus::Cancelled);
}

void t_orders_cancel_from_paid_releases_reservations() {
    Setup ctx;
    auto& o = ctx.orders.place("c1", {{"A", 3}});
    ctx.orders.mark_paid(o.id);
    ctx.orders.cancel(o.id);
    EXPECT_EQ(ctx.inventory.stock_of("A").reserved, 0);
    EXPECT_EQ(ctx.inventory.stock_of("A").on_hand, 100);
}

void t_orders_cancel_from_shipped_raises() {
    Setup ctx;
    auto& o = ctx.orders.place("c1", {{"A", 1}});
    ctx.orders.mark_paid(o.id);
    ctx.orders.ship(o.id);
    EXPECT_THROWS(ctx.orders.cancel(o.id), InvalidTransitionError);
}

void t_orders_history_records_every_transition() {
    Setup ctx;
    auto& o = ctx.orders.place("c1", {{"A", 1}});
    ctx.orders.mark_paid(o.id);
    ctx.orders.ship(o.id);
    ctx.orders.deliver(o.id);
    auto& h = ctx.orders.get(o.id).history;
    EXPECT_EQ(h.size(), size_t(4));
    EXPECT(!h[0].from_status.has_value());
    EXPECT(h[0].to_status == OrderStatus::New);
    EXPECT(h[1].to_status == OrderStatus::Paid);
    EXPECT(h[2].to_status == OrderStatus::Shipped);
    EXPECT(h[3].to_status == OrderStatus::Delivered);
}

void t_orders_item_snapshots_unit_price() {
    Setup ctx;
    auto& o = ctx.orders.place("c1", {{"A", 2}});
    EXPECT(std::abs(o.items[0].unit_price - 10.0) < 1e-9);
    EXPECT(std::abs(o.total() - 20.0) < 1e-9);
    EXPECT(std::abs(ctx.inventory.get_product("A").price - 10.0) < 1e-9);
}

void t_orders_total_uses_line_total_aggregation() {
    Setup ctx;
    auto& o = ctx.orders.place("c1", {{"A", 3}, {"B", 7}});
    EXPECT(std::abs(o.total() - (3 * 10.0 + 7 * 3.5)) < 1e-9);
}

// ============================================================
// Persistence
// ============================================================

void t_persistence_snapshot_restore() {
    Store s;
    CustomerService cs(s);
    InventoryService inv(s);
    OrderService os_(s, cs, inv);
    cs.register_customer("c1", "A", "a@x.com");
    inv.register_product("A", "W", 10.0);
    inv.add_stock("A", 50);
    auto& o = os_.place("c1", {{"A", 3}});
    std::string oid = o.id;
    os_.mark_paid(oid);
    auto snap = s.snapshot();

    // Mutate after snapshot
    cs.register_customer("c2", "B", "b@x.com");
    inv.add_stock("A", 100);
    os_.cancel(oid);
    // Restore should wipe the post-snapshot mutations
    s.restore(snap);
    EXPECT_EQ(s.customers.size(), size_t(1));
    EXPECT(s.customers.find("c2") == s.customers.end());
    EXPECT_EQ(s.stock.find("A")->second.on_hand, 50);
    EXPECT(s.orders.find(oid)->second.status == OrderStatus::Paid);
}

// ============================================================

int main() {
    RUN(t_customers_register_and_lookup);
    RUN(t_customers_register_duplicate_raises_conflict);
    RUN(t_customers_register_bad_email_raises_validation);
    RUN(t_customers_get_unknown_raises_notfound);
    RUN(t_customers_add_address_appends);

    RUN(t_inv_register_product_and_lookup);
    RUN(t_inv_duplicate_sku_raises_conflict);
    RUN(t_inv_non_positive_price_raises_validation);
    RUN(t_inv_add_stock_reserve_commit);
    RUN(t_inv_release_returns_stock);
    RUN(t_inv_reserve_insufficient_raises);
    RUN(t_inv_commit_twice_raises);
    RUN(t_inv_release_after_commit_raises);
    RUN(t_inv_add_stock_non_positive_raises);

    RUN(t_orders_place_lifecycle_to_delivered);
    RUN(t_orders_place_unknown_customer_raises);
    RUN(t_orders_place_unknown_sku_raises);
    RUN(t_orders_place_empty_lines_raises);
    RUN(t_orders_place_insufficient_releases_priors);
    RUN(t_orders_mark_paid_twice_raises);
    RUN(t_orders_ship_from_new_raises);
    RUN(t_orders_cancel_from_new_releases_reservations);
    RUN(t_orders_cancel_from_paid_releases_reservations);
    RUN(t_orders_cancel_from_shipped_raises);
    RUN(t_orders_history_records_every_transition);
    RUN(t_orders_item_snapshots_unit_price);
    RUN(t_orders_total_uses_line_total_aggregation);

    RUN(t_persistence_snapshot_restore);

    std::cout << g_pass << " passed, " << g_fail << " failed\n";
    return g_fail == 0 ? 0 : 1;
}
