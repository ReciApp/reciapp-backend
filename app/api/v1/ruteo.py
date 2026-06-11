from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.v1.dependencies import get_current_user
from app.services import ruteo

router = APIRouter()


class RuteoRequest(BaseModel):
    origen_lat: float
    origen_lon: float
    destino_lat: float
    destino_lon: float


class RuteoResponse(BaseModel):
    ruta: list[list[float]]
    distancia_km: float
    eta_min: int


@router.post("", response_model=RuteoResponse, summary="Calcular ruta entre dos puntos (A*)")
def calcular_ruta(
    data: RuteoRequest,
    _=Depends(get_current_user),
):
    coords, dist = ruteo.calcular_ruta(
        data.origen_lat, data.origen_lon,
        data.destino_lat, data.destino_lon,
    )
    if not coords:
        raise HTTPException(status_code=404, detail="Sin ruta disponible entre los puntos")
    return RuteoResponse(
        ruta=[[lat, lon] for lat, lon in coords],
        distancia_km=round(dist, 3),
        eta_min=ruteo.calcular_eta_min(dist),
    )
