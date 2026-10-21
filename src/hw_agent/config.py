import os
from pathlib import Path
from dotenv import load_dotenv

BASE = Path(__file__).resolve().parents[2]
load_dotenv(BASE / ".env")
DATA = Path(os.getenv("DATA_DIR", str(BASE / "data"))).resolve()
DATA.mkdir(parents=True, exist_ok=True)
os.chmod(DATA, 0o700)
USERNAME = os.environ["DASHBOARD_USERNAME"]
PASSWORD = os.environ["DASHBOARD_PASSWORD"]
SECRET = os.environ["SESSION_SECRET"]
if len(SECRET) < 32:
    raise RuntimeError("SESSION_SECRET must contain at least 32 characters")
LLM_URL = os.getenv("LLM_BASE_URL", "http://127.0.0.1:8081")
LLM_KEY_FILE = DATA / "llm-api-key"
LLM_HEADERS = {"Authorization": "Bearer " + LLM_KEY_FILE.read_text().strip()} if LLM_KEY_FILE.exists() else {}
SECURE_COOKIE = os.getenv("SECURE_COOKIE", "false").lower() == "true"
EXCLUDED_DIRECTORY_NAMES = {name.strip().casefold() for name in os.getenv("EXCLUDED_DIRECTORY_NAMES", "").split(",") if name.strip()}
