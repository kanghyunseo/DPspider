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

# Optional: raw JSON contents passed via env var (for cloud deployments
# like Railway where mounting files is inconvenient). If set, main.py
# materializes these to the corresponding *_PATH at startup.
GOOGLE_CREDENTIALS_JSON = os.environ.get("GOOGLE_CREDENTIALS_JSON")
GOOGLE_TOKEN_JSON = os.environ.get("GOOGLE_TOKEN_JSON")

CALENDAR_ID = os.environ.get("CALENDAR_ID", "primary")
DB_PATH = os.environ.get("DB_PATH") or _pkg_file("assistant.db")
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-haiku-4-5")
HISTORY_LIMIT = int(os.environ.get("HISTORY_LIMIT", "40"))

# --- Google Drive (optional) ---
# If set, weekly reports are uploaded into this Drive folder. If not set,
# they go to the root of My Drive.
DRIVE_FOLDER_ID = os.environ.get("DRIVE_FOLDER_ID")

# --- Weekly report scheduler ---
# Cron-style: day_of_week and hour (24h) in DEFAULT_TIMEZONE.
# Default: every Friday 17:00 KST.
WEEKLY_REPORT_DAY = os.environ.get("WEEKLY_REPORT_DAY", "fri")
WEEKLY_REPORT_HOUR = int(os.environ.get("WEEKLY_REPORT_HOUR", "17"))
WEEKLY_REPORT_MINUTE = int(os.environ.get("WEEKLY_REPORT_MINUTE", "0"))

# Telegram chat id to deliver the weekly report to. Defaults to the
# first entry of ALLOWED_TELEGRAM_USER_IDS (private chat with owner).
_WEEKLY_REPORT_CHAT_ID_RAW = os.environ.get("WEEKLY_REPORT_CHAT_ID")
WEEKLY_REPORT_CHAT_ID = (
    int(_WEEKLY_REPORT_CHAT_ID_RAW)
    if _WEEKLY_REPORT_CHAT_ID_RAW
    else (ALLOWED_TELEGRAM_USER_IDS[0] if ALLOWED_TELEGRAM_USER_IDS else None)
)
