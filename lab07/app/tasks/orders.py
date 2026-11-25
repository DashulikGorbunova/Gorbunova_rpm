from functools import lru_cache
from app.core.celery_app import celery_app
from app.core.config import Settings
from app.database import make_session_factory
from app.tasks.execution import TaskExecutor,JobFailure
from app.tasks.dispatch import CeleryDispatcher

@lru_cache
def factory():
    # First used in the worker child, never a shared prefork connection.
    return make_session_factory(Settings().database_url)

def perform(task, job_id, kind):
    settings=Settings()
    try:
        return TaskExecutor(factory(),settings).execute(job_id,kind)
    except JobFailure as error:
        if error.exhausted:
            CeleryDispatcher(factory(),settings).publish_dead(job_id)
            raise RuntimeError('Retries exhausted; job retained in DLQ') from None
        raise task.retry(exc=RuntimeError('Simulated provider temporarily unavailable'),
                         countdown=min(600,settings.retry_base_seconds*2**(error.attempts-1)),max_retries=3)

@celery_app.task(bind=True,name='sirius.generate_order_pdf',max_retries=3)
def generate_order_pdf(self,job_id):
    return perform(self,job_id,'pdf')

@celery_app.task(bind=True,name='sirius.send_order_email',max_retries=3)
def send_order_email(self,job_id):
    return perform(self,job_id,'email')

@celery_app.task(bind=True,name='sirius.send_order_sms',max_retries=3)
def send_order_sms(self,job_id):
    return perform(self,job_id,'sms')
