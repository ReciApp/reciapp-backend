"""Tests para RECI-57: POST /api/calificaciones con recálculo de promedio."""
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
from app.schemas.user import RecicladorCreate, UsuarioCreate


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


@pytest.fixture
def ciudadano(db):
    return crud_user.create_ciudadano(db, UsuarioCreate(
        nombre="Ciudadano Test", correo="ciudadano@test.com", dni="12345678",
        celular="999888777", contrasena="secreta123",
    ))


@pytest.fixture
def reciclador(db):
    return crud_user.create_reciclador(db, RecicladorCreate(
        nombre="Reciclador Test", correo="reciclador@test.com", dni="87654321",
        celular="911222333", contrasena="secreta123",
        zona_cobertura="Puente Piedra", disponibilidad_horaria="manana",
    ))


@pytest.fixture
def client(db, ciudadano):
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: ciudadano
    yield TestClient(app)
    app.dependency_overrides.clear()


def _solicitud_completada(db, ciudadano, reciclador, estado="completada"):
    solicitud = crud_solicitud.create(db, SolicitudCreate(
        tipo_residuo="plastico", cantidad_kg=2.0, fecha_recoleccion="2026-06-15",
        franja_horaria="manana", direccion="Av. Test 123",
    ), ciudadano.id)
    solicitud.reciclador_id = reciclador.id
    solicitud.estado = estado
    db.commit()
    return solicitud


class TestCalificarServicio:
    def test_calificacion_valida_y_promedio_actualizado(self, client, db, ciudadano, reciclador):
        solicitud = _solicitud_completada(db, ciudadano, reciclador)

        resp = client.post("/api/calificaciones", json={
            "solicitud_id": solicitud.id, "puntuacion": 4, "comentario": "Buen servicio",
        })

        assert resp.status_code == 201
        body = resp.json()
        assert body["puntuacion"] == 4
        assert body["promedio_reciclador"] == 4.0
        assert body["total_calificaciones"] == 1

        db.refresh(reciclador)
        assert reciclador.calificacion_promedio == 4.0

    def test_promedio_con_varias_calificaciones(self, client, db, ciudadano, reciclador):
        s1 = _solicitud_completada(db, ciudadano, reciclador)
        s2 = _solicitud_completada(db, ciudadano, reciclador)

        client.post("/api/calificaciones", json={"solicitud_id": s1.id, "puntuacion": 5})
        resp = client.post("/api/calificaciones", json={"solicitud_id": s2.id, "puntuacion": 2})

        assert resp.json()["promedio_reciclador"] == 3.5
        assert resp.json()["total_calificaciones"] == 2

    def test_409_si_solicitud_no_completada(self, client, db, ciudadano, reciclador):
        solicitud = _solicitud_completada(db, ciudadano, reciclador, estado="en_camino")
        resp = client.post("/api/calificaciones",
                           json={"solicitud_id": solicitud.id, "puntuacion": 5})
        assert resp.status_code == 409

    def test_409_si_ya_fue_calificada(self, client, db, ciudadano, reciclador):
        solicitud = _solicitud_completada(db, ciudadano, reciclador)
        client.post("/api/calificaciones", json={"solicitud_id": solicitud.id, "puntuacion": 5})

        resp = client.post("/api/calificaciones",
                           json={"solicitud_id": solicitud.id, "puntuacion": 1})

        assert resp.status_code == 409
        db.refresh(reciclador)
        assert reciclador.calificacion_promedio == 5.0  # la segunda no alteró el promedio

    def test_403_si_no_es_su_solicitud(self, client, db, ciudadano, reciclador):
        otro = crud_user.create_ciudadano(db, UsuarioCreate(
            nombre="Otro", correo="otro@test.com", dni="11223344",
            celular="900111222", contrasena="secreta123",
        ))
        solicitud = _solicitud_completada(db, otro, reciclador)
        resp = client.post("/api/calificaciones",
                           json={"solicitud_id": solicitud.id, "puntuacion": 5})
        assert resp.status_code == 403

    def test_404_si_solicitud_no_existe(self, client):
        resp = client.post("/api/calificaciones", json={"solicitud_id": 999, "puntuacion": 5})
        assert resp.status_code == 404

    def test_puntuacion_fuera_de_rango_da_422(self, client, db, ciudadano, reciclador):
        solicitud = _solicitud_completada(db, ciudadano, reciclador)
        assert client.post("/api/calificaciones",
                           json={"solicitud_id": solicitud.id, "puntuacion": 0}).status_code == 422
        assert client.post("/api/calificaciones",
                           json={"solicitud_id": solicitud.id, "puntuacion": 6}).status_code == 422

    def test_comentario_mayor_a_500_da_422(self, client, db, ciudadano, reciclador):
        solicitud = _solicitud_completada(db, ciudadano, reciclador)
        resp = client.post("/api/calificaciones", json={
            "solicitud_id": solicitud.id, "puntuacion": 5, "comentario": "x" * 501,
        })
        assert resp.status_code == 422

    def test_comentario_es_opcional(self, client, db, ciudadano, reciclador):
        solicitud = _solicitud_completada(db, ciudadano, reciclador)
        resp = client.post("/api/calificaciones",
                           json={"solicitud_id": solicitud.id, "puntuacion": 3})
        assert resp.status_code == 201
        assert resp.json()["comentario"] is None

    def test_reciclador_no_puede_calificar(self, client, ciudadano):
        ciudadano.rol = "reciclador"
        resp = client.post("/api/calificaciones", json={"solicitud_id": 1, "puntuacion": 5})
        assert resp.status_code == 403
