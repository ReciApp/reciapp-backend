from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from jose import JWTError

from app.core.security import decode_token
from app.websockets.manager import manager

router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str = Query(..., description="JWT de acceso"),
):
    """Conexión WebSocket autenticada.

    El cliente se conecta a /ws?token=<jwt>.
    Mensajes entrantes se descartan (keep-alive); todas las notificaciones
    son server-push.
    """
    try:
        payload = decode_token(token)
        raw_id = payload.get("sub")
        if raw_id is None:
            await websocket.close(code=1008)
            return
        user_id = int(raw_id)
    except (JWTError, ValueError):
        await websocket.close(code=1008)
        return

    await manager.connect(user_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(user_id)
