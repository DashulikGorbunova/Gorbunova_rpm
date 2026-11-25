"""Durable RabbitMQ topology and confirmed publishing."""
import json
import aio_pika
from aio_pika import ExchangeType

EXCHANGE = 'sirius_events'
DLX = 'dlx_exchange'

async def connect(url):
    return await aio_pika.connect_robust(url)

async def declare_topology(channel):
    exchange = await channel.declare_exchange(EXCHANGE, ExchangeType.TOPIC, durable=True)
    dlx = await channel.declare_exchange(DLX, ExchangeType.DIRECT, durable=True)
    for name, key in [('kitchen', 'order.paid'), ('delivery', 'order.paid'),
                      ('compensation', 'delivery.failed')]:
        dead = await channel.declare_queue(name + '_dlq', durable=True)
        await dead.bind(dlx, routing_key=name + '.dlq')
        queue = await channel.declare_queue(name + '_queue', durable=True,
            arguments={'x-dead-letter-exchange': DLX,
                       'x-dead-letter-routing-key': name + '.dlq'})
        await queue.bind(exchange, routing_key=key)
    return exchange

async def publish_event(channel, routing_key, payload):
    exchange = await declare_topology(channel)
    message = aio_pika.Message(
        body=json.dumps(payload, ensure_ascii=False).encode('utf8'),
        content_type='application/json',
        message_id=payload['event_id'],
        delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
    )
    await exchange.publish(message, routing_key=routing_key, mandatory=True)
