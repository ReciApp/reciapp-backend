"""Tests para RECI-66: GET /api/analytics/resumen + servicio de agregación con caché."""
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
from app.models.calificacion import Calificacion
from app.models.wallet_transaccion import WalletTransaccion
from app.schemas.solicitud import SolicitudCreate
from app.schemas.user import UsuarioCreate
from app.services import analytics

_dni = itertools.count(20000000)


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


# ---------------------------------------------------------------------------
# Servicio de agregación
# ---------------------------------------------------------------------------

class TestResumenServicio:
    def test_agrega_kg_eco_creditos_y_calificacion(self, db):
        ciudadano = _ciudadano(db)
        s1 = _solicitud(db, ciudadano.id, tipo="plastico", kg=3.0)
        s2 = _solicitud(db, ciudadano.id, tipo="vidrio", kg=2.0)
        _solicitud(db, ciudadano.id, tipo="papel", kg=5.0, estado="pendiente")

        db.add(WalletTransaccion(usuario_id=ciudadano.id, tipo="acreditacion",
                                 monto=30.0, solicitud_id=s1.id))
        db.add(WalletTransaccion(usuario_id=ciudadano.id, tipo="acreditacion",
                                 monto=20.0, solicitud_id=s2.id))
        db.add(Calificacion(solicitud_id=s1.id, ciudadano_id=ciudadano.id,
                            reciclador_id=1, puntuacion=5))
        db.add(Calificacion(solicitud_id=s2.id, ciudadano_id=ciudadano.id,
                            reciclador_id=1, puntuacion=3))
        db.commit()

        r = analytics.resumen(db, analytics.Filtros())

        assert r["total_solicitudes"] == 3
        assert r["completadas"] == 2
        assert r["total_kg_reciclados"] == 5.0
        assert r["eco_creditos_otorgados"] == 50.0
        assert r["calificacion_promedio"] == 4.0
        assert r["total_calificaciones"] == 2
        assert r["por_tipo_residuo"] == {"plastico": 1, "vidrio": 1}
        assert r["por_estado"]["completada"] == 2
        assert r["por_estado"]["pendiente"] == 1

    def test_serie_kg_por_dia_ordenada(self, db):
        ciudadano = _ciudadano(db)
        _solicitud(db, ciudadano.id, kg=2.0, fecha="2026-06-16")
        _solicitud(db, ciudadano.id, kg=3.0, fecha="2026-06-15")
        _solicitud(db, ciudadano.id, kg=1.0, fecha="2026-06-15")

        serie = analytics.resumen(db, analytics.Filtros())["serie_kg_por_dia"]
        assert serie == [
            {"fecha": "2026-06-15", "kg": 4.0},
            {"fecha": "2026-06-16", "kg": 2.0},
        ]

    def test_filtros_por_fecha_y_tipo(self, db):
        ciudadano = _ciudadano(db)
        _solicitud(db, ciudadano.id, tipo="plastico", kg=2.0, fecha="2026-06-15")
        _solicitud(db, ciudadano.id, tipo="vidrio", kg=3.0, fecha="2026-06-20")

        r = analytics.resumen(db, analytics.Filtros(desde="2026-06-18", tipo_residuo="vidrio"))
        assert r["completadas"] == 1
        assert r["total_kg_reciclados"] == 3.0

    def test_sin_datos_devuelve_ceros(self, db):
        r = analytics.resumen(db, analytics.Filtros())
        assert r["total_solicitudes"] == 0
        assert r["calificacion_promedio"] is None
        assert r["serie_kg_por_dia"] == []


class TestCache:
    def test_segunda_llamada_usa_cache(self, db):
        ciudadano = _ciudadano(db)
        _solicitud(db, ciudadano.id, kg=2.0)

        primera = analytics.resumen(db, analytics.Filtros())
        # Agrega datos nuevos sin invalidar: el caché debe devolver lo viejo
        _solicitud(db, ciudadano.id, kg=10.0)
        segunda = analytics.resumen(db, analytics.Filtros())
        assert segunda == primera

        analytics.invalidar_cache()
        tercera = analytics.resumen(db, analytics.Filtros())
        assert tercera["completadas"] == 2

    def test_filtros_distintos_no_comparten_cache(self, db):
        ciudadano = _ciudadano(db)
        _solicitud(db, ciudadano.id, tipo="plastico", kg=2.0)
        _solicitud(db, ciudadano.id, tipo="vidrio", kg=3.0)

        todos = analytics.resumen(db, analytics.Filtros())
        solo_vidrio = analytics.resumen(db, analytics.Filtros(tipo_residuo="vidrio"))
        assert todos["completadas"] == 2
        assert solo_vidrio["completadas"] == 1


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

class TestEndpointResumen:
    def _client(self, db, rol="admin"):
        usuario = type("U", (), {"id": 1, "rol": rol, "activo": True})()
        app.dependency_overrides[get_db] = lambda: db
        app.dependency_overrides[get_current_user] = lambda: usuario
        return TestClient(app)

    def teardown_method(self):
        app.dependency_overrides.clear()

    def test_admin_obtiene_resumen(self, db):
        ciudadano = _ciudadano(db)
        _solicitud(db, ciudadano.id, kg=4.0)
        client = self._client(db)

        resp = client.get("/api/analytics/resumen")
        assert resp.status_code == 200
        assert resp.json()["total_kg_reciclados"] == 4.0

    def test_no_admin_recibe_403(self, db):
        client = self._client(db, rol="ciudadano")
        resp = client.get("/api/analytics/resumen")
        assert resp.status_code == 403

    def test_fecha_invalida_da_422(self, db):
        client = self._client(db)
        resp = client.get("/api/analytics/resumen?desde=15-06-2026")
        assert resp.status_code == 422
