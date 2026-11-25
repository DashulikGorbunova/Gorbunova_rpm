from datetime import datetime, timedelta, timezone
import uuid
from app.domain.ports import AuthRepository, Passwords, TokenCodec
from app.domain.errors import InvalidCredentials, AccessDenied

class AuthService:
    def __init__(self, repository: AuthRepository, passwords: Passwords,
                 codec: TokenCodec, dummy_hash: str, refresh_days: int = 7):
        self.repository, self.passwords, self.codec = repository, passwords, codec
        self.dummy_hash, self.refresh_days = dummy_hash, refresh_days

    def login(self, email, password):
        user = self.repository.by_email(email.strip().lower())
        valid = self.passwords.verify(password, user.password_hash if user else self.dummy_hash)
        if not user or not valid or user.is_blocked:
            raise InvalidCredentials('Invalid credentials')
        sid = str(uuid.uuid4())
        expires = datetime.now(timezone.utc) + timedelta(days=self.refresh_days)
        self.repository.create_session(user.id, sid, expires)
        pair = self.codec.issue(user.id, sid, expires)
        self.repository.save_refresh(self.codec.digest(pair['refresh_token']), sid, expires)
        self.repository.commit()
        return pair

    def authenticate(self, token):
        claims = self.codec.decode(token, 'access')
        session = self.repository.get_session(claims['sid'])
        if (not session or session.is_revoked or session.user_id != int(claims['sub'])
                or session.expires_at <= datetime.now(timezone.utc)):
            raise InvalidCredentials('Session expired or revoked')
        user = self.repository.get(session.user_id)
        if not user:
            raise InvalidCredentials('Invalid credentials')
        if user.is_blocked:
            raise AccessDenied('User is blocked')
        return user

    def refresh(self, token):
        claims = self.codec.decode(token, 'refresh')
        # PostgreSQL row lock serializes rotations for the entire token family.
        session = self.repository.lock_session(claims['sid'])
        if (not session or session.is_revoked or session.user_id != int(claims['sub'])
                or session.expires_at <= datetime.now(timezone.utc)):
            raise InvalidCredentials('Invalid refresh token')
        stored = self.repository.refresh(self.codec.digest(token))
        if not stored or stored.session_id != session.id:
            raise InvalidCredentials('Invalid refresh token')
        if stored.is_revoked:
            self.repository.revoke_session(session.id)
            # Persist replay revocation even though the request will return 401.
            self.repository.commit()
            raise InvalidCredentials('Refresh token replay: session revoked')
        if stored.expires_at <= datetime.now(timezone.utc):
            raise InvalidCredentials('Expired refresh token')
        user = self.repository.get(session.user_id)
        if not user or user.is_blocked:
            raise InvalidCredentials('Invalid credentials')
        self.repository.consume_refresh(stored.token_hash)
        pair = self.codec.issue(user.id, session.id, session.expires_at)
        self.repository.save_refresh(self.codec.digest(pair['refresh_token']), session.id, session.expires_at)
        self.repository.commit()
        return pair

    def logout(self, token):
        claims = self.codec.decode(token, 'access')
        # Require authentication in router before locking/revoking.
        session = self.repository.lock_session(claims['sid'])
        if session:
            self.repository.revoke_session(session.id)
            self.repository.commit()
