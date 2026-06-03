from datetime import datetime
from pydantic import BaseModel, ConfigDict


class EvidenciaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    solicitud_id: int
    reciclador_id: int
    foto_url: str
    peso_kg: float
    tipo_residuo: str
    eco_creditos: float
    fecha_registro: datetime | None
