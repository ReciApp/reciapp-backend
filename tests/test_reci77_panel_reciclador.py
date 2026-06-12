"""Tests para RECI-77: GET /api/reciclador/solicitudes + tabla SolicitudHistorial."""
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.api.v1.dependencies import get_current_user, require_role
from app.db.session import get_db
from app.crud import crud_historial, crud_solicitud, crud_user
from app.models.base import Base
from app.schemas.solicitud import SolicitudCreate
from app.schemas.user import UsuarioCreate


# ---------------------------------------------------------------------------
# Fixtures: BD SQLite en memoria para probar la trazabilidad real
# ---------------------------------------------------------------------------

@pytest.fixture
def db():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def _crear_ciudadano(db, correo="ciudadano@test.com"):
    return crud_user.create_ciudadano(db, UsuarioCreate(
        nombre="Ciudadano Test", correo=correo, dni="12345678",
        celular="999888777", contrasena="secreta123",
    ))


def _crear_solicitud(db, ciudadano_id):
    return crud_solicitud.create(db, SolicitudCreate(
        tipo_residuo="plastico", cantidad_kg=2.5, fecha_recoleccion="2026-06-15",
        franja_horaria="manana", direccion="Av. Test 123",
        latitud=-11.86, longitud=-77.07,
    ), ciudadano_id)


# ---------------------------------------------------------------------------
# Trazabilidad: cada transición queda registrada en solicitud_historial
# ---------------------------------------------------------------------------

class TestSolicitudHistorial:
    def test_crear_solicitud_registra_transicion_inicial(self, db):
        ciudadano = _crear_ciudadano(db)
        solicitud = _crear_solicitud(db, ciudadano.id)

        historial = crud_historial.get_by_solicitud(db, solicitud.id)
        assert len(historial) == 1
        assert historial[0].estado_anterior is None
        assert historial[0].estado_nuevo == "pendiente"
        assert historial[0].usuario_id == ciudadano.id
        assert historial[0].fecha is not None

    def test_tomar_registra_transicion_con_reciclador(self, db):
        ciudadano = _crear_ciudadano(db)
        solicitud = _crear_solicitud(db, ciudadano.id)

        crud_solicitud.tomar(db, solicitud.id, reciclador_id=ciudadano.id)

        historial = crud_historial.get_by_solicitud(db, solicitud.id)
        assert [h.estado_nuevo for h in historial] == ["pendiente", "en_camino"]
        assert historial[1].estado_anterior == "pendiente"
        assert historial[1].usuario_id == ciudadano.id

    def test_tomar_fallido_no_registra(self, db):
        ciudadano = _crear_ciudadano(db)
        solicitud = _crear_solicitud(db, ciudadano.id)
        crud_solicitud.marcar_estado(db, solicitud, "completada")

        resultado = crud_solicitud.tomar(db, solicitud.id, reciclador_id=99)

        assert resultado is None
        historial = crud_historial.get_by_solicitud(db, solicitud.id)
        assert [h.estado_nuevo for h in historial] == ["pendiente", "completada"]

    def test_flujo_completo_queda_trazado(self, db):
        ciudadano = _crear_ciudadano(db)
        solicitud = _crear_solicitud(db, ciudadano.id)

        crud_solicitud.asignar(db, solicitud, reciclador_id=ciudadano.id)
        crud_solicitud.marcar_estado(db, solicitud, "en_camino", actor_id=ciudadano.id)
        crud_solicitud.marcar_estado(db, solicitud, "pendiente_confirmacion", actor_id=ciudadano.id)
        crud_solicitud.marcar_estado(db, solicitud, "completada", actor_id=ciudadano.id)

        historial = crud_historial.get_by_solicitud(db, solicitud.id)
        assert [(h.estado_anterior, h.estado_nuevo) for h in historial] == [
            (None, "pendiente"),
            ("pendiente", "asignada"),
            ("asignada", "en_camino"),
            ("en_camino", "pendiente_confirmacion"),
            ("pendiente_confirmacion", "completada"),
        ]

    def test_resetear_asignacion_registra_vuelta_a_pendiente(self, db):
        ciudadano = _crear_ciudadano(db)
        solicitud = _crear_solicitud(db, ciudadano.id)
        crud_solicitud.asignar(db, solicitud, reciclador_id=ciudadano.id)

        crud_solicitud.resetear_asignacion(db, solicitud, actor_id=ciudadano.id)

        historial = crud_historial.get_by_solicitud(db, solicitud.id)
        assert historial[-1].estado_anterior == "asignada"
        assert historial[-1].estado_nuevo == "pendiente"
        assert historial[-1].usuario_id == ciudadano.id


# ---------------------------------------------------------------------------
# GET /api/reciclador/solicitudes
# ---------------------------------------------------------------------------

def _solicitud_mock(solicitud_id=1, estado="asignada", reciclador_id=10):
    s = MagicMock()
    s.id = solicitud_id
    s.numero_seguimiento = f"uuid-{solicitud_id}"
    s.ciudadano_id = 5
    s.tipo_residuo = "plastico"
    s.cantidad_kg = 2.0
    s.fecha_recoleccion = "2026-06-15"
    s.franja_horaria = "manana"
    s.direccion = "Av. Test 1"
    s.latitud = -11.86
    s.longitud = -77.07
    s.estado = estado
    s.reciclador_id = reciclador_id
    s.fecha_asignacion = None
    s.fecha_creacion = None
    s.fecha_actualizacion = None
    return s


def _historial_mock(hist_id, solicitud_id, anterior, nuevo, usuario_id=None):
    h = MagicMock()
    h.id = hist_id
    h.solicitud_id = solicitud_id
    h.usuario_id = usuario_id
    h.estado_anterior = anterior
    h.estado_nuevo = nuevo
    h.fecha = datetime(2026, 6, 11, 10, 0, tzinfo=timezone.utc)
    return h


class TestEndpointPanelReciclador:
    def _client_as_reciclador(self, reciclador_id=10):
        reciclador = MagicMock()
        reciclador.id = reciclador_id
        reciclador.rol = "reciclador"
        reciclador.activo = True
        app.dependency_overrides[get_db] = lambda: MagicMock()
        app.dependency_overrides[get_current_user] = lambda: reciclador
        app.dependency_overrides[require_role("reciclador")] = lambda: reciclador
        return TestClient(app)

    def teardown_method(self):
        app.dependency_overrides.clear()

    def test_devuelve_solicitudes_con_historial(self):
        solicitudes = [_solicitud_mock(1), _solicitud_mock(2, estado="en_camino")]
        transiciones = [
            _historial_mock(1, 1, None, "pendiente", usuario_id=5),
            _historial_mock(2, 1, "pendiente", "asignada"),
            _historial_mock(3, 2, None, "pendiente", usuario_id=5),
        ]
        with (
            patch("app.api.v1.reciclador.crud_solicitud.get_by_reciclador_filtrado",
                  return_value=solicitudes),
            patch("app.api.v1.reciclador.crud_historial.get_by_solicitudes",
                  return_value=transiciones),
        ):
            client = self._client_as_reciclador()
            resp = client.get("/api/reciclador/solicitudes")

        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 2
        assert [h["estado_nuevo"] for h in body[0]["historial"]] == ["pendiente", "asignada"]
        assert len(body[1]["historial"]) == 1
        assert body[0]["historial"][0]["fecha"] is not None

    def test_solo_consulta_sus_propias_solicitudes(self):
        with (
            patch("app.api.v1.reciclador.crud_solicitud.get_by_reciclador_filtrado",
                  return_value=[]) as mock_get,
            patch("app.api.v1.reciclador.crud_historial.get_by_solicitudes", return_value=[]),
        ):
            client = self._client_as_reciclador(reciclador_id=42)
            resp = client.get("/api/reciclador/solicitudes")

        assert resp.status_code == 200
        assert mock_get.call_args[0][1] == 42

    def test_filtros_estado_y_fecha_se_propagan(self):
        with (
            patch("app.api.v1.reciclador.crud_solicitud.get_by_reciclador_filtrado",
                  return_value=[]) as mock_get,
            patch("app.api.v1.reciclador.crud_historial.get_by_solicitudes", return_value=[]),
        ):
            client = self._client_as_reciclador()
            resp = client.get("/api/reciclador/solicitudes?estado=asignada&fecha=2026-06-15")

        assert resp.status_code == 200
        assert mock_get.call_args.kwargs == {"estado": "asignada", "fecha": "2026-06-15"}

    def test_fecha_invalida_da_422(self):
        client = self._client_as_reciclador()
        resp = client.get("/api/reciclador/solicitudes?fecha=15-06-2026")
        assert resp.status_code == 422
