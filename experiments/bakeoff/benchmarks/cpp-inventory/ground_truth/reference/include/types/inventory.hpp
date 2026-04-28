// types/inventory.hpp — Stock level + reservation token.
#pragma once

#include <string>

struct StockLevel {
    std::string sku;
    int on_hand = 0;
    int reserved = 0;

    explicit StockLevel(std::string sku_) : sku(std::move(sku_)) {}

    int available() const { return on_hand - reserved; }
};

struct ReservationToken {
    std::string token_id;
    std::string order_id;
    std::string sku;
    int quantity;
    bool committed = false;
    bool released = false;

    ReservationToken(std::string token_id_, std::string order_id_,
                      std::string sku_, int quantity_)
        : token_id(std::move(token_id_)),
          order_id(std::move(order_id_)),
          sku(std::move(sku_)),
          quantity(quantity_) {}

    bool is_open() const { return !committed && !released; }
};
