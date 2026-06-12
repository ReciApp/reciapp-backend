from sqlalchemy import update as sa_update
from sqlalchemy.orm import Session
from app.models.reward import Reward
from app.schemas.reward import RewardCreate, RewardUpdate


def create(db: Session, data: RewardCreate) -> Reward:
    reward = Reward(**data.model_dump())
    db.add(reward)
    db.commit()
    db.refresh(reward)
    return reward


def get_by_id(db: Session, reward_id: int) -> Reward | None:
    return db.query(Reward).filter(Reward.id == reward_id).first()


def get_all(db: Session) -> list[Reward]:
    return db.query(Reward).order_by(Reward.fecha_creacion.desc()).all()


def get_activos(db: Session) -> list[Reward]:
    """Catálogo visible para el ciudadano: solo recompensas activas."""
    return (
        db.query(Reward)
        .filter(Reward.activo == True)  # noqa: E712
        .order_by(Reward.costo_creditos.asc())
        .all()
    )


def update(db: Session, reward: Reward, data: RewardUpdate) -> Reward:
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(reward, field, value)
    db.commit()
    db.refresh(reward)
    return reward


def toggle(db: Session, reward: Reward) -> Reward:
    reward.activo = not reward.activo
    db.commit()
    db.refresh(reward)
    return reward


def descontar_stock(db: Session, reward_id: int) -> bool:
    """Descuenta una unidad de stock de forma atómica; el stock nunca queda
    negativo porque el UPDATE exige stock > 0. Devuelve False si no había stock."""
    resultado = db.execute(
        sa_update(Reward)
        .where(Reward.id == reward_id, Reward.stock > 0, Reward.activo == True)  # noqa: E712
        .values(stock=Reward.stock - 1)
    )
    return resultado.rowcount > 0
