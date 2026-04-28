/// services/customer_service.dart — Customer registration + lookup + address mgmt.
///
/// Backed by `Store.customers`. All errors are domain errors from `errors.dart`.

import '../errors.dart';
import '../persistence.dart';
import '../types/customers.dart';

class CustomerService {
  final Store store;
  CustomerService(this.store);

  Customer register({
    required String id,
    required String name,
    required String email,
  }) {
    if (store.customers.containsKey(id)) {
      throw ConflictError('customer with id $id already exists');
    }
    final c = Customer(id: id, name: name, email: email);
    store.customers[id] = c;
    return c;
  }

  Customer get(String id) {
    final c = store.customers[id];
    if (c == null) {
      throw NotFoundError('customer not found: $id');
    }
    return c;
  }

  Customer addAddress(String id, Address addr) {
    final c = get(id);
    c.addresses.add(addr);
    return c;
  }
}
