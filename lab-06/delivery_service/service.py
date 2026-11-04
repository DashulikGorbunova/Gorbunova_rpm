from app.domain.ports import DeliveryRepository
from app.domain.errors import AccessDenied, NotFound, Conflict

class DeliveryService:
    def __init__(self, repository: DeliveryRepository):
        self.repository = repository
    def get(self, delivery_id, actor):
        delivery = self.repository.get(delivery_id)
        if delivery is None:
            raise NotFound('Delivery not found')
        allowed = (actor.role == 'admin' or
                   actor.role == 'courier' and delivery.courier_id == actor.id or
                   actor.role == 'student' and delivery.customer_id == actor.id)
        if not allowed:
            raise AccessDenied('Access denied')
        return delivery
    def list(self, actor):
        if actor.role not in {'admin','courier','student'}:
            raise AccessDenied('Access denied')
        return self.repository.list(actor)
    def assign(self, order_id, courier_id, actor):
        if actor.role != 'admin':
            raise AccessDenied('Only admin assigns deliveries')
        order = self.repository.order(order_id)
        if order is None:
            raise NotFound('Order not found')
        if order.status != 'PENDING':
            raise Conflict('Cancelled order')
        courier = self.repository.user(courier_id)
        if not courier or courier.role != 'courier' or courier.is_blocked:
            raise Conflict('Active courier required')
        return self.repository.create(order_id,courier_id)
    def complete(self, delivery_id, actor):
        if actor.role != 'courier':
            raise AccessDenied('Only courier completes delivery')
        self.get(delivery_id,actor)
        return self.repository.complete(delivery_id)

    def advance(self, delivery_id, actor):
        if actor.role!='courier':
            raise AccessDenied('Only courier starts delivery')
        self.get(delivery_id,actor)
        return self.repository.advance(delivery_id)
    def by_order(self, order_id, actor):
        delivery=self.repository.by_order(order_id)
        if delivery is None:
            raise NotFound('Delivery not found')
        return self.get(delivery.id,actor)
