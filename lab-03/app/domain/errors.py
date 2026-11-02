class DomainError(Exception):
    pass
class NotFound(DomainError):
    pass
class AccessDenied(DomainError):
    pass
class InvalidCredentials(DomainError):
    pass
class Conflict(DomainError):
    pass
