"""Atomic payment, event handlers and Saga compensation."""
from app.core.observability import context_fields, log
import json
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import select
from app.models import (OrderRow, MenuRow, PaymentRow, EventOutboxRow,
                        KitchenOrderRow, DeliveryRequestRow, ProcessedEventRow, BonusRow)

def pay_order(db, order_id, actor):
    with db.begin():
        order = db.scalar(select(OrderRow).where(OrderRow.id == order_id).with_for_update())
        if order is None:
            raise LookupError('Order not found')
        if order.customer_id != actor.id and actor.role != 'admin':
            raise PermissionError('Access denied')
        if order.status == 'CANCELLED':
            raise ValueError('Cancelled order cannot be paid')
        if order.status == 'PAID':
            return {'order_id': order.id, 'status': 'PAID', 'already_paid': True}
        amount = Decimal(db.get(MenuRow, order.item_id).price) * order.quantity
        db.add(PaymentRow(order_id=order.id, amount=amount, status='CAPTURED'))
        order.status = 'PAID'
        event = dict(event_id=str(uuid.uuid4()), event_type='OrderPaid',
                     order_id=order.id, customer_id=order.customer_id, amount=str(amount))
        event.update(context_fields())
        db.add(EventOutboxRow(id=event['event_id'], routing_key='order.paid', payload=event))
        return {'order_id': order.id, 'status': 'PAID', 'already_paid': False}

def parse_event(raw, expected_type):
    data = json.loads(raw)
    if not isinstance(data, dict) or data.get('event_type') != expected_type:
        raise ValueError('Unexpected event type')
    uuid.UUID(data['event_id'])
    if type(data.get('order_id')) is not int or data['order_id'] <= 0:
        raise ValueError('Invalid order id')
    return data

def process_kitchen(db, data):
    with db.begin():
        key = {'consumer':'kitchen','event_id':data['event_id']}
        if db.get(ProcessedEventRow,key):
            return False
        db.add(ProcessedEventRow(**key))
        if not db.get(KitchenOrderRow,data['order_id']):
            db.add(KitchenOrderRow(order_id=data['order_id'],status='PENDING'))
    return True

def process_delivery(db, data, fail=False):
    with db.begin():
        key = {'consumer':'delivery','event_id':data['event_id']}
        if db.get(ProcessedEventRow,key):
            return False
        db.add(ProcessedEventRow(**key))
        if not db.get(DeliveryRequestRow,data['order_id']):
            db.add(DeliveryRequestRow(order_id=data['order_id'],
                      status='FAILED' if fail else 'PENDING'))
            if fail:
                event = dict(event_id=str(uuid.uuid4()),event_type='DeliveryFailed',
                             order_id=data['order_id'],reason='No available courier')
                event.update(context_fields())
                db.add(EventOutboxRow(id=event['event_id'],
                                     routing_key='delivery.failed',payload=event))
    return True

def compensate(db, data):
    with db.begin():
        key = {'consumer':'compensation','event_id':data['event_id']}
        if db.get(ProcessedEventRow,key):
            return False
        db.add(ProcessedEventRow(**key))
        order = db.scalar(select(OrderRow).where(OrderRow.id==data['order_id']).with_for_update())
        if order is None:
            raise LookupError('Order not found')
        payment = db.scalar(select(PaymentRow).where(PaymentRow.order_id==order.id).with_for_update())
        if payment is None:
            raise ValueError('Payment not found')
        if order.status == 'CANCELLED':
            return False
        if order.status != 'PAID' or payment.status != 'CAPTURED':
            raise ValueError('Not refundable')
        order.status='CANCELLED'
        payment.status='REFUNDED'
        payment.refunded_at=datetime.now(timezone.utc)
        bonus=db.get(BonusRow,order.id)
        if bonus:
            bonus.points=0
        event=dict(event_id=str(uuid.uuid4()), event_type='OrderCancelled',
                   order_id=order.id, customer_id=order.customer_id,
                   reason=data.get('reason','Delivery failed'))
        event.update(context_fields())
        db.add(EventOutboxRow(id=event['event_id'],routing_key='order.cancelled',
                              payload=event))
    return True
