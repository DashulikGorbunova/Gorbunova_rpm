"""Consumer runner with durable queues, DB idempotency, ack and DLQ."""
import asyncio
import logging
from app.core.config import Settings
from app.core.events import connect, declare_topology
from app.core.eda import parse_event, process_kitchen, process_delivery, compensate
from app.database import make_session_factory
LOG = logging.getLogger(__name__)
HANDLERS={'kitchen':('OrderPaid',process_kitchen),
          'delivery':('OrderPaid',process_delivery),
          'compensation':('DeliveryFailed',compensate)}

async def run(name):
    settings=Settings()
    factory=make_session_factory(settings.database_url)
    conn=await connect(settings.rabbitmq_url)
    try:
        channel=await conn.channel(publisher_confirms=True,on_return_raises=True)
        await channel.set_qos(prefetch_count=10)
        await declare_topology(channel)
        queue=await channel.get_queue(name+'_queue')
        event_type, handler=HANDLERS[name]
        async def handle(message):
            try:
                payload=parse_event(message.body,event_type)
                with factory() as db:
                    result=(handler(db,payload,fail=settings.demo_no_courier)
                            if name=='delivery' else handler(db,payload))
                LOG.info('%s: order %s, new=%s',name,payload['order_id'],result)
                await message.ack()
            except (ValueError,TypeError,KeyError,UnicodeDecodeError) as exc:
                LOG.warning('Bad message in %s, sent to DLQ: %s',name,exc)
                await message.reject(requeue=False)
            except Exception:
                LOG.exception('Transient consumer failure: requeue')
                await message.reject(requeue=True)
        await queue.consume(handle,no_ack=False)
        LOG.info('%s listening',name)
        await asyncio.Future()
    finally:
        await conn.close()
        factory.kw['bind'].dispose()
