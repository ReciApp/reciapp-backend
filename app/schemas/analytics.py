from pydantic import BaseModel


class PuntoSerie(BaseModel):
    fecha: str
    kg: float


class ResumenAnalytics(BaseModel):
    total_solicitudes: int
    completadas: int
    total_kg_reciclados: float
    eco_creditos_otorgados: float
    calificacion_promedio: float | None
    total_calificaciones: int
    por_estado: dict[str, int]
    por_tipo_residuo: dict[str, int]
    serie_kg_por_dia: list[PuntoSerie]


class PuntoHeatmap(BaseModel):
    lat: float
    lon: float
    peso: float
