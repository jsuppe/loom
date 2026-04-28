/// types/inventory.dart — Stock level + reservation token.
///
/// `StockLevel` tracks `onHand` and `reserved` for a single sku.
/// `available == onHand - reserved`. `ReservationToken` ties a stock
/// hold to an orderId; `committed` flips when the reservation is
/// applied to onHand at ship time.

class StockLevel {
  final String sku;
  int onHand;
  int reserved;

  StockLevel({required this.sku, this.onHand = 0, this.reserved = 0});

  int get available => onHand - reserved;
}

class ReservationToken {
  final String tokenId;
  final String orderId;
  final String sku;
  final int quantity;
  bool committed;
  bool released;

  ReservationToken({
    required this.tokenId,
    required this.orderId,
    required this.sku,
    required this.quantity,
    this.committed = false,
    this.released = false,
  });

  bool get isOpen => !committed && !released;
}
