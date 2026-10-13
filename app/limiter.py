import threading
import time
from pathlib import Path
import redis

class SharedLimiter:
    def __init__(self, url):
        pool = redis.BlockingConnectionPool.from_url(url, decode_responses=True,
            socket_connect_timeout=0.25, socket_timeout=0.25, max_connections=16, timeout=0.25)
        self.client = redis.Redis(connection_pool=pool)
        self.script = self.client.register_script(Path(__file__).with_name('token_bucket.lua').read_text())

    def take(self, key, capacity, refill, cost=1):
        allowed, remaining, retry = self.script(keys=['mtl:' + key], args=[capacity, refill, cost])
        return bool(allowed), int(remaining), int(retry)

class LocalFallback:
    """Small independent per-instance allowance; deliberately not a global quota."""
    def __init__(self):
        self.lock = threading.Lock()
        self.buckets = {}

    def take(self, key):
        now = time.monotonic()
        with self.lock:
            self.buckets = {k: v for k, v in self.buckets.items() if now - v[1] < 60}
            if key not in self.buckets and len(self.buckets) >= 1024:
                return False, 0, 5
            tokens, updated = self.buckets.get(key, (2, now))
            tokens = min(2, tokens + max(0, now - updated) * 0.5)
            allowed = tokens >= 1
            self.buckets[key] = (tokens - 1 if allowed else tokens, now)
            return allowed, int(self.buckets[key][0]), 0 if allowed else 2
