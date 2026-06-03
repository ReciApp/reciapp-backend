import os
import shutil
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.api.v1.dependencies import require_role
from app.crud import crud_evidencia, crud_solicitud
from app.db.session import get_db
from app.models.user import Usuario
from app.schemas.evidencia import EvidenciaOut

router = APIRouter()

UPLOAD_DIR = "uploads/evidencias"
os.makedirs(UPLOAD_DIR, exist_ok=True)

EXTENSIONES_PERMITIDAS = {"jpg", "jpeg", "png", "webp"}


@router.post(
    "",
    response_model=EvidenciaOut,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar evidencia de recolección",
)
def registrar_evidencia(
    solicitud_id: int = Form(...),
    peso_kg: float = Form(...),
    foto: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_role("reciclador")),
):
    solicitud = crud_solicitud.get_by_id(db, solicitud_id)
    if not solicitud:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")
    if solicitud.reciclador_id != current_user.id:
        raise HTTPException(status_code=403, detail="No eres el reciclador asignado a esta solicitud")
    if solicitud.estado not in ("asignada", "en_camino"):
        raise HTTPException(
            status_code=400,
            detail=f"No se puede registrar evidencia en estado '{solicitud.estado}'",
        )
    if peso_kg <= 0:
        raise HTTPException(status_code=422, detail="El peso debe ser mayor a 0 kg")

    ext = (foto.filename or "foto").rsplit(".", 1)[-1].lower()
    if ext not in EXTENSIONES_PERMITIDAS:
        raise HTTPException(status_code=422, detail="Formato de imagen no permitido (jpg, jpeg, png, webp)")

    filename = f"{uuid.uuid4()}.{ext}"
    filepath = os.path.join(UPLOAD_DIR, filename)
    with open(filepath, "wb") as f:
        shutil.copyfileobj(foto.file, f)

    foto_url = f"/uploads/evidencias/{filename}"

    evidencia = crud_evidencia.create(
        db,
        solicitud_id=solicitud_id,
        reciclador_id=current_user.id,
        foto_url=foto_url,
        peso_kg=peso_kg,
        tipo_residuo=solicitud.tipo_residuo,
    )
    return evidencia
