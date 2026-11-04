"""Explicit local admin creation: python -m app.bootstrap admin@example.org"""
import getpass
import sys
from pydantic import TypeAdapter, EmailStr
from app.core.config import Settings
from app.core.security import passwords
from app.database import make_session_factory
from app.modules.users.repository import UserRepository

def main():
    if len(sys.argv) != 2:
        raise SystemExit('Usage: python -m app.bootstrap EMAIL (password prompted securely)')
    email = str(TypeAdapter(EmailStr).validate_python(sys.argv[1])).lower()
    password = getpass.getpass('New admin password (12..72 UTF-8 bytes): ')
    if password != getpass.getpass('Repeat password: '):
        raise SystemExit('Passwords differ')
    factory = make_session_factory(Settings().database_url)
    with factory() as db:
        repository = UserRepository(db)
        if repository.by_email(email):
            raise SystemExit('Account already exists; no change')
        repository.create(email,passwords.hash(password),'admin')
    print('Admin created')
if __name__ == '__main__':
    main()
