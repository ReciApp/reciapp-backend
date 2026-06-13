from pydantic import BaseModel, Field


class MensajeHistorial(BaseModel):
    role: str = Field(..., description="'user' o 'assistant'")
    content: str


class ChatRequest(BaseModel):
    mensaje: str = Field(..., min_length=1, max_length=2000)
    historial: list[MensajeHistorial] = Field(default_factory=list)


class ChatResponse(BaseModel):
    respuesta: str
