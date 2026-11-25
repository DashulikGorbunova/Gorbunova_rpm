"""Payment HTTP endpoint, using JWT and the shared DB."""
from fastapi import APIRouter, Depends, HTTPException
from app.core.dependencies import get_current_user, get_db
from app.core.eda import pay_order
from app.core.observability import log
from opentelemetry import trace
router = APIRouter(tags=['orders'])

@router.post('/orders/{order_id}/pay')
def pay(order_id: int, user=Depends(get_current_user), db=Depends(get_db)):
    try:
        with trace.get_tracer(__name__).start_as_current_span('OrderService.pay'):
            result=pay_order(db, order_id, user)
        log('monolith','order_paid',order_id=order_id,already_paid=result['already_paid'])
        return result
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
