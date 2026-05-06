import os
import google.generativeai as genai

_script_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(_script_dir)
_env_path = os.path.join(_project_root, ".env")
if os.path.isfile(_env_path):
    try:
        with open(_env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip().strip("\ufeff")
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, _, value = line.partition("=")
                    key = key.strip()
                    value = value.strip().strip("'\"")
                    if key and value:
                        os.environ.setdefault(key, value)
                        if key.upper() == "GEMINI_API_KEY":
                            os.environ["GEMINI_API_KEY"] = value
    except OSError:
        pass

API_KEY = os.getenv("GEMINI_API_KEY")
if not API_KEY:
    raise SystemExit(
        "Set GEMINI_API_KEY in .env (copy .env.example) or export it. "
        "Create a key: https://aistudio.google.com/apikey"
    )

genai.configure(api_key=API_KEY)

print("Listing supported models:")
try:
    for m in genai.list_models():
        if "generateContent" in m.supported_generation_methods:
            print(f"Model: {m.name}, DisplayName: {m.display_name}")
except Exception as e:
    print(f"Error listing models: {e}")
