// persistence.hpp — In-memory store + Snapshot (declarations).
//
// Implementations live in src/persistence.cpp.
// Snapshot DEEP-COPIES mutable state (StockLevel, Order, ReservationToken)
// so post-snapshot mutations don't bleed through restore().
#pragma once

#include <map>
#include <string>
#include "types/customers.hpp"
#include "types/inventory.hpp"
#include "types/orders.hpp"
#include "types/products.hpp"

struct Snapshot {
    std::map<std::string, Customer> customers;
    std::map<std::string, Product> products;
    std::map<std::string, StockLevel> stock;
    std::map<std::string, Order> orders;
    std::map<std::string, ReservationToken> reservations;
};

struct Store {
    std::map<std::string, Customer> customers;
    std::map<std::string, Product> products;
    std::map<std::string, StockLevel> stock;
    std::map<std::string, Order> orders;
    std::map<std::string, ReservationToken> reservations;

    Snapshot snapshot() const;
    void restore(const Snapshot& s);
};
