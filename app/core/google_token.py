# app/core/config.py (o un módulo nuevo, ej. app/core/google_token.py)
import os
import base64

def asegurar_google_master_token():
    """Railway tiene filesystem efímero y tokens/*.json está en .gitignore,
    así que el token nunca llega con el deploy. Si existe la env var
    GOOGLE_MASTER_TOKEN_B64, la decodifica a tokens/master_token.json."""
    token_path = "tokens/master_token.json"
    if os.path.exists(token_path):
        return
    token_b64 = os.getenv("GOOGLE_MASTER_TOKEN_B64")
    if not token_b64:
        print("⚠️ Falta GOOGLE_MASTER_TOKEN_B64 y no hay tokens/master_token.json local")
        return
    os.makedirs("tokens", exist_ok=True)
    with open(token_path, "wb") as f:
        f.write(base64.b64decode(token_b64))
    print("✅ tokens/master_token.json restaurado desde variable de entorno")