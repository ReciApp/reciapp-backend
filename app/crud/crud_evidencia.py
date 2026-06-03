from sqlalchemy.orm import Session
from app.core.eco_creditos import calcular
from app.models.evidencia import Evidencia


def create(
    db: Session,
    solicitud_id: int,
    reciclador_id: int,
    foto_url: str,
    peso_kg: float,
    tipo_residuo: str,
) -> Evidencia:
    evidencia = Evidencia(
        solicitud_id=solicitud_id,
        reciclador_id=reciclador_id,
        foto_url=foto_url,
        peso_kg=peso_kg,
        tipo_residuo=tipo_residuo,
        eco_creditos=calcular(tipo_residuo, peso_kg),
    )
    db.add(evidencia)
    db.commit()
    db.refresh(evidencia)
    return evidencia


def get_by_solicitud(db: Session, solicitud_id: int) -> list[Evidencia]:
    return db.query(Evidencia).filter(Evidencia.solicitud_id == solicitud_id).all()
