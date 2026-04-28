// types/customers.hpp — Customer + Address value types.
#pragma once

#include <string>
#include <vector>
#include "../errors.hpp"

struct Address {
    std::string street;
    std::string city;
    std::string postal_code;

    bool operator==(const Address& other) const {
        return street == other.street && city == other.city
            && postal_code == other.postal_code;
    }
};

struct Customer {
    std::string id;
    std::string name;
    std::string email;
    std::vector<Address> addresses;

    Customer(std::string id_, std::string name_, std::string email_)
        : id(std::move(id_)), name(std::move(name_)), email(std::move(email_)) {
        if (id.empty())
            throw ValidationError("customer id must be non-empty");
        if (name.empty())
            throw ValidationError("customer name must be non-empty");
        if (email.find('@') == std::string::npos)
            throw ValidationError("customer email must contain @");
    }
};
