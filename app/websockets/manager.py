import asyncio
from typing import Dict

from fastapi import WebSocket


class ConnectionManager:
    """Gestiona conexiones WebSocket activas keyed por user_id.

    notify_from_thread() es seguro llamarlo desde hilos de background
    (BackgroundTasks, threading.Timer) usando run_coroutine_threadsafe.
    """

    def __init__(self) -> None:
        self._connections: Dict[int, WebSocket] = {}
        self._loop: asyncio.AbstractEventLoop | None = None

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    async def connect(self, user_id: int, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections[user_id] = websocket

    def disconnect(self, user_id: int) -> None:
        self._connections.pop(user_id, None)

    def is_connected(self, user_id: int) -> bool:
        return user_id in self._connections

    async def send_to_user(self, user_id: int, message: dict) -> None:
        ws = self._connections.get(user_id)
        if ws is None:
            return
        try:
            await ws.send_json(message)
        except Exception:
            self.disconnect(user_id)

    def notify_from_thread(self, user_id: int, message: dict) -> None:
        """Envía notificación desde un hilo de background sin bloquear."""
        if not self._loop or not self._loop.is_running():
            return
        if user_id not in self._connections:
            return
        asyncio.run_coroutine_threadsafe(
            self.send_to_user(user_id, message),
            self._loop,
        )


manager = ConnectionManager()
