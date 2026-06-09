"""E2E real: ciudadano crea solicitud, reciclador la toma y envía GPS,
el ciudadano debe recibir la ubicación en vivo por WebSocket."""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_e2e.db"

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module", autouse=True)
def _restaurar_event_loop():
    """TestClient cierra el event loop del hilo principal; los tests legacy
    (reci37) dependen de asyncio.get_event_loop(), así que lo restauramos."""
    import asyncio
    yield
    asyncio.set_event_loop(asyncio.new_event_loop())


@pytest.fixture(scope="module")
def client():
    if os.path.exists("test_e2e.db"):
        os.remove("test_e2e.db")
    # Importar después de fijar DATABASE_URL
    from app.main import app
    from app.db.session import engine
    from app.models.base import Base

    Base.metadata.create_all(bind=engine)

    with TestClient(app) as c:
        yield c
    if os.path.exists("test_e2e.db"):
        os.remove("test_e2e.db")


def _login(client, correo):
    r = client.post("/auth/login", data={"username": correo, "password": "Password123"})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _recibir_tipo(ws, tipo, max_msgs=5):
    """Recibe mensajes hasta encontrar el del tipo esperado (el orden entre
    ruta_actualizada y ubicacion_reciclador depende de si el grafo cargó)."""
    for _ in range(max_msgs):
        msg = ws.receive_json()
        if msg["tipo"] == tipo:
            return msg
    raise AssertionError(f"No llegó ningún mensaje de tipo '{tipo}'")


def test_tracking_en_vivo_e2e(client):
    # Ciudadano
    r = client.post("/auth/register", json={
        "nombre": "Ciu Test",
        "correo": "ciu@test.com",
        "contrasena": "Password123",
    })
    assert r.status_code == 201, r.text

    # Reciclador
    r = client.post("/auth/register/reciclador", json={
        "nombre": "Rec Test",
        "correo": "rec@test.com",
        "contrasena": "Password123",
        "zona_cobertura": "Puente Piedra",
        "disponibilidad_horaria": "manana",
    })
    assert r.status_code == 201, r.text

    # Activar reciclador directamente en DB (normalmente lo valida el admin)
    from app.db.session import SessionLocal
    from app.models.user import Usuario
    db = SessionLocal()
    rec = db.query(Usuario).filter(Usuario.correo == "rec@test.com").first()
    rec.activo = True
    rec.estado_validacion = "aprobado"
    db.commit()
    db.close()

    token_ciu = _login(client, "ciu@test.com")
    token_rec = _login(client, "rec@test.com")

    # Ciudadano crea solicitud con coordenadas
    r = client.post("/api/solicitudes", json={
        "tipo_residuo": "plastico",
        "cantidad_kg": 3.0,
        "fecha_recoleccion": "2026-06-10",
        "franja_horaria": "manana",
        "direccion": "Calle Falsa 123, Puente Piedra",
        "latitud": -11.871,
        "longitud": -77.071,
    }, headers={"Authorization": f"Bearer {token_ciu}"})
    assert r.status_code == 201, r.text
    sol_id = r.json()["id"]

    # Reciclador la toma (queda en_camino)
    r = client.put(f"/api/solicitudes/{sol_id}/tomar",
                   headers={"Authorization": f"Bearer {token_rec}"})
    assert r.status_code == 200, r.text
    assert r.json()["estado"] == "en_camino"

    # Ambos conectan su WebSocket
    with client.websocket_connect(f"/ws?token={token_ciu}") as ws_ciu, \
         client.websocket_connect(f"/ws?token={token_rec}") as ws_rec:

        ws_rec.send_json({
            "tipo": "ubicacion_reciclador",
            "solicitud_id": sol_id,
            "lat": -11.87,
            "lon": -77.07,
        })

        # El ciudadano recibe la ruta resaltada y la posición en vivo
        msg = _recibir_tipo(ws_ciu, "ruta_actualizada")
        assert len(msg["ruta"]) >= 2
        msg = _recibir_tipo(ws_ciu, "ubicacion_reciclador")
        assert msg["lat"] == -11.87
        assert msg["solicitud_id"] == sol_id

    # Escenario del bug: el ciudadano abre el seguimiento DESPUÉS del último
    # update GPS del reciclador — debe recibir la última ubicación conocida
    # apenas se suscribe, sin esperar a que el reciclador vuelva a moverse.
    with client.websocket_connect(f"/ws?token={token_ciu}") as ws_ciu:
        ws_ciu.send_json({"tipo": "seguir_solicitud", "solicitud_id": sol_id})

        msg = _recibir_tipo(ws_ciu, "ubicacion_reciclador")
        assert msg["lat"] == -11.87
        assert msg["lon"] == -77.07
        assert msg["solicitud_id"] == sol_id


def test_seguir_solicitud_ajena_no_filtra_ubicacion(client):
    """Un usuario que no es el ciudadano de la solicitud no debe recibir nada."""
    import asyncio
    from unittest.mock import AsyncMock, patch

    from app.api.v1.ws import _handle_seguir_solicitud

    with patch("app.api.v1.ws.manager") as mock_manager:
        mock_manager.send_to_user = AsyncMock()
        # user_id 999 no es el ciudadano de la solicitud 1
        asyncio.run(_handle_seguir_solicitud(ciudadano_id=999, solicitud_id=1))

    mock_manager.send_to_user.assert_not_called()
