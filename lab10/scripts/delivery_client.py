#!/usr/bin/env python3
"""Interactive monolith-side client. JWT is obtained by login, never a CLI token."""
import argparse
import getpass
import json
from pathlib import Path
import queue
import sys
import threading
from urllib.request import Request,urlopen
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import grpc
import delivery_pb2 as pb
from app.core.config import Settings
from app.modules.delivery.grpc_client import DeliveryGrpcClient

parser=argparse.ArgumentParser()
parser.add_argument('mode',choices=['track','chat']);parser.add_argument('delivery_id',type=int)
parser.add_argument('--email',required=True);parser.add_argument('--api',default='http://127.0.0.1:8000')
args=parser.parse_args()
password=getpass.getpass('Password: ')
request=Request(args.api+'/auth/login',data=json.dumps({'email':args.email,'password':password}).encode(),headers={'Content-Type':'application/json'})
with urlopen(request,timeout=10) as response:token=json.load(response)['access_token']
settings=Settings()
with grpc.insecure_channel(settings.delivery_grpc_target) as channel:
    client=DeliveryGrpcClient(channel,token,settings.delivery_timeout_seconds,settings.delivery_stream_seconds)
    if args.mode=='track':
        for value in client.track(args.delivery_id):print(value.observed_at,value.status,flush=True)
    else:
        outgoing=queue.Queue();outgoing.put(pb.ChatMessage(delivery_id=args.delivery_id))
        def messages():
            while True:
                item=outgoing.get()
                if item is None:return
                yield item
        call=client.chat(messages())
        def read():
            try:
                for message in call:
                    print('[joined]' if message.event=='joined' else f'User {message.sender_id}: {message.text}',flush=True)
            except grpc.RpcError as error:print('Chat ended:',error.code().name,flush=True)
        reader=threading.Thread(target=read,daemon=True);reader.start()
        try:
            while True:
                text=input()
                if text=='/quit':break
                outgoing.put(pb.ChatMessage(delivery_id=args.delivery_id,text=text))
        except (KeyboardInterrupt,EOFError):pass
        finally:outgoing.put(None);call.cancel();reader.join(timeout=2)
