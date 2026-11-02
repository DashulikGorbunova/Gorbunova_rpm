from fastapi import APIRouter, Depends
from app.schemas import MenuWrite, MenuView
from app.core.dependencies import get_db, get_current_user, require_role
from app.modules.menu.repository import MenuRepository
from app.modules.menu.service import MenuService

router = APIRouter(prefix='/menu', tags=['menu'])
def service(db=Depends(get_db)):
    return MenuService(MenuRepository(db))

@router.get('', response_model=list[MenuView])
def menu(user=Depends(get_current_user), svc=Depends(service)):
    return svc.list()

@router.post('', response_model=MenuView, status_code=201)
def create(payload: MenuWrite, user=Depends(require_role('admin','cook')), svc=Depends(service)):
    return svc.save(user,payload.name,payload.price)

@router.patch('/{item_id}', response_model=MenuView)
def update(item_id: int, payload: MenuWrite, user=Depends(require_role('admin','cook')), svc=Depends(service)):
    return svc.save(user,payload.name,payload.price,item_id)
