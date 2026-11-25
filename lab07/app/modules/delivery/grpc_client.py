"""Infrastructure adapter: generated stub, deadlines and domain error mapping."""
import grpc
import delivery_pb2 as pb
import delivery_pb2_grpc as wire
from app.domain.entities import Delivery
from app.domain.errors import (NotFound,AccessDenied,InvalidCredentials,Conflict,
                               ServiceUnavailable,ServiceTimeout,InvalidInput)

def identifier(value):
    if not 0<value<2**63:
        raise InvalidInput('Positive int64 identifier required')
    return value

def entity(value):
    return Delivery(value.id,value.order_id,value.customer_id,value.courier_id,value.status)

def translate(error):
    errors={grpc.StatusCode.NOT_FOUND:NotFound,grpc.StatusCode.PERMISSION_DENIED:AccessDenied,
            grpc.StatusCode.UNAUTHENTICATED:InvalidCredentials,grpc.StatusCode.ALREADY_EXISTS:Conflict,
            grpc.StatusCode.FAILED_PRECONDITION:Conflict,grpc.StatusCode.INVALID_ARGUMENT:InvalidInput,
            grpc.StatusCode.UNAVAILABLE:ServiceUnavailable,grpc.StatusCode.DEADLINE_EXCEEDED:ServiceTimeout,
            grpc.StatusCode.RESOURCE_EXHAUSTED:ServiceUnavailable}
    error_type=errors.get(error.code(),ServiceUnavailable)
    # Never expose raw server exceptions/tracebacks in the public REST response.
    text={ServiceUnavailable:'Delivery service unavailable',ServiceTimeout:'Delivery service timeout',
          AccessDenied:'Access denied',InvalidCredentials:'Invalid credentials',NotFound:'Delivery not found',
          Conflict:'Delivery state conflict',InvalidInput:'Invalid delivery request'}[error_type]
    raise error_type(text) from None

class DeliveryGrpcClient:
    def __init__(self, channel, token, timeout=5, stream_timeout=30):
        self.stub=wire.DeliveryServiceStub(channel)
        self.metadata=(('authorization','Bearer '+token),)
        self.timeout,self.stream_timeout=timeout,stream_timeout
    def call(self, rpc, request):
        try:
            return rpc(request,metadata=self.metadata,timeout=self.timeout)
        except grpc.RpcError as error:
            translate(error)
    def get(self, delivery_id):
        return entity(self.call(self.stub.GetDelivery,pb.DeliveryLookup(delivery_id=identifier(delivery_id))))
    def by_order(self, order_id):
        return entity(self.call(self.stub.GetDelivery,pb.DeliveryLookup(order_id=identifier(order_id))))
    def list(self):
        return [entity(v) for v in self.call(self.stub.ListDeliveries,pb.Empty()).deliveries]
    def assign(self, order_id, courier_id):
        return entity(self.call(self.stub.AssignCourier,pb.AssignCourierRequest(order_id=identifier(order_id),courier_id=identifier(courier_id))))
    def complete(self, delivery_id):
        return entity(self.call(self.stub.CompleteDelivery,pb.DeliveryId(delivery_id=identifier(delivery_id))))
    def advance(self, delivery_id):
        return entity(self.call(self.stub.AdvanceDelivery,pb.DeliveryId(delivery_id=identifier(delivery_id))))
    def track(self, delivery_id):
        call=self.stub.TrackDelivery(pb.DeliveryId(delivery_id=identifier(delivery_id)),metadata=self.metadata,timeout=self.stream_timeout)
        try:
            yield from call
        except grpc.RpcError as error:
            translate(error)
        finally:
            call.cancel()
    def chat(self, messages):
        # Return the cancellable full-duplex call; CLI and integration use it directly.
        return self.stub.ChatWithCourier(messages,metadata=self.metadata,timeout=self.stream_timeout)
