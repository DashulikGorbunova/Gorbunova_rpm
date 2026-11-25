import itertools
import logging
import queue
import threading
import time
from concurrent import futures
from datetime import datetime,timezone
import grpc
import delivery_pb2 as pb
import delivery_pb2_grpc as wire
from app.core.config import Settings
from app.core.jwt import JwtCodec
from app.core.security import passwords,DUMMY_HASH
from app.database import make_session_factory
from app.modules.auth.repository import AuthRepository
from app.modules.auth.service import AuthService
from app.domain.errors import NotFound,AccessDenied,Conflict,InvalidCredentials,InvalidInput
from delivery_service.repository import DeliveryRepository
from delivery_service.service import DeliveryService
from delivery_service.chat import ChatHub

log=logging.getLogger(__name__)

def snapshot(value):
    return pb.Delivery(id=value.id,order_id=value.order_id,customer_id=value.customer_id,
                       courier_id=value.courier_id,status=value.status)

class DeliveryServicer(wire.DeliveryServiceServicer):
    def __init__(self, settings, factory=None):
        self.settings=settings
        self.factory=factory or make_session_factory(settings.database_url)
        self.codec=JwtCodec(settings);self.hub=ChatHub()
    def actor(self, context, db):
        headers=[v for k,v in context.invocation_metadata() if k=='authorization']
        if len(headers)!=1 or not headers[0].startswith('Bearer '):
            raise InvalidCredentials('Bearer required')
        user=AuthService(AuthRepository(db),passwords,self.codec,DUMMY_HASH).authenticate(headers[0][7:])
        db.rollback()  # Release authentication's read connection before business work.
        return user
    def abort(self, context, error):
        codes={NotFound:grpc.StatusCode.NOT_FOUND,AccessDenied:grpc.StatusCode.PERMISSION_DENIED,
               Conflict:grpc.StatusCode.FAILED_PRECONDITION,InvalidCredentials:grpc.StatusCode.UNAUTHENTICATED,
               InvalidInput:grpc.StatusCode.INVALID_ARGUMENT}
        if type(error) not in codes:
            log.exception('Delivery RPC failed',exc_info=error)
        context.abort(codes.get(type(error),grpc.StatusCode.INTERNAL),
                      str(error) if type(error) in codes else 'Delivery service error')
    def execute(self, context, action):
        try:
            with self.factory() as db:
                user=self.actor(context,db)
                return action(DeliveryService(DeliveryRepository(db)),user)
        except Exception as error:
            self.abort(context,error)
    @staticmethod
    def positive(*ids):
        if any(v<=0 for v in ids):raise InvalidInput('Positive identifiers required')
    def AssignCourier(self, request, context):
        log.info("AssignCourier order=%s",request.order_id)
        def action(s,u):
            self.positive(request.order_id,request.courier_id)
            return snapshot(s.assign(request.order_id,request.courier_id,u))
        return self.execute(context,action)
    def CompleteDelivery(self, request, context):
        log.info("CompleteDelivery delivery=%s",request.delivery_id)
        def action(s,u):
            self.positive(request.delivery_id);return snapshot(s.complete(request.delivery_id,u))
        return self.execute(context,action)
    def AdvanceDelivery(self, request, context):
        log.info("AdvanceDelivery delivery=%s",request.delivery_id)
        def action(s,u):
            self.positive(request.delivery_id);return snapshot(s.advance(request.delivery_id,u))
        return self.execute(context,action)
    def GetDelivery(self, request, context):
        log.info("GetDelivery")
        def action(s,u):
            kind=request.WhichOneof('reference')
            if kind is None:raise InvalidInput('Delivery or order id required')
            self.positive(getattr(request,kind))
            return snapshot(s.get(request.delivery_id,u) if kind=='delivery_id' else s.by_order(request.order_id,u))
        return self.execute(context,action)
    def ListDeliveries(self, request, context):
        return self.execute(context,lambda s,u:pb.DeliveryList(deliveries=[snapshot(v) for v in s.list(u)]))
    def TrackDelivery(self, request, context):
        last=None
        stopped=threading.Event();context.add_callback(stopped.set)
        end=time.monotonic()+self.settings.delivery_stream_seconds
        while context.is_active() and time.monotonic()<end:
            def action(s,u):
                self.positive(request.delivery_id);return s.get(request.delivery_id,u)
            value=self.execute(context,action)
            if value.status!=last:
                yield pb.DeliveryStatus(delivery_id=value.id,status=value.status,observed_at=datetime.now(timezone.utc).isoformat())
                last=value.status
            if value.status=='DELIVERED':return
            # Wait without holding a Session/connection; cancellation wakes this sleep.
            if stopped.wait(self.settings.delivery_poll_seconds):return
        if context.is_active():context.abort(grpc.StatusCode.DEADLINE_EXCEEDED,"Stream duration reached")
    def ChatWithCourier(self, request_iterator, context):
        try:first=next(request_iterator)
        except StopIteration:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT,'Join message required')
        def check(s,u):
            self.positive(first.delivery_id);return s.get(first.delivery_id,u)
        self.execute(context,check)
        try:q=self.hub.join(first.delivery_id)
        except Exception as error:self.abort(context,error)
        done=threading.Event();cancelled=threading.Event();errors=queue.Queue()
        context.add_callback(cancelled.set)
        def read_requests():
            try:
                for index,request in enumerate(itertools.chain([first],request_iterator)):
                    if cancelled.is_set():return
                    if index>=100:raise InvalidInput('At most 100 messages per stream')
                    if request.delivery_id!=first.delivery_id:raise AccessDenied('Cannot switch room')
                    if request.sender_id or request.sequence or request.sent_at or request.event:
                        raise InvalidInput('Output fields must be empty')
                    if len(request.text)>1000:raise InvalidInput('Message too long')
                    def publish(s,u):
                        s.get(first.delivery_id,u)
                        if request.text:self.hub.publish(first.delivery_id,request.text,u.id)
                    self.execute_writer(context,publish)
            except Exception as error:
                if not cancelled.is_set():errors.put(error)
            finally:done.set()
        thread=threading.Thread(target=read_requests,daemon=True);thread.start()
        try:
            yield pb.ChatMessage(delivery_id=first.delivery_id,event='joined')
            end=time.monotonic()+self.settings.delivery_stream_seconds
            while context.is_active() and time.monotonic()<end:
                if not errors.empty():self.abort(context,errors.get())
                try:message=q.get(timeout=.1)
                except queue.Empty:
                    if done.is_set() and errors.empty():return
                    continue
                if message is None:context.abort(grpc.StatusCode.RESOURCE_EXHAUSTED,'Slow chat reader')
                self.execute(context,check)  # Revalidate session, role and ownership before disclosure.
                yield message
        finally:
            cancelled.set();self.hub.leave(first.delivery_id,q)
    def execute_writer(self, context, action):
        # Writer errors are forwarded to the response generator, which calls abort.
        with self.factory() as db:
            action(DeliveryService(DeliveryRepository(db)),self.actor(context,db))

def build_server(settings):
    if not settings.delivery_grpc_bind.startswith(('127.0.0.1:','localhost:','[::1]:')):
        raise ValueError('Plaintext demo gRPC must bind loopback; use TLS for remote deployment')
    server=grpc.server(futures.ThreadPoolExecutor(max_workers=32),maximum_concurrent_rpcs=32,
                       options=[('grpc.max_receive_message_length',65536),('grpc.max_send_message_length',65536)])
    servicer=DeliveryServicer(settings)
    wire.add_DeliveryServiceServicer_to_server(servicer,server)
    port=server.add_insecure_port(settings.delivery_grpc_bind)
    if not port:raise RuntimeError('Cannot bind delivery gRPC')
    return server,port
