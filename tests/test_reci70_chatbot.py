"""Tests para RECI-70: chatbot sobre la API de NVIDIA.

No se llama a la API real: se mockea httpx.post y la configuración."""
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.api.v1.dependencies import get_current_user
from app.services import chatbot


def _client():
    usuario = type("U", (), {"id": 1, "rol": "ciudadano", "activo": True})()
    app.dependency_overrides[get_current_user] = lambda: usuario
    return TestClient(app)


def teardown_function():
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Servicio
# ---------------------------------------------------------------------------

class TestServicioChatbot:
    def test_construye_mensajes_con_system_y_limita_historial(self):
        historial = [{"role": "user", "content": f"m{i}"} for i in range(20)]
        mensajes = chatbot._construir_mensajes("hola", historial)

        assert mensajes[0]["role"] == "system"
        assert mensajes[-1] == {"role": "user", "content": "hola"}
        # system + MAX_HISTORIAL + el mensaje nuevo
        assert len(mensajes) == 1 + chatbot.MAX_HISTORIAL + 1

    def test_ignora_roles_invalidos_en_historial(self):
        historial = [{"role": "system", "content": "x"}, {"role": "user", "content": "y"}]
        mensajes = chatbot._construir_mensajes("z", historial)
        roles = [m["role"] for m in mensajes]
        assert roles == ["system", "user", "user"]

    @patch("app.services.chatbot.NVIDIA_API_KEY", "fake-key")
    @patch("app.services.chatbot.httpx.post")
    def test_responder_extrae_contenido(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "  Hola, soy EcoBot  "}}]
        }
        mock_resp.raise_for_status.return_value = None
        mock_post.return_value = mock_resp

        out = chatbot.responder("hola")
        assert out == "Hola, soy EcoBot"
        # La key viaja en el header Authorization, no en el cuerpo
        _, kwargs = mock_post.call_args
        assert kwargs["headers"]["Authorization"] == "Bearer fake-key"

    @patch("app.services.chatbot.NVIDIA_API_KEY", "")
    def test_responder_sin_key_lanza_no_configurado(self):
        import pytest
        with pytest.raises(chatbot.ChatbotNoConfigurado):
            chatbot.responder("hola")


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

class TestEndpointChatbot:
    @patch("app.api.v1.chatbot.chatbot.esta_configurado", return_value=True)
    @patch("app.api.v1.chatbot.chatbot.responder", return_value="Respuesta de prueba")
    def test_devuelve_respuesta(self, mock_responder, _cfg):
        client = _client()
        resp = client.post("/api/chatbot", json={"mensaje": "¿Cómo reciclo vidrio?"})
        assert resp.status_code == 200
        assert resp.json() == {"respuesta": "Respuesta de prueba"}
        mock_responder.assert_called_once()

    @patch("app.api.v1.chatbot.chatbot.esta_configurado", return_value=False)
    def test_503_si_no_configurado(self, _cfg):
        client = _client()
        resp = client.post("/api/chatbot", json={"mensaje": "hola"})
        assert resp.status_code == 503

    @patch("app.api.v1.chatbot.chatbot.esta_configurado", return_value=True)
    @patch("app.api.v1.chatbot.chatbot.responder", side_effect=chatbot.ChatbotError("boom"))
    def test_502_si_falla_la_api(self, _resp, _cfg):
        client = _client()
        resp = client.post("/api/chatbot", json={"mensaje": "hola"})
        assert resp.status_code == 502

    def test_mensaje_vacio_da_422(self):
        with patch("app.api.v1.chatbot.chatbot.esta_configurado", return_value=True):
            client = _client()
            resp = client.post("/api/chatbot", json={"mensaje": ""})
        assert resp.status_code == 422

    def test_requiere_autenticacion(self):
        # sin override de get_current_user
        app.dependency_overrides.clear()
        client = TestClient(app)
        resp = client.post("/api/chatbot", json={"mensaje": "hola"})
        assert resp.status_code == 401
