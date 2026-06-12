from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class CalificacionCreate(BaseModel):
    solicitud_id: int
    puntuacion: int = Field(..., ge=1, le=5)
    comentario: str | None = Field(None, max_length=500)


class CalificacionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    solicitud_id: int
    ciudadano_id: int
    reciclador_id: int
    puntuacion: int
    comentario: str | None
    fecha: datetime | None


class CalificacionResultadoOut(CalificacionOut):
    """Calificación creada + promedio actualizado del reciclador."""
    promedio_reciclador: float
    total_calificaciones: int
