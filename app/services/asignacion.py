import threading

from app.db.session import SessionLocal

MAX_INTENTOS = 3
INTERVALO_REINTENTO_SEG = 900  # 15 minutos


def trigger_asignacion(solicitud_id: int, intento: int = 1) -> None:
    """Lanza la asignación en background; se llama desde BackgroundTasks del endpoint."""
    if intento > MAX_INTENTOS:
        return

    db = SessionLocal()
    try:
        from app.crud import crud_solicitud  # import local para evitar ciclos
        solicitud = crud_solicitud.get_by_id(db, solicitud_id)
        if not solicitud or solicitud.estado != "pendiente":
            return

        from app.services.algoritmo_asignacion import asignar_solicitud
        asignado = asignar_solicitud(db, solicitud)

        if not asignado and intento < MAX_INTENTOS:
            t = threading.Timer(
                INTERVALO_REINTENTO_SEG,
                trigger_asignacion,
                args=(solicitud_id, intento + 1),
            )
            t.daemon = True
            t.start()
    finally:
        db.close()
