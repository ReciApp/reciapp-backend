"""Tests para RECI-41: endpoints aceptar/rechazar y timeout de reasignación."""
from unittest.mock import MagicMock, patch, call

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.api.v1.dependencies import get_current_user, require_role
from app.db.session import get_db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _solicitud(estado="asignada", reciclador_id=10, ciudadano_id=5, solicitud_id=1):
    s = MagicMock()
    s.id = solicitud_id
    s.estado = estado
    s.reciclador_id = reciclador_id
    s.ciudadano_id = ciudadano_id
    s.numero_seguimiento = "abc-123"
    s.ciudadano_id = ciudadano_id
    s.tipo_residuo = "plastico"
    s.cantidad_kg = 2.0
    s.fecha_recoleccion = "2026-06-15"
    s.franja_horaria = "manana"
    s.direccion = "Av. Test 1"
    s.latitud = -12.0
    s.longitud = -77.0
    s.fecha_asignacion = None
    s.fecha_creacion = None
    s.fecha_actualizacion = None
    return s


def _reciclador(user_id=10):
    u = MagicMock()
    u.id = user_id
    u.rol = "reciclador"
    u.activo = True
    return u


def _ciudadano(user_id=5):
    u = MagicMock()
    u.id = user_id
    u.rol = "ciudadano"
    u.activo = True
    return u


def _override_db():
    return MagicMock()


# ---------------------------------------------------------------------------
# PUT /aceptar
# ---------------------------------------------------------------------------

class TestAceptarSolicitud:
    def _client_as_reciclador(self, reciclador_id=10):
        reciclador = _reciclador(reciclador_id)
        app.dependency_overrides[get_db] = _override_db
        app.dependency_overrides[get_current_user] = lambda: reciclador
        app.dependency_overrides[require_role("reciclador")] = lambda: reciclador
        return TestClient(app)

    def teardown_method(self):
        app.dependency_overrides.clear()

    def test_aceptar_ok_cambia_estado_a_en_camino(self):
        solicitud = _solicitud(estado="asignada", reciclador_id=10)
        en_camino = _solicitud(estado="en_camino", reciclador_id=10)

        with (
            patch("app.api.v1.solicitudes.crud_solicitud.get_by_id", return_value=solicitud),
            patch("app.api.v1.solicitudes.crud_solicitud.marcar_estado", return_value=en_camino) as mock_marcar,
            patch("app.api.v1.solicitudes.manager.notify_from_thread"),
        ):
            client = self._client_as_reciclador(reciclador_id=10)
            resp = client.put("/api/solicitudes/1/aceptar")

        assert resp.status_code == 200
        mock_marcar.assert_called_once()
        args = mock_marcar.call_args[0]
        assert args[2] == "en_camino"

    def test_aceptar_notifica_ciudadano(self):
        solicitud = _solicitud(estado="asignada", reciclador_id=10, ciudadano_id=5)
        en_camino = _solicitud(estado="en_camino", reciclador_id=10, ciudadano_id=5)

        with (
            patch("app.api.v1.solicitudes.crud_solicitud.get_by_id", return_value=solicitud),
            patch("app.api.v1.solicitudes.crud_solicitud.marcar_estado", return_value=en_camino),
            patch("app.api.v1.solicitudes.manager.notify_from_thread") as mock_notify,
        ):
            client = self._client_as_reciclador(reciclador_id=10)
            client.put("/api/solicitudes/1/aceptar")

        mock_notify.assert_called_once()
        user_id, msg = mock_notify.call_args[0]
        assert user_id == 5
        assert msg["tipo"] == "solicitud_en_camino"
        assert msg["solicitud_id"] == 1

    def test_aceptar_403_si_no_es_el_asignado(self):
        solicitud = _solicitud(estado="asignada", reciclador_id=99)  # otro reciclador

        with patch("app.api.v1.solicitudes.crud_solicitud.get_by_id", return_value=solicitud):
            client = self._client_as_reciclador(reciclador_id=10)
            resp = client.put("/api/solicitudes/1/aceptar")

        assert resp.status_code == 403

    def test_aceptar_409_si_estado_no_es_asignada(self):
        solicitud = _solicitud(estado="en_camino", reciclador_id=10)

        with patch("app.api.v1.solicitudes.crud_solicitud.get_by_id", return_value=solicitud):
            client = self._client_as_reciclador(reciclador_id=10)
            resp = client.put("/api/solicitudes/1/aceptar")

        assert resp.status_code == 409

    def test_aceptar_404_solicitud_inexistente(self):
        with patch("app.api.v1.solicitudes.crud_solicitud.get_by_id", return_value=None):
            client = self._client_as_reciclador(reciclador_id=10)
            resp = client.put("/api/solicitudes/999/aceptar")

        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# PUT /rechazar
# ---------------------------------------------------------------------------

class TestRechazarSolicitud:
    def _client_as_reciclador(self, reciclador_id=10):
        reciclador = _reciclador(reciclador_id)
        app.dependency_overrides[get_db] = _override_db
        app.dependency_overrides[get_current_user] = lambda: reciclador
        app.dependency_overrides[require_role("reciclador")] = lambda: reciclador
        return TestClient(app)

    def teardown_method(self):
        app.dependency_overrides.clear()

    def test_rechazar_ok_resetea_asignacion(self):
        solicitud = _solicitud(estado="asignada", reciclador_id=10)
        pendiente = _solicitud(estado="pendiente", reciclador_id=None, ciudadano_id=5)

        with (
            patch("app.api.v1.solicitudes.crud_solicitud.get_by_id", return_value=solicitud),
            patch("app.api.v1.solicitudes.crud_solicitud.resetear_asignacion", return_value=pendiente) as mock_reset,
            patch("app.api.v1.solicitudes.manager.notify_from_thread"),
            patch("app.api.v1.solicitudes.trigger_asignacion"),
        ):
            client = self._client_as_reciclador(reciclador_id=10)
            resp = client.put("/api/solicitudes/1/rechazar")

        assert resp.status_code == 200
        mock_reset.assert_called_once()

    def test_rechazar_notifica_ciudadano_reasignando(self):
        solicitud = _solicitud(estado="asignada", reciclador_id=10, ciudadano_id=5)
        pendiente = _solicitud(estado="pendiente", reciclador_id=None, ciudadano_id=5)

        with (
            patch("app.api.v1.solicitudes.crud_solicitud.get_by_id", return_value=solicitud),
            patch("app.api.v1.solicitudes.crud_solicitud.resetear_asignacion", return_value=pendiente),
            patch("app.api.v1.solicitudes.manager.notify_from_thread") as mock_notify,
            patch("app.api.v1.solicitudes.trigger_asignacion"),
        ):
            client = self._client_as_reciclador(reciclador_id=10)
            client.put("/api/solicitudes/1/rechazar")

        mock_notify.assert_called_once()
        user_id, msg = mock_notify.call_args[0]
        assert user_id == 5
        assert msg["tipo"] == "solicitud_reasignando"

    def test_rechazar_403_si_no_es_el_asignado(self):
        solicitud = _solicitud(estado="asignada", reciclador_id=99)

        with patch("app.api.v1.solicitudes.crud_solicitud.get_by_id", return_value=solicitud):
            client = self._client_as_reciclador(reciclador_id=10)
            resp = client.put("/api/solicitudes/1/rechazar")

        assert resp.status_code == 403

    def test_rechazar_409_si_estado_no_es_asignada(self):
        solicitud = _solicitud(estado="en_camino", reciclador_id=10)

        with patch("app.api.v1.solicitudes.crud_solicitud.get_by_id", return_value=solicitud):
            client = self._client_as_reciclador(reciclador_id=10)
            resp = client.put("/api/solicitudes/1/rechazar")

        assert resp.status_code == 409


# ---------------------------------------------------------------------------
# trigger_timeout_reasignacion
# ---------------------------------------------------------------------------

class TestTimeoutReasignacion:
    def test_no_hace_nada_si_estado_cambio(self):
        from app.services.asignacion import trigger_timeout_reasignacion

        solicitud = _solicitud(estado="en_camino", reciclador_id=10)

        with (
            patch("app.services.asignacion.SessionLocal") as mock_session,
            patch("app.crud.crud_solicitud.get_by_id", return_value=solicitud),
            patch("app.services.asignacion.trigger_asignacion") as mock_trigger,
        ):
            db_inst = MagicMock()
            db_inst.close = MagicMock()
            mock_session.return_value = db_inst

            trigger_timeout_reasignacion(1, reciclador_id_actual=10)

        mock_trigger.assert_not_called()

    def test_no_hace_nada_si_reciclador_cambio(self):
        from app.services.asignacion import trigger_timeout_reasignacion

        solicitud = _solicitud(estado="asignada", reciclador_id=99)  # ya reasignada a otro

        with (
            patch("app.services.asignacion.SessionLocal") as mock_session,
            patch("app.crud.crud_solicitud.get_by_id", return_value=solicitud),
            patch("app.services.asignacion.trigger_asignacion") as mock_trigger,
        ):
            db_inst = MagicMock()
            db_inst.close = MagicMock()
            mock_session.return_value = db_inst

            trigger_timeout_reasignacion(1, reciclador_id_actual=10)

        mock_trigger.assert_not_called()

    def test_reasigna_y_notifica_si_timeout_aplica(self):
        from app.services.asignacion import trigger_timeout_reasignacion

        solicitud = _solicitud(estado="asignada", reciclador_id=10, ciudadano_id=5)

        with (
            patch("app.services.asignacion.SessionLocal") as mock_session,
            patch("app.crud.crud_solicitud.get_by_id", return_value=solicitud),
            patch("app.crud.crud_solicitud.resetear_asignacion") as mock_reset,
            patch("app.websockets.manager.manager") as mock_manager,
            patch("app.services.asignacion.trigger_asignacion") as mock_trigger,
        ):
            db_inst = MagicMock()
            db_inst.close = MagicMock()
            mock_session.return_value = db_inst

            trigger_timeout_reasignacion(1, reciclador_id_actual=10)

        mock_reset.assert_called_once()
        mock_trigger.assert_called_once_with(1, excluir_ids={10})

        notify_calls = mock_manager.notify_from_thread.call_args_list
        assert len(notify_calls) == 1
        assert notify_calls[0][0][0] == 5
        assert notify_calls[0][0][1]["tipo"] == "solicitud_reasignando"
        assert notify_calls[0][0][1]["razon"] == "timeout"
