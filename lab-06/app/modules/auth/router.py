from fastapi import APIRouter, Depends
from fastapi.security import OAuth2PasswordRequestForm
from app.schemas import Login, Refresh, TokenPair
from app.core.dependencies import auth_service, get_current_user, oauth2_scheme
from app.core.rate_limit import rate_limit

router = APIRouter(prefix='/auth', tags=['auth'])
login_limit = rate_limit('login')

@router.post('/login', response_model=TokenPair, dependencies=[Depends(login_limit)])
def login(payload: Login, service=Depends(auth_service)):
    return service.login(str(payload.email),payload.password)

@router.post('/token', response_model=TokenPair, dependencies=[Depends(login_limit)])
def token(form: OAuth2PasswordRequestForm = Depends(), service=Depends(auth_service)):
    """Swagger OAuth2: enter email in username; JSON clients use /auth/login."""
    return service.login(form.username,form.password)

@router.post('/refresh', response_model=TokenPair, dependencies=[Depends(rate_limit('refresh',20))])
def refresh(payload: Refresh, service=Depends(auth_service)):
    return service.refresh(payload.refresh_token)

@router.post('/logout')
def logout(user=Depends(get_current_user), token: str=Depends(oauth2_scheme), service=Depends(auth_service)):
    service.logout(token)
    return {'status':'success'}
