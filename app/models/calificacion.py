from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.sql import func
from app.models.base import Base


class Calificacion(Base):
    """Calificación post-servicio: una por solicitud, emitida por el ciudadano."""
    __tablename__ = "calificaciones"

    id = Column(Integer, primary_key=True, index=True)
    solicitud_id = Column(Integer, ForeignKey("solicitudes.id"), unique=True,
                          nullable=False, index=True)
    ciudadano_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    reciclador_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False, index=True)
    puntuacion = Column(Integer, nullable=False)  # 1 a 5 estrellas
    comentario = Column(String(500), nullable=True)
    fecha = Column(DateTime(timezone=True), server_default=func.now())
