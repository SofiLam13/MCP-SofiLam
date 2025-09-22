import os, json, sys

# === 1) LLM (opcional para usar el host_chatbot_simple.py) ===
# Si no tienes API key de Gemini, déjalo vacío; el host usa heurísticas básicas.
GEMINI_API_KEY = ""                 # p.ej. "AIzaSyD..."
GEMINI_MODEL   = "gemini-1.5-flash"
GEMINI_BASE    = "https://generativelanguage.googleapis.com/v1beta"

# === 2) Google OAuth2 (Calendar / Gmail) ===
CLIENT_ID = ""
CLIENT_SECRET = ""
if os.path.exists("credentials.json"):
    with open("credentials.json", "r", encoding="utf-8") as f:
        creds = json.load(f)
        if "installed" in creds:
            CLIENT_ID = creds["installed"]["client_id"]
            CLIENT_SECRET = creds["installed"]["client_secret"]
        elif "web" in creds:
            CLIENT_ID = creds["web"]["client_id"]
            CLIENT_SECRET = creds["web"]["client_secret"]

REFRESH_TOKEN = ""
if os.path.exists("token.json"):
    with open("token.json", "r", encoding="utf-8") as f:
        REFRESH_TOKEN = json.load(f).get("refresh_token", "")

# === 3) Emails (pon tu correo) ===
USER_EMAIL   = "tu_correo@gmail.com"
SENDER_EMAIL = "tu_correo@gmail.com"
NOTIFY_EMAIL = "tu_correo@gmail.com"

# === 4) Scopes requeridos ===
SCOPES = (
    "https://www.googleapis.com/auth/calendar "
    "https://www.googleapis.com/auth/gmail.send"
)

# === 5) Otros ajustes ===
TIMEZONE       = "America/Guatemala"
LOG_FILE       = "mcp_io.log"
SERVER_NAME    = "google-calendar-mcp"
SERVER_VERSION = "0.2.0"

# === 6) Registro de MCPs disponibles (no toques rutas si usas este repo tal cual) ===
MCP_SERVERS = {
    "calendar": [sys.executable, "google_calendar_mcp_server.py"],
}
MCP_DEFAULT = "calendar"
