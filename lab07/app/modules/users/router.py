from fastapi import APIRouter, Depends
from app.schemas import Register, UserView, UserPatch
from app.core.dependencies import get_db, get_current_user, require_role
from app.core.rate_limit import rate_limit
from app.core.security import passwords
from app.modules.users.service import UserService
from app.modules.users.repository import UserRepository

router = APIRouter(prefix='/users', tags=['users'])
def service(db=Depends(get_db)):
    return UserService(UserRepository(db),passwords)

@router.post('/register', response_model=UserView, status_code=201,
             dependencies=[Depends(rate_limit('register'))])
def register(payload: Register, svc=Depends(service)):
    return svc.register(str(payload.email),payload.password)

@router.get('/me', response_model=UserView)
def me(user=Depends(get_current_user)):
    return user

@router.get('', response_model=list[UserView])
def users(user=Depends(require_role('admin')), svc=Depends(service)):
    return svc.list(user)

@router.get('/{user_id}', response_model=UserView)
def get(user_id: int, user=Depends(get_current_user), svc=Depends(service)):
    return svc.get(user_id,user)

@router.patch('/{user_id}', response_model=UserView)
def update(user_id: int, payload: UserPatch, user=Depends(require_role('admin')), svc=Depends(service)):
    return svc.update(user_id,user,payload.role,payload.is_blocked)
