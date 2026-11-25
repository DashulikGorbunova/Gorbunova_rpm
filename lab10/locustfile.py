import os
from locust import HttpUser,task,between
class SiriusUser(HttpUser):
    wait_time=between(1,3)
    def on_start(self):
        token=os.environ['LOAD_TOKEN']
        self.item_id=int(os.environ['LOAD_ITEM_ID'])
        self.client.headers.update({'Authorization':'Bearer '+token})
    @task(7)
    def menu(self):
        self.client.get('/menu/items')
    @task(2)
    def item(self):
        self.client.get(f'/menu/items/{self.item_id}',name='/menu/items/:id')
    @task(1)
    def order(self):
        self.client.post('/orders/create',json={'item_id':self.item_id,'quantity':1})
