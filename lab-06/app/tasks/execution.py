"""Durable idempotency for the local simulated provider, not an SMTP guarantee."""
import time
from dataclasses import dataclass
from sqlalchemy import select, delete
from datetime import datetime,timedelta,timezone
from app.models import JobRow,EffectRow,TaskLogRow,DeadLetterRow,MaintenanceRow

@dataclass
class JobFailure(Exception):
    attempts: int
    exhausted: bool

class TaskExecutor:
    def __init__(self, factory, settings):
        self.factory,self.settings=factory,settings

    def execute(self, job_id, expected_kind=None):
        failed=None
        with self.factory() as db,db.begin():
            job=db.scalar(select(JobRow).where(JobRow.id==job_id).with_for_update())
            if job is None:
                return {'status':'missing','job_id':job_id}
            if expected_kind is not None and job.kind!=expected_kind:
                raise ValueError('Job kind mismatch')
            if job.status in {'SUCCEEDED','DEAD'}:
                return {'status':'skipped','job_id':job_id,'state':job.status}
            job.attempts+=1
            attempts=job.attempts
            delay=getattr(self.settings,'simulated_'+job.kind+'_seconds')
            time.sleep(delay)  # Explicit educational simulation, as requested in the assignment.
            modulo=self.settings.demo_fail_email_modulo
            unavailable=(job.kind=='email' and
                         ((modulo>0 and job.order_id%modulo==0) or
                          attempts<=self.settings.demo_transient_email_failures))
            if unavailable:
                job.last_error='SIMULATED_PROVIDER_UNAVAILABLE'
                exhausted=attempts>=4
                job.status='DEAD' if exhausted else 'RETRYING'
                if exhausted:
                    dead=db.get(DeadLetterRow,job.id)
                    if dead is None:
                        db.add(DeadLetterRow(job_id=job.id,error=job.last_error,attempts=attempts))
                    else:
                        dead.error,dead.attempts=job.last_error,attempts
                        dead.published_at,dead.redriven_at=None,None
                db.add(TaskLogRow(job_id=job.id,attempt=attempts,outcome=job.status))
                failed=JobFailure(attempts,exhausted)
            else:
                # The simulated effect and completion flag share the transaction.
                db.add(EffectRow(job_id=job.id,order_id=job.order_id,kind=job.kind,
                                 content=f'SIMULATED {job.kind.upper()} for order {job.order_id}'))
                job.status,job.last_error='SUCCEEDED',None
                db.add(TaskLogRow(job_id=job.id,attempt=attempts,outcome='SUCCEEDED'))
        if failed:
            raise failed
        return {'status':'succeeded','job_id':job_id,'attempts':attempts}

    def cleanup(self):
        with self.factory() as db,db.begin():
            count=db.execute(delete(TaskLogRow).where(TaskLogRow.created_at<datetime.now(timezone.utc)-timedelta(days=30))).rowcount
            db.add(MaintenanceRow(deleted_logs=count))
        return {'deleted_logs':count}
