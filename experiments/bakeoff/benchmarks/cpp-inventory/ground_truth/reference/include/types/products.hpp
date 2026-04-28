// types/products.hpp — Product catalog entry.
//
// Immutable in spirit (no mutators); `sku` unique; `price` must be > 0.
#pragma once

#include <string>
#include "../errors.hpp"

struct Product {
    std::string sku;
    std::string name;
    double price;

    Product(std::string sku_, std::string name_, double price_)
        : sku(std::move(sku_)), name(std::move(name_)), price(price_) {
        if (sku.empty())
            throw ValidationError("product sku must be non-empty");
        if (name.empty())
            throw ValidationError("product name must be non-empty");
        if (price <= 0)
            throw ValidationError("product price must be > 0");
    }
};
