from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.v1.dependencies import require_role
from app.crud import crud_calificacion, crud_solicitud, crud_user
from app.db.session import get_db
from app.models.user import Usuario
from app.schemas.calificacion import CalificacionCreate, CalificacionResultadoOut

router = APIRouter()


@router.post(
    "",
    response_model=CalificacionResultadoOut,
    status_code=status.HTTP_201_CREATED,
    summary="Calificar el servicio (1-5 estrellas) y recalcular promedio del reciclador",
)
def calificar_servicio(
    data: CalificacionCreate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_role("ciudadano")),
):
    solicitud = crud_solicitud.get_by_id(db, data.solicitud_id)
    if not solicitud:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")
    if solicitud.ciudadano_id != current_user.id:
        raise HTTPException(status_code=403, detail="No eres el ciudadano de esta solicitud")
    if solicitud.estado != "completada":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Solo se califica una solicitud completada (estado actual: '{solicitud.estado}')",
        )
    if solicitud.reciclador_id is None:
        raise HTTPException(status_code=409, detail="La solicitud no tiene reciclador asignado")
    if crud_calificacion.get_by_solicitud(db, data.solicitud_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Esta solicitud ya fue calificada",
        )

    calificacion = crud_calificacion.create(
        db,
        solicitud_id=data.solicitud_id,
        ciudadano_id=current_user.id,
        reciclador_id=solicitud.reciclador_id,
        puntuacion=data.puntuacion,
        comentario=data.comentario,
    )

    reciclador = crud_user.get_by_id(db, solicitud.reciclador_id)
    return CalificacionResultadoOut(
        **{c: getattr(calificacion, c) for c in
           ("id", "solicitud_id", "ciudadano_id", "reciclador_id",
            "puntuacion", "comentario", "fecha")},
        promedio_reciclador=reciclador.calificacion_promedio if reciclador else data.puntuacion,
        total_calificaciones=reciclador.total_calificaciones if reciclador else 1,
    )
