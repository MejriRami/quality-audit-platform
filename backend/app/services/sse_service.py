import asyncio
import json
import logging
from typing import Any, Optional

from fastapi import Request
from app.utils.sse_manager import get_sse_manager

logger = logging.getLogger(__name__)

def sse_pack(event: str, data: Any, event_id: Optional[str | int] = None) -> str:
    lines = [f"event: {event}"]
    if event_id is not None:
        lines.append(f"id: {event_id}")

    payload = json.dumps(data, ensure_ascii=False)
    for line in payload.splitlines() or ["{}"]:
        lines.append(f"data: {line}")

    return "\n".join(lines) + "\n\n"

async def generate_sse_stream(request: Request, user_id: int, heartbeat_interval: int = 5):
    sse_manager = get_sse_manager()
    queue = await sse_manager.connect(user_id)

    try:
        # start immediately
        yield sse_pack("connected", {}, None)

        while True:
            if await request.is_disconnected():
                break

            try:
                # wait for event dict or heartbeat timeout
                event = await asyncio.wait_for(queue.get(), timeout=heartbeat_interval)

                # event is dict: {"event": "...", "data": ..., "id": ...}
                yield sse_pack(
                    event=event.get("event", "message"),
                    data=event.get("data", {}),
                    event_id=event.get("id"),
                )

            except asyncio.TimeoutError:
                yield ": keep-alive\n\n"

    except Exception as e:
        logger.exception("SSE stream crashed for user %s: %s", user_id, e)
        raise

    finally:
        await sse_manager.disconnect(user_id, queue)
