"""Local operator CLI; no public task management or unauthenticated result endpoint."""
import sys
from datetime import datetime,timezone
from sqlalchemy import select
from app.models import JobRow,DeadLetterRow
from app.core.config import Settings
from app.database import make_session_factory
from app.tasks.dispatch import CeleryDispatcher

def main():
    settings=Settings();factory=make_session_factory(settings.database_url)
    command=sys.argv[1:]
    if command==['dlq']:
        with factory() as db:
            for dead in db.scalars(select(DeadLetterRow)):
                print(dead.job_id,dead.error,dead.attempts,'redriven' if dead.redriven_at else 'unresolved')
    elif len(command)==2 and command[0]=='redrive':
        with factory() as db,db.begin():
            job=db.scalar(select(JobRow).where(JobRow.id==command[1]).with_for_update())
            if job is None or job.status!='DEAD':
                raise SystemExit('Only existing DEAD jobs can be redriven')
            dead=db.get(DeadLetterRow,job.id)
            dead.redriven_at=datetime.now(timezone.utc)
            job.status,job.attempts,job.last_error,job.published_at='PENDING',0,None,None
            order_id=job.order_id
        print('Published:',CeleryDispatcher(factory,settings).publish_pending(order_id))
    else:
        raise SystemExit('Usage: python -m app.operations dlq | redrive JOB_UUID')
if __name__=='__main__':
    main()
