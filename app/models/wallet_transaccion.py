from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.sql import func
from app.models.base import Base


class WalletTransaccion(Base):
    """Movimiento de eco-créditos: acreditación por reciclaje (monto positivo)
    o canje de recompensa (monto negativo, con voucher único)."""
    __tablename__ = "wallet_transacciones"

    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False, index=True)
    tipo = Column(String(20), nullable=False)  # acreditacion | canje
    monto = Column(Float, nullable=False)
    descripcion = Column(String(200), nullable=True)
    solicitud_id = Column(Integer, ForeignKey("solicitudes.id"), nullable=True)
    reward_id = Column(Integer, ForeignKey("rewards.id"), nullable=True)
    voucher = Column(String(30), unique=True, nullable=True, index=True)
    fecha = Column(DateTime(timezone=True), server_default=func.now())
