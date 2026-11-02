from datetime import datetime
from decimal import Decimal
from sqlalchemy import String, ForeignKey, DateTime, Numeric, CheckConstraint, UniqueConstraint, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

class Base(DeclarativeBase):
    pass

class RoleRow(Base):
    __tablename__ = 'roles'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True)

class UserRow(Base):
    __tablename__ = 'users'
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    password_hash: Mapped[str] = mapped_column(String(128))
    role_id: Mapped[int] = mapped_column(ForeignKey('roles.id'))
    is_blocked: Mapped[bool] = mapped_column(default=False, server_default=text('false'))
    role: Mapped[RoleRow] = relationship(lazy='joined')

class SessionRow(Base):
    __tablename__ = 'auth_sessions'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    is_revoked: Mapped[bool] = mapped_column(default=False, server_default=text('false'))

class RefreshRow(Base):
    __tablename__ = 'refresh_tokens'
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey('auth_sessions.id'), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    is_revoked: Mapped[bool] = mapped_column(default=False, server_default=text('false'))

class MenuRow(Base):
    __tablename__ = 'menu'
    __table_args__ = (CheckConstraint('price >= 0', name='ck_menu_price'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    price: Mapped[Decimal] = mapped_column(Numeric(10,2))

class OrderRow(Base):
    __tablename__ = 'orders'
    __table_args__ = (CheckConstraint('quantity > 0 AND quantity <= 100', name='ck_order_quantity'),
                     CheckConstraint("status IN ('PENDING','CANCELLED')", name='ck_order_status'))
    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    item_id: Mapped[int] = mapped_column(ForeignKey('menu.id'))
    quantity: Mapped[int]
    status: Mapped[str] = mapped_column(String(20), default='PENDING', server_default='PENDING')

class DeliveryRow(Base):
    __tablename__ = 'deliveries'
    __table_args__ = (UniqueConstraint('order_id', name='uq_delivery_order'),
                     CheckConstraint("status IN ('ASSIGNED','DELIVERED')", name='ck_delivery_status'))
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey('orders.id'))
    courier_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    status: Mapped[str] = mapped_column(String(20), default='ASSIGNED', server_default='ASSIGNED')
