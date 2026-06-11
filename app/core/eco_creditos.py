ECO_CREDITOS_POR_KG: dict[str, float] = {
    "plastico": 10.0,
    "papel": 5.0,
    "vidrio": 8.0,
    "metal": 15.0,
    "organico": 3.0,
    "electronicos": 20.0,
    "carton": 5.0,
}


def calcular(tipo_residuo: str, peso_kg: float) -> float:
    creditos_por_kg = ECO_CREDITOS_POR_KG.get(tipo_residuo, 5.0)
    return round(creditos_por_kg * peso_kg, 2)
