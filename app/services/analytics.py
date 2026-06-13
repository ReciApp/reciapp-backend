"""Servicio de analytics: agrega sobre las solicitudes ya generadas y expone
un pequeño caché TTL en memoria que comparten el resumen (RECI-66) y el
heatmap (RECI-68), ya que ambos parten de los mismos filtros."""
import time
from collections import Counter, defaultdict
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models.calificacion import Calificacion
from app.models.solicitud import Solicitud
from app.models.wallet_transaccion import WalletTransaccion

CACHE_TTL_SEG = 60
ESTADOS_PRODUCTIVOS = ("completada",)

_cache: dict[tuple, tuple[float, object]] = {}


@dataclass(frozen=True)
class Filtros:
    """Filtros compartidos por resumen y heatmap. Sirven de clave de caché."""
    desde: str | None = None
    hasta: str | None = None
    tipo_residuo: str | None = None

    def key(self) -> tuple:
        return (self.desde, self.hasta, self.tipo_residuo)


def _cache_get(namespace: str, filtros: Filtros):
    entrada = _cache.get((namespace, filtros.key()))
    if not entrada:
        return None
    expira_en, valor = entrada
    if time.monotonic() > expira_en:
        _cache.pop((namespace, filtros.key()), None)
        return None
    return valor


def _cache_set(namespace: str, filtros: Filtros, valor):
    _cache[(namespace, filtros.key())] = (time.monotonic() + CACHE_TTL_SEG, valor)


def invalidar_cache() -> None:
    """Limpia todo el caché (útil en tests o tras una recarga masiva de datos)."""
    _cache.clear()


def _solicitudes_filtradas(db: Session, filtros: Filtros) -> list[Solicitud]:
    query = db.query(Solicitud)
    if filtros.desde:
        query = query.filter(Solicitud.fecha_recoleccion >= filtros.desde)
    if filtros.hasta:
        query = query.filter(Solicitud.fecha_recoleccion <= filtros.hasta)
    if filtros.tipo_residuo:
        query = query.filter(Solicitud.tipo_residuo == filtros.tipo_residuo)
    return query.all()


def resumen(db: Session, filtros: Filtros) -> dict:
    """KPIs agregados sobre las solicitudes que cumplen los filtros."""
    cacheado = _cache_get("resumen", filtros)
    if cacheado is not None:
        return cacheado

    solicitudes = _solicitudes_filtradas(db, filtros)
    completadas = [s for s in solicitudes if s.estado in ESTADOS_PRODUCTIVOS]

    por_estado = Counter(s.estado for s in solicitudes)
    por_tipo = Counter(s.tipo_residuo for s in completadas)

    kg_por_dia: dict[str, float] = defaultdict(float)
    for s in completadas:
        kg_por_dia[s.fecha_recoleccion] += s.cantidad_kg or 0.0
    serie = [
        {"fecha": fecha, "kg": round(kg, 2)}
        for fecha, kg in sorted(kg_por_dia.items())
    ]

    ids = [s.id for s in solicitudes]
    eco_creditos = 0.0
    puntuaciones: list[int] = []
    if ids:
        eco_creditos = (
            db.query(WalletTransaccion)
            .filter(
                WalletTransaccion.tipo == "acreditacion",
                WalletTransaccion.solicitud_id.in_(ids),
            )
            .with_entities(WalletTransaccion.monto)
            .all()
        )
        eco_creditos = round(sum(m[0] for m in eco_creditos), 2)
        puntuaciones = [
            p[0]
            for p in db.query(Calificacion.puntuacion)
            .filter(Calificacion.solicitud_id.in_(ids))
            .all()
        ]

    total_kg = round(sum(s.cantidad_kg or 0.0 for s in completadas), 2)
    calificacion_promedio = (
        round(sum(puntuaciones) / len(puntuaciones), 2) if puntuaciones else None
    )

    resultado = {
        "total_solicitudes": len(solicitudes),
        "completadas": len(completadas),
        "total_kg_reciclados": total_kg,
        "eco_creditos_otorgados": eco_creditos,
        "calificacion_promedio": calificacion_promedio,
        "total_calificaciones": len(puntuaciones),
        "por_estado": dict(por_estado),
        "por_tipo_residuo": dict(por_tipo),
        "serie_kg_por_dia": serie,
    }
    _cache_set("resumen", filtros, resultado)
    return resultado


def heatmap_puntos(db: Session, filtros: Filtros) -> list[dict]:
    """Puntos georreferenciados (lat, lon, peso) de las solicitudes completadas
    con coordenadas, para alimentar un mapa de calor (RECI-68)."""
    cacheado = _cache_get("heatmap", filtros)
    if cacheado is not None:
        return cacheado

    solicitudes = _solicitudes_filtradas(db, filtros)
    puntos = [
        {
            "lat": s.latitud,
            "lon": s.longitud,
            "peso": round(s.cantidad_kg or 0.0, 2),
        }
        for s in solicitudes
        if s.estado in ESTADOS_PRODUCTIVOS
        and s.latitud is not None
        and s.longitud is not None
    ]
    _cache_set("heatmap", filtros, puntos)
    return puntos
