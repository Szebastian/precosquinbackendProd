"""List all available Gemini models."""
import os
from dotenv import load_dotenv
load_dotenv()

from google import genai

api_key = os.environ.get("GEMINI_API_KEY")
client = genai.Client(api_key=api_key)

print("All available models:")
for model in client.models.list():
    print(f"  {model.name}")
