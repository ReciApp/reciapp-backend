"""Tests para RECI-59: historial de solicitudes con filtros y exportación CSV."""
import csv
import io

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.api.v1.dependencies import get_current_user
from app.db.session import get_db
from app.crud import crud_solicitud, crud_user
from app.models.base import Base
from app.schemas.solicitud import SolicitudCreate
from app.schemas.user import UsuarioCreate

_dni_counter = iter(range(20000000, 99999999))


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


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


def _crear_solicitud(db, ciudadano_id, tipo="plastico", fecha="2026-06-15", kg=2.5):
    return crud_solicitud.create(db, SolicitudCreate(
        tipo_residuo=tipo, cantidad_kg=kg, fecha_recoleccion=fecha,
        franja_horaria="manana", direccion="Av. Test 123",
        latitud=-11.86, longitud=-77.07,
    ), ciudadano_id)


def _client_como(db, usuario):
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: usuario
    return TestClient(app)


@pytest.fixture(autouse=True)
def _limpiar_overrides():
    yield
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# CRUD: get_historial_filtrado
# ---------------------------------------------------------------------------

class TestCrudHistorialFiltrado:
    def test_filtra_por_estado_tipo_y_rango_de_fechas(self, db):
        c = _crear_usuario(db, "c1@test.com")
        s1 = _crear_solicitud(db, c.id, tipo="plastico", fecha="2026-06-10")
        s2 = _crear_solicitud(db, c.id, tipo="papel", fecha="2026-06-15")
        s3 = _crear_solicitud(db, c.id, tipo="plastico", fecha="2026-06-20")
        crud_solicitud.marcar_estado(db, s3, "completada")

        assert {s.id for s in crud_solicitud.get_historial_filtrado(
            db, ciudadano_id=c.id, tipo_residuo="plastico")} == {s1.id, s3.id}
        assert {s.id for s in crud_solicitud.get_historial_filtrado(
            db, ciudadano_id=c.id, estado="completada")} == {s3.id}
        assert {s.id for s in crud_solicitud.get_historial_filtrado(
            db, ciudadano_id=c.id, desde="2026-06-12", hasta="2026-06-16")} == {s2.id}

    def test_sin_filtros_de_duenio_devuelve_todas(self, db):
        c1 = _crear_usuario(db, "c2@test.com")
        c2 = _crear_usuario(db, "c3@test.com")
        _crear_solicitud(db, c1.id)
        _crear_solicitud(db, c2.id)

        assert len(crud_solicitud.get_historial_filtrado(db)) == 2

    def test_ordena_por_fecha_recoleccion_descendente(self, db):
        c = _crear_usuario(db, "c4@test.com")
        s_vieja = _crear_solicitud(db, c.id, fecha="2026-06-01")
        s_nueva = _crear_solicitud(db, c.id, fecha="2026-06-20")

        resultado = crud_solicitud.get_historial_filtrado(db, ciudadano_id=c.id)
        assert [s.id for s in resultado] == [s_nueva.id, s_vieja.id]


# ---------------------------------------------------------------------------
# GET /api/historial — visibilidad por rol
# ---------------------------------------------------------------------------

class TestHistorialPorRol:
    def test_ciudadano_solo_ve_lo_suyo(self, db):
        c1 = _crear_usuario(db, "c5@test.com")
        c2 = _crear_usuario(db, "c6@test.com")
        mia = _crear_solicitud(db, c1.id)
        _crear_solicitud(db, c2.id)

        client = _client_como(db, c1)
        resp = client.get("/api/historial")

        assert resp.status_code == 200
        assert [s["id"] for s in resp.json()] == [mia.id]

    def test_reciclador_solo_ve_sus_asignadas(self, db):
        c = _crear_usuario(db, "c7@test.com")
        r = _crear_usuario(db, "r1@test.com", rol="reciclador")
        asignada = _crear_solicitud(db, c.id)
        crud_solicitud.asignar(db, asignada, r.id)
        _crear_solicitud(db, c.id)  # sin asignar

        client = _client_como(db, r)
        resp = client.get("/api/historial")

        assert resp.status_code == 200
        assert [s["id"] for s in resp.json()] == [asignada.id]

    def test_admin_ve_todo(self, db):
        c1 = _crear_usuario(db, "c8@test.com")
        c2 = _crear_usuario(db, "c9@test.com")
        admin = _crear_usuario(db, "admin@test.com", rol="admin")
        _crear_solicitud(db, c1.id)
        _crear_solicitud(db, c2.id)

        client = _client_como(db, admin)
        resp = client.get("/api/historial")

        assert resp.status_code == 200
        assert len(resp.json()) == 2

    def test_filtros_combinados_en_endpoint(self, db):
        c = _crear_usuario(db, "c10@test.com")
        objetivo = _crear_solicitud(db, c.id, tipo="vidrio", fecha="2026-06-15")
        _crear_solicitud(db, c.id, tipo="vidrio", fecha="2026-07-01")
        _crear_solicitud(db, c.id, tipo="papel", fecha="2026-06-15")

        client = _client_como(db, c)
        resp = client.get(
            "/api/historial?tipo_residuo=vidrio&desde=2026-06-01&hasta=2026-06-30")

        assert resp.status_code == 200
        assert [s["id"] for s in resp.json()] == [objetivo.id]

    def test_fecha_invalida_da_422(self, db):
        c = _crear_usuario(db, "c11@test.com")
        client = _client_como(db, c)
        assert client.get("/api/historial?desde=15-06-2026").status_code == 422


# ---------------------------------------------------------------------------
# GET /api/historial/csv
# ---------------------------------------------------------------------------

class TestHistorialCsv:
    def test_exporta_csv_con_cabecera_y_filas(self, db):
        c = _crear_usuario(db, "c12@test.com")
        s = _crear_solicitud(db, c.id, tipo="metal", fecha="2026-06-18", kg=4.0)

        client = _client_como(db, c)
        resp = client.get("/api/historial/csv")

        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/csv")
        assert "historial_reciapp.csv" in resp.headers["content-disposition"]

        filas = list(csv.reader(io.StringIO(resp.text)))
        assert filas[0][:5] == [
            "id", "numero_seguimiento", "tipo_residuo", "cantidad_kg", "fecha_recoleccion",
        ]
        assert len(filas) == 2
        assert filas[1][0] == str(s.id)
        assert filas[1][2] == "metal"
        assert filas[1][4] == "2026-06-18"

    def test_csv_respeta_filtros(self, db):
        c = _crear_usuario(db, "c13@test.com")
        _crear_solicitud(db, c.id, tipo="plastico")
        _crear_solicitud(db, c.id, tipo="papel")

        client = _client_como(db, c)
        resp = client.get("/api/historial/csv?tipo_residuo=papel")

        filas = list(csv.reader(io.StringIO(resp.text)))
        assert len(filas) == 2  # cabecera + 1
        assert filas[1][2] == "papel"

    def test_csv_vacio_solo_cabecera(self, db):
        c = _crear_usuario(db, "c14@test.com")
        client = _client_como(db, c)
        resp = client.get("/api/historial/csv")

        filas = list(csv.reader(io.StringIO(resp.text)))
        assert len(filas) == 1
