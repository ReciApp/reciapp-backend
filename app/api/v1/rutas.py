from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.v1.dependencies import require_role
from app.crud import crud_solicitud
from app.db.session import get_db
from app.models.user import Usuario
from app.services import ruteo

router = APIRouter()

ESTADOS_OPTIMIZABLES = ("asignada", "en_camino")


class OptimizarRequest(BaseModel):
    origen_lat: float
    origen_lon: float
    solicitud_ids: list[int] = Field(..., min_length=1)


class ParadaOut(BaseModel):
    orden: int
    solicitud_id: int
    direccion: str
    latitud: float
    longitud: float
    distancia_km: float
    eta_min: int
    ruta: list[list[float]]


class OptimizarResponse(BaseModel):
    paradas: list[ParadaOut]
    distancia_total_km: float
    eta_total_min: int


@router.post(
    "/optimizar",
    response_model=OptimizarResponse,
    summary="Ruta óptima multi-punto (A* + vecino más cercano con mejora 2-opt)",
)
def optimizar_ruta(
    data: OptimizarRequest,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_role("reciclador")),
):
    solicitudes = []
    for solicitud_id in dict.fromkeys(data.solicitud_ids):
        solicitud = crud_solicitud.get_by_id(db, solicitud_id)
        if not solicitud:
            raise HTTPException(status_code=404, detail=f"Solicitud {solicitud_id} no encontrada")
        if solicitud.reciclador_id != current_user.id:
            raise HTTPException(
                status_code=403,
                detail=f"La solicitud {solicitud_id} no está asignada a ti",
            )
        if solicitud.estado not in ESTADOS_OPTIMIZABLES:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"La solicitud {solicitud_id} está en estado '{solicitud.estado}', "
                       "no puede incluirse en la ruta",
            )
        if solicitud.latitud is None or solicitud.longitud is None:
            raise HTTPException(
                status_code=400,
                detail=f"La solicitud {solicitud_id} no tiene coordenadas registradas",
            )
        solicitudes.append(solicitud)

    orden, tramos = ruteo.optimizar_multipunto(
        (data.origen_lat, data.origen_lon),
        [(s.latitud, s.longitud) for s in solicitudes],
    )

    paradas = []
    for posicion, (idx, tramo) in enumerate(zip(orden, tramos), start=1):
        solicitud = solicitudes[idx]
        paradas.append(ParadaOut(
            orden=posicion,
            solicitud_id=solicitud.id,
            direccion=solicitud.direccion,
            latitud=solicitud.latitud,
            longitud=solicitud.longitud,
            distancia_km=round(tramo["distancia_km"], 3),
            eta_min=ruteo.calcular_eta_min(tramo["distancia_km"]),
            ruta=[[lat, lon] for lat, lon in tramo["coords"]],
        ))

    distancia_total = sum(t["distancia_km"] for t in tramos)
    return OptimizarResponse(
        paradas=paradas,
        distancia_total_km=round(distancia_total, 3),
        eta_total_min=ruteo.calcular_eta_min(distancia_total),
    )
