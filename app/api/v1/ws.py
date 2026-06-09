import json

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from jose import JWTError

from app.core.security import decode_token
from app.crud import crud_solicitud
from app.db.session import SessionLocal
from app.services import ruteo
from app.websockets.manager import manager

router = APIRouter()

_UMBRAL_DESVIO_M = 40.0


async def _handle_ubicacion_reciclador(
    reciclador_id: int,
    solicitud_id: int | None,
    lat: float | None,
    lon: float | None,
) -> None:
    if not solicitud_id or lat is None or lon is None:
        return

    db = SessionLocal()
    try:
        solicitud = crud_solicitud.get_by_id(db, solicitud_id)
        if not solicitud:
            return
        if solicitud.reciclador_id != reciclador_id:
            return
        if solicitud.estado != "en_camino":
            return

        destino_lat = solicitud.latitud
        destino_lon = solicitud.longitud

        # Recalcular ruta si no existe o hay desvío mayor al umbral
        ruta_actual = ruteo.obtener_ruta_activa(solicitud_id)
        recalcular = (
            ruta_actual is None
            or ruteo.calcular_desvio_metros(lat, lon, ruta_actual) > _UMBRAL_DESVIO_M
        )

        if recalcular and destino_lat and destino_lon:
            coords, dist_km = ruteo.calcular_ruta(lat, lon, destino_lat, destino_lon)
            if coords:
                ruteo.guardar_ruta_activa(solicitud_id, coords)
                await manager.send_to_user(reciclador_id, {
                    "tipo": "ruta_actualizada",
                    "solicitud_id": solicitud_id,
                    "ruta": [[c[0], c[1]] for c in coords],
                    "distancia_km": round(dist_km, 3),
                    "eta_min": ruteo.calcular_eta_min(dist_km),
                })

        # Siempre notificar posición actual al ciudadano
        if destino_lat and destino_lon:
            dist_rest = ruteo.haversine_km(lat, lon, destino_lat, destino_lon)
            eta_min: int | None = ruteo.calcular_eta_min(dist_rest)
        else:
            eta_min = None

        await manager.send_to_user(solicitud.ciudadano_id, {
            "tipo": "ubicacion_reciclador",
            "solicitud_id": solicitud_id,
            "lat": lat,
            "lon": lon,
            "eta_min": eta_min,
        })
    finally:
        db.close()


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str = Query(..., description="JWT de acceso"),
):
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
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
            except json.JSONDecodeError:
                continue

            if msg.get("tipo") == "ubicacion_reciclador":
                await _handle_ubicacion_reciclador(
                    reciclador_id=user_id,
                    solicitud_id=msg.get("solicitud_id"),
                    lat=msg.get("lat"),
                    lon=msg.get("lon"),
                )
    except WebSocketDisconnect:
        manager.disconnect(user_id)
