import asyncio
import threading
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import FRONTEND_URL
from app.db.session import engine
from app.models.base import Base
import app.models  # noqa: F401 — registra todos los modelos en Base.metadata
from app.api.v1 import auth, users, solicitudes, evidencias, reciclador, rutas, ws
from app.api.v1 import ruteo as ruteo_api
from app.services.ruteo import _init_grafo as _init_ruteo
from app.websockets.manager import manager

app = FastAPI(
    title="ReciApp API",
    description="Autenticación, gestión de usuarios y solicitudes de recolección",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(auth.router, prefix="/auth", tags=["Autenticación"])
app.include_router(users.router, prefix="/api/usuarios", tags=["Usuarios"])
app.include_router(solicitudes.router, prefix="/api/solicitudes", tags=["Solicitudes"])
app.include_router(evidencias.router, prefix="/api/evidencias", tags=["Evidencias"])
app.include_router(ruteo_api.router, prefix="/api/ruteo", tags=["Ruteo"])
app.include_router(rutas.router, prefix="/api/rutas", tags=["Rutas"])
app.include_router(reciclador.router, prefix="/api/reciclador", tags=["Reciclador"])
app.include_router(ws.router, tags=["WebSocket"])


@app.on_event("startup")
async def startup():
    manager.set_loop(asyncio.get_event_loop())
    threading.Thread(target=_init_ruteo, daemon=True).start()
    max_retries = 20
    for attempt in range(max_retries):
        try:
            Base.metadata.create_all(bind=engine)
            print("Tablas creadas exitosamente")
            return
        except Exception as exc:
            if attempt < max_retries - 1:
                print(f"Esperando base de datos... intento {attempt + 1}/{max_retries}: {exc}")
                await asyncio.sleep(2)
            else:
                raise


import os as _os
_os.makedirs("uploads/evidencias", exist_ok=True)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")


@app.get("/healthcheck", tags=["Sistema"])
def healthcheck():
    return {"status": "ok"}
