import uuid
from datetime import datetime, timezone
from sqlalchemy import update as sa_update
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


def get_pendientes(db: Session) -> list[Solicitud]:
    return (
        db.query(Solicitud)
        .filter(Solicitud.estado == "pendiente")
        .order_by(Solicitud.fecha_creacion.desc())
        .all()
    )


def tomar(db: Session, solicitud_id: int, reciclador_id: int) -> Solicitud | None:
    """Reclama atómicamente una solicitud pendiente para el reciclador.

    Usa un UPDATE condicionado a estado='pendiente' para que, si dos
    recicladores la toman a la vez, solo uno gane la condición de carrera.
    Devuelve None si la solicitud ya no estaba disponible.
    """
    resultado = db.execute(
        sa_update(Solicitud)
        .where(Solicitud.id == solicitud_id, Solicitud.estado == "pendiente")
        .values(
            estado="en_camino",
            reciclador_id=reciclador_id,
            fecha_asignacion=datetime.now(timezone.utc),
        )
    )
    db.commit()
    if resultado.rowcount == 0:
        return None
    return get_by_id(db, solicitud_id)


def get_by_ciudadano(db: Session, ciudadano_id: int) -> list[Solicitud]:
    return (
        db.query(Solicitud)
        .filter(Solicitud.ciudadano_id == ciudadano_id)
        .order_by(Solicitud.fecha_creacion.desc())
        .all()
    )


def get_by_reciclador(db: Session, reciclador_id: int) -> list[Solicitud]:
    return (
        db.query(Solicitud)
        .filter(Solicitud.reciclador_id == reciclador_id)
        .order_by(Solicitud.fecha_creacion.desc())
        .all()
    )


def asignar(db: Session, solicitud: Solicitud, reciclador_id: int) -> Solicitud:
    solicitud.reciclador_id = reciclador_id
    solicitud.estado = "asignada"
    solicitud.fecha_asignacion = datetime.now(timezone.utc)
    db.commit()
    db.refresh(solicitud)
    return solicitud


def reasignar(db: Session, solicitud: Solicitud, nuevo_reciclador_id: int) -> Solicitud:
    """Cambia el reciclador asignado sin modificar el estado (sigue 'asignada')."""
    solicitud.reciclador_id = nuevo_reciclador_id
    solicitud.fecha_asignacion = datetime.now(timezone.utc)
    db.commit()
    db.refresh(solicitud)
    return solicitud


def marcar_estado(db: Session, solicitud: Solicitud, nuevo_estado: str) -> Solicitud:
    solicitud.estado = nuevo_estado
    db.commit()
    db.refresh(solicitud)
    return solicitud


def resetear_asignacion(db: Session, solicitud: Solicitud) -> Solicitud:
    """Limpia reciclador y vuelve a 'pendiente' (rechazar o timeout)."""
    solicitud.estado = "pendiente"
    solicitud.reciclador_id = None
    solicitud.fecha_asignacion = None
    db.commit()
    db.refresh(solicitud)
    return solicitud
