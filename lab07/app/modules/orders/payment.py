"""Payment HTTP endpoint, using JWT and the shared DB."""
from fastapi import APIRouter, Depends, HTTPException
from app.core.dependencies import get_current_user, get_db
from app.core.eda import pay_order
router = APIRouter(tags=['orders'])

@router.post('/orders/{order_id}/pay')
def pay(order_id: int, user=Depends(get_current_user), db=Depends(get_db)):
    try:
        return pay_order(db, order_id, user)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
