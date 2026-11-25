"""DB integration test; isolated disposable PostgreSQL DB only."""
import os
import uuid
from decimal import Decimal
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from app.models import (Base,RoleRow,UserRow,CategoryRow,MenuRow,OrderRow,BonusRow,
                        PaymentRow,EventOutboxRow,KitchenOrderRow,DeliveryRequestRow)
from app.core.eda import pay_order,process_kitchen,process_delivery,compensate
from app.domain.entities import User

def test_end_to_end_db():
    url=os.environ.get('EDA_TEST_DATABASE_URL','')
    if not url.endswith('_eda_test'):
        pytest.skip('EDA_TEST_DATABASE_URL must end with _eda_test')
    engine=create_engine(url)
    Base.metadata.create_all(engine)
    with Session(engine) as db, db.begin():
        role=db.scalar(select(RoleRow).where(RoleRow.name=='student'))
        if role is None:
            role=RoleRow(name='student');db.add(role);db.flush()
        user=UserRow(email=f'eda-{uuid.uuid4()}@example.org',
                     password_hash='test-placeholder',role_id=role.id)
        db.add(user);db.flush()
        category=CategoryRow(name=f'EDA-{uuid.uuid4()}')
        db.add(category);db.flush()
        item=MenuRow(name='Soup',price=Decimal('120.50'),category_id=category.id)
        db.add(item);db.flush()
        order=OrderRow(customer_id=user.id,item_id=item.id,quantity=2)
        db.add(order);db.flush()
        db.add(BonusRow(order_id=order.id,points=2))
        uid,oid=user.id,order.id
    actor=User(uid,'example@example.org','student','unused')
    with Session(engine) as db:
        assert pay_order(db,oid,actor)['already_paid'] is False
        assert pay_order(db,oid,actor)['already_paid'] is True
    with Session(engine) as db:
        event=db.scalar(select(EventOutboxRow).where(EventOutboxRow.routing_key=='order.paid',
                        EventOutboxRow.payload['order_id'].as_integer()==oid))
        assert event is not None
        payload=event.payload
    with Session(engine) as db:
        assert process_kitchen(db,payload)
        assert not process_kitchen(db,payload)
        assert process_delivery(db,payload,fail=True)
        assert not process_delivery(db,payload,fail=True)
    with Session(engine) as db:
        failure=db.scalar(select(EventOutboxRow).where(EventOutboxRow.routing_key=='delivery.failed',
                         EventOutboxRow.payload['order_id'].as_integer()==oid))
        assert failure
        failed_event=failure.payload
    with Session(engine) as db:
        assert compensate(db,failed_event)
        assert not compensate(db,failed_event)
    with Session(engine) as db:
        assert db.get(OrderRow,oid).status=='CANCELLED'
        assert db.get(PaymentRow,oid).status=='REFUNDED'
        assert db.get(KitchenOrderRow,oid)
        assert db.get(DeliveryRequestRow,oid).status=='FAILED'
    engine.dispose()
