"""Conversation state is held for the lifetime of the service process."""
from copy import deepcopy
from threading import RLock
from time import time

class ConversationStore:
    def __init__(self):self._lock=RLock();self._items={};self._sent_keys=set();self._auto_counts={};self._merchant_optouts=set();self._metrics={'requests':0,'success':0,'errors':0,'latency_ms':{}}
    def create(self,conversation_id,**fields):
        with self._lock:
            if conversation_id in self._items:return deepcopy(self._items[conversation_id])
            item={'conversation_id':conversation_id,'messages':[],'turn_number':1,'last_inbound_turn':0,'last_inbound_text':None,'last_transition':None,'next_eligible_at':None,'created_at':time(),'last_activity':time(),'language':'en','intent':'unknown','strategy':'contextual','last_cta':'none','auto_reply_detected':False,'auto_reply_count':0,'message_count':0,'status':'open','suppression_keys':[],'merchant_id':None,'customer_id':None,'scope':'merchant','trigger_id':None};item.update(fields);self._items[conversation_id]=item;return deepcopy(item)
    def get(self,cid):
        with self._lock:return deepcopy(self._items.get(cid))
    def update(self,cid,**fields):
        with self._lock:
            if cid not in self._items:return None
            self._items[cid].update(fields);self._items[cid]['last_activity']=time();return deepcopy(self._items[cid])
    def add_message(self,cid,role,body,**meta):
        with self._lock:
            if cid not in self._items:return None
            self._items[cid]['messages'].append({'role':role,'body':body,'at':time(),**meta});self._items[cid]['message_count']+=1;self._items[cid]['last_activity']=time();return deepcopy(self._items[cid])
    def seen_suppression(self,key):
        with self._lock:return key in self._sent_keys
    def mark_suppression(self,key):
        if key:
            with self._lock:self._sent_keys.add(key)
    def clear_suppression(self,key):
        if key:
            with self._lock:self._sent_keys.discard(key)
    def mark_optout(self,merchant_id):
        if merchant_id:
            with self._lock:self._merchant_optouts.add(str(merchant_id))
    def is_opted_out(self,merchant_id):
        with self._lock:return bool(merchant_id and str(merchant_id) in self._merchant_optouts)
    def auto_count(self,merchant_id,message):
        import hashlib
        digest=hashlib.sha256(' '.join(message.lower().split()).encode()).hexdigest();key=(merchant_id,digest)
        with self._lock:self._auto_counts[key]=self._auto_counts.get(key,0)+1;return self._auto_counts[key]
    def all(self):
        with self._lock:return [deepcopy(v) for v in self._items.values()]
    def metrics(self):
        with self._lock:return deepcopy(self._metrics)
    def record_request(self,route,elapsed_ms,error=False):
        with self._lock:
            self._metrics['requests']+=1;self._metrics['errors' if error else 'success']+=1
            bucket=self._metrics['latency_ms'].setdefault(route,[]);bucket.append(round(elapsed_ms,2));del bucket[:-100]
