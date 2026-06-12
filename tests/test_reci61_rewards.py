"""Tests para RECI-61: CRUD de Reward y endpoints /admin/rewards."""
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.api.v1.dependencies import get_current_user
from app.db.session import get_db
from app.crud import crud_reward
from app.models.base import Base
from app.schemas.reward import RewardCreate, RewardUpdate


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


@pytest.fixture
def client(db):
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app)
    app.dependency_overrides.clear()


def _como(rol, user_id=1):
    usuario = MagicMock()
    usuario.id = user_id
    usuario.rol = rol
    usuario.activo = True
    app.dependency_overrides[get_current_user] = lambda: usuario
    return usuario


def _payload(**extra):
    base = {"nombre": "Bolsa ecológica", "descripcion": "Bolsa de tela reutilizable",
            "costo_creditos": 50.0, "stock": 10}
    base.update(extra)
    return base


# ---------------------------------------------------------------------------
# CRUD (unidad, con BD real en memoria)
# ---------------------------------------------------------------------------

class TestCrudReward:
    def test_create_y_get(self, db):
        reward = crud_reward.create(db, RewardCreate(**_payload()))
        assert reward.id is not None
        assert reward.activo is True
        assert crud_reward.get_by_id(db, reward.id).nombre == "Bolsa ecológica"

    def test_get_activos_excluye_inactivas(self, db):
        activa = crud_reward.create(db, RewardCreate(**_payload(nombre="Activa")))
        inactiva = crud_reward.create(db, RewardCreate(**_payload(nombre="Inactiva")))
        crud_reward.toggle(db, inactiva)

        catalogo = crud_reward.get_activos(db)
        assert [r.id for r in catalogo] == [activa.id]

    def test_update_parcial(self, db):
        reward = crud_reward.create(db, RewardCreate(**_payload()))
        crud_reward.update(db, reward, RewardUpdate(stock=3))
        assert reward.stock == 3
        assert reward.nombre == "Bolsa ecológica"

    def test_descontar_stock_atomico(self, db):
        reward = crud_reward.create(db, RewardCreate(**_payload(stock=1)))

        assert crud_reward.descontar_stock(db, reward.id) is True
        db.commit()
        db.refresh(reward)
        assert reward.stock == 0

        # sin stock: el descuento falla y el stock nunca queda negativo
        assert crud_reward.descontar_stock(db, reward.id) is False
        db.commit()
        db.refresh(reward)
        assert reward.stock == 0

    def test_descontar_stock_falla_si_inactiva(self, db):
        reward = crud_reward.create(db, RewardCreate(**_payload(stock=5)))
        crud_reward.toggle(db, reward)
        assert crud_reward.descontar_stock(db, reward.id) is False


# ---------------------------------------------------------------------------
# Endpoints /admin/rewards (solo admin) y catálogo /api/rewards
# ---------------------------------------------------------------------------

class TestEndpointsRewards:
    def test_admin_crea_recompensa(self, client):
        _como("admin")
        resp = client.post("/admin/rewards", json=_payload())
        assert resp.status_code == 201
        assert resp.json()["nombre"] == "Bolsa ecológica"
        assert resp.json()["activo"] is True

    def test_ciudadano_no_puede_crear(self, client):
        _como("ciudadano")
        resp = client.post("/admin/rewards", json=_payload())
        assert resp.status_code == 403

    def test_reciclador_no_puede_editar_ni_toggle(self, client):
        _como("admin")
        reward_id = client.post("/admin/rewards", json=_payload()).json()["id"]

        _como("reciclador")
        assert client.put(f"/admin/rewards/{reward_id}", json={"stock": 1}).status_code == 403
        assert client.patch(f"/admin/rewards/{reward_id}/toggle").status_code == 403

    def test_admin_edita_recompensa(self, client):
        _como("admin")
        reward_id = client.post("/admin/rewards", json=_payload()).json()["id"]
        resp = client.put(f"/admin/rewards/{reward_id}",
                          json={"nombre": "Tomatodo", "costo_creditos": 80})
        assert resp.status_code == 200
        assert resp.json()["nombre"] == "Tomatodo"
        assert resp.json()["costo_creditos"] == 80

    def test_editar_404_si_no_existe(self, client):
        _como("admin")
        assert client.put("/admin/rewards/999", json={"stock": 1}).status_code == 404

    def test_toggle_desactiva_y_reactiva(self, client):
        _como("admin")
        reward_id = client.post("/admin/rewards", json=_payload()).json()["id"]

        assert client.patch(f"/admin/rewards/{reward_id}/toggle").json()["activo"] is False
        assert client.patch(f"/admin/rewards/{reward_id}/toggle").json()["activo"] is True

    def test_stock_negativo_rechazado(self, client):
        _como("admin")
        resp = client.post("/admin/rewards", json=_payload(stock=-1))
        assert resp.status_code == 422

    def test_costo_cero_rechazado(self, client):
        _como("admin")
        resp = client.post("/admin/rewards", json=_payload(costo_creditos=0))
        assert resp.status_code == 422

    def test_catalogo_solo_muestra_activas(self, client):
        _como("admin")
        client.post("/admin/rewards", json=_payload(nombre="Visible"))
        oculta_id = client.post("/admin/rewards", json=_payload(nombre="Oculta")).json()["id"]
        client.patch(f"/admin/rewards/{oculta_id}/toggle")

        _como("ciudadano")
        resp = client.get("/api/rewards")
        assert resp.status_code == 200
        assert [r["nombre"] for r in resp.json()] == ["Visible"]

    def test_listado_admin_incluye_inactivas(self, client):
        _como("admin")
        client.post("/admin/rewards", json=_payload(nombre="Visible"))
        oculta_id = client.post("/admin/rewards", json=_payload(nombre="Oculta")).json()["id"]
        client.patch(f"/admin/rewards/{oculta_id}/toggle")

        resp = client.get("/admin/rewards")
        assert len(resp.json()) == 2
