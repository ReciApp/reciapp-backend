"""Cliente del chatbot de ReciApp sobre la API de NVIDIA (compatible con OpenAI).

La API key se lee de la variable de entorno NVIDIA_API_KEY; nunca se hardcodea.
Si no está configurada, el endpoint responde 503 en vez de fallar."""
import httpx

from app.core.config import NVIDIA_API_KEY, NVIDIA_BASE_URL, NVIDIA_MODEL

TIMEOUT_SEG = 30
MAX_HISTORIAL = 10  # pares usuario/asistente que se reenvían como contexto

SYSTEM_PROMPT = (
    "Eres EcoBot, el asistente virtual de ReciApp, una app de recolección de "
    "reciclaje en Puente Piedra (Lima, Perú). Ayudas a ciudadanos y recicladores "
    "con dudas sobre cómo crear solicitudes de recolección, tipos de residuos "
    "aceptados (plástico, papel, vidrio, metal, orgánico, electrónicos, cartón), "
    "eco-créditos, canje de recompensas y el estado de sus recolecciones. "
    "Responde de forma breve, clara y amable, siempre en español."
)


class ChatbotNoConfigurado(RuntimeError):
    """La API key de NVIDIA no está configurada."""


class ChatbotError(RuntimeError):
    """Error al comunicarse con la API del modelo."""


def esta_configurado() -> bool:
    return bool(NVIDIA_API_KEY)


def _construir_mensajes(mensaje: str, historial: list[dict] | None) -> list[dict]:
    mensajes = [{"role": "system", "content": SYSTEM_PROMPT}]
    for turno in (historial or [])[-MAX_HISTORIAL:]:
        rol = turno.get("role")
        contenido = turno.get("content", "")
        if rol in ("user", "assistant") and contenido:
            mensajes.append({"role": rol, "content": contenido})
    mensajes.append({"role": "user", "content": mensaje})
    return mensajes


def responder(mensaje: str, historial: list[dict] | None = None) -> str:
    if not esta_configurado():
        raise ChatbotNoConfigurado()

    payload = {
        "model": NVIDIA_MODEL,
        "messages": _construir_mensajes(mensaje, historial),
        "temperature": 0.4,
        "max_tokens": 512,
    }
    headers = {
        "Authorization": f"Bearer {NVIDIA_API_KEY}",
        "Accept": "application/json",
    }

    try:
        resp = httpx.post(
            f"{NVIDIA_BASE_URL}/chat/completions",
            json=payload,
            headers=headers,
            timeout=TIMEOUT_SEG,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"].strip()
    except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
        raise ChatbotError(str(exc)) from exc
