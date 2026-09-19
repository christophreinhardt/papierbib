"""Project-local response cache. It stores bibliographic JSON, never API keys."""
from datetime import datetime, timezone, timedelta
import hashlib
import json

from ..persistence.project import atomic_write, json_bytes


class MetadataCache:
    def __init__(self, store, ttl_days=30):
        self.path=store.root/'metadata-cache.json'; self.ttl=timedelta(days=ttl_days)
        self.data={'version':1,'entries':{}}
        try:
            if self.path.exists() and self.path.stat().st_size <= 20*1024*1024:
                loaded=json.loads(self.path.read_text(encoding='utf-8'))
                if loaded.get('version')==1 and isinstance(loaded.get('entries'),dict):self.data=loaded
        except (OSError,ValueError,UnicodeError): pass

    @staticmethod
    def key(provider,query):
        canonical=json.dumps([provider,query],ensure_ascii=False,sort_keys=True,separators=(',',':'))
        return hashlib.sha256(canonical.encode()).hexdigest()

    def get(self,provider,query,offline=False):
        item=self.data['entries'].get(self.key(provider,query))
        if not item:return None
        try: fresh=datetime.fromisoformat(item['at']) >= datetime.now(timezone.utc)-self.ttl
        except (ValueError,TypeError):fresh=False
        return item['records'] if fresh or offline else None

    def put(self,provider,query,records):
        self.data['entries'][self.key(provider,query)]={'at':datetime.now(timezone.utc).isoformat(),'records':records}
        atomic_write(self.path,json_bytes(self.data))
