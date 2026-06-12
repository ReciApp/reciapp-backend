from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.sql import func
from app.models.base import Base


class SolicitudHistorial(Base):
    """Trazabilidad de cada transición de estado de una solicitud:
    quién la hizo (None = sistema), cuándo, estado anterior y nuevo."""
    __tablename__ = "solicitud_historial"

    id = Column(Integer, primary_key=True, index=True)
    solicitud_id = Column(Integer, ForeignKey("solicitudes.id"), nullable=False, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    estado_anterior = Column(String(30), nullable=True)
    estado_nuevo = Column(String(30), nullable=False)
    fecha = Column(DateTime(timezone=True), server_default=func.now())
