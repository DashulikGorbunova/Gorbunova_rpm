import queue
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import time
import socket
import grpc
import pytest
from sqlalchemy import event,select
import delivery_pb2 as pb
import delivery_pb2_grpc as wire
from app.models import DeliveryRow,UserRow
from app.modules.orders.repository import OrderRepository
from app.modules.delivery.grpc_client import DeliveryGrpcClient


def order(application):
    with application.state.session_factory() as db:
        return OrderRepository(db).create(1,1,1).id


def assign(client,headers,application):
    order_id=order(application)
    auth=headers('root')
    r=client.post('/delivery/assign',json={'order_id':order_id,'courier_id':4},headers=auth)
    assert r.status_code==201,r.text
    return r.json(),auth

@contextmanager
def rpc(application,auth):
    with grpc.insecure_channel(application.state.settings.delivery_grpc_target) as channel:
        yield wire.DeliveryServiceStub(channel),(('authorization',auth['Authorization']),)


def test_unary_contract_and_legacy_rest(client,headers,application):
    d,admin=assign(client,headers,application)
    with rpc(application,admin) as (stub,md):
        assert stub.GetDelivery(pb.DeliveryLookup(order_id=d['order_id']),metadata=md,timeout=2).id==d['id']
        assert stub.GetDelivery(pb.DeliveryLookup(delivery_id=d['id']),metadata=md,timeout=2).status=='ASSIGNED'
        assert len(stub.ListDeliveries(pb.Empty(),metadata=md,timeout=2).deliveries)==1
    assert client.get('/delivery/order/'+str(d['order_id']),headers=admin).json()==d
    assert client.get('/delivery/'+str(d['id']),headers=admin).json()==d
    assert client.post('/delivery',json={'order_id':d['order_id'],'courier_id':4},headers=admin).status_code==409


def test_no_direct_delivery_sql_in_monolith(client,headers,application):
    queries=[]
    engine=application.state.session_factory.kw['bind']
    def record(conn,cursor,statement,*args):
        if 'deliveries' in statement.lower():queries.append(statement)
    event.listen(engine,'before_cursor_execute',record)
    try:
        d,admin=assign(client,headers,application)
        assert client.get('/delivery/'+str(d['id']),headers=admin).status_code==200
        assert client.get('/delivery',headers=admin).status_code==200
        assert queries==[]
    finally:event.remove(engine,'before_cursor_execute',record)


def test_direct_grpc_requires_real_identity(client,headers,application):
    d,_=assign(client,headers,application)
    alice,bob=headers(),headers('bob')
    with rpc(application,bob) as (stub,md):
        with pytest.raises(grpc.RpcError) as error:
            stub.GetDelivery(pb.DeliveryLookup(delivery_id=d['id']),metadata=md,timeout=2)
        assert error.value.code()==grpc.StatusCode.PERMISSION_DENIED
    with rpc(application,alice) as (stub,md):
        for metadata in ((),(('authorization','Bearer invalid'),)):
            with pytest.raises(grpc.RpcError) as error:
                stub.GetDelivery(pb.DeliveryLookup(delivery_id=d['id']),metadata=metadata,timeout=2)
            assert error.value.code()==grpc.StatusCode.UNAUTHENTICATED
        with pytest.raises(grpc.RpcError) as error:
            stub.AssignCourier(pb.AssignCourierRequest(order_id=d['order_id'],courier_id=4),metadata=md,timeout=2)
        assert error.value.code()==grpc.StatusCode.PERMISSION_DENIED


def test_not_found_and_invalid_identifiers(client,headers,application):
    auth=headers('root')
    assert client.get('/delivery/999999',headers=auth).status_code==404
    for value in (-1,2**80):
        assert client.get('/delivery/'+str(value),headers=auth).status_code==422
    with rpc(application,auth) as (stub,md):
        with pytest.raises(grpc.RpcError) as error:
            stub.GetDelivery(pb.DeliveryLookup(),metadata=md,timeout=2)
        assert error.value.code()==grpc.StatusCode.INVALID_ARGUMENT


def test_unavailable_is_http_503_and_rest_stays_alive(client,headers,application):
    auth=headers()
    sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1];sock.close()
    original=application.state.delivery_channel
    broken=grpc.insecure_channel(f'127.0.0.1:{port}')
    application.state.delivery_channel=broken
    try:
        r=client.get('/delivery/1',headers=auth)
        assert r.status_code==503 and r.json()['detail']=='Delivery service unavailable'
        assert client.get('/menu/items',headers=auth).status_code==200
        assert client.get('/health').status_code==200
    finally:
        application.state.delivery_channel=original;broken.close()


def test_real_deadline_is_http_504(client,headers,application):
    class Slow(wire.DeliveryServiceServicer):
        def GetDelivery(self,request,context):
            time.sleep(.25);return pb.Delivery(id=1)
    server=grpc.server(ThreadPoolExecutor(max_workers=1))
    wire.add_DeliveryServiceServicer_to_server(Slow(),server)
    port=server.add_insecure_port('127.0.0.1:0');server.start()
    old_channel,old_settings=application.state.delivery_channel,application.state.settings
    application.state.delivery_channel=grpc.insecure_channel(f'127.0.0.1:{port}')
    application.state.settings=old_settings.model_copy(update={'delivery_timeout_seconds':.03})
    try:
        r=client.get('/delivery/1',headers=headers())
        assert r.status_code==504 and r.json()['detail']=='Delivery service timeout'
    finally:
        application.state.delivery_channel.close()
        application.state.delivery_channel,application.state.settings=old_channel,old_settings
        server.stop(0).wait()


def test_server_streaming_reads_real_transitions(client,headers,application):
    d,_=assign(client,headers,application)
    alice,rider=headers(),headers('rider')
    with rpc(application,alice) as (stub,md):
        stream=stub.TrackDelivery(pb.DeliveryId(delivery_id=d['id']),metadata=md,timeout=3)
        try:
            assert next(stream).status=='ASSIGNED'
            assert client.post(f"/delivery/{d['id']}/start",headers=rider).json()['status']=='ON_THE_WAY'
            assert next(stream).status=='ON_THE_WAY'
            assert client.post(f"/delivery/{d['id']}/complete",headers=rider).json()['status']=='DELIVERED'
            assert next(stream).status=='DELIVERED'
            with pytest.raises(StopIteration):next(stream)
        finally:stream.cancel()


def test_foreign_streams_rejected(client,headers,application):
    d,_=assign(client,headers,application)
    with rpc(application,headers('bob')) as (stub,md):
        stream=stub.TrackDelivery(pb.DeliveryId(delivery_id=d['id']),metadata=md,timeout=2)
        with pytest.raises(grpc.RpcError) as error:next(stream)
        assert error.value.code()==grpc.StatusCode.PERMISSION_DENIED
        chat=stub.ChatWithCourier(iter([pb.ChatMessage(delivery_id=d['id'])]),metadata=md,timeout=2)
        with pytest.raises(grpc.RpcError) as error:next(chat)
        assert error.value.code()==grpc.StatusCode.PERMISSION_DENIED


class ChatPeer:
    def __init__(self,application,auth,delivery_id):
        self.channel=grpc.insecure_channel(application.state.settings.delivery_grpc_target)
        self.requests=queue.Queue();self.requests.put(pb.ChatMessage(delivery_id=delivery_id))
        def outgoing():
            while True:
                item=self.requests.get()
                if item is None:return
                yield item
        self.call=wire.DeliveryServiceStub(self.channel).ChatWithCourier(outgoing(),metadata=(('authorization',auth['Authorization']),),timeout=5)
        assert next(self.call).event=='joined'
    def close(self):
        self.call.cancel();self.requests.put(None);self.channel.close()


def test_bidi_chat_between_two_actual_clients(client,headers,application):
    d,_=assign(client,headers,application)
    a=ChatPeer(application,headers(),d['id']);b=ChatPeer(application,headers('rider'),d['id'])
    try:
        a.requests.put(pb.ChatMessage(delivery_id=d['id'],text='Where are you?'))
        own,received=next(a.call),next(b.call)
        assert own.text==received.text=='Where are you?' and received.sender_id==1
        b.requests.put(pb.ChatMessage(delivery_id=d['id'],text='On my way'))
        received,own=next(a.call),next(b.call)
        assert received.sender_id==4 and own.text==received.text=='On my way'
    finally:a.close();b.close()


def test_chat_sender_spoofing_is_rejected(client,headers,application):
    d,_=assign(client,headers,application)
    a=ChatPeer(application,headers(),d['id'])
    try:
        a.requests.put(pb.ChatMessage(delivery_id=d['id'],text='spoof',sender_id=4))
        with pytest.raises(grpc.RpcError) as error:next(a.call)
        assert error.value.code()==grpc.StatusCode.INVALID_ARGUMENT
    finally:a.close()


def test_stream_rechecks_blocked_user(client,headers,application):
    d,_=assign(client,headers,application)
    auth=headers()
    with rpc(application,auth) as (stub,md):
        stream=stub.TrackDelivery(pb.DeliveryId(delivery_id=d['id']),metadata=md,timeout=3)
        assert next(stream).status=='ASSIGNED'
        with application.state.session_factory() as db:
            user=db.get(UserRow,1);user.is_blocked=True;db.commit()
        with pytest.raises(grpc.RpcError) as error:next(stream)
        assert error.value.code()==grpc.StatusCode.PERMISSION_DENIED
