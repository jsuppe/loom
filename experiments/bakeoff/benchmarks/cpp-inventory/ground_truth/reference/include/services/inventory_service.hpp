// services/inventory_service.hpp — Product catalog + stock + reservations.
#pragma once

#include <iomanip>
#include <sstream>
#include "../errors.hpp"
#include "../persistence.hpp"
#include "../types/inventory.hpp"
#include "../types/products.hpp"

class InventoryService {
public:
    explicit InventoryService(Store& store) : store_(store) {}

    Product& register_product(const std::string& sku, const std::string& name,
                               double price) {
        if (store_.products.find(sku) != store_.products.end())
            throw ConflictError("product with sku " + sku + " already exists");
        auto [it_p, _p] = store_.products.emplace(sku, Product(sku, name, price));
        store_.stock.emplace(sku, StockLevel(sku));
        return it_p->second;
    }

    Product& get_product(const std::string& sku) {
        auto it = store_.products.find(sku);
        if (it == store_.products.end())
            throw NotFoundError("product not found: " + sku);
        return it->second;
    }

    StockLevel& stock_of(const std::string& sku) {
        auto it = store_.stock.find(sku);
        if (it == store_.stock.end())
            throw NotFoundError("no stock record for sku " + sku);
        return it->second;
    }

    void add_stock(const std::string& sku, int qty) {
        if (qty <= 0)
            throw ValidationError("add_stock qty must be > 0");
        stock_of(sku).on_hand += qty;
    }

    ReservationToken& reserve(const std::string& order_id,
                               const std::string& sku, int quantity) {
        if (quantity <= 0)
            throw ValidationError("reserve quantity must be > 0");
        auto& s = stock_of(sku);
        if (s.available() < quantity)
            throw InsufficientStockError(
                "insufficient stock for " + sku + ": have "
                + std::to_string(s.available())
                + ", need " + std::to_string(quantity));
        s.reserved += quantity;
        std::ostringstream oss;
        oss << "rsv-" << std::setw(6) << std::setfill('0') << ++token_seq_;
        std::string token_id = oss.str();
        auto [it, _] = store_.reservations.emplace(
            token_id,
            ReservationToken(token_id, order_id, sku, quantity));
        return it->second;
    }

    void commit(const std::string& token_id) {
        auto it = store_.reservations.find(token_id);
        if (it == store_.reservations.end())
            throw NotFoundError("reservation not found: " + token_id);
        auto& t = it->second;
        if (!t.is_open())
            throw ReservationError("reservation " + token_id + " already closed");
        auto& s = stock_of(t.sku);
        s.on_hand -= t.quantity;
        s.reserved -= t.quantity;
        t.committed = true;
    }

    void release(const std::string& token_id) {
        auto it = store_.reservations.find(token_id);
        if (it == store_.reservations.end())
            throw NotFoundError("reservation not found: " + token_id);
        auto& t = it->second;
        if (!t.is_open())
            throw ReservationError("reservation " + token_id + " already closed");
        auto& s = stock_of(t.sku);
        s.reserved -= t.quantity;
        t.released = true;
    }

private:
    Store& store_;
    int token_seq_ = 0;
};
