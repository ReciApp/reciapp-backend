"""Tests para RECI-55: GET /api/wallets/me y POST /api/wallets/me/canjear/{reward_id}."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.api.v1.dependencies import get_current_user
from app.db.session import get_db
from app.crud import crud_reward, crud_user, crud_wallet
from app.models.base import Base
from app.schemas.reward import RewardCreate
from app.schemas.user import UsuarioCreate


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
    usuario = crud_user.create_ciudadano(db, UsuarioCreate(
        nombre="Ciudadano Test", correo="ciudadano@test.com", dni="12345678",
        celular="999888777", contrasena="secreta123",
    ))
    usuario.eco_creditos = 100.0
    db.commit()
    return usuario


@pytest.fixture
def client(db, ciudadano):
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: ciudadano
    yield TestClient(app)
    app.dependency_overrides.clear()


def _reward(db, costo=50.0, stock=5, nombre="Bolsa ecológica"):
    return crud_reward.create(db, RewardCreate(
        nombre=nombre, descripcion="Test", costo_creditos=costo, stock=stock,
    ))


# ---------------------------------------------------------------------------
# GET /api/wallets/me
# ---------------------------------------------------------------------------

class TestMiWallet:
    def test_saldo_y_wallet_vacia(self, client):
        resp = client.get("/api/wallets/me")
        assert resp.status_code == 200
        body = resp.json()
        assert body["saldo"] == 100.0
        assert body["transacciones"] == []
        assert body["total_paginas"] == 1

    def test_historial_paginado_10_por_pagina(self, client, db, ciudadano):
        for i in range(13):
            crud_wallet.registrar_acreditacion(db, ciudadano.id, 5.0, solicitud_id=None,
                                               descripcion=f"mov {i}")

        pagina1 = client.get("/api/wallets/me?pagina=1").json()
        pagina2 = client.get("/api/wallets/me?pagina=2").json()

        assert pagina1["total_transacciones"] == 13
        assert pagina1["total_paginas"] == 2
        assert len(pagina1["transacciones"]) == 10
        assert len(pagina2["transacciones"]) == 3

    def test_solo_ve_su_propia_wallet(self, client, db, ciudadano):
        otro = crud_user.create_ciudadano(db, UsuarioCreate(
            nombre="Otro", correo="otro@test.com", dni="87654321",
            celular="911222333", contrasena="secreta123",
        ))
        crud_wallet.registrar_acreditacion(db, otro.id, 99.0)
        crud_wallet.registrar_acreditacion(db, ciudadano.id, 5.0)

        body = client.get("/api/wallets/me").json()
        assert body["total_transacciones"] == 1
        assert body["transacciones"][0]["monto"] == 5.0

    def test_reciclador_no_tiene_wallet(self, client, ciudadano):
        ciudadano.rol = "reciclador"
        resp = client.get("/api/wallets/me")
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# POST /api/wallets/me/canjear/{reward_id}
# ---------------------------------------------------------------------------

class TestCanje:
    def test_canje_exitoso_genera_voucher_y_descuenta(self, client, db, ciudadano):
        reward = _reward(db, costo=40.0, stock=2)

        resp = client.post(f"/api/wallets/me/canjear/{reward.id}")

        assert resp.status_code == 200
        body = resp.json()
        assert body["voucher"].startswith("RECI-")
        assert body["saldo_restante"] == 60.0

        db.refresh(reward)
        assert reward.stock == 1

        wallet = client.get("/api/wallets/me").json()
        assert wallet["saldo"] == 60.0
        assert wallet["transacciones"][0]["tipo"] == "canje"
        assert wallet["transacciones"][0]["monto"] == -40.0
        assert wallet["transacciones"][0]["voucher"] == body["voucher"]

    def test_vouchers_son_unicos(self, client, db):
        reward = _reward(db, costo=10.0, stock=5)
        vouchers = {
            client.post(f"/api/wallets/me/canjear/{reward.id}").json()["voucher"]
            for _ in range(3)
        }
        assert len(vouchers) == 3

    def test_400_si_saldo_insuficiente(self, client, db, ciudadano):
        reward = _reward(db, costo=500.0)

        resp = client.post(f"/api/wallets/me/canjear/{reward.id}")

        assert resp.status_code == 400
        assert "insuficiente" in resp.json()["detail"].lower()
        db.refresh(reward)
        assert reward.stock == 5  # no se descontó nada

    def test_404_si_reward_no_existe(self, client):
        assert client.post("/api/wallets/me/canjear/999").status_code == 404

    def test_404_si_reward_inactiva(self, client, db):
        reward = _reward(db)
        crud_reward.toggle(db, reward)
        assert client.post(f"/api/wallets/me/canjear/{reward.id}").status_code == 404

    def test_409_si_no_hay_stock(self, client, db, ciudadano):
        reward = _reward(db, costo=10.0, stock=0)

        resp = client.post(f"/api/wallets/me/canjear/{reward.id}")

        assert resp.status_code == 409
        assert client.get("/api/wallets/me").json()["saldo"] == 100.0

    def test_reciclador_no_puede_canjear(self, client, db, ciudadano):
        reward = _reward(db)
        ciudadano.rol = "reciclador"
        assert client.post(f"/api/wallets/me/canjear/{reward.id}").status_code == 403
