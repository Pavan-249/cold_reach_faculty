import os
import google.generativeai as genai

API_KEY = os.getenv("GEMINI_API_KEY")
if not API_KEY:
    raise SystemExit("Set GEMINI_API_KEY in the environment or in .env (see .env.example).")

genai.configure(api_key=API_KEY)

print("Listing supported models:")
try:
    for m in genai.list_models():
        if "generateContent" in m.supported_generation_methods:
            print(f"Model: {m.name}, DisplayName: {m.display_name}")
except Exception as e:
    print(f"Error listing models: {e}")
