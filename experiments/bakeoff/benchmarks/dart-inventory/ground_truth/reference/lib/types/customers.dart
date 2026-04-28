/// types/customers.dart — Customer + Address value types.
///
/// `id`, `name`, and `email` are required. `email` must contain '@'.
/// `addresses` is mutable so customer_service can append.

import '../errors.dart';

class Address {
  final String street;
  final String city;
  final String postalCode;
  const Address({
    required this.street,
    required this.city,
    required this.postalCode,
  });

  @override
  bool operator ==(Object other) =>
      other is Address &&
      other.street == street &&
      other.city == city &&
      other.postalCode == postalCode;

  @override
  int get hashCode => Object.hash(street, city, postalCode);
}

class Customer {
  final String id;
  final String name;
  final String email;
  final List<Address> addresses;

  Customer({
    required this.id,
    required this.name,
    required this.email,
    List<Address>? addresses,
  }) : addresses = addresses ?? <Address>[] {
    if (id.isEmpty) {
      throw ValidationError('customer id must be non-empty');
    }
    if (name.isEmpty) {
      throw ValidationError('customer name must be non-empty');
    }
    if (!email.contains('@')) {
      throw ValidationError('customer email must contain @');
    }
  }
}
