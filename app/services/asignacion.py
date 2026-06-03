import threading

from app.db.session import SessionLocal

MAX_INTENTOS = 3
INTERVALO_REINTENTO_SEG = 900   # 15 minutos entre reintentos de asignación inicial
TIMEOUT_RESPUESTA_SEG = 600     # 10 minutos para que el reciclador acepte o rechace


def _notificar_asignacion(solicitud_id: int) -> None:
    """Emite notificaciones WebSocket a reciclador y ciudadano tras asignación."""
    from app.crud import crud_solicitud
    from app.websockets.manager import manager

    db = SessionLocal()
    try:
        solicitud = crud_solicitud.get_by_id(db, solicitud_id)
        if not solicitud:
            return

        manager.notify_from_thread(
            solicitud.reciclador_id,
            {
                "tipo": "nueva_solicitud",
                "solicitud_id": solicitud.id,
                "ciudadano_id": solicitud.ciudadano_id,
                "tipo_residuo": solicitud.tipo_residuo,
                "cantidad_kg": solicitud.cantidad_kg,
                "direccion": solicitud.direccion,
                "fecha_recoleccion": solicitud.fecha_recoleccion,
                "franja_horaria": solicitud.franja_horaria,
                "latitud": solicitud.latitud,
                "longitud": solicitud.longitud,
            },
        )
        manager.notify_from_thread(
            solicitud.ciudadano_id,
            {
                "tipo": "solicitud_asignada",
                "solicitud_id": solicitud.id,
                "reciclador_id": solicitud.reciclador_id,
            },
        )
    finally:
        db.close()


def trigger_timeout_reasignacion(solicitud_id: int, reciclador_id_actual: int) -> None:
    """Reasigna automáticamente si el reciclador no respondió en TIMEOUT_RESPUESTA_SEG."""
    db = SessionLocal()
    try:
        from app.crud import crud_solicitud
        from app.websockets.manager import manager

        solicitud = crud_solicitud.get_by_id(db, solicitud_id)
        if not solicitud:
            return
        # Si ya fue aceptada, rechazada o reasignada por otra causa, no hacer nada
        if solicitud.estado != "asignada" or solicitud.reciclador_id != reciclador_id_actual:
            return

        manager.notify_from_thread(
            solicitud.ciudadano_id,
            {
                "tipo": "solicitud_reasignando",
                "solicitud_id": solicitud.id,
                "razon": "timeout",
            },
        )
        crud_solicitud.resetear_asignacion(db, solicitud)
    finally:
        db.close()

    # Reasignar en nueva sesión excluyendo al reciclador que no respondió
    trigger_asignacion(solicitud_id, excluir_ids={reciclador_id_actual})


def trigger_asignacion(
    solicitud_id: int,
    intento: int = 1,
    excluir_ids: set[int] | None = None,
) -> None:
    """Lanza la asignación en background; se llama desde BackgroundTasks del endpoint."""
    if intento > MAX_INTENTOS:
        return

    db = SessionLocal()
    try:
        from app.crud import crud_solicitud
        solicitud = crud_solicitud.get_by_id(db, solicitud_id)
        if not solicitud or solicitud.estado != "pendiente":
            return

        from app.services.algoritmo_asignacion import asignar_solicitud
        asignado = asignar_solicitud(db, solicitud, excluir_ids)

        if asignado:
            reciclador_id = solicitud.reciclador_id  # capturar antes de db.close()
            _notificar_asignacion(solicitud_id)

            t = threading.Timer(
                TIMEOUT_RESPUESTA_SEG,
                trigger_timeout_reasignacion,
                args=(solicitud_id, reciclador_id),
            )
            t.daemon = True
            t.start()
        elif intento < MAX_INTENTOS:
            t = threading.Timer(
                INTERVALO_REINTENTO_SEG,
                trigger_asignacion,
                args=(solicitud_id, intento + 1),
                kwargs={"excluir_ids": excluir_ids},
            )
            t.daemon = True
            t.start()
    finally:
        db.close()
