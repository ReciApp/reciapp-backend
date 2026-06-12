import csv
import io

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.v1.dependencies import get_current_user
from app.crud import crud_solicitud
from app.db.session import get_db
from app.models.user import Usuario
from app.schemas.solicitud import SolicitudOut

router = APIRouter()

FECHA_PATTERN = r"^\d{4}-\d{2}-\d{2}$"

COLUMNAS_CSV = [
    "id", "numero_seguimiento", "tipo_residuo", "cantidad_kg",
    "fecha_recoleccion", "franja_horaria", "direccion", "estado",
    "ciudadano_id", "reciclador_id", "fecha_creacion",
]


def _filtros_por_rol(current_user: Usuario) -> dict:
    """El ciudadano ve sus solicitudes, el reciclador las suyas y el admin todas."""
    if current_user.rol == "ciudadano":
        return {"ciudadano_id": current_user.id}
    if current_user.rol == "reciclador":
        return {"reciclador_id": current_user.id}
    return {}


def _consultar(
    db: Session,
    current_user: Usuario,
    estado: str | None,
    tipo_residuo: str | None,
    desde: str | None,
    hasta: str | None,
):
    return crud_solicitud.get_historial_filtrado(
        db,
        estado=estado,
        tipo_residuo=tipo_residuo,
        desde=desde,
        hasta=hasta,
        **_filtros_por_rol(current_user),
    )


@router.get(
    "",
    response_model=list[SolicitudOut],
    summary="Historial de solicitudes (solo lectura) con filtros",
)
def listar_historial(
    estado: str | None = Query(None, description="Filtrar por estado"),
    tipo_residuo: str | None = Query(None, description="Filtrar por tipo de residuo"),
    desde: str | None = Query(None, pattern=FECHA_PATTERN,
                              description="Fecha de recolección mínima (YYYY-MM-DD)"),
    hasta: str | None = Query(None, pattern=FECHA_PATTERN,
                              description="Fecha de recolección máxima (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    return _consultar(db, current_user, estado, tipo_residuo, desde, hasta)


@router.get(
    "/csv",
    summary="Exportar el historial filtrado como archivo CSV",
)
def exportar_historial_csv(
    estado: str | None = Query(None, description="Filtrar por estado"),
    tipo_residuo: str | None = Query(None, description="Filtrar por tipo de residuo"),
    desde: str | None = Query(None, pattern=FECHA_PATTERN,
                              description="Fecha de recolección mínima (YYYY-MM-DD)"),
    hasta: str | None = Query(None, pattern=FECHA_PATTERN,
                              description="Fecha de recolección máxima (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    solicitudes = _consultar(db, current_user, estado, tipo_residuo, desde, hasta)

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(COLUMNAS_CSV)
    for s in solicitudes:
        writer.writerow([
            s.id, s.numero_seguimiento, s.tipo_residuo, s.cantidad_kg,
            s.fecha_recoleccion, s.franja_horaria, s.direccion, s.estado,
            s.ciudadano_id, s.reciclador_id or "",
            s.fecha_creacion.isoformat() if s.fecha_creacion else "",
        ])
    buffer.seek(0)

    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="historial_reciapp.csv"'},
    )
