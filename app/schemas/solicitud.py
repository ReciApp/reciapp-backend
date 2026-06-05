from datetime import datetime
from enum import Enum
from pydantic import BaseModel, ConfigDict, field_validator


class TipoResiduo(str, Enum):
    plastico = "plastico"
    papel = "papel"
    vidrio = "vidrio"
    metal = "metal"
    organico = "organico"
    electronico = "electronico"


class FranjaHoraria(str, Enum):
    manana = "manana"
    tarde = "tarde"
    noche = "noche"


class EstadoSolicitud(str, Enum):
    pendiente = "pendiente"
    asignada = "asignada"
    en_camino = "en_camino"
    pendiente_confirmacion = "pendiente_confirmacion"
    completada = "completada"
    cancelada = "cancelada"


class SolicitudCreate(BaseModel):
    tipo_residuo: TipoResiduo
    cantidad_kg: float
    fecha_recoleccion: str
    franja_horaria: FranjaHoraria
    direccion: str
    latitud: float | None = None
    longitud: float | None = None

    @field_validator("cantidad_kg")
    @classmethod
    def cantidad_positiva(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("La cantidad debe ser mayor a 0 kg")
        return v

    @field_validator("fecha_recoleccion")
    @classmethod
    def fecha_formato(cls, v: str) -> str:
        import re
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
            raise ValueError("La fecha debe tener formato YYYY-MM-DD")
        return v

    @field_validator("direccion")
    @classmethod
    def direccion_no_vacia(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("La dirección no puede estar vacía")
        return v.strip()


class SolicitudOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    numero_seguimiento: str
    ciudadano_id: int
    tipo_residuo: str
    cantidad_kg: float
    fecha_recoleccion: str
    franja_horaria: str
    direccion: str
    latitud: float | None
    longitud: float | None
    estado: str
    reciclador_id: int | None
    fecha_asignacion: datetime | None
    fecha_creacion: datetime | None
    fecha_actualizacion: datetime | None
