"""Thread-safe, versioned four-scope context registry."""
from copy import deepcopy
from threading import RLock
from time import time

SCOPES=('category','merchant','customer','trigger')

class StaleVersionError(ValueError):
    def __init__(self,current_version): self.current_version=current_version

class ContextStore:
    def __init__(self):
        self._lock=RLock();self._items={scope:{} for scope in SCOPES}
    def put(self,scope,context_id,version,payload,delivered_at=None):
        if scope not in SCOPES: raise ValueError('invalid_scope')
        if not context_id or not isinstance(version,int) or version<1 or not isinstance(payload,dict):raise ValueError('invalid_context')
        with self._lock:
            current=self._items[scope].get(context_id)
            if current and version<current['version']:raise StaleVersionError(current['version'])
            if current and version==current['version']:return False
            self._items[scope][context_id]={'version':version,'payload':deepcopy(payload),'delivered_at':delivered_at,'stored_epoch':time()}
            return True
    def get(self,scope,context_id):
        with self._lock:
            item=self._items.get(scope,{}).get(context_id)
            return deepcopy(item['payload']) if item else None
    def record(self,scope,context_id):
        with self._lock:
            item=self._items.get(scope,{}).get(context_id)
            return deepcopy(item) if item else None
    def get_version(self,scope,context_id):
        rec=self.record(scope,context_id);return rec['version'] if rec else None
    def all(self,scope):
        with self._lock:return {k:deepcopy(v['payload']) for k,v in self._items.get(scope,{}).items()}
    def counts(self):
        with self._lock:return {scope:len(self._items[scope]) for scope in SCOPES}
    def total(self):return sum(self.counts().values())
