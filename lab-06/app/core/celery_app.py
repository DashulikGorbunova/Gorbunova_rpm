from celery import Celery
from kombu import Queue, Exchange
from app.core.config import Settings

def build_celery(settings, producer=False):
    app=Celery('sirius_food',broker=settings.broker_url,backend=settings.result_backend,
               include=['app.tasks.orders','app.tasks.maintenance'],set_as_current=False)
    app.conf.update(
        task_serializer='json',result_serializer='json',accept_content=['json'],
        timezone='UTC',enable_utc=True,task_default_queue='default',
        task_queues=(Queue('default',Exchange('default'),routing_key='default'),
                     Queue('dlq',Exchange('dlq'),routing_key='dlq')),
        task_publish_retry=False,broker_connection_timeout=.3,
        broker_transport_options={'global_keyprefix':'sirius06:','visibility_timeout':60,
                                  'socket_connect_timeout':.2,'socket_timeout':.2 if producer else 5,
                                  'retry_on_timeout':False},
        result_backend_transport_options={'global_keyprefix':'sirius06:','visibility_timeout':60},
        visibility_timeout=60,result_expires=3600,
        task_acks_late=True,task_reject_on_worker_lost=True,
        task_acks_on_failure_or_timeout=True,worker_prefetch_multiplier=1,
        worker_send_task_events=True,task_send_sent_event=True,task_track_started=True,
        worker_cancel_long_running_tasks_on_connection_loss=True,
        broker_connection_retry_on_startup=True,task_soft_time_limit=20,task_time_limit=25,
        beat_schedule={
            'cleanup-old-task-logs':{'task':'sirius.cleanup_task_logs','schedule':settings.beat_cleanup_seconds},
            'recover-pending-outbox':{'task':'sirius.dispatch_outbox','schedule':settings.beat_outbox_seconds}},
    )
    return app

celery_app=build_celery(Settings())
