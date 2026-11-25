import logging
from datetime import datetime,timedelta,timezone
from sqlalchemy import select,or_
from kombu.exceptions import OperationalError as BrokerError
from redis.exceptions import RedisError
from app.models import JobRow,DeadLetterRow
from app.core.celery_app import build_celery
from app.tasks.execution import TaskExecutor,JobFailure

log=logging.getLogger(__name__)
NAMES={'pdf':'sirius.generate_order_pdf','email':'sirius.send_order_email','sms':'sirius.send_order_sms'}

class CeleryDispatcher:
    def __init__(self, factory, settings):
        self.factory,self.settings=factory,settings
        self.celery=build_celery(settings,producer=True)

    def kick(self, order_id):
        self.publish_pending(order_id)

    def publish_pending(self, order_id=None):
        try:
            count=0
            with self.factory() as db,db.begin():
                query=select(JobRow).where(JobRow.status.in_(['PENDING','RETRYING']),
                    or_(JobRow.published_at.is_(None),JobRow.published_at<datetime.now(timezone.utc)-timedelta(seconds=60)))
                if order_id is not None:
                    query=query.where(JobRow.order_id==order_id)
                jobs=db.scalars(query.order_by(JobRow.created_at,JobRow.id).limit(100).with_for_update(skip_locked=True))
                for job in jobs:
                    self.celery.send_task(NAMES[job.kind],args=[job.id],task_id=job.id,queue='default',retry=False)
                    job.published_at=datetime.now(timezone.utc)
                    count+=1
            self.publish_dead()
            return count
        except (BrokerError,RedisError,OSError):
            log.warning('Broker unavailable; committed jobs remain in PostgreSQL outbox')
            return 0

    def publish_dead(self, job_id=None):
        try:
            count=0
            with self.factory() as db,db.begin():
                query=select(DeadLetterRow).where(DeadLetterRow.published_at.is_(None),DeadLetterRow.redriven_at.is_(None))
                if job_id is not None:
                    query=query.where(DeadLetterRow.job_id==job_id)
                for dead in db.scalars(query.limit(100).with_for_update(skip_locked=True)):
                    # Actual DLQ message. Default workers never consume the dlq queue.
                    self.celery.send_task('sirius.dead_letter',kwargs={'job_id':dead.job_id,'error':dead.error,
                                           'attempts':dead.attempts},queue='dlq',retry=False)
                    dead.published_at=datetime.now(timezone.utc)
                    count+=1
            return count
        except (BrokerError,RedisError,OSError):
            log.warning('DLQ broker unavailable; durable dead-letter record retained')
            return 0

class SyncDispatcher:
    """Only for honest before/after timing of the same three simulated effects."""
    def __init__(self, factory, settings):
        self.factory,self.settings=factory,settings
    def kick(self, order_id):
        with self.factory() as db:
            jobs=list(db.scalars(select(JobRow.id).where(JobRow.order_id==order_id)))
        for job_id in jobs:
            try:
                TaskExecutor(self.factory,self.settings).execute(job_id)
            except JobFailure:
                # Baseline failure stays durable; normal demo benchmarks disable faults.
                log.warning('Synchronous simulated notification failed')
