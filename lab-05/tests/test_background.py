import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timedelta,timezone
import pytest
from sqlalchemy import select,func,event
from sqlalchemy.exc import IntegrityError
from kombu.exceptions import OperationalError
from app.models import JobRow,EffectRow,BonusRow,OrderRow,DeadLetterRow,TaskLogRow,MaintenanceRow
from app.modules.orders.repository import OrderRepository
from app.tasks.execution import TaskExecutor,JobFailure
from app.tasks.dispatch import CeleryDispatcher


def jobs(application):
    factory=application.state.session_factory
    with factory() as db:
        order=OrderRepository(db).create(1,1,2,operations=('pdf','email','sms'))
        values={j.kind:j.id for j in db.scalars(select(JobRow).where(JobRow.order_id==order.id))}
    return order,values


def executor(application,**changes):
    settings=application.state.settings.model_copy(update={
        'simulated_pdf_seconds':0,'simulated_email_seconds':0,'simulated_sms_seconds':0,**changes})
    return TaskExecutor(application.state.session_factory,settings)


def test_order_and_jobs_are_atomic(application):
    factory=application.state.session_factory
    with factory() as db:
        with pytest.raises(IntegrityError):
            OrderRepository(db).create(1,1,2,operations=('pdf','invalid'))
        db.rollback()
        assert db.scalar(select(func.count()).select_from(OrderRow))==0
        assert db.scalar(select(func.count()).select_from(JobRow))==0
        assert db.scalar(select(func.count()).select_from(BonusRow))==0


def test_service_enqueues_durable_jobs_and_bonus(client,headers,application):
    auth=headers()
    r=client.post('/orders/create',json={'item_id':1,'quantity':2},headers=auth)
    assert r.status_code==201
    order_id=r.json()['order_id']
    result=client.get(f'/orders/{order_id}/jobs',headers=auth)
    assert result.status_code==200 and {j['kind'] for j in result.json()}=={'pdf','email','sms'}
    assert all(j['status']=='PENDING' for j in result.json())
    assert client.get(f'/orders/{order_id}/jobs',headers=headers('bob')).status_code==403
    with application.state.session_factory() as db:
        assert db.get(BonusRow,order_id).points==2
    from redis import Redis
    with Redis.from_url(application.state.settings.broker_url) as broker:
        assert broker.llen('sirius05:default')==3


def test_idempotent_even_concurrently(application):
    order,values=jobs(application)
    work=executor(application,simulated_pdf_seconds=.05)
    start=threading.Barrier(2)
    def run(_):
        start.wait(5)
        return work.execute(values['pdf'])
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(run,range(2)))
    assert {r['status'] for r in results}=={'succeeded','skipped'}
    with application.state.session_factory() as db:
        assert db.get(JobRow,values['pdf']).attempts==1
        assert db.scalar(select(func.count()).select_from(EffectRow))==1


def test_crash_before_commit_rolls_back_effect_and_marker(application):
    _,values=jobs(application)
    work=executor(application)
    factory=application.state.session_factory
    first=True
    def failing_factory():
        nonlocal first
        db=factory()
        if first:
            first=False
            def crash(session):
                raise RuntimeError('simulated commit failure')
            event.listen(db,'before_commit',crash,once=True)
        return db
    broken=TaskExecutor(failing_factory,work.settings)
    with pytest.raises(RuntimeError,match='simulated commit failure'):
        broken.execute(values['pdf'])
    with factory() as db:
        assert db.get(JobRow,values['pdf']).attempts==0
        assert db.scalar(select(func.count()).select_from(EffectRow))==0
    assert work.execute(values['pdf'])['status']=='succeeded'


def test_retries_exhaust_and_durable_dlq(application):
    _,values=jobs(application)
    work=executor(application,demo_fail_email_modulo=1)
    for attempt in range(1,5):
        with pytest.raises(JobFailure) as error:
            work.execute(values['email'])
        assert error.value.attempts==attempt and error.value.exhausted==(attempt==4)
    assert work.execute(values['email'])['status']=='skipped'
    with application.state.session_factory() as db:
        assert db.get(DeadLetterRow,values['email']).attempts==4
        assert db.get(JobRow,values['email']).status=='DEAD'
        assert db.scalar(select(func.count()).select_from(EffectRow))==0
        assert db.scalar(select(func.count()).select_from(TaskLogRow))==4


def test_transient_failure_recovers_without_duplicates(application):
    _,values=jobs(application)
    work=executor(application,demo_transient_email_failures=2)
    for _ in range(2):
        with pytest.raises(JobFailure): work.execute(values['email'])
    assert work.execute(values['email'])['attempts']==3
    assert work.execute(values['email'])['status']=='skipped'
    with application.state.session_factory() as db:
        assert db.scalar(select(func.count()).select_from(EffectRow))==1
        assert db.get(DeadLetterRow,values['email']) is None


def test_failed_publish_recovers_from_outbox(application,monkeypatch):
    order,values=jobs(application)
    publisher=CeleryDispatcher(application.state.session_factory,application.state.settings)
    original=publisher.celery.send_task
    def unavailable(*args,**kwargs):
        raise OperationalError('simulated broker outage')
    monkeypatch.setattr(publisher.celery,'send_task',unavailable)
    assert publisher.publish_pending(order.id)==0
    with application.state.session_factory() as db:
        assert all(j.published_at is None for j in db.scalars(select(JobRow)))
    monkeypatch.setattr(publisher.celery,'send_task',original)
    assert publisher.publish_pending(order.id)==3
    assert publisher.publish_pending(order.id)==0


def test_actual_dlq_message_is_published_and_not_consumed(application):
    _,values=jobs(application)
    work=executor(application,demo_fail_email_modulo=1)
    for _ in range(4):
        with pytest.raises(JobFailure):work.execute(values['email'])
    publisher=CeleryDispatcher(application.state.session_factory,application.state.settings)
    assert publisher.publish_dead()==1
    assert publisher.publish_dead()==0
    from redis import Redis
    import json,base64
    with Redis.from_url(application.state.settings.broker_url) as broker:
        assert broker.llen('sirius05:dlq')==1
        message=json.loads(broker.lindex('sirius05:dlq',0))
        body=json.loads(base64.b64decode(message['body']))
        assert body[1]['job_id']==values['email'] and body[1]['attempts']==4
        assert message['headers']['task']=='sirius.dead_letter'


def test_cleanup_keeps_idempotency_and_dlq(application):
    _,values=jobs(application)
    work=executor(application)
    work.execute(values['pdf'])
    with application.state.session_factory() as db:
        db.add(TaskLogRow(job_id=values['pdf'],attempt=0,outcome='OLD',created_at=datetime.now(timezone.utc)-timedelta(days=31)))
        db.commit()
    assert work.cleanup()=={'deleted_logs':1}
    with application.state.session_factory() as db:
        assert db.get(JobRow,values['pdf']).status=='SUCCEEDED'
        assert db.get(EffectRow,values['pdf']) is not None
        assert db.scalar(select(func.count()).select_from(MaintenanceRow))==1
        assert db.scalar(select(func.count()).select_from(TaskLogRow))==1
