"""Reproduce el flujo en vivo: reciclador envía GPS → ciudadano recibe ubicación."""
import asyncio
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.ws import router
from app.core.security import create_access_token

app = FastAPI()
app.include_router(router)


@pytest.fixture(autouse=True)
def _restaurar_event_loop():
    """TestClient cierra el event loop del hilo principal; los tests legacy
    (reci37) dependen de asyncio.get_event_loop(), así que lo restauramos."""
    yield
    asyncio.set_event_loop(asyncio.new_event_loop())

RECICLADOR_ID = 42
CIUDADANO_ID = 7


def _solicitud_mock():
    s = MagicMock()
    s.id = 10
    s.ciudadano_id = CIUDADANO_ID
    s.reciclador_id = RECICLADOR_ID
    s.estado = "en_camino"
    s.latitud = -11.871
    s.longitud = -77.071
    return s


def test_ciudadano_recibe_ubicacion_en_vivo():
    token_rec = create_access_token({"sub": str(RECICLADOR_ID)})
    token_ciu = create_access_token({"sub": str(CIUDADANO_ID)})

    client = TestClient(app)

    with (
        patch("app.api.v1.ws.SessionLocal", return_value=MagicMock()),
        patch("app.api.v1.ws.crud_solicitud.get_by_id", return_value=_solicitud_mock()),
    ):
        with client.websocket_connect(f"/ws?token={token_ciu}") as ws_ciu, \
             client.websocket_connect(f"/ws?token={token_rec}") as ws_rec:

            ws_rec.send_json({
                "tipo": "ubicacion_reciclador",
                "solicitud_id": 10,
                "lat": -11.87,
                "lon": -77.07,
            })

            # El reciclador primero recibe la ruta calculada
            msg_rec = ws_rec.receive_json()
            assert msg_rec["tipo"] == "ruta_actualizada"

            # El ciudadano recibe la ruta resaltada y la posición en vivo
            msg_ruta = ws_ciu.receive_json()
            assert msg_ruta["tipo"] == "ruta_actualizada"
            assert msg_ruta["solicitud_id"] == 10
            assert len(msg_ruta["ruta"]) >= 2

            msg_ciu = ws_ciu.receive_json()
            assert msg_ciu["tipo"] == "ubicacion_reciclador"
            assert msg_ciu["lat"] == -11.87
            assert msg_ciu["lon"] == -77.07
            assert msg_ciu["solicitud_id"] == 10
