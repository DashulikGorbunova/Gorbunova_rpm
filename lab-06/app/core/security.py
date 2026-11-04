import bcrypt

class BcryptPasswords:
    def hash(self, password: str) -> str:
        data = password.encode('utf-8')
        if not 12 <= len(data) <= 72:
            raise ValueError('Password must contain 12..72 UTF-8 bytes')
        return bcrypt.hashpw(data, bcrypt.gensalt(rounds=12)).decode('ascii')

    def verify(self, password: str, hashed: str) -> bool:
        data = password.encode('utf-8')
        if len(data) > 72:
            return False
        try:
            return bcrypt.checkpw(data, hashed.encode('ascii'))
        except (ValueError, UnicodeError):
            return False

passwords = BcryptPasswords()
# Used for unknown accounts so failed login still performs bcrypt work.
DUMMY_HASH = passwords.hash('dummy-password-never-used')
