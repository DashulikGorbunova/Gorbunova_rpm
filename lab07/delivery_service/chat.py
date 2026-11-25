"""Ephemeral live room fan-out for one delivery service process (not an echo bot)."""
import queue
import threading
from datetime import datetime,timezone
import delivery_pb2 as pb
from app.domain.errors import Conflict

class ChatHub:
    def __init__(self):
        self.lock=threading.Lock();self.rooms={};self.sequence=0
    def join(self, delivery_id):
        q=queue.Queue(maxsize=100)
        with self.lock:
            room=self.rooms.setdefault(delivery_id,set())
            if len(room)>=16:raise Conflict('Room full')
            room.add(q)
        return q
    def leave(self, delivery_id, q):
        with self.lock:
            room=self.rooms.get(delivery_id,set());room.discard(q)
            if not room:self.rooms.pop(delivery_id,None)
    def publish(self, delivery_id, text, user_id):
        with self.lock:
            self.sequence+=1
            msg=pb.ChatMessage(delivery_id=delivery_id,text=text,sender_id=user_id,
                 sequence=self.sequence,sent_at=datetime.now(timezone.utc).isoformat(),event='message')
            for q in self.rooms.get(delivery_id,()):
                try:q.put_nowait(msg)
                except queue.Full:
                    # Slow clients are disconnected by the reader's overflow sentinel.
                    try:q.get_nowait()
                    except queue.Empty:pass
                    try:q.put_nowait(None)
                    except queue.Full:pass
