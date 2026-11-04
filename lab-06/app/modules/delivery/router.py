import json
from fastapi import APIRouter,Depends,Request
from fastapi.responses import StreamingResponse
from app.schemas import DeliveryCreate,DeliveryView
from app.core.dependencies import get_current_user,require_role,oauth2_scheme
from app.modules.delivery.grpc_client import DeliveryGrpcClient
from app.modules.delivery.service import DeliveryService
from app.domain.errors import DomainError

router=APIRouter(prefix='/delivery',tags=['delivery'])
def gateway(request: Request,token: str=Depends(oauth2_scheme)):
    settings=request.app.state.settings
    return DeliveryGrpcClient(request.app.state.delivery_channel,token,settings.delivery_timeout_seconds,settings.delivery_stream_seconds)
def service(client=Depends(gateway)):
    return DeliveryService(client)

@router.get('',response_model=list[DeliveryView])
def deliveries(user=Depends(require_role('student','courier','admin')),svc=Depends(service)):
    return svc.list(user)

@router.get('/order/{order_id}',response_model=DeliveryView)
def by_order(order_id:int,user=Depends(get_current_user),svc=Depends(service)):
    return svc.by_order(order_id,user)

@router.get('/{delivery_id}',response_model=DeliveryView)
def get(delivery_id:int,user=Depends(get_current_user),svc=Depends(service)):
    return svc.get(delivery_id,user)

@router.post('/assign',response_model=DeliveryView,status_code=201)
@router.post('',response_model=DeliveryView,status_code=201,include_in_schema=False)
def assign(payload:DeliveryCreate,user=Depends(require_role('admin')),svc=Depends(service)):
    return svc.assign(payload.order_id,payload.courier_id,user)

@router.post('/{delivery_id}/complete',response_model=DeliveryView)
def complete(delivery_id:int,user=Depends(require_role('courier')),svc=Depends(service)):
    return svc.complete(delivery_id,user)

@router.post('/{delivery_id}/start',response_model=DeliveryView)
def start(delivery_id:int,user=Depends(require_role('courier')),svc=Depends(service)):
    return svc.advance(delivery_id,user)

@router.get('/{delivery_id}/track')
def track(delivery_id:int,user=Depends(get_current_user),svc=Depends(service),client=Depends(gateway)):
    svc.get(delivery_id,user)  # Preflight so auth/outage returns normal HTTP status.
    def events():
        try:
            for value in client.track(delivery_id):
                yield 'event: status\ndata: '+json.dumps({'delivery_id':value.delivery_id,'status':value.status,'observed_at':value.observed_at})+'\n\n'
        except DomainError as error:
            yield 'event: error\ndata: '+json.dumps({'detail':str(error)})+'\n\n'
    return StreamingResponse(events(),media_type='text/event-stream',headers={'Cache-Control':'no-cache'})
