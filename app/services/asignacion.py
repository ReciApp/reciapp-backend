import threading

from app.db.session import SessionLocal

MAX_INTENTOS = 3
INTERVALO_REINTENTO_SEG = 900  # 15 minutos


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


def trigger_asignacion(solicitud_id: int, intento: int = 1) -> None:
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
        asignado = asignar_solicitud(db, solicitud)

        if asignado:
            _notificar_asignacion(solicitud_id)
        elif intento < MAX_INTENTOS:
            t = threading.Timer(
                INTERVALO_REINTENTO_SEG,
                trigger_asignacion,
                args=(solicitud_id, intento + 1),
            )
            t.daemon = True
            t.start()
    finally:
        db.close()
