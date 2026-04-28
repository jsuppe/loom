// services/inventory_service.hpp — declarations.
//
// Implementations live in src/services/inventory_service.cpp.
#pragma once

#include "../errors.hpp"
#include "../persistence.hpp"
#include "../types/inventory.hpp"
#include "../types/products.hpp"

class InventoryService {
public:
    explicit InventoryService(Store& store);

    Product& register_product(const std::string& sku, const std::string& name,
                               double price);
    Product& get_product(const std::string& sku);
    StockLevel& stock_of(const std::string& sku);
    void add_stock(const std::string& sku, int qty);
    ReservationToken& reserve(const std::string& order_id,
                               const std::string& sku, int quantity);
    void commit(const std::string& token_id);
    void release(const std::string& token_id);

private:
    Store& store_;
    int token_seq_ = 0;
};
