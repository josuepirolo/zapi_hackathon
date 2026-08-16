"""Rate limit in-memory (por IP) — protege creditos OpenAI/MCP no chat publico."""

from __future__ import annotations

import threading
import time
from collections import defaultdict

_lock = threading.Lock()
_hits: dict[str, list[float]] = defaultdict(list)


def allow(key: str, *, max_calls: int, window_seconds: int) -> bool:
    """True se ainda dentro do limite; False se excedeu."""
    now = time.monotonic()
    with _lock:
        recent = [t for t in _hits[key] if t > now - window_seconds]
        if len(recent) >= max_calls:
            _hits[key] = recent
            return False
        recent.append(now)
        _hits[key] = recent
        return True
