from collections import defaultdict

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.v1.dependencies import require_role
from app.crud import crud_historial, crud_solicitud
from app.db.session import get_db
from app.models.user import Usuario
from app.schemas.solicitud import HistorialOut, SolicitudConHistorialOut

router = APIRouter()


@router.get(
    "/solicitudes",
    response_model=list[SolicitudConHistorialOut],
    summary="Backlog del reciclador: sus solicitudes con trazabilidad de estados",
)
def listar_solicitudes_reciclador(
    estado: str | None = Query(None, description="Filtrar por estado"),
    fecha: str | None = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$",
                              description="Filtrar por fecha de recolección (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_role("reciclador")),
):
    solicitudes = crud_solicitud.get_by_reciclador_filtrado(
        db, current_user.id, estado=estado, fecha=fecha,
    )

    transiciones = crud_historial.get_by_solicitudes(db, [s.id for s in solicitudes])
    por_solicitud: dict[int, list] = defaultdict(list)
    for t in transiciones:
        por_solicitud[t.solicitud_id].append(t)

    respuesta = []
    for s in solicitudes:
        item = SolicitudConHistorialOut.model_validate(s)
        item.historial = [HistorialOut.model_validate(t) for t in por_solicitud[s.id]]
        respuesta.append(item)
    return respuesta
