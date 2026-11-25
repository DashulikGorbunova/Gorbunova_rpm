from app.core.celery_app import celery_app
from app.core.config import Settings
from app.tasks.orders import factory
from app.tasks.execution import TaskExecutor
from app.tasks.dispatch import CeleryDispatcher

@celery_app.task(name='sirius.cleanup_task_logs')
def cleanup_task_logs():
    return TaskExecutor(factory(),Settings()).cleanup()

@celery_app.task(name='sirius.dispatch_outbox')
def dispatch_outbox():
    return {'published':CeleryDispatcher(factory(),Settings()).publish_pending()}
