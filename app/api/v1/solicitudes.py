from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.v1.dependencies import get_current_user, require_role
from app.crud import crud_solicitud
from app.db.session import get_db
from app.models.user import Usuario
from app.schemas.solicitud import SolicitudCreate, SolicitudOut
from app.services.asignacion import trigger_asignacion
from app.websockets.manager import manager

router = APIRouter()


@router.post(
    "",
    response_model=SolicitudOut,
    status_code=status.HTTP_201_CREATED,
    summary="Crear solicitud de recolección",
)
def crear_solicitud(
    data: SolicitudCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_role("ciudadano")),
):
    solicitud = crud_solicitud.create(db, data, current_user.id)
    background_tasks.add_task(trigger_asignacion, solicitud.id)
    return solicitud


@router.get(
    "",
    response_model=list[SolicitudOut],
    summary="Listar mis solicitudes",
)
def listar_solicitudes(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    if current_user.rol == "reciclador":
        return crud_solicitud.get_by_reciclador(db, current_user.id)
    return crud_solicitud.get_by_ciudadano(db, current_user.id)


@router.get(
    "/{solicitud_id}",
    response_model=SolicitudOut,
    summary="Obtener detalle de una solicitud",
)
def obtener_solicitud(
    solicitud_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    solicitud = crud_solicitud.get_by_id(db, solicitud_id)
    if not solicitud:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")

    if current_user.rol == "admin":
        return solicitud
    if current_user.rol == "ciudadano" and solicitud.ciudadano_id == current_user.id:
        return solicitud
    if current_user.rol == "reciclador" and solicitud.reciclador_id == current_user.id:
        return solicitud

    raise HTTPException(status_code=403, detail="No tienes acceso a esta solicitud")


@router.put(
    "/{solicitud_id}/aceptar",
    response_model=SolicitudOut,
    summary="Reciclador acepta la solicitud asignada",
)
def aceptar_solicitud(
    solicitud_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_role("reciclador")),
):
    solicitud = crud_solicitud.get_by_id(db, solicitud_id)
    if not solicitud:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")
    if solicitud.reciclador_id != current_user.id:
        raise HTTPException(status_code=403, detail="No eres el reciclador asignado a esta solicitud")
    if solicitud.estado != "asignada":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"La solicitud está en estado '{solicitud.estado}', no puede aceptarse",
        )

    solicitud = crud_solicitud.marcar_estado(db, solicitud, "en_camino")

    manager.notify_from_thread(
        solicitud.ciudadano_id,
        {
            "tipo": "solicitud_en_camino",
            "solicitud_id": solicitud.id,
            "reciclador_id": solicitud.reciclador_id,
        },
    )
    return solicitud


@router.put(
    "/{solicitud_id}/rechazar",
    response_model=SolicitudOut,
    summary="Reciclador rechaza la solicitud; se dispara reasignación automática",
)
def rechazar_solicitud(
    solicitud_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_role("reciclador")),
):
    solicitud = crud_solicitud.get_by_id(db, solicitud_id)
    if not solicitud:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")
    if solicitud.reciclador_id != current_user.id:
        raise HTTPException(status_code=403, detail="No eres el reciclador asignado a esta solicitud")
    if solicitud.estado != "asignada":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"La solicitud está en estado '{solicitud.estado}', no puede rechazarse",
        )

    reciclador_rechazado_id = current_user.id
    solicitud = crud_solicitud.resetear_asignacion(db, solicitud)

    manager.notify_from_thread(
        solicitud.ciudadano_id,
        {
            "tipo": "solicitud_reasignando",
            "solicitud_id": solicitud.id,
        },
    )

    background_tasks.add_task(trigger_asignacion, solicitud_id, 1, {reciclador_rechazado_id})
    return solicitud
