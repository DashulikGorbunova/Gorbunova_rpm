"""Monolith facade. Business ownership rules now live in delivery_service/service.py."""
from app.domain.ports import DeliveryGateway

class DeliveryService:
    def __init__(self, gateway: DeliveryGateway):
        self.gateway=gateway
    def get(self, delivery_id, actor):
        return self.gateway.get(delivery_id)
    def list(self, actor):
        return self.gateway.list()
    def assign(self, order_id, courier_id, actor):
        return self.gateway.assign(order_id,courier_id)
    def complete(self, delivery_id, actor):
        return self.gateway.complete(delivery_id)
    def advance(self, delivery_id, actor):
        return self.gateway.advance(delivery_id)
    def by_order(self, order_id, actor):
        return self.gateway.by_order(order_id)
