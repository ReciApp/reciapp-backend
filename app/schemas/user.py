from datetime import datetime
from enum import Enum
from pydantic import BaseModel, ConfigDict, EmailStr, field_validator


class RolUsuario(str, Enum):
    ciudadano = "ciudadano"
    reciclador = "reciclador"
    admin = "admin"


class EstadoValidacion(str, Enum):
    pendiente = "pendiente"
    aprobado = "aprobado"
    rechazado = "rechazado"


class UsuarioCreate(BaseModel):
    nombre: str
    correo: EmailStr
    dni: str | None = None
    celular: str | None = None
    contrasena: str
    rol: RolUsuario = RolUsuario.ciudadano

    @field_validator("contrasena")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("La contraseña debe tener al menos 8 caracteres")
        return v

    @field_validator("dni")
    @classmethod
    def dni_format(cls, v: str | None) -> str | None:
        if v is not None:
            if not v.isdigit():
                raise ValueError("El DNI debe contener solo dígitos")
            if len(v) != 8:
                raise ValueError("El DNI debe tener exactamente 8 dígitos")
        return v


class RecicladorCreate(UsuarioCreate):
    rol: RolUsuario = RolUsuario.reciclador
    zona_cobertura: str
    disponibilidad_horaria: str


class UsuarioLogin(BaseModel):
    correo: EmailStr
    contrasena: str


class UsuarioUpdate(BaseModel):
    """Campos que un usuario puede modificar en su propio perfil."""
    nombre: str | None = None
    celular: str | None = None
    zona_cobertura: str | None = None
    disponibilidad_horaria: str | None = None


class ValidarReciclador(BaseModel):
    accion: EstadoValidacion


class UsuarioOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nombre: str
    correo: EmailStr
    rol: RolUsuario
    activo: bool
    verificado: bool
    fecha_registro: datetime | None = None
    zona_cobertura: str | None = None
    disponibilidad_horaria: str | None = None
    estado_validacion: str | None = None


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
