"""
Gemini AI client for chatbot responses and embeddings.
Uses the google-genai library (new API).
"""
from google import genai
from google.genai import types
from typing import List, Optional
import structlog

from app.core.config import settings

logger = structlog.get_logger()

# System prompt optimizado (corto para ahorrar tokens)
SYSTEM_PROMPT = """Sos el asistente virtual oficial de Pre-Cosquín Puerto Pirámides 2027, el 55° Certamen para Nuevos Valores que clasifica al Festival Nacional de Folklore de Cosquín.

Reglas:
- Respondé en máximo 2 oraciones, sé conciso y directo
- Usá siempre el nombre completo: "Pre-Cosquín Puerto Pirámides 2027"
- Si no sabés algo, decí "Visitá precosquinpiramides.com para más info"
- No inventes información
- Usá un tono amigable, cálido y profesional
- Si te preguntan por inscripción, mencioná que es gratuita
- Si te preguntan por sponsors, mencioná la página precosquinpiramides.com/patrocinio
- Categorías: Música (7) y Danza (6)
- Fechas: 5 y 6 de septiembre de 2027
- Lugar: Puerto Pirámides, Chubut, Patagonia Argentina
- Contacto: info@precosquinpiramides.com"""


_client: Optional[genai.Client] = None


def _get_client() -> Optional[genai.Client]:
    """Get or create Gemini client (singleton)."""
    global _client
    if _client is None and settings.GEMINI_API_KEY:
        _client = genai.Client(api_key=settings.GEMINI_API_KEY)
    return _client


def generate_embedding(text: str) -> Optional[List[float]]:
    """Generate an embedding vector for text using Gemini."""
    client = _get_client()
    if not client:
        return None
    try:
        result = client.models.embed_content(
            model="models/gemini-embedding-001",
            contents=text,
        )
        return result.embeddings[0].values
    except Exception as e:
        logger.warning("gemini_embedding_error", error=str(e))
        return None


def generate_chat_response(
    user_message: str,
    faq_context: str = "",
    history: Optional[List[dict]] = None,
) -> Optional[str]:
    """Generate a chat response using Gemini."""
    client = _get_client()
    if not client:
        return None
    try:
        prompt_parts = []
        if faq_context:
            prompt_parts.append(f"Contexto de preguntas frecuentes:\n{faq_context}")
        if history:
            for msg in history[-3:]:  # Solo últimos 3 mensajes
                role = "user" if msg.get("role") == "user" else "model"
                prompt_parts.append(f"{role}: {msg.get('content', '')}")
        prompt_parts.append(f"Usuario: {user_message}")

        prompt = "\n".join(prompt_parts)

        response = client.models.generate_content(
            model="models/gemini-2.5-flash-lite",
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                temperature=0.3,
                max_output_tokens=150,
            ),
        )

        return response.text
    except Exception as e:
        logger.warning("gemini_chat_error", error=str(e))
        return None
