"""Environment configuration loader.

All file paths (credentials, token, DB, .env) resolve relative to the
package directory by default, so the bot works regardless of CWD.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

PACKAGE_DIR = Path(__file__).resolve().parent

load_dotenv(PACKAGE_DIR / ".env")


def _require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing required env var: {name}")
    return value


def _pkg_file(name: str) -> str:
    return str(PACKAGE_DIR / name)


TELEGRAM_BOT_TOKEN = _require("TELEGRAM_BOT_TOKEN")
ANTHROPIC_API_KEY = _require("ANTHROPIC_API_KEY")

ALLOWED_TELEGRAM_USER_IDS = [
    int(uid.strip())
    for uid in os.environ.get("ALLOWED_TELEGRAM_USER_IDS", "").split(",")
    if uid.strip()
]

DEFAULT_TIMEZONE = os.environ.get("DEFAULT_TIMEZONE", "Asia/Seoul")
GOOGLE_CREDENTIALS_PATH = (
    os.environ.get("GOOGLE_CREDENTIALS_PATH") or _pkg_file("credentials.json")
)
GOOGLE_TOKEN_PATH = os.environ.get("GOOGLE_TOKEN_PATH") or _pkg_file("token.json")
CALENDAR_ID = os.environ.get("CALENDAR_ID", "primary")
DB_PATH = os.environ.get("DB_PATH") or _pkg_file("assistant.db")
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-haiku-4-5")
HISTORY_LIMIT = int(os.environ.get("HISTORY_LIMIT", "40"))
