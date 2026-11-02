from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

Role = Literal['student','cook','courier','admin']
class Input(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=False)
class Register(Input):
    email: EmailStr
    password: str = Field(min_length=12, max_length=72)
    @field_validator('password')
    @classmethod
    def password_bytes(cls, value):
        if not 12 <= len(value.encode('utf-8')) <= 72:
            raise ValueError('Password must contain 12..72 UTF-8 bytes')
        return value
class Login(Input):
    email: EmailStr
    password: str = Field(min_length=1, max_length=72)
class Refresh(Input):
    refresh_token: str = Field(min_length=1, max_length=4096)
class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str
class UserView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: str
    role: Role
    is_blocked: bool
class UserPatch(Input):
    role: Role | None = None
    is_blocked: bool | None = None
class MenuWrite(Input):
    name: str = Field(min_length=1, max_length=120)
    price: Decimal = Field(ge=0, max_digits=10, decimal_places=2)
class MenuView(MenuWrite):
    model_config = ConfigDict(from_attributes=True)
    id: int
class OrderCreate(Input):
    item_id: int = Field(gt=0, strict=True)
    quantity: int = Field(ge=1, le=100, strict=True)
class OrderView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    customer_id: int
    item_id: int
    quantity: int
    status: str
class KitchenView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    item_id: int
    quantity: int
    status: str
class DeliveryCreate(Input):
    order_id: int = Field(gt=0, strict=True)
    courier_id: int = Field(gt=0, strict=True)
class DeliveryView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    order_id: int
    customer_id: int
    courier_id: int
    status: str
