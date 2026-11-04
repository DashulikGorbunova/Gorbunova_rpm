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

class CategoryRow(Base):
    __tablename__ = 'menu_categories'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)

class MenuRow(Base):
    __tablename__ = 'menu'
    __table_args__ = (CheckConstraint('price >= 0', name='ck_menu_price'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    price: Mapped[Decimal] = mapped_column(Numeric(10,2))
    category_id: Mapped[int] = mapped_column(ForeignKey('menu_categories.id',name='fk_menu_category'), server_default='1', default=1, index=True)
    category: Mapped[CategoryRow] = relationship(lazy='joined')

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
                     CheckConstraint("status IN ('ASSIGNED','ON_THE_WAY','DELIVERED')", name='ck_delivery_status'))
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey('orders.id'))
    courier_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    status: Mapped[str] = mapped_column(String(20), default='ASSIGNED', server_default='ASSIGNED')

from sqlalchemy import Text, func

class JobRow(Base):
    __tablename__ = 'order_jobs'
    __table_args__ = (UniqueConstraint('order_id','kind',name='uq_order_job_kind'),
                     CheckConstraint("kind IN ('pdf','email','sms')",name='ck_job_kind'),
                     CheckConstraint("status IN ('PENDING','RETRYING','SUCCEEDED','DEAD')",name='ck_job_status'))
    id: Mapped[str] = mapped_column(String(36),primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey('orders.id'),index=True)
    kind: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(12),default='PENDING',server_default='PENDING')
    attempts: Mapped[int] = mapped_column(default=0,server_default='0')
    last_error: Mapped[str | None] = mapped_column(String(100))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),server_default=func.now())

class EffectRow(Base):
    __tablename__ = 'order_effects'
    __table_args__ = (UniqueConstraint('order_id','kind',name='uq_order_effect_kind'),)
    job_id: Mapped[str] = mapped_column(ForeignKey('order_jobs.id'),primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey('orders.id'))
    kind: Mapped[str] = mapped_column(String(10))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),server_default=func.now())

class BonusRow(Base):
    __tablename__ = 'order_bonuses'
    order_id: Mapped[int] = mapped_column(ForeignKey('orders.id'),primary_key=True)
    points: Mapped[int]

class TaskLogRow(Base):
    __tablename__ = 'task_logs'
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[str] = mapped_column(ForeignKey('order_jobs.id'),index=True)
    attempt: Mapped[int]
    outcome: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),server_default=func.now(),index=True)

class DeadLetterRow(Base):
    __tablename__ = 'dead_letters'
    job_id: Mapped[str] = mapped_column(ForeignKey('order_jobs.id'),primary_key=True)
    error: Mapped[str] = mapped_column(String(100))
    attempts: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),server_default=func.now())
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    redriven_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

class MaintenanceRow(Base):
    __tablename__ = 'maintenance_runs'
    id: Mapped[int] = mapped_column(primary_key=True)
    deleted_logs: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),server_default=func.now())
