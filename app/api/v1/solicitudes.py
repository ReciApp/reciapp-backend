from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.v1.dependencies import get_current_user, require_role
from app.crud import crud_solicitud
from app.db.session import get_db
from app.models.user import Usuario
from app.schemas.solicitud import SolicitudCreate, SolicitudOut
from app.services.asignacion import trigger_asignacion

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
