from fastapi import APIRouter, Depends
from app.schemas import OrderCreate, OrderView, KitchenView
from app.core.dependencies import get_db, get_current_user, require_role
from app.core.rate_limit import rate_limit
from app.modules.orders.repository import OrderRepository
from app.modules.orders.service import OrderService

router = APIRouter(tags=['orders'])
def service(db=Depends(get_db)):
    return OrderService(OrderRepository(db))

@router.post('/orders/create', status_code=201)
def create(payload: OrderCreate, user=Depends(require_role('student')), svc=Depends(service),
           limited=Depends(rate_limit('orders',10))):
    order = svc.create(user,payload.item_id,payload.quantity)
    return {'status':'success','order_id':order.id}

@router.get('/orders', response_model=list[OrderView])
def orders(user=Depends(require_role('student','admin')), svc=Depends(service)):
    return svc.list(user)

@router.get('/orders/{order_id}', response_model=OrderView)
def get(order_id: int, user=Depends(get_current_user), svc=Depends(service)):
    return svc.get(order_id,user)

@router.post('/orders/{order_id}/cancel')
def cancel(order_id: int, user=Depends(require_role('student','admin')), svc=Depends(service)):
    svc.cancel(order_id,user)
    return {'status':'success'}

@router.get('/kitchen/orders', response_model=list[KitchenView])
def kitchen(user=Depends(require_role('cook')), svc=Depends(service)):
    return svc.kitchen(user)
