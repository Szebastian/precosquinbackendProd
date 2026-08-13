"""Test keyword matching logic directly."""
import sys
from pathlib import Path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))
from dotenv import load_dotenv
load_dotenv(backend_dir / ".env", override=True)

# Test keyword matching
message_lower = "¿cómo me inscribo?".lower().strip().rstrip("?!.")
keywords_to_check = ["inscribir", "formulario", "anotarse", "registrar", "requisitos", "como"]

print(f"Message: {message_lower}")
print(f"Checking keywords...")
for kw in keywords_to_check:
    if kw in message_lower:
        print(f"  ✓ Match: '{kw}'")
    else:
        print(f"  ✗ No match: '{kw}'")

# Also test the "¿Cuánto cuesta inscribirse?" FAQ
message2 = "¿cuánto cuesta inscribirse?".lower().strip().rstrip("?!.")
print(f"\nMessage: {message2}")
keywords_for_inscripcion = ["costo", "precio", "gratis", "paga"]
for kw in keywords_for_inscripcion:
    if kw in message2:
        print(f"  ✓ Match: '{kw}'")
