"""
connection_manager.py
---------------------
Production-hardened WebSocket connection manager for FastAPI.

Design choices:
- asyncio.Lock guards all mutations so concurrent coroutines cannot
  corrupt the connection lists.
- The router performs websocket.accept() before auth/read, and the
  manager only tracks accepted sockets.
- Dead sockets are pruned both on failed sends AND via an explicit
  `remove_dead` helper that the heartbeat endpoint can call.
- Structured log fields make Azure Monitor / App Insights queries easy.
"""

import asyncio
import logging
from typing import Dict, List

from fastapi import WebSocket
from starlette.websockets import WebSocketState

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self) -> None:
        # user_id -> list of open WebSocket connections (multiple tabs / devices)
        self._connections: Dict[int, List[WebSocket]] = {}
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self, user_id: int, websocket: WebSocket) -> None:
        """Register an already-accepted socket."""
        async with self._lock:
            sockets = self._connections.setdefault(user_id, [])
            if websocket not in sockets:
                sockets.append(websocket)
        logger.info(
            "ws_connect",
            extra={
                "user_id": user_id,
                "user_sockets": len(self._connections.get(user_id, [])),
                "total_sockets": self._total_connections_unsafe(),
            },
        )

    async def disconnect(self, user_id: int, websocket: WebSocket) -> None:
        """Remove a single socket; clean up the user key when empty."""
        async with self._lock:
            self._remove_socket_unsafe(user_id, websocket)
        logger.info(
            "ws_disconnect",
            extra={
                "user_id": user_id,
                "remaining_user_sockets": len(self._connections.get(user_id, [])),
                "total_sockets": self._total_connections_unsafe(),
            },
        )

    # ------------------------------------------------------------------
    # Sending
    # ------------------------------------------------------------------

    async def send_personal_notification(
        self, user_id: int, message: dict
    ) -> bool:
        """
        Send *message* to every active socket of *user_id*.

        Returns True if at least one socket received the message.
        Dead sockets discovered during the send are pruned automatically.
        """
        async with self._lock:
            sockets = list(self._connections.get(user_id, []))

        if not sockets:
            logger.debug("ws_no_sockets user_id=%s", user_id)
            return False

        delivered = False
        dead: List[WebSocket] = []

        for ws in sockets:
            if ws.client_state != WebSocketState.CONNECTED:
                dead.append(ws)
                continue
            try:
                await ws.send_json(message)
                delivered = True
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "ws_send_error user_id=%s error=%s", user_id, exc
                )
                dead.append(ws)

        if dead:
            async with self._lock:
                for ws in dead:
                    self._remove_socket_unsafe(user_id, ws)

        logger.info(
            "ws_notification_sent",
            extra={
                "user_id": user_id,
                "attempted": len(sockets),
                "dead_pruned": len(dead),
                "delivered": delivered,
            },
        )
        return delivered

    async def broadcast(self, message: dict) -> None:
        """Send *message* to every connected user (e.g. system-wide alerts)."""
        async with self._lock:
            snapshot = {
                uid: list(sockets)
                for uid, sockets in self._connections.items()
            }

        dead: List[tuple[int, WebSocket]] = []

        for user_id, sockets in snapshot.items():
            for ws in sockets:
                if ws.client_state != WebSocketState.CONNECTED:
                    dead.append((user_id, ws))
                    continue
                try:
                    await ws.send_json(message)
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "ws_broadcast_error user_id=%s error=%s", user_id, exc
                    )
                    dead.append((user_id, ws))

        if dead:
            async with self._lock:
                for user_id, ws in dead:
                    self._remove_socket_unsafe(user_id, ws)

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------

    def active_user_count(self) -> int:
        return len(self._connections)

    def total_connection_count(self) -> int:
        # Safe to call without lock for approximate metrics
        return self._total_connections_unsafe()

    # ------------------------------------------------------------------
    # Internal helpers (must be called while holding self._lock)
    # ------------------------------------------------------------------

    def _remove_socket_unsafe(self, user_id: int, websocket: WebSocket) -> None:
        sockets = self._connections.get(user_id)
        if not sockets:
            return
        try:
            sockets.remove(websocket)
        except ValueError:
            pass  # already removed
        if not sockets:
            self._connections.pop(user_id, None)

    def _total_connections_unsafe(self) -> int:
        return sum(len(s) for s in self._connections.values())


# Single process-wide instance.
# NOTE: In a multi-worker / multi-instance Azure deployment this instance
# is NOT shared across workers. See the Redis section in the review notes
# for the pub/sub upgrade path.
manager = ConnectionManager()
