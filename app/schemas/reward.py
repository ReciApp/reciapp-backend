from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class RewardCreate(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=100)
    descripcion: str | None = Field(None, max_length=300)
    costo_creditos: float = Field(..., gt=0)
    stock: int = Field(..., ge=0)
    activo: bool = True


class RewardUpdate(BaseModel):
    nombre: str | None = Field(None, min_length=1, max_length=100)
    descripcion: str | None = Field(None, max_length=300)
    costo_creditos: float | None = Field(None, gt=0)
    stock: int | None = Field(None, ge=0)


class RewardOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nombre: str
    descripcion: str | None
    costo_creditos: float
    stock: int
    activo: bool
    fecha_creacion: datetime | None
    fecha_actualizacion: datetime | None
