from app.domain.ports import UserRepository, Passwords
from app.domain.entities import User
from app.domain.errors import AccessDenied, NotFound, Conflict

class UserService:
    def __init__(self, repository: UserRepository, passwords: Passwords):
        self.repository, self.passwords = repository, passwords

    def register(self, email: str, password: str) -> User:
        email = email.strip().lower()
        if self.repository.by_email(email):
            raise Conflict('Email already registered')
        return self.repository.create(email, self.passwords.hash(password), 'student')

    def get(self, user_id: int, actor: User) -> User:
        if actor.id != user_id and actor.role != 'admin':
            raise AccessDenied('Access denied')
        user = self.repository.get(user_id)
        if user is None:
            raise NotFound('User not found')
        return user

    def list(self, actor: User) -> list[User]:
        if actor.role != 'admin':
            raise AccessDenied('Access denied')
        return self.repository.list()

    def update(self, user_id: int, actor: User, role: str | None, blocked: bool | None) -> User:
        if actor.role != 'admin':
            raise AccessDenied('Access denied')
        if role is not None and role not in {'student','cook','courier','admin'}:
            raise Conflict('Unknown role')
        if self.repository.get(user_id) is None:
            raise NotFound('User not found')
        return self.repository.update(user_id, role, blocked)
