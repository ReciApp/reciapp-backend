import asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import FRONTEND_URL
from app.db.session import engine
from app.models.base import Base
import app.models  # noqa: F401 — registra todos los modelos en Base.metadata
from app.api.v1 import auth, users, solicitudes

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


@app.on_event("startup")
async def startup():
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


@app.get("/healthcheck", tags=["Sistema"])
def healthcheck():
    return {"status": "ok"}
