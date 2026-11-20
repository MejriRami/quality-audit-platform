import asyncio, logging
from typing import Dict, Set, List, Any

logger = logging.getLogger(__name__)

class SSEConnectionManager:
    def __init__(self, queue_size: int = 200):
        self._connections: Dict[int, Set[asyncio.Queue[dict]]] = {}
        self._lock = asyncio.Lock()
        self._queue_size = queue_size

    async def connect(self, user_id: int) -> asyncio.Queue[dict]:
        q: asyncio.Queue[dict] = asyncio.Queue(maxsize=self._queue_size)
        async with self._lock:
            self._connections.setdefault(user_id, set()).add(q)
        return q

    async def disconnect(self, user_id: int, q: asyncio.Queue[dict]) -> None:
        async with self._lock:
            if user_id in self._connections:
                self._connections[user_id].discard(q)
                if not self._connections[user_id]:
                    del self._connections[user_id]

    async def send_to_user(self, user_id: int, event: dict) -> int:
        """
        event is a dict like:
        {"event": "notification", "data": {...}, "id": 123, ...}
        """
        async with self._lock:
            queues: List[asyncio.Queue[dict]] = list(self._connections.get(user_id, set()))

        sent = 0
        for q in queues:
            try:
                if q.full():
                    try:
                        q.get_nowait()  
                    except Exception:
                        pass
                q.put_nowait(event)  
                sent += 1
            except Exception as e:
                logger.warning("send_to_user failed: %s", e)

        return sent

_sse_manager = SSEConnectionManager()
def get_sse_manager():
    return _sse_manager
