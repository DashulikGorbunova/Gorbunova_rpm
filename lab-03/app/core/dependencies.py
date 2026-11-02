from fastapi import Depends, Request, HTTPException
from fastapi.security import OAuth2PasswordBearer
from app.modules.auth.repository import AuthRepository
from app.modules.auth.service import AuthService
from app.core.security import passwords, DUMMY_HASH

oauth2_scheme = OAuth2PasswordBearer(tokenUrl='/auth/token')

def get_db(request: Request):
    with request.app.state.session_factory() as db:
        try:
            yield db
        finally:
            db.rollback()

def auth_service(request: Request, db=Depends(get_db)):
    return AuthService(AuthRepository(db), passwords, request.app.state.codec,
                       DUMMY_HASH, request.app.state.settings.refresh_days)

def get_current_user(token: str = Depends(oauth2_scheme), service=Depends(auth_service)):
    return service.authenticate(token)

def require_role(*roles: str):
    def checker(user=Depends(get_current_user)):
        if user.role not in roles:
            raise HTTPException(403, 'Access denied')
        return user
    return checker
