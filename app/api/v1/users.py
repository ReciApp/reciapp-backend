from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.api.v1.dependencies import get_current_user, require_role
from app.crud import crud_user
from app.db.session import get_db
from app.models.user import Usuario
from app.schemas.user import UsuarioOut, UsuarioUpdate, ValidarReciclador

router = APIRouter()


@router.get("/me", response_model=UsuarioOut)
def obtener_perfil(current_user: Usuario = Depends(get_current_user)):
    return current_user


@router.put("/me", response_model=UsuarioOut)
def actualizar_perfil(
    data: UsuarioUpdate,
    current_user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return crud_user.update_perfil(db, current_user, data)


# ── Endpoints exclusivos del admin ─────────────────────────────────────────────

@router.get(
    "/admin/recicladores-pendientes",
    response_model=list[UsuarioOut],
    dependencies=[Depends(require_role("admin"))],
)
def listar_recicladores_pendientes(db: Session = Depends(get_db)):
    return crud_user.get_recicladores_pendientes(db)


@router.put(
    "/admin/recicladores/{usuario_id}/validar",
    response_model=UsuarioOut,
    dependencies=[Depends(require_role("admin"))],
)
def validar_reciclador(
    usuario_id: int,
    data: ValidarReciclador,
    db: Session = Depends(get_db),
):
    usuario = crud_user.validar_reciclador(db, usuario_id, data.accion.value)
    if not usuario:
        raise HTTPException(status_code=404, detail="Reciclador no encontrado")
    return usuario
