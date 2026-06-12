import uuid
from datetime import datetime, timezone
from sqlalchemy import update as sa_update
from sqlalchemy.orm import Session
from app.crud import crud_historial
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
    db.flush()
    crud_historial.agregar(db, solicitud.id, None, "pendiente", usuario_id=ciudadano_id)
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
    if resultado.rowcount == 0:
        db.commit()
        return None
    crud_historial.agregar(db, solicitud_id, "pendiente", "en_camino", usuario_id=reciclador_id)
    db.commit()
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


def get_by_reciclador_filtrado(
    db: Session,
    reciclador_id: int,
    estado: str | None = None,
    fecha: str | None = None,
) -> list[Solicitud]:
    """Solicitudes del reciclador con filtros opcionales por estado y
    fecha de recolección (YYYY-MM-DD)."""
    query = db.query(Solicitud).filter(Solicitud.reciclador_id == reciclador_id)
    if estado:
        query = query.filter(Solicitud.estado == estado)
    if fecha:
        query = query.filter(Solicitud.fecha_recoleccion == fecha)
    return query.order_by(Solicitud.fecha_creacion.desc()).all()


def get_dia_siguiente(db: Session, reciclador_id: int, fecha: str) -> list[Solicitud]:
    """Solicitudes del reciclador planificables para el día siguiente:
    las asignadas (por confirmar) y las ya confirmadas para esa fecha."""
    return (
        db.query(Solicitud)
        .filter(
            Solicitud.reciclador_id == reciclador_id,
            Solicitud.fecha_recoleccion == fecha,
            Solicitud.estado.in_(("asignada", "confirmada")),
        )
        .order_by(Solicitud.franja_horaria.asc(), Solicitud.fecha_creacion.asc())
        .all()
    )


def asignar(db: Session, solicitud: Solicitud, reciclador_id: int) -> Solicitud:
    estado_anterior = solicitud.estado
    solicitud.reciclador_id = reciclador_id
    solicitud.estado = "asignada"
    solicitud.fecha_asignacion = datetime.now(timezone.utc)
    crud_historial.agregar(db, solicitud.id, estado_anterior, "asignada")
    db.commit()
    db.refresh(solicitud)
    return solicitud


def reasignar(db: Session, solicitud: Solicitud, nuevo_reciclador_id: int) -> Solicitud:
    """Cambia el reciclador asignado sin modificar el estado (sigue 'asignada')."""
    solicitud.reciclador_id = nuevo_reciclador_id
    solicitud.fecha_asignacion = datetime.now(timezone.utc)
    crud_historial.agregar(db, solicitud.id, "asignada", "asignada")
    db.commit()
    db.refresh(solicitud)
    return solicitud


def marcar_estado(
    db: Session, solicitud: Solicitud, nuevo_estado: str, actor_id: int | None = None,
) -> Solicitud:
    estado_anterior = solicitud.estado
    solicitud.estado = nuevo_estado
    crud_historial.agregar(db, solicitud.id, estado_anterior, nuevo_estado, usuario_id=actor_id)
    db.commit()
    db.refresh(solicitud)
    return solicitud


def resetear_asignacion(
    db: Session, solicitud: Solicitud, actor_id: int | None = None,
) -> Solicitud:
    """Limpia reciclador y vuelve a 'pendiente' (rechazar o timeout)."""
    estado_anterior = solicitud.estado
    solicitud.estado = "pendiente"
    solicitud.reciclador_id = None
    solicitud.fecha_asignacion = None
    crud_historial.agregar(db, solicitud.id, estado_anterior, "pendiente", usuario_id=actor_id)
    db.commit()
    db.refresh(solicitud)
    return solicitud
