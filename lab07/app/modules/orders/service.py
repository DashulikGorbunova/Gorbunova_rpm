from app.domain.ports import OrderRepository, OrderDispatcher
from app.domain.errors import AccessDenied, NotFound, Conflict

class OrderService:
    def __init__(self, repository: OrderRepository, dispatcher: OrderDispatcher | None = None):
        self.repository, self.dispatcher = repository, dispatcher
    def create(self, actor, item_id, quantity):
        if actor.role != 'student':
            raise AccessDenied('Only students create orders')
        if quantity < 1 or quantity > 100:
            raise Conflict('Invalid quantity')
        if not self.repository.item_exists(item_id):
            raise NotFound('Menu item not found')
        # Business orchestration stays here; adapters implement delivery.
        order = self.repository.create(actor.id,item_id,quantity,operations=('pdf','email','sms'),bonus_points=quantity)
        if self.dispatcher:
            self.dispatcher.kick(order.id)
        return order
    def get(self, order_id, actor, lock=False):
        order = self.repository.get(order_id,lock=lock)
        if order is None:
            raise NotFound('Order not found')
        if order.customer_id != actor.id and actor.role != 'admin':
            raise AccessDenied('Access denied')
        return order
    def list(self, actor):
        if actor.role not in {'student','admin'}:
            raise AccessDenied('Access denied')
        return self.repository.list(None if actor.role == 'admin' else actor.id)
    def jobs(self, order_id, actor):
        self.get(order_id,actor)
        return self.repository.jobs(order_id)
    def kitchen(self, actor):
        if actor.role != 'cook':
            raise AccessDenied('Only cooks see kitchen')
        return self.repository.list(kitchen=True)
    def cancel(self, order_id, actor):
        if actor.role not in {'student','admin'}:
            raise AccessDenied('Access denied')
        order = self.get(order_id,actor,lock=True)
        if order.status != 'PENDING':
            raise Conflict('Order already cancelled')
        return self.repository.cancel(order_id)
