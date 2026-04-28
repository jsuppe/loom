// services/order_service.hpp — Order placement + lifecycle.
#pragma once

#include <chrono>
#include <iomanip>
#include <sstream>
#include "../errors.hpp"
#include "../persistence.hpp"
#include "../types/orders.hpp"
#include "customer_service.hpp"
#include "inventory_service.hpp"

struct OrderLine {
    std::string sku;
    int quantity;
};

class OrderService {
public:
    OrderService(Store& store, CustomerService& customers,
                  InventoryService& inventory)
        : store_(store), customers_(customers), inventory_(inventory) {}

    Order& place(const std::string& customer_id,
                  const std::vector<OrderLine>& lines) {
        customers_.get(customer_id);
        if (lines.empty())
            throw ValidationError("order must have at least one line");
        for (const auto& l : lines) inventory_.get_product(l.sku);

        std::ostringstream oss;
        oss << "ord-" << std::setw(6) << std::setfill('0') << ++order_seq_;
        std::string order_id = oss.str();
        std::vector<std::string> reserved_tokens;
        std::vector<Item> items;
        try {
            for (const auto& l : lines) {
                auto& p = inventory_.get_product(l.sku);
                auto& tok = inventory_.reserve(order_id, l.sku, l.quantity);
                reserved_tokens.push_back(tok.token_id);
                items.emplace_back(l.sku, l.quantity, p.price);
            }
        } catch (...) {
            for (const auto& tid : reserved_tokens) inventory_.release(tid);
            throw;
        }

        auto [it, _] = store_.orders.emplace(
            order_id, Order(order_id, customer_id, std::move(items)));
        auto& order = it->second;
        order.reservation_tokens = reserved_tokens;
        order.history.push_back(Transition{
            std::nullopt, OrderStatus::New, std::chrono::system_clock::now()
        });
        return order;
    }

    Order& get(const std::string& order_id) {
        auto it = store_.orders.find(order_id);
        if (it == store_.orders.end())
            throw NotFoundError("order not found: " + order_id);
        return it->second;
    }

    void mark_paid(const std::string& order_id) {
        auto& o = get(order_id);
        if (o.status != OrderStatus::New)
            throw InvalidTransitionError("cannot mark paid from current status");
        transition_(o, OrderStatus::Paid);
    }

    void ship(const std::string& order_id) {
        auto& o = get(order_id);
        if (o.status != OrderStatus::Paid)
            throw InvalidTransitionError("cannot ship from current status");
        for (const auto& tid : o.reservation_tokens) inventory_.commit(tid);
        transition_(o, OrderStatus::Shipped);
    }

    void deliver(const std::string& order_id) {
        auto& o = get(order_id);
        if (o.status != OrderStatus::Shipped)
            throw InvalidTransitionError("cannot deliver from current status");
        transition_(o, OrderStatus::Delivered);
    }

    void cancel(const std::string& order_id) {
        auto& o = get(order_id);
        if (o.status == OrderStatus::Shipped
            || o.status == OrderStatus::Delivered
            || o.status == OrderStatus::Cancelled)
            throw InvalidTransitionError("cannot cancel from current status");
        for (const auto& tid : o.reservation_tokens) {
            auto it = store_.reservations.find(tid);
            if (it != store_.reservations.end() && it->second.is_open())
                inventory_.release(tid);
        }
        transition_(o, OrderStatus::Cancelled);
    }

private:
    void transition_(Order& o, OrderStatus next) {
        o.history.push_back(Transition{
            o.status, next, std::chrono::system_clock::now()
        });
        o.status = next;
    }

    Store& store_;
    CustomerService& customers_;
    InventoryService& inventory_;
    int order_seq_ = 0;
};
