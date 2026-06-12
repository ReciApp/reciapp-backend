from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.v1.dependencies import require_role
from app.crud import crud_reward, crud_wallet
from app.crud.crud_wallet import TRANSACCIONES_POR_PAGINA
from app.db.session import get_db
from app.models.user import Usuario
from app.schemas.wallet import CanjeOut, TransaccionOut, WalletOut

router = APIRouter()


@router.get(
    "/me",
    response_model=WalletOut,
    summary="Mi wallet: saldo de eco-créditos e historial paginado (10 por página)",
)
def mi_wallet(
    pagina: int = Query(1, ge=1),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_role("ciudadano")),
):
    transacciones, total = crud_wallet.get_paginado(db, current_user.id, pagina)
    return WalletOut(
        saldo=current_user.eco_creditos or 0.0,
        pagina=pagina,
        total_paginas=WalletOut.total_paginas_de(total, TRANSACCIONES_POR_PAGINA),
        total_transacciones=total,
        transacciones=[TransaccionOut.model_validate(t) for t in transacciones],
    )


@router.post(
    "/me/canjear/{reward_id}",
    response_model=CanjeOut,
    summary="Canjear una recompensa: descuenta saldo y stock, genera voucher único",
)
def canjear_reward(
    reward_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_role("ciudadano")),
):
    reward = crud_reward.get_by_id(db, reward_id)
    if not reward or not reward.activo:
        raise HTTPException(status_code=404, detail="Recompensa no disponible")

    saldo = current_user.eco_creditos or 0.0
    if saldo < reward.costo_creditos:
        raise HTTPException(status_code=400, detail="Saldo de eco-créditos insuficiente")

    if not crud_reward.descontar_stock(db, reward_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="La recompensa no tiene stock disponible",
        )

    # Saldo, stock y movimiento se confirman en una sola transacción
    current_user.eco_creditos = round(saldo - reward.costo_creditos, 2)
    transaccion = crud_wallet.registrar_canje(
        db, current_user.id, reward_id, reward.costo_creditos,
        descripcion=f"Canje: {reward.nombre}",
    )
    db.commit()
    db.refresh(transaccion)

    return CanjeOut(
        voucher=transaccion.voucher,
        reward_id=reward.id,
        reward_nombre=reward.nombre,
        costo_creditos=reward.costo_creditos,
        saldo_restante=current_user.eco_creditos,
    )
