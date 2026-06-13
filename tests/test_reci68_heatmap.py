"""Tests para RECI-68: GET /api/analytics/heatmap (comparte filtros y caché con RECI-66)."""
import itertools

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
from app.services import analytics

_dni = itertools.count(30000000)


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    analytics.invalidar_cache()
    yield session
    session.close()
    analytics.invalidar_cache()


def _ciudadano(db, correo="c@test.com"):
    return crud_user.create_ciudadano(db, UsuarioCreate(
        nombre="Ciudadano", correo=correo, dni=str(next(_dni)),
        celular="999888777", contrasena="secreta123",
    ))


def _solicitud(db, ciudadano_id, tipo="plastico", kg=2.0, fecha="2026-06-15",
               estado="completada", lat=-11.86, lon=-77.07):
    s = crud_solicitud.create(db, SolicitudCreate(
        tipo_residuo=tipo, cantidad_kg=kg, fecha_recoleccion=fecha,
        franja_horaria="manana", direccion="Av. Test 123", latitud=lat, longitud=lon,
    ), ciudadano_id)
    if estado != "pendiente":
        crud_solicitud.marcar_estado(db, s, estado)
    return s


class TestHeatmapServicio:
    def test_solo_completadas_con_coordenadas(self, db):
        ciudadano = _ciudadano(db)
        _solicitud(db, ciudadano.id, kg=3.0, lat=-11.8, lon=-77.0)
        _solicitud(db, ciudadano.id, kg=5.0, estado="pendiente")  # excluida
        _solicitud(db, ciudadano.id, kg=2.0, lat=None, lon=None)  # sin coords, excluida

        puntos = analytics.heatmap_puntos(db, analytics.Filtros())
        assert len(puntos) == 1
        assert puntos[0] == {"lat": -11.8, "lon": -77.0, "peso": 3.0}

    def test_respeta_filtros_de_tipo(self, db):
        ciudadano = _ciudadano(db)
        _solicitud(db, ciudadano.id, tipo="plastico", lat=-11.8, lon=-77.0)
        _solicitud(db, ciudadano.id, tipo="vidrio", lat=-11.9, lon=-77.1)

        puntos = analytics.heatmap_puntos(db, analytics.Filtros(tipo_residuo="vidrio"))
        assert len(puntos) == 1
        assert puntos[0]["lat"] == -11.9


class TestEndpointHeatmap:
    def _client(self, db, rol="admin"):
        usuario = type("U", (), {"id": 1, "rol": rol, "activo": True})()
        app.dependency_overrides[get_db] = lambda: db
        app.dependency_overrides[get_current_user] = lambda: usuario
        return TestClient(app)

    def teardown_method(self):
        app.dependency_overrides.clear()

    def test_admin_obtiene_puntos(self, db):
        ciudadano = _ciudadano(db)
        _solicitud(db, ciudadano.id, kg=4.0, lat=-11.8, lon=-77.0)
        client = self._client(db)

        resp = client.get("/api/analytics/heatmap")
        assert resp.status_code == 200
        body = resp.json()
        assert body == [{"lat": -11.8, "lon": -77.0, "peso": 4.0}]

    def test_no_admin_recibe_403(self, db):
        client = self._client(db, rol="reciclador")
        resp = client.get("/api/analytics/heatmap")
        assert resp.status_code == 403

    def test_comparte_filtros_con_resumen(self, db):
        client = self._client(db)
        resp = client.get("/api/analytics/heatmap?desde=15-06-2026")
        assert resp.status_code == 422
