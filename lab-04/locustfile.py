"""Real Bearer authentication is preserved; tokens never enter report files."""
import json
import math
import os
import time
from pathlib import Path
from locust import HttpUser, task, between, events

started=0.0
samples=[]
peak_spawned=0

@events.test_start.add_listener
def start(environment,**kwargs):
    global started
    started=time.monotonic()
    samples.clear()

@events.spawning_complete.add_listener
def spawned(user_count, **kwargs):
    global peak_spawned
    peak_spawned=max(peak_spawned,user_count)

@events.request.add_listener
def record(request_type,name,response_time,response_length,exception,**kwargs):
    if name=='/menu/items':
        samples.append((time.monotonic()-started,response_time,exception is not None))

@events.quitting.add_listener
def finish(environment,**kwargs):
    duration=time.monotonic()-started
    steady_start=float(os.getenv('BENCH_STEADY_START','50'))
    steady_end=float(os.getenv('BENCH_STEADY_END','85'))
    values=[ms for elapsed,ms,failed in samples if steady_start<=elapsed<steady_end]
    elapsed=max(.001,min(duration,steady_end)-steady_start)
    values.sort()
    stats=environment.stats.total
    result={'full_rps':stats.total_rps,'full_mean_ms':stats.avg_response_time,
            'full_p95_ms':stats.get_response_time_percentile(.95),
            'full_requests':stats.num_requests,'full_failures':stats.num_failures,
            'steady_end_seconds':steady_end,'duration_seconds':duration,'steady_start_seconds':steady_start,
            'steady_seconds':elapsed,'steady_requests':len(values),
            'steady_rps':len(values)/elapsed,
            'steady_mean_ms':sum(values)/len(values) if values else None,
            'steady_p95_ms':values[math.ceil(.95*len(values))-1] if values else None,
            'failures':sum(failed for _,_,failed in samples),'total_requests':len(samples),
            'peak_spawned_users':peak_spawned,
            'configured_users':environment.parsed_options.num_users}
    target=os.getenv('BENCH_RESULT')
    if target:
        Path(target).write_text(json.dumps(result,indent=2)+'\n')

class MenuUser(HttpUser):
    wait_time=between(.1,.5)
    def on_start(self):
        self.client.headers['Authorization']='Bearer '+os.environ['BENCHMARK_TOKEN']
    @task
    def get_menu(self):
        self.client.get('/menu/items',name='/menu/items')
