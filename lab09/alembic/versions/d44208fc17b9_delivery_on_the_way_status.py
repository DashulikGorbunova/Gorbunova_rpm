"""delivery on-the-way status

Revision ID: d44208fc17b9
Revises: ef9451bc3464
Create Date: 2026-11-04 20:44:59.000212

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd44208fc17b9'
down_revision: Union[str, None] = 'ef9451bc3464'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint('ck_delivery_status','deliveries',type_='check')
    op.create_check_constraint('ck_delivery_status','deliveries',
                               "status IN ('ASSIGNED','ON_THE_WAY','DELIVERED')")

def downgrade() -> None:
    op.execute("UPDATE deliveries SET status='ASSIGNED' WHERE status='ON_THE_WAY'")
    op.drop_constraint('ck_delivery_status','deliveries',type_='check')
    op.create_check_constraint('ck_delivery_status','deliveries',
                               "status IN ('ASSIGNED','DELIVERED')")
