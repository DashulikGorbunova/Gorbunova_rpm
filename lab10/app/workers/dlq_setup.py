import asyncio
from app.core.config import Settings
from app.core.events import connect, declare_topology
async def main():
    conn=await connect(Settings().rabbitmq_url)
    try:
        channel=await conn.channel()
        await declare_topology(channel)
        print('RabbitMQ topology and DLQ ready')
    finally:
        await conn.close()
if __name__=='__main__':
    asyncio.run(main())
