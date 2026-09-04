"""
Chatbot endpoint with Gemini AI + Supabase FAQ search + Upstash cache.
"""
import hashlib
import json
from typing import Optional, List
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException
import structlog

from app.core.deps import get_db
from app.core.gemini import generate_embedding, generate_chat_response
from app.core.upstash import get_upstash
from app.core.config import settings

logger = structlog.get_logger()
router = APIRouter()


# ─── Schemas ────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    session_id: str = "anonymous"


class ChatResponse(BaseModel):
    reply: str
    source: str  # 'faq' | 'cache' | 'gemini'
    suggestions: List[str] = []


# ─── FAQ Context for Gemini ─────────────────────────────────────────────────

FAQ_CONTEXT = """Preguntas frecuentes de Pre-Cosquín Puerto Pirámides 2027:

GENERAL:
- ¿Qué es? Pre-Cosquín Puerto Pirámides 2027, el 55° Certamen para Nuevos Valores que clasifica al Festival Nacional de Folklore de Cosquín. Está declarado de Interés Cultural, Turístico y Comunitario.
- ¿Cuándo? 5 y 6 de septiembre de 2027
- ¿Dónde? Esc. 87 (Anfiteatro Natural), Av. de las Ballenas S/N, Puerto Pirámides, Chubut
- ¿Es gratuito? Sí, la entrada es gratuita para el público general
- Contacto: info@precosquinpiramides.com | Instagram: @precosquinpuertopiramides | WhatsApp: +54 9 280 487-2996

INSCRIPCIÓN:
- Cómo inscribirse: ingresá a https://precosquinpiramides.com/inscripcion y completá el formulario online
- Es gratuita, no hay ningún costo
- Edad mínima: 16 años
- Pueden inscribirse argentinos nativos o naturalizados
- Documentos: DNI, nombre, email, teléfono, provincia

CATEGORÍAS:
En Pre-Cosquín Puerto Pirámides 2027 hay dos grandes áreas: Música y Danza.

MÚSICA (7 categorías):
- Solista Vocal (5 min)
- Duo Vocal (5 min)
- Expresión Oral Folclórica (5-8 min, nueva 2027)
- Conjunto Vocal (3-8 integrantes, 5 min)
- Solista Instrumental (Art. 31, sin pistas pregrabadas)
- Conjunto Instrumental (hasta 10, 5 min)
- Canción Inédita (obra original, 5 min)

DANZA (6 categorías):
- Malambo Masculino/Femenino (2-4 min)
- Conjunto de Malambo (4-8 bailarines)
- Pareja Tradicional/Estilizada (5 min)
- Conjunto de Baile Folclórico (mín. 8, 8-10 min)

STANDS:
- Cómo solicitar: ingresá a https://precosquinpiramides.com/stands/nuevo y completá el formulario
- Tipos: Stands de Exposición, Gastronomía, Comerciales y Artísticos
- Tamaños: 2x2 a 6x6 metros
- Se puede solicitar electricidad al momento de la solicitud
- Comida: sí, en categoría Gastronomía con certificación sanitaria

SPONSORS/PATROCINIO:
- Para ser sponsor: contactar por WhatsApp +54 9 280 487-2996 o email info@precosquinpiramides.com
- Beneficios: visibilidad de marca, presencia en redes, menciones en el evento, espacios de exposición
- Planes adaptados a diferentes tamaños de empresa
- Más info: https://precosquinpiramides.com/patrocinio

CRONOGRAMA:
- Ver en: https://precosquinpiramides.com/cronograma
- Horario certamen: 8:00 a 18:00 hs
- Se publica el orden de presentación en la página oficial antes del inicio"""


# ─── Suggested questions per category ───────────────────────────────────────

SUGGESTIONS = [
    "¿Cómo me inscribo?",
    "¿Qué categorías hay?",
    "¿Cómo solicito un stand?",
    "¿Cómo me hago sponsor?",
    "¿Cuándo es Pre-Cosquín?",
    "¿Dónde es el evento?",
    "¿Es gratuito?",
]

# ─── Greeting patterns ─────────────────────────────────────────────────────

GREETING_RESPONSE = """¡Hola! Soy el asistente de Pre-Cosquín Puerto Pirámides 2027. 

¿En qué puedo ayudarte? Elegí una de estas opciones:"""


# ─── Helper: hash for cache key ─────────────────────────────────────────────

def _cache_key(text: str) -> str:
    """Generate a cache key from normalized text."""
    normalized = text.lower().strip().rstrip("?!.")
    return hashlib.md5(normalized.encode()).hexdigest()


# ─── Endpoint ───────────────────────────────────────────────────────────────

@router.post("/", response_model=ChatResponse)
async def chat(req: ChatRequest, db=Depends(get_db)):
    """
    Chatbot endpoint.
    Flow:
    1. Check Upstash cache
    2. Search FAQs with pgvector similarity
    3. If no match, call Gemini
    """
    message = req.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="Message is required")

    # ── Step 0: Detect greetings ─────────────────────────────────────────
    greetings = ["hola", "holi", "holis", "buenos dias", "buenas tardes", "buenas noches", "hey", "que tal", "como va", "que onda"]
    if message.lower() in greetings:
        return ChatResponse(
            reply=GREETING_RESPONSE,
            source="greeting",
            suggestions=SUGGESTIONS[:3],
        )

    upstash = get_upstash()

    # ── Step 1: Check cache ──────────────────────────────────────────────
    cache_key = f"chat2:{_cache_key(message)}"
    if upstash:
        cached = await upstash.get(cache_key)
        if cached:
            try:
                data = json.loads(cached)
                return ChatResponse(
                    reply=data["reply"],
                    source="cache",
                    suggestions=data.get("suggestions", SUGGESTIONS[:3]),
                )
            except (json.JSONDecodeError, KeyError):
                pass

    # ── Step 2: Search FAQs ────────────────────────────────────────────────
    from difflib import SequenceMatcher
    embedding = None
    try:
        embedding = generate_embedding(message)
    except Exception:
        pass

    # ── Step 2a: Try exact question matching first ──────────────────────────
    message_lower = message.lower().strip().rstrip("?!.")
    best_match_faq = None
    best_similarity = 0.0
    try:
        all_result = db.table("faqs").select("id, question, answer, category, keywords").eq("is_active", True).execute()
        if all_result.data:
            for faq in all_result.data:
                faq_question_lower = faq.get("question", "").lower().strip().rstrip("?!.")
                similarity = SequenceMatcher(None, message_lower, faq_question_lower).ratio()
                if similarity > best_similarity:
                    best_similarity = similarity
                    best_match_faq = faq
    except Exception:
        pass

    # If exact match found (similarity >= 0.6), use it
    if best_match_faq and best_similarity >= 0.6:
        reply = best_match_faq["answer"]
        source = "faq"

        if upstash:
            await upstash.setex(
                cache_key, 3600, json.dumps({"reply": reply, "suggestions": SUGGESTIONS[:3]})
            )

        return ChatResponse(
            reply=reply,
            source=source,
            suggestions=SUGGESTIONS[:3],
        )

    # ── Step 2b: Semantic search with pgvector ─────────────────────────────
    try:
        if embedding:
            embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"

            result = db.rpc(
                "search_faqs",
                {
                    "query_embedding": embedding_str,
                    "match_threshold": 0.75,
                    "match_count": 3,
                },
            ).execute()

            if result.data and len(result.data) > 0:
                best_match = result.data[0]
                similarity = best_match.get("similarity", 0)

                if similarity >= 0.7:
                    reply = best_match["answer"]
                    source = "faq"

                    if upstash:
                        await upstash.setex(
                            cache_key,
                            3600,
                            json.dumps({"reply": reply, "suggestions": SUGGESTIONS[:3]}),
                        )

                    return ChatResponse(
                        reply=reply,
                        source=source,
                        suggestions=SUGGESTIONS[:3],
                    )
    except Exception as e:
        logger.warning("faq_search_error", error=str(e))

    # ── Step 3: Call Gemini ──────────────────────────────────────────────
    try:
        reply = generate_chat_response(
            user_message=message,
            faq_context=FAQ_CONTEXT,
        )

        if reply:
            source = "gemini"

            # Cache the response
            if upstash:
                await upstash.setex(
                    cache_key,
                    3600,  # 1 hour
                    json.dumps({
                        "reply": reply,
                        "suggestions": SUGGESTIONS[:3],
                    }),
                )

            return ChatResponse(
                reply=reply,
                source=source,
                suggestions=SUGGESTIONS[:3],
            )
    except Exception as e:
        logger.warning("gemini_error", error=str(e))

    # ── Fallback ─────────────────────────────────────────────────────────
    return ChatResponse(
        reply="No encontré una respuesta exacta. Podés preguntarme sobre:\n• Inscripción: precosquinpiramides.com/inscripcion\n• Stands: precosquinpiramides.com/stands/nuevo\n• Sponsors: precosquinpiramides.com/patrocinio\n• Contacto: info@precosquinpiramides.com",
        source="fallback",
        suggestions=SUGGESTIONS[:3],
    )


# ─── Health check ───────────────────────────────────────────────────────────

@router.get("/health")
async def chat_health():
    """Check chatbot service health."""
    upstash = get_upstash()
    gemini_configured = bool(settings.GEMINI_API_KEY)
    upstash_configured = upstash is not None

    return {
        "status": "ok",
        "gemini": "configured" if gemini_configured else "not_configured",
        "upstash": "configured" if upstash_configured else "not_configured",
    }
