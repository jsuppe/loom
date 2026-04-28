// services/order_service.hpp — declarations.
//
// Implementations live in src/services/order_service.cpp.
#pragma once

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
                  InventoryService& inventory);

    Order& place(const std::string& customer_id,
                  const std::vector<OrderLine>& lines);
    Order& get(const std::string& order_id);
    void mark_paid(const std::string& order_id);
    void ship(const std::string& order_id);
    void deliver(const std::string& order_id);
    void cancel(const std::string& order_id);

private:
    void transition_(Order& o, OrderStatus next);

    Store& store_;
    CustomerService& customers_;
    InventoryService& inventory_;
    int order_seq_ = 0;
};
