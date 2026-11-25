from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from app.models import UserRow, RoleRow, SessionRow
from app.domain.entities import User
from app.domain.errors import Conflict

def user_entity(row):
    return None if row is None else User(row.id, row.email, row.role.name, row.password_hash, row.is_blocked)

class UserRepository:
    def __init__(self, db):
        self.db = db

    def by_email(self, email):
        return user_entity(self.db.scalar(select(UserRow).where(UserRow.email == email)))

    def get(self, user_id):
        return user_entity(self.db.get(UserRow, user_id))

    def list(self):
        return [user_entity(r) for r in self.db.scalars(select(UserRow).order_by(UserRow.id).limit(100))]

    def create(self, email, password_hash, role):
        role_row = self.db.scalar(select(RoleRow).where(RoleRow.name == role))
        row = UserRow(email=email, password_hash=password_hash, role_id=role_row.id)
        self.db.add(row)
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            raise Conflict('Email already registered') from None
        return user_entity(row)

    def update(self, user_id, role, blocked):
        row = self.db.get(UserRow, user_id)
        if role is not None:
            row.role = self.db.scalar(select(RoleRow).where(RoleRow.name == role))
        if blocked is not None:
            row.is_blocked = blocked
            if blocked:
                self.db.execute(update(SessionRow).where(SessionRow.user_id == user_id).values(is_revoked=True))
        self.db.commit()
        return user_entity(row)
