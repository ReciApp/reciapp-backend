from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.sql import func
from app.models.base import Base


class Evidencia(Base):
    __tablename__ = "evidencias"

    id = Column(Integer, primary_key=True, index=True)
    solicitud_id = Column(Integer, ForeignKey("solicitudes.id"), nullable=False, index=True)
    reciclador_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False, index=True)

    foto_url = Column(String(500), nullable=False)
    peso_kg = Column(Float, nullable=False)
    tipo_residuo = Column(String(50), nullable=False)
    eco_creditos = Column(Float, nullable=False)

    fecha_registro = Column(DateTime(timezone=True), server_default=func.now())
