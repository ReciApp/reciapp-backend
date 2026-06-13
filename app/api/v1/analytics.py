from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.v1.dependencies import require_role
from app.db.session import get_db
from app.models.user import Usuario
from app.schemas.analytics import PuntoHeatmap, ResumenAnalytics
from app.services import analytics

router = APIRouter()

FECHA_PATTERN = r"^\d{4}-\d{2}-\d{2}$"


def filtros_analytics(
    desde: str | None = Query(None, pattern=FECHA_PATTERN,
                              description="Fecha de recolección desde (YYYY-MM-DD, inclusivo)"),
    hasta: str | None = Query(None, pattern=FECHA_PATTERN,
                              description="Fecha de recolección hasta (YYYY-MM-DD, inclusivo)"),
    tipo_residuo: str | None = Query(None, description="Filtrar por tipo de residuo"),
) -> analytics.Filtros:
    """Dependencia de filtros compartida por resumen (RECI-66) y heatmap (RECI-68)."""
    return analytics.Filtros(desde=desde, hasta=hasta, tipo_residuo=tipo_residuo)


@router.get(
    "/resumen",
    response_model=ResumenAnalytics,
    summary="Resumen de KPIs agregados sobre las solicitudes (solo admin)",
)
def resumen_analytics(
    filtros: analytics.Filtros = Depends(filtros_analytics),
    db: Session = Depends(get_db),
    _: Usuario = Depends(require_role("admin")),
):
    return analytics.resumen(db, filtros)


@router.get(
    "/heatmap",
    response_model=list[PuntoHeatmap],
    summary="Puntos georreferenciados de recolecciones para el mapa de calor (solo admin)",
)
def heatmap_analytics(
    filtros: analytics.Filtros = Depends(filtros_analytics),
    db: Session = Depends(get_db),
    _: Usuario = Depends(require_role("admin")),
):
    return analytics.heatmap_puntos(db, filtros)
