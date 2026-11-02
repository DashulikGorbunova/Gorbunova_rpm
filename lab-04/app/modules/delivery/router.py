from fastapi import APIRouter, Depends
from app.schemas import DeliveryCreate, DeliveryView
from app.core.dependencies import get_db, get_current_user, require_role
from app.modules.delivery.repository import DeliveryRepository
from app.modules.delivery.service import DeliveryService

router = APIRouter(prefix='/delivery', tags=['delivery'])
def service(db=Depends(get_db)):
    return DeliveryService(DeliveryRepository(db))

@router.get('', response_model=list[DeliveryView])
def deliveries(user=Depends(require_role('student','courier','admin')), svc=Depends(service)):
    return svc.list(user)

@router.get('/{delivery_id}', response_model=DeliveryView)
def get(delivery_id: int, user=Depends(get_current_user), svc=Depends(service)):
    return svc.get(delivery_id,user)

@router.post('', response_model=DeliveryView, status_code=201)
def assign(payload: DeliveryCreate, user=Depends(require_role('admin')), svc=Depends(service)):
    return svc.assign(payload.order_id,payload.courier_id,user)

@router.post('/{delivery_id}/complete', response_model=DeliveryView)
def complete(delivery_id: int, user=Depends(require_role('courier')), svc=Depends(service)):
    return svc.complete(delivery_id,user)
