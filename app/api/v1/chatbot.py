from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.concurrency import run_in_threadpool

from app.api.v1.dependencies import get_current_user
from app.models.user import Usuario
from app.schemas.chatbot import ChatRequest, ChatResponse
from app.services import chatbot

router = APIRouter()


@router.post(
    "",
    response_model=ChatResponse,
    summary="Conversar con EcoBot, el asistente de ReciApp (NVIDIA API)",
)
async def conversar(
    data: ChatRequest,
    _: Usuario = Depends(get_current_user),
):
    if not chatbot.esta_configurado():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="El chatbot no está configurado (falta NVIDIA_API_KEY)",
        )
    historial = [m.model_dump() for m in data.historial]
    try:
        respuesta = await run_in_threadpool(chatbot.responder, data.mensaje, historial)
    except chatbot.ChatbotError:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="No se pudo obtener respuesta del asistente en este momento",
        )
    return ChatResponse(respuesta=respuesta)
