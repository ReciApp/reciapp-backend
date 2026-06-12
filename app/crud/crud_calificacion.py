from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.calificacion import Calificacion
from app.models.user import Usuario


def get_by_solicitud(db: Session, solicitud_id: int) -> Calificacion | None:
    return (
        db.query(Calificacion)
        .filter(Calificacion.solicitud_id == solicitud_id)
        .first()
    )


def create(
    db: Session,
    solicitud_id: int,
    ciudadano_id: int,
    reciclador_id: int,
    puntuacion: int,
    comentario: str | None,
) -> Calificacion:
    """Crea la calificación y recalcula el promedio del reciclador en la
    misma transacción, para que quede actualizado de inmediato."""
    calificacion = Calificacion(
        solicitud_id=solicitud_id,
        ciudadano_id=ciudadano_id,
        reciclador_id=reciclador_id,
        puntuacion=puntuacion,
        comentario=comentario,
    )
    db.add(calificacion)
    db.flush()

    promedio, total = (
        db.query(func.avg(Calificacion.puntuacion), func.count(Calificacion.id))
        .filter(Calificacion.reciclador_id == reciclador_id)
        .one()
    )
    reciclador = db.query(Usuario).filter(Usuario.id == reciclador_id).first()
    if reciclador:
        reciclador.calificacion_promedio = round(float(promedio), 2)
        reciclador.total_calificaciones = int(total)

    db.commit()
    db.refresh(calificacion)
    return calificacion
