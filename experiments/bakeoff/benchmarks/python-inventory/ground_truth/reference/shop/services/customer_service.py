"""services/customer_service.py — Customer registration + lookup + address mgmt.

Backed by Store.customers. All errors are domain errors from errors.py.
"""

from ..errors import ConflictError, NotFoundError
from ..persistence import Store
from ..types.customers import Address, Customer


class CustomerService:
    def __init__(self, store: Store) -> None:
        self.store = store

    def register(self, *, id: str, name: str, email: str) -> Customer:
        if id in self.store.customers:
            raise ConflictError(f"customer with id {id} already exists")
        customer = Customer(id=id, name=name, email=email)
        self.store.customers[id] = customer
        return customer

    def get(self, id: str) -> Customer:
        customer = self.store.customers.get(id)
        if customer is None:
            raise NotFoundError(f"customer not found: {id}")
        return customer

    def add_address(self, id: str, address: Address) -> Customer:
        customer = self.get(id)
        customer.addresses.append(address)
        return customer
