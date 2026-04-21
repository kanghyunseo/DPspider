"""Environment configuration loader."""
import os

from dotenv import load_dotenv

load_dotenv()


def _require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing required env var: {name}")
    return value


TELEGRAM_BOT_TOKEN = _require("TELEGRAM_BOT_TOKEN")
ANTHROPIC_API_KEY = _require("ANTHROPIC_API_KEY")

ALLOWED_TELEGRAM_USER_IDS = [
    int(uid.strip())
    for uid in os.environ.get("ALLOWED_TELEGRAM_USER_IDS", "").split(",")
    if uid.strip()
]

DEFAULT_TIMEZONE = os.environ.get("DEFAULT_TIMEZONE", "Asia/Seoul")
GOOGLE_CREDENTIALS_PATH = os.environ.get("GOOGLE_CREDENTIALS_PATH", "credentials.json")
GOOGLE_TOKEN_PATH = os.environ.get("GOOGLE_TOKEN_PATH", "token.json")
CALENDAR_ID = os.environ.get("CALENDAR_ID", "primary")
DB_PATH = os.environ.get("DB_PATH", "assistant.db")
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-opus-4-7")
HISTORY_LIMIT = int(os.environ.get("HISTORY_LIMIT", "40"))
