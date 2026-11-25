from pathlib import Path
import sys, os
from decimal import Decimal
BASE=Path(__file__).resolve().parents[2]/'lab-06'
sys.path.insert(0,str(BASE))
os.chdir(BASE)
from sqlalchemy import select
from app.core.config import Settings
from app.database import make_session_factory
from app.models import MenuRow,CategoryRow
from app.modules.menu.repository import MenuRepository
from app.modules.menu.cache import MenuCache
from app.core.redis import menu_redis
settings=Settings()
factory=make_session_factory(settings.database_url)
cache=menu_redis(settings.redis_url)
try:
    with factory() as db:
        category=db.scalar(select(CategoryRow).order_by(CategoryRow.id))
        if category is None:
            category=CategoryRow(name='Общее');db.add(category);db.commit()
        repo=MenuRepository(db,MenuCache(cache,settings))
        for name,price in [('Сырники',150),('Борщ',180),('Паста',240),('Гречка с курицей',220),('Салат овощной',120),('Компот',65)]:
            if not db.scalar(select(MenuRow).where(MenuRow.name==name)):
                repo.create(name,Decimal(price),category.id)
    print('Меню заполнено')
finally:
    cache.close()
