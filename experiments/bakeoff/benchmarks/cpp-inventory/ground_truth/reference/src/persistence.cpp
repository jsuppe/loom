// persistence.cpp — Store + Snapshot definitions.

#include "../include/persistence.hpp"

Snapshot Store::snapshot() const {
    Snapshot s;
    s.customers = customers;
    s.products = products;
    s.stock = stock;
    s.orders = orders;
    s.reservations = reservations;
    return s;
}

void Store::restore(const Snapshot& s) {
    customers = s.customers;
    products = s.products;
    stock = s.stock;
    orders = s.orders;
    reservations = s.reservations;
}
