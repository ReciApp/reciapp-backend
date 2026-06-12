"""Tests para RECI-79: confirmar/liberar solicitudes del día siguiente."""
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.api.v1.dependencies import get_current_user
from app.db.session import get_db
from app.crud import crud_historial, crud_solicitud, crud_user
from app.models.base import Base
from app.schemas.solicitud import SolicitudCreate
from app.schemas.user import UsuarioCreate

MANANA = (date.today() + timedelta(days=1)).isoformat()
PASADO_MANANA = (date.today() + timedelta(days=2)).isoformat()


# ---------------------------------------------------------------------------
# Fixtures: BD SQLite en memoria
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


_dni_counter = iter(range(10000000, 99999999))


def _crear_usuario(db, correo, rol="ciudadano"):
    usuario = crud_user.create_ciudadano(db, UsuarioCreate(
        nombre="Usuario Test", correo=correo, dni=str(next(_dni_counter)),
        celular="999888777", contrasena="secreta123",
    ))
    if rol != "ciudadano":
        usuario.rol = rol
        usuario.estado_validacion = "aprobado"
        db.commit()
        db.refresh(usuario)
    return usuario


def _crear_solicitud(db, ciudadano_id, fecha=MANANA):
    return crud_solicitud.create(db, SolicitudCreate(
        tipo_residuo="plastico", cantidad_kg=2.5, fecha_recoleccion=fecha,
        franja_horaria="manana", direccion="Av. Test 123",
        latitud=-11.86, longitud=-77.07,
    ), ciudadano_id)


@pytest.fixture
def client_reciclador(db):
    reciclador = _crear_usuario(db, "reciclador@test.com", rol="reciclador")
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: reciclador
    yield TestClient(app), reciclador
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# CRUD: get_dia_siguiente
# ---------------------------------------------------------------------------

class TestGetDiaSiguiente:
    def test_solo_devuelve_asignadas_y_confirmadas_de_la_fecha(self, db):
        ciudadano = _crear_usuario(db, "c1@test.com")
        reciclador = _crear_usuario(db, "r1@test.com", rol="reciclador")

        s_asignada = _crear_solicitud(db, ciudadano.id)
        crud_solicitud.asignar(db, s_asignada, reciclador.id)

        s_confirmada = _crear_solicitud(db, ciudadano.id)
        crud_solicitud.asignar(db, s_confirmada, reciclador.id)
        crud_solicitud.marcar_estado(db, s_confirmada, "confirmada", actor_id=reciclador.id)

        s_otra_fecha = _crear_solicitud(db, ciudadano.id, fecha=PASADO_MANANA)
        crud_solicitud.asignar(db, s_otra_fecha, reciclador.id)

        s_pendiente = _crear_solicitud(db, ciudadano.id)  # sin asignar

        resultado = crud_solicitud.get_dia_siguiente(db, reciclador.id, MANANA)
        ids = {s.id for s in resultado}
        assert ids == {s_asignada.id, s_confirmada.id}
        assert s_otra_fecha.id not in ids
        assert s_pendiente.id not in ids

    def test_no_devuelve_solicitudes_de_otro_reciclador(self, db):
        ciudadano = _crear_usuario(db, "c2@test.com")
        reciclador = _crear_usuario(db, "r2@test.com", rol="reciclador")
        otro = _crear_usuario(db, "r3@test.com", rol="reciclador")

        s = _crear_solicitud(db, ciudadano.id)
        crud_solicitud.asignar(db, s, otro.id)

        assert crud_solicitud.get_dia_siguiente(db, reciclador.id, MANANA) == []


# ---------------------------------------------------------------------------
# GET /api/reciclador/dia-siguiente
# ---------------------------------------------------------------------------

class TestPlanDiaSiguiente:
    def test_devuelve_el_plan_de_manana(self, db, client_reciclador):
        client, reciclador = client_reciclador
        ciudadano = _crear_usuario(db, "c4@test.com")
        s = _crear_solicitud(db, ciudadano.id)
        crud_solicitud.asignar(db, s, reciclador.id)

        resp = client.get("/api/reciclador/dia-siguiente")

        assert resp.status_code == 200
        body = resp.json()
        assert [item["id"] for item in body] == [s.id]
        assert body[0]["fecha_recoleccion"] == MANANA


# ---------------------------------------------------------------------------
# PUT /api/reciclador/solicitudes/{id}/confirmar-dia
# ---------------------------------------------------------------------------

class TestConfirmarDia:
    def test_confirma_solicitud_asignada_de_manana(self, db, client_reciclador):
        client, reciclador = client_reciclador
        ciudadano = _crear_usuario(db, "c5@test.com")
        s = _crear_solicitud(db, ciudadano.id)
        crud_solicitud.asignar(db, s, reciclador.id)

        with patch("app.api.v1.reciclador.manager") as mock_manager:
            resp = client.put(f"/api/reciclador/solicitudes/{s.id}/confirmar-dia")

        assert resp.status_code == 200
        assert resp.json()["estado"] == "confirmada"
        historial = crud_historial.get_by_solicitud(db, s.id)
        assert historial[-1].estado_anterior == "asignada"
        assert historial[-1].estado_nuevo == "confirmada"
        assert historial[-1].usuario_id == reciclador.id
        mock_manager.notify_from_thread.assert_called_once()
        destino, payload = mock_manager.notify_from_thread.call_args[0]
        assert destino == ciudadano.id
        assert payload["tipo"] == "solicitud_confirmada"

    def test_rechaza_si_no_es_para_manana(self, db, client_reciclador):
        client, reciclador = client_reciclador
        ciudadano = _crear_usuario(db, "c6@test.com")
        s = _crear_solicitud(db, ciudadano.id, fecha=PASADO_MANANA)
        crud_solicitud.asignar(db, s, reciclador.id)

        resp = client.put(f"/api/reciclador/solicitudes/{s.id}/confirmar-dia")

        assert resp.status_code == 409
        assert "mañana" in resp.json()["detail"]

    def test_rechaza_estado_no_asignada(self, db, client_reciclador):
        client, reciclador = client_reciclador
        ciudadano = _crear_usuario(db, "c7@test.com")
        s = _crear_solicitud(db, ciudadano.id)
        crud_solicitud.asignar(db, s, reciclador.id)
        crud_solicitud.marcar_estado(db, s, "en_camino")

        resp = client.put(f"/api/reciclador/solicitudes/{s.id}/confirmar-dia")
        assert resp.status_code == 409

    def test_rechaza_solicitud_de_otro_reciclador(self, db, client_reciclador):
        client, _ = client_reciclador
        ciudadano = _crear_usuario(db, "c8@test.com")
        otro = _crear_usuario(db, "r9@test.com", rol="reciclador")
        s = _crear_solicitud(db, ciudadano.id)
        crud_solicitud.asignar(db, s, otro.id)

        resp = client.put(f"/api/reciclador/solicitudes/{s.id}/confirmar-dia")
        assert resp.status_code == 403

    def test_404_si_no_existe(self, client_reciclador):
        client, _ = client_reciclador
        resp = client.put("/api/reciclador/solicitudes/9999/confirmar-dia")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# PUT /api/reciclador/solicitudes/{id}/liberar
# ---------------------------------------------------------------------------

class TestLiberar:
    def test_libera_solicitud_confirmada_y_notifica(self, db, client_reciclador):
        client, reciclador = client_reciclador
        ciudadano = _crear_usuario(db, "c10@test.com")
        otro_reciclador = _crear_usuario(db, "r11@test.com", rol="reciclador")
        s = _crear_solicitud(db, ciudadano.id)
        crud_solicitud.asignar(db, s, reciclador.id)
        crud_solicitud.marcar_estado(db, s, "confirmada", actor_id=reciclador.id)

        with patch("app.api.v1.reciclador.manager") as mock_manager:
            resp = client.put(f"/api/reciclador/solicitudes/{s.id}/liberar")

        assert resp.status_code == 200
        body = resp.json()
        assert body["estado"] == "pendiente"
        assert body["reciclador_id"] is None

        historial = crud_historial.get_by_solicitud(db, s.id)
        assert historial[-1].estado_anterior == "confirmada"
        assert historial[-1].estado_nuevo == "pendiente"

        destinos = [c.args[0] for c in mock_manager.notify_from_thread.call_args_list]
        assert ciudadano.id in destinos          # aviso de liberación
        assert otro_reciclador.id in destinos    # vuelve a estar disponible
        assert reciclador.id not in destinos     # no se notifica a sí mismo

    def test_rechaza_liberar_en_camino(self, db, client_reciclador):
        client, reciclador = client_reciclador
        ciudadano = _crear_usuario(db, "c12@test.com")
        s = _crear_solicitud(db, ciudadano.id)
        crud_solicitud.asignar(db, s, reciclador.id)
        crud_solicitud.marcar_estado(db, s, "en_camino")

        resp = client.put(f"/api/reciclador/solicitudes/{s.id}/liberar")
        assert resp.status_code == 409


# ---------------------------------------------------------------------------
# Integración con el flujo existente: confirmada sigue siendo aceptable/optimizable
# ---------------------------------------------------------------------------

class TestEstadoConfirmadaCompatible:
    def test_aceptar_funciona_desde_confirmada(self, db, client_reciclador):
        client, reciclador = client_reciclador
        ciudadano = _crear_usuario(db, "c13@test.com")
        s = _crear_solicitud(db, ciudadano.id)
        crud_solicitud.asignar(db, s, reciclador.id)
        crud_solicitud.marcar_estado(db, s, "confirmada", actor_id=reciclador.id)

        with patch("app.api.v1.solicitudes.manager"):
            resp = client.put(f"/api/solicitudes/{s.id}/aceptar")

        assert resp.status_code == 200
        assert resp.json()["estado"] == "en_camino"

    def test_estados_optimizables_incluyen_confirmada(self):
        from app.api.v1.rutas import ESTADOS_OPTIMIZABLES
        assert "confirmada" in ESTADOS_OPTIMIZABLES
