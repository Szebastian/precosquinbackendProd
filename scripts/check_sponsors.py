"""Check sponsor FAQs."""
import sys
from pathlib import Path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))
from dotenv import load_dotenv
load_dotenv(backend_dir / ".env", override=True)
from supabase import create_client
from app.core.config import settings

client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
result = client.table("faqs").select("question,answer").eq("category", "sponsors").execute()
for faq in result.data:
    print(f"Q: {faq['question']}")
    print(f"A: {faq['answer']}")
    print()
