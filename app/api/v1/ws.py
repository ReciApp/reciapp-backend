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
                # No persistir la ruta si el grafo OSM aún está cargando: sería
                # la línea recta de fallback y, sin desvío >40 m que fuerce el
                # recálculo, quedaría pegada aunque el grafo termine de cargar.
                if ruteo.grafo_listo():
                    ruteo.guardar_ruta_activa(solicitud_id, coords)
                msg_ruta = {
                    "tipo": "ruta_actualizada",
                    "solicitud_id": solicitud_id,
                    "ruta": [[c[0], c[1]] for c in coords],
                    "distancia_km": round(dist_km, 3),
                    "eta_min": ruteo.calcular_eta_min(dist_km),
                }
                await manager.send_to_user(reciclador_id, msg_ruta)
                # El ciudadano también ve la ruta resaltada en su mapa
                await manager.send_to_user(solicitud.ciudadano_id, msg_ruta)

        # Siempre notificar posición actual al ciudadano
        if destino_lat and destino_lon:
            dist_rest = ruteo.haversine_km(lat, lon, destino_lat, destino_lon)
            eta_min: int | None = ruteo.calcular_eta_min(dist_rest)
        else:
            eta_min = None

        # Guardar la última posición para poder reenviarla al ciudadano
        # que conecte después de este update (ej: recién abre el seguimiento)
        ruteo.guardar_ubicacion_activa(solicitud_id, lat, lon, eta_min)

        await manager.send_to_user(solicitud.ciudadano_id, {
            "tipo": "ubicacion_reciclador",
            "solicitud_id": solicitud_id,
            "lat": lat,
            "lon": lon,
            "eta_min": eta_min,
        })
    finally:
        db.close()


async def _handle_seguir_solicitud(
    ciudadano_id: int,
    solicitud_id: int | None,
) -> None:
    """El ciudadano abre la página de seguimiento: reenviarle de inmediato
    la última ubicación conocida del reciclador (si existe)."""
    if not solicitud_id:
        return

    db = SessionLocal()
    try:
        solicitud = crud_solicitud.get_by_id(db, solicitud_id)
        if not solicitud:
            return
        if solicitud.ciudadano_id != ciudadano_id:
            return
        if solicitud.estado != "en_camino":
            return

        # Reenviar también la ruta activa para que el mapa la dibuje de inmediato
        ruta = ruteo.obtener_ruta_activa(solicitud_id)
        if ruta:
            dist_km = ruteo.longitud_ruta_km(ruta)
            await manager.send_to_user(ciudadano_id, {
                "tipo": "ruta_actualizada",
                "solicitud_id": solicitud_id,
                "ruta": [[c[0], c[1]] for c in ruta],
                "distancia_km": round(dist_km, 3),
                "eta_min": ruteo.calcular_eta_min(dist_km),
            })

        ubicacion = ruteo.obtener_ubicacion_activa(solicitud_id)
        if ubicacion is None:
            return

        await manager.send_to_user(ciudadano_id, {
            "tipo": "ubicacion_reciclador",
            "solicitud_id": solicitud_id,
            "lat": ubicacion["lat"],
            "lon": ubicacion["lon"],
            "eta_min": ubicacion["eta_min"],
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
            elif msg.get("tipo") == "seguir_solicitud":
                await _handle_seguir_solicitud(
                    ciudadano_id=user_id,
                    solicitud_id=msg.get("solicitud_id"),
                )
    except WebSocketDisconnect:
        manager.disconnect(user_id, websocket)
