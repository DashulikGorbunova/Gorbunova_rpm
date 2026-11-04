from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

@dataclass(frozen=True)
class User:
    id: int
    email: str
    role: str
    password_hash: str
    is_blocked: bool = False

@dataclass(frozen=True)
class Order:
    id: int
    customer_id: int
    item_id: int
    quantity: int
    status: str

@dataclass(frozen=True)
class MenuItem:
    id: int
    name: str
    price: Decimal
    category_id: int = 1
    category_name: str = "Общее"

@dataclass(frozen=True)
class Delivery:
    id: int
    order_id: int
    customer_id: int
    courier_id: int
    status: str

@dataclass(frozen=True)
class AuthSession:
    id: str
    user_id: int
    expires_at: datetime
    is_revoked: bool

@dataclass(frozen=True)
class RefreshToken:
    token_hash: str
    session_id: str
    expires_at: datetime
    is_revoked: bool
