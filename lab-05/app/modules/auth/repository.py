from sqlalchemy import select
from app.models import SessionRow, RefreshRow
from app.domain.entities import AuthSession, RefreshToken
from app.modules.users.repository import UserRepository

class AuthRepository(UserRepository):
    def create_session(self, user_id, session_id, expires_at):
        self.db.add(SessionRow(id=session_id, user_id=user_id, expires_at=expires_at))
        self.db.flush()

    @staticmethod
    def session_entity(row):
        return None if row is None else AuthSession(row.id,row.user_id,row.expires_at,row.is_revoked)

    def lock_session(self, session_id):
        row = self.db.scalar(select(SessionRow).where(SessionRow.id == session_id).with_for_update())
        return self.session_entity(row)

    def get_session(self, session_id):
        return self.session_entity(self.db.get(SessionRow, session_id))

    def refresh(self, token_hash):
        r = self.db.get(RefreshRow, token_hash)
        return None if r is None else RefreshToken(r.token_hash,r.session_id,r.expires_at,r.is_revoked)

    def save_refresh(self, token_hash, session_id, expires_at):
        self.db.add(RefreshRow(token_hash=token_hash,session_id=session_id,expires_at=expires_at))

    def consume_refresh(self, token_hash):
        self.db.get(RefreshRow, token_hash).is_revoked = True

    def revoke_session(self, session_id):
        self.db.get(SessionRow, session_id).is_revoked = True

    def commit(self):
        self.db.commit()
