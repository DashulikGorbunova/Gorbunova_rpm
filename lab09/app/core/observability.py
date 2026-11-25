import os, re, uuid, sys
from contextvars import ContextVar
from time import perf_counter
import structlog
import sentry_sdk
from dotenv import load_dotenv
from opentelemetry import trace, propagate
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from fastapi.responses import JSONResponse
load_dotenv()
correlation = ContextVar('correlation_id', default='unknown')
def setup(service):
    structlog.configure(processors=[structlog.processors.TimeStamper(fmt='iso',utc=True),structlog.processors.add_log_level,structlog.processors.EventRenamer('message'),structlog.processors.JSONRenderer()],logger_factory=structlog.PrintLoggerFactory(file=sys.stdout))
    if os.getenv('SENTRY_DSN') and service=='monolith':
        sentry_sdk.init(dsn=os.environ['SENTRY_DSN'],send_default_pii=False)
    if os.getenv('OTEL_EXPORTER_OTLP_ENDPOINT') and not isinstance(trace.get_tracer_provider(),TracerProvider):
        provider=TracerProvider(resource=Resource.create({'service.name':service}))
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(insecure=True)))
        trace.set_tracer_provider(provider)
def log(service,event,**fields):
    structlog.get_logger().info(event,service=service,correlation_id=correlation.get(),**fields)
def context_fields():
    carrier={}
    propagate.inject(carrier)
    return {'correlation_id':correlation.get(),'trace_headers':carrier}
async def middleware(request,call_next):
    value=request.headers.get('X-Correlation-ID','')
    cid=value if re.fullmatch(r'[A-Za-z0-9_.-]{1,128}',value) else str(uuid.uuid4())
    token=correlation.set(cid)
    request.state.correlation_id=cid
    start=perf_counter()
    try:
        with sentry_sdk.new_scope() as scope:
            scope.set_tag('correlation_id',cid)
            try:
                response=await call_next(request)
            except Exception as exc:
                sentry_sdk.capture_exception(exc)
                log('monolith','request_failed',path=request.url.path)
                response=JSONResponse({'detail':'Internal server error'},status_code=500)
        response.headers['X-Correlation-ID']=cid
        log('monolith','http_request',method=request.method,path=request.url.path,status=response.status_code,duration_ms=round((perf_counter()-start)*1000,2))
        return response
    finally:
        correlation.reset(token)
