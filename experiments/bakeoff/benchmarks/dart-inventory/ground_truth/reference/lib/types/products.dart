/// types/products.dart — Product catalog entry.
///
/// Immutable. `sku` is the unique product identifier; `price` must be > 0.

import '../errors.dart';

class Product {
  final String sku;
  final String name;
  final double price;

  Product({required this.sku, required this.name, required this.price}) {
    if (sku.isEmpty) {
      throw ValidationError('product sku must be non-empty');
    }
    if (name.isEmpty) {
      throw ValidationError('product name must be non-empty');
    }
    if (price <= 0) {
      throw ValidationError('product price must be > 0');
    }
  }
}
