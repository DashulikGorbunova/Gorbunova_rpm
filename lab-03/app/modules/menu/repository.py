from sqlalchemy import select
from app.models import MenuRow
from app.domain.entities import MenuItem

def entity(row):
    return None if row is None else MenuItem(row.id,row.name,row.price)

class MenuRepository:
    def __init__(self, db):
        self.db = db
    def get(self, item_id):
        return entity(self.db.get(MenuRow,item_id))
    def list(self):
        return [entity(r) for r in self.db.scalars(select(MenuRow).order_by(MenuRow.id).limit(100))]
    def create(self, name, price):
        row = MenuRow(name=name,price=price)
        self.db.add(row); self.db.commit()
        return entity(row)
    def update(self, item_id, name, price):
        row = self.db.get(MenuRow,item_id)
        row.name, row.price = name, price
        self.db.commit()
        return entity(row)
