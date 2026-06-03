import uuid
from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.sql import func
from app.models.base import Base


class Solicitud(Base):
    __tablename__ = "solicitudes"

    id = Column(Integer, primary_key=True, index=True)
    numero_seguimiento = Column(String(36), unique=True, nullable=False, index=True,
                                default=lambda: str(uuid.uuid4()))
    ciudadano_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False, index=True)

    tipo_residuo = Column(String(50), nullable=False)
    cantidad_kg = Column(Float, nullable=False)
    fecha_recoleccion = Column(String(10), nullable=False)   # YYYY-MM-DD
    franja_horaria = Column(String(10), nullable=False)      # manana | tarde | noche

    direccion = Column(String(300), nullable=False)
    latitud = Column(Float, nullable=True)
    longitud = Column(Float, nullable=True)

    estado = Column(String(20), nullable=False, default="pendiente")
    reciclador_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True, index=True)
    fecha_asignacion = Column(DateTime(timezone=True), nullable=True)

    fecha_creacion = Column(DateTime(timezone=True), server_default=func.now())
    fecha_actualizacion = Column(DateTime(timezone=True), server_default=func.now(),
                                  onupdate=func.now())
