from __future__ import annotations

import threading
import time
from collections import deque


class MemoryRateLimiter:
    def __init__(self) -> None:
        self._events: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def hit(self, key: str, *, limit: int, window_seconds: int) -> bool:
        now = time.time()
        with self._lock:
            bucket = self._events.setdefault(key, deque())
            cutoff = now - window_seconds
            while bucket and bucket[0] < cutoff:
                bucket.popleft()
            if len(bucket) >= limit:
                return False
            bucket.append(now)
            return True

    def reset(self, key: str) -> None:
        with self._lock:
            self._events.pop(key, None)


rate_limiter = MemoryRateLimiter()
