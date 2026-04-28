// services/customer_service.hpp — Customer registration + lookup + address mgmt.
#pragma once

#include "../errors.hpp"
#include "../persistence.hpp"
#include "../types/customers.hpp"

class CustomerService {
public:
    explicit CustomerService(Store& store) : store_(store) {}

    Customer& register_customer(const std::string& id,
                                 const std::string& name,
                                 const std::string& email) {
        if (store_.customers.find(id) != store_.customers.end())
            throw ConflictError("customer with id " + id + " already exists");
        auto [it, _] = store_.customers.emplace(id, Customer(id, name, email));
        return it->second;
    }

    Customer& get(const std::string& id) {
        auto it = store_.customers.find(id);
        if (it == store_.customers.end())
            throw NotFoundError("customer not found: " + id);
        return it->second;
    }

    Customer& add_address(const std::string& id, const Address& address) {
        auto& c = get(id);
        c.addresses.push_back(address);
        return c;
    }

private:
    Store& store_;
};
