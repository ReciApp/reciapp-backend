import uuid

from sqlalchemy.orm import Session
from app.models.wallet_transaccion import WalletTransaccion

TRANSACCIONES_POR_PAGINA = 10


def generar_voucher() -> str:
    return f"RECI-{uuid.uuid4().hex[:10].upper()}"


def registrar_acreditacion(
    db: Session,
    usuario_id: int,
    monto: float,
    solicitud_id: int | None = None,
    descripcion: str | None = None,
) -> WalletTransaccion:
    transaccion = WalletTransaccion(
        usuario_id=usuario_id,
        tipo="acreditacion",
        monto=round(monto, 2),
        solicitud_id=solicitud_id,
        descripcion=descripcion or "Eco-créditos por recolección",
    )
    db.add(transaccion)
    db.commit()
    db.refresh(transaccion)
    return transaccion


def registrar_canje(
    db: Session,
    usuario_id: int,
    reward_id: int,
    costo: float,
    descripcion: str | None = None,
) -> WalletTransaccion:
    """Agrega el movimiento de canje a la sesión sin commit: el endpoint lo
    confirma junto con el descuento de saldo y stock en una sola transacción."""
    transaccion = WalletTransaccion(
        usuario_id=usuario_id,
        tipo="canje",
        monto=-round(costo, 2),
        reward_id=reward_id,
        voucher=generar_voucher(),
        descripcion=descripcion,
    )
    db.add(transaccion)
    return transaccion


def get_paginado(
    db: Session, usuario_id: int, pagina: int = 1,
) -> tuple[list[WalletTransaccion], int]:
    """Devuelve (transacciones de la página, total de registros)."""
    query = (
        db.query(WalletTransaccion)
        .filter(WalletTransaccion.usuario_id == usuario_id)
        .order_by(WalletTransaccion.fecha.desc(), WalletTransaccion.id.desc())
    )
    total = query.count()
    transacciones = (
        query.offset((pagina - 1) * TRANSACCIONES_POR_PAGINA)
        .limit(TRANSACCIONES_POR_PAGINA)
        .all()
    )
    return transacciones, total
