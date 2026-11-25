"""RabbitMQ OrderPaid, Saga and transactional outbox.

Revision ID: 7c0a7e000007
Revises: d44208fc17b9
"""
from alembic import op
import sqlalchemy as sa
revision = '7c0a7e000007'
down_revision = 'd44208fc17b9'
branch_labels = None
depends_on = None

def upgrade():
    op.drop_constraint('ck_order_status','orders',type_='check')
    op.create_check_constraint('ck_order_status','orders',"status IN ('PENDING','PAID','CANCELLED')")
    op.create_table('payments',
        sa.Column('order_id',sa.Integer(),sa.ForeignKey('orders.id'),primary_key=True),
        sa.Column('amount',sa.Numeric(10,2),nullable=False),
        sa.Column('status',sa.String(12),nullable=False),
        sa.Column('refunded_at',sa.DateTime(timezone=True)),
        sa.CheckConstraint('amount >= 0',name='ck_payment_amount'),
        sa.CheckConstraint("status IN ('CAPTURED','REFUNDED')",name='ck_payment_status'))
    op.create_table('event_outbox',
        sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('routing_key',sa.String(100),nullable=False),
        sa.Column('payload',sa.JSON(),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()),
        sa.Column('published_at',sa.DateTime(timezone=True)))
    op.create_index('ix_event_outbox_unpublished','event_outbox',['created_at'],postgresql_where=sa.text('published_at IS NULL'))
    op.create_table('processed_events',
        sa.Column('consumer',sa.String(30),primary_key=True),
        sa.Column('event_id',sa.String(36),primary_key=True),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()))
    op.create_table('kitchen_orders',
        sa.Column('order_id',sa.Integer(),sa.ForeignKey('orders.id'),primary_key=True),
        sa.Column('status',sa.String(20),nullable=False))
    op.create_table('delivery_requests',
        sa.Column('order_id',sa.Integer(),sa.ForeignKey('orders.id'),primary_key=True),
        sa.Column('status',sa.String(20),nullable=False))

def downgrade():
    op.drop_table('delivery_requests')
    op.drop_table('kitchen_orders')
    op.drop_table('processed_events')
    op.drop_index('ix_event_outbox_unpublished',table_name='event_outbox')
    op.drop_table('event_outbox')
    op.drop_table('payments')
    op.execute("UPDATE orders SET status='PENDING' WHERE status='PAID'")
    op.drop_constraint('ck_order_status','orders',type_='check')
    op.create_check_constraint('ck_order_status','orders',"status IN ('PENDING','CANCELLED')")
