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

class ServiceUnavailable(DomainError):
    pass
class ServiceTimeout(DomainError):
    pass
class InvalidInput(DomainError):
    pass
