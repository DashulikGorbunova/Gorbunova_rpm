"""Standalone event validation tests, without broker or DB."""
import json
import uuid
import pytest
from app.core.eda import parse_event

def test_valid_order_paid():
    event={'event_id':str(uuid.uuid4()),'event_type':'OrderPaid','order_id':42}
    assert parse_event(json.dumps(event).encode(),'OrderPaid')==event

@pytest.mark.parametrize('raw',[b'not-json',b'[]',b'{}',
    b'{"event_type":"OrderPaid","event_id":"invalid","order_id":5}'])
def test_poison_event_is_invalid(raw):
    with pytest.raises((ValueError,KeyError,TypeError)):
        parse_event(raw,'OrderPaid')

def test_delivery_failed():
    event={'event_id':str(uuid.uuid4()),'event_type':'DeliveryFailed','order_id':42}
    assert parse_event(json.dumps(event),'DeliveryFailed')['order_id']==42
