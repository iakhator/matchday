"""Per-key request limiting.

Deliberately in-process. This gateway is a single container that a
self-hoster runs for their own apps, and an in-memory window needs no
extra infrastructure to keep working. Redis would be the right answer for
a multi-replica deployment; pretending this is that would be worse than
saying plainly what it is.

Two consequences worth knowing, both documented in the README:

  - limits reset when the process restarts
  - limits are per worker, so N uvicorn workers allow N times the
    configured rate

Neither matters for the case this exists to handle: stopping one
misbehaving consumer from starving the others and the sync jobs, which
share this process.
"""

import time
from collections import defaultdict, deque
from typing import Deque, Dict, Optional

WINDOW_SECONDS = 60


class RateLimiter:
    """Sliding window over the last minute, per key.

    Keeps timestamps rather than a counter so the limit cannot be evaded by
    timing requests around a fixed window boundary - a caller limited to 60
    a minute could otherwise send 120 in two seconds by straddling one.
    """

    def __init__(self, window_seconds: int = WINDOW_SECONDS):
        self.window_seconds = window_seconds
        self._hits: Dict[str, Deque[float]] = defaultdict(deque)

    def check(self, key: str, limit: int) -> Optional[int]:
        """Record a request. Returns seconds to wait if over the limit.

        `limit <= 0` means unlimited, which is what the anonymous identity
        used in local development gets.
        """
        if limit <= 0:
            return None

        now = time.monotonic()
        hits = self._hits[key]

        cutoff = now - self.window_seconds
        while hits and hits[0] <= cutoff:
            hits.popleft()

        if len(hits) >= limit:
            # When the oldest request in the window expires, there is room
            # again. Rounded up so a caller obeying Retry-After is not
            # rejected a second time by a fraction of a second.
            retry_after = self.window_seconds - (now - hits[0])
            return max(1, int(retry_after) + 1)

        hits.append(now)
        return None

    def reset(self, key: Optional[str] = None) -> None:
        """Clear history. Exists for tests; nothing in the app calls it."""
        if key is None:
            self._hits.clear()
        else:
            self._hits.pop(key, None)


# One limiter for the process, shared by every request.
limiter = RateLimiter()
