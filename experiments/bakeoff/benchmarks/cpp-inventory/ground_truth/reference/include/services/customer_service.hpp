// services/customer_service.hpp — declarations.
//
// Implementations live in src/services/customer_service.cpp.
#pragma once

#include "../errors.hpp"
#include "../persistence.hpp"
#include "../types/customers.hpp"

class CustomerService {
public:
    explicit CustomerService(Store& store);

    Customer& register_customer(const std::string& id,
                                 const std::string& name,
                                 const std::string& email);

    Customer& get(const std::string& id);

    Customer& add_address(const std::string& id, const Address& address);

private:
    Store& store_;
};
