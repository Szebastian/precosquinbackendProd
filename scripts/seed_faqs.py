"""
Script to seed FAQs into Supabase with Gemini embeddings.
Run: python scripts/seed_faqs.py

Requirements:
- GEMINI_API_KEY in .env
- Supabase tables created (run sql/create_chat_tables.sql first)
"""
import sys
import os
from pathlib import Path

# Add backend to path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from dotenv import load_dotenv
load_dotenv(backend_dir / ".env", override=True)

from supabase import create_client
from app.core.config import settings
from app.core.gemini import generate_embedding


# ─── FAQ Data ───────────────────────────────────────────────────────────────

FAQS = [
    # GENERAL (8)
    {
        "question": "¿Qué es Pre-Cosquín Puerto Pirámides?",
        "answer": "Es el 55° Certamen para Nuevos Valores Pre-Cosquín, un concurso de folklore que clasifica al Festival Nacional de Folklore de Cosquín. Está declarado de Interés Cultural, Turístico y Comunitario.",
        "category": "general",
        "keywords": ["que es", "certamen", "folklore", "cosquin"],
    },
    {
        "question": "¿Cuándo es el festival?",
        "answer": "Pre-Cosquín Puerto Pirámides 2027 se realizará el 5 y 6 de septiembre de 2027 en Puerto Pirámides, Chubut.",
        "category": "general",
        "keywords": ["cuando", "fecha", "epoca", "dia"],
    },
    {
        "question": "¿Dónde es el evento?",
        "answer": "Se realiza en la Esc. 87 (Anfiteatro Natural), Av. de las Ballenas S/N, Puerto Pirámides, Chubut, Patagonia Argentina.",
        "category": "general",
        "keywords": ["donde", "lugar", "ubicacion", "direccion"],
    },
    {
        "question": "¿Es gratuito el evento?",
        "answer": "Sí, la entrada es gratuita para el público general. Te esperamos en Puerto Pirámides.",
        "category": "general",
        "keywords": ["gratis", "costo", "precio", "entrada"],
    },
    {
        "question": "¿Cómo puedo contactar a los organizadores?",
        "answer": "Email: info@precosquinpiramides.com | Instagram: @precosquinpuertopiramides | WhatsApp: +54 9 280 487-2996",
        "category": "general",
        "keywords": ["contacto", "email", "instagram", "whatsapp", "redes"],
    },
    {
        "question": "¿Hay transmisión en vivo del evento?",
        "answer": "Sí, el evento se transmite en vivo por YouTube y las redes sociales oficiales de Pre-Cosquín Puerto Pirámides.",
        "category": "general",
        "keywords": ["transmit", "vivo", "youtube", "streaming"],
    },
    {
        "question": "¿Qué es la Peña Oficial?",
        "answer": "La Peña Oficial se realiza en La Nona, 193 Av. de las Ballenas, Puerto Pirámides, a partir de las 19:00 horas.",
        "category": "general",
        "keywords": ["pena", "oficial", "noche"],
    },
    {
        "question": "¿Qué significa 'Declarado de Interés Cultural'?",
        "answer": "Es una resolución N° 35/26 del Concejo Deliberante de Puerto Pirámides que reconoce el valor cultural del certamen.",
        "category": "general",
        "keywords": ["interes", "cultural", "declaracion", "resolucion"],
    },

    # INSCRIPCIÓN (10)
    {
        "question": "¿Cómo me inscribo en el certamen?",
        "answer": "Para inscribirte hacé click acá https://precosquinpiramides.com/inscripcion\n\nRequisitos:\n• Tener al menos 16 años\n• DNI válido\n• Email activo\n• Teléfono de contacto\n• Ser argentino nativo o naturalizado",
        "category": "inscripcion",
        "keywords": ["inscribir", "formulario", "anotarse", "registrar", "requisitos", "como"],
    },
    {
        "question": "¿Cuánto cuesta inscribirse?",
        "answer": "La inscripción es completamente gratuita. No hay ningún costo para participar de Pre-Cosquín Puerto Pirámides 2027.",
        "category": "inscripcion",
        "keywords": ["costo", "precio", "gratis", "paga"],
    },
    {
        "question": "¿Cuál es la edad mínima para inscribirse?",
        "answer": "El requisito es tener mínimo 16 años al momento de la inscripción. No hay límite de edad máximo.",
        "category": "inscripcion",
        "keywords": ["edad", "minimo", "mayor"],
    },
    {
        "question": "¿Pueden inscribirse personas de otros países?",
        "answer": "Sí, pueden inscribirse argentinos nativos o naturalizados. El certamen es de alcance regional y nacional.",
        "category": "inscripcion",
        "keywords": ["extranjeros", "paises", "nacionalidad"],
    },
    {
        "question": "¿Qué documentos necesito para inscribirme?",
        "answer": "Necesitás: nombre completo, DNI, fecha de nacimiento, dirección, localidad, provincia, teléfono y email.",
        "category": "inscripcion",
        "keywords": ["documentos", "requisitos", "datos", "dni"],
    },
    {
        "question": "¿Puedo modificar mi inscripción después de enviarla?",
        "answer": "Sí, podés modificar datos personales, categoría, información artística y temas. No se pueden modificar archivos ni documentos.",
        "category": "inscripcion",
        "keywords": ["modificar", "cambiar", "editar"],
    },
    {
        "question": "¿Cómo descargo la constancia de inscripción?",
        "answer": "Después de inscribirte, podés descargar la constancia desde tu panel de inscripción. También la recibís por email.",
        "category": "inscripcion",
        "keywords": ["constancia", "descargar", "comprobante"],
    },
    {
        "question": "¿Qué pasa si mi inscripción dice 'Necesita Corrección'?",
        "answer": "Revisá tu email, te indicamos qué datos hay que corregir. Entrá al panel de inscripción y actualizá la información.",
        "category": "inscripcion",
        "keywords": ["correccion", "error", "arreglar"],
    },
    {
        "question": "¿Puedo inscribirme en más de una categoría?",
        "answer": "No, solo podés inscribirte en una categoría ya sea de Música o Danza.",
        "category": "inscripcion",
        "keywords": ["varias", "categorias", "doble"],
    },
    {
        "question": "¿Cuántas personas pueden integrar un grupo?",
        "answer": "Depende la categoría: Conjunto Vocal 3-8 integrantes, Conjunto Instrumental hasta 10, Conjunto de Danza mínimo 8.",
        "category": "inscripcion",
        "keywords": ["integrantes", "grupo", "personas", "cantidad"],
    },

    # CATEGORÍAS (8)
    {
        "question": "¿Qué categorías hay?",
        "answer": "En Pre-Cosquín Puerto Pirámides 2027 hay dos grandes áreas:\n\n🎵 Música (7): Solista Vocal, Duo Vocal, Expresión Oral Folclórica, Conjunto Vocal, Solista Instrumental, Conjunto Instrumental y Canción Inédita.\n\n💃 Danza (6): Malambo Masculino, Malambo Femenino, Conjunto de Malambo, Pareja Tradicional, Pareja Estilizada y Conjunto de Baile Folclórico.",
        "category": "categorias",
        "keywords": ["categorias", "que hay", "todas", "áreas"],
    },
    {
        "question": "¿Qué categorías de música hay?",
        "answer": "En Pre-Cosquín Puerto Pirámides 2027 existen dos grandes áreas: Música y Danza. En Música hay 7 categorías: Solista Vocal, Duo Vocal, Expresión Oral Folclórica, Conjunto Vocal, Solista Instrumental, Conjunto Instrumental y Canción Inédita.",
        "category": "categorias",
        "keywords": ["musica", "categorias", "solista", "banda"],
    },
    {
        "question": "¿Qué categorías de danza hay?",
        "answer": "En Pre-Cosquín Puerto Pirámides 2027 existen dos grandes áreas: Música y Danza. En Danza hay 6 categorías: Malambo Masculino, Malambo Femenino, Conjunto de Malambo, Pareja Tradicional, Pareja Estilizada y Conjunto de Baile Folclórico.",
        "category": "categorias",
        "keywords": ["danza", "bailarines", "malambo", "baile"],
    },
    {
        "question": "¿Qué es la categoría Solista Instrumental?",
        "answer": "Es presentación instrumental sin pistas pregrabadas. No se permite cambio de instrumento. Puede ser acompañado por 1 instrumento armónico (Art. 31).",
        "category": "categorias",
        "keywords": ["instrumental", "art 31", "instrumento"],
    },
    {
        "question": "¿Qué instrumentos puedo usar?",
        "answer": "Melódicos: violín, flauta, quena, erke. Armónicos: guitarra, piano, bandoneón, acordeón, charango. No se permiten pistas pregrabadas.",
        "category": "categorias",
        "keywords": ["instrumentos", "guitarra", "quena", "piano"],
    },
    {
        "question": "¿Qué es la categoría Canción Inédita?",
        "answer": "Es una obra musical original inédita. Se evalúa la producción, el arreglo y la letra. Duración máxima: 5 minutos.",
        "category": "categorias",
        "keywords": ["inedita", "original", "cancion"],
    },
    {
        "question": "¿Qué es Expresión Oral Folclórica?",
        "answer": "Es una nueva categoría desde 2027 para narradores, recitadores y 'decidores'. Duración: 5 a 8 minutos.",
        "category": "categorias",
        "keywords": ["oral", "folclorica", "narrador", "decidor"],
    },
    {
        "question": "¿Cuánto dura cada presentación?",
        "answer": "Depende la categoría: de 2 a 10 minutos. Solista Vocal/Instrumental: 5 min. Conjunto de Danza: 8-10 min.",
        "category": "categorias",
        "keywords": ["duracion", "tiempo", "minutos"],
    },
    {
        "question": "¿Qué premios ganan los ganadores?",
        "answer": "Actuación en el Festival Nacional de Cosquín, certificado de acreditación, y derecho a competir por el premio 'Revelación'.",
        "category": "categorias",
        "keywords": ["premios", "ganador", "cosquin", "revelacion"],
    },

    # STANDS (6)
    {
        "question": "¿Como solicito un stand?",
        "answer": "Podés solicitar tu stand completando el formulario: hacé click acá https://precosquinpiramides.com/stands/nuevo",
        "category": "stands",
        "keywords": ["stand", "carpa", "comercio", "vender"],
    },
    {
        "question": "¿Qué tipos de stands hay?",
        "answer": "Hay 4 tipos: Stands de Exposición, Stands de Gastronomía, Stands Comerciales y Stands Artísticos.",
        "category": "stands",
        "keywords": ["tipos", "exposicion", "gastronomia", "comercial"],
    },
    {
        "question": "¿Cuánto cuesta un stand?",
        "answer": "Los precios varían según el tipo y tamaño. Consultá los precios actualizados en el formulario de solicitud.",
        "category": "stands",
        "keywords": ["costo", "precio", "tarifa"],
    },
    {
        "question": "¿Qué tamaño tienen los stands?",
        "answer": "Los stands van desde 2x2 metros hasta 6x6 metros. Elegís el tamaño que mejor se adapte a tu negocio.",
        "category": "stands",
        "keywords": ["tamaño", "medida", "metros", "espacio"],
    },
    {
        "question": "¿Necesito electricidad para mi stand?",
        "answer": "Podés solicitar electricidad al momento de completar el formulario de solicitud de stand.",
        "category": "stands",
        "keywords": ["electricidad", "luz", "energia", "tomacorriente"],
    },
    {
        "question": "¿Puedo vender comida en mi stand?",
        "answer": "Sí, en la categoría Gastronomía. Necesitás contar con certificación sanitaria y cumplir con las normativas.",
        "category": "stands",
        "keywords": ["comida", "gastronomia", "vender", "cocinar"],
    },

    # CRONOGRAMA (3)
    {
        "question": "¿Dónde veo el cronograma del evento?",
        "answer": "El cronograma completo está en https://precosquinpiramides.com/cronograma con el orden de presentación y agenda general.",
        "category": "cronograma",
        "keywords": ["cronograma", "agenda", "horarios"],
    },
    {
        "question": "¿Cuándo se publica el orden de presentación?",
        "answer": "El orden de presentación se publica en la página oficial antes del inicio del certamen. Seguí nuestras redes para novedades.",
        "category": "cronograma",
        "keywords": ["orden", "presentacion", "publicar"],
    },
    {
        "question": "¿Qué horario tiene el evento?",
        "answer": "El certamen es el sábado 5 y domingo 6 de septiembre, de 8:00 a 18:00 horas.",
        "category": "cronograma",
        "keywords": ["horario", "hora", "inicio", "fin"],
    },

    # SPONSORS (3)
    {
        "question": "¿Cómo me hago sponsor o patrocinador?",
        "answer": "Contactanos por WhatsApp al +54 9 280 487-2996 o escribinos a info@precosquinpiramides.com. Conocé los planes: hacé click acá https://precosquinpiramides.com/patrocinio",
        "category": "sponsors",
        "keywords": ["sponsor", "patrocinador", "patrocinio", "empresas", "sumar"],
    },
    {
        "question": "¿Qué beneficios tiene ser sponsor?",
        "answer": "Los sponsors obtienen visibilidad de marca, presencia en redes sociales, menciones en el evento y espacios de exposición. Hacé click acá para más info: https://precosquinpiramides.com/patrocinio",
        "category": "sponsors",
        "keywords": ["beneficios", "ventajas", "que ganan"],
    },
    {
        "question": "¿Hay diferentes planes de patrocinio?",
        "answer": "Sí, ofrecemos varios planes para diferentes tamaños de empresa. Hacé click acá para verlos: https://precosquinpiramides.com/patrocinio",
        "category": "sponsors",
        "keywords": ["planes", "opciones", "disponibles"],
    },

    # INSCRIPCIÓN DETALLADA (5)
    {
        "question": "¿Qué edad mínima tengo que tener para inscribirme?",
        "answer": "Tenés que tener al menos 16 años al momento de la inscripción. No hay límite de edad máximo.",
        "category": "inscripcion",
        "keywords": ["edad", "minimo", "16", "años"],
    },
    {
        "question": "¿Qué archivos necesito subir?",
        "answer": "Necesitás subir: foto del DNI (frente y dorso), y una foto promocional tuya o de tu grupo. Si hacés canción inédita, también la letra y partitura. En danza, el MP3 de la música.",
        "category": "inscripcion",
        "keywords": ["archivos", "subir", "dni", "foto", "documentos"],
    },
    {
        "question": "¿Cómo descargo la constancia de inscripción?",
        "answer": "Después de inscribirte, la constancia de inscripción llega a tu email y también la podés descargar desde tu panel de inscripción.",
        "category": "inscripcion",
        "keywords": ["constancia", "descargar", "comprobante"],
    },
    {
        "question": "¿Qué pasa si mi inscripción dice 'Necesita Corrección'?",
        "answer": "Revisá tu email, te indicamos qué datos hay que corregir. Entrá al panel de inscripción y actualizá la información requerida.",
        "category": "inscripcion",
        "keywords": ["correccion", "error", "arreglar"],
    },
    {
        "question": "¿Puedo inscribirme en más de una categoría?",
        "answer": "No, solo podés inscribirte en una categoría: ya sea de Música o Danza. Tenés que elegir al momento de la inscripción.",
        "category": "inscripcion",
        "keywords": ["varias", "categorias", "doble", "una sola"],
    },
]


# ─── Main Script ────────────────────────────────────────────────────────────

def main():
    print("🌱 Seeding FAQs into Supabase...")

    # Connect to Supabase
    client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
    print(f"✅ Connected to Supabase: {settings.SUPABASE_URL[:50]}...")

    # Check Gemini API key
    if not settings.GEMINI_API_KEY:
        print("❌ GEMINI_API_KEY not configured in .env")
        print("   Get one free at: https://aistudio.google.com/apikey")
        sys.exit(1)

    print(f"✅ Gemini API key configured")

    # Clear existing FAQs
    print("🗑️  Clearing existing FAQs...")
    client.table("faqs").delete().neq("id", 0).execute()

    # Insert FAQs with embeddings
    inserted = 0
    errors = 0

    for i, faq in enumerate(FAQS, 1):
        print(f"📝 [{i}/{len(FAQS)}] {faq['question'][:50]}...")

        # Generate embedding
        embedding = generate_embedding(faq["question"])
        if not embedding:
            print(f"   ⚠️  Failed to generate embedding, skipping")
            errors += 1
            continue

        # Insert into Supabase
        try:
            client.table("faqs").insert({
                "question": faq["question"],
                "answer": faq["answer"],
                "category": faq["category"],
                "keywords": faq["keywords"],
                "embedding": str(embedding),  # PostgreSQL vector format
                "is_active": True,
            }).execute()
            inserted += 1
            print(f"   ✅ Inserted (similarity embedding generated)")
        except Exception as e:
            print(f"   ❌ Insert error: {e}")
            errors += 1

    print(f"\n🎉 Done! Inserted: {inserted}, Errors: {errors}")

    # Verify
    result = client.table("faqs").select("id").execute()
    print(f"📊 Total FAQs in database: {len(result.data)}")


if __name__ == "__main__":
    main()
