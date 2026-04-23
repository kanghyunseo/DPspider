"""Environment configuration loader.

All file paths (credentials, token, DB, .env) resolve relative to the
package directory by default, so the bot works regardless of CWD.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

PACKAGE_DIR = Path(__file__).resolve().parent

load_dotenv(PACKAGE_DIR / ".env", override=True)


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
# If set, reports are uploaded into this Drive folder. If not set,
# they go to the root of My Drive.
DRIVE_FOLDER_ID = os.environ.get("DRIVE_FOLDER_ID")

# --- Airwallex (optional, for weekly finance summary) ---
# https://www.airwallex.com/docs → API Keys (Client ID + API Key)
# If unset, the weekly report simply omits the finance section.
AIRWALLEX_CLIENT_ID = os.environ.get("AIRWALLEX_CLIENT_ID")
AIRWALLEX_API_KEY = os.environ.get("AIRWALLEX_API_KEY")
AIRWALLEX_BASE_URL = os.environ.get(
    "AIRWALLEX_BASE_URL", "https://api.airwallex.com"
)

# --- Weekly report scheduler (calendar + finance) ---
# Default: every Monday 09:00 KST. Reports cover the PREVIOUS week
# (last Mon 00:00 → last Sun 23:59:59).
WEEKLY_REPORT_DAY = os.environ.get("WEEKLY_REPORT_DAY", "mon")
WEEKLY_REPORT_HOUR = int(os.environ.get("WEEKLY_REPORT_HOUR", "9"))
WEEKLY_REPORT_MINUTE = int(os.environ.get("WEEKLY_REPORT_MINUTE", "0"))

# --- Trends report scheduler (국가별 F&B 트렌드 브리프) ---
# Default: every Monday 09:00 KST.
TRENDS_REPORT_DAY = os.environ.get("TRENDS_REPORT_DAY", "mon")
TRENDS_REPORT_HOUR = int(os.environ.get("TRENDS_REPORT_HOUR", "9"))
TRENDS_REPORT_MINUTE = int(os.environ.get("TRENDS_REPORT_MINUTE", "0"))

# --- Daily briefing (every morning) ---
# 오늘 일정 + 오늘 마감 task + 지연 task. 0/0 으로 두면 비활성화.
DAILY_BRIEFING_HOUR = int(os.environ.get("DAILY_BRIEFING_HOUR", "9"))
DAILY_BRIEFING_MINUTE = int(os.environ.get("DAILY_BRIEFING_MINUTE", "0"))
DAILY_BRIEFING_ENABLED = (
    os.environ.get("DAILY_BRIEFING_ENABLED", "true").lower() == "true"
)

# --- Meeting reminders ---
# Calendar 일정 시작 N분 전에 텔레그램으로 알림. 0이면 비활성화.
MEETING_REMINDER_LEAD_MINUTES = int(
    os.environ.get("MEETING_REMINDER_LEAD_MINUTES", "30")
)
# 알림 체크 주기 (분). lead time 보다 작아야 함.
MEETING_REMINDER_CHECK_INTERVAL_MINUTES = int(
    os.environ.get("MEETING_REMINDER_CHECK_INTERVAL_MINUTES", "5")
)

# --- Backup ---
# assistant.db, token.json, .env 매일 백업. 로컬 디렉터리.
BACKUP_DIR = os.environ.get("BACKUP_DIR") or _pkg_file("backups")
BACKUP_RETENTION_DAYS = int(os.environ.get("BACKUP_RETENTION_DAYS", "14"))
BACKUP_HOUR = int(os.environ.get("BACKUP_HOUR", "3"))  # 03:00 KST
BACKUP_MINUTE = int(os.environ.get("BACKUP_MINUTE", "0"))

# --- Health check ---
# UptimeRobot 같은 외부 모니터의 heartbeat URL. 비우면 비활성화.
# 봇이 살아있으면 주기적으로 GET 호출 → 외부에서 봇 다운 감지 가능.
HEALTHCHECK_URL = os.environ.get("HEALTHCHECK_URL")
HEALTHCHECK_INTERVAL_MINUTES = int(
    os.environ.get("HEALTHCHECK_INTERVAL_MINUTES", "5")
)

# Countries to research for the weekly trends brief.
# Comma-separated names as they should appear in output.
TREND_COUNTRIES = [
    c.strip()
    for c in os.environ.get(
        "TREND_COUNTRIES", "싱가포르,베트남,일본,미국,인도네시아"
    ).split(",")
    if c.strip()
]

# Telegram chat id to deliver reports to. Defaults to the first entry
# of ALLOWED_TELEGRAM_USER_IDS (private chat with owner).
_WEEKLY_REPORT_CHAT_ID_RAW = os.environ.get("WEEKLY_REPORT_CHAT_ID")
WEEKLY_REPORT_CHAT_ID = (
    int(_WEEKLY_REPORT_CHAT_ID_RAW)
    if _WEEKLY_REPORT_CHAT_ID_RAW
    else (ALLOWED_TELEGRAM_USER_IDS[0] if ALLOWED_TELEGRAM_USER_IDS else None)
)
