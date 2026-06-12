import math
from datetime import datetime
from pydantic import BaseModel, ConfigDict


class TransaccionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tipo: str
    monto: float
    descripcion: str | None
    solicitud_id: int | None
    reward_id: int | None
    voucher: str | None
    fecha: datetime | None


class WalletOut(BaseModel):
    saldo: float
    pagina: int
    total_paginas: int
    total_transacciones: int
    transacciones: list[TransaccionOut]

    @staticmethod
    def total_paginas_de(total: int, por_pagina: int) -> int:
        return max(1, math.ceil(total / por_pagina))


class CanjeOut(BaseModel):
    voucher: str
    reward_id: int
    reward_nombre: str
    costo_creditos: float
    saldo_restante: float
