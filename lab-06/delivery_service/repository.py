from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from app.models import DeliveryRow, OrderRow, UserRow
from app.domain.entities import Delivery
from app.domain.errors import Conflict
from app.modules.orders.repository import entity as order_entity
from app.modules.users.repository import user_entity

class DeliveryRepository:
    def __init__(self, db):
        self.db = db
    def _entity(self, row):
        if row is None:
            return None
        order = self.db.get(OrderRow,row.order_id)
        return Delivery(row.id,row.order_id,order.customer_id,row.courier_id,row.status)
    def get(self, delivery_id):
        return self._entity(self.db.get(DeliveryRow,delivery_id))
    def list(self, user):
        query = select(DeliveryRow).join(OrderRow)
        if user.role == 'student':
            query = query.where(OrderRow.customer_id == user.id)
        elif user.role == 'courier':
            query = query.where(DeliveryRow.courier_id == user.id)
        return [self._entity(r) for r in self.db.scalars(query.order_by(DeliveryRow.id).limit(100))]
    def order(self, order_id):
        return order_entity(self.db.scalar(select(OrderRow).where(OrderRow.id == order_id).with_for_update()))
    def user(self, user_id):
        return user_entity(self.db.get(UserRow,user_id))
    def create(self, order_id, courier_id):
        row = DeliveryRow(order_id=order_id,courier_id=courier_id)
        self.db.add(row)
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            raise Conflict('Delivery already assigned') from None
        return self._entity(row)
    def complete(self, delivery_id):
        row = self.db.scalar(select(DeliveryRow).where(DeliveryRow.id == delivery_id).with_for_update())
        if row.status not in {'ASSIGNED','ON_THE_WAY'}:
            raise Conflict('Delivery already completed')
        row.status = 'DELIVERED'; self.db.commit()
        return self._entity(row)

    def advance(self, delivery_id):
        row=self.db.scalar(select(DeliveryRow).where(DeliveryRow.id==delivery_id).with_for_update())
        if row.status!='ASSIGNED':
            raise Conflict('Delivery is not assigned')
        row.status='ON_THE_WAY';self.db.commit()
        return self._entity(row)
    def by_order(self, order_id):
        return self._entity(self.db.scalar(select(DeliveryRow).where(DeliveryRow.order_id==order_id)))
