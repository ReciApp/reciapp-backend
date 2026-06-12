from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.v1.dependencies import get_current_user, require_role
from app.crud import crud_evidencia, crud_solicitud, crud_user, crud_wallet
from app.db.session import get_db
from app.models.user import Usuario
from app.schemas.solicitud import SolicitudCreate, SolicitudOut
from app.services.asignacion import programar_asignacion_fallback, trigger_asignacion
from app.websockets.manager import manager

router = APIRouter()


@router.post(
    "",
    response_model=SolicitudOut,
    status_code=status.HTTP_201_CREATED,
    summary="Crear solicitud de recolección",
)
def crear_solicitud(
    data: SolicitudCreate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_role("ciudadano")),
):
    solicitud = crud_solicitud.create(db, data, current_user.id)

    # Queda visible para que cualquier reciclador la tome; si nadie lo hace,
    # programar_asignacion_fallback la asignará automáticamente más tarde.
    for r in crud_user.get_recicladores_activos(db):
        manager.notify_from_thread(r.id, {
            "tipo": "solicitud_disponible",
            "solicitud_id": solicitud.id,
            "ciudadano_id": solicitud.ciudadano_id,
            "tipo_residuo": solicitud.tipo_residuo,
            "cantidad_kg": solicitud.cantidad_kg,
            "direccion": solicitud.direccion,
            "fecha_recoleccion": solicitud.fecha_recoleccion,
            "franja_horaria": solicitud.franja_horaria,
            "latitud": solicitud.latitud,
            "longitud": solicitud.longitud,
        })
    programar_asignacion_fallback(solicitud.id)
    return solicitud


@router.get(
    "",
    response_model=list[SolicitudOut],
    summary="Listar mis solicitudes",
)
def listar_solicitudes(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    if current_user.rol == "reciclador":
        return crud_solicitud.get_by_reciclador(db, current_user.id)
    return crud_solicitud.get_by_ciudadano(db, current_user.id)


@router.get(
    "/disponibles",
    response_model=list[SolicitudOut],
    summary="Listar solicitudes pendientes que cualquier reciclador puede tomar",
)
def listar_disponibles(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_role("reciclador")),
):
    return crud_solicitud.get_pendientes(db)


@router.put(
    "/{solicitud_id}/tomar",
    response_model=SolicitudOut,
    summary="Reciclador toma una solicitud disponible (queda en camino de inmediato)",
)
def tomar_solicitud(
    solicitud_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_role("reciclador")),
):
    solicitud = crud_solicitud.tomar(db, solicitud_id, current_user.id)
    if not solicitud:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="La solicitud ya no está disponible — alguien más la tomó primero",
        )

    for r in crud_user.get_recicladores_activos(db):
        if r.id != current_user.id:
            manager.notify_from_thread(r.id, {"tipo": "solicitud_no_disponible", "solicitud_id": solicitud.id})

    manager.notify_from_thread(
        solicitud.ciudadano_id,
        {
            "tipo": "solicitud_en_camino",
            "solicitud_id": solicitud.id,
            "reciclador_id": solicitud.reciclador_id,
        },
    )
    return solicitud


@router.get(
    "/{solicitud_id}",
    response_model=SolicitudOut,
    summary="Obtener detalle de una solicitud",
)
def obtener_solicitud(
    solicitud_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    solicitud = crud_solicitud.get_by_id(db, solicitud_id)
    if not solicitud:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")

    if current_user.rol == "admin":
        return solicitud
    if current_user.rol == "ciudadano" and solicitud.ciudadano_id == current_user.id:
        return solicitud
    if current_user.rol == "reciclador" and solicitud.reciclador_id == current_user.id:
        return solicitud

    raise HTTPException(status_code=403, detail="No tienes acceso a esta solicitud")


@router.put(
    "/{solicitud_id}/aceptar",
    response_model=SolicitudOut,
    summary="Reciclador acepta la solicitud asignada",
)
def aceptar_solicitud(
    solicitud_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_role("reciclador")),
):
    solicitud = crud_solicitud.get_by_id(db, solicitud_id)
    if not solicitud:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")
    if solicitud.reciclador_id != current_user.id:
        raise HTTPException(status_code=403, detail="No eres el reciclador asignado a esta solicitud")
    if solicitud.estado != "asignada":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"La solicitud está en estado '{solicitud.estado}', no puede aceptarse",
        )

    solicitud = crud_solicitud.marcar_estado(db, solicitud, "en_camino", actor_id=current_user.id)

    manager.notify_from_thread(
        solicitud.ciudadano_id,
        {
            "tipo": "solicitud_en_camino",
            "solicitud_id": solicitud.id,
            "reciclador_id": solicitud.reciclador_id,
        },
    )
    return solicitud


@router.put(
    "/{solicitud_id}/rechazar",
    response_model=SolicitudOut,
    summary="Reciclador rechaza la solicitud; se dispara reasignación automática",
)
def rechazar_solicitud(
    solicitud_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_role("reciclador")),
):
    solicitud = crud_solicitud.get_by_id(db, solicitud_id)
    if not solicitud:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")
    if solicitud.reciclador_id != current_user.id:
        raise HTTPException(status_code=403, detail="No eres el reciclador asignado a esta solicitud")
    if solicitud.estado != "asignada":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"La solicitud está en estado '{solicitud.estado}', no puede rechazarse",
        )

    reciclador_rechazado_id = current_user.id
    solicitud = crud_solicitud.resetear_asignacion(db, solicitud, actor_id=current_user.id)

    manager.notify_from_thread(
        solicitud.ciudadano_id,
        {
            "tipo": "solicitud_reasignando",
            "solicitud_id": solicitud.id,
        },
    )

    background_tasks.add_task(trigger_asignacion, solicitud_id, 1, {reciclador_rechazado_id})
    return solicitud


@router.put(
    "/{solicitud_id}/confirmar",
    response_model=SolicitudOut,
    summary="Ciudadano confirma la recolección — acredita eco-créditos y marca completada",
)
def confirmar_recoleccion(
    solicitud_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_role("ciudadano")),
):
    solicitud = crud_solicitud.get_by_id(db, solicitud_id)
    if not solicitud:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")
    if solicitud.ciudadano_id != current_user.id:
        raise HTTPException(status_code=403, detail="No eres el ciudadano de esta solicitud")
    if solicitud.estado != "pendiente_confirmacion":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"La solicitud está en estado '{solicitud.estado}', no puede confirmarse",
        )

    evidencias = crud_evidencia.get_by_solicitud(db, solicitud_id)
    if not evidencias:
        raise HTTPException(status_code=400, detail="No hay evidencia registrada para confirmar")

    total_eco_creditos = sum(e.eco_creditos for e in evidencias)

    ciudadano = crud_user.sumar_eco_creditos(db, current_user.id, total_eco_creditos)
    crud_wallet.registrar_acreditacion(
        db, current_user.id, total_eco_creditos, solicitud_id=solicitud.id,
    )
    solicitud = crud_solicitud.marcar_estado(db, solicitud, "completada", actor_id=current_user.id)

    manager.notify_from_thread(
        solicitud.ciudadano_id,
        {
            "tipo": "eco_creditos_acreditados",
            "solicitud_id": solicitud.id,
            "eco_creditos": total_eco_creditos,
            "wallet_total": ciudadano.eco_creditos if ciudadano else total_eco_creditos,
        },
    )
    manager.notify_from_thread(
        solicitud.reciclador_id,
        {
            "tipo": "recoleccion_completada",
            "solicitud_id": solicitud.id,
        },
    )

    return solicitud
