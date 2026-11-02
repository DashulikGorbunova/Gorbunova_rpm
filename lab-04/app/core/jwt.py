import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from jose import jwt, JWTError
from app.domain.errors import InvalidCredentials

class JwtCodec:
    def __init__(self, settings):
        self.settings = settings

    @staticmethod
    def digest(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()

    def issue(self, user_id: int, session_id: str, expires_at: datetime) -> dict:
        now = datetime.now(timezone.utc)
        common = {'sub': str(user_id), 'sid': session_id, 'iat': int(now.timestamp()),
                  'iss': self.settings.jwt_issuer, 'aud': self.settings.jwt_audience}
        def make(kind, expiry):
            return jwt.encode({**common, 'type': kind, 'jti': str(uuid.uuid4()),
                               'exp': int(expiry.timestamp())},
                              self.settings.jwt_secret.get_secret_value(), algorithm='HS256')
        return {'access_token': make('access', min(now + timedelta(minutes=self.settings.access_minutes), expires_at)),
                'refresh_token': make('refresh', expires_at), 'token_type': 'bearer'}

    def decode(self, token: str, kind: str) -> dict:
        try:
            claims = jwt.decode(token, self.settings.jwt_secret.get_secret_value(), algorithms=['HS256'],
                                issuer=self.settings.jwt_issuer, audience=self.settings.jwt_audience,
                                options={'require_exp': True, 'require_iat': True, 'require_sub': True,
                                         'require_aud': True, 'require_iss': True, 'require_jti': True})
            if claims.get('type') != kind or not isinstance(claims.get('sid'), str):
                raise ValueError('Wrong token type or session')
            uuid.UUID(claims['sid'])
            if int(claims['sub']) <= 0:
                raise ValueError('Invalid subject')
            return claims
        except (JWTError, ValueError, TypeError, KeyError):
            raise InvalidCredentials('Invalid or expired token') from None
