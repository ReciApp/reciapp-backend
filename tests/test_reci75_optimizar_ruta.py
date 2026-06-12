"""Tests para RECI-75: A* multi-punto y POST /api/rutas/optimizar."""
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.api.v1.dependencies import get_current_user, require_role
from app.db.session import get_db
from app.services import ruteo


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _solicitud(solicitud_id=1, estado="asignada", reciclador_id=10, lat=-11.86, lon=-77.07):
    s = MagicMock()
    s.id = solicitud_id
    s.estado = estado
    s.reciclador_id = reciclador_id
    s.direccion = f"Av. Test {solicitud_id}"
    s.latitud = lat
    s.longitud = lon
    return s


def _reciclador(user_id=10):
    u = MagicMock()
    u.id = user_id
    u.rol = "reciclador"
    u.activo = True
    return u


# ---------------------------------------------------------------------------
# optimizar_multipunto (unidad) — con fallback de línea directa (haversine)
# ---------------------------------------------------------------------------

class TestOptimizarMultipunto:
    """El grafo OSM no está cargado en tests, así que calcular_ruta usa la
    distancia haversine en línea directa: suficiente para validar el orden."""

    def test_ordena_por_vecino_mas_cercano(self):
        origen = (-11.860, -77.070)
        # Paradas dadas en orden de llegada inverso a su cercanía al origen
        paradas = [
            (-11.890, -77.070),  # lejos
            (-11.870, -77.070),  # media
            (-11.863, -77.070),  # cerca
        ]
        orden, tramos = ruteo.optimizar_multipunto(origen, paradas)
        assert orden == [2, 1, 0]
        assert len(tramos) == 3

    def test_costo_total_menor_o_igual_que_orden_de_llegada(self):
        origen = (-11.860, -77.070)
        paradas = [
            (-11.885, -77.040),
            (-11.862, -77.068),
            (-11.875, -77.090),
            (-11.864, -77.045),
        ]
        orden, tramos = ruteo.optimizar_multipunto(origen, paradas)

        costo_optimo = sum(t["distancia_km"] for t in tramos)
        secuencia_llegada = [origen] + paradas
        costo_llegada = sum(
            ruteo.haversine_km(*secuencia_llegada[i], *secuencia_llegada[i + 1])
            for i in range(len(secuencia_llegada) - 1)
        )
        assert costo_optimo <= costo_llegada + 1e-9

    def test_visita_todas_las_paradas_sin_repetir(self):
        origen = (-11.860, -77.070)
        paradas = [(-11.87, -77.05), (-11.88, -77.08), (-11.85, -77.06), (-11.89, -77.04)]
        orden, tramos = ruteo.optimizar_multipunto(origen, paradas)
        assert sorted(orden) == [0, 1, 2, 3]
        assert len(tramos) == len(paradas)

    def test_2opt_corrige_cruce_del_vecino_mas_cercano(self):
        # Configuración donde el vecino más cercano produce un camino subóptimo
        # y la mejora 2-opt debe reducir (o igualar) el costo.
        origen = (0.0, 0.0)
        paradas = [(0.0, 0.01), (0.0, 0.05), (0.001, 0.02), (0.0, 0.06)]
        dist, _ = ruteo._matriz_distancias([origen] + paradas)
        orden_nn = ruteo._vecino_mas_cercano(dist)
        orden_2opt = ruteo._mejora_2opt(orden_nn, dist)
        assert ruteo._costo_camino(orden_2opt, dist) <= ruteo._costo_camino(orden_nn, dist)

    def test_una_sola_parada(self):
        orden, tramos = ruteo.optimizar_multipunto((-11.86, -77.07), [(-11.87, -77.06)])
        assert orden == [0]
        assert len(tramos) == 1
        assert tramos[0]["distancia_km"] > 0


# ---------------------------------------------------------------------------
# POST /api/rutas/optimizar
# ---------------------------------------------------------------------------

class TestEndpointOptimizar:
    def _client_as_reciclador(self, reciclador_id=10):
        reciclador = _reciclador(reciclador_id)
        app.dependency_overrides[get_db] = lambda: MagicMock()
        app.dependency_overrides[get_current_user] = lambda: reciclador
        app.dependency_overrides[require_role("reciclador")] = lambda: reciclador
        return TestClient(app)

    def teardown_method(self):
        app.dependency_overrides.clear()

    def _payload(self, ids):
        return {"origen_lat": -11.860, "origen_lon": -77.070, "solicitud_ids": ids}

    def test_devuelve_orden_de_visita_y_totales(self):
        solicitudes = {
            1: _solicitud(1, lat=-11.890, lon=-77.070),   # lejos
            2: _solicitud(2, lat=-11.863, lon=-77.070),   # cerca
            3: _solicitud(3, estado="en_camino", lat=-11.870, lon=-77.070),  # media
        }
        with patch(
            "app.api.v1.rutas.crud_solicitud.get_by_id",
            side_effect=lambda _db, sid: solicitudes.get(sid),
        ):
            client = self._client_as_reciclador()
            resp = client.post("/api/rutas/optimizar", json=self._payload([1, 2, 3]))

        assert resp.status_code == 200
        body = resp.json()
        assert [p["solicitud_id"] for p in body["paradas"]] == [2, 3, 1]
        assert [p["orden"] for p in body["paradas"]] == [1, 2, 3]
        assert body["distancia_total_km"] > 0
        assert body["eta_total_min"] >= 1
        for parada in body["paradas"]:
            assert parada["ruta"], "cada tramo incluye su polilínea"

    def test_404_si_solicitud_no_existe(self):
        with patch("app.api.v1.rutas.crud_solicitud.get_by_id", return_value=None):
            client = self._client_as_reciclador()
            resp = client.post("/api/rutas/optimizar", json=self._payload([99]))
        assert resp.status_code == 404

    def test_403_si_solicitud_es_de_otro_reciclador(self):
        ajena = _solicitud(1, reciclador_id=99)
        with patch("app.api.v1.rutas.crud_solicitud.get_by_id", return_value=ajena):
            client = self._client_as_reciclador(reciclador_id=10)
            resp = client.post("/api/rutas/optimizar", json=self._payload([1]))
        assert resp.status_code == 403

    def test_409_si_estado_no_optimizable(self):
        completada = _solicitud(1, estado="completada")
        with patch("app.api.v1.rutas.crud_solicitud.get_by_id", return_value=completada):
            client = self._client_as_reciclador()
            resp = client.post("/api/rutas/optimizar", json=self._payload([1]))
        assert resp.status_code == 409

    def test_400_si_solicitud_sin_coordenadas(self):
        sin_coords = _solicitud(1, lat=None, lon=None)
        with patch("app.api.v1.rutas.crud_solicitud.get_by_id", return_value=sin_coords):
            client = self._client_as_reciclador()
            resp = client.post("/api/rutas/optimizar", json=self._payload([1]))
        assert resp.status_code == 400

    def test_422_si_lista_vacia(self):
        client = self._client_as_reciclador()
        resp = client.post("/api/rutas/optimizar", json=self._payload([]))
        assert resp.status_code == 422

    def test_ids_duplicados_se_visitan_una_vez(self):
        s = _solicitud(1)
        with patch("app.api.v1.rutas.crud_solicitud.get_by_id", return_value=s):
            client = self._client_as_reciclador()
            resp = client.post("/api/rutas/optimizar", json=self._payload([1, 1, 1]))
        assert resp.status_code == 200
        assert len(resp.json()["paradas"]) == 1
