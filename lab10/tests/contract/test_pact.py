import json
from decimal import Decimal
from pact import Consumer, Provider
from app.core.order_event import order_paid,validate_paid
from app.core.eda import parse_event
def test_kitchen_message_contract(tmp_path):
    from pact import MessageConsumer
    pact=MessageConsumer('kitchen').has_pact_with(Provider('monolith'),pact_dir=str(tmp_path))
    sample=order_paid(42,7,Decimal('300.00'))
    pact.expects_to_receive('OrderPaid').with_content(sample)
    with pact:
        message=pact.message
        body=message['contents'] if isinstance(message,dict) and 'contents' in message else message
        if isinstance(body,str):
            body=json.loads(body)
        assert parse_event(json.dumps(body),'OrderPaid')['total']=='300.00'
    # Provider verification against generated Pact content, using real factory.
    contract=json.loads(next(tmp_path.glob('*.json')).read_text())
    expected=contract['messages'][0]['contents']
    actual=order_paid(42,7,Decimal('300.00'))
    actual['event_id']=expected['event_id'] # nondeterministic UUID
    assert actual==expected
