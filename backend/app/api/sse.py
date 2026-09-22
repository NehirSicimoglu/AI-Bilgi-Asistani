"""SSE (Server-Sent Events) formatlama — servisin yapısal event'lerini tel formatına çevirir.

Servis (`ChatService.stream_answer`) transport'tan bağımsız `StreamEvent` üretir;
burada bunlar `text/event-stream` satır formatına serialize edilir:

    event: <ad>
    data: <json>
    <boş satır>

JSON `ensure_ascii=False` ile üretilir (Türkçe karakterler bozulmasın).
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

from app.services.chat import StreamEvent


def format_sse(event: StreamEvent) -> str:
    payload = json.dumps(event.data, ensure_ascii=False)
    return f"event: {event.event}\ndata: {payload}\n\n"


async def sse_stream(events: AsyncIterator[StreamEvent]) -> AsyncIterator[str]:
    async for event in events:
        yield format_sse(event)
