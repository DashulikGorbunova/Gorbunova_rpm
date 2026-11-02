from app.domain.ports import MenuRepository
from app.domain.errors import AccessDenied, NotFound

class MenuService:
    def __init__(self, repository: MenuRepository):
        self.repository = repository
    def list(self):
        return self.repository.list()
    def save(self, actor, name, price, item_id=None):
        if actor.role not in {'admin','cook'}:
            raise AccessDenied('Access denied')
        if item_id is None:
            return self.repository.create(name,price)
        if self.repository.get(item_id) is None:
            raise NotFound('Menu item not found')
        return self.repository.update(item_id,name,price)
