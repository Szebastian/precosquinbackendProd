"""Test the chat endpoint flow directly."""
import sys
from pathlib import Path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))
from dotenv import load_dotenv
load_dotenv(backend_dir / ".env", override=True)

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

# Test "¿Cómo me inscribo?"
response = client.post("/v1/chat/", json={
    "message": "¿Cómo me inscribo?",
    "session_id": "test"
})
print("Response:")
print(response.json())