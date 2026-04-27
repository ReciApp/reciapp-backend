from sqlalchemy import Boolean, Column, DateTime, Integer, String
from sqlalchemy.sql import func
from app.models.base import Base


class Usuario(Base):
    __tablename__ = "usuarios"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(100), nullable=False)
    dni = Column(String(8), unique=True, nullable=True, index=True)
    correo = Column(String(120), unique=True, nullable=False, index=True)
    celular = Column(String(15), nullable=True)
    contrasena = Column(String(255), nullable=False)
    rol = Column(String(50), nullable=False, default="ciudadano")
    activo = Column(Boolean, default=True, nullable=False)
    verificado = Column(Boolean, default=False, nullable=False)
    fecha_registro = Column(DateTime(timezone=True), server_default=func.now())

    # Campos exclusivos del reciclador
    zona_cobertura = Column(String(200), nullable=True)
    disponibilidad_horaria = Column(String(200), nullable=True)
    # pendiente | aprobado | rechazado — solo aplica al rol reciclador
    estado_validacion = Column(String(20), nullable=True)
