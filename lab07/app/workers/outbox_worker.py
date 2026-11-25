"""Confirmed transactional outbox relay with row-level lock."""
import asyncio
import logging
from datetime import datetime, timezone
from sqlalchemy import select
from app.core.config import Settings
from app.core.events import connect, declare_topology, publish_event
from app.database import make_session_factory
from app.models import EventOutboxRow
LOG=logging.getLogger(__name__)

async def relay_one(factory,channel):
    with factory() as db, db.begin():
        row=db.scalar(select(EventOutboxRow).where(EventOutboxRow.published_at.is_(None))
              .order_by(EventOutboxRow.created_at,EventOutboxRow.id)
              .with_for_update(skip_locked=True).limit(1))
        if row is None:
            return False
        await publish_event(channel,row.routing_key,row.payload)
        row.published_at=datetime.now(timezone.utc)
        LOG.info('Published %s %s',row.routing_key,row.id)
    return True

async def main():
    settings=Settings()
    factory=make_session_factory(settings.database_url)
    while True:
        try:
            conn=await connect(settings.rabbitmq_url)
            try:
                channel=await conn.channel(publisher_confirms=True,on_return_raises=True)
                await declare_topology(channel)
                while True:
                    if not await relay_one(factory,channel):
                        await asyncio.sleep(settings.outbox_poll_seconds)
            finally:
                await conn.close()
        except Exception:
            LOG.exception('Outbox broker/database unavailable; retry')
            await asyncio.sleep(settings.outbox_poll_seconds)

if __name__=='__main__':
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
