# test_shop.py — hidden test suite for the python-inventory benchmark.
# Never shown to the planning or executor agents.

import pytest

from shop import (
    Address,
    ConflictError,
    Customer,
    CustomerService,
    InsufficientStockError,
    InvalidTransitionError,
    InventoryService,
    Item,
    NotFoundError,
    Order,
    OrderService,
    OrderStatus,
    Product,
    ReservationError,
    ReservationToken,
    Snapshot,
    StockLevel,
    Store,
    Transition,
    ValidationError,
)


# ============================================================
# Customer service
# ============================================================


def test_customers_register_and_lookup():
    s = Store()
    svc = CustomerService(s)
    c = svc.register(id="c1", name="Alice", email="a@x.com")
    assert c.id == "c1"
    assert svc.get("c1").name == "Alice"


def test_customers_register_duplicate_raises_conflict():
    svc = CustomerService(Store())
    svc.register(id="c1", name="Alice", email="a@x.com")
    with pytest.raises(ConflictError):
        svc.register(id="c1", name="Alice2", email="b@x.com")


def test_customers_register_bad_email_raises_validation():
    svc = CustomerService(Store())
    with pytest.raises(ValidationError):
        svc.register(id="c1", name="Alice", email="no-at-sign")


def test_customers_get_unknown_raises_notfound():
    svc = CustomerService(Store())
    with pytest.raises(NotFoundError):
        svc.get("nope")


def test_customers_add_address_appends():
    svc = CustomerService(Store())
    svc.register(id="c1", name="A", email="a@x.com")
    svc.add_address("c1", Address(street="1 Main", city="Town", postal_code="00001"))
    svc.add_address("c1", Address(street="2 Side", city="Town", postal_code="00002"))
    assert len(svc.get("c1").addresses) == 2


# ============================================================
# Inventory service
# ============================================================


def test_inventory_register_product_and_lookup():
    svc = InventoryService(Store())
    svc.register_product(sku="A", name="Widget", price=9.99)
    assert svc.get_product("A").name == "Widget"


def test_inventory_duplicate_sku_raises_conflict():
    svc = InventoryService(Store())
    svc.register_product(sku="A", name="Widget", price=9.99)
    with pytest.raises(ConflictError):
        svc.register_product(sku="A", name="Other", price=1.00)


def test_inventory_non_positive_price_raises_validation():
    svc = InventoryService(Store())
    with pytest.raises(ValidationError):
        svc.register_product(sku="A", name="Widget", price=0)


def test_inventory_add_stock_reserve_commit():
    svc = InventoryService(Store())
    svc.register_product(sku="A", name="W", price=1.0)
    svc.add_stock("A", 10)
    assert svc.stock_of("A").available == 10
    t = svc.reserve(order_id="o1", sku="A", quantity=3)
    assert svc.stock_of("A").reserved == 3
    assert svc.stock_of("A").available == 7
    svc.commit(t.token_id)
    assert svc.stock_of("A").on_hand == 7
    assert svc.stock_of("A").reserved == 0
    assert svc.stock_of("A").available == 7


def test_inventory_release_returns_stock():
    svc = InventoryService(Store())
    svc.register_product(sku="A", name="W", price=1.0)
    svc.add_stock("A", 10)
    t = svc.reserve(order_id="o1", sku="A", quantity=4)
    svc.release(t.token_id)
    assert svc.stock_of("A").reserved == 0
    assert svc.stock_of("A").available == 10
    assert svc.stock_of("A").on_hand == 10


def test_inventory_reserve_insufficient_raises():
    svc = InventoryService(Store())
    svc.register_product(sku="A", name="W", price=1.0)
    svc.add_stock("A", 2)
    with pytest.raises(InsufficientStockError):
        svc.reserve(order_id="o1", sku="A", quantity=5)


def test_inventory_commit_twice_raises_reservation_error():
    svc = InventoryService(Store())
    svc.register_product(sku="A", name="W", price=1.0)
    svc.add_stock("A", 10)
    t = svc.reserve(order_id="o1", sku="A", quantity=2)
    svc.commit(t.token_id)
    with pytest.raises(ReservationError):
        svc.commit(t.token_id)


def test_inventory_release_after_commit_raises():
    svc = InventoryService(Store())
    svc.register_product(sku="A", name="W", price=1.0)
    svc.add_stock("A", 10)
    t = svc.reserve(order_id="o1", sku="A", quantity=2)
    svc.commit(t.token_id)
    with pytest.raises(ReservationError):
        svc.release(t.token_id)


def test_inventory_add_stock_non_positive_raises_validation():
    svc = InventoryService(Store())
    svc.register_product(sku="A", name="W", price=1.0)
    with pytest.raises(ValidationError):
        svc.add_stock("A", 0)


# ============================================================
# Order service
# ============================================================


@pytest.fixture
def setup():
    s = Store()
    cs = CustomerService(s)
    inv = InventoryService(s)
    os_ = OrderService(s, cs, inv)
    cs.register(id="c1", name="A", email="a@x.com")
    inv.register_product(sku="A", name="W", price=10.0)
    inv.register_product(sku="B", name="G", price=3.5)
    inv.add_stock("A", 100)
    inv.add_stock("B", 100)
    return {"store": s, "customers": cs, "inventory": inv, "orders": os_}


def test_orders_place_lifecycle_to_delivered(setup):
    os_ = setup["orders"]
    inv = setup["inventory"]
    o = os_.place(
        customer_id="c1",
        lines=[
            {"sku": "A", "quantity": 2},
            {"sku": "B", "quantity": 4},
        ],
    )
    assert o.status == OrderStatus.NEW
    assert o.total == 10.0 * 2 + 3.5 * 4
    assert inv.stock_of("A").reserved == 2
    assert inv.stock_of("B").reserved == 4

    os_.mark_paid(o.id)
    os_.ship(o.id)
    assert inv.stock_of("A").on_hand == 98
    assert inv.stock_of("A").reserved == 0
    os_.deliver(o.id)
    assert os_.get(o.id).status == OrderStatus.DELIVERED


def test_orders_place_unknown_customer_raises_notfound(setup):
    with pytest.raises(NotFoundError):
        setup["orders"].place(customer_id="ghost", lines=[{"sku": "A", "quantity": 1}])


def test_orders_place_unknown_sku_raises_notfound(setup):
    with pytest.raises(NotFoundError):
        setup["orders"].place(customer_id="c1", lines=[{"sku": "Z", "quantity": 1}])


def test_orders_place_empty_lines_raises_validation(setup):
    with pytest.raises(ValidationError):
        setup["orders"].place(customer_id="c1", lines=[])


def test_orders_place_insufficient_stock_releases_priors(setup):
    inv = setup["inventory"]
    os_ = setup["orders"]
    with pytest.raises(InsufficientStockError):
        os_.place(
            customer_id="c1",
            lines=[
                {"sku": "A", "quantity": 5},
                {"sku": "B", "quantity": 200},
            ],
        )
    assert inv.stock_of("A").reserved == 0
    assert inv.stock_of("B").reserved == 0


def test_orders_mark_paid_twice_raises_invalid_transition(setup):
    os_ = setup["orders"]
    o = os_.place(customer_id="c1", lines=[{"sku": "A", "quantity": 1}])
    os_.mark_paid(o.id)
    with pytest.raises(InvalidTransitionError):
        os_.mark_paid(o.id)


def test_orders_ship_from_new_raises_invalid_transition(setup):
    os_ = setup["orders"]
    o = os_.place(customer_id="c1", lines=[{"sku": "A", "quantity": 1}])
    with pytest.raises(InvalidTransitionError):
        os_.ship(o.id)


def test_orders_cancel_from_new_releases_reservations(setup):
    inv = setup["inventory"]
    os_ = setup["orders"]
    o = os_.place(customer_id="c1", lines=[{"sku": "A", "quantity": 3}])
    assert inv.stock_of("A").reserved == 3
    os_.cancel(o.id)
    assert inv.stock_of("A").reserved == 0
    assert inv.stock_of("A").on_hand == 100
    assert os_.get(o.id).status == OrderStatus.CANCELLED


def test_orders_cancel_from_paid_releases_reservations(setup):
    inv = setup["inventory"]
    os_ = setup["orders"]
    o = os_.place(customer_id="c1", lines=[{"sku": "A", "quantity": 3}])
    os_.mark_paid(o.id)
    os_.cancel(o.id)
    assert inv.stock_of("A").reserved == 0
    assert inv.stock_of("A").on_hand == 100


def test_orders_cancel_from_shipped_raises_invalid_transition(setup):
    os_ = setup["orders"]
    o = os_.place(customer_id="c1", lines=[{"sku": "A", "quantity": 1}])
    os_.mark_paid(o.id)
    os_.ship(o.id)
    with pytest.raises(InvalidTransitionError):
        os_.cancel(o.id)


def test_orders_history_records_every_transition(setup):
    os_ = setup["orders"]
    o = os_.place(customer_id="c1", lines=[{"sku": "A", "quantity": 1}])
    os_.mark_paid(o.id)
    os_.ship(o.id)
    os_.deliver(o.id)
    h = os_.get(o.id).history
    assert len(h) == 4
    assert h[0].from_status is None
    assert h[0].to_status == OrderStatus.NEW
    assert h[1].to_status == OrderStatus.PAID
    assert h[2].to_status == OrderStatus.SHIPPED
    assert h[3].to_status == OrderStatus.DELIVERED


def test_orders_item_snapshots_unit_price(setup):
    inv = setup["inventory"]
    os_ = setup["orders"]
    o = os_.place(customer_id="c1", lines=[{"sku": "A", "quantity": 2}])
    original_total = o.total
    assert o.items[0].unit_price == 10.0
    assert original_total == 20.0
    assert inv.get_product("A").price == 10.0


def test_orders_total_uses_line_total_aggregation(setup):
    os_ = setup["orders"]
    o = os_.place(
        customer_id="c1",
        lines=[
            {"sku": "A", "quantity": 3},
            {"sku": "B", "quantity": 7},
        ],
    )
    assert o.total == 3 * 10.0 + 7 * 3.5


# ============================================================
# Persistence: snapshot + restore round trip
# ============================================================


def test_persistence_snapshot_restore_round_trips_full_state():
    s = Store()
    cs = CustomerService(s)
    inv = InventoryService(s)
    os_ = OrderService(s, cs, inv)
    cs.register(id="c1", name="A", email="a@x.com")
    inv.register_product(sku="A", name="W", price=10.0)
    inv.add_stock("A", 50)
    o = os_.place(customer_id="c1", lines=[{"sku": "A", "quantity": 3}])
    os_.mark_paid(o.id)
    snap = s.snapshot()

    # Mutate after snapshot
    cs.register(id="c2", name="B", email="b@x.com")
    inv.add_stock("A", 100)
    os_.cancel(o.id)
    # Restore should wipe the post-snapshot mutations
    s.restore(snap)
    assert len(s.customers) == 1
    assert "c2" not in s.customers
    assert s.stock["A"].on_hand == 50
    assert s.orders[o.id].status == OrderStatus.PAID
