// persistence.hpp — In-memory store + Snapshot.
//
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

    Snapshot snapshot() const {
        Snapshot s;
        s.customers = customers;
        s.products = products;
        s.stock = stock;            // value-copy; StockLevel has trivial copy
        s.orders = orders;          // value-copy; Order has vector members
        s.reservations = reservations;
        return s;
    }

    void restore(const Snapshot& s) {
        customers = s.customers;
        products = s.products;
        stock = s.stock;
        orders = s.orders;
        reservations = s.reservations;
    }
};
