import uuid
from sqlalchemy import select
from app.models import OrderRow, MenuRow, JobRow, BonusRow
from app.domain.entities import Order

def entity(row):
    return None if row is None else Order(row.id,row.customer_id,row.item_id,row.quantity,row.status)

class OrderRepository:
    def __init__(self, db):
        self.db = db
    def get(self, order_id, lock=False):
        query = select(OrderRow).where(OrderRow.id == order_id)
        if lock:
            query = query.with_for_update()
        return entity(self.db.scalar(query))
    def item_exists(self, item_id):
        return self.db.get(MenuRow,item_id) is not None
    def create(self, customer_id, item_id, quantity, operations=(), bonus_points=0):
        row = OrderRow(customer_id=customer_id,item_id=item_id,quantity=quantity)
        self.db.add(row)
        self.db.flush()
        for kind in operations:
            self.db.add(JobRow(id=str(uuid.uuid4()),order_id=row.id,kind=kind))
        self.db.add(BonusRow(order_id=row.id,points=bonus_points))
        # Order, bonus and durable jobs are committed together, before publishing.
        self.db.commit()
        return entity(row)
    def list(self, customer_id=None, kitchen=False):
        query = select(OrderRow)
        if customer_id is not None:
            query = query.where(OrderRow.customer_id == customer_id)
        if kitchen:
            query = query.where(OrderRow.status == 'PENDING')
        return [entity(r) for r in self.db.scalars(query.order_by(OrderRow.id).limit(100))]
    def jobs(self, order_id):
        return [dict(id=r.id,kind=r.kind,status=r.status,attempts=r.attempts,last_error=r.last_error)
                for r in self.db.scalars(select(JobRow).where(JobRow.order_id==order_id).order_by(JobRow.kind))]
    def cancel(self, order_id):
        row = self.db.get(OrderRow,order_id)
        row.status = 'CANCELLED'; self.db.commit()
        return entity(row)
