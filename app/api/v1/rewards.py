from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.v1.dependencies import get_current_user, require_role
from app.crud import crud_reward
from app.db.session import get_db
from app.models.user import Usuario
from app.schemas.reward import RewardCreate, RewardOut, RewardUpdate

router_admin = APIRouter()
router_catalogo = APIRouter()


# ── Administración (solo admin) ───────────────────────────────────────────────

@router_admin.get(
    "",
    response_model=list[RewardOut],
    summary="Listar todas las recompensas (incluye inactivas)",
)
def listar_rewards(
    db: Session = Depends(get_db),
    _: Usuario = Depends(require_role("admin")),
):
    return crud_reward.get_all(db)


@router_admin.post(
    "",
    response_model=RewardOut,
    status_code=status.HTTP_201_CREATED,
    summary="Crear recompensa",
)
def crear_reward(
    data: RewardCreate,
    db: Session = Depends(get_db),
    _: Usuario = Depends(require_role("admin")),
):
    return crud_reward.create(db, data)


@router_admin.put(
    "/{reward_id}",
    response_model=RewardOut,
    summary="Editar recompensa",
)
def editar_reward(
    reward_id: int,
    data: RewardUpdate,
    db: Session = Depends(get_db),
    _: Usuario = Depends(require_role("admin")),
):
    reward = crud_reward.get_by_id(db, reward_id)
    if not reward:
        raise HTTPException(status_code=404, detail="Recompensa no encontrada")
    return crud_reward.update(db, reward, data)


@router_admin.patch(
    "/{reward_id}/toggle",
    response_model=RewardOut,
    summary="Activar o desactivar recompensa",
)
def toggle_reward(
    reward_id: int,
    db: Session = Depends(get_db),
    _: Usuario = Depends(require_role("admin")),
):
    reward = crud_reward.get_by_id(db, reward_id)
    if not reward:
        raise HTTPException(status_code=404, detail="Recompensa no encontrada")
    return crud_reward.toggle(db, reward)


# ── Catálogo (cualquier usuario autenticado) ─────────────────────────────────

@router_catalogo.get(
    "",
    response_model=list[RewardOut],
    summary="Catálogo de recompensas activas",
)
def catalogo_rewards(
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    return crud_reward.get_activos(db)
