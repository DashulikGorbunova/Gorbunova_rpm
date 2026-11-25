from decimal import Decimal
from sqlalchemy import select
from app.models import OrderRow,PaymentRow,EventOutboxRow,KitchenOrderRow
from app.core.eda import process_kitchen,parse_event
import json
def test_create_and_pay(environment):
    client,app,uid,iid,headers=environment
    response=client.post('/orders/create',json={'item_id':iid,'quantity':2},headers=headers)
    assert response.status_code==201,response.text
    assert response.headers['X-Correlation-ID']=='lab10-test'
    oid=response.json()['order_id']
    with app.state.session_factory() as db:
        order=db.get(OrderRow,oid)
        assert (order.customer_id,order.item_id,order.quantity,order.status)==(uid,iid,2,'PENDING')
    for expected in (False,True):
        response=client.post(f'/orders/{oid}/pay',headers=headers)
        assert response.status_code==200,response.text
        assert response.json()['already_paid'] is expected
    with app.state.session_factory() as db:
        assert db.get(PaymentRow,oid).amount==Decimal('300.00')
        event=db.scalars(select(EventOutboxRow)).one().payload
    payload=parse_event(json.dumps(event),'OrderPaid')
    assert payload['correlation_id']=='lab10-test'
    with app.state.session_factory() as db:
        assert process_kitchen(db,payload)
        assert not process_kitchen(db,payload)
        assert db.get(KitchenOrderRow,oid)
def test_invalid_order(environment):
    client,app,uid,iid,headers=environment
    assert client.post('/orders/create',json={'item_id':iid,'quantity':0},headers=headers).status_code in (409,422)
    assert client.post('/orders/create',json={'item_id':iid,'quantity':1}).status_code==401
    with app.state.session_factory() as db:
        assert db.scalars(select(OrderRow)).all()==[]
