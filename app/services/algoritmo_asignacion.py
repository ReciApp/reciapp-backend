import math

from sqlalchemy.orm import Session

from app.crud import crud_solicitud
from app.models.solicitud import Solicitud
from app.models.user import Usuario


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlon / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _recicladores_disponibles(
    db: Session,
    franja_horaria: str,
    excluir_ids: set[int] | None = None,
) -> list[Usuario]:
    candidatos = (
        db.query(Usuario)
        .filter(
            Usuario.rol == "reciclador",
            Usuario.estado_validacion == "aprobado",
            Usuario.activo == True,  # noqa: E712
        )
        .all()
    )
    if excluir_ids:
        candidatos = [r for r in candidatos if r.id not in excluir_ids]
    # Priorizar los que tienen la franja horaria coincidente
    con_franja = [
        r for r in candidatos
        if r.disponibilidad_horaria and franja_horaria in r.disponibilidad_horaria
    ]
    return con_franja if con_franja else candidatos


def _reciclador_mas_cercano(candidatos: list[Usuario], solicitud: Solicitud) -> Usuario | None:
    if not candidatos:
        return None

    if solicitud.latitud is None or solicitud.longitud is None:
        return candidatos[0]

    con_coords = [r for r in candidatos if r.latitud is not None and r.longitud is not None]
    if not con_coords:
        return candidatos[0]

    return min(
        con_coords,
        key=lambda r: _haversine_km(solicitud.latitud, solicitud.longitud, r.latitud, r.longitud),
    )


def asignar_solicitud(
    db: Session,
    solicitud: Solicitud,
    excluir_ids: set[int] | None = None,
) -> bool:
    """Busca el reciclador más cercano disponible y asigna la solicitud.

    Args:
        excluir_ids: IDs de recicladores a excluir (rechazaron previamente).

    Returns True si se asignó, False si no hay reciclador disponible.
    """
    candidatos = _recicladores_disponibles(db, solicitud.franja_horaria, excluir_ids)
    reciclador = _reciclador_mas_cercano(candidatos, solicitud)

    if not reciclador:
        return False

    crud_solicitud.asignar(db, solicitud, reciclador.id)
    return True
