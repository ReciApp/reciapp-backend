"""Tests unitarios para RECI-38: cambio de estado a 'asignada'."""
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.services.algoritmo_asignacion import (
    _haversine_km,
    _reciclador_mas_cercano,
    asignar_solicitud,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_solicitud(lat=None, lon=None, franja="manana", estado="pendiente"):
    s = MagicMock()
    s.latitud = lat
    s.longitud = lon
    s.franja_horaria = franja
    s.estado = estado
    return s


def _make_reciclador(id_: int, lat=None, lon=None, franja="manana"):
    r = MagicMock()
    r.id = id_
    r.latitud = lat
    r.longitud = lon
    r.disponibilidad_horaria = franja
    r.rol = "reciclador"
    r.estado_validacion = "aprobado"
    r.activo = True
    return r


# ---------------------------------------------------------------------------
# Haversine
# ---------------------------------------------------------------------------

def test_haversine_misma_ubicacion():
    assert _haversine_km(-12.05, -77.05, -12.05, -77.05) == pytest.approx(0.0)


def test_haversine_distancia_conocida():
    # Lima ↔ Callao ~13 km
    dist = _haversine_km(-12.0464, -77.0428, -12.0565, -77.1219)
    assert 7 < dist < 15


# ---------------------------------------------------------------------------
# _reciclador_mas_cercano
# ---------------------------------------------------------------------------

def test_sin_candidatos_retorna_none():
    solicitud = _make_solicitud(lat=-12.0, lon=-77.0)
    assert _reciclador_mas_cercano([], solicitud) is None


def test_sin_coords_en_solicitud_retorna_primero():
    r1 = _make_reciclador(1)
    r2 = _make_reciclador(2)
    solicitud = _make_solicitud(lat=None, lon=None)
    assert _reciclador_mas_cercano([r1, r2], solicitud) is r1


def test_elige_el_mas_cercano():
    # r1 lejos, r2 cerca
    r1 = _make_reciclador(1, lat=-12.10, lon=-77.10)
    r2 = _make_reciclador(2, lat=-12.05, lon=-77.05)
    solicitud = _make_solicitud(lat=-12.046, lon=-77.043)
    assert _reciclador_mas_cercano([r1, r2], solicitud) is r2


# ---------------------------------------------------------------------------
# asignar_solicitud
# ---------------------------------------------------------------------------

def test_asignar_solicitud_sin_recicladores_retorna_false():
    db = MagicMock()
    solicitud = _make_solicitud()
    with patch(
        "app.services.algoritmo_asignacion._recicladores_disponibles",
        return_value=[],
    ):
        result = asignar_solicitud(db, solicitud)
    assert result is False


def test_asignar_solicitud_setea_estado_y_fecha(monkeypatch):
    db = MagicMock()
    solicitud = _make_solicitud(lat=-12.0, lon=-77.0)
    reciclador = _make_reciclador(42, lat=-12.01, lon=-77.01)

    monkeypatch.setattr(
        "app.services.algoritmo_asignacion._recicladores_disponibles",
        lambda *a, **kw: [reciclador],
    )

    assigned_solicitud = MagicMock()
    assigned_solicitud.estado = "asignada"
    assigned_solicitud.reciclador_id = 42
    assigned_solicitud.fecha_asignacion = datetime.now(timezone.utc)

    with patch("app.services.algoritmo_asignacion.crud_solicitud.asignar") as mock_asignar:
        mock_asignar.return_value = assigned_solicitud
        result = asignar_solicitud(db, solicitud)

    assert result is True
    mock_asignar.assert_called_once_with(db, solicitud, 42)


def test_asignar_solicitud_excluye_reciclador(monkeypatch):
    """Al pasar excluir_ids, ese reciclador no debe ser elegido."""
    db = MagicMock()
    solicitud = _make_solicitud(lat=-12.0, lon=-77.0)

    r1 = _make_reciclador(10, lat=-12.01, lon=-77.01)  # el más cercano pero excluido
    r2 = _make_reciclador(20, lat=-12.05, lon=-77.05)

    captured = {}

    def fake_disponibles(db, franja, excluir_ids=None):
        captured["excluir_ids"] = excluir_ids
        if excluir_ids and 10 in excluir_ids:
            return [r2]
        return [r1, r2]

    monkeypatch.setattr(
        "app.services.algoritmo_asignacion._recicladores_disponibles",
        fake_disponibles,
    )

    with patch("app.services.algoritmo_asignacion.crud_solicitud.asignar") as mock_asignar:
        mock_asignar.return_value = MagicMock()
        asignar_solicitud(db, solicitud, excluir_ids={10})

    mock_asignar.assert_called_once_with(db, solicitud, 20)
    assert captured["excluir_ids"] == {10}
