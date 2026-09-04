"""Quick script to list available Gemini models."""
import os
from dotenv import load_dotenv
load_dotenv()

from google import genai

api_key = os.environ.get("GEMINI_API_KEY")
print(f"API Key: {api_key[:10]}..." if api_key else "No API Key")

client = genai.Client(api_key=api_key)

print("\nListing all available models...")
for model in client.models.list():
    # Only show embedding models
    if "embed" in model.name.lower() or "embedding" in model.name.lower():
        print(f"  {model.name}")
