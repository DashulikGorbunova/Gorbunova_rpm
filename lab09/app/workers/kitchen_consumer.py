import asyncio
import logging
from app.workers.common import run
if __name__=='__main__':
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run('kitchen'))
