"""Consumer runner with durable queues, DB idempotency, ack and DLQ."""
import asyncio
from app.core.observability import setup, correlation, log
from opentelemetry import trace, propagate
from opentelemetry.trace import SpanKind
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
    setup(name)
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
            headers=message.headers or {}
            token=correlation.set(str(headers.get('X-Correlation-ID','unknown')))
            parent=propagate.extract({k:v for k,v in headers.items() if isinstance(v,str)})
            try:
                payload=parse_event(message.body,event_type)
                with trace.get_tracer(__name__).start_as_current_span(name+'.consume',context=parent,kind=SpanKind.CONSUMER) as span:
                    span.set_attribute('order.id',payload['order_id'])
                    with factory() as db:
                        result=(handler(db,payload,fail=settings.demo_no_courier)
                                if name=='delivery' else handler(db,payload))
                    log(name,'order_received',order_id=payload['order_id'],new=result)
                await message.ack()
            except (ValueError,TypeError,KeyError,UnicodeDecodeError) as exc:
                log(name,'invalid_message_dlq',error_type=type(exc).__name__)
                await message.reject(requeue=False)
            except Exception:
                log(name,'consumer_failure')
                await message.reject(requeue=True)
            finally:
                correlation.reset(token)
        await queue.consume(handle,no_ack=False)
        log(name,'consumer_listening')
        await asyncio.Future()
    finally:
        await conn.close()
        factory.kw['bind'].dispose()
