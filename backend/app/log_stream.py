"""Admin Dashboard için canlı log yayını.

`structlog` işlemci (processor) zincirine, renderer'dan hemen önce eklenir;
her log olayının event_dict'ini hem son N logu tutan ring buffer'a ekler hem
de bağlı SSE abonelerine (`asyncio.Queue`) anlık olarak dağıtır. Böylece bir
soru sorulduğunda arka planda dönen retrieval/LLM adımları Admin sayfasından
gerçek zamanlı izlenebilir.
"""

from __future__ import annotations

import asyncio
from collections import deque
from typing import Any

_BUFFER: deque[dict[str, Any]] = deque(maxlen=200)
_SUBSCRIBERS: set[asyncio.Queue[dict[str, Any]]] = set()


def capture_log_event(logger: Any, method_name: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    """structlog processor: event_dict'i değiştirmeden buffer'a/abonelere iletir."""
    entry = dict(event_dict)
    _BUFFER.append(entry)
    for queue in _SUBSCRIBERS:
        try:
            queue.put_nowait(entry)
        except asyncio.QueueFull:
            pass
    return event_dict


def recent_logs() -> list[dict[str, Any]]:
    return list(_BUFFER)


def subscribe() -> asyncio.Queue[dict[str, Any]]:
    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=200)
    _SUBSCRIBERS.add(queue)
    return queue


def unsubscribe(queue: asyncio.Queue[dict[str, Any]]) -> None:
    _SUBSCRIBERS.discard(queue)
