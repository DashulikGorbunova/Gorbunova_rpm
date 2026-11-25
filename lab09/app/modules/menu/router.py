from fastapi import APIRouter, Depends, Request
from app.schemas import MenuWrite, MenuView
from app.core.dependencies import get_db, get_current_user, require_role
from app.modules.menu.repository import MenuRepository
from app.modules.menu.cache import MenuCache
from app.modules.menu.service import MenuService

router = APIRouter(prefix='/menu', tags=['menu'])
def service(request: Request, db=Depends(get_db)):
    cache = MenuCache(request.app.state.menu_redis,request.app.state.settings)
    return MenuService(MenuRepository(db,cache))

@router.get('', response_model=list[MenuView], include_in_schema=False)
@router.get('/items', response_model=list[MenuView])
def menu(user=Depends(get_current_user), svc=Depends(service)):
    return svc.list()

@router.get('/categories/{category_id}', response_model=list[MenuView])
def category(category_id: int, user=Depends(get_current_user), svc=Depends(service)):
    return svc.category(category_id)

@router.post('', response_model=MenuView, status_code=201, include_in_schema=False)
@router.post('/items', response_model=MenuView, status_code=201)
def create(payload: MenuWrite, user=Depends(require_role('admin','cook')), svc=Depends(service)):
    return svc.save(user,payload.name,payload.price,category_id=payload.category_id)

@router.patch('/{item_id}', response_model=MenuView, include_in_schema=False)
@router.patch('/items/{item_id}', response_model=MenuView)
def update(item_id: int, payload: MenuWrite, user=Depends(require_role('admin','cook')), svc=Depends(service)):
    return svc.save(user,payload.name,payload.price,item_id,category_id=payload.category_id)
