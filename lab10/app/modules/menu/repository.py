from sqlalchemy import select
from sqlalchemy.orm import contains_eager, Session
from app.models import MenuRow, CategoryRow
from app.domain.entities import MenuItem
from app.domain.errors import NotFound
from app.modules.menu.cache import MenuCache

def entity(row):
    return None if row is None else MenuItem(row.id,row.name,row.price,row.category_id,row.category.name)

class MenuRepository:
    def __init__(self, db, cache: MenuCache | None = None):
        self.db, self.cache = db, cache

    def get(self, item_id):
        return entity(self.db.get(MenuRow,item_id))

    def _load(self, category_id=None):
        # Bound read session: release its connection before response serialization.
        # Both baseline and cached miss use exactly the same SQL and lifetime.
        with Session(self.db.get_bind()) as reader:
            query = select(MenuRow).join(MenuRow.category).options(contains_eager(MenuRow.category)).order_by(CategoryRow.name,MenuRow.name,MenuRow.id).limit(100)
            if category_id is not None:
                if reader.get(CategoryRow,category_id) is None:
                    raise NotFound('Category not found')
                query = query.where(MenuRow.category_id == category_id)
            return [entity(r) for r in reader.scalars(query)]

    def list(self):
        if self.cache is None:
            return self._load()
        return self.cache.get_or_load('menu:all',self.cache.settings.menu_ttl,self._load)

    def category(self, category_id):
        if self.cache is None:
            return self._load(category_id)
        return self.cache.get_or_load(f'menu:category:{category_id}',self.cache.settings.category_ttl,
                                      lambda:self._load(category_id))

    def _category_exists(self, category_id):
        if self.db.get(CategoryRow,category_id) is None:
            raise NotFound('Category not found')

    def create(self, name, price, category_id=1):
        self._category_exists(category_id)
        row = MenuRow(name=name,price=price,category_id=category_id)
        self.db.add(row)
        self.db.commit()
        if self.cache:
            self.cache.invalidate([category_id])
        return entity(row)

    def update(self, item_id, name, price, category_id=1):
        self._category_exists(category_id)
        row = self.db.get(MenuRow,item_id)
        old_category = row.category_id
        row.name, row.price, row.category_id = name, price, category_id
        self.db.commit()
        if self.cache:
            self.cache.invalidate([old_category,category_id])
        # Reload joined category after invalidating the committed update.
        self.db.refresh(row)
        return entity(row)
