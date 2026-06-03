"""Tests unitarios para RECI-37: ConnectionManager y notificaciones."""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.websockets.manager import ConnectionManager


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mgr():
    return ConnectionManager()


@pytest.fixture
def event_loop_with_manager(mgr):
    loop = asyncio.new_event_loop()
    mgr.set_loop(loop)
    yield loop, mgr
    loop.close()


# ---------------------------------------------------------------------------
# connect / disconnect
# ---------------------------------------------------------------------------

def test_connect_acepta_websocket_y_registra(mgr):
    ws = AsyncMock()
    asyncio.get_event_loop().run_until_complete(mgr.connect(1, ws))
    ws.accept.assert_called_once()
    assert mgr.is_connected(1)


def test_disconnect_elimina_conexion(mgr):
    ws = AsyncMock()
    asyncio.get_event_loop().run_until_complete(mgr.connect(1, ws))
    mgr.disconnect(1)
    assert not mgr.is_connected(1)


def test_disconnect_usuario_inexistente_no_lanza(mgr):
    mgr.disconnect(999)  # no debe explotar


# ---------------------------------------------------------------------------
# send_to_user
# ---------------------------------------------------------------------------

def test_send_to_user_envia_json(mgr):
    ws = AsyncMock()
    asyncio.get_event_loop().run_until_complete(mgr.connect(1, ws))
    asyncio.get_event_loop().run_until_complete(
        mgr.send_to_user(1, {"tipo": "nueva_solicitud", "solicitud_id": 5})
    )
    ws.send_json.assert_called_once_with({"tipo": "nueva_solicitud", "solicitud_id": 5})


def test_send_to_user_desconectado_no_lanza(mgr):
    asyncio.get_event_loop().run_until_complete(
        mgr.send_to_user(999, {"tipo": "test"})
    )


def test_send_to_user_desconecta_si_falla(mgr):
    ws = AsyncMock()
    ws.send_json.side_effect = RuntimeError("conexión cerrada")
    asyncio.get_event_loop().run_until_complete(mgr.connect(1, ws))
    asyncio.get_event_loop().run_until_complete(mgr.send_to_user(1, {"tipo": "test"}))
    assert not mgr.is_connected(1)


# ---------------------------------------------------------------------------
# notify_from_thread
# ---------------------------------------------------------------------------

def test_notify_sin_loop_no_lanza(mgr):
    mgr._loop = None
    ws = AsyncMock()
    asyncio.get_event_loop().run_until_complete(mgr.connect(1, ws))
    mgr.notify_from_thread(1, {"tipo": "test"})  # no debe lanzar


def test_notify_usuario_no_conectado_no_lanza(event_loop_with_manager):
    loop, mgr = event_loop_with_manager
    mgr.notify_from_thread(999, {"tipo": "test"})  # no debe lanzar


def test_notify_from_thread_encola_coroutine():
    """notify_from_thread debe enviar el mensaje cuando el loop corre en un hilo."""
    import threading
    import time

    mgr = ConnectionManager()
    loop = asyncio.new_event_loop()
    mgr.set_loop(loop)

    # loop corriendo en hilo separado (simula uvicorn)
    t = threading.Thread(target=loop.run_forever, daemon=True)
    t.start()

    ws = AsyncMock()
    future = asyncio.run_coroutine_threadsafe(mgr.connect(1, ws), loop)
    future.result(timeout=1)

    mgr.notify_from_thread(1, {"tipo": "solicitud_asignada", "solicitud_id": 7})
    time.sleep(0.1)

    ws.send_json.assert_called_once_with({"tipo": "solicitud_asignada", "solicitud_id": 7})

    loop.call_soon_threadsafe(loop.stop)
    t.join(timeout=1)


# ---------------------------------------------------------------------------
# notificaciones desde trigger_asignacion
# ---------------------------------------------------------------------------

def test_notificar_asignacion_llama_notify_reciclador_y_ciudadano():
    from app.services.asignacion import _notificar_asignacion

    solicitud_mock = MagicMock()
    solicitud_mock.id = 10
    solicitud_mock.reciclador_id = 42
    solicitud_mock.ciudadano_id = 7
    solicitud_mock.tipo_residuo = "plastico"
    solicitud_mock.cantidad_kg = 3.5
    solicitud_mock.direccion = "Av. Test 123"
    solicitud_mock.fecha_recoleccion = "2026-06-10"
    solicitud_mock.franja_horaria = "manana"
    solicitud_mock.latitud = -12.0
    solicitud_mock.longitud = -77.0

    with (
        patch("app.services.asignacion.SessionLocal") as mock_session,
        patch("app.crud.crud_solicitud.get_by_id", return_value=solicitud_mock),
        patch("app.websockets.manager.manager") as mock_manager,
    ):
        db_instance = MagicMock()
        db_instance.close = MagicMock()
        mock_session.return_value = db_instance

        _notificar_asignacion(10)

    calls = mock_manager.notify_from_thread.call_args_list
    assert len(calls) == 2

    # Primera llamada: al reciclador
    reciclador_call_user_id = calls[0][0][0]
    reciclador_msg = calls[0][0][1]
    assert reciclador_call_user_id == 42
    assert reciclador_msg["tipo"] == "nueva_solicitud"
    assert reciclador_msg["solicitud_id"] == 10

    # Segunda llamada: al ciudadano
    ciudadano_call_user_id = calls[1][0][0]
    ciudadano_msg = calls[1][0][1]
    assert ciudadano_call_user_id == 7
    assert ciudadano_msg["tipo"] == "solicitud_asignada"
    assert ciudadano_msg["reciclador_id"] == 42
