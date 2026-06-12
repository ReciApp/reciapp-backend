from collections import defaultdict
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.v1.dependencies import require_role
from app.crud import crud_historial, crud_solicitud, crud_user
from app.db.session import get_db
from app.models.user import Usuario
from app.schemas.solicitud import HistorialOut, SolicitudConHistorialOut, SolicitudOut
from app.websockets.manager import manager

router = APIRouter()


def _fecha_dia_siguiente() -> str:
    return (date.today() + timedelta(days=1)).isoformat()


def _solicitud_del_reciclador_o_404(db, solicitud_id: int, reciclador_id: int):
    solicitud = crud_solicitud.get_by_id(db, solicitud_id)
    if not solicitud:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")
    if solicitud.reciclador_id != reciclador_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="La solicitud no está asignada a ti",
        )
    return solicitud


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


@router.get(
    "/dia-siguiente",
    response_model=list[SolicitudOut],
    summary="Plan del día siguiente: solicitudes asignadas o confirmadas para mañana",
)
def plan_dia_siguiente(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_role("reciclador")),
):
    return crud_solicitud.get_dia_siguiente(db, current_user.id, _fecha_dia_siguiente())


@router.put(
    "/solicitudes/{solicitud_id}/confirmar-dia",
    response_model=SolicitudOut,
    summary="Confirmar una solicitud asignada para el día siguiente",
)
def confirmar_dia_siguiente(
    solicitud_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_role("reciclador")),
):
    solicitud = _solicitud_del_reciclador_o_404(db, solicitud_id, current_user.id)

    if solicitud.estado != "asignada":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"La solicitud está en estado '{solicitud.estado}', no puede confirmarse",
        )
    if solicitud.fecha_recoleccion != _fecha_dia_siguiente():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Solo pueden confirmarse solicitudes programadas para mañana",
        )

    solicitud = crud_solicitud.marcar_estado(db, solicitud, "confirmada", actor_id=current_user.id)

    manager.notify_from_thread(
        solicitud.ciudadano_id,
        {
            "tipo": "solicitud_confirmada",
            "solicitud_id": solicitud.id,
            "reciclador_id": current_user.id,
            "fecha_recoleccion": solicitud.fecha_recoleccion,
            "franja_horaria": solicitud.franja_horaria,
        },
    )
    return solicitud


@router.put(
    "/solicitudes/{solicitud_id}/liberar",
    response_model=SolicitudOut,
    summary="Liberar una solicitud del plan: vuelve a 'pendiente' y al pool de disponibles",
)
def liberar_solicitud(
    solicitud_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_role("reciclador")),
):
    solicitud = _solicitud_del_reciclador_o_404(db, solicitud_id, current_user.id)

    if solicitud.estado not in ("asignada", "confirmada"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"La solicitud está en estado '{solicitud.estado}', no puede liberarse",
        )

    solicitud = crud_solicitud.resetear_asignacion(db, solicitud, actor_id=current_user.id)

    # Vuelve al pool: avisar al ciudadano y al resto de recicladores activos.
    manager.notify_from_thread(
        solicitud.ciudadano_id,
        {"tipo": "solicitud_liberada", "solicitud_id": solicitud.id},
    )
    for r in crud_user.get_recicladores_activos(db):
        if r.id != current_user.id:
            manager.notify_from_thread(r.id, {
                "tipo": "solicitud_disponible",
                "solicitud_id": solicitud.id,
                "ciudadano_id": solicitud.ciudadano_id,
                "tipo_residuo": solicitud.tipo_residuo,
                "cantidad_kg": solicitud.cantidad_kg,
                "direccion": solicitud.direccion,
                "fecha_recoleccion": solicitud.fecha_recoleccion,
                "franja_horaria": solicitud.franja_horaria,
                "latitud": solicitud.latitud,
                "longitud": solicitud.longitud,
            })
    return solicitud
