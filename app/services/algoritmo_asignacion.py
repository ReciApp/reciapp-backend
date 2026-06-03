# Stub — implementación completa en RECI-36
from sqlalchemy.orm import Session
from app.models.solicitud import Solicitud


def asignar_solicitud(db: Session, solicitud: Solicitud) -> bool:
    """Asigna un reciclador a la solicitud. Devuelve True si se asignó."""
    return False
