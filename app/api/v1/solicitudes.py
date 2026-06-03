from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.v1.dependencies import get_current_user, require_role
from app.crud import crud_solicitud
from app.db.session import get_db
from app.models.user import Usuario
from app.schemas.solicitud import SolicitudCreate, SolicitudOut

router = APIRouter()


@router.post(
    "",
    response_model=SolicitudOut,
    status_code=status.HTTP_201_CREATED,
    summary="Crear solicitud de recolección",
)
def crear_solicitud(
    data: SolicitudCreate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_role("ciudadano")),
):
    solicitud = crud_solicitud.create(db, data, current_user.id)
    return solicitud
