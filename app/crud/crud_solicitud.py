import uuid
from sqlalchemy.orm import Session
from app.models.solicitud import Solicitud
from app.schemas.solicitud import SolicitudCreate


def create(db: Session, data: SolicitudCreate, ciudadano_id: int) -> Solicitud:
    solicitud = Solicitud(
        numero_seguimiento=str(uuid.uuid4()),
        ciudadano_id=ciudadano_id,
        tipo_residuo=data.tipo_residuo,
        cantidad_kg=data.cantidad_kg,
        fecha_recoleccion=data.fecha_recoleccion,
        franja_horaria=data.franja_horaria,
        direccion=data.direccion,
        latitud=data.latitud,
        longitud=data.longitud,
        estado="pendiente",
    )
    db.add(solicitud)
    db.commit()
    db.refresh(solicitud)
    return solicitud


def get_by_id(db: Session, solicitud_id: int) -> Solicitud | None:
    return db.query(Solicitud).filter(Solicitud.id == solicitud_id).first()


def get_by_ciudadano(db: Session, ciudadano_id: int) -> list[Solicitud]:
    return (
        db.query(Solicitud)
        .filter(Solicitud.ciudadano_id == ciudadano_id)
        .order_by(Solicitud.fecha_creacion.desc())
        .all()
    )
