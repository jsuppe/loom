// types/orders.hpp — Order + Item types and OrderStatus enum.
//
// Item snapshots unit_price at order time so later product price changes
// don't retroactively affect totals. Order::total is computed from items.
// Order::history records every status change.
#pragma once

#include <chrono>
#include <optional>
#include <string>
#include <vector>
#include "../errors.hpp"

enum class OrderStatus {
    New,
    Paid,
    Shipped,
    Delivered,
    Cancelled,
};

struct Item {
    std::string sku;
    int quantity;
    double unit_price;

    Item(std::string sku_, int quantity_, double unit_price_)
        : sku(std::move(sku_)), quantity(quantity_), unit_price(unit_price_) {
        if (quantity <= 0)
            throw ValidationError("item quantity must be > 0");
        if (unit_price < 0)
            throw ValidationError("item unit_price must be >= 0");
    }

    double line_total() const { return quantity * unit_price; }
};

struct Transition {
    std::optional<OrderStatus> from_status;
    OrderStatus to_status;
    std::chrono::system_clock::time_point timestamp;
};

struct Order {
    std::string id;
    std::string customer_id;
    std::vector<Item> items;
    OrderStatus status = OrderStatus::New;
    std::vector<Transition> history;
    std::vector<std::string> reservation_tokens;

    Order(std::string id_, std::string customer_id_, std::vector<Item> items_)
        : id(std::move(id_)),
          customer_id(std::move(customer_id_)),
          items(std::move(items_)) {
        if (id.empty())
            throw ValidationError("order id must be non-empty");
        if (customer_id.empty())
            throw ValidationError("order customer_id must be non-empty");
        if (items.empty())
            throw ValidationError("order must have at least one item");
    }

    double total() const {
        double sum = 0.0;
        for (const auto& it : items) sum += it.line_total();
        return sum;
    }
};
