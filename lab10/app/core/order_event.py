import uuid
from decimal import Decimal
def order_paid(order_id, customer_id, amount):
    return dict(event_id=str(uuid.uuid4()),event_type='OrderPaid',
                order_id=order_id,customer_id=customer_id,
                amount=str(amount),total=str(amount),currency='RUB')
def validate_paid(data):
    if data['currency'] != 'RUB' or Decimal(data['total']) != Decimal(data['amount']):
        raise ValueError('Invalid payment contract')
    if not Decimal(data['total']).is_finite() or Decimal(data['total']) < 0:
        raise ValueError('Invalid total')
    return data
