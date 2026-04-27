import asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import FRONTEND_URL
from app.db.session import engine
from app.models.base import Base
from app.api.v1 import auth, users

app = FastAPI(
    title="ReciApp API — Entregable 1",
    description="Autenticación y gestión de usuarios",
    version="1.0.0",
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
