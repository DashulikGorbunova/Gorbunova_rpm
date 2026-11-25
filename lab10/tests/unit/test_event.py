from decimal import Decimal
import pytest
from app.core.order_event import order_paid,validate_paid
def test_event():
    event=order_paid(42,7,Decimal('300.00'))
    assert event['order_id']==42
    assert event['total']==event['amount']=='300.00'
    assert event['currency']=='RUB'
    assert validate_paid(event)==event
def test_missing_total():
    event=order_paid(42,7,Decimal('300'))
    del event['total']
    with pytest.raises(KeyError):
        validate_paid(event)
