from sqlalchemy.orm import Session
from app.models.solicitud_historial import SolicitudHistorial


def agregar(
    db: Session,
    solicitud_id: int,
    estado_anterior: str | None,
    estado_nuevo: str,
    usuario_id: int | None = None,
) -> SolicitudHistorial:
    """Agrega la transición a la sesión sin hacer commit: queda en la misma
    transacción que el cambio de estado que la originó."""
    registro = SolicitudHistorial(
        solicitud_id=solicitud_id,
        usuario_id=usuario_id,
        estado_anterior=estado_anterior,
        estado_nuevo=estado_nuevo,
    )
    db.add(registro)
    return registro


def get_by_solicitud(db: Session, solicitud_id: int) -> list[SolicitudHistorial]:
    return (
        db.query(SolicitudHistorial)
        .filter(SolicitudHistorial.solicitud_id == solicitud_id)
        .order_by(SolicitudHistorial.fecha.asc(), SolicitudHistorial.id.asc())
        .all()
    )


def get_by_solicitudes(db: Session, solicitud_ids: list[int]) -> list[SolicitudHistorial]:
    if not solicitud_ids:
        return []
    return (
        db.query(SolicitudHistorial)
        .filter(SolicitudHistorial.solicitud_id.in_(solicitud_ids))
        .order_by(SolicitudHistorial.fecha.asc(), SolicitudHistorial.id.asc())
        .all()
    )
